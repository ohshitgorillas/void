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
import fakes  # noqa: E402
from fakes import hiss, ears  # noqa: E402
from loopback_http import LoopbackThreadingHTTPServer  # noqa: E402
from test_hearing import SPK_RATE, FakePlayer, FakeRef  # noqa: E402  (the Speaker player stand-ins)

try:
    import server
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
        self._saved = {k: W.__dict__[k] for k in ("thread", "talked", "follow_on", "cut", "asleep")}
        self.addCleanup(self._restore)
        W.thread, W.asleep, W.cut = None, False, None
        W.talked = []
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
        self.srv = LoopbackThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
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
        self.post("/api/speaking", {"on": True, "left": 5})      # (quiet-replies-design.md:71: `left` is his sound)
        self.assert_session_soon(t0, what="/api/speaking on (barge-in)")

    def test_speaking_without_barge_in_does_not(self):
        self.start(follow_up=4)                  # wanted only for the follow-up window
        self.idle()
        self.post("/api/speaking", {"on": True, "left": 5})      # (quiet-replies-design.md:71, :76: no window while he sounds)
        time.sleep(0.4)
        self.assertEqual(self.sessions, [])

    def test_follow_up_window_opening_starts_a_session(self):
        self.start(follow_up=4)
        self.idle()
        self.post("/api/speaking", {"on": True, "left": 5})
        time.sleep(0.2)
        self.assertEqual(self.sessions, [])               # (quiet-replies-design.md:76: closed while he makes sound)
        opens = time.monotonic()                         # the window opens at the end of his sound (:76)
        self.post("/api/speaking", {"on": False})        # stops talking: his sound ends now (quiet-replies-design.md:71)
        posted = time.monotonic()
        self.assertGreaterEqual(server.Wake.talked[-1][1], opens, "his sound recorded as ending before the `off` post")
        self.assertLessEqual(server.Wake.talked[-1][1], posted, "his sound recorded as ending after the `off` post")
        self.assertGreater(server.Wake.talked[-1][2], opens)
        self.assert_session_soon(opens, what="the follow-up window opening")

    def test_talking_until_sets_follow_window_directly(self):  # (what the server-side Speaker calls per sentence)
        self.start(follow_up=4)
        self.idle()
        ends = time.monotonic() + 0.3
        server.Wake.talking_until(ends)
        # (quiet-replies-design.md:76: the window opens at the end of his sound, not after the ring)
        self.assert_session_soon(ends, what="Wake.talking_until's follow-up window")

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
        saved = {k: W.__dict__[k] for k in ("talked",)}
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
        server.Wake.talked = [[now - 3 - server.ECHO_TAIL, now - 1 - server.ECHO_TAIL, now + 5]] if follow else []
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
        now = time.monotonic()
        server.Wake.talked = [[now, now + 5, now + 5]]           # (no follow-up window after it)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            stopped = server.Wake.stop_in(pcm, now)
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
        server.Wake.talked = []
        with contextlib.redirect_stderr(io.StringIO()):
            said = server.Wake.heard(pcm, time.monotonic())
        self.assertEqual(len(calls), 1, f"gate.judge called {len(calls)}x on one quick listen")
        self.assertIsInstance(calls[0], gate.Burst, f"gate.judge not handed a gate.Burst: {calls[0]!r}")
        self.assertEqual(calls[0].kind, "wake", f"the quick listen not judged as a 'wake' burst: {calls[0]!r}")
        self.assertIsInstance(said, server.Heard, f"the quick listen didn't hand back a Heard: {said!r}")
        self.assertEqual(said.text, SAID["you_hey_void.wav"], "the quick listen didn't hand back what was heard")

    # ---- Wake.heard hands back the Heard itself, and Wake.check takes that Heard in place of its text
    def quick_listen(self, name, said):
        """Wake.heard on fixture `name`, heard as `said`, its first sample caught `len(pcm)` ago, its words timed.
        → (what Wake.heard returned, the words its Heard should carry, the `at` each timing was asked for, `at`)."""
        import gate
        pcm = clip(name)
        at = time.monotonic() - len(pcm) / (server.RATE * 2)
        words = tuple(gate.Word(w, at + 0.4 * i, at + 0.4 * i + 0.3) for i, w in enumerate(said.split()))
        asked = []

        def words_for(p, a):
            asked.append(a)
            return words

        server.Wake.talked = []
        with ears(server, lambda p: said, words_for=words_for), contextlib.redirect_stderr(io.StringIO()):
            got = server.Wake.heard(pcm, time.monotonic(), at)
        return got, words, asked, at

    def test_the_quick_listen_hands_back_the_heard_with_its_word_times(self):
        got, words, asked, at = self.quick_listen("you_hey_void.wav", SAID["you_hey_void.wav"])
        self.assertIsInstance(got, server.Heard, f"Wake.heard didn't hand back a Heard: {got!r}")
        self.assertEqual(got.text, SAID["you_hey_void.wav"], f"the Heard handed back isn't what was heard: {got!r}")
        self.assertEqual(asked, [at], "the quick listen wasn't timed from when its first sample was caught")
        self.assertEqual(got.words, words, f"the Heard handed back lost its word times: {got!r}")

    def test_the_quick_listen_hands_back_the_heard_when_dropped_for_more_than_no_speech(self):
        got, words, asked, at = self.quick_listen("room_music.wav", SAID["room_music.wav"])   # (no wake word in it)
        self.assertIsInstance(got, server.Heard, f"Wake.heard didn't hand back a Heard on a dropped burst: {got!r}")
        self.assertEqual(got.text, SAID["room_music.wav"], f"the Heard handed back isn't what was heard: {got!r}")

    def test_check_judges_the_text_and_word_times_of_the_heard_it_is_handed_without_hearing_it_again(self):
        import gate
        calls = self.judged()
        pcm = clip("you_hey_void.wav")
        now = time.monotonic()
        said = SAID["you_hey_void.wav"]
        words = (gate.Word("Hey", now, now + 0.3), gate.Word("Void,", now + 0.3, now + 0.7))
        handed = fakes.heard(said, seconds=len(pcm) / (server.RATE * 2), words=words)
        transcribed = []

        def text_for(p):
            transcribed.append(p)
            return "something else was heard the second time"

        server.Wake.talked = []
        err = io.StringIO()
        with ears(server, text_for), contextlib.redirect_stderr(err):
            server.Wake.check(pcm, now, handed)
        events = []
        while not self.q.empty():
            events.append(self.q.get_nowait())
        self.assertEqual(transcribed, [], "Wake.check heard the burst again instead of judging the Heard it was handed")
        self.assertEqual(len(calls), 1, f"gate.judge called {len(calls)}x on one burst")
        b = calls[0]
        self.assertEqual(b.text, said, f"not judged as the Heard it was handed: {b!r}")
        self.assertEqual(b.words, words, f"not judged with the Heard's word times: {b!r}")
        self.assertEqual(len(self.wakes(events)), 1, f"the wake word in the Heard handed it not taken: {events}\n"
                         + err.getvalue())

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
        server.Wake.talked = [[now - 3 - server.ECHO_TAIL, now - 1 - server.ECHO_TAIL, now + 5]] if follow else []
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
        end = at + len(his) / (server.RATE * 2)
        W.talked = [[at - 5, end, end + server.ECHO_TAIL + 4]]
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


