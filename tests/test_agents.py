"""Tests for app/agents.py: the stream-json parser (against real captures in fixtures/) and the long-lived process.

    python3 -m unittest discover tests
"""
import http.server
import json
import os
import queue
import signal
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "app"))
sys.path.insert(0, str(HERE))
import agents  # noqa: E402
from loopback_http import LoopbackHTTPServer  # noqa: E402

FIX = HERE / "fixtures"


def rows(name):
    return [json.loads(ln) for ln in (FIX / name).read_text(encoding="utf-8").splitlines() if ln.strip()]


def replay(name, stream, on_control=None):
    """Feed a capture through a Stream the way the Brain would: a "send" row opens your message."""
    out = []
    for r in rows(name):
        if "send" in r:
            stream.ask_open = True
        elif "control" in r:
            if on_control:
                on_control(r["control"])
        elif "close_stdin" not in r:
            out += stream.feed(r)
    return out


def bus(out, t=None):
    return [e for d, e in out if d == "bus" and (t is None or e["t"] == t)]


def to_ask(out):
    return [e for d, e in out if d in ("ask", "end")]


def said(out):
    return "".join(e.get("text", "") for e in to_ask(out) if e["t"] == "delta")


# ---------------------------------------------------------------- parsing real captures
class RealCaptures(unittest.TestCase):
    def test_long_lived_subagent_follow_up_and_interrupt(self):
        s = agents.Stream()
        out = replay("longlived_followup_interrupt.jsonl", s, lambda c: s.stop_all() if c["subtype"] == "interrupt" else None)
        starts = bus(out, "sub_start")
        self.assertEqual([(e["type"], e["desc"], e["bg"]) for e in starts],
                         [("general-purpose", "Slow worker A", True), ("general-purpose", "Slow worker B", True)])
        ends = {e["id"]: e["status"] for e in bus(out, "sub_end")}
        self.assertEqual(ends, {starts[0]["id"]: "done", starts[1]["id"]: "stopped"})
        self.assertTrue(bus(out, "sub_tick"))
        # A finished while he was idle: Claude Code took a turn for it → one follow-up, said on its own
        fu = bus(out, "followup")
        self.assertEqual(len(fu), 1)
        self.assertIn("Slow worker A has finished", fu[0]["text"])
        # three messages of yours, three answers; the follow-up and the subagents' own words aren't among them
        ends_ask = [e for d, e in out if d == "end"]
        self.assertEqual(len(ends_ask), 3)
        self.assertIn("Four.", [e["text"] for e in ends_ask])
        self.assertNotIn("Slow worker A has finished", said(out))
        self.assertNotIn("I ran it in the foreground", said(out))
        self.assertEqual(s.tasks, {})

    def test_subagent_tools_never_reach_his_terminal(self):
        s = agents.Stream(oneshot=True)
        out = replay("oneshot_fg_bg.jsonl", s)
        tools = [e["name"] for e in to_ask(out) if e["t"] == "tool"]
        self.assertEqual(tools, ["Agent", "Agent"])          # his two; the subagents' Bash calls stay theirs
        starts = bus(out, "sub_start")
        self.assertEqual([(e["desc"], e["bg"]) for e in starts], [("Quick echo", False), ("Slow sleeper", True)])
        # (the subagent's own background shell isn't a little Void)
        self.assertEqual({e["status"] for e in bus(out, "sub_end")}, {"done"})
        self.assertEqual(len(bus(out, "sub_end")), 2)

    def test_one_shot_streams_both_turns_like_before(self):
        s = agents.Stream(oneshot=True)
        out = replay("oneshot_fg_bg.jsonl", s)
        self.assertIn("foreground agent returned", said(out))
        self.assertIn("Slow sleeper", said(out))          # (the follow-up turn: in the same reply, as it always was)
        self.assertEqual(len([1 for d, _ in out if d == "end"]), 1)
        self.assertEqual(bus(out, "followup"), [])

    def test_launch_errors_are_failed_minis(self):
        s = agents.Stream()
        s.ask_open = True
        out = replay("launch_errors.jsonl", s)
        starts = {e["id"]: e for e in bus(out, "sub_start")}
        ends = {e["id"]: e["status"] for e in bus(out, "sub_end")}
        failed = [starts[i] for i, st in ends.items() if st == "failed"]
        self.assertEqual(sorted(e["desc"] for e in failed), ["Bad model", "Bad type"])
        self.assertTrue(all(e["id"].startswith("launch-") for e in failed))
        throws = [e for e in starts.values() if e["desc"] == "Throws"][0]
        self.assertTrue(throws["bg"])                         # Claude Code backgrounded it on its own
        self.assertEqual(ends[throws["id"]], "done")          # (its tool was refused, but it finished)

    def test_model_switch_and_stop_task_follow_up_suppressed(self):
        s = agents.Stream()
        stopped = []

        def ctl(c):
            if c["subtype"] == "stop_task":                   # Void stops this one itself
                t = s.tasks[c["task_id"]] if c["task_id"] in s.tasks else next(iter(s.tasks.values()))
                s.void_stopped.add(t["run"])
                stopped.append(t["id"])
        out = replay("longlived_model_stoptask.jsonl", s, ctl)
        self.assertEqual(len(stopped), 1)
        ends = {e["id"]: e["status"] for e in bus(out, "sub_end")}
        self.assertEqual(ends[stopped[0]], "stopped")
        fu = [e["text"] for e in bus(out, "followup")]
        self.assertEqual(len(fu), 1)                          # Worker D's; Worker C's "it was stopped" isn't said
        self.assertIn("Worker D", fu[0])


# ---------------------------------------------------------------- whose turn is it (synthetic, same shapes)
def init():
    return {"type": "system", "subtype": "init", "session_id": "sess-1", "model": "m"}


def delta(text):
    return {"type": "stream_event", "parent_tool_use_id": None,
            "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": text}}}


