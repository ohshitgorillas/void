"""Scenes replayed through a simulated room into the real mic path: Void talks through the speakers, you talk into the
room, and Wake.session listens through open_clean_mic. At least 25 dB of Void's echo is removed; your speech after
Void stops is kept within about 3 dB; with the canceller missing, the mic is passed through unchanged.

Fast tier (always runs; speech detection and Whisper stood in for):
    ~/.local/share/void/venv/bin/python -m unittest tests.test_scenes
Slow tier (real speech detection and Whisper): VOID_SCENES=1, same command.
"""
import contextlib
import io
import json
import math
import os
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


# Slow tier (VOID_SCENES=1): real speech detection and Whisper base.en hear each scene; what Void did is read off the
# BUS events Wake.check publishes ("barge": you stopped him; "wake": a request, follow=True when no "hey Void").

OVER = 2.0                  # you cut in this long after his voice starts
LAST_SECOND = 0.5           # and start this long before his voice ends to talk over his last second


def heard(sc, you_at=0.0):
    """Play scene `sc` with real hearing: the Take, plus what Void logged hearing and deciding (his "[void]" lines)."""
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        t = scenes.play(scenes.Room(music=sc.get("room")), void=sc.get("void"), you=sc.get("you"),
                        you_at=you_at, hear=True)
    return t, [ln for ln in err.getvalue().splitlines() if ln.startswith("[void]")]


def did(t):
    """Just the events that are Void acting on what he heard: interruptions and requests."""
    return [e for e in t.events if e.get("t") in ("barge", "wake")]


def instead(t, log):
    """What Void did instead, for a failure message: his interruptions and requests, every event kind seen, and his
    log of what he heard and made of it."""
    lines = "".join(f"\n    {ln}" for ln in log) or " nothing logged"
    return (f"\n  Void did: {did(t) or 'nothing'}\n  events seen: {sorted({e.get('t') for e in t.events})}"
            f"\n  heard:{lines}")


@unittest.skipUnless(os.environ.get("VOID_SCENES") == "1", "slow tier: set VOID_SCENES=1")
@unittest.skipIf(server is None, f"server.py doesn't import here: {IMPORT_ERR}")
@unittest.skipIf(LIVEKIT_ERR is not None, f"livekit doesn't import here: {LIVEKIT_ERR}")
class SlowScenes(unittest.TestCase):
    def test_void_talking_alone_produces_nothing(self):
        t, log = heard(SCENES["void_alone"])
        self.assertEqual(did(t), [], f"Void acted on his own voice:{instead(t, log)}")

    def _interrupts(self, name):
        t, log = heard(SCENES[name], you_at=OVER)
        self.assertTrue(any(e["t"] == "barge" for e in did(t)),
                        f"{name}: Void wasn't interrupted:{instead(t, log)}")

    # Expected failure until addition 1 of stage a (stop words over Void) lands: the canceller turns your voice down 7-8 dB for its first second over him, and Whisper hears "That's not what I asked for" with no "Stop, stop".
    @unittest.expectedFailure
    def test_stop_over_void_interrupts_him(self):
        self._interrupts("interrupt_stop")

    def test_hold_on_over_void_interrupts_him(self):
        self._interrupts("interrupt_hold_on")

    def _follows_up(self, name, you_at):
        t, log = heard(SCENES[name], you_at=you_at)
        got = did(t)
        self.assertTrue(len(got) == 1 and got[0]["t"] == "wake" and got[0].get("follow"),
                        f"{name}: not taken as one follow-up request:{instead(t, log)}")

    # Expected failure until stage b: "Move them into Pictures, please." is heard right, then dropped by is_echo as his own voice, because it repeats his words. Stage b trusts the echo canceller over word-matching.
    @unittest.expectedFailure
    def test_answering_just_after_void_finishes_is_a_follow_up(self):
        sc = SCENES["answer_after"]
        self._follows_up("answer_after", seconds(sc["void"]) + AFTER)

    def test_starting_in_his_last_second_and_carrying_on_is_a_follow_up(self):
        sc = SCENES["overlap_last_second"]
        self._follows_up("overlap_last_second", seconds(sc["void"]) - LAST_SECOND)

    def test_room_music_with_no_reference_gives_nothing(self):
        t, log = heard(SCENES["room_music"])
        self.assertEqual(did(t), [], f"Void acted on the room's music:{instead(t, log)}")


if __name__ == "__main__":
    unittest.main()
