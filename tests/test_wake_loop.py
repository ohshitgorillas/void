"""The "hey Void" loop (Wake.loop) at rest: while it shouldn't listen (hidden, the mic busy, he's quiet and the wake
word is off) it waits without waking up every 0.2 s, and still starts listening right away (within 0.25 s) when it
should again: shown (/api/sleep off), the wake word switched on (/api/settings), the mic let go (/api/listen ends),
he starts talking with barge-in on (/api/speaking), the follow-up window opening after he stops. Switched off
entirely, the loop ends promptly. The real request handler on a local port; the mic session is a stand-in.

And Wake.check's follow-up gate: a follow-up without "hey Void" that is music in the room is dropped and the page told
(gate_drop, with the log line); the owner's follow-up is kept; a wake-word clip is never judged; the owner's voice is
learned only from wake-word and Listen clips, never from follow-ups; voice_gate off takes follow-ups as before; and
the gate adds under 100 ms of wall time to a follow-up over Whisper alone, the voice scored while Whisper transcribes.

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


# ---- the follow-up gate in Wake.check, and where the owner's voice is learned
# Wake.check is fed fixture clips with speech detection and Whisper stood in for (Whisper is "sure" of every clip, so
# only the voice can tell music from the owner). The voiceprint scores with a print enrolled from the owner's own clips
# in a temporary folder; enrolment by the server is only recorded, so the real print on this machine is never touched.

ROOT = Path(__file__).resolve().parent.parent
SCENES = ROOT / "tests" / "fixtures" / "scenes"
VP_MODEL_DIR = suite_data.MODEL_DIR
ENROLL = ["you_stop.wav", "you_hold_on.wav", "you_shut_up.wav", "you_hey_void.wav", "you_answer.wav"]
SAID = {"room_music.wav": "take me down to the river tonight where the summer lights are shining bright",
        "you_overlap.wav": "Yeah, move them, and while you're at it, make a new folder called summer for them.",
        "you_hey_void.wav": "Hey Void, open my Downloads folder instead."}
WHISPER_S = 0.5             # the Whisper stand-in's time on a clip in the latency test (longer than a warm voice score)
GATE_BUDGET = 0.100         # wall time the gate may add to a follow-up over Whisper alone (design: Latency)

try:
    import voiceprint
except Exception as e:  # noqa: BLE001
    voiceprint, VP_ERR = None, e
else:
    VP_ERR = None


def clip(name):
    import wave
    with wave.open(str(SCENES / name), "rb") as w:
        return w.readframes(w.getnframes())


def hiss(seconds, seed):
    """Quiet room hiss, `seconds` long: the lead-in a burst carries before you start talking."""
    import random
    rnd = random.Random(seed)
    return b"".join(int(max(-32768, min(32767, round(rnd.gauss(0.0, 0.003) * 32768)))).to_bytes(2, "little", signed=True)
                    for _ in range(int(seconds * 16000)))


def pieces(pcm, ms=20):
    """Every `ms`-long piece of `pcm`, back to back."""
    n = 16000 * 2 * ms // 1000
    return [pcm[i:i + n] for i in range(0, len(pcm) - n + 1, n)]


@unittest.skipIf(server is None, f"server.py doesn't import here: {IMPORT_ERR}")
class FollowUpGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.vp = None
        if voiceprint is not None:
            cls.vp = voiceprint.Voiceprint(Path(cls.tmp.name) / "voiceprint", VP_MODEL_DIR)
            if cls.vp.available:
                for n in ENROLL:
                    cls.vp.enroll(clip(n))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.assertIsNotNone(voiceprint, f"app/voiceprint.py doesn't import: {VP_ERR}")
        self.assertTrue(self.vp.available, f"voiceprint unavailable: {self.vp.why}")
        W = server.Wake
        saved = {k: W.__dict__[k] for k in ("speaking_until", "follow_from", "follow_until")}
        self.addCleanup(lambda: [setattr(W, k, v) for k, v in saved.items()])
        self.enrolled, self.scored, self.learned = [], [], []
        test = self
        ours = self.vp
        real_score = voiceprint.Voiceprint.score

        def enroll(vp, pcm):
            test.enrolled.append(pcm)

        def score(vp, pcm):
            test.scored.append(pcm)
            return real_score(ours, pcm)

        self.heard_text = {}
        self.whisper_s = 0.0

        def heard(pcm, **kw):
            time.sleep(test.whisper_s)
            return server.Heard(text=test.heard_text[pcm], logprob=-0.2, no_speech=0.02,
                                seconds=len(pcm) / (server.RATE * 2))
        gate_cfg = {k: server.DEFAULTS[k] for k in ("voice_gate", "voice_min") if k in server.DEFAULTS}
        for p in (mock.patch.dict(server.CFG, gate_cfg),     # (the defaults, whatever this machine's config says)
                  mock.patch.object(server, "speech_seconds", lambda pcm: len(pcm) / (server.RATE * 2)),
                  mock.patch.object(server, "transcribe_pcm_heard", heard),
                  mock.patch.object(server, "transcribe_pcm", lambda pcm, **kw: heard(pcm, **kw).text),
                  mock.patch.object(server, "SPOKEN", type(server.SPOKEN)()),
                  mock.patch.object(server.Speaker, "idle", classmethod(lambda cls: True)),
                  mock.patch.object(server.MicAuto, "learn", classmethod(lambda cls, pcm: test.learned.append(pcm))),
                  mock.patch.object(voiceprint, "fetch", lambda folder: VP_MODEL_DIR / voiceprint.MODEL),
                  mock.patch.object(voiceprint.Voiceprint, "enroll", enroll),
                  mock.patch.object(voiceprint.Voiceprint, "score", score)):
            p.start()
            self.addCleanup(p.stop)
        self.q = server.BUS.sub()
        self.addCleanup(server.BUS.unsub, self.q)

    def check(self, name, follow):
        """Wake.check on fixture `name`, heard inside the follow-up window or not. → (bus events, '[void]' log lines)."""
        pcm = clip(name)
        self.heard_text[pcm] = SAID[name]
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

    @staticmethod
    def spoken(pcm):
        """The stretch of `pcm` where the owner spoke (server.speech_span): what's scored or enrolled."""
        span = server.speech_span(pcm)
        return pcm if span is None else pcm[span[0]:span[1]]

    def judged(self):
        try:
            import gate
        except Exception as e:  # noqa: BLE001
            self.fail(f"app/gate.py doesn't import: {e}")
        calls = []
        real = gate.judge
        p = mock.patch.object(gate, "judge", lambda *a, **k: calls.append(a) or real(*a, **k))
        p.start()
        self.addCleanup(p.stop)
        return calls

    def wakes(self, events):
        return [e for e in events if e.get("t") == "wake"]

    def test_room_music_follow_up_is_dropped_and_the_page_told(self):
        _, events, log = self.check("room_music.wav", follow=True)
        self.assertEqual(self.wakes(events), [], f"room music taken as a request: {events}\n{log}")
        drops = [e for e in events if e.get("t") == "gate_drop"]
        self.assertEqual(len(drops), 1, f"no single gate_drop published: {events}\n{log}")
        shown = [v for v in drops[0].values() if isinstance(v, str) and v != "gate_drop" and v.strip()]
        self.assertTrue(any(v in ln and "take me down" in ln for v in shown for ln in log),
                        f"gate_drop doesn't carry the log line of the drop: {drops[0]}\n{log}")

    def test_owner_follow_up_is_kept(self):
        _, events, log = self.check("you_overlap.wav", follow=True)
        got = self.wakes(events)
        self.assertTrue(len(got) == 1 and got[0].get("follow"), f"the owner's follow-up not kept: {events}\n{log}")
        self.assertFalse([e for e in events if e.get("t") == "gate_drop"], f"gate_drop on a kept clip: {events}")

    def test_each_follow_up_is_judged_once_with_its_voice_score(self):
        calls = self.judged()
        self.check("you_overlap.wav", follow=True)
        self.assertEqual(len(calls), 1, f"gate.judge called {len(calls)}x on one follow-up")
        self.assertIsInstance(calls[0][1], float, "judged without the clip's voice score")

    def test_every_follow_up_verdict_logs_its_voice_score(self):
        for name in ("you_overlap.wav", "room_music.wav"):     # (one kept, one dropped)
            with self.subTest(name):
                pcm, events, log = self.check(name, follow=True)
                score = self.vp.score(pcm)
                verdict = [ln for ln in log if SAID[name][:30] in ln]
                self.assertEqual(len(verdict), 1, f"{name}: no single verdict line in the log:\n{log}")
                numbers = [float(n) for n in re.findall(r"\d+\.\d+", verdict[0])]
                self.assertTrue(any(abs(n - score) < 0.01 for n in numbers),
                                f"{name}: the verdict doesn't log its voice score {score:.2f}: {verdict[0]}")

    def test_wake_word_clip_is_never_judged(self):
        calls = self.judged()
        for follow in (False, True):
            with self.subTest(in_follow_window=follow):
                calls.clear()
                self.enrolled.clear()
                pcm, events, log = self.check("you_hey_void.wav", follow=follow)
                self.assertEqual(len(self.wakes(events)), 1, f"wake word not taken: {events}\n{log}")
                self.assertEqual(calls, [], "a wake-word clip went through gate.judge")
                self.assertTrue(self.enrolled == [self.spoken(pcm)], f"the wake-word clip was enrolled {len(self.enrolled)}x, "
                                                        "not once by the wake-word branch alone")

    def test_wake_word_clip_is_enrolled_beside_mic_learn(self):
        pcm, events, log = self.check("you_hey_void.wav", follow=False)
        self.assertTrue(self.learned == [pcm], f"MicAuto.learn got {len(self.learned)} clip(s), not the wake-word clip: {log}")
        self.assertTrue(self.enrolled == [self.spoken(pcm)], f"the wake-word clip wasn't enrolled into the voiceprint ({len(self.enrolled)} clip(s) enrolled)")

    def test_follow_ups_are_never_enrolled(self):
        followed = []
        for name in ("you_overlap.wav", "room_music.wav"):     # (one kept, one dropped)
            self.scored.clear()
            pcm, events, log = self.check(name, follow=True)
            followed.append(self.spoken(pcm))
            self.assertTrue(self.scored == [self.spoken(pcm)],f"follow-up {name} not scored once against the voiceprint "
                                                  f"({len(self.scored)} score(s)): {log}")
        wake, events, log = self.check("you_hey_void.wav", follow=False)
        self.assertEqual(len(self.enrolled), 1, f"{len(self.enrolled)} clip(s) enrolled, not just the wake-word clip")
        self.assertFalse([p for p in followed if p in self.enrolled], "a follow-up clip was enrolled into the voiceprint")
        self.assertTrue(self.enrolled == [self.spoken(wake)], "the wake-word clip after the follow-ups wasn't enrolled")

    def test_the_gate_adds_under_100_ms_over_whisper_alone(self):
        self.whisper_s = WHISPER_S

        def took(name, gate_on):                 # (best of two, so one hiccup on this machine doesn't decide it)
            server.CFG["voice_gate"] = gate_on
            best = None
            for _ in range(2):
                t0 = time.perf_counter()
                self.check(name, follow=True)
                t = time.perf_counter() - t0
                best = t if best is None else min(best, t)
            return best

        for name in ("you_overlap.wav", "room_music.wav"):
            with self.subTest(name):
                took(name, True)                 # (warm)
                alone = took(name, False)
                self.scored.clear()
                gated = took(name, True)
                self.assertTrue(self.scored, f"{name}: the follow-up wasn't scored against the voiceprint")
                self.assertLess(gated - alone, GATE_BUDGET,
                                f"{name}: the gate added {(gated - alone) * 1000:.0f} ms over Whisper alone "
                                f"({alone * 1000:.0f} ms → {gated * 1000:.0f} ms)")

    def test_gate_switched_off_takes_room_music_as_before(self):
        server.CFG["voice_gate"] = False
        _, events, log = self.check("room_music.wav", follow=True)
        self.assertEqual(len(self.wakes(events)), 1, f"voice_gate off but the follow-up wasn't taken: {events}\n{log}")
        self.assertFalse([e for e in events if e.get("t") == "gate_drop"], f"gate_drop with voice_gate off: {events}")

    def test_listen_clip_is_enrolled_beside_mic_learn(self):
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
        with mock.patch.object(server, "open_clean_mic", lambda: (FakeMic(), "fake mic", b"")), \
                mock.patch.object(server, "transcribe_pcm", lambda b, **kw: "Move them into Pictures, please."), \
                contextlib.redirect_stderr(io.StringIO()):
            server.Listen("ptt").run(lambda **ev: events.append(ev))
        self.assertEqual(len(self.learned), 1, f"MicAuto.learn not called once on the Listen clip: {events[-3:]}")
        self.assertEqual(len(self.enrolled), 1, f"exactly one clip should be enrolled ({len(self.enrolled)} enrolled)")
        self.assertTrue(self.enrolled[0] in self.learned[0] and len(self.enrolled[0]) < len(self.learned[0]),
                        "the enrolled clip should be the speech within the recording MicAuto.learn got, not the whole recording")

    # ---- only the stretch where the owner spoke is scored or enrolled, cut by one shared speech-span function
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

    def assert_speech_only(self, got, lead, speech, what):
        led = sum(1 for p in pieces(lead) if p in got)
        self.assertEqual(led, 0, f"{what}: {led * 20} ms of the lead-in went in with the owner's speech")
        spoken = pieces(speech)
        kept = sum(1 for p in spoken if p in got)
        self.assertGreaterEqual(kept / len(spoken), 0.8, f"{what}: only {kept} of {len(spoken)} 20 ms pieces of the "
                                                         "owner's speech went in")

    def test_owner_follow_up_after_seconds_of_lead_in_is_kept(self):
        pcm = hiss(self.LEAD_IN, 7) + clip("you_overlap.wav")
        events, log = self.check_pcm(pcm, SAID["you_overlap.wav"], follow=True)
        got = self.wakes(events)
        self.assertTrue(len(got) == 1 and got[0].get("follow"),
                        f"the owner's follow-up after {self.LEAD_IN:.0f} s of lead-in was not kept: {events}\n{log}")
        self.assertFalse([e for e in events if e.get("t") == "gate_drop"], f"gate_drop on the owner's follow-up: {log}")

    def test_follow_up_is_scored_on_the_owner_s_speech_alone(self):
        lead, speech = hiss(self.LEAD_IN, 7), clip("you_overlap.wav")
        events, log = self.check_pcm(lead + speech, SAID["you_overlap.wav"], follow=True)
        self.assertEqual(len(self.scored), 1, f"the follow-up was scored {len(self.scored)}x, not once: {log}")
        self.assert_speech_only(bytes(self.scored[0]), lead, speech, "the follow-up's voice score")

    def test_reply_begun_over_him_is_heard_and_scored_on_the_owner_s_voice_alone(self):
        """You start answering in his last words and carry on (ran on): the burst opened on his echo, as the canceller
        leaves it, and that opening is neither heard nor scored as you."""
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
        self.assertEqual(len(self.scored), 1, f"the reply was scored {len(self.scored)}x, not once")
        self.assert_speech_only(bytes(self.scored[0]), his, you, "the reply's voice score")

    def test_wake_word_clip_is_enrolled_without_its_lead_in(self):
        lead, speech = hiss(self.LEAD_IN, 8), clip("you_hey_void.wav")
        events, log = self.check_pcm(lead + speech, SAID["you_hey_void.wav"], follow=False)
        self.assertEqual(len(self.wakes(events)), 1, f"wake word not taken: {events}\n{log}")
        self.assertEqual(len(self.enrolled), 1, f"the wake-word clip was enrolled {len(self.enrolled)}x, not once")
        self.assert_speech_only(bytes(self.enrolled[0]), lead, speech, "the wake-word enrolment")

    def test_wake_word_enrolment_logs_the_voiceprint_enrolling_line(self):
        events, log = self.check_pcm(hiss(1.0, 9) + clip("you_hey_void.wav"), SAID["you_hey_void.wav"], follow=False)
        self.assertEqual(len(self.enrolled), 1, f"the wake-word clip was enrolled {len(self.enrolled)}x, not once")
        lines = [ln for ln in log if "voiceprint enrolling" in ln]
        self.assertEqual(len(lines), 1, f"a wake-word enrolment logged {len(lines)} 'voiceprint enrolling' lines, "
                                        f"not one:\n" + "\n".join(log))
        m = re.match(r"\[void\] voiceprint enrolling (\d+\.\d)s of your speech: (.+)$", lines[0])
        self.assertIsNotNone(m, f"not the line Listen logs ('voiceprint enrolling N.Ns of your speech: ...'): {lines[0]!r}")
        secs = len(self.enrolled[0]) / (server.RATE * 2)
        self.assertLessEqual(abs(float(m.group(1)) - secs), 0.1,
                             f"the line says {m.group(1)}s but {secs:.1f}s was enrolled: {lines[0]!r}")
        self.assertIn("open my downloads", m.group(2).lower(), f"the line doesn't say what was enrolled: {lines[0]!r}")

    def test_listen_wake_word_and_follow_up_cut_the_same_stretch_of_one_recording(self):
        server.CFG["voice_gate"] = True
        speech = clip("you_hey_void.wav")
        pcm = hiss(1.0, 10) + speech + hiss(0.6, 11)
        pcm = pcm[:len(pcm) // server.FRAME * server.FRAME]  # (whole 40 ms frames: Listen keeps every byte it reads)
        said = SAID["you_hey_void.wav"]

        class FakeMic:                           # the recording, 0.1 s a read, then the recorder ends
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

        with mock.patch.object(server, "open_clean_mic", lambda: (FakeMic(), "fake mic", b"")), \
                mock.patch.object(server, "transcribe_pcm", lambda b, **kw: said), \
                contextlib.redirect_stderr(io.StringIO()):
            server.Listen("ptt").run(lambda **ev: None)
        self.assertEqual(len(self.enrolled), 1, f"Listen enrolled {len(self.enrolled)} clip(s), not one")
        listen = bytes(self.enrolled[0])
        self.enrolled.clear()
        self.check_pcm(pcm, said, follow=False)
        self.assertEqual(len(self.enrolled), 1, f"the wake word enrolled {len(self.enrolled)} clip(s), not one")
        wake = bytes(self.enrolled[0])
        self.scored.clear()
        self.check_pcm(pcm, "Open my Downloads folder instead, and the Pictures one too.", follow=True)
        self.assertEqual(len(self.scored), 1, f"the follow-up was scored {len(self.scored)}x, not once")
        followed = bytes(self.scored[0])
        self.assertEqual((len(wake), len(followed)), (len(listen), len(listen)),
                         "Listen, the wake word and a follow-up cut different stretches of one recording "
                         f"(Listen {len(listen)} bytes, wake word {len(wake)}, follow-up {len(followed)})")
        self.assertTrue(wake == listen and followed == listen,
                        "Listen, the wake word and a follow-up cut different stretches of one recording")


if __name__ == "__main__":
    unittest.main()
