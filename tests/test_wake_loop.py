"""The "hey Void" loop (Wake.loop) at rest: while it shouldn't listen (hidden, the mic busy, he's quiet and the wake
word is off) it waits without waking up every 0.2 s, and still starts listening right away (within 0.25 s) when it
should again: shown (/api/sleep off), the wake word switched on (/api/settings), the mic let go (/api/listen ends),
he starts talking with barge-in on (/api/speaking), the follow-up window opening after he stops. Switched off
entirely, the loop ends promptly. The real request handler on a local port; the mic session is a stand-in.

And Wake.check's follow-up gate: a dropped follow-up tells the page (gate_drop, with the log line); the owner's
follow-up is kept; voice_gate off takes follow-ups as before; nothing is scored or enrolled as anyone's voice.

Every burst Wake.check, Wake.heard and Wake.stop_in hear is kept or dropped by gate.judge alone, handed a gate.Burst;
each verdict logs one '[void] <stamp> <why> (<kind>): <said>' line through server.verdict_out, the heard line before it
is stamped too, and only a dropped follow-up also tells the page (gate_drop). run_whisper_heard keeps only the segments gate.sure passes and blanks nothing.

    python3 -m unittest discover -s tests
"""
import collections
import contextlib
import http.client
import io
import json
import re
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import suite_data  # noqa: E402  (Void's data folder: the suite's own, set before server.py settles it)
from fakes import hiss, ears  # noqa: E402

try:
    import server
    from http.server import ThreadingHTTPServer
except Exception as e:  # noqa: BLE001
    server, IMPORT_ERR = None, e
else:
    IMPORT_ERR = None

PROMPT = 0.25            # how soon a session must start (or the loop end) once it should
OFF = {"wake_word": False, "barge_in": False, "follow_up": 0}


