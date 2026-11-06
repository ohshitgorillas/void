"""Tests for .github/ci/coverage-modules.mjs: the per-module coverage gate, on hand-built coverage.py reports.
Needs `node` on PATH. A missing node fails these tests on purpose: a skip would let CI go green without the gate
ever being tested.

    python3 -m unittest tests.test_coverage_modules
"""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNNER = ".github/ci/coverage-modules.mjs"
GATE, LANGMARK = "app/gate.py", "app/langmark.py"   # tracked files: the checker confirms include paths with git ls-files


def summary(lines, covered, branches, covered_branches):
    """A coverage.py `files[<f>]` entry with that `summary`."""
    return {"summary": {"covered_lines": covered, "num_statements": lines,
                        "covered_branches": covered_branches, "num_branches": branches}}


def run_modules(tmp, files, include, report_text=None):
    """Writes tmp/coverage.json and tmp/policy.json (floor 85 on lines and branches), runs the runner from the repo root."""
    totals = {key: sum(f["summary"][key] for f in files.values())
              for key in ("covered_lines", "num_statements", "covered_branches", "num_branches")}
    report = tmp / "coverage.json"
    report.write_text(report_text if report_text is not None else
                      json.dumps({"meta": {"branch_coverage": True}, "totals": totals, "files": files}))
    policy = tmp / "policy.json"
    policy.write_text(json.dumps({"coverage": {"lines": 85, "branches": 85, "statements": 0,
                                               "include": include, "exclude": [], "commands": []}}))
    return subprocess.run(["node", RUNNER, "--report", str(report), "--policy", str(policy)],
                          cwd=ROOT, capture_output=True, text=True, timeout=60)


class CoverageModules(unittest.TestCase):
    def setUp(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        self.tmp = Path(tmpdir.name)

    def lines_for(self, result, name):
        return [line for line in result.stdout.splitlines() if line.startswith(f"{name}: ")]

    def test_every_module_at_floor_passes(self):
        files = {GATE: summary(100, 85, 20, 17), LANGMARK: summary(200, 200, 40, 40)}
        r = run_modules(self.tmp, files, [GATE, LANGMARK])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for name in (GATE, LANGMARK):
            got = self.lines_for(r, name)
            self.assertTrue(any(l.startswith(f"{name}: lines:") and "meets 85" in l for l in got), r.stdout)
            self.assertTrue(any(l.startswith(f"{name}: branches:") and "meets 85" in l for l in got), r.stdout)

    def test_module_lines_below_floor_fails_naming_it(self):
        files = {GATE: summary(100, 99, 20, 20), LANGMARK: summary(100, 84, 20, 20)}
        r = run_modules(self.tmp, files, [GATE, LANGMARK])
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(f"{LANGMARK}: FAIL lines:", r.stdout)
        self.assertNotIn(f"{GATE}: FAIL", r.stdout)

    def test_module_branches_below_floor_fails_naming_it(self):
        files = {GATE: summary(100, 99, 20, 20), LANGMARK: summary(100, 99, 20, 16)}
        r = run_modules(self.tmp, files, [GATE, LANGMARK])
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(f"{LANGMARK}: FAIL branches:", r.stdout)
        self.assertNotIn(f"{GATE}: FAIL", r.stdout)

    def test_high_total_hides_no_low_module(self):
        # the report's totals are 1090/1100 lines (99%), far above the floor; the small module alone is at 50%
        files = {GATE: summary(1000, 1000, 100, 100), LANGMARK: summary(100, 50, 20, 20)}
        r = run_modules(self.tmp, files, [GATE, LANGMARK])
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(f"{LANGMARK}: FAIL lines:", r.stdout)
        self.assertNotIn(f"{GATE}: FAIL", r.stdout)

    def test_module_absent_from_report_fails_naming_it(self):
        r = run_modules(self.tmp, {GATE: summary(100, 99, 20, 20)}, [GATE, LANGMARK])
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertTrue(any("FAIL" in l and LANGMARK in l for l in self.lines_for(r, LANGMARK)), r.stdout)
        self.assertNotIn(f"{GATE}: FAIL", r.stdout)

    def test_glob_include_entry_fails(self):
        r = run_modules(self.tmp, {GATE: summary(100, 99, 20, 20)}, ["app/*.py", GATE])
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("FAIL app/*.py: include entries must be file paths", r.stdout)
        self.assertTrue(any("lines:" in l and "meets 85" in l for l in self.lines_for(r, GATE)), r.stdout)

    def test_empty_include_fails_saying_no_module_was_checked(self):
        r = run_modules(self.tmp, {GATE: summary(100, 10, 20, 2)}, [])
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("no module was checked", r.stdout)

    def test_unreadable_report_fails(self):
        r = run_modules(self.tmp, {}, [GATE], report_text="{ not json")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("FAIL", r.stdout)


if __name__ == "__main__":
    unittest.main()
