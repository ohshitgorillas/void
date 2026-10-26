"""Void must finish the sentence on the new speakers when you pick others while he talks: Speaker._write opens a new
player and carries on, including the part the old one had queued but never played.

    python3 -m unittest discover -s tests
"""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import suite_data  # noqa: E402  (Void's data folder: the suite's own, set before server.py settles it)

try:
    import server
except Exception as e:  # noqa: BLE001
    server, IMPORT_ERR = None, e
else:
    IMPORT_ERR = None

RATE = 8000
STEP = 320                                                 # bytes per write: 20 ms at RATE
DATA = bytes(range(256)) * 19                              # 4864 bytes, 15.2 steps; no two chunks alike


class FakeProc:
    """A player that plays in real time (the clock moves 20 ms per step) and dies after `dies` writes."""
    def __init__(self, clock, dies=None, on_die=None):
        self.clock, self.dies, self.on_die, self.got, self.dead = clock, dies, on_die, b"", False
        self.stdin = self

    def write(self, b):
        if self.dies is not None and len(self.got) // STEP >= self.dies:
            self.dead = True
            if self.on_die:
                self.on_die()
            raise BrokenPipeError("the speakers have changed")
        self.got += b
        self.clock[0] += STEP / 2 / RATE

    def flush(self):
        pass

    def poll(self):
        return 0 if self.dead else None

    def kill(self):
        pass