@unittest.skipIf(server is None, f"server.py doesn't import here: {IMPORT_ERR}")
class PageSpeaking(unittest.TestCase):
    """/api/speaking as the page posts it: `on` with the seconds of his scheduled sound still to come, per sentence it
    schedules, and `off` once playback is quiet. His span is that sound, and nothing more."""

    def setUp(self):
        W = server.Wake
        saved = {k: W.__dict__[k] for k in ("talked", "cut", "owed")}
        self.addCleanup(lambda: [setattr(W, k, v) for k, v in saved.items()])
        W.talked, W.cut, W.owed = [], None, 0
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.clock = [1000.0]
        self.pub = mock.Mock()
        self.text = ""
        for p in (mock.patch.dict(server.CFG, {"wake_word": False, "barge_in": False, "follow_up": 30}),
                  mock.patch.object(server, "time", mock.Mock(wraps=time, monotonic=lambda: self.clock[0])),
                  mock.patch.object(server, "CONF_PATH", Path(tmp.name) / "config.json"),
                  mock.patch.object(server, "state_info", lambda: {}),
                  mock.patch.object(server, "whisper", lambda: None),
                  mock.patch.object(server, "SPOKEN", type(server.SPOKEN)()),
                  mock.patch.object(server.BUS, "pub", self.pub),
                  mock.patch.object(server.MicAuto, "learn", lambda pcm: None),
                  mock.patch.object(server.Speaker, "idle", classmethod(lambda cls: True)),
                  mock.patch.object(server.Speaker, "stop", classmethod(lambda cls: None)),
                  mock.patch.object(W, "ensure", classmethod(lambda cls: None)),
                  mock.patch.object(W, "session", classmethod(lambda cls: None))):
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(ears(server, lambda pcm: self.text).close)
        server.PLAYED.clear()
        self.addCleanup(server.PLAYED.clear)
        self.srv = LoopbackThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        self.srv.daemon_threads = True
        threading.Thread(target=self.srv.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)

    def call(self, path, body):
        """POST `body` to `path`. → the JSON reply."""
        c = http.client.HTTPConnection("127.0.0.1", self.srv.server_address[1], timeout=10)
        c.request("POST", path, body=json.dumps(body),
                  headers={"X-Void-Token": server.TOKEN, "Content-Type": "application/json"})
        r = c.getresponse()
        data = r.read()
        c.close()
        self.assertEqual(r.status, 200, data)
        return json.loads(data)

    def speaking(self, body):
        return self.call("/api/speaking", body)

    def told(self):
        """The copies of the record published so far (BUS, t="voice")."""
        return [c.kwargs for c in self.pub.call_args_list if c.kwargs.get("t") == "voice"]

    def test_speaking_on_records_talking_until_now_plus_left(self):
        calls, real = [], server.Wake.__dict__["talking_until"].__func__
        with mock.patch.object(server.Wake, "talking_until",
                               classmethod(lambda cls, t, *a, **k: calls.append(t) or real(cls, t, *a, **k))):
            self.speaking({"on": True, "left": 2.5})
            self.clock[0] = 1001.0
            self.speaking({"on": True, "left": 0.4})
        self.assertEqual(len(calls), 2, f"talking_until called {len(calls)}x for two posts: {calls}")
        self.assertAlmostEqual(calls[0], 1002.5, delta=1e-6)
        self.assertAlmostEqual(calls[1], 1001.4, delta=1e-6)
        spans = [list(s) for s in server.Wake.talked]
        self.assertTrue(spans, "nothing recorded in Wake.talked for two `on` posts")
        self.assertTrue(all(1000.0 - 1e-6 <= s[0] <= s[1] for s in spans), f"a span begun before the first post: {spans}")
        self.assertLessEqual(max(s[1] for s in spans), 1002.5 + 1e-6, f"a span past any sound the page posted: {spans}")
        self.assertAlmostEqual(spans[-1][1], 1001.4, delta=1e-6,
                               msg=f"his sound doesn't end where the page last said it would: {spans}")
        self.assertLessEqual(max(s[2] for s in spans), 1002.5 + server.ECHO_TAIL + 30 + 1e-6,
                             f"a span held open past his sound's ring and follow-up: {spans}")

    def test_owe_and_paid_count_the_sentences_handed_to_the_page_s_player(self):
        W = server.Wake
        self.speaking({"owe": 1})
        self.speaking({"owe": 1})
        self.assertEqual((W.owed, W.talked), (2, []), "an owe made a span, or didn't count")
        self.speaking({"on": True, "left": 1, "paid": 1})
        self.assertEqual(W.owed, 1)
        self.assertAlmostEqual(W.talked[-1][1] - W.talked[-1][0], 1.0, delta=1e-6)
        self.speaking({"paid": 1})
        self.assertEqual((W.owed, len(W.talked)), (0, 1), "a pay alone moved the span, or didn't count")
        self.speaking({"paid": 1})
        self.assertEqual(W.owed, 0, "a pay with nothing owed went below 0")

    # the played words ride the post that starts the sentence's sound: timed from the end it records, less `dur`
    WORDS = [[0.0, 0.3], [0.3, 0.6], [0.6, 1.0]]               # "Okay, I'll stop." as tidy_and_time gives it

    def played(self):
        return [(w.text, w.start, w.end) for w in server.played_lately()]

    def test_the_post_that_starts_a_sentence_notes_its_stop_phrase_from_where_its_sound_starts(self):
        before = self.clock[0]                                               # (the server's clock is this one)
        r = self.speaking({"on": True, "left": 1.2, "paid": 1, "text": "Okay, I'll stop.", "dur": 1.0, "words": self.WORDS})
        after = self.clock[0]
        self.assertEqual(r["ok"], True)
        got = self.played()
        self.assertEqual(len(got), 1, f"noted {got}")
        start = got[0][1]
        self.assertTrue(before + 0.2 + 0.6 <= start <= after + 0.2 + 0.6 + 1e-6, f"start {start}, not {before + 0.8}")
        self.assertAlmostEqual(got[0][2] - start, 0.4, places=6)

    def test_a_sentence_scheduled_behind_the_playing_one_starts_where_the_record_says_its_sound_does(self):
        self.speaking({"on": True, "left": 3.0, "paid": 1})                  # (the one playing: sound to 1003)
        self.speaking({"on": True, "left": 5.0, "paid": 1, "text": "I'll stop.", "dur": 2.0, "words": [[0.0, 0.5], [0.5, 2.0]]})
        self.assertAlmostEqual(self.played()[0][1], 1005.0 - 2.0 + 0.5, delta=1e-6)   # (its sound starts at 1003, not at the post)

    def test_words_that_are_null_or_malformed_spread_the_words_over_dur_and_the_post_is_still_200(self):
        for bad in (None, "x", [[0.0, 1.0]], [[0.0, "a"]] * 3, [[0.0, float("nan")]] * 3, [[True, 1.0]] * 3, [[0.0]] * 3, 7):
            server.PLAYED.clear()
            r = self.speaking({"on": True, "left": 1.2, "paid": 1, "text": "Okay, I'll stop.", "dur": 1.0, "words": bad})
            self.assertTrue(r["ok"], bad)
            got = self.played()
            self.assertEqual(len(got), 1, f"words {bad!r}: noted {got}")
            self.assertAlmostEqual(got[0][1], 1000.2 + 2 / 3, delta=1e-6, msg=f"words {bad!r}")   # two of three thirds in
            self.assertAlmostEqual(got[0][2], 1000.2 + 1.0, delta=1e-6)

    def test_the_text_is_noted_as_speakable_makes_it(self):
        self.speaking({"on": True, "left": 1.2, "paid": 1, "text": "**Okay**, I'll `stop`.", "dur": 1.0, "words": self.WORDS})
        self.assertEqual([w[0] for w in self.played()], ["stop."])

    def test_a_post_without_usable_text_or_dur_notes_nothing_and_still_records_his_sound(self):
        for extra in ({}, {"text": "I'll stop."}, {"dur": 1.0}, {"text": 5, "dur": 1.0}, {"text": ["stop"], "dur": 1.0},
                      {"text": "stop", "dur": 0}, {"text": "stop", "dur": -1.0}, {"text": "stop", "dur": "1"},
                      {"text": "stop", "dur": True}, {"text": "stop", "dur": float("nan")}, {"text": "stop", "dur": float("inf")},
                      {"text": "stop", "dur": None}):
            server.Wake.talked = []
            r = self.speaking({"on": True, "left": 1.2, "paid": 1, **extra})
            self.assertTrue(r["ok"], extra)
            self.assertEqual(self.played(), [], f"{extra} noted something")
            self.assertAlmostEqual(server.Wake.talked[-1][1], 1001.2, delta=1e-6, msg=f"{extra} left the record alone")

    def test_an_on_false_post_removes_the_stop_phrases_that_had_not_started_and_keeps_the_ones_that_had(self):
        words = [[0.0, 0.5], [0.5, 1.0], [1.0, 1.5], [1.5, 2.0], [2.0, 2.5]]           # "Stop. Then be calm stop." has two
        self.speaking({"on": True, "left": 3.0, "paid": 1, "text": "Stop. Then be calm stop.", "dur": 3.0, "words": words})
        self.assertEqual([(w[0], round(w[1] - 1000.0, 6)) for w in self.played()], [("Stop.", 0.0), ("stop.", 2.0)])
        self.clock[0] = 1000.5
        self.speaking({"on": False})
        self.assertEqual([(w[0], round(w[1] - 1000.0, 6)) for w in self.played()], [("Stop.", 0.0)])

    def test_a_post_with_left_publishes_where_his_sound_ends_and_the_replies_carry_the_record(self):
        for body in ({"owe": 1}, {"on": True, "left": 1.5, "paid": 1}, {"paid": 1}, {"on": False}):
            reply = self.speaking(body)
            self.assertEqual(sorted(k for k in reply if k != "ok"), ["left", "n", "owed"], f"{body}: reply {reply}")
        events = self.told()
        self.assertEqual([(e["left"], e["owed"]) for e in events], [(0.0, 1), (1.5, 0), (1.5, 0), (0.0, 0)],
                         "a change of the record wasn't published once, with its new left and owed")

    def test_n_rises_strictly_across_the_events_and_the_replies(self):
        order = []
        for body in ({"owe": 1}, {"on": True, "left": 1.5, "paid": 1}, {"on": False}):
            before = len(self.told())
            reply = self.speaking(body)
            order += [e["n"] for e in self.told()[before:]] + [reply["n"]]
        self.assertEqual(order, sorted(set(order)), f"n didn't rise strictly: {order}")
        self.assertGreater(len(order), 3)

    def test_say_and_say_stop_reply_with_the_record(self):
        S = server.Speaker
        for k in ("todo", "ready", "epoch"):
            p = mock.patch.object(S, k, [] if k != "epoch" else 0)
            p.start()
            self.addCleanup(p.stop)
        for p in (mock.patch.object(S, "_start", classmethod(lambda cls: None)),
                  mock.patch.object(S, "stop", classmethod(lambda cls, epoch=None: None)),
                  mock.patch.object(server, "tts_engine", lambda: True)):
            p.start()
            self.addCleanup(p.stop)
        reply = self.call("/api/say", {"text": "Hello there.", "id": 1})
        self.assertEqual((reply["owed"], reply["left"]), (1, 0.0), f"/api/say reply: {reply}")
        self.assertIn("n", reply)
        stop = self.call("/api/say/stop", {})                 # (Speaker.stop is stubbed: the reply only reports the record)
        self.assertEqual(sorted(k for k in stop if k != "ok"), ["left", "n", "owed"])
        self.assertGreater(stop["n"], reply["n"])

    def test_off_ends_his_sound_now_and_clears_what_he_owed(self):
        W = server.Wake
        self.speaking({"owe": 1})
        self.speaking({"owe": 1})
        self.speaking({"on": True, "left": 5})
        self.speaking({"on": False})
        self.assertEqual(W.owed, 0)
        self.assertAlmostEqual(W.talked[-1][1], self.clock[0], delta=1e-6)

    def test_its_good_said_after_the_page_went_quiet_is_a_follow_up(self):
        """The 27 Oct reply: 'while talking (over): It's good', said after his last sound, in the ring and after it."""
        burst = bytes(int(server.RATE * 2 * 1.9))
        got = []
        for after in (0.1, server.ECHO_TAIL + 0.2):                    # began in the ring / after it
            server.Wake.talked = []
            server.note_spoken("Both albums are in the 30K folder now, next to the original pressing.")
            self.clock[0] = 1000.0
            self.speaking({"on": True, "left": 1.5})                   # his first sentence, scheduled
            self.clock[0] = 1000.1
            self.speaking({"on": True, "left": 3.2})                   # his last, scheduled after it: sound to 1003.3
            self.clock[0] = 1003.3
            self.speaking({"on": False})                               # playback quiet
            began = 1003.3 + after
            self.clock[0] = began + 1.9 + 0.4
            import gate
            judged, real = [], gate.judge
            err = io.StringIO()
            self.text = "It's good"
            self.pub.reset_mock()
            with mock.patch.object(gate, "judge", lambda b, *a: judged.append(b) or real(b, *a)), \
                    contextlib.redirect_stderr(err):
                server.Wake.check(burst, began, ended=began + 1.9)
            events = [(c.kwargs.get("t"), c.kwargs.get("text"), c.kwargs.get("follow")) for c in self.pub.call_args_list]
            log = [ln for ln in err.getvalue().splitlines() if ln.startswith("[void]")]
            got.append((round(after, 1), events, [b.kind for b in judged],
                        any("while talking" in ln for ln in log)))
        self.assertEqual(got, [(round(after, 1), [("wake", "It's good", True)], ["follow"], False)
                               for after in (0.1, server.ECHO_TAIL + 0.2)])


