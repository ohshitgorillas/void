"""Scenes replayed through a simulated room into the real mic path: Void talks through the speakers, you talk into the
room, and Wake.session listens through open_clean_mic. Once Void has spoken through the clean mic in this run, at least
25 dB of his echo is removed, from the first second of every later mic session on; your speech after Void stops is
kept within about 3 dB; with the canceller missing, the mic is passed through unchanged. The follow-up gate is on, and
"you" is the voice it knows as its owner's, enrolled by saying "hey Void" (Void's voice and the music never are). Every
test starts a fresh run of Void (scenes.new_run), so none depends on which ran before it.

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
import suite_data  # noqa: E402  (Void's data folder: the suite's own, set before server.py settles it)

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
SWITCH = 3.0                # the speakers change this long after his voice starts
DELAYS = (0.010, 0.020, 0.030, 0.040)   # speakers this far off Speaker.LAT: the range real hardware lands in
FIRST = 1.0                 # the first this-many seconds of every warm mic session must already have his echo out
MID_VOICE = 2.0             # a session that opens while he is already talking opens this far into his voice
CUT_IN = (1.0, 2.0, 3.0, 4.0)   # you tell him to stop this far into his voice (he talks for 7.7 s)
SAID = {                    # each way to stop him, said on its own, as people say it: its words and how long they take
    "interrupt_stop": ("Stop, stop.", 1.02),
    "interrupt_hold_on": ("Hold on.", 0.72),
    "interrupt_shut_up": ("Shut up.", 0.39),
    "interrupt_hey_void": ("Hey Void.", 0.72),
}


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


class FreshRun(unittest.TestCase):
    """Each test starts, and leaves behind, a fresh run of Void: no canceller kept from another test's scenes, and a
    voiceprint holding only your enrolled voice, in a file of the harness's own."""
    def setUp(self):
        scenes.new_run()
        self.addCleanup(scenes.new_run)