@unittest.skipIf(server is None, f"server.py doesn't import here: {IMPORT_ERR}")
class WakeLoop(unittest.TestCase):
    def setUp(self):
        W = server.Wake
        self._saved = {k: W.__dict__[k] for k in ("thread", "speaking_until", "follow_from", "follow_until",
                                                    "follow_on", "cut", "asleep")}
        self.addCleanup(self._restore)
        W.thread, W.asleep, W.cut = None, False, None
        W.speaking_until = W.follow_from = W.follow_until = 0.0
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.orig_should_run = W.__dict__["should_run"].__func__
        self.orig_wanted = W.__dict__["wanted"].__func__
        self.sessions = []                       # monotonic start time of each mic session
        self.counts = {"should_run": 0, "wanted": 0}
        self.counting = False
        self.release = threading.Event()         # lets a stand-in /api/listen recording finish
        test = self

        def should_run(cls):
            if test.counting and threading.current_thread() is cls.thread:
                test.counts["should_run"] += 1
            return test.orig_should_run(cls)

        def wanted(cls):
            if test.counting and threading.current_thread() is cls.thread:
                test.counts["wanted"] += 1
            return test.orig_wanted(cls)

        def session(cls):                        # "the mic is open" until it shouldn't be
            test.sessions.append(time.monotonic())
            while test.orig_should_run(cls):
                time.sleep(0.01)

        def listen_run(ls, emit):                # a push-to-talk recording held until the test lets go
            test.release.wait(5)

        for p in (mock.patch.dict(server.CFG, OFF),
                  mock.patch.object(server, "CONF_PATH", Path(tmp.name) / "config.json"),
                  mock.patch.object(server, "state_info", lambda: {}),
                  mock.patch.object(server, "whisper", lambda: None),
                  mock.patch.object(server.Speaker, "stop", classmethod(lambda cls: None)),
                  mock.patch.object(server.Wake, "should_run", classmethod(should_run)),
                  mock.patch.object(server.Wake, "wanted", classmethod(wanted)),
                  mock.patch.object(server.Wake, "session", classmethod(session)),
                  mock.patch.object(server.Listen, "run", listen_run)):
            p.start()
            self.addCleanup(p.stop)
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        self.srv.daemon_threads = True
        threading.Thread(target=self.srv.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)
        self.addCleanup(self._shutdown_loop)     # (runs first)

    def _restore(self):
        for k, v in self._saved.items():
            setattr(server.Wake, k, v)

    def _shutdown_loop(self):
        self.release.set()
        server.CFG.update(OFF)
        getattr(server.Wake, "nudge", lambda: None)()        # (CFG changed behind save_config's back)
        t = server.Wake.thread
        if t:
            t.join(2)

    def post(self, path, body=None, wait=True):
        c = http.client.HTTPConnection("127.0.0.1", self.srv.server_address[1], timeout=10)
        c.request("POST", path, body=json.dumps(body or {}),
                  headers={"X-Void-Token": server.TOKEN, "Content-Type": "application/json"})
        if not wait:
            return c
        r = c.getresponse()
        data = r.read()
        c.close()
        self.assertEqual(r.status, 200, data)
        return data

    def start(self, **cfg):
        """Settings as given, then the loop started as the server does (Wake.ensure)."""
        self.t_start = time.monotonic()
        server.CFG.update(cfg)
        server.Wake.ensure()
        self.assertTrue(server.Wake.thread and server.Wake.thread.is_alive())

    def idle(self, settle=0.25):
        """Let the loop find it shouldn't run (and any session end)."""
        time.sleep(settle)
        self.assertFalse(server.Wake.should_run())

    def assert_session_soon(self, t0, budget=PROMPT, what=""):
        n = len(self.sessions)
        deadline = t0 + budget + 0.5
        while time.monotonic() < deadline and not [s for s in self.sessions if s >= t0]:  # noqa: B023
            time.sleep(0.005)
        got = [s for s in self.sessions if s >= t0]
        self.assertTrue(got, f"no session after {what}")
        self.assertLessEqual(got[0] - t0, budget, f"session started {got[0] - t0:.3f}s after {what}")
        return n

    # ---- 1. no busy-polling at rest
    def test_waits_without_polling_while_asleep(self):
        self.start(wake_word=True)
        self.post("/api/sleep", {"on": True})
        self.idle()
        self.counting = True
        time.sleep(1.0)
        self.counting = False
        c = self.counts
        self.assertLessEqual(c["should_run"], 2, f"should_run checked {c['should_run']}x in 1 s while asleep")
        self.assertLessEqual(c["wanted"], 2, f"wanted checked {c['wanted']}x in 1 s while asleep")

    def test_waits_without_polling_while_wake_word_off(self):
        self.start(barge_in=True)                # wanted, but nothing to listen for while he's quiet
        self.idle()
        self.counting = True
        time.sleep(1.0)
        self.counting = False
        self.assertLessEqual(self.counts["should_run"], 2, f"should_run checked {self.counts['should_run']}x in 1 s")

    # ---- 2. every way back to "should run" starts a session promptly
    def test_unsleeping_starts_a_session(self):
        self.start(wake_word=True)
        self.assert_session_soon(self.t_start, PROMPT, "the loop starting")
        self.post("/api/sleep", {"on": True})
        self.idle()
        t0 = time.monotonic()
        self.post("/api/sleep", {"on": False})
        self.assert_session_soon(t0, what="/api/sleep off")

    def test_enabling_wake_word_in_settings_starts_a_session(self):
        self.start(barge_in=True)
        self.idle()
        self.assertEqual(self.sessions, [])
        t0 = time.monotonic()
        self.post("/api/settings", {"wake_word": True})
        self.assert_session_soon(t0, what="settings wake_word on")

    def test_enabling_wake_word_from_fully_off_starts_a_session(self):
        t0 = time.monotonic()
        self.post("/api/settings", {"wake_word": True})   # (no loop yet: settings starts it)
        self.assert_session_soon(t0, what="settings wake_word on (loop not running)")

    def test_mic_let_go_starts_a_session(self):
        self.start(wake_word=True)
        self.assert_session_soon(self.t_start, PROMPT, "the loop starting")
        c = self.post("/api/listen", {"mode": "ptt"}, wait=False)
        self.addCleanup(c.close)
        deadline = time.monotonic() + 3
        while not server.Listen.lock.locked() and time.monotonic() < deadline:
            time.sleep(0.005)
        self.assertTrue(server.Listen.lock.locked())
        self.idle()
        t0 = time.monotonic()
        self.release.set()                       # the recording ends: /api/listen lets go of the mic
        r = c.getresponse()
        r.read()
        self.assertFalse(server.Listen.lock.locked())
        self.assert_session_soon(t0, what="the Listen lock released")

    def test_speaking_with_barge_in_starts_a_session(self):
        self.start(barge_in=True)
        self.idle()
        t0 = time.monotonic()
        self.post("/api/speaking", {"on": True})
        self.assert_session_soon(t0, what="/api/speaking on (barge-in)")

    def test_speaking_without_barge_in_does_not(self):
        self.start(follow_up=4)                  # wanted only for the follow-up window
        self.idle()
        self.post("/api/speaking", {"on": True})
        time.sleep(0.4)
        self.assertEqual(self.sessions, [])

    def test_follow_up_window_opening_starts_a_session(self):
        self.start(follow_up=4)
        self.idle()
        self.post("/api/speaking", {"on": True})
        time.sleep(0.2)
        self.post("/api/speaking", {"on": False})        # stops talking: window opens 0.8 s from now
        opens = server.Wake.follow_from
        self.assertGreater(server.Wake.follow_until, opens)
        self.assertEqual(self.sessions, [])
        self.assert_session_soon(opens, what="the follow-up window opening")

    def test_talking_until_sets_follow_window_directly(self):  # (what the server-side Speaker calls per sentence)
        self.start(follow_up=4)
        self.idle()
        server.Wake.talking_until(time.monotonic() + 0.3)
        self.assert_session_soon(server.Wake.follow_from, what="Wake.talking_until's follow-up window")

    # ---- 3. switched off: the loop ends promptly, even while waiting
    def test_switching_everything_off_ends_the_loop(self):
        self.start(barge_in=True)
        self.idle()
        t = server.Wake.thread
        t0 = time.monotonic()
        self.post("/api/settings", {"barge_in": False, "wake_word": False, "follow_up": 0})
        t.join(PROMPT + 1.0)
        self.assertFalse(t.is_alive(), "the wake loop is still running")
        self.assertLessEqual(time.monotonic() - t0, PROMPT, f"took {time.monotonic() - t0:.3f}s to end")

    def test_switching_off_while_asleep_ends_the_loop(self):
        self.start(wake_word=True)
        self.post("/api/sleep", {"on": True})
        self.idle()
        t = server.Wake.thread
        t0 = time.monotonic()
        self.post("/api/settings", {"wake_word": False})
        t.join(PROMPT + 1.0)
        self.assertFalse(t.is_alive(), "the wake loop is still running")
        self.assertLessEqual(time.monotonic() - t0, PROMPT, f"took {time.monotonic() - t0:.3f}s to end")


