"""PlayRef keeps what the speakers play, by monotonic time, at 16 kHz mono s16le, with silence where nothing plays,
whatever rate the player itself runs at; and once the speakers are stopped, nothing after that moment plays.

    python3 -m unittest tests.test_hearing -v
"""
import array
import importlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

try:
    import hearing
except Exception as e:  # noqa: BLE001
    hearing, IMPORT_ERR = None, e
else:
    IMPORT_ERR = None

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


if __name__ == "__main__":
    unittest.main()