PEER = {"kind": "peer"}


def result(text, run=None, origin=None):
    o = {"type": "result", "subtype": "success", "is_error": False, "result": text}
    if run:
        o["origin"] = {"kind": "task-notification", "producer": "session-task", "runId": run}
    if origin:
        o["origin"] = origin
    return o


def echo(text):
    """Your message, as --replay-user-messages sends it back once Claude Code takes it in (2.1.304)."""
    return {"type": "user", "message": {"role": "user", "content": text}, "parent_tool_use_id": None, "isReplay": True}


def started(tid, run, bg=True, **kw):
    return dict({"type": "system", "subtype": "task_started", "task_id": tid, "run_id": run, "tool_use_id": "tu-" + tid,
                 "description": "Find it", "subagent_type": "Explore", "is_backgrounded": bg, "spawn_depth": 1,
                 "task_type": "local_agent"}, **kw)


def notified(tid, status="completed"):
    return {"type": "system", "subtype": "task_notification", "task_id": tid, "status": status, "summary": "x"}


def feed(s, *objs):
    out = []
    for o in objs:
        out += s.feed(o)
    return out


class Routing(unittest.TestCase):
    def test_your_answer_streams_live(self):
        s = agents.Stream()
        s.ask_open = True
        out = s.feed(init()) + s.feed(delta("Hi "))
        self.assertEqual(out, [("session", "sess-1"), ("ask", {"t": "init", "model": "m"}),
                               ("ask", {"t": "delta", "text": "Hi "})])

    def test_held_once_a_follow_up_could_be_in_flight(self):
        s = agents.Stream()
        s.ask_open = True
        out = feed(s, init(), started("t1", "r1"), delta("Working… "), notified("t1"), delta("and done."))
        self.assertIn(("ask", {"t": "delta", "text": "Working… "}), out)       # before: live
        self.assertNotIn(("ask", {"t": "delta", "text": "and done."}), out)   # after the notification: held
        out = s.feed(result("Working… and done."))
        self.assertEqual([e.get("text") for d, e in out if d == "ask"], ["and done."])
        self.assertEqual(out[-1][0], "end")

    def test_follow_up_turn_first_while_you_wait(self):
        """You sent a message just as a subagent finished, and Claude Code took the follow-up turn first."""
        s = agents.Stream()
        feed(s, init(), started("t1", "r1"), result("Started it."))
        out = s.feed(notified("t1"))
        s.ask_open = True
        out += feed(s, init(), delta("The search found 3 files."))
        self.assertEqual(to_ask(out), [])                     # not a word of it goes out as your answer…
        out = s.feed(result("The search found 3 files.", run="r1"))
        self.assertEqual(bus(out, "followup"), [{"t": "followup", "text": "The search found 3 files.", "ok": True}])
        self.assertTrue(s.ask_open)                           # …and your message is still waiting for its own
        out = feed(s, init(), delta("Sure, "))
        self.assertIn(("ask", {"t": "delta", "text": "Sure, "}), out)          # which streams live again
        self.assertEqual(s.feed(result("Sure, done."))[-1][0], "end")

    def test_your_message_taken_into_a_peers_turn_is_answered_by_it(self):
        s = agents.Stream()
        feed(s, init(), delta("Got your note. "))             # another session's message started this turn
        s.ask_open = True
        out = feed(s, echo("And the tests?"), delta("They pass."), result("They pass.", origin=PEER))
        self.assertEqual(bus(out, "followup"), [])
        self.assertIn("They pass.", said(out))
        self.assertEqual(out[-1], ("end", {"t": "result", "text": "They pass.", "is_error": False, "cost": None,
                                           "turns": None}))
        self.assertFalse(s.ask_open)

    def test_your_message_taken_into_a_follow_up_turn_is_answered_by_it(self):
        s = agents.Stream()
        feed(s, init(), started("t1", "r1"), result("Started it."), notified("t1"), init())
        s.ask_open = True
        out = feed(s, echo("Is it done?"), delta("Yes."), result("Yes.", run="r1"))
        self.assertEqual(bus(out, "followup"), [])
        self.assertEqual([e["text"] for d, e in out if d == "end"], ["Yes."])

    def test_a_peers_turn_is_a_follow_up(self):
        s = agents.Stream()
        out = feed(s, init(), delta("Your build finished."), result("Your build finished.", origin=PEER))
        self.assertEqual(bus(out, "followup"), [{"t": "followup", "text": "Your build finished.", "ok": True}])
        self.assertEqual(to_ask(out), [])

    def test_follow_up_while_idle(self):
        s = agents.Stream()
        feed(s, init(), started("t1", "r1"), result("ok"))
        out = feed(s, notified("t1"), init(), delta("It finished."), result("It finished.", run="r1"))
        self.assertEqual([e["text"] for e in bus(out, "followup")], ["It finished."])
        self.assertEqual(to_ask(out), [])

    def test_follow_up_announced_when_its_subagent_ends(self):
        s = agents.Stream()
        feed(s, init(), started("t1", "r1"), started("t2", "r2", bg=False), result("ok"))
        out = feed(s, notified("t1"), notified("t2"))
        self.assertEqual(bus(out, "followup_soon"), [{"t": "followup_soon", "id": "t1"}])   # (not for a foreground one)
        s = agents.Stream()
        feed(s, init(), started("t1", "r1"), result("ok"))
        s.stop_all()
        self.assertEqual(bus(s.feed(notified("t1", "stopped")), "followup_soon"), [])        # nor one Void stopped

    def test_follow_up_for_a_subagent_void_stopped_is_not_said(self):
        s = agents.Stream()
        feed(s, init(), started("t1", "r1"), result("ok"))
        s.stop_all()
        out = feed(s, notified("t1", "stopped"), init(), delta("It was stopped."), result("It was stopped.", run="r1"))
        self.assertEqual(bus(out, "followup"), [])
        self.assertEqual(bus(out, "sub_end"), [{"t": "sub_end", "id": "t1", "status": "stopped"}])

    def test_a_follow_up_that_never_comes_stops_holding(self):
        s = agents.Stream()
        feed(s, init(), started("t1", "r1"), notified("t1"))
        s.ask_open = True
        feed(s, init(), result("one"))
        s.ask_open = True
        feed(s, init(), result("two"))                         # two answers later it's given up on
        s.ask_open = True
        self.assertIn(("ask", {"t": "delta", "text": "live"}), s.feed(delta("live")))

    def test_an_answer_nobody_waits_for_is_dropped(self):
        s = agents.Stream()
        self.assertEqual([d for d, _ in feed(s, init(), delta("late"), result("late"))], ["session"])

    def test_statuses_nested_and_backstop(self):
        s = agents.Stream()
        out = feed(s, started("t1", "r1"), started("n1", "rn", owned_by_subagent=True),
                   started("n2", "rn2", spawn_depth=2), started("b1", "rb", task_type="local_bash"))
        self.assertEqual([e["id"] for e in bus(out, "sub_start")], ["t1"])
        out = feed(s, notified("n1"), started("t2", "r2"), started("t3", "r3"), notified("t1", "failed"))
        self.assertEqual(bus(out, "sub_end"), [{"t": "sub_end", "id": "t1", "status": "failed"}])
        # gone from the background list without a word: it ended (as its last update said)
        out = feed(s, {"type": "system", "subtype": "task_updated", "task_id": "t2", "patch": {"status": "killed"}},
                   {"type": "system", "subtype": "background_tasks_changed", "tasks": [{"task_id": "t3"}]})
        self.assertEqual(bus(out, "sub_end"), [{"t": "sub_end", "id": "t2", "status": "stopped"}])
        self.assertEqual(list(s.tasks), ["t3"])

    def test_a_subagents_own_helpers_are_counted_on_its_little_void(self):
        """Shaped like the captures' subagent-owned tasks: owned_by_subagent + parent_task_id, ended by their own
        task_notification; background ones also sit in the background list."""
        s = agents.Stream()
        kid = lambda tid, par, bg=False, **kw: started(tid, "r" + tid, bg, **dict(
            {"owned_by_subagent": True, "parent_task_id": par, "spawn_depth": 2}, **kw))
        out = feed(s, started("t1", "r1"), started("t2", "r2"), kid("k1", "t1"), kid("k2", "t1", bg=True),
                   kid("k3", "t1", task_type="local_bash"), kid("k4", "k1", spawn_depth=3), kid("k5", "nobody"))
        self.assertEqual([e["id"] for e in bus(out, "sub_start")], ["t1", "t2"])     # no little Void of their own…
        self.assertEqual(bus(out, "sub_kids"), [{"t": "sub_kids", "id": "t1", "n": 1}, {"t": "sub_kids", "id": "t1", "n": 2},
                                                {"t": "sub_kids", "id": "t1", "n": 3}])   # …but t1's count (k4 via k1)
        self.assertEqual({t["id"]: t["kids"] for t in s.running()}, {"t1": 3, "t2": 0})
        out = feed(s, notified("k1"), notified("k3"))
        self.assertEqual(bus(out), [{"t": "sub_kids", "id": "t1", "n": 2}])           # (a shell isn't a helper)
        # a background one gone from the list without a word has ended too
        out = s.feed({"type": "system", "subtype": "background_tasks_changed", "tasks": [{"task_id": "t1"}, {"task_id": "t2"}]})
        self.assertEqual(bus(out), [{"t": "sub_kids", "id": "t1", "n": 1}])
        out = s.feed(notified("k4"))
        self.assertEqual(bus(out), [{"t": "sub_kids", "id": "t1", "n": 0}])

    def test_a_subagents_helpers_go_with_it(self):
        s = agents.Stream()
        kid = lambda tid, par: started(tid, "r" + tid, False, owned_by_subagent=True, parent_task_id=par)
        feed(s, started("t1", "r1"), kid("k1", "t1"), kid("k2", "t1"), started("t2", "r2"), kid("k3", "t2"))
        out = feed(s, notified("t1"), notified("k1"))
        self.assertEqual(bus(out, "sub_end"), [{"t": "sub_end", "id": "t1", "status": "done"}])
        self.assertEqual(bus(out, "sub_kids"), [])                                     # (no count for an ended one)
        self.assertEqual(s.kids, {"k3": ("t2", False)})
        self.assertEqual(bus(s.end_all("failed"), "sub_kids"), [])
        self.assertEqual(s.kids, {})

    def test_memory_prefix_text(self):
        self.assertIn("- tea, not coffee", agents.notes_prefix("Things…:\n- tea, not coffee"))
        self.assertIn("cleared", agents.notes_prefix(""))


