"""The owner's voiceprint (app/voiceprint.py): once it has heard enough of the owner's own clips, the owner's voice
scores above Void's own voice (Kokoro) and above music playing in the room. It says when it can't work and why, and it
gives no score at all until enough clips are enrolled.

The model is fetched on first use into Void's data folder, so the first run needs the network.

    python3 -m unittest tests.test_voiceprint -v
"""
import os
import sys
import tempfile
import unittest
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCENES = ROOT / "tests" / "fixtures" / "scenes"
sys.path.insert(0, str(ROOT / "app"))

try:
    import voiceprint
except Exception as e:  # noqa: BLE001
    voiceprint, IMPORT_ERR = None, e
else:
    IMPORT_ERR = None

DATA_DIR = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share") / "void"
MODEL_DIR = DATA_DIR / "voices" / "voiceprint"     # shared with the app, so the model is fetched once

ENROLL = ["you_stop.wav", "you_hold_on.wav", "you_shut_up.wav", "you_hey_void.wav", "you_answer.wav"]
HELD_OUT = ["you_overlap.wav", "you_long_pauses.wav"]   # the owner, never enrolled
NOT_OWNER = ["void_question.wav", "room_music.wav"]     # Void's own voice; music in the room


def pcm(name):
    with wave.open(str(SCENES / name), "rb") as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, 16000), name
        return w.readframes(w.getnframes())


class Voiceprint(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(voiceprint, f"app/voiceprint.py doesn't import: {IMPORT_ERR}")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "voiceprint"

    def ready(self):
        vp = voiceprint.Voiceprint(self.path, MODEL_DIR)
        self.assertTrue(vp.available, f"voiceprint unavailable: {vp.why}")
        self.assertEqual(vp.why, "")
        return vp

    def test_no_score_until_enough_clips_are_enrolled(self):
        vp = self.ready()
        self.assertEqual(vp.enrolled, 0)
        self.assertIsNone(vp.score(pcm(HELD_OUT[0])))
        clips = [pcm(n) for n in ENROLL]
        for i in range(voiceprint.MIN_ENROLL):
            vp.enroll(clips[i % len(clips)])
            self.assertEqual(vp.enrolled, i + 1)
            if vp.enrolled < voiceprint.MIN_ENROLL:
                self.assertIsNone(vp.score(pcm(HELD_OUT[0])), f"scored with {vp.enrolled} clips enrolled")
        self.assertIsInstance(vp.score(pcm(HELD_OUT[0])), float)

    def test_owner_scores_above_void_and_room_music(self):
        vp = self.ready()
        clips = [pcm(n) for n in ENROLL]
        for i in range(max(len(clips), voiceprint.MIN_ENROLL)):
            vp.enroll(clips[i % len(clips)])
        owner = {n: vp.score(pcm(n)) for n in HELD_OUT}
        other = {n: vp.score(pcm(n)) for n in NOT_OWNER}
        for scores in (owner, other):
            for n, s in scores.items():
                self.assertIsInstance(s, float, n)
        self.assertGreater(min(owner.values()), max(other.values()), f"owner {owner}, not owner {other}")

    def test_says_when_unavailable_and_why(self):
        blocker = Path(self.tmp.name) / "not_a_folder"
        blocker.write_text("a file where the model folder should be")
        vp = voiceprint.Voiceprint(self.path, blocker / "models")
        self.assertFalse(vp.available)
        self.assertIsInstance(vp.why, str)
        self.assertTrue(vp.why.strip(), "unavailable without saying why")
        vp.enroll(pcm(ENROLL[0]))
        self.assertIsNone(vp.score(pcm(HELD_OUT[0])))


if __name__ == "__main__":
    unittest.main()
