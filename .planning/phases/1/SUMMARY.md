---
phase: 1
status: complete
completed: 2026-11-06
---

# Phase 1: Coverage gate - Summary

A `tests` job on `macos-14` (`.github/workflows/tests.yml`) runs the full suite with branch coverage, then a per-module gate (`.github/ci/coverage-modules.mjs`) that fails, naming the module, when any fork-owned file in the policy's `include` list is below 85% lines or branches. New tests bring `drops`, `agents` and `macsys` up to that floor.

## What shipped

- Vendored Cadence coverage report checker - `.github/cadence/coverage-report-check.mjs`
- Per-module coverage runner that slices `coverage.json` by the policy's `include` list and judges each module separately - `.github/ci/coverage-modules.mjs`
- Runner tests on hand-built reports, including the missing, non-array and empty `include` cases - `tests/test_coverage_modules.py`
- Runtime package list for the suite - `tests/requirements.txt`
- Accepted coverage commands rendered into `.planning/config.json` and `.github/cadence/coverage-policy.json`
- Coverage outputs ignored - `.gitignore` (`coverage.json`, `.coverage`)
- New module tests: `tests/test_drops.py`, `tests/test_agents.py` (additions), `tests/test_macsys.py`
- Order-independent Core Audio test - `tests/test_audio_devices.py`
- CI workflow - `.github/workflows/tests.yml`, job `tests` on `macos-14`, pushes to `macos` and `personal`

## Commits

| Plan | Task | Commit | Description |
|---|---|---|---|
| 1 | 1 | 710b687 | Vendor the Cadence coverage report checker |
| 1 | 2 | 74394fc | Add the per-module coverage runner |
| 1 | 3 | 55d87a8 | Prove the per-module gate on hand-built reports |
| 1 | 4 | 5a4f07d | Ignore coverage outputs |
| 1 | 5 | 03ef50e | Declare the app's runtime packages for the suite |
| 1 | 6 | 45d4f02 | Render the accepted coverage commands |
| 1 | 7 | 1ce278c | Import `macsys` afresh in the Core Audio test so it ignores collection order |
| 1 | 8 | 2f4b0f3 | Fail the gate when the policy's `include` list is empty (risk_surface round 1) |
| 2 | 1 | none | `gate` already at the floor (99.06 / 97.62) |
| 2 | 2 | none | `hearing` already at the floor (98.12 / 87.50) |
| 2 | 3 | cc0e7b9 | Cover `drops` log forms, report text and command entry |
| 2 | 4 | f4acc7d | Cover `agents` stream events, kill tree, Brain restart and stop |
| 2 | 5 | 4aac55c | Cover `macsys` at the process boundary and its Cocoa helpers |
| 2 | 6 | none | `langmark` already at the floor (98.06 / 94.44) |
| 2 | 7 | none | `notifier` already at the floor (100 / 100) |
| 2 | 8 | 3ad5209 | Fail the gate when `include` is missing or not an array (risk_surface round 2) |
| 2 | 9 | 13a1d40 | Run the suite and the per-module gate on `macos-14` |

Plan amendments: 0e1d85d (move the workflow commit to the end of Plan 2), 18c56ef (carry the missing-include runner fix into Plan 2).

## Deviations

- [deviation] `CoreAudio.test_audio_devices` already failed when the whole suite ran in one process, because an earlier test's `macsys` import skipped the import-time `winsys.devices` assignment. Fixed in the test, not the app: it re-imports `macsys` and restores the earlier module (1ce278c). Recorded as Plan 1 Task 7 by amendment 0e1d85d.
- [deviation] The workflow commit was held until Plan 2 was green, so no commit ever carried a gate that would fail on the baseline (0e1d85d; workflow landed as 13a1d40).
- [deviation] risk_surface on Plan 1 (matched `destructive`, `untrusted_input`) found the gate passed with an empty `include` list; fixed in 2f4b0f3. The capped round-2 re-fire found the same pass with `include` missing or `{}`; carried into Plan 2 by amendment 18c56ef and fixed in 3ad5209. Both findings were medium, ruled survived with their fix commits (`ADJUDICATION-risk_surface-plan-1.json`, `-r2.json`).

## Open items

- The CI halves of criteria 3 and 4 (the `tests` job passing on a pushed `personal` commit and uploading `coverage.json`, and failing when a module's tests are removed) have not run: nothing has been pushed, and a push of `personal` needs the owner's authorization.
- Assumptions unresolved until that first CI run: Qt/Cocoa tests not skipping on the runner, Playwright `channel: "chrome"`, no model download. Locally nothing skipped for an import.
- `required_jobs` names `build`, which does not run on `personal` pushes (owner's call, from Plan 1's Notes).
- Criterion 4 wording: with `tests/test_langmark.py` removed, only the second accepted command exits non-zero (`app/langmark.py: FAIL lines: 24.27% is below 85`); pytest itself carries no threshold (D-02) and exits 0. The job as a whole fails.
- `hearing` branches sit at 87.50, the thinnest margin over the floor.
- The project has never set `review.triggers.risk_surface.surfaces`; this phase's risk checks passed all eight categories on the command line, and the choice is not saved to config.

## Goal check

The commits plausibly deliver the goal locally. `.github/workflows/tests.yml:8-9` defines job `tests` on `macos-14`, triggered on pushes to `macos` and `personal` (`:5-6`), running the first accepted command (`:24`, pytest with `--cov-branch`) and the per-module gate (`:26`), which meets criterion 1. `planning.mjs test-policy check --root .` returns `"gate_found":true` (re-run at summary time), which meets criterion 2. For criterion 3, Plan 2's executor reports the full suite at 594 passed, 9 skipped (slow-tier scenes only) after the last code commit 3ad5209, and the gate exiting 0 with all 14 module lines at or above 85 (plan-2 report, closing checks). For criterion 4, the same report shows the gate exiting 1 with `app/langmark.py: FAIL lines: 24.27% is below 85` when that module's tests were moved aside. The coordinator did not re-run the suite. The round-2 risk finding was reproduced against HEAD at summary time: a policy with `include` missing, `{}` or `[]` now exits 1 with `FAIL policy: coverage.include is missing or empty, so no module was checked`. What is missing is any CI evidence: the job has never run on a runner.

complete locally, not CI-verified
