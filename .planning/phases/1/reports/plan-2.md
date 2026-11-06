PLAN COMPLETE
Plan: .planning/phases/1/PLAN-2.md
Tasks: 9 of 9
| Task | Commit | Note |
|---|---|---|
| 1 gate | none | already at the floor in the baseline (lines 99.06, branches 97.62); no tests added, per the plan's loop |
| 2 hearing | none | already at the floor (lines 98.12, branches 87.50); no tests added |
| 3 drops | cc0e7b9 | baseline lines 89.47, branches 81.82 (FAIL). New tests/test_drops.py (log forms, report text, main, script entry). Subset (test_drops, test_echo, test_log_cases, test_wake_loop) 103 passed; drops lines 100.00, branches 100.00 |
| 4 agents | f4acc7d | baseline lines 89.22, branches 81.94 (FAIL). Helper, KillTree (os.killpg and subprocess.run mocked: no real signal), StreamEvents and MoreBrain tests in tests/test_agents.py on the existing FakeProc harness, no real claude. 73 passed three runs in a row; lines 99.80, branches 96.76 on the subset; `ps` shows no leftover child |
| 5 macsys | 4aac55c | baseline lines 47.32, branches 33.33 (FAIL). New tests/test_macsys.py: a Sealed base makes any unmocked subprocess.run/Popen fail the test; osa, _run, _apps, _send and the CoreGraphics calls are replaced. Subset (test_macsys, test_audio_devices, test_mac_autostart, test_window_poll, test_quit, test_window_mac) 161 passed, none skipped; lines 100.00, branches 100.00. Slate volume (19) and clipboard hash unchanged before and after; test_macsys passes alone and after test_audio_devices. test_window_mac.py not changed (no gap there) |
| 6 langmark | none | already at the floor (lines 98.06, branches 94.44). Full run with -rs shows no RealPhonemes skip: the only 9 skips are tests/test_scenes.py "slow tier: set VOID_SCENES=1" |
| 7 notifier | none | already at the floor (lines 100.00, branches 100.00) |
| 8 Runner: no usable include list | 3ad5209 | Two new tests in tests/test_coverage_modules.py (no `include` key, `"include": {}`) failed before the fix (no-key printed the totals FAIL lines instead of the no-module line; `{}` exited 0), then 10 passed, none skipped. `run()` now sends only an unreadable report or policy to the checker passthrough; a readable policy whose include is missing, not an array, or empty prints `FAIL policy: coverage.include is missing or empty, so no module was checked`, exit 1. `--report /nonexistent.json` still prints `FAIL report: cannot read /nonexistent.json`, exit 1 |
| 9 tests workflow | 13a1d40 | Existing untracked file checked against the spec, no departure found, committed unchanged after the closing checks. `test-policy check` prints `"gate_found":true`; `grep -c 'continue-on-error\|fail-under\|paths:'` prints 0 |

Closing checks (run after Task 8, before Task 9; UV_PYTHON=3.12, PYTEST_ADDOPTS=-rs):
- AC3 local half: first accepted command, one process: 594 passed, 9 skipped (slow tier only), 297 s, exit 0. Second command exit 0 with all 14 lines `meets 85`: gate 99.06/97.62, hearing 98.12/87.50, agents 100.00/97.22, langmark 98.06/94.44, macsys 100.00/100.00, notifier 100.00/100.00, drops 100.00/100.00 (lines/branches).
- AC4 with tests/test_langmark.py moved aside: first command 576 passed, 9 skipped, exit 0; second command exit 1 printing `app/langmark.py: FAIL lines: 24.27% is below 85` and `app/langmark.py: FAIL branches: 0.00% is below 85`. Module used: langmark (not the agents fallback). File restored; `git status tests/` clean.
- Unchanged: nothing under app/, no pragma: no cover, no coverage config file, .planning/config.json and .github/cadence/coverage-policy.json untouched.
- Full suite for the contract: the AC3 run above, after the last code commit (3ad5209), GREEN. Task 9 added only the workflow file.

Deviations: none
Open items:
- AC4 wording: only the second accepted command exits non-zero without langmark's tests; the first (pytest) exits 0 because pytest carries no threshold (D-02). The pair as a gate fails, with the named FAIL line.
- CI halves of AC3 and AC5 (the `tests` job passing on a pushed `personal` commit, uploading coverage.json, no import or Playwright skip) are (ci: tests); they need the owner to authorize a push. Nothing was pushed.
- Flagged assumptions still unresolved until that first CI run: Qt/Cocoa not skipping on the runner, Playwright `channel: "chrome"`, no model download. Locally nothing skipped for an import.
- `required_jobs` names `build`, which does not run on `personal` pushes (owner's call, from Plan 1).
- hearing branches sit at 87.50, the thinnest margin over the floor; no test added there (the plan adds none for a module already at the floor).
- Uncommitted by this plan: the owner's .gitignore, .planning/STATE.md, CLAUDE.md edits and untracked .planning/, queues/, .claude/worktrees/ files; coverage.json and .coverage in the repo root are git-ignored outputs.