@unittest.skipIf(server is None, f"server.py doesn't import here: {IMPORT_ERR}")
class SwitchSpeakers(unittest.TestCase):
    def setUp(self):
        S = server.Speaker
        self.clock = [100.0]
        self.made = []
        for k, v in (("gen", 7), ("proc", None), ("prate", RATE), ("written", 1000), ("t0", 100.0), ("filled", False),
                     ("stats", {})):
            p = mock.patch.object(S, k, v)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(server.time, "monotonic", lambda: self.clock[0])
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch.object(server, "make_player", self.make_player)
        p.start()
        self.addCleanup(p.stop)
        self.old = FakeProc(self.clock, dies=10)           # 1000 samples (125 ms) queued, then it dies
        S.proc = self.old
        self.spare = []                                    # the players the Speaker will be given next

    def make_player(self, rate):
        proc = self.spare.pop(0) if self.spare else FakeProc(self.clock)
        self.made.append(proc)
        return proc

    def test_carries_on_from_what_the_old_player_still_had_queued(self):
        self.assertTrue(server.Speaker._write(DATA, 7))
        self.assertEqual(len(self.made), 1)
        new = self.made[0]
        self.assertIs(server.Speaker.proc, new)
        self.assertEqual(len(self.old.got), 10 * STEP)
        self.assertEqual(new.got, DATA[len(DATA) - len(new.got):])      # the end of the sentence, whole
        back = len(new.got) - (len(DATA) - 10 * STEP)
        self.assertAlmostEqual(back, 1000 * 2, delta=4)                 # replays the queue, nothing more
        self.assertEqual(server.Speaker.written, len(new.got) // 2)     # the clock counts from the new player

    def test_cut_off_meanwhile_returns_false(self):
        self.old.on_die = lambda: setattr(server.Speaker, "gen", 8)
        self.assertFalse(server.Speaker._write(DATA, 7))
        self.assertEqual(self.made, [])

    def test_stopped_returns_false(self):
        self.old.on_die = lambda: setattr(server.Speaker, "proc", None)
        self.assertFalse(server.Speaker._write(DATA, 7))
        self.assertEqual(self.made, [])

    def test_gives_up_after_one_new_player(self):
        self.spare = [FakeProc(self.clock, dies=3)]
        self.assertFalse(server.Speaker._write(DATA, 7))
        self.assertEqual(len(self.made), 1)

    def test_no_new_player_returns_false(self):
        with mock.patch.object(server, "make_player", side_effect=OSError("no speakers")), \
                mock.patch.object(sys, "stderr"):
            self.assertFalse(server.Speaker._write(DATA, 7))


OPEN = 0.1                                                 # seconds the new speakers take to open (a DAC waking up)


def fresh_ref():
    """A PlayRef of its own, empty, to hold what the speakers truly played (and when) for comparison."""
    P = server.hearing.PlayRef
    return type("TrueRef", (P,), {"ring": server.hearing.np.zeros(len(P.ring), server.hearing.np.int16),
                                  "lo": None, "hi": None, "tail": None})


@unittest.skipIf(server is None, f"server.py doesn't import here: {IMPORT_ERR}")
class SwitchKeepsTheEchoReference(unittest.TestCase):
    """After a switch, PlayRef holds what the new speakers play, when they play it, and nothing the dead player was
    handed but never played; so the echo canceller keeps cancelling."""
    setUp_switch = SwitchSpeakers.setUp

    def setUp(self):
        self.setUp_switch()
        P = server.hearing.PlayRef
        for k, v in (("ring", server.hearing.np.zeros(len(P.ring), server.hearing.np.int16)), ("lo", None),
                     ("hi", None), ("tail", None)):
            p = mock.patch.object(P, k, v)
            p.start()
            self.addCleanup(p.stop)
        self.died = []                                     # the clock at each player's death
        self.old.on_die = lambda: self.died.append(self.clock[0])
        self.lat = server.Speaker.LAT
        self.open_takes = OPEN

    def make_player(self, rate):
        self.clock[0] += self.open_takes                   # opening the new speakers takes a moment
        proc = self.spare.pop(0) if self.spare else FakeProc(self.clock)
        if proc.on_die is None:
            proc.on_die = lambda: self.died.append(self.clock[0])
        self.opened = self.clock[0]
        self.made.append(proc)
        return proc

    def span(self, ref, a, b):
        n = int(round((b - a) * server.hearing.SR))
        return server.hearing.np.frombuffer(ref.span(a, n), server.hearing.np.int16)

    def truth(self, players):
        """A PlayRef fed only what each player really played: (pcm handed over, its first sample heard at, stopped
        at or None). Chunks go in as Speaker._write hands them over, 20 ms at a time."""
        ref = fresh_ref()
        for pcm, at, stop in players:
            for k in range(0, len(pcm), STEP):
                ref.played(pcm[k:k + STEP], RATE, at + k / 2 / RATE)
            if stop is not None:
                ref.cut(stop)
        return ref

    def test_nothing_the_dead_player_never_played_stays_in_the_reference(self):
        self.assertTrue(server.Speaker._write(DATA, 7))
        self.assertEqual(len(self.made), 1)
        dead_from = self.died[0] + self.lat                # the old speakers fell silent here
        new_from = self.opened + self.lat                  # and the new ones started here
        gap = self.span(server.hearing.PlayRef, dead_from, new_from)
        self.assertGreater(len(gap), 0)
        loud = server.hearing.np.flatnonzero(gap)
        self.assertEqual(len(loud), 0, f"PlayRef holds {len(loud)} samples of the dead player's unplayed queue "
                                       f"between its death ({dead_from:.3f}) and the new speakers ({new_from:.3f})")

    def test_reference_matches_what_the_old_then_new_speakers_played(self):
        self.assertTrue(server.Speaker._write(DATA, 7))
        new = self.made[0]
        dead_from, new_from = self.died[0] + self.lat, self.opened + self.lat
        old_from = 100.0 + 1000 / RATE + self.lat          # after the 1000 samples queued before this sentence
        new_to = new_from + len(new.got) / 2 / RATE
        want = self.truth([(self.old.got, old_from, dead_from), (new.got, new_from, None)])
        got = self.span(server.hearing.PlayRef, old_from, new_to)
        exp = self.span(want, old_from, new_to)
        bad = server.hearing.np.flatnonzero(got != exp)
        self.assertEqual(len(bad), 0, f"PlayRef differs from what the speakers played at {len(bad)} of {len(exp)} "
                                      f"samples, first at {old_from + (bad[0] if len(bad) else 0) / server.hearing.SR:.4f}"
                                      f" (old died {dead_from:.3f}, new from {new_from:.3f})")

    def test_new_speakers_are_heard_from_when_they_open(self):
        self.assertTrue(server.Speaker._write(DATA, 7))
        new = self.made[0]
        new_from = self.opened + self.lat
        new_to = new_from + len(new.got) / 2 / RATE
        want = self.truth([(new.got, new_from, None)])
        got = self.span(server.hearing.PlayRef, new_from, new_to)
        exp = self.span(want, new_from, new_to)
        self.assertTrue(exp.any())
        bad = server.hearing.np.flatnonzero(got != exp)
        self.assertEqual(len(bad), 0, f"the new speakers' audio isn't in PlayRef where they play it: "
                                      f"{len(bad)} of {len(exp)} samples differ")

    def test_giving_up_leaves_nothing_after_the_last_player_died(self):
        self.open_takes = 0.0                              # at once: the old queue would have outlasted the new player
        self.spare = [FakeProc(self.clock, dies=3)]
        self.assertFalse(server.Speaker._write(DATA, 7))
        self.assertEqual(len(self.died), 2)
        silent_from = self.died[1] + self.lat              # nothing plays after the second player died
        after = self.span(server.hearing.PlayRef, silent_from, silent_from + 1.0)
        loud = server.hearing.np.flatnonzero(after)
        self.assertEqual(len(loud), 0, f"PlayRef holds {len(loud)} samples after the last player died at "
                                       f"{silent_from:.3f}, first at {silent_from + (loud[0] if len(loud) else 0) / server.hearing.SR:.4f}")


if __name__ == "__main__":
    unittest.main()
