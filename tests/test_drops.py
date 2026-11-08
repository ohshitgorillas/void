"""`void drops` (app/drops.py): a server log read back into its heard bursts, kept and dropped, the report printed, and
the command's entry.

test_log_cases.py replays the owner's 26 Oct log through it; this file holds the other log forms, the report text and
`main`.

    python3 -m unittest tests.test_drops -v
"""
import contextlib
import io
import runpy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "tests"))
import suite_data  # noqa: E402,F401  (Void's data folder: the suite's own)
import drops  # noqa: E402

LOOP = ("one two three four. " * 4)[:80]     # a looping sentence, cut by the log at 80 characters

LOG = "\n".join([
    "Traceback (most recent call last):",                                   # 1: not a server log line
    "[void] heard 2.0s, 4 words (follow-up)",                               # 2
    "[void] dropped follow-up, not your voice (voice 0.43): Keep it moving",  # 3: his follow-up, the old voiceprint drop
    "[void] ignored while talking: and then the next step",                 # 4
    "[void] heard 1.0s, 3 words while talking",                             # 5
    "[void] dropped echo of own speech: so the build is done",              # 6: kind from the heard line above
    "[void] 2026-11-01 10:00:00 no wake word (wake): what time is it",      # 7
    "[void] 2026-11-02 10:00:00 kept (wake): hey Void what time is it",     # 8: kept, so not a drop
    "[void] 2026-11-02 10:05:00 while talking (over): stop",                # 9: the stop phrase said over him
    '[void] ignored: no "hey Void": turn it up',                            # 10
    "[void] ignored stray word: Keep it moving",                            # 11
    "[void] heard 3.0s, 20 words",                                          # 12
    "[void] dropped as noise: " + "a" * 80,                                 # 13: logged at the cut, a looping sentence
    "[void] dropped as noise: ",                                            # 14: nothing was heard
    "[void] 2026-11-03 08:00:00 no speech (follow) (voice n/a): music",     # 15
    "[void] 2026-12-01 10:00:00 kept (wake): " + LOOP,                      # 16: kept at the cut, a loop today's gate drops
])


class Replay(unittest.TestCase):
    def rows(self, day=None):
        return [(d.line, d.at, d.why, d.kind, d.text, d.now) for d in drops.replay(LOG.splitlines(), day)]

    def test_each_log_form_is_a_row_with_its_verdict_and_kind(self):
        self.assertEqual(self.rows(), [
            (3, "", "not your voice", "follow", "Keep it moving", "kept"),       # he said it: today it gets through
            (4, "", "while talking", "over", "and then the next step", "while talking"),
            (6, "", "echo", "over", "so the build is done", "as logged"),        # it rang, so it needs his words: not logged
            (7, "2026-11-01 10:00:00", "no wake word", "wake", "what time is it", "no wake word"),
            # (line 5's heard line pairs with line 6 alone: line 8 has none of its own, so it is judged as a plain wake)
            (8, "2026-11-02 10:00:00", "kept", "wake", "hey Void what time is it", "kept"),
            (9, "2026-11-02 10:05:00", "while talking", "over", "stop", "kept: stops him"),
            (10, "", "no wake word", "wake", "turn it up", "no wake word"),
            (11, "", "stray word", "follow", "Keep it moving", "kept"),
            (13, "", "noise", "wake", "a" * 80, "as logged"),                    # a looping sentence needs all of it
            (14, "", "noise", "wake", "", "noise"),
            (15, "2026-11-03 08:00:00", "no speech", "follow", "music", "as logged"),
            (16, "2026-12-01 10:00:00", "kept", "wake", LOOP, "as logged"),     # a loop needs all of it, as a drop's does
        ])

    def test_a_heard_line_pairs_with_the_one_verdict_line_after_it(self):
        log = ["[void] heard 1.0s, 3 words, while talking",
               "[void] dropped as noise: ",                       # pairs with the heard line: over him
               "[void] dropped as noise: "]                       # its own heard line is missing: a plain wake
        self.assertEqual([(d.kind, d.now) for d in drops.replay(log)], [("over", "noise"), ("wake", "noise")])

    def test_an_echo_drop_with_no_heard_line_of_its_own_replays_as_logged(self):
        log = ["[void] heard 2.0s, 3 words, follow-up", "[void] echo (follow): Yes, do it",      # clear of him: judged
               "[void] echo (follow): Yes, do it",                                               # no heard line: as logged
               "[void] heard 2.0s, 3 words, follow-up, in his echo", "[void] echo (follow): Yes, do it"]  # it rang
        self.assertEqual([d.now for d in drops.replay(log)], ["kept", "as logged", "as logged"])

    def test_lines_that_are_not_server_log_lines_are_skipped_but_counted(self):
        got = drops.replay(["Traceback", "", "[void] dropped echo of own speech: hello there"])
        self.assertEqual([d.line for d in got], [3])

    def test_a_kept_line_is_a_row_too(self):
        self.assertEqual(drops.parse("kept (follow): Yes"), ("kept", "follow", "Yes"))
        self.assertIsNone(drops.parse("listening"))

    def test_a_day_keeps_only_lines_stamped_that_day(self):
        self.assertEqual([r[0] for r in self.rows("2026-11-02")], [8, 9])
        self.assertEqual(self.rows("2030-01-01"), [])

    def test_a_heard_line_names_the_kind_of_the_drop_after_it(self):
        self.assertEqual(drops._kind(" (follow-up)"), "follow")
        self.assertEqual(drops._kind(" while talking"), "over")
        self.assertEqual(drops._kind(""), "wake")