# ---------------------------------------------------------------- the long-lived process (a fake claude)
class FakeStdin:
    def __init__(self, proc):
        self.proc, self.closed = proc, False

    def write(self, s):
        if self.closed or self.proc.returncode is not None:
            raise BrokenPipeError("closed")
        o = json.loads(s)
        self.proc.writes.append(o)
        if self.proc.responder:
            self.proc.responder(self.proc, o)

    def flush(self):
        pass

    def close(self):
        self.closed = True


class FakeProc:
    n = 0

    def __init__(self, cmd, responder=None, **kw):
        FakeProc.n += 1
        self.cmd, self.kw, self.pid = cmd, kw, 900000 + FakeProc.n
        self.responder, self.writes, self.returncode = responder, [], None
        self.out, self.errq, self.done = queue.Queue(), queue.Queue(), threading.Event()
        self.stdin = FakeStdin(self)
        self.stdout = iter(self.out.get, None)
        self.stderr = iter(self.errq.get, None)

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        if not self.done.wait(timeout):
            raise subprocess.TimeoutExpired("fake", timeout)
        return self.returncode

    def emit(self, *objs):
        for o in objs:
            self.out.put(json.dumps(o) + "\n")

    def exit(self, code=0, stderr=""):
        if self.returncode is not None:
            return
        if stderr:
            self.errq.put(stderr)
        self.errq.put(None)
        self.returncode = code
        self.done.set()
        self.out.put(None)

    def users(self):
        return [w["message"]["content"] for w in self.writes if w.get("type") == "user"]

    def controls(self):
        return [w["request"] for w in self.writes if w.get("type") == "control_request"]