SPK_STEP_BYTES = 640                    # (two 20 ms chunks at SPK_RATE)


class _Done(BaseException):
    """Ends a Speaker worker after it has handled what it was given (raised by its Condition when it would wait)."""


class _OneRound(threading.Condition):
    def wait(self, timeout=None):
        raise _Done


@unittest.skipIf(server is None, f"server.py doesn't import here: {IMPORT_ERR}")
class NativeOwed(unittest.TestCase):
    """Wake.owed with the native Speaker: Speaker.say owes the sentence, the first chunk of its sound pays it (inside
    the Wake.talking call that records the chunk), every road that ends it with no sound pays it too, and a sentence
    dropped as stale pays nothing (Speaker.stop's hush settled it). Wake.air reads none of it. The stop phrases of the
    sentence are noted in server.PLAYED at the time of that same first chunk."""

    def setUp(self):
        S, W = server.Speaker, server.Wake
        saved = {k: W.__dict__[k] for k in ("talked", "owed")}
        self.addCleanup(lambda: [setattr(W, k, v) for k, v in saved.items()])
        W.talked, W.owed = [], 0
        self.clock = [100.0]
        self.player = FakePlayer(self.clock)
        self.q = server.BUS.sub()
        self.addCleanup(server.BUS.unsub, self.q)
        for k, v in (("gen", 7), ("epoch", 0), ("proc", self.player), ("prate", SPK_RATE), ("written", 1000),
                     ("t0", 100.0), ("filled", False), ("stats", {}), ("todo", []), ("ready", []), ("making", False),
                     ("cv", _OneRound())):
            self.patch(S, k, v)
        self.patch(S, "_start", classmethod(lambda cls: None))
        self.patch(server, "time", mock.Mock(wraps=time, monotonic=lambda: self.clock[0],
                                             sleep=lambda s: self.clock.__setitem__(0, self.clock[0] + s)))
        self.patch(server.hearing, "PlayRef", FakeRef())
        self.patch(server, "SPOKEN", type(server.SPOKEN)())
        self.patch(server, "PLAYED", collections.deque())
        self.patch(W, "nudge", classmethod(lambda cls: None))

    def events(self, kind="voice"):
        """The BUS events of `kind` published since the last call."""
        got = []
        while not self.q.empty():
            got.append(self.q.get_nowait())
        return [e for e in got if e.get("t") == kind]

    def patch(self, obj, name, value):
        p = mock.patch.object(obj, name, value)
        p.start()
        self.addCleanup(p.stop)

    def work(self, loop):
        """Run a Speaker worker on a thread until it would wait for more."""
        def run():
            try:
                loop()
            except _Done:
                pass
        t = threading.Thread(target=run, daemon=True)
        t.start()
        t.join(10)
        self.assertFalse(t.is_alive(), "the Speaker worker didn't finish its round")

    def made(self, text="Hello there.", pcm=b"\x01\x00" * 800):
        """A sentence the maker has finished: waiting in `ready` for the player."""
        server.Speaker.ready.append((server.Speaker.gen, 1, text, pcm, SPK_RATE, None, 0.0, 0.0))

    def test_say_owes_the_sentence_and_changes_nothing_else(self):
        server.Speaker.say("Hello there.", 1)
        self.assertEqual(server.Wake.owed, 1)
        self.assertEqual((server.Wake.talked, server.Wake.air(0.0, 1e6)), ([], (False, False)),
                         "owing a sentence put sound in the record, or in the air")

    def test_a_sentence_sent_before_the_cut_off_is_not_owed(self):
        server.Speaker.epoch = 3
        server.Speaker.say("Hello there.", 1, epoch=2)
        self.assertEqual(server.Wake.owed, 0)

    def test_its_first_sound_chunk_pays_it_in_the_same_change_as_the_span(self):
        server.Speaker.say("Hello there.", 1)
        self.made()
        seen, real = [], server.Wake.__dict__["talking"].__func__

        def talking(cls, *a, **k):
            before = cls.owed
            r = real(cls, *a, **k)
            seen.append((before, cls.owed, len(cls.talked)))
            return r
        with mock.patch.object(server.Wake, "talking", classmethod(talking)):
            self.work(server.Speaker._player_loop)
        self.assertGreater(len(seen), 1, "the sentence was written in one chunk")
        self.assertEqual(seen[0], (1, 0, 1), "the first chunk didn't pay the sentence and add its span in one call")
        self.assertTrue(all(b == 0 and a == 0 for b, a, _ in seen[1:]), f"a later chunk moved the owe: {seen}")

    def test_a_sentence_with_no_samples_pays(self):
        server.Speaker.say("Hello there.", 1)
        self.made(pcm=b"")
        self.work(server.Speaker._player_loop)
        self.assertEqual((server.Wake.owed, server.Wake.talked), (0, []))

    def test_a_failing_player_pays(self):
        server.Speaker.say("Hello there.", 1)
        self.made()
        with mock.patch.object(server.Speaker, "_player", classmethod(lambda cls, rate: 1 / 0)), \
                contextlib.redirect_stderr(io.StringIO()):
            self.work(server.Speaker._player_loop)
        self.assertEqual(server.Wake.owed, 0)
        self.assertEqual([e["id"] for e in self.events("spk_skip")], [1])

    def test_a_failing_synth_pays(self):
        server.Speaker.say("Hello there.", 1)
        with mock.patch.object(server, "synth", lambda text: 1 / 0), contextlib.redirect_stderr(io.StringIO()):
            self.work(server.Speaker._maker)
        self.assertEqual(server.Wake.owed, 0)
        self.assertEqual([e["id"] for e in self.events("spk_skip")], [1])

    def test_a_sentence_dropped_as_stale_leaves_the_next_ones_owe(self):
        server.Speaker.say("First one.", 1)
        server.Speaker.stop()                                     # (the maker had already taken the first one)
        self.assertEqual(server.Wake.owed, 0, "a cut-off left a sentence owed")
        server.Speaker.say("Second one.", 2)
        server.Speaker.todo[:] = [(7, 1, "First one.")]           # (the old generation's, which the maker had taken; the
                                                                  # second is on its way, owed, not in this maker's hands)
        self.work(server.Speaker._maker)
        self.assertEqual(server.Wake.owed, 1, "a stale sentence paid the next one's owe")

    def test_hush_clears_what_he_owed(self):
        server.Wake.owe()
        server.Wake.owe()
        server.Wake.hush()
        self.assertEqual(server.Wake.owed, 0)

    # ---- the copies of the record the page is told
    def test_two_seconds_of_sound_are_told_at_a_bounded_rate_and_the_last_copy_has_the_true_end(self):
        data = bytes(SPK_RATE * 2 * 2)                              # 2 s, written in 20 ms chunks
        self.assertTrue(server.Speaker._write(data, 7))
        events = self.events()
        self.assertGreater(len(events), 1, "the page was told once for two seconds of sound")
        self.assertLessEqual(len(events), 2 * 10 + 2, f"{len(events)} copies for two seconds of sound")
        self.assertTrue(all(e["left"] > 0 for e in events), f"the page was told he'd gone quiet mid-sound: {events}")
        self.assertAlmostEqual(self.clock[0] + events[-1]["left"], server.Wake.talked[-1][1], delta=0.05,
                               msg="the last copy doesn't put his end where the record has it")
        ns = [e["n"] for e in events]
        self.assertEqual(ns, sorted(set(ns)), "n didn't rise strictly")

    def test_an_owe_a_pay_and_a_cut_off_each_publish_at_once(self):
        W = server.Wake
        W.owe()
        W.owe()
        W.pay()
        W.talking(self.clock[0], self.clock[0] + 5)
        W.hush(self.clock[0])
        self.assertEqual([(e["left"], e["owed"]) for e in self.events()],
                         [(0.0, 1), (0.0, 2), (0.0, 1), (5.0, 1), (0.0, 0)])

    def test_the_first_chunk_pays_and_tells_in_one_copy(self):
        server.Wake.owe()
        self.events()                                               # (the owe's own copy)
        server.Speaker._write(bytes(SPK_STEP_BYTES), 7, owe=[True])
        first = self.events()[0]
        self.assertEqual((first["owed"], first["left"] > 0), (0, True), f"the copy showed the sentence neither owed nor sounding: {first}")

    # ---- his stop phrases, timed from the first sound chunk Wake.talked records for the sentence
    def first_chunks(self):
        """Wrap Wake.talking: → the list of (start, paid) it is given, in order."""
        seen, real = [], server.Wake.__dict__["talking"].__func__

        def talking(cls, start, end, paid=0, chunk=False):
            seen.append((start, paid))
            return real(cls, start, end, paid, chunk)
        p = mock.patch.object(server.Wake, "talking", classmethod(talking))
        p.start()
        self.addCleanup(p.stop)
        return seen

    def test_a_stop_in_a_sentence_is_noted_at_the_first_chunks_time_plus_the_words_offset(self):
        chunks = self.first_chunks()
        text, words = "Okay, I will stop now.", [[0.0, 0.2], [0.2, 0.4], [0.4, 0.6], [0.6, 0.8], [0.8, 1.0]]
        server.Speaker.say(text, 1)
        server.Speaker.ready.append((server.Speaker.gen, 1, text, bytes(SPK_RATE * 2), SPK_RATE, words, 0.0, 0.0))
        self.work(server.Speaker._player_loop)
        paid = [at for at, p in chunks if p]
        self.assertEqual(len(paid), 1, f"the sentence's first chunk didn't pay it exactly once: {chunks}")
        self.assertEqual(server.Wake.talked[0][0], paid[0], "Wake.talked doesn't start at the paying chunk")
        self.assertEqual([(w.start, w.end) for w in server.PLAYED], [(paid[0] + 0.6, paid[0] + 0.8)],
                         "his one stop phrase isn't timed from the sentence's first sound chunk")

    def test_a_sentence_with_no_stop_phrase_notes_nothing(self):
        server.Speaker.say("Hello there.", 1)
        self.made()
        self.work(server.Speaker._player_loop)
        self.assertEqual(list(server.PLAYED), [])

    def test_a_sentence_that_never_sounds_notes_nothing(self):
        server.Speaker.say("Please stop.", 1)
        self.made(text="Please stop.", pcm=b"")
        self.work(server.Speaker._player_loop)
        self.assertEqual(list(server.PLAYED), [])

    def test_the_silent_pause_after_a_sentence_notes_nothing_more(self):
        server.Speaker.say("Stop.", 1)
        server.Speaker.ready.append((server.Speaker.gen, 1, "Stop.", bytes(SPK_RATE * 2 // 5), SPK_RATE, None, 0.0, 0.0))
        self.work(server.Speaker._player_loop)
        self.assertEqual(len(server.PLAYED), 1, list(server.PLAYED))

    def test_the_retry_on_a_reopened_player_notes_the_sentence_once_at_its_first_chunk(self):
        chunks = self.first_chunks()
        server.Wake.owe()
        server.Speaker.proc = FakePlayer(self.clock, dies=0)          # (the speakers changed: its first write fails)

        def reopen(cls, rate):
            cls.proc = FakePlayer(self.clock)
            return cls.proc
        with mock.patch.object(server.Speaker, "_player", classmethod(reopen)):
            ok = server.Speaker._write(bytes(SPK_RATE * 2 // 2), 7, owe=[True], played=("Stop.", 0.5, None))
        self.assertTrue(ok)
        paid = [at for at, p in chunks if p]
        self.assertEqual(len(paid), 1, f"the retry didn't pay the sentence exactly once: {chunks}")
        self.assertEqual([(w.start, w.end) for w in server.PLAYED], [(paid[0], paid[0] + 0.5)])


# ---- when his own stop phrases play: server.PLAYED, written only by note_played, read through played_lately, cut by
# played_cut (Wake.hush cuts it, so Speaker.stop and Wake.barge cut it too)

FAR = 10000.0            # seconds: far longer ago than any echo is kept


def spans(words):
    return [(w.start, w.end) for w in words]


@unittest.skipIf(server is None, f"server.py doesn't import here: {IMPORT_ERR}")
class Played(unittest.TestCase):
    def setUp(self):
        server.PLAYED.clear()
        self.addCleanup(server.PLAYED.clear)
        self.now = time.monotonic()

    def assertSpans(self, got, want):
        self.assertEqual(len(got), len(want), f"kept {spans(got)}, wanted {want}")
        for (a, b), (wa, wb) in zip(spans(got), want):
            self.assertAlmostEqual(a, wa, places=6)
            self.assertAlmostEqual(b, wb, places=6)

    # note_played: each word timed from `start` plus its [start, end] pair, or spread evenly over `dur`
    def test_word_times_place_the_stop_phrase(self):
        s = self.now
        server.note_played("Okay I will stop now", s, 1.5, [[0.0, 0.25], [0.25, 0.5], [0.5, 0.75], [0.75, 1.0],
                                                            [1.0, 1.5]])
        self.assertSpans(list(server.PLAYED), [(s + 0.75, s + 1.0)])

    def test_two_word_stop_phrase_runs_from_its_first_word_to_its_last(self):
        s = self.now
        server.note_played("Please hold on a moment", s, 1.5, [[0.0, 0.25], [0.25, 0.5], [0.5, 0.75], [0.75, 1.0],
                                                               [1.0, 1.5]])
        self.assertSpans(list(server.PLAYED), [(s + 0.25, s + 0.75)])

    def test_no_word_times_spreads_the_words_evenly(self):
        s = self.now
        server.note_played("Fine then I stop", s, 2.0, None)              # four words, half a second each
        self.assertSpans(list(server.PLAYED), [(s + 1.5, s + 2.0)])

    def test_a_count_of_word_times_that_is_not_the_words_spreads_them_evenly_too(self):
        s = self.now
        server.note_played("Fine then I stop", s, 2.0, [[0.0, 1.0]])
        self.assertSpans(list(server.PLAYED), [(s + 1.5, s + 2.0)])

    def test_every_stop_phrase_in_the_sentence_is_kept(self):
        s = self.now
        server.note_played("Stop, I said, hold on", s, 2.5, None)         # five words, half a second each
        self.assertSpans(list(server.PLAYED), [(s, s + 0.5), (s + 1.5, s + 2.5)])

    def test_a_sentence_with_no_stop_phrase_keeps_nothing(self):
        server.note_played("Sure, I moved the meeting", self.now, 2.5, None)
        server.note_played("Sure, I moved the meeting", self.now, 2.5, [[0.0, 0.5], [0.5, 1.0], [1.0, 1.5],
                                                                        [1.5, 2.0], [2.0, 2.5]])
        self.assertEqual(list(server.PLAYED), [])

    def test_a_markup_only_sentence_keeps_nothing(self):
        server.note_played("", self.now, 1.0, None)
        self.assertEqual(list(server.PLAYED), [])

    # played_lately: what ended more than ECHO_KEEP ago is dropped, the rest returned
    def test_played_lately_drops_what_ended_long_ago(self):
        server.note_played("stop", self.now - FAR, 1.0, None)
        server.note_played("stop", self.now, 1.0, None)
        got = server.played_lately()
        self.assertIsInstance(got, tuple)
        self.assertSpans(got, [(self.now, self.now + 1.0)])
        self.assertSpans(list(server.PLAYED), [(self.now, self.now + 1.0)])

    def test_a_stop_that_ended_just_inside_echo_keep_survives_note_played_and_played_lately(self):
        import gate
        end = self.now - (gate.ECHO_KEEP - 1.0)
        server.note_played("stop", end - 0.5, 0.5, None)
        server.note_played("stop", self.now, 1.0, None)                    # (note_played drops old entries again)
        want = [(end - 0.5, end), (self.now, self.now + 1.0)]
        self.assertSpans(list(server.PLAYED), want)
        self.assertSpans(server.played_lately(), want)
        self.assertSpans(list(server.PLAYED), want)

    def test_played_lately_itself_drops_what_ended_more_than_echo_keep_ago(self):
        import gate
        server.note_played("stop", self.now, 1.0, None)
        old = self.now - gate.ECHO_KEEP - 1.0
        server.PLAYED.appendleft(gate.Word("stop", old - 0.5, old))   # (past note_played: only played_lately drops it)
        got = server.played_lately()
        self.assertSpans(got, [(self.now, self.now + 1.0)])
        self.assertSpans(list(server.PLAYED), [(self.now, self.now + 1.0)])

    # played_cut(at): every entry starting at or after `at` is dropped
    def test_played_cut_drops_what_starts_at_or_after(self):
        s = self.now
        for start in (s, s + 9.5, s + 10.0, s + 20.0):
            server.note_played("stop", start, 1.0, None)
        server.played_cut(s + 10.0)
        self.assertSpans(list(server.PLAYED), [(s, s + 1.0), (s + 9.5, s + 10.5)])


@unittest.skipIf(server is None, f"server.py doesn't import here: {IMPORT_ERR}")
class Hush(unittest.TestCase):
    """Wake.hush(at) cuts what was to play from `at` on."""

    def setUp(self):
        W, S = server.Wake, server.Speaker
        self._saved = {k: W.__dict__[k] for k in ("talked", "follow_on", "cut", "owed")}
        self.addCleanup(self._restore)
        W.talked, W.owed = [], 0
        for k, v in (("todo", []), ("ready", []), ("making", False), ("proc", None), ("filled", False)):
            p = mock.patch.object(S, k, v)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(server.BUS, "pub", mock.Mock())
        p.start()
        self.addCleanup(p.stop)
        server.PLAYED.clear()
        self.addCleanup(server.PLAYED.clear)
        self.now = time.monotonic()
        server.note_played("stop", self.now - 1.0, 0.5, None)              # already played
        server.note_played("stop", self.now + 60.0, 0.5, None)             # still to play

    def _restore(self):
        for k, v in self._saved.items():
            setattr(server.Wake, k, v)

    def starts(self):
        return [w.start for w in server.PLAYED]

    def test_hush_cuts_what_starts_at_or_after_at(self):
        server.Wake.hush(self.now + 60.0)
        self.assertEqual(self.starts(), [self.now - 1.0])

    def test_hush_calls_played_cut_with_at(self):
        with mock.patch.object(server, "played_cut") as cut:
            server.Wake.hush(self.now + 5.0)
        cut.assert_called_once_with(self.now + 5.0)

    def test_speaker_stop_cuts_what_was_still_to_play(self):
        server.Speaker.stop()
        self.assertEqual(self.starts(), [self.now - 1.0])

    def test_barge_cuts_what_was_still_to_play(self):
        server.Wake.barge("stop")
        self.assertEqual(self.starts(), [self.now - 1.0])


if __name__ == "__main__":
    unittest.main()
