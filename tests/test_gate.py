"""The follow-up gate (app/gate.py): one decision on a clip heard in the follow-up window without "hey Void". Music in
the room is dropped once the owner's voiceprint knows his voice; the owner himself is kept; until five of his clips are
enrolled only Whisper's confidence counts; the gate can be switched off in the config; `void doctor` says whether the
voiceprint is on and, when not, why. (What the gate adds to a follow-up's wall time is tested where it runs, in
Wake.check: tests/test_wake_loop.py.)

The voiceprint model is fetched on first use into Void's data folder (shared with the app), so the first run needs
the network.

    python3 -m unittest tests.test_gate -v
"""
import contextlib
import io
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCENES = ROOT / "tests" / "fixtures" / "scenes"
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "tests"))
import suite_data  # noqa: E402  (Void's data folder: the suite's own, set before server.py settles it)

try:
    import server
    import voiceprint
except Exception as e:  # noqa: BLE001
    server = voiceprint = None
    IMPORT_ERR = e
else:
    IMPORT_ERR = None

try:
    import gate
except Exception as e:  # noqa: BLE001
    gate, GATE_ERR = None, e
else:
    GATE_ERR = None

MODEL_DIR = suite_data.MODEL_DIR

ENROLL = ["you_stop.wav", "you_hold_on.wav", "you_shut_up.wav", "you_hey_void.wav", "you_answer.wav"]
OWNER = ["you_overlap.wav", "you_long_pauses.wav"]      # the owner, never enrolled
MUSIC = "room_music.wav"
WHYS = {"low confidence", "no speech", "not your voice", "kept"}


def pcm(name):
    with wave.open(str(SCENES / name), "rb") as w:
        return w.readframes(w.getnframes())


def sure(pcm_bytes, text="something was said here"):
    """What Whisper reports for a clip it is sure of: the confidence filters alone would let it through."""
    return server.Heard(text=text, logprob=-0.2, no_speech=0.02, seconds=len(pcm_bytes) / 32000)


def nothing():
    """What Whisper reports when it kept no segment at all (Heard's documented 'none' values)."""
    return server.Heard(text="", logprob=float("-inf"), no_speech=1.0, seconds=0.0)


def config(**over):
    cfg = dict(server.DEFAULTS)
    cfg.update(over)
    return cfg


@unittest.skipIf(server is None, f"server.py / voiceprint.py don't import here: {IMPORT_ERR}")
class Gate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.vp = voiceprint.Voiceprint(Path(cls.tmp.name) / "voiceprint", MODEL_DIR)
        if cls.vp.available:
            for n in ENROLL[:voiceprint.MIN_ENROLL]:
                cls.vp.enroll(pcm(n))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.assertIsNotNone(gate, f"app/gate.py doesn't import: {GATE_ERR}")
        self.assertTrue(self.vp.available, f"voiceprint unavailable: {self.vp.why}")

    def judge(self, heard, voice, cfg=None):
        v = gate.judge(heard, voice, config() if cfg is None else cfg)
        self.assertIsInstance(v.keep, bool)
        self.assertIn(v.why, WHYS)
        return v

    # ---- room music is dropped, the owner is kept
    def test_room_music_follow_up_is_dropped(self):
        clip = pcm(MUSIC)
        v = self.judge(sure(clip), self.vp.score(clip))
        self.assertFalse(v.keep, f"room music kept ({v.why})")
        self.assertEqual(v.why, "not your voice")

    def test_owner_follow_up_is_kept(self):
        for n in OWNER:
            with self.subTest(n):
                clip = pcm(n)
                v = self.judge(sure(clip), self.vp.score(clip))
                self.assertTrue(v.keep, f"the owner's {n} dropped ({v.why})")
                self.assertEqual(v.why, "kept")

    def test_a_clip_whisper_heard_nothing_in_is_dropped(self):
        v = self.judge(nothing(), None)
        self.assertFalse(v.keep, "a clip with no kept segment was kept")
        self.assertNotEqual(v.why, "kept")

    # ---- the voice only counts once five clips are enrolled
    def test_confidence_alone_until_five_clips_are_enrolled(self):
        clip = pcm(MUSIC)
        with tempfile.TemporaryDirectory() as d:
            vp = voiceprint.Voiceprint(Path(d) / "voiceprint", MODEL_DIR)
            for i, n in enumerate(ENROLL[:5]):
                v = self.judge(sure(clip), vp.score(clip))
                self.assertTrue(v.keep, f"room music dropped ({v.why}) with only {i} clips enrolled")
                vp.enroll(pcm(n))
            self.assertEqual(vp.enrolled, 5)
            v = self.judge(sure(clip), vp.score(clip))
            self.assertFalse(v.keep, "room music kept with five clips enrolled")

    # ---- switched off in the config
    def test_the_gate_switched_off_keeps_everything(self):
        clip = pcm(MUSIC)
        cfg = config(voice_gate=False)
        for heard, voice in ((sure(clip), self.vp.score(clip)), (nothing(), None)):
            v = self.judge(heard, voice, cfg)
            self.assertTrue(v.keep, f"dropped ({v.why}) with voice_gate off")


@unittest.skipIf(server is None, f"server.py / voiceprint.py don't import here: {IMPORT_ERR}")
class Config(unittest.TestCase):
    def test_config_has_the_gate_on_by_default_with_a_voice_threshold(self):
        self.assertIs(server.DEFAULTS.get("voice_gate"), True, "DEFAULTS has no voice_gate switched on")
        self.assertIsInstance(server.DEFAULTS.get("voice_min"), (int, float), "DEFAULTS has no voice_min")


@unittest.skipIf(server is None, f"server.py / voiceprint.py don't import here: {IMPORT_ERR}")
class DoctorVoiceprint(unittest.TestCase):
    """`void doctor` says whether the voiceprint is on and, when it isn't, why."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        for p in (mock.patch.object(server, "claude_bin", lambda: None),
                  mock.patch.object(server, "tts_engine", lambda: None),
                  mock.patch.object(server, "WIN", False),
                  mock.patch.object(server, "OSYS", None),
                  mock.patch.object(server, "mic_cmds", lambda: []),
                  mock.patch.object(server, "open_mic", mock.Mock(side_effect=RuntimeError("no mic in tests"))),
                  mock.patch.object(server.shutil, "which", lambda *a, **k: None)):
            p.start()
            self.addCleanup(p.stop)

    def doctor_lines(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            server.doctor()
        text = out.getvalue()
        lines = [ln for ln in text.splitlines() if "voiceprint" in ln.lower()]
        self.assertTrue(lines, f"nothing about the voiceprint in:\n{text}")
        return lines

    def test_doctor_says_the_voiceprint_is_on(self):
        with mock.patch.object(voiceprint, "fetch", lambda folder: MODEL_DIR / voiceprint.MODEL):
            lines = self.doctor_lines()
        self.assertTrue(any(" on" in ln.lower() and "unavailable" not in ln.lower() for ln in lines),
                        f"doesn't say the voiceprint is on: {lines}")

    def test_doctor_says_why_the_voiceprint_is_unavailable(self):
        why = "no route to the voiceprint model (test)"
        with mock.patch.object(voiceprint, "fetch", mock.Mock(side_effect=RuntimeError(why))):
            lines = self.doctor_lines()
        self.assertTrue(any(why in ln for ln in lines), f"doesn't say the voiceprint is unavailable because {why!r}: {lines}")


if __name__ == "__main__":
    unittest.main()
