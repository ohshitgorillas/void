PLAN COMPLETE
Plan: .planning/phases/1/PLAN-1.md
Tasks: 8 of 8
| Task | Commit | Note |
|---|---|---|
| 1 Vendor checker | 710b687 | `cmp` against the template exits 0; no-arg run prints `usage:` and exits 1 |
| 2 Per-module runner | 74394fc | exports print `function function function`; `--report /nonexistent.json` prints `FAIL report: cannot read /nonexistent.json`, exit 1; grep for 85 / comparisons finds nothing |
| 3 Runner tests | 55d87a8 | 7 passed, none skipped; with `node` off PATH 7 failed, none skipped; whole-report judging fails `test_high_total_hides_no_low_module`; reverted, `git diff .github/ci/` empty |
| 4 Ignore outputs | 5a4f07d | commit is `2 ++`; `git check-ignore coverage.json .coverage` prints both; owner's .gitignore edits still unstaged |
| 5 Requirements | 03ef50e | `uv pip compile` resolves; includes `livekit==1.1.21`, `pyside6`, `faster-whisper`, `kokoro-onnx` |
| 6 Render commands | 45d4f02 | config and policy change only the two `commands` entries |
| 7 Order dependence in `CoreAudio.test_audio_devices` | 1ce278c | the test now pops any earlier `macsys` from `sys.modules`, imports it afresh (so `winsys.devices = audio_devices` runs again), and restores the earlier module in `finally`. Predicted and observed: `test_audio_devices.py` alone 26 passed; `test_window_mac.py test_audio_devices.py` 72 passed; `test_audio_devices.py test_window_mac.py` 72 passed. `git diff --stat HEAD -- app/` empty. No other test in the file leans on the import-time assignment (`Base` sets `winsys.devices` itself in setUp). `.github/workflows/tests.yml` left untracked, untouched. |
| 8 Fix: empty `coverage.include` (risk_surface finding, medium) | 2f4b0f3 | `run()` now prints `FAIL policy: coverage.include is empty, so no module was checked` and returns 1 before slicing. New `test_empty_include_fails_saying_no_module_was_checked` failed first (exit 0, empty output), then passed; `tests.test_coverage_modules` 8 passed. No lint or typecheck command found. |

Full suite (no `workflow.test_command` set and no manifest; ran the plan's first accepted command, `UV_PYTHON=3.12 uvx --with pytest-cov --with-requirements tests/requirements.txt pytest --cov=app --cov-branch --cov-report=json`, one process): 492 passed, 9 skipped (all `tests/test_scenes.py` slow tier, VOID_SCENES unset), 172 subtests passed, 4m42s. GREEN. Re-run after the Task 8 fix (uvx PID 84264, pytest PID 84268); both have exited.

Deviations: none new. (Earlier Task 7 deviation in plan-1.1.md is superseded by the amendment in 0e1d85d.)
Open items:
- The second accepted command still exits 1 on the measured baseline (agents branches 81.94, macsys lines 45.30 / branches 30.56, drops branches 81.82 below 85); Plan 2 closes it.
- `required_jobs` names `build`, which does not run on `personal` pushes (owner's call, per the plan Notes).
- Flagged assumptions unresolved until first CI run: Qt/Cocoa not skipping on the runner; Playwright `channel: "chrome"`.
- `coverage.json` and `.coverage` sit in the repo root from the earlier local run (git-ignored).
