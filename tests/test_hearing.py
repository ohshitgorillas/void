"""PlayRef keeps what the speakers play, by monotonic time, at 16 kHz mono s16le, with silence where nothing plays,
whatever rate the player itself runs at; and once the speakers are stopped, nothing after that moment plays.
Canceller takes Void's own voice out of the mic against that record, leaving yours; off, or without livekit, it hands
the mic back untouched and says so once.

    python3 -m unittest tests.test_hearing -v
"""
import array
import contextlib
import importlib
import io
import math
import random
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

try:
    import hearing
except Exception as e:  # noqa: BLE001
    hearing, IMPORT_ERR = None, e
else:
    IMPORT_ERR = None

try:
    import server
except Exception as e:  # noqa: BLE001
    server, SERVER_ERR = None, e
else:
    SERVER_ERR = None

SR = 16000                                                  # the rate PlayRef keeps
EDGE = 160                                                  # 10 ms of slack at a resampled edge


def pcm(samples):
    return array.array("h", samples).tobytes()


def samples(b):
    a = array.array("h")
    a.frombytes(b)
    return list(a)


def tone(value, rate, secs):
    """A steady level for `secs` at `rate`: survives any resampling as the same level."""
    return pcm([value] * round(rate * secs))


@unittest.skipIf(hearing is None, f"hearing.py doesn't import here: {IMPORT_ERR}")
class PlayRefTest(unittest.TestCase):
    def setUp(self):
        global hearing
        hearing = importlib.reload(hearing)                 # a fresh PlayRef: no state left by another test
        self.P = hearing.PlayRef

    def assertLevel(self, got, value, msg=""):
        self.assertTrue(got, f"no samples {msg}")
        bad = [x for x in got if abs(x - value) > max(64, abs(value) * 0.05)]
        self.assertFalse(bad, f"{len(bad)} of {len(got)} samples off level {value} {msg}: e.g. {bad[:5]}")

    def test_silence_where_nothing_has_played(self):
        self.assertEqual(self.P.span(100.0, 1600), bytes(3200))

    def test_span_is_n_samples_of_16k_s16le(self):
        self.P.played(tone(5000, 22050, 1.0), 22050, 100.0)
        for at, n in ((100.0, 1), (100.25, 4000), (99.0, 48000)):
            self.assertEqual(len(self.P.span(at, n)), 2 * n, f"span({at}, {n})")

    def test_16k_audio_comes_back_as_played(self):
        src = [(i * 37) % 20000 - 10000 for i in range(SR // 2)]
        self.P.played(pcm(src), SR, 100.0)
        self.assertEqual(samples(self.P.span(100.0, len(src))), src)

    def test_other_rates_come_back_at_16k_with_the_same_duration(self):
        self.P.played(tone(6000, 22050, 0.5), 22050, 100.0)       # half a second at the player's rate
        got = samples(self.P.span(100.0, SR))                      # one second at 16 kHz
        self.assertLevel(got[EDGE:SR // 2 - EDGE], 6000, "inside the half second played")
        self.assertLevel(got[SR // 2 + EDGE:], 0, "after it ends")

    def test_audio_sits_at_its_play_time(self):
        self.P.played(tone(7000, SR, 0.25), SR, 100.5)
        got = samples(self.P.span(100.0, SR))
        self.assertLevel(got[:SR // 2], 0, "before it plays")
        self.assertLevel(got[SR // 2:SR * 3 // 4], 7000, "while it plays")
        self.assertLevel(got[SR * 3 // 4:], 0, "after it ends")

    def test_chunks_follow_each_other_and_gaps_are_silent(self):
        self.P.played(tone(3000, 24000, 0.2), 24000, 100.0)
        self.P.played(tone(-4000, 24000, 0.2), 24000, 100.2)       # straight after the first
        self.P.played(tone(5000, 24000, 0.2), 24000, 100.6)        # after 200 ms of nothing
        got = samples(self.P.span(100.0, SR))
        ms = SR // 1000
        self.assertLevel(got[EDGE:200 * ms - EDGE], 3000, "first chunk")
        self.assertLevel(got[200 * ms + EDGE:400 * ms - EDGE], -4000, "second chunk")
        self.assertLevel(got[400 * ms + EDGE:600 * ms - EDGE], 0, "the gap")
        self.assertLevel(got[600 * ms + EDGE:800 * ms - EDGE], 5000, "third chunk")
        self.assertLevel(got[800 * ms + EDGE:], 0, "after the last")

    def test_cut_silences_everything_after_it(self):
        self.P.played(tone(8000, 22050, 1.0), 22050, 100.0)
        self.P.cut(100.4)
        got = samples(self.P.span(100.0, SR))
        self.assertLevel(got[EDGE:int(0.4 * SR) - EDGE], 8000, "before the cut")
        self.assertLevel(got[int(0.4 * SR) + EDGE:], 0, "after the cut")

    def test_playing_resumes_after_a_cut(self):
        self.P.played(tone(8000, SR, 1.0), SR, 100.0)
        self.P.cut(100.2)
        self.P.played(tone(-6000, SR, 0.2), SR, 100.5)
        got = samples(self.P.span(100.0, SR))
        self.assertLevel(got[:int(0.2 * SR)], 8000, "before the cut")
        self.assertLevel(got[int(0.2 * SR):int(0.5 * SR)], 0, "between the cut and the next chunk")
        self.assertLevel(got[int(0.5 * SR):int(0.7 * SR)], -6000, "the chunk played after the cut")
        self.assertLevel(got[int(0.7 * SR):], 0, "after it ends")


try:
    import livekit.rtc  # noqa: F401
except Exception as e:  # noqa: BLE001
    LIVEKIT_ERR = e
else:
    LIVEKIT_ERR = None

CHUNK = SR // 50                                            # the mic's 20 ms, in samples
T0 = 100.0                                                  # monotonic time the audio starts at


def rms(x):
    return math.sqrt(sum(v * v for v in x) / len(x)) if x else 0.0


def noise(secs, level, seed):
    """Speech-band-ish broadband sound: what Void's voice looks like to an echo canceller."""
    rng = random.Random(seed)
    return [max(-32768, min(32767, round(rng.gauss(0, level)))) for _ in range(round(SR * secs))]


def voice(secs, level):
    """Your voice: voiced harmonics, rising and falling four times a second like syllables."""
    n = round(SR * secs)
    return [round(level * (0.6 + 0.4 * math.sin(2 * math.pi * 4 * i / SR))
                  * (math.sin(2 * math.pi * 180 * i / SR) + 0.5 * math.sin(2 * math.pi * 360 * i / SR)
                     + 0.25 * math.sin(2 * math.pi * 540 * i / SR))) for i in range(n)]


@unittest.skipIf(hearing is None, f"hearing.py doesn't import here: {IMPORT_ERR}")
class CancellerTest(unittest.TestCase):
    def setUp(self):
        global hearing
        hearing = importlib.reload(hearing)                 # a fresh PlayRef: nothing left playing by another test

    def run_mic(self, c, mic):
        """Feed mic (samples from T0) through c in 20 ms chunks at their capture times; the cleaned samples back."""
        out = []
        for i in range(0, len(mic), CHUNK):
            chunk = pcm(mic[i:i + CHUNK])
            got = c.process(chunk, T0 + i / SR)
            self.assertEqual(len(got), len(chunk), f"process() at {T0 + i / SR:.2f} changed the length")
            out += samples(got)
        return out

    def assertPassesThrough(self, make):
        """Whatever `make` builds hands the mic back untouched, says it isn't cancelling, and says so once."""
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            c = make()
            hearing.PlayRef.played(pcm(noise(0.5, 4000, 1)), SR, T0)       # something playing: still untouched
            mic = noise(0.5, 3000, 2)
            for i in range(0, len(mic), CHUNK):
                chunk = pcm(mic[i:i + CHUNK])
                self.assertEqual(c.process(chunk, T0 + i / SR), chunk, f"mic changed at {T0 + i / SR:.2f}")
            self.assertEqual(c.process(pcm([123] * 77), T0 + 1), pcm([123] * 77), "an odd-sized chunk changed")
        self.assertIs(c.available, False)
        said = [ln for ln in err.getvalue().splitlines() if ln.startswith("[void]")]
        self.assertEqual(len(said), 1, f"expected one [void] line saying it passes the mic through, got {said}")

    def test_off_passes_the_mic_through_and_says_so_once(self):
        self.assertPassesThrough(lambda: hearing.Canceller(on=False))

    def test_passes_the_mic_through_when_livekit_cannot_load(self):
        blocked = {m: None for m in list(sys.modules) if m == "livekit" or m.startswith("livekit.")}
        blocked.update({"livekit": None, "livekit.rtc": None})            # None in sys.modules: import fails
        self.addCleanup(importlib.reload, hearing)                        # (after the patch lifts: the real livekit)
        with mock.patch.dict(sys.modules, blocked):
            importlib.reload(hearing)
            self.assertPassesThrough(lambda: hearing.Canceller(on=True))

    @unittest.skipIf(LIVEKIT_ERR is not None, f"livekit doesn't import here: {LIVEKIT_ERR}")
    def test_on_with_livekit_is_available(self):
        self.assertIs(hearing.Canceller().available, True)

    @unittest.skipIf(LIVEKIT_ERR is not None, f"livekit doesn't import here: {LIVEKIT_ERR}")
    def test_returns_the_length_it_was_given(self):
        c = hearing.Canceller(on=True)
        hearing.PlayRef.played(pcm(noise(1.0, 4000, 3)), SR, T0)
        at = T0
        for n in (160, 320, 480, 1, 77, 1000, 3200, 0):              # 10 ms multiples and not
            got = c.process(pcm(noise(n / SR, 3000, n)), at)
            self.assertEqual(len(got), 2 * n, f"process() of {n} samples")
            at += n / SR

    @unittest.skipIf(LIVEKIT_ERR is not None, f"livekit doesn't import here: {LIVEKIT_ERR}")
    def test_takes_his_own_voice_out_of_the_mic(self):
        far = noise(4.0, 4000, 4)
        hearing.PlayRef.played(pcm(far), SR, T0)
        d = SR // 200                                                # the room: 5 ms later, at half the level
        mic = [0] * d + [v // 2 for v in far[:-d]]
        out = self.run_mic(hearing.Canceller(on=True), mic)
        before, after = rms(mic[-SR:]), rms(out[-SR:])
        self.assertLess(after, before / 4, f"his echo in the last second: {after:.0f} RMS out of {before:.0f} in")

    @unittest.skipIf(LIVEKIT_ERR is not None, f"livekit doesn't import here: {LIVEKIT_ERR}")
    def test_leaves_your_voice_in_when_he_is_quiet(self):
        mic = voice(3.0, 3000)
        out = self.run_mic(hearing.Canceller(on=True), mic)
        before, after = rms(mic[-SR:]), rms(out[-SR:])
        self.assertGreater(after, before / 2, f"your voice in the last second: {after:.0f} RMS out of {before:.0f} in")


@unittest.skipIf(server is None, f"server.py doesn't import here: {SERVER_ERR}")
class EchoCancelSettingTest(unittest.TestCase):
    def test_echo_cancel_is_on_by_default(self):
        self.assertIs(server.DEFAULTS.get("echo_cancel"), True)


if __name__ == "__main__":
    unittest.main()