def answer(proc, o):
    """A well-behaved claude: every message gets an answer."""
    if o.get("type") == "user":
        proc.emit(init(), delta("ok"), result("ok"))


class Harness:
    def __init__(self, responder=answer):
        self.procs, self.killed, self.events = [], [], []
        self.session = None
        self.responder = responder

        def popen(cmd, **kw):
            p = FakeProc(cmd, self.responder, **kw)
            self.procs.append(p)
            return p

        def killer(p):
            self.killed.append(p)
            p.exit(-15)

        def on_session(sid):
            self.session = sid
        self.brain = agents.Brain(lambda **ev: self.events.append(ev), on_session=on_session, popen=popen,
                                  killer=killer, watchdog=False)

    def launch(self, **kw):
        L = {"cmd": ["claude", "-p"] + (["--resume", self.session] if self.session else []), "perm": ("ask", "/x"),
             "sig": ("p1",), "session": self.session, "model": "", "notes": "", "cwd": None, "env": None}
        L.update(kw)
        return L

    def ask(self, text="hi", **kw):
        got = []
        r = self.brain.ask(self.launch(**kw), text, lambda **ev: got.append(ev))
        return r, got

    def bus(self, t):
        return [e for e in self.events if e["t"] == t]


def wait_for(cond, limit=3.0):
    end = time.time() + limit
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