@unittest.skipIf(server is None, f"server.py doesn't import here: {IMPORT_ERR}")
class FastScenes(FreshRun):
    @unittest.skipIf(LIVEKIT_ERR is not None, f"livekit doesn't import here: {LIVEKIT_ERR}")
    def test_removes_at_least_25_db_of_his_echo(self):
        sc = SCENES["void_alone"]
        scenes.warm_up(scenes.Room())                              # (he has already spoken in this run)
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

    @unittest.skipIf(LIVEKIT_ERR is not None, f"livekit doesn't import here: {LIVEKIT_ERR}")
    def test_removes_at_least_25_db_of_his_echo_after_the_speakers_change(self):
        sc = SCENES["void_alone"]
        t = scenes.play(scenes.Room(), void=sc["void"], switch_at=SWITCH)
        want = None if t.void_start is None else t.void_start + SWITCH
        self.assertTrue(t.switched is not None and want is not None and abs(t.switched - want) <= 0.02,
                        f"the speakers didn't change {SWITCH} s into his voice: switched at {t.switched}, "
                        f"his voice started at {t.void_start}")
        n = (t.void_end or 0.0) + TAIL - t.switched
        removed = level_db(window(t.raw, t.switched, n)) - level_db(window(t.clean, t.switched, n))
        self.assertGreaterEqual(removed, ECHO_REMOVED_DB,
                                f"only {removed:.1f} dB of Void's echo removed after the speakers changed")

    @unittest.skipIf(LIVEKIT_ERR is not None, f"livekit doesn't import here: {LIVEKIT_ERR}")
    def test_removes_at_least_25_db_of_his_echo_in_the_first_second_of_every_session_once_he_has_spoken(self):
        sc = SCENES["void_alone"]
        for delay in DELAYS:
            for mic_at, when in ((0.0, "as his voice starts"), (MID_VOICE, f"{MID_VOICE} s into his voice")):
                with self.subTest(delay=delay, opens=when):
                    scenes.new_run()
                    scenes.warm_up(scenes.Room(delay=delay))       # (he has spoken through the clean mic in this run)
                    t = scenes.play(scenes.Room(delay=delay), void=sc["void"], mic_at=mic_at)
                    removed = level_db(window(t.raw, t.mic_from, FIRST)) - level_db(window(t.clean, t.mic_from, FIRST))
                    self.assertGreaterEqual(removed, ECHO_REMOVED_DB,
                                            f"only {removed:.1f} dB of Void's echo removed in the first {FIRST} s of a "
                                            f"later mic session in the run, opened {when}, speakers {delay * 1000:.0f} ms off Speaker.LAT")

    def _stops_him(self, name):
        sc, (words, length) = SCENES[name], SAID[name]
        for at in CUT_IN:
            with self.subTest(said=words, into_his_voice=at):
                scenes.new_run()
                scenes.warm_up(scenes.Room())                      # (he has already spoken in this run)
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    t = scenes.play(scenes.Room(), void=sc["void"], you=sc["you"], you_at=at,
                                    you_only=(words, length))
                log = [ln for ln in err.getvalue().splitlines() if ln.startswith("[void]")]
                self.assertTrue(any(e["t"] == "barge" for e in did(t)),
                                f"\"{words}\" said {at} s into his voice didn't stop him: its opening came through "
                                + ("unmeasured" if t.opening_db is None else f"{t.opening_db:+.1f} dB")
                                + f" against how you said it{instead(t, log)}")

    @unittest.skipIf(LIVEKIT_ERR is not None, f"livekit doesn't import here: {LIVEKIT_ERR}")
    def test_stop_said_over_him_stops_him(self):
        self._stops_him("interrupt_stop")

    @unittest.skipIf(LIVEKIT_ERR is not None, f"livekit doesn't import here: {LIVEKIT_ERR}")
    def test_hold_on_said_over_him_stops_him(self):
        self._stops_him("interrupt_hold_on")

    @unittest.skipIf(LIVEKIT_ERR is not None, f"livekit doesn't import here: {LIVEKIT_ERR}")
    def test_shut_up_said_over_him_stops_him(self):
        self._stops_him("interrupt_shut_up")

    @unittest.skipIf(LIVEKIT_ERR is not None, f"livekit doesn't import here: {LIVEKIT_ERR}")
    def test_hey_void_said_over_him_stops_him(self):
        self._stops_him("interrupt_hey_void")

    @unittest.skipIf(LIVEKIT_ERR is not None, f"livekit doesn't import here: {LIVEKIT_ERR}")
    def test_every_recorded_event_carries_its_scene_time_in_seconds_from_the_start(self):
        sc = SCENES["interrupt_stop"]
        scenes.warm_up(scenes.Room())                              # (he has already spoken in this run)
        with contextlib.redirect_stderr(io.StringIO()):
            t = scenes.play(scenes.Room(), void=sc["void"], you=sc["you"], you_at=CUT_IN[0],
                            you_only=SAID["interrupt_stop"])
        self.assertTrue(t.events, "the scene recorded no events at all")
        for e in t.events:
            self.assertIn("scene_at", e, f"event carries no scene time: {e}")
            self.assertIsInstance(e["scene_at"], (int, float), f"scene time is not seconds: {e}")
            self.assertGreaterEqual(e["scene_at"], 0.0, f"scene time before the scene's start: {e}")
            if e.get("t") == "spk":      # the server's own `at` (ms, where in the playback) is left as it put it
                self.assertIn("at", e, f"the spk event lost the server's own `at`: {e}")
                self.assertNotEqual(e["at"], e["scene_at"], f"the scene stamp overwrote the server's `at`: {e}")

    @unittest.skipIf(LIVEKIT_ERR is not None, f"livekit doesn't import here: {LIVEKIT_ERR}")
    def test_him_talking_alone_does_nothing(self):
        scenes.warm_up(scenes.Room())                              # (he has already spoken in this run)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            t = scenes.play(scenes.Room(), void=SCENES["void_alone"]["void"])
        log = [ln for ln in err.getvalue().splitlines() if ln.startswith("[void]")]
        self.assertEqual(did(t), [], f"Void acted on his own voice:{instead(t, log)}")

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
PROMPT = 1.5                # a stop word said over him stops him this soon, though you go on talking
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
class SlowScenes(FreshRun):
    def test_void_talking_alone_produces_nothing(self):
        t, log = heard(SCENES["void_alone"])
        self.assertEqual(did(t), [], f"Void acted on his own voice:{instead(t, log)}")

    def _interrupts(self, name):
        t, log = heard(SCENES[name], you_at=OVER)
        self.assertTrue(any(e["t"] == "barge" for e in did(t)),
                        f"{name}: Void wasn't interrupted:{instead(t, log)}")

    def test_stop_over_void_interrupts_him(self):
        self._interrupts("interrupt_stop")

    def test_stop_over_void_stops_him_while_you_are_still_talking(self):
        t, log = heard(SCENES["interrupt_stop"], you_at=OVER)
        barge = [e for e in did(t) if e["t"] == "barge"]
        self.assertTrue(barge and t.you_start is not None and barge[0]["scene_at"] - t.you_start <= PROMPT,
                        "interrupt_stop: Void wasn't stopped within " + f"{PROMPT} s of you starting"
                        + (f" (stopped {barge[0]['scene_at'] - t.you_start:.1f} s in)" if barge and t.you_start is not None else "")
                        + instead(t, log))

    def test_shut_up_over_void_interrupts_him(self):
        self._interrupts("interrupt_shut_up")

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
