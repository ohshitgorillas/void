PLAN CHECKPOINT: blocked
Plan: .planning/phases/3/PLAN-2.md
Tasks: 6 of 8
| Task | Commit | Note |
|---|---|---|
| 1 - open build worktree | none (worktree) | /Users/atom/dev/void-replay on macos; S = 226ed6ae290ff6bdb669f1f6c9477e7f85e53dac; porcelain empty |
| 2 - void drops prints every judged burst | 77d89cc | real log: 128175 rows, 126684 stamped (= grep count 126684), 126723 dropped, 24 of those kept now; gate.py diff vs S empty |
| 3 - determinism test | d54b5db | new Main test passes; two real-log runs diff to nothing |
| 4 - YOURS as regression table | 00326c0 | 12 row tests + length test pass; mutating one row's why to "echo" failed that row alone; no HIS_* line changed |
| 5 - owner's reported drops in the table | 98eac42 | 43 row tests: 20 pass, 23 XFAIL (all "Phase 4: ..."), 0 skipped/failed/XPASS; each phased row's gate verdict matches the logged class (echo / no wake word / while talking); mutating "Yes and yes" to today's verdict gave [XPASS(strict)] and a red run (restored from a scratchpad copy, since the file was uncommitted, not by git checkout) |
| 6 - prove the gates on macos | none (verification) | py_compile exit 0; full suite with coverage (PYTEST_ADDOPTS=-rsxX): 591 passed, 11 skipped, 23 xfailed in 242 s; the 11 skips are all "slow tier: set VOID_SCENES=1" in test_hearing.py / test_scenes.py, none in test_log_cases.py or test_drops.py; 23 test_log_cases XFAIL reasons all open "Phase 4"; coverage-modules.mjs exit 0: app/drops.py 100.00% lines / 100.00% branches, app/gate.py 99.06% / 97.62%; git diff 226ed6a..macos -- app/gate.py empty; AC5 grep -F -f (132595 whole real-log lines of 20+ chars against 141 added test lines) printed nothing, probe with a real line was found; row-length test passed |
| 7 - merge macos into personal | not done | blocked, see Open items |
| 8 - remove build worktree | not done | /Users/atom/dev/void-replay still exists (macos at 98eac42) |
Deviations: none
Open items:
- BLOCKED at Task 7: its precondition `git status --porcelain --untracked-files=no` in /Users/atom/dev/void on personal is not empty: ` M .planning/STATE.md`. STATE.md is the orchestrator's to write, so I did not touch it. After it is committed or otherwise cleared, run Task 7 (git merge macos, default message; checks per the plan) and Task 8. Nothing was merged or pushed. Refs now: macos 98eac42, personal 3f1dd05, origin/macos 29e22ae, origin/personal 9b309e0 (unchanged).
- Task 6 grep note: `git grep -n 'gate\.judge' app/drops.py` prints three lines (module docstring line 1, now() docstring line 71, the one call at line 78). The call at line 78, inside now(), is the only one.
- Task 2 stale heard flags (not fixed): replay keeps the last heard line's flags until the next heard line, so a verdict line with no heard line of its own (the quick listen before a heard line) is judged with the previous burst's "while talking". The test_drops.py fixture line 8 shows it ("kept: stops him", commented). In the real log it touches few rows (14 "KEPT: STOPS HIM" kept rows, all peek/over bursts or a bare "Void"). Pre-existing behavior of drop rows too, left as is; resetting flags after each verdict would change drop rows' printed verdicts beyond this plan.
- Task 4/5 table: dropped the voiceprint score from the YOURS tuples (Row has no score field; the voiceprint is gone). O-17/O-18 (identical text, kind, talking, expected) are one row. The "talking" column of DROPS.md was used as logged (O-27, O-28, O-29, O-37, O-42, O-43 are over bursts with talking False; the verdict is the same either way). "Yes, do it" is two rows (wake and follow); test ids carry the kind: "Yes, do it (wake)", "Yes, do it (follow)".
- Fixture lines added to the drops tests use 2026-12-01 as the stamp (outside 26 Oct to 5 Nov).
- Declined fuller shapes: no --all flag (Verify asks for kept rows by default); Drop class not renamed to Row-like name (tests use drops.Drop; one class holds drops and kept rows, why="kept").
