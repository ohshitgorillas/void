---
phase: 1
status: complete
completed: 2026-11-07
---

# Phase 1: Coverage gate - Summary

A `tests` job on `macos-15` (`.github/workflows/tests.yml`) runs the full suite with branch coverage, then a per-module gate (`.github/ci/coverage-modules.mjs`) that fails, naming the module, when any fork-owned file in the policy's `include` list is below 85% lines or branches. New tests bring `drops`, `agents` and `macsys` up to that floor. The `tests` job is green on the runner (run 42362803211 at 89f4bfe). The last 14 failures were fake servers stuck in `HTTPServer.server_bind`'s `socket.getfqdn("127.0.0.1")`, which blocks about 35 s on macos-15. Every test server now binds without that lookup.

## What shipped

- Vendored Cadence coverage report checker - `.github/cadence/coverage-report-check.mjs`
- Per-module coverage runner that slices `coverage.json` by the policy's `include` list and judges each module separately - `.github/ci/coverage-modules.mjs`
- Runner tests on hand-built reports, including the missing, non-array and empty `include` cases - `tests/test_coverage_modules.py`
- Runtime package list for the suite - `tests/requirements.txt`
- Accepted coverage commands rendered into `.planning/config.json` and `.github/cadence/coverage-policy.json`
- Coverage outputs ignored - `.gitignore` (`coverage.json`, `.coverage`)
- New module tests: `tests/test_drops.py`, `tests/test_agents.py` (additions), `tests/test_macsys.py`
- Order-independent Core Audio test - `tests/test_audio_devices.py`
- CI workflow - `.github/workflows/tests.yml`, job `tests` on `macos-15`, pushes to `macos` and `personal`
- Failed-start diagnostics: fake servers log to a file, failed starts carry the log tails, and `VOID_TEST_LOGS` copies them out - `tests/test_launchers.py`, `tests/test_quit.py`. On the runner, the `failed-start-logs` artifact is uploaded on failure - `.github/workflows/tests.yml`
- Page tests report the conditions they ran under (`RM.matches`, `lowFx`, frames seen, and the browser's own rAF rate) - `tests/test_page_notch.py`, `tests/test_page_idle.py`
- Qt page tests pinned to full motion whatever the host's Reduce Motion setting - `tests/test_page_notch.py` `Page.setUpClass`
- Idle frame-rate checks judged against the browser's own rate (ratio in (0.75, 1.3), at least 6 reference frames) instead of an absolute `> 30` floor - `tests/test_page_idle.py`
- One bind with no name lookup for every HTTP server in `tests/` - `tests/loopback_http.py`. The child-process fakes carry its text (`FAKE_SERVER` in `tests/test_launchers.py`, `tests/test_quit.py`). The in-process servers import it (`tests/test_launchers.py` `WindowsLauncherUp`, `tests/test_wake_loop.py`, `tests/test_agents.py` `ApproveHook`)
- UAT item 4's `cause:` records the diagnosed cause (run 42346423614) - `.planning/phases/1/UAT.md`

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
| 3 | 1 | e433e99 | Show a fake server's own log when its start fails |
| 3 | 2 | d158c18 | Upload the failed-start logs from the tests job |
| 3 | 3 | 72e9dad | Report the conditions the page tests ran under |
| 3 | 4 | none | Diagnostic CI run 42340055084 at 72e9dad: 20 failed, 572 passed. Evidence read per cluster |
| 3 | 5 | none | Not run: cluster (a) cause not shown by the evidence |
| 3 | 6 | 80fa8e8 | Run the Qt page tests with full motion on any host |
| 3 | 7 | 75b8a6c | Judge the page's frame loop against the browser's own rate |
| 3 | 8 | none | Local gate green. CI run 42341370023 at 75b8a6c: 14 failed, 578 passed. Job still red |
| 4 | 1 | f7cef25 | Record the diagnosed cause of the fake-server failures in UAT item 4 |
| 4 | 2 | 6271a78 | Bind the child-process fake servers without a name lookup |
| 4 | 3 | 89f4bfe | Bind the in-process test servers without a name lookup |
| 4 | 4 | none | Local gate on Slate: `592 passed, 11 skipped in 268.97s`, 14 `meets 85`, `gate_found:true` |
| 4 | 5 | none | Pushed 75b8a6c..89f4bfe (owner authorized). CI run 42362803211 at 89f4bfe: `tests` success, `592 passed, 11 skipped in 356.94s`, `Per-module floor` passed |

Plan amendments: 0e1d85d (move the workflow commit to the end of Plan 2), 18c56ef (carry the missing-include runner fix into Plan 2). Between Plans 2 and 3, 4488777 moved both workflows to `macos-15` after GitHub retired `macos-14` (D-01 amended).

## Deviations

- [deviation] `CoreAudio.test_audio_devices` already failed when the whole suite ran in one process, because an earlier test's `macsys` import skipped the import-time `winsys.devices` assignment. Fixed in the test, not the app: it re-imports `macsys` and restores the earlier module (1ce278c). Recorded as Plan 1 Task 7 by amendment 0e1d85d.
- [deviation] The workflow commit was held until Plan 2 was green, so no commit ever carried a gate that would fail on the baseline (0e1d85d; workflow landed as 13a1d40).
- [deviation] risk_surface on Plan 1 (matched `destructive`, `untrusted_input`) found the gate passed with an empty `include` list; fixed in 2f4b0f3. The capped round-2 re-fire found the same pass with `include` missing or `{}`; carried into Plan 2 by amendment 18c56ef and fixed in 3ad5209. Both findings were medium, ruled survived with their fix commits (`ADJUDICATION-risk_surface-plan-1.json`, `-r2.json`).
- [deviation] Plan 3 Task 4 expected the failed-start logs to show the cause of cluster (a). All 14 came back 0 bytes, the fake servers' own logs and the launchers' `server.log` alike, so Task 5 was not run, as the plan directs.
- [deviation] Plan 3 was not re-dispatched on this run, although its report still reads `PLAN PARTIAL` (7 of 8). Its one unrun task, Task 5 (fix cluster (a)), is the work Plan 4 was written to do, and Plan 3's Task 8 sends that fix to a further gap plan rather than back into Plan 3. Plan 4 did it (6271a78, 89f4bfe).

## Open items

- UAT item 4's record still reads `status: fail` with the 4488777 commit and evidence. Plan 4 left those fields for the run that could change them. Run 42362803211 is that run, and `/cad-verify 1` re-judges the item.
- `app/server.py` `main` binds `ThreadingHTTPServer(("127.0.0.1", ...))` through the same `getfqdn` lookup. On a Mac where the reverse lookup of 127.0.0.1 is slow, the real server would write `runtime.json` about 35 s late, past the launchers' 6 s wait. Reported, not fixed: `app/` is outside this phase's lease.
- Plan 3's report stays `PLAN PARTIAL`, so `replay-check` keeps listing it as outstanding (see Deviations).
- The debug branch `ci-debug/fake-servers` and its `ci-debug.yml` are left as the owner left them. Deleting it is the owner's call.
- The `Logs` helper is duplicated in `tests/test_launchers.py` and `tests/test_quit.py`, because a shared tests module was outside the plan's lease.
- The reference rAF loop in `tests/test_page_idle.py` `INIT` adds one callback per frame to the page it measures.
- `required_jobs` names `build`, which does not run on `personal` pushes (owner's call, from Plan 1's Notes).
- Criterion 4 wording: with `tests/test_langmark.py` removed, only the second accepted command exits non-zero (`app/langmark.py: FAIL lines: 24.27% is below 85`); pytest itself carries no threshold (D-02) and exits 0. The job as a whole fails.
- `hearing` branches sit at 87.50, locally and on the runner, the thinnest margin over the floor.
- The project has never set `review.triggers.risk_surface.surfaces`. This phase's risk checks, Plans 3 and 4 included, passed all eight categories on the command line, and the choice is not saved to config.
- Git's keychain credential for github.com lacks the `workflow` scope and is refused on any push that touches `.github/workflows/`. Plan 3's two pushes went through the `gh` credential instead.

## Goal check

The phase goal is met, on the runner as well as locally. On CI run 42362803211 at 89f4bfe (`macos-15`), the `tests` job concluded `success`: `Suite with coverage` passed with `592 passed, 11 skipped in 356.94s`, `Per-module floor` ran and passed, and the 11 skips are all `slow tier: set VOID_SCENES=1` (plan-4 report, Task 5; `gh run list --branch personal` shows `success` at 89f4bfe). The downloaded `coverage.json`, put through `coverage-modules.mjs --report`, exits 0 with 14 `meets 85` lines. The lowest is still `app/hearing.py` branches at 87.50%. The previous run, 42341370023 at 75b8a6c, ended `14 failed, 578 passed`. The 14 cluster (a) tests passed: the run has no failures. Its log is summary-only, so they show only in that pass count. Plan 4's three commits (`git log --oneline 486b45e..HEAD`: f7cef25, 6271a78, 89f4bfe) touch only `tests/` and UAT.md, 38 insertions and 13 deletions. The fix was proven before the push: with `socket.getfqdn` made to raise, both fakes at 486b45e died with `RuntimeError: getfqdn called` and started with the change, and the in-process trio went from `17 failed, 19 passed` to `36 passed`. Locally the gate stays green (`592 passed, 11 skipped in 268.97s`, `gate_found:true`). The coordinator did not re-run the suite. One gap is outside the goal: the same lookup in `app/server.py` (Open items).

CI-verified: the `tests` job passed on run 42362803211 at 89f4bfe.