class LongLived(unittest.TestCase):
    def test_one_process_for_the_whole_chat(self):
        h = Harness()
        for _ in range(3):
            r, got = h.ask()
            self.assertEqual(r, "done")
            self.assertEqual(got[-1]["t"], "result")
        self.assertEqual(len(h.procs), 1)
        self.assertTrue(h.procs[0].kw.get("start_new_session") or h.procs[0].kw.get("creationflags"))

    def test_changed_memory_notes_go_in_front_of_the_next_message_not_a_restart(self):
        h = Harness()
        h.ask("one", notes="N1")
        h.ask("two", notes="N1\n- tea")
        h.ask("three", notes="N1\n- tea")
        h.ask("four", notes="")
        u = h.procs[0].users()
        self.assertEqual(len(h.procs), 1)
        self.assertEqual(u[0], "one")                          # (the first ones are in its system prompt)
        self.assertTrue(u[1].startswith(agents.notes_prefix("N1\n- tea")) and u[1].endswith("two"))
        self.assertEqual(u[2], "three")
        self.assertTrue(u[3].startswith(agents.notes_prefix("")))

    def test_model_switches_without_a_restart(self):
        h = Harness()
        h.ask(model="")
        h.ask(model="haiku")
        h.ask(model="")
        self.assertEqual(len(h.procs), 1)
        self.assertEqual([c["model"] for c in h.procs[0].controls() if c["subtype"] == "set_model"], ["haiku", "default"])

    def test_restarts(self):
        h = Harness(lambda p, o: (answer(p, o), o.get("type") == "user" and "bg" in o["message"]["content"]
                                  and p.emit(started("t1", "r1"))))
        h.ask("start bg")
        h.ask("x", sig=("p2",))                                # other settings: wait while a subagent runs
        self.assertEqual(len(h.procs), 1)
        h.ask("y", perm=("trust", "/x"))                       # what he may do: at once, even if it stops it
        self.assertEqual(len(h.procs), 2)
        self.assertTrue(wait_for(lambda: h.procs[0] in h.killed))   # (killed on its own thread)
        self.assertEqual(h.bus("sub_end"), [{"t": "sub_end", "id": "t1", "status": "stopped"}])
        h.ask("z", perm=("trust", "/x"), sig=("p3",))          # idle now: other settings restart too
        self.assertEqual(len(h.procs), 3)

    def test_crash_mid_turn_ends_the_message_fails_its_minis_and_resumes_next_time(self):
        def crash(p, o):
            if o.get("type") == "user":
                p.emit(init(), started("t1", "r1"), delta("Looking"))
                p.exit(1, "something broke\nFatal: out of cheese\n")
        h = Harness(crash)
        r, got = h.ask("find it")
        self.assertEqual(r, "done")
        errs = [e for e in got if e["t"] == "error"]
        self.assertEqual(len(errs), 1)
        self.assertIn("stopped unexpectedly (exit code 1): Fatal: out of cheese", errs[0]["text"])
        self.assertNotIn("\n", errs[0]["text"])
        self.assertEqual(h.bus("sub_end"), [{"t": "sub_end", "id": "t1", "status": "failed"}])
        self.assertTrue(wait_for(lambda: h.procs[0] in h.killed))   # (its group goes: children may be left)
        self.assertEqual(h.brain.running(), [])
        h.responder = answer
        r, got = h.ask("again")
        self.assertEqual(len(h.procs), 2)
        self.assertEqual(h.procs[1].cmd[-2:], ["--resume", "sess-1"])
        self.assertEqual(got[-1]["t"], "result")

    def test_crash_while_idle_fails_its_minis(self):
        h = Harness(lambda p, o: (answer(p, o), o.get("type") == "user" and p.emit(started("t1", "r1"))))
        h.ask()
        h.procs[0].exit(1, "gone")
        self.assertTrue(wait_for(lambda: h.bus("sub_end")))
        self.assertEqual(h.bus("sub_end")[0]["status"], "failed")
        h.responder = answer
        self.assertEqual(h.ask()[0], "done")
        self.assertEqual(len(h.procs), 2)

    def test_old_claude_without_stream_json_input(self):
        h = Harness(lambda p, o: None)
        h.procs_exit = None

        def popen_dead(cmd, **kw):
            p = FakeProc(cmd, None, **kw)
            p.exit(1, "error: unknown option '--input-format'\n")
            h.procs.append(p)
            return p
        h.brain.popen = popen_dead
        r, got = h.ask()
        self.assertEqual(r, "unsupported")
        self.assertEqual([e for e in got if e["t"] == "error"], [])

    def test_stop_interrupts_and_falls_back_to_killing_the_group(self):
        h = Harness(lambda p, o: o.get("type") == "user" and p.emit(init(), started("t1", "r1"), delta("hmm")))
        res = {}
        th = threading.Thread(target=lambda: res.update(r=h.ask()))
        th.start()
        self.assertTrue(wait_for(lambda: h.brain.running()))
        h.brain.stop(wait=0.2)
        th.join(3)
        r, got = res["r"]
        self.assertEqual(got[-1], {"t": "stopped"})
        self.assertIn({"subtype": "interrupt"}, h.procs[0].controls())
        self.assertTrue(wait_for(lambda: h.procs[0] in h.killed))   # (killed on its own thread, after "stopped")
        self.assertEqual(h.bus("sub_end")[0]["status"], "stopped")

    def test_stop_ends_his_answer_and_spares_background_helpers(self):
        def cli(p, o):                                     # (2.1.304: an interrupt spares them only if Void said so)
            r = o.get("request") or {}
            if o.get("type") == "user":
                p.emit(init(), started("t1", "r1"), delta("hmm"))
            elif r.get("subtype") == "interrupt":
                if {"subtype": "initialize", "perTaskStopAffordance": True} not in p.controls():
                    p.emit(notified("t1", "stopped"))
                p.emit({"type": "result", "subtype": "error_during_execution", "is_error": True})
        h = Harness(cli)
        res = {}
        th = threading.Thread(target=lambda: res.update(r=h.ask()))
        th.start()
        self.assertTrue(wait_for(lambda: h.brain.running()))
        h.brain.stop(wait=0.2)
        th.join(3)
        self.assertEqual(res["r"][1][-1], {"t": "stopped"})
        time.sleep(0.3)
        self.assertEqual(h.killed, [])
        self.assertEqual([t["id"] for t in h.brain.running()], ["t1"])
        h.procs[0].emit(notified("t1"), init(), delta("Found it."), result("Found it.", run="r1"))
        self.assertTrue(wait_for(lambda: h.bus("followup")))   # (and what it finds is still said)
        self.assertEqual(h.bus("followup")[0]["text"], "Found it.")

    def test_stop_with_no_turn_under_way_ends_the_message_and_keeps_the_process(self):
        h = Harness(lambda p, o: None)                         # (no system/init: he never started on it)
        res = {}
        th = threading.Thread(target=lambda: res.update(r=h.ask()))
        th.start()
        self.assertTrue(wait_for(lambda: h.procs and h.procs[0].users()))
        h.brain.stop(wait=0.1)
        th.join(3)
        self.assertEqual(res["r"], ("done", [{"t": "stopped"}]))
        time.sleep(0.3)
        self.assertEqual(h.killed, [])
        self.assertTrue(h.brain.alive())

    def test_shutdown_stops_everything(self):
        h = Harness(lambda p, o: (answer(p, o), o.get("type") == "user" and p.emit(started("t1", "r1"))))
        h.ask()
        self.assertTrue(h.brain.shutdown(wait=True))
        self.assertIn(h.procs[0], h.killed)
        self.assertTrue(h.procs[0].stdin.closed)
        self.assertEqual(h.bus("sub_end"), [{"t": "sub_end", "id": "t1", "status": "stopped"}])
        self.assertFalse(h.brain.shutdown())

    def test_idle_shutdown(self):
        now = [0.0]
        h = Harness(lambda p, o: (answer(p, o), o.get("type") == "user" and "bg" in o["message"]["content"]
                                  and p.emit(started("t1", "r1"))))
        h.brain.clock = lambda: now[0]
        h.ask("bg")
        now[0] = 10_000
        self.assertFalse(h.brain.idle_check())                 # a subagent is still working
        h.procs[0].emit(notified("t1"))
        self.assertTrue(wait_for(lambda: not h.brain.running()))
        now[0] = 20_000
        self.assertTrue(h.brain.idle_check())
        self.assertIn(h.procs[0], h.killed)

    def test_who_is_asking(self):
        h = Harness(lambda p, o: (answer(p, o), o.get("type") == "user" and p.emit(started("t1", "r1"))))
        h.ask()
        self.assertTrue(wait_for(lambda: h.brain.running()))
        self.assertEqual(h.brain.agent_info("t1", "Explore"), {"id": "t1", "type": "Explore", "desc": "Find it"})
        self.assertIsNone(h.brain.agent_info(None))
        self.assertEqual(h.brain.agent_info("zz", "Plan"), {"id": "zz", "type": "Plan", "desc": ""})
        h.brain.set_waiting("t1", True)
        self.assertEqual(h.brain.running(), [{"id": "t1", "type": "Explore", "desc": "Find it", "waiting": True, "kids": 0}])
        h.brain.set_waiting("t1", False)
        self.assertEqual(h.bus("sub_wait"), [{"t": "sub_wait", "id": "t1", "on": True},
                                             {"t": "sub_wait", "id": "t1", "on": False}])


