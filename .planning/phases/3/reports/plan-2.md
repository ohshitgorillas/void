PLAN COMPLETE
Plan: .planning/phases/3/PLAN-2.md
Tasks: 8 of 8
| Task | Commit | Note |
|---|---|---|
| 1 - open build worktree | none (worktree) | /Users/atom/dev/void-replay on macos; S = 226ed6ae290ff6bdb669f1f6c9477e7f85e53dac; porcelain empty |
| 2 - void drops prints every judged burst | 77d89cc | real log: 128175 rows, 126684 stamped (= grep count 126684), 126723 dropped, 24 of those kept now; gate.py diff vs S empty |
| 3 - determinism test | d54b5db | new Main test passes; two real-log runs diff to nothing |
| 4 - YOURS as regression table | 00326c0 | 12 row tests + length test pass; mutating one row's why to "echo" failed that row alone; no HIS_* line changed |
| 5 - owner's reported drops in the table | 98eac42 | 43 row tests: 20 pass, 23 XFAIL (all "Phase 4: ..."), 0 skipped/failed/XPASS; mutating "Yes and yes" to today's verdict gave [XPASS(strict)] and a red run (restored from a scratchpad copy) |
| 6 - prove the gates on macos | none (verification) | py_compile exit 0; full suite with coverage (PYTEST_ADDOPTS=-rsxX): 591 passed, 11 skipped, 23 xfailed in 242 s; the 11 skips are all "slow tier: set VOID_SCENES=1", none in test_log_cases.py or test_drops.py; 23 XFAIL reasons all open "Phase 4"; coverage-modules.mjs exit 0: app/drops.py 100.00% lines / 100.00% branches, app/gate.py 99.06% / 97.62%; git diff 226ed6a..macos -- app/gate.py empty; AC5 grep -F -f printed nothing (probe with a real line was found); row-length test passed |
| 7 - merge macos into personal | 2552790 (merge) | tracked porcelain was empty; `git merge macos` clean (4 files, 165+/58-); `git diff macos personal` on the four files empty; `rev-list --count personal..macos` = 0; drops + log_cases tests on personal: 41 passed, 23 xfailed (same 23 xfails as Task 5); origin/macos 29e22ae and origin/personal 9b309e0 unchanged |
| 8 - remove build worktree | none (worktree) | /Users/atom/dev/void-replay removed, no longer in `git worktree list`. Final: macos 98eac42, personal 2552790, origin/macos 29e22ae; stream/replies-after-quiet ce5b1e5, stream/stop-echo 3ef6fbc, ci-debug/fake-servers e667dad unchanged |
Deviations: none
Open items:
- Task 6 grep note: `git grep -n 'gate\.judge' app/drops.py` prints three lines (module docstring, now() docstring, the one call at line 78). The call in now() is the only one.
- Task 2 stale heard flags (not fixed): replay keeps the last heard line's flags until the next heard line, so a verdict line with no heard line of its own is judged with the previous burst's "while talking". In the real log it touches few rows (14 "KEPT: STOPS HIM" kept rows). Pre-existing for drop rows too; resetting flags would change drop rows' printed verdicts beyond this plan.
- Task 4/5 table: dropped the voiceprint score from the YOURS tuples (Row has no score field). O-17/O-18 are one row. "talking" used as logged in DROPS.md. "Yes, do it" is two rows (wake and follow).
- Fixture lines added to the drops tests use 2026-12-01 as the stamp (outside 26 Oct to 5 Nov).
- Declined fuller shapes: no --all flag; Drop class not renamed (one class holds drops and kept rows, why="kept").
- Previous checkpoint report kept as plan-2.1.md (rotated before this write). Task 7 earlier blocked on the coordinator's STATE.md write, since committed as b9de3a5.
- Final full suite not re-run after the merge: Task 6's single allowed run was on the identical tree (macos 98eac42); the merge adds no file change beyond macos's, and the two touched test files were re-run on personal.