class Report(unittest.TestCase):
    DROPS = [
        drops.Drop(4, "", "no wake word", "wake", "hello there", "no wake word"),
        drops.Drop(9, "2026-11-01 10:00:00", "echo", "over", "so the build", "as logged"),
        drops.Drop(12, "", "no wake word", "follow", "Keep it moving", "kept"),
        drops.Drop(13, "", "while talking", "over", "stop", "kept: stops him"),
        drops.Drop(14, "", "kept", "wake", "hey Void hello", "kept"),
    ]

    def test_one_row_per_burst_then_a_count_per_verdict_and_of_the_drops_kept(self):
        dash = "-" + " " * 18
        self.assertEqual(drops.report(self.DROPS), [
            f"     4  {dash}  no wake word (wake)  ->  drops: no wake word  hello there",
            "     9  2026-11-01 10:00:00  echo (over)  ->  as logged  so the build",
            f"    12  {dash}  no wake word (follow)  ->  KEPT  Keep it moving",
            f"    13  {dash}  while talking (over)  ->  KEPT: STOPS HIM  stop",
            f"    14  {dash}  kept (wake)  ->  KEPT  hey Void hello",
            "",
            "     2  no wake word",
            "     1  echo",
            "     1  while talking",
            "     1  kept",
            "     5  heard in all; 4 dropped, 2 of them kept now",
        ])

    def test_no_rows_still_reports_the_total(self):
        self.assertEqual(drops.report([]), ["", "     0  heard in all; 0 dropped, 0 of them kept now"])


class Main(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.log = Path(tmp.name) / "server.log"
        self.log.write_bytes(LOG.encode() + b"\n[void] 2026-11-04 09:00:00 no wake word (wake): caf\xff\n")

    def out(self, *argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            drops.main(list(argv))
        return buf.getvalue().splitlines()

    def test_prints_the_report_of_the_named_log(self):
        lines = self.out(str(self.log))
        self.assertEqual(lines[-1], "    13  heard in all; 11 dropped, 3 of them kept now")
        self.assertIn("  no wake word (wake)  ->  drops: no wake word  what time is it", lines[3])

    def test_bytes_that_are_not_text_are_read_through(self):
        self.assertTrue(any(ln.endswith("  caf�") for ln in self.out(str(self.log))))

    def test_day_filters_before_or_after_the_log_name(self):
        for argv in (("--day", "2026-11-02", str(self.log)), (str(self.log), "--day", "2026-11-02")):
            lines = self.out(*argv)
            self.assertEqual(len(lines), 6)
            self.assertIn("kept (wake)  ->  KEPT  hey Void what time is it", lines[0])
            self.assertIn("KEPT: STOPS HIM  stop", lines[1])
            self.assertEqual(lines[-1], "     2  heard in all; 1 dropped, 1 of them kept now")

    def test_without_a_name_it_reads_the_default_log(self):
        with mock.patch.object(drops, "LOG", self.log):
            self.assertEqual(self.out("--day", "2026-11-04")[-1], "     1  heard in all; 1 dropped, 0 of them kept now")

    def test_one_log_replays_to_identical_lines(self):
        first, second = self.out(str(self.log)), self.out(str(self.log))
        self.assertGreater(len(first), 10)       # (old and stamped, kept and dropped rows went through both runs)
        self.assertEqual(first, second)

    def test_run_as_a_script_it_prints_the_same_report(self):
        buf = io.StringIO()
        with mock.patch.object(sys, "argv", ["drops.py", str(self.log)]), contextlib.redirect_stdout(buf):
            runpy.run_path(str(ROOT / "app" / "drops.py"), run_name="__main__")
        self.assertEqual(buf.getvalue().splitlines(), self.out(str(self.log)))


if __name__ == "__main__":
    unittest.main()