# ---------------------------------------------------------------- real processes: the group kill
@unittest.skipIf(os.name == "nt", "process groups are POSIX")
class GroupKill(unittest.TestCase):
    def _gone(self, pgid):
        """Nothing in the group runs any more. (macOS answers EPERM, not ESRCH, for a group left with only zombies: the
        orphan, killed, waits a few ms for launchd to reap it.)"""
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            ps = subprocess.run(["ps", "-axo", "pgid=,stat="], capture_output=True, text=True).stdout.split()
            return not any(g == str(pgid) and not st.startswith("Z") for g, st in zip(ps[::2], ps[1::2]))
        return False

    def test_kills_the_whole_group(self):
        p = subprocess.Popen(["sh", "-c", "sleep 30 & sleep 30 & wait"], **agents.own_group_kw())
        try:
            time.sleep(0.2)
            agents.kill_tree(p, grace=1)
            self.assertTrue(wait_for(lambda: self._gone(p.pid)))
        finally:
            if not self._gone(p.pid):
                os.killpg(p.pid, signal.SIGKILL)

    def test_kills_children_left_behind_by_a_dead_leader(self):
        p = subprocess.Popen(["sh", "-c", "sleep 30 & exit 0"], **agents.own_group_kw())
        try:
            p.wait(5)
            self.assertFalse(self._gone(p.pid))                # the leader's gone, its sleep isn't
            agents.kill_tree(p, grace=1)
            self.assertTrue(wait_for(lambda: self._gone(p.pid)))
        finally:
            if not self._gone(p.pid):
                os.killpg(p.pid, signal.SIGKILL)


# ---------------------------------------------------------------- what the helpers make of a tool's output
class Helpers(unittest.TestCase):
    def test_result_text_joins_text_and_marks_pictures(self):
        self.assertEqual(agents.result_text("plain"), "plain")
        blocks = [{"type": "text", "text": "a"}, {"type": "image"}, {"type": "tool_use"}, "junk"]
        self.assertEqual(agents.result_text(blocks), "a\n[image]\n\n")
        self.assertEqual(agents.result_text(None), "")

    def test_a_long_output_keeps_its_head_and_tail(self):
        out = agents.tool_output("\n".join(f"line{i}" for i in range(100))).splitlines()
        self.assertEqual(out[:40], [f"line{i}" for i in range(40)])
        self.assertEqual(out[40], "… 30 more lines …")
        self.assertEqual(out[41:], [f"line{i}" for i in range(70, 100)])
        self.assertEqual(agents.tool_output("short"), "short")

    def test_one_huge_line_is_cut_at_6000_characters(self):
        self.assertEqual(agents.tool_output("x" * 7000), "x" * 6000 + "\n…")

    @staticmethod
    def pic(data="AAAA", media="image/png", kind="base64"):
        return {"type": "image", "source": {"type": kind, "media_type": media, "data": data}}

    def test_pictures_become_data_uris_and_unusable_ones_are_left_out(self):
        got = agents.tool_images([self.pic(), self.pic("BBBB", "image/jpeg"), self.pic(media="text/plain"),
                                  self.pic(kind="url"), self.pic(data="x" * 11), {"type": "text", "text": "t"}],
                                 limit=10)
        self.assertEqual(got, ["data:image/png;base64,AAAA", "data:image/jpeg;base64,BBBB"])
        self.assertEqual(agents.tool_images("not a list"), [])

    def test_at_most_three_pictures(self):
        self.assertEqual(len(agents.tool_images([self.pic(str(i)) for i in range(5)])), 3)

    def test_the_notes_prefix_says_when_memory_was_cleared(self):
        self.assertIn("cleared your memory notes", agents.notes_prefix(""))
        self.assertIn("likes tea", agents.notes_prefix("likes tea"))


class KillTree(unittest.TestCase):
    """The process boundary is replaced: no signal reaches a real group, no real process is started."""

    class P:
        pid = 4242

        def __init__(self, hangs=False, running=True):
            self.hangs, self.running, self.waits = hangs, running, []

        def poll(self):
            return None if self.running else 0

        def wait(self, timeout=None):
            self.waits.append(timeout)
            if self.hangs:
                raise subprocess.TimeoutExpired("p", timeout)

    def test_nothing_to_kill(self):
        self.assertIsNone(agents.kill_tree(None))

    def test_term_then_kill_for_a_group_that_will_not_go(self):
        p = self.P(hangs=True)
        with mock.patch.object(agents.os, "killpg") as killpg:
            agents.kill_tree(p, grace=0.5)
        self.assertEqual(killpg.call_args_list, [mock.call(4242, signal.SIGTERM), mock.call(4242, signal.SIGKILL)])
        self.assertEqual(p.waits, [0.5, 0.5])

    def test_a_group_already_gone_is_no_error(self):
        for err in (ProcessLookupError, PermissionError):
            with mock.patch.object(agents.os, "killpg", side_effect=err):
                agents.kill_tree(self.P())

    def test_windows_kills_the_tree_of_a_running_process_only(self):
        with mock.patch.object(agents, "WIN", True), mock.patch.object(agents.subprocess, "run") as run:
            agents.kill_tree(self.P(running=False))
            run.assert_not_called()
            agents.kill_tree(self.P())
        run.assert_called_once_with(["taskkill", "/T", "/F", "/PID", "4242"], capture_output=True, creationflags=0x08000000)

    def test_own_group_arguments_per_platform(self):
        self.assertEqual(agents.own_group_kw(), {"start_new_session": True})
        with mock.patch.object(agents, "WIN", True):
            self.assertEqual(agents.own_group_kw(), {"creationflags": 0x00000200 | 0x08000000})


# ---------------------------------------------------------------- the stream events no capture holds
def user_result(content, tid="tu1", **kw):
    return {"type": "user", "message": {"role": "user", "content": content}, "parent_tool_use_id": None,
            "tool_use_id": tid, **kw}


def tool_result(tid="tu1", content="out", **kw):
    return user_result([dict({"type": "tool_result", "tool_use_id": tid, "content": content}, **kw)], tid)


