"""Pings in, at most one turn out per quiet spell, no model call."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
import notifier


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, s):
        self.t += s


QUIET = 20.0
HOLD = 120.0


class Batching(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.batch = notifier.PingBatch(quiet_s=QUIET, hold_s=HOLD, clock=self.clock)

    def test_nothing_due_with_no_pings(self):
        self.assertIsNone(self.batch.due())
        self.clock.advance(HOLD * 3)
        self.assertIsNone(self.batch.due())

    def test_due_once_quiet_spell_has_passed(self):
        self.batch.add("build finished")
        self.clock.advance(QUIET - 1)
        self.assertIsNone(self.batch.due())
        self.clock.advance(1)
        self.assertEqual(self.batch.due(), ["build finished"])

    def test_each_new_line_restarts_the_quiet_spell(self):
        for line in ("one", "two", "three"):
            self.batch.add(line)
            self.clock.advance(QUIET - 5)
            self.assertIsNone(self.batch.due())
        self.clock.advance(5)
        self.assertEqual(self.batch.due(), ["one", "two", "three"])

    def test_due_after_hold_even_if_never_quiet(self):
        self.batch.add("first")
        lines = ["first"]
        while self.clock.t + 10 < 1000.0 + HOLD:
            self.clock.advance(10)
            self.assertIsNone(self.batch.due())
            line = f"line at {self.clock.t - 1000.0:.0f}s"
            self.batch.add(line)
            lines.append(line)
        self.clock.advance(1000.0 + HOLD - self.clock.t)
        self.assertEqual(self.batch.due(), lines)

    def test_one_batch_per_quiet_spell(self):
        for line in ("a", "b", "c", "d", "e"):
            self.batch.add(line)
            self.clock.advance(1)
        self.clock.advance(QUIET)
        self.assertEqual(self.batch.due(), ["a", "b", "c", "d", "e"])
        self.assertIsNone(self.batch.due())
        self.clock.advance(HOLD * 2)
        self.assertIsNone(self.batch.due())

    def test_next_batch_starts_fresh_after_one_is_handed_back(self):
        self.batch.add("old")
        self.clock.advance(QUIET)
        self.assertEqual(self.batch.due(), ["old"])
        self.batch.add("new")
        self.clock.advance(QUIET - 1)
        self.assertIsNone(self.batch.due())
        self.clock.advance(1)
        self.assertEqual(self.batch.due(), ["new"])


class Digest(unittest.TestCase):
    def test_one_line_per_ping_in_arrival_order(self):
        text = notifier.digest(["tests green", "deploy done", "backup ok"])
        self.assertEqual(text.splitlines(), ["tests green", "deploy done", "backup ok"])

    def test_single_ping_is_its_own_line(self):
        self.assertEqual(notifier.digest(["only one"]).splitlines(), ["only one"])


if __name__ == "__main__":
    unittest.main()
