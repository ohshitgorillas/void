"""Scenes replayed through a simulated room into the real mic path: Void talks through the speakers, you talk into the
room, and Wake.session listens through open_clean_mic. At least 25 dB of Void's echo is removed; your speech after
Void stops is kept within about 3 dB; with the canceller missing, the mic is passed through unchanged.

Fast tier (always runs; speech detection and Whisper stood in for):
    ~/.local/share/void/venv/bin/python -m unittest tests.test_scenes
Slow tier (real speech detection and Whisper): VOID_SCENES=1, same command.
"""
import json
import math
import sys
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "app"))
sys.path.insert(0, str(HERE))

try:
    import server
except Exception as e:  # noqa: BLE001
    server, IMPORT_ERR = None, e
else:
    IMPORT_ERR = None

try:
    import livekit.rtc  # noqa: F401
except Exception as e:  # noqa: BLE001
    LIVEKIT_ERR = e
else:
    LIVEKIT_ERR = None

import scenes  # noqa: E402

SR = 16000
MANIFEST = json.loads((scenes.FIXTURES / "manifest.json").read_text(encoding="utf-8"))
CLIPS, SCENES = MANIFEST["clips"], MANIFEST["scenes"]

ECHO_REMOVED_DB = 25.0      # at least this much of Void's echo is taken out
KEPT_DB = 3.0               # your speech after he stops comes through within about this much
SETTLE = 1.0                # seconds the canceller has to learn the room before his echo is measured
TAIL = 0.1                  # and his echo is measured this far past his voice's end (the room's reflections)
AFTER = 0.5                 # you answer this long after his voice stops


def seconds(name):
    return CLIPS[name]["seconds"]


def window(x, start, length):
    """x from `start` seconds for `length` seconds on the scene's clock; empty when there is no start."""
    if start is None:
        return np.zeros(0, np.int16)
    a = max(0, round(start * SR))
    return x[a:a + round(length * SR)]


def level_db(x):
    """Mean power of x in dB (int16 units): -inf for silence; NaN when there is nothing to measure."""
    if not len(x):
        return math.nan
    p = float(np.mean(np.asarray(x, np.float64) ** 2))
    return 10 * math.log10(p) if p > 0 else -math.inf


@unittest.skipIf(server is None, f"server.py doesn't import here: {IMPORT_ERR}")
class FastScenes(unittest.TestCase):
    @unittest.skipIf(LIVEKIT_ERR is not None, f"livekit doesn't import here: {LIVEKIT_ERR}")
    def test_removes_at_least_25_db_of_his_echo(self):
        sc = SCENES["void_alone"]
        t = scenes.play(scenes.Room(), void=sc["void"])
        start = None if t.void_start is None else t.void_start + SETTLE
        n = seconds(sc["void"]) - SETTLE + TAIL
        removed = level_db(window(t.raw, start, n)) - level_db(window(t.clean, start, n))
        self.assertGreaterEqual(removed, ECHO_REMOVED_DB,
                                f"only {removed:.1f} dB of Void's echo removed while he talked alone")

    @unittest.skipIf(LIVEKIT_ERR is not None, f"livekit doesn't import here: {LIVEKIT_ERR}")
    def test_keeps_your_speech_after_he_stops(self):
        sc = SCENES["answer_after"]
        t = scenes.play(scenes.Room(), void=sc["void"], you=sc["you"], you_at=seconds(sc["void"]) + AFTER)
        n = seconds(sc["you"])
        off = level_db(window(t.clean, t.you_start, n)) - level_db(window(t.you, t.you_start, n))
        self.assertLessEqual(abs(off), KEPT_DB, f"your answer after he stopped came through {off:+.1f} dB off")

    def test_passes_the_mic_through_unchanged_without_the_canceller(self):
        sc = SCENES["interrupt_stop"]
        with mock.patch.object(server.hearing, "rtc", None):            # livekit missing: no canceller
            t = scenes.play(scenes.Room(), void=sc["void"], you=sc["you"], you_at=2.0)
        differ = int(np.count_nonzero(t.clean != t.raw)) if len(t.clean) == len(t.raw) else None
        self.assertTrue(len(t.raw) > 0 and differ == 0,
                        f"the mic didn't come through unchanged: {len(t.raw)} samples picked up, {len(t.clean)} "
                        f"read, {differ} of them different")


# Slow tier (VOID_SCENES=1: real speech detection and Whisper) goes here.


if __name__ == "__main__":
    unittest.main()