class StreamEvents(unittest.TestCase):
    def open_stream(self):
        s = agents.Stream()
        s.ask_open = True
        return s

    def test_how_full_the_chat_is_comes_from_usage_and_the_biggest_window(self):
        s = self.open_stream()
        usage = {"input_tokens": 5}
        self.assertEqual(s.feed({"type": "assistant", "message": {"usage": usage, "content": []}}),
                         [("ctx", {"usage": usage})])
        res = dict(result("ok"), session_id="s9",
                   modelUsage={"a": {"contextWindow": 200000}, "b": {"contextWindow": 1000000}, "c": "junk"})
        self.assertEqual(s.feed(res)[:2], [("session", "s9"), ("ctx", {"window": 1000000})])

    def test_a_whole_message_is_sent_once_when_no_deltas_came(self):
        s = self.open_stream()
        out = s.feed({"type": "assistant", "message": {"content": ["junk", {"type": "text", "text": "Hello"}]}})
        self.assertEqual(out, [("ask", {"t": "break"}), ("ask", {"t": "delta", "text": "Hello"})])
        s.feed(delta("Hi"))
        self.assertEqual(s.feed({"type": "assistant", "message": {"content": [{"type": "text", "text": "Hi"}]}}), [])

    def test_a_new_message_breaks_the_text_and_other_stream_events_say_nothing(self):
        s = self.open_stream()
        self.assertEqual(s.feed({"type": "stream_event", "event": {"type": "message_start"}}),
                         [("ask", {"t": "break"})])
        self.assertEqual(s.feed({"type": "stream_event", "event": {"type": "content_block_start"}}), [])

    def test_a_tool_result_carries_its_pictures(self):
        s = self.open_stream()
        img = {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "AAAA"}}
        self.assertEqual(s.feed(tool_result("tu1", [img])),
                         [("ask", {"t": "toolres", "id": "tu1", "text": "[image]", "is_error": False,
                                   "images": ["data:image/png;base64,AAAA"]})])

    def test_user_rows_that_are_not_tool_results_say_nothing(self):
        s = self.open_stream()
        self.assertEqual(s.feed(user_result([{"type": "text", "text": "x"}])), [])
        self.assertEqual(s.feed(user_result("plain text")), [])

    def test_a_failed_launch_without_a_known_launch_makes_no_little_void(self):
        s = self.open_stream()
        out = feed(s, {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "tu1", "name": "Agent", "input": None}]}}, tool_result("tu1", "boom", is_error=True))
        self.assertEqual(bus(out), [])
        self.assertEqual(to_ask(out)[-1]["is_error"], True)

    def test_init_without_a_session_names_none(self):
        s = self.open_stream()
        out = s.feed({"type": "system", "subtype": "init", "model": "m"})
        self.assertEqual(out, [("ask", {"t": "init", "model": "m"})])
        self.assertTrue(s.inited and s.in_turn)

    def test_a_subagent_without_a_run_id_is_not_awaited_after_it_ends(self):
        s = agents.Stream()
        out = feed(s, started("t1", None), {"type": "system", "subtype": "task_progress", "task_id": "zz"},
                   notified("t1"))
        self.assertEqual([e["t"] for e in bus(out)], ["sub_start", "sub_end"])   # no tick for an unknown task
        self.assertEqual((s.runs, s.awaiting), ({}, {}))

    def test_a_helper_of_an_unknown_subagent_is_not_counted(self):
        s = agents.Stream()
        out = s.feed(started("k1", "rk", parent_task_id="ghost"))
        self.assertEqual((out, s.kids, s.tasks), ([], {}, {}))

    def test_a_peers_empty_turn_says_nothing(self):
        s = self.open_stream()
        out = feed(s, init(), result("   ", origin=PEER))
        self.assertEqual(bus(out, "followup"), [])


