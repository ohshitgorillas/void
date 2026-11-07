PLAN CHECKPOINT: decision
Plan: .planning/phases/1/PLAN-3.md
Tasks: 3 of 8
| Task | Commit | Note |
|---|---|---|
| 1 | e433e99 | fake servers log to a file; start asserts carry the log tails; VOID_TEST_LOGS copies them out. 18 passed before/after; probe run (RuntimeError before bind) showed `RuntimeError: probe` in all three message shapes (launchers foreign_server, quit WindowKeepsTheRecord.start, quit LauncherQuit server.log) and the logs landed in the VOID_TEST_LOGS dir; probe reverted |
| 2 | d158c18 | tests.yml: VOID_TEST_LOGS in the Suite step's env under runner.temp; `failed-start-logs` upload under `if: failure()`, if-no-files-found: ignore. test-policy check gate_found:true; grep -c for continue-on-error/fail-under/paths: = 0; both accepted commands found verbatim. Commit type is chore (ci is not in the contract's type list) |
| 3 | 72e9dad | notch assertions and real-split test report RM.matches/lowFx/frames; INIT gains a reference rAF counter, rate messages show page loop vs browser rate. 18 passed, same count. Forced-reduce run (`--force-prefers-reduced-motion` took in Qt's Chromium): NotchShift "0 not greater than 3 : shift to 30, page: RM.matches=true lowFx=false, 0 frames seen"; SplitEyes "0.792 != 0 : page: RM.matches=true lowFx=false, 85 frames seen"; hypothesis for cluster (c) reproduced locally |
| 4 | none | CHECKPOINT: needs the owner's authorization, this turn, to push `personal` (e433e99, d158c18, 72e9dad plus the earlier unpushed commits) for a diagnostic tests-job run. Blocks Tasks 5-8 |
Deviations: none
Open items: Logs helper is duplicated in tests/test_launchers.py and tests/test_quit.py (a shared tests module is outside the lease). Reference rAF loop in tests/test_page_idle.py INIT adds one callback per frame to the measured page. I left a stray `cat` (PID 11100) running from a mistaken command; killed by PID, verified gone.