# ---- the follow-up gate in Wake.check
# Wake.check is fed fixture clips with speech detection and Whisper stood in for (Whisper is "sure" of every clip).

ROOT = Path(__file__).resolve().parent.parent
SCENES = ROOT / "tests" / "fixtures" / "scenes"
SAID = {"room_music.wav": "take me down to the river tonight where the summer lights are shining bright",
        "you_overlap.wav": "Yeah, move them, and while you're at it, make a new folder called summer for them.",
        "you_hey_void.wav": "Hey Void, open my Downloads folder instead."}
STAMP = r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d"   # what server.hear_out puts after '[void] '


def clip(name):
    import wave
    with wave.open(str(SCENES / name), "rb") as w:
        return w.readframes(w.getnframes())


@unittest.skipIf(server is None, f"server.py doesn't import here: {IMPORT_ERR}")
class FollowUpGate(unittest.TestCase):
    def setUp(self):
        W = server.Wake
        saved = {k: W.__dict__[k] for k in ("speaking_until", "follow_from", "follow_until")}
        self.addCleanup(lambda: [setattr(W, k, v) for k, v in saved.items()])
        self.learned = []
        test = self
        self.heard_text = {}

        def said(pcm):
            return test.heard_text[pcm]
        gate_cfg = {"voice_gate": server.DEFAULTS["voice_gate"]}
        for p in (mock.patch.dict(server.CFG, gate_cfg),     # (the defaults, whatever this machine's config says)
                  mock.patch.object(server, "SPOKEN", type(server.SPOKEN)()),
                  mock.patch.object(server.Speaker, "idle", classmethod(lambda cls: True)),
                  mock.patch.object(server.MicAuto, "learn", classmethod(lambda cls, pcm: test.learned.append(pcm)))):
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(ears(server, said).close)
        self.q = server.BUS.sub()
        self.addCleanup(server.BUS.unsub, self.q)

    def check(self, name, follow, said=None):
        """Wake.check on fixture `name`, heard (as `said`, else SAID[name]) inside the follow-up window or not.
        → (pcm, bus events, '[void]' log lines)."""
        pcm = clip(name)
        self.heard_text[pcm] = SAID[name] if said is None else said
        now = time.monotonic()
        server.Wake.speaking_until = 0.0
        server.Wake.follow_from, server.Wake.follow_until = (now - 1, now + 5) if follow else (0.0, 0.0)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            server.Wake.check(pcm, now)
        events = []
        while not self.q.empty():
            events.append(self.q.get_nowait())
        return pcm, events, [ln for ln in err.getvalue().splitlines() if ln.startswith("[void]")]

    def judged(self):
        """Spy on gate.judge. → the list each call's first argument (the burst judged) is appended to."""
        try:
            import gate
        except Exception as e:  # noqa: BLE001
            self.fail(f"app/gate.py doesn't import: {e}")
        calls = []
        real = gate.judge
        p = mock.patch.object(gate, "judge", lambda *a, **k: calls.append(a[0] if a else k.get("b")) or real(*a, **k))
        p.start()
        self.addCleanup(p.stop)
        return calls

    @staticmethod
    def verdicts(log):
        """The verdict lines in `log`: '[void] <stamp> <why> (<kind>): <said>', <why> any reason gate.WHY names."""
        import gate
        return [(w, ln) for ln in log for w in gate.WHY if re.match(rf"\[void\] {STAMP} {re.escape(w)} \([a-z]+\): ", ln)]

    def wakes(self, events):
        return [e for e in events if e.get("t") == "wake"]

    def test_a_dropped_follow_up_tells_the_page(self):
        _, events, log = self.check("room_music.wav", follow=True, said="Thank you.")
        self.assertEqual(self.wakes(events), [], f"a filler taken as a request: {events}\n{log}")
        drops = [e for e in events if e.get("t") == "gate_drop"]
        self.assertEqual(len(drops), 1, f"no single gate_drop published: {events}\n{log}")
        shown = [v for v in drops[0].values() if isinstance(v, str) and v != "gate_drop" and v.strip()]
        self.assertTrue(any(v in ln and "Thank you" in ln for v in shown for ln in log),
                        f"gate_drop doesn't carry the log line of the drop: {drops[0]}\n{log}")

    def test_owner_follow_up_is_kept(self):
        _, events, log = self.check("you_overlap.wav", follow=True)
        got = self.wakes(events)
        self.assertTrue(len(got) == 1 and got[0].get("follow"), f"the owner's follow-up not kept: {events}\n{log}")
        self.assertFalse([e for e in events if e.get("t") == "gate_drop"], f"gate_drop on a kept clip: {events}")

    def test_each_follow_up_is_judged_once_as_a_burst(self):
        import gate
        calls = self.judged()
        self.check("you_overlap.wav", follow=True)
        self.assertEqual(len(calls), 1, f"gate.judge called {len(calls)}x on one follow-up")
        b = calls[0]
        self.assertIsInstance(b, gate.Burst, f"gate.judge not handed a gate.Burst: {b!r}")
        self.assertEqual((b.kind, b.text), ("follow", SAID["you_overlap.wav"]), f"not judged as the follow-up heard: {b!r}")
        self.assertIsInstance(b.heard, server.Heard, f"judged without Whisper's confidence: {b!r}")

    def test_every_heard_line_and_verdict_line_is_stamped_with_the_time(self):
        for name, follow in (("you_overlap.wav", True), ("room_music.wav", False)):     # (one kept, one dropped)
            with self.subTest(name):
                _, events, log = self.check(name, follow=follow)
                said = [ln for ln in log if re.match(r"\[void\] (?:\S+ \S+ )?heard ", ln) or SAID[name][:30] in ln]
                self.assertEqual(len(said), 2, f"{name}: not one heard line and one verdict line:\n" + "\n".join(log))
                for ln in said:
                    self.assertRegex(ln, rf"^\[void\] {STAMP} ", "a hearing line without its time stamp")

    def test_wake_word_clip_is_judged_once_and_taken(self):
        import gate
        calls = self.judged()
        for follow in (False, True):
            with self.subTest(in_follow_window=follow):
                calls.clear()
                pcm, events, log = self.check("you_hey_void.wav", follow=follow)
                self.assertEqual(len(self.wakes(events)), 1, f"wake word not taken: {events}\n{log}")
                self.assertEqual(len(calls), 1, f"gate.judge called {len(calls)}x on one wake-word clip")
                self.assertIsInstance(calls[0], gate.Burst, f"gate.judge not handed a gate.Burst: {calls[0]!r}")
                if not follow:
                    self.assertEqual(calls[0].kind, "wake", f"a wake-word clip outside the follow-up window not "
                                                            f"judged as a 'wake' burst: {calls[0]!r}")

    def test_wake_word_clip_tunes_the_mic(self):
        pcm, events, log = self.check("you_hey_void.wav", follow=False)
        self.assertTrue(self.learned == [pcm], f"MicAuto.learn got {len(self.learned)} clip(s), not the wake-word clip: {log}")

    def test_each_verdict_logs_one_line_with_its_reason_and_what_was_heard(self):
        for name, follow, why in (("you_overlap.wav", True, "kept"), ("room_music.wav", False, "no wake word"),
                                  ("you_hey_void.wav", False, "kept")):
            with self.subTest(name=name, in_follow_window=follow):
                pcm, events, log = self.check(name, follow=follow)
                got = self.verdicts(log)
                self.assertEqual([w for w, _ in got], [why], f"{name}: not one '{why}' verdict line:\n" + "\n".join(log))
                self.assertIn(SAID[name][:30].lower(), got[0][1].lower(),
                              f"{name}: the verdict line doesn't say what was heard: {got[0][1]!r}")

    def test_only_a_dropped_follow_up_tells_the_page(self):
        for name, follow, said, told in (("room_music.wav", True, "Thank you.", 1), ("room_music.wav", False, None, 0),
                                         ("you_overlap.wav", True, None, 0)):
            with self.subTest(name=name, in_follow_window=follow):
                _, events, log = self.check(name, follow=follow, said=said)
                drops = [e for e in events if e.get("t") == "gate_drop"]
                self.assertEqual(len(drops), told, f"{name}: {len(drops)} gate_drop(s), not {told}: {events}\n{log}")

    # ---- a burst begun over him, peeked at for a stop phrase, and the quick listen for his name
    STOP = "Stop, stop, that's not what I asked for."

    def peek(self, name, said):
        """Wake.stop_in on fixture `name`, heard as `said`, while he talks. → (its answer, bus events, '[void]' lines)."""
        pcm = clip(name)
        self.heard_text[pcm] = said
        server.Wake.speaking_until = time.monotonic() + 5
        server.Wake.follow_from = server.Wake.follow_until = 0.0
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            stopped = server.Wake.stop_in(pcm)
        events = []
        while not self.q.empty():
            events.append(self.q.get_nowait())
        return stopped, events, [ln for ln in err.getvalue().splitlines() if ln.startswith("[void]")]

    def test_a_stop_said_over_him_is_judged_as_a_peek_and_stops_him(self):
        import gate
        calls = self.judged()
        stopped, events, log = self.peek("you_stop.wav", self.STOP)
        self.assertEqual(len(calls), 1, f"gate.judge called {len(calls)}x on one peek")
        self.assertIsInstance(calls[0], gate.Burst, f"gate.judge not handed a gate.Burst: {calls[0]!r}")
        self.assertEqual(calls[0].kind, "peek", f"a burst peeked at while he talks not judged as a 'peek': {calls[0]!r}")
        self.assertTrue(stopped, f"a stop phrase said over him didn't stop him:\n{log}")
        self.assertEqual([e for e in events if e.get("t") == "barge"], [{"t": "barge", "listen": False, "text": ""}],
                         f"no single plain barge published: {events}")
        self.assertEqual([w for w, _ in self.verdicts(log)], ["kept"], "the stop not logged as one kept verdict:\n"
                         + "\n".join(log))

    def test_anything_else_said_over_him_is_dropped_by_the_peek(self):
        stopped, events, log = self.peek("you_overlap.wav", SAID["you_overlap.wav"])
        self.assertFalse(stopped, "a burst with no stop phrase in it stopped him")
        self.assertEqual([e for e in events if e.get("t") == "barge"], [], f"barge published without a stop: {events}")
        self.assertEqual([w for w, _ in self.verdicts(log)], ["while talking"],
                         "not logged as one 'while talking' verdict:\n" + "\n".join(log))

    def test_the_quick_listen_for_his_name_is_judged_as_a_wake_burst(self):
        import gate
        calls = self.judged()
        pcm = clip("you_hey_void.wav")
        self.heard_text[pcm] = SAID["you_hey_void.wav"]
        server.Wake.speaking_until = server.Wake.follow_from = server.Wake.follow_until = 0.0
        with contextlib.redirect_stderr(io.StringIO()):
            said = server.Wake.heard(pcm)
        self.assertEqual(len(calls), 1, f"gate.judge called {len(calls)}x on one quick listen")
        self.assertIsInstance(calls[0], gate.Burst, f"gate.judge not handed a gate.Burst: {calls[0]!r}")
        self.assertEqual(calls[0].kind, "wake", f"the quick listen not judged as a 'wake' burst: {calls[0]!r}")
        self.assertEqual(said, SAID["you_hey_void.wav"], "the quick listen didn't hand back what was heard")

    def test_gate_switched_off_takes_room_music_as_before(self):
        server.CFG["voice_gate"] = False
        _, events, log = self.check("room_music.wav", follow=True)
        self.assertEqual(len(self.wakes(events)), 1, f"voice_gate off but the follow-up wasn't taken: {events}\n{log}")
        self.assertFalse([e for e in events if e.get("t") == "gate_drop"], f"gate_drop with voice_gate off: {events}")

    def test_listen_clip_tunes_the_mic(self):
        pcm = clip("you_answer.wav")

        class FakeMic:                           # the clip, 0.1 s a read, then the recorder ends
            def __init__(self):
                self.left = pcm

            def read(self, s):
                if not self.left:
                    raise EOFError
                n = int(server.RATE * 2 * s)
                out, self.left = self.left[:n], self.left[n:]
                return out

            def close(self):
                pass

            def err(self):
                return ""

        events = []
        self.heard_text = collections.defaultdict(lambda: "Move them into Pictures, please.")
        with mock.patch.object(server, "open_clean_mic", lambda: (FakeMic(), "fake mic", b"")), \
                contextlib.redirect_stderr(io.StringIO()):
            server.Listen("ptt").run(lambda **ev: events.append(ev))
        self.assertEqual(len(self.learned), 1, f"MicAuto.learn not called once on the Listen clip: {events[-3:]}")

    # ---- a follow-up after a lead-in, and one begun over him
    LEAD_IN = 3.0                                # seconds of room before the owner starts a follow-up

    def check_pcm(self, pcm, said, follow):
        """Wake.check on `pcm`, heard as `said`, inside the follow-up window or not. → (bus events, '[void]' log lines)."""
        self.heard_text[pcm] = said
        now = time.monotonic()
        server.Wake.speaking_until = 0.0
        server.Wake.follow_from, server.Wake.follow_until = (now - 1, now + 5) if follow else (0.0, 0.0)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            server.Wake.check(pcm, now)
        events = []
        while not self.q.empty():
            events.append(self.q.get_nowait())
        return events, [ln for ln in err.getvalue().splitlines() if ln.startswith("[void]")]

    def test_owner_follow_up_after_seconds_of_lead_in_is_kept(self):
        pcm = hiss(self.LEAD_IN, 7) + clip("you_overlap.wav")
        events, log = self.check_pcm(pcm, SAID["you_overlap.wav"], follow=True)
        got = self.wakes(events)
        self.assertTrue(len(got) == 1 and got[0].get("follow"),
                        f"the owner's follow-up after {self.LEAD_IN:.0f} s of lead-in was not kept: {events}\n{log}")
        self.assertFalse([e for e in events if e.get("t") == "gate_drop"], f"gate_drop on the owner's follow-up: {log}")

    def test_reply_begun_over_him_is_kept_as_a_follow_up(self):
        """You start answering in his last words and carry on (ran on): the burst opened on his echo, as the canceller
        leaves it, and is still your follow-up."""
        import array
        his = array.array("h", clip("void_question.wav"))
        his = array.array("h", (x // 10 for x in his)).tobytes()     # his echo 20 dB down: enough to open a burst
        you = clip("you_overlap.wav")
        pcm, said = his + you, SAID["you_overlap.wav"]
        self.heard_text = collections.defaultdict(lambda: said)
        W, now = server.Wake, time.monotonic()
        at = now - len(pcm) / (server.RATE * 2)                      # (when the burst's first sample was caught)
        W.speaking_until = at + len(his) / (server.RATE * 2)
        W.follow_from = W.speaking_until + server.ECHO_TAIL
        W.follow_until = W.follow_from + 4
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            W.check(pcm, at + 0.5, ended=now - 0.3, at=at)
        events = []
        while not self.q.empty():
            events.append(self.q.get_nowait())
        got = self.wakes(events)
        self.assertTrue(len(got) == 1 and got[0].get("follow"),
                        f"the owner's reply begun over him was not kept: {events}\n{err.getvalue()}")

@unittest.skipIf(server is None, f"server.py doesn't import here: {IMPORT_ERR}")
class VerdictOut(unittest.TestCase):
    """server.verdict_out: one stderr line per verdict, and a dropped follow-up also tells the page."""

    def setUp(self):
        self.q = server.BUS.sub()
        self.addCleanup(server.BUS.unsub, self.q)

    def out(self, keep, why, act, said, kind):
        import gate
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            server.verdict_out(gate.Verdict(keep, why, act, said if keep else ""), said, kind)
        events = []
        while not self.q.empty():
            events.append(self.q.get_nowait())
        return events, err.getvalue().splitlines()

    def test_one_stamped_line_per_verdict_with_its_reason_kind_and_what_was_heard(self):
        said = "take me down to the river tonight"
        for keep, why, act, kind in ((False, "low confidence", "drop", "follow"),
                                     (True, "kept", "follow", "follow"),
                                     (False, "no wake word", "drop", "wake")):
            with self.subTest(why=why, kind=kind):
                t0 = time.strftime("%Y-%m-%d %H:%M:%S")
                _, lines = self.out(keep, why, act, said, kind)
                self.assertEqual(len(lines), 1, f"{len(lines)} stderr lines for one verdict: {lines}")
                m = re.match(rf"^\[void\] ({STAMP}) {re.escape(why)} \({kind}\): {re.escape(said)}$", lines[0])
                self.assertIsNotNone(m, f"not '[void] <stamp> <why> (<kind>): <said>': {lines[0]!r}")
                self.assertTrue(t0 <= m.group(1) <= time.strftime("%Y-%m-%d %H:%M:%S"), f"not stamped now: {lines[0]!r}")

    def test_only_a_dropped_follow_up_publishes_gate_drop(self):
        said = "take me down to the river tonight"
        for keep, why, act, kind, told in ((False, "low confidence", "drop", "follow", 1),
                                           (True, "kept", "follow", "follow", 0),
                                           (False, "no wake word", "drop", "wake", 0),
                                           (False, "noise", "drop", "listen", 0),
                                           (False, "while talking", "drop", "over", 0)):
            with self.subTest(why=why, kind=kind):
                events, _ = self.out(keep, why, act, said, kind)
                drops = [e for e in events if e.get("t") == "gate_drop"]
                self.assertEqual(len(drops), told, f"{len(drops)} gate_drop(s) for a {kind} verdict '{why}', not {told}")


@unittest.skipIf(server is None, f"server.py doesn't import here: {IMPORT_ERR}")
class WhisperHeard(unittest.TestCase):
    """run_whisper_heard keeps the segments gate.sure passes and blanks nothing: fillers reach the gate as heard."""

    def run_on(self, *texts, sure=True):
        import types
        import numpy as np
        segs = [types.SimpleNamespace(text=" " + t, avg_logprob=-0.2, compression_ratio=1.2, no_speech_prob=0.05)
                for t in texts]
        model = types.SimpleNamespace(transcribe=lambda audio, **kw: (iter(segs), None))
        with mock.patch.object(server, "whisper", lambda: model), \
                mock.patch.object(server, "_speech_seconds", lambda audio: 1.0):
            return server.run_whisper_heard(np.zeros(16000, dtype=np.float32), sure=sure)

    def test_filler_is_handed_on_as_heard(self):
        for said in ("Thank you.", "you", "Bye.", "Thanks for watching!"):
            with self.subTest(said=said):
                self.assertEqual(self.run_on(said).text, said, f"run_whisper_heard blanked {said!r}")

    def test_sure_keeps_only_what_gate_sure_passes(self):
        import gate
        seen = []
        with mock.patch.object(gate, "sure", lambda segs: seen.append(list(segs)) or segs[1:]):
            heard = self.run_on("Open the", "Downloads folder.")
        self.assertEqual(len(seen), 1, f"gate.sure called {len(seen)}x on one transcription")
        self.assertEqual(heard.text, "Downloads folder.", "the text isn't made of the segments gate.sure kept")


if __name__ == "__main__":
    unittest.main()