class MoreBrain(unittest.TestCase):
    def test_stop_with_no_process_is_false(self):
        self.assertFalse(Harness().brain.stop())

    def test_a_waiting_flag_for_an_unknown_subagent_is_ignored(self):
        h = Harness()
        h.brain.set_waiting("nobody", True)
        self.assertEqual(h.events, [])

    def test_another_chat_restarts_him(self):
        h = Harness()
        h.ask()
        h.ask(session="sess-1")
        self.assertEqual(len(h.procs), 1)
        h.ask(session="another")
        self.assertEqual(len(h.procs), 2)
        self.assertTrue(wait_for(lambda: h.procs[0] in h.killed))

    def test_context_events_go_to_on_ctx(self):
        h = Harness(lambda p, o: o.get("type") == "user" and p.emit(
            init(), {"type": "assistant", "message": {"usage": {"input_tokens": 7}, "content": []}}, result("ok")))
        seen = []
        h.brain.on_ctx = seen.append
        h.ask()
        self.assertEqual(seen, [{"usage": {"input_tokens": 7}}])

    def test_a_process_that_cannot_start_ends_the_message_with_the_reason(self):
        h = Harness()

        def refuse(cmd, **kw):
            raise OSError("no such file")
        h.brain.popen = refuse
        r, got = h.ask()
        self.assertEqual((r, got), ("done", [{"t": "error", "text": "couldn't start Claude Code: no such file"}]))
        self.assertFalse(h.brain.alive())
        self.assertEqual(h.brain.err, ["no such file"])

    def test_lines_that_are_not_json_are_skipped(self):
        def noisy(p, o):
            if o.get("type") == "user":
                p.out.put("\n")
                p.out.put("not json at all\n")
                p.emit(init(), delta("ok"), result("ok"))
        r, got = Harness(noisy).ask()
        self.assertEqual((r, got[-1]["t"]), ("done", "result"))

    def test_shutdown_without_waiting_kills_in_the_background(self):
        h = Harness()
        h.ask()
        self.assertTrue(h.brain.shutdown(wait=False))
        self.assertTrue(wait_for(lambda: h.procs[0] in h.killed))

    def test_shutdown_goes_on_when_the_pipe_will_not_close(self):
        h = Harness()
        h.ask()

        def broken():
            raise ValueError("closed")
        h.procs[0].stdin.close = broken
        self.assertTrue(h.brain.shutdown(wait=True))
        self.assertIn(h.procs[0], h.killed)

    def dies_at_start(self, stderr, **launch):
        h = Harness()

        def popen_dead(cmd, **kw):
            p = FakeProc(cmd, None, **kw)
            p.exit(1, stderr)
            h.procs.append(p)
            return p
        h.brain.popen = popen_dead
        return h.ask(**launch)

    def test_a_claude_that_does_not_know_partial_messages_asks_for_a_retry_without_them(self):
        r, got = self.dies_at_start("error: unknown option '--include-partial-messages'\n")
        self.assertEqual((r, [e for e in got if e["t"] == "error"]), ("retry_nopartial", []))

    def test_a_chat_claude_cannot_find_asks_for_a_fresh_start(self):
        r, got = self.dies_at_start("No conversation found with session ID: old\n", session="old")
        self.assertEqual((r, [e for e in got if e["t"] == "error"]), ("retry_fresh", []))

    def test_a_crash_with_no_message_says_so_without_a_code(self):
        r, got = self.dies_at_start("")
        self.assertEqual(r, "done")
        self.assertEqual(got[0]["text"], "Claude Code stopped unexpectedly (exit code 1) — your next message starts it again.")

    def test_a_process_that_exits_on_the_interrupt_is_stopped_not_crashed(self):
        def cli(p, o):
            if o.get("type") == "user":
                p.emit(init(), started("t1", "r1"), delta("hmm"))
            elif (o.get("request") or {}).get("subtype") == "interrupt":
                p.exit(0)
        h = Harness(cli)
        res = {}
        th = threading.Thread(target=lambda: res.update(r=h.ask()))
        th.start()
        self.assertTrue(wait_for(lambda: h.brain.running()))
        h.brain.stop(wait=5)
        th.join(3)
        r, got = res["r"]
        self.assertEqual((r, got[-1]), ("done", {"t": "stopped"}))
        self.assertEqual([e["t"] for e in got if e["t"] == "error"], [])
        self.assertEqual(h.bus("sub_end")[0]["status"], "stopped")

    def test_a_reader_that_hangs_on_a_dead_process_does_not_block_the_crash_report(self):
        def crash(p, o):
            if o.get("type") == "user":
                p.emit(init())
                p.wait = lambda timeout=None: (_ for _ in ()).throw(subprocess.TimeoutExpired("fake", timeout))
                p.out.put(None)                                # (its output ended, but it never exits)
        h = Harness(crash)
        r, got = h.ask()
        self.assertEqual(r, "done")
        self.assertEqual(got[-1]["t"], "error")
        self.assertTrue(wait_for(lambda: h.procs[0] in h.killed))

    def test_a_process_that_died_unnoticed_is_replaced_and_its_late_words_are_not_heard(self):
        h = Harness(lambda p, o: (answer(p, o), o.get("type") == "user" and "bg" in o["message"]["content"]
                                  and p.emit(started("t1", "r1"))))
        h.ask("bg")
        self.assertTrue(wait_for(lambda: h.brain.running()))
        old = h.procs[0]
        old.returncode = 1                                     # (gone, but its reader hasn't noticed)
        self.assertEqual(h.ask("again")[0], "done")
        self.assertEqual(len(h.procs), 2)
        self.assertEqual(h.bus("sub_end"), [{"t": "sub_end", "id": "t1", "status": "failed"}])
        self.assertTrue(wait_for(lambda: old in h.killed))
        old.emit(started("late", "rl"))                        # the old reader wakes up: it is not his any more
        old.out.put(None)
        time.sleep(0.2)
        self.assertEqual(h.brain.running(), [])

    def test_a_write_that_fails_on_a_warm_process_starts_a_new_one_once(self):
        h = Harness()
        h.ask()
        h.procs[0].stdin.closed = True                         # (still "alive", but takes no input)
        r, got = h.ask("again")
        self.assertEqual((r, got[-1]["t"]), ("done", "result"))
        self.assertEqual(len(h.procs), 2)
        self.assertTrue(wait_for(lambda: h.procs[0] in h.killed))
        self.assertEqual(h.procs[1].users(), ["again"])

    def test_the_watchdog_survives_a_failing_idle_check_and_runs_it_each_round(self):
        class Quit(BaseException):
            pass
        h = Harness()
        calls = []

        def boom():
            calls.append(1)
            raise RuntimeError("x")
        h.brain.idle_check = boom
        with mock.patch.object(agents.time, "sleep", side_effect=[None, None, Quit()]) as sleep:
            with self.assertRaises(Quit):
                h.brain._watch()
        self.assertEqual((len(calls), sleep.call_args_list), (2, [mock.call(20)] * 3))


# ---------------------------------------------------------------- the approval hook says who's asking
class ApproveHook(unittest.TestCase):
    def test_forwards_the_subagent(self):
        got = []

        class H(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                got.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                body = b'{"ok": true}'
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass
        srv = LoopbackHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.handle_request, daemon=True).start()
        hook = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "ls"},
                "agent_id": "t1", "agent_type": "Explore"}
        env = dict(os.environ, VOID_PORT=str(srv.server_address[1]), VOID_TOKEN="x")
        r = subprocess.run([sys.executable, str(HERE.parent / "app" / "approve.py")], input=json.dumps(hook),
                           capture_output=True, text=True, env=env, timeout=20)
        srv.server_close()
        self.assertEqual(got[0]["agent_id"], "t1")
        self.assertEqual(got[0]["agent_type"], "Explore")
        self.assertEqual(json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"], "allow")


if __name__ == "__main__":
    unittest.main()
