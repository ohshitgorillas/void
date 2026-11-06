PLAN CHECKPOINT: structural
Plan: .planning/phases/1/PLAN-1.md
Tasks: 6 of 7
| Task | Commit | Note |
|---|---|---|
| 1 Vendor checker | 710b687 | `cmp` against the template exits 0; no-arg run prints `usage:` and exits 1 |
| 2 Per-module runner | 74394fc | exports print `function function function`; `--report /nonexistent.json` prints `FAIL report: cannot read /nonexistent.json`, exit 1; the grep for 85 / comparisons finds nothing |
| 3 Runner tests | 55d87a8 | `uvx pytest tests/test_coverage_modules.py -rs`: 7 passed, none skipped; with `node` off PATH: 7 failed (FileNotFoundError), none skipped; with `slice` returning the whole report `test_high_total_hides_no_low_module` fails (as do the two below-floor tests); reverted, `git diff .github/ci/` empty |
| 4 Ignore outputs | 5a4f07d | staged via a blob built from HEAD's file plus the two lines; commit is `2 ++`; `git check-ignore coverage.json .coverage` prints both; the owner's todo.txt / trace / reads lines remain unstaged in the working tree |
| 5 Requirements | 03ef50e | `uv pip compile` resolves; includes `livekit==1.1.21`, `pyside6==6.11.3`, `faster-whisper==1.2.1`, `kokoro-onnx==0.6.1` |
| 6 Render commands | 45d4f02 | config and policy change only the two `commands` entries; `check` then named the two commands and the `tests` job as missing from workflows |
| 7 `tests` workflow | NOT COMMITTED | `.github/workflows/tests.yml` written and left untracked; `test-policy check` prints `"gate_found":true`, `grep -c 'continue-on-error\|fail-under\|paths:'` prints 0; local run does not meet the Verify (below) |

Task 7 local run (UV_PYTHON=3.12 PYTEST_ADDOPTS=-rs, one process, 5m12s): first command exit 1, `1 failed, 490 passed, 9 skipped`.
Failing test, quoted: `tests/test_audio_devices.py:372: AssertionError: None is not <function audio_devices at 0x10802c860>` in `CoreAudio.test_audio_devices` (`self.assertIs(winsys.devices, macsys.audio_devices)`).
Evidence on cause (not a plan assumption): the test passes alone (`pytest tests/test_audio_devices.py`: 26 passed) and fails when `tests/test_window_mac.py` shares the process (1 failed, 71 passed). `app/macsys.py:93` sets `winsys.devices = audio_devices` only at import; pytest imports `test_window_mac` (and `macsys`) at collection, and `tests/test_audio_devices.py:132` resets `winsys.devices = None` in the Base teardown, so by the time the test runs its `import macsys` is a no-op. Pre-existing order dependence in a test file outside this plan's lease, exposed by running the whole suite in one pytest process; no change in this plan caused it. Confidence: high on mechanism, not tried with a fix.
The 9 skips are all `tests/test_scenes.py` "slow tier: set VOID_SCENES=1"; none is an import or Playwright skip (page tests passed locally).

Measured baseline from the second command on the run's coverage.json (exit 1, 21 lines):
```
app/gate.py: lines: 99.06% meets 85
app/gate.py: branches: 97.62% meets 85
app/gate.py: statements: disabled (threshold 0)
app/hearing.py: lines: 98.12% meets 85
app/hearing.py: branches: 87.50% meets 85
app/hearing.py: statements: disabled (threshold 0)
app/agents.py: lines: 89.22% meets 85
app/agents.py: FAIL branches: 81.94% is below 85
app/agents.py: statements: disabled (threshold 0)
app/langmark.py: lines: 98.06% meets 85
app/langmark.py: branches: 94.44% meets 85
app/langmark.py: statements: disabled (threshold 0)
app/macsys.py: FAIL lines: 45.30% is below 85
app/macsys.py: FAIL branches: 30.56% is below 85
app/macsys.py: statements: disabled (threshold 0)
app/notifier.py: lines: 100.00% meets 85
app/notifier.py: branches: 100.00% meets 85
app/notifier.py: statements: disabled (threshold 0)
app/drops.py: lines: 89.47% meets 85
app/drops.py: FAIL branches: 81.82% is below 85
app/drops.py: statements: disabled (threshold 0)
```
Every include file is present in the report under its `app/<module>.py` key. Below the floor: agents (branches), macsys (lines, branches), drops (branches).

Deviations: [deviation] Task 7 Verify asserts the first accepted command exits 0 locally; it exits 1 on the pre-existing order-dependent `CoreAudio.test_audio_devices`. The second command also exits 1 (agents, macsys, drops below 85), which is the gap Plan 2 closes. Per CLAUDE.md 11.4 (never commit a failing gate) `tests.yml` is left uncommitted rather than committed over a red gate; the plan's own Notes flagged this tension for the orchestrator.
Open items:
- `tests/test_audio_devices.py::CoreAudio::test_audio_devices` order dependence needs a fix in a file outside the lease (a 6.1 question: how the test should guarantee a fresh `macsys` import, e.g. restoring the assignment or reloading); it also blocks the first command exiting 0 and so the CI `tests` job.
- Task 7 commit decision (11.4): commit `tests.yml` now, or hold it to the end of Plan 2 once both commands are green.
- Declined fuller shapes: none beyond leanness defaults; Playwright pinned to 1.65.0 (`npm view playwright version` on 2026-11-06) in the workflow.
- Plan Notes still open for the owner: `required_jobs` names `build`, which does not run on `personal` pushes.
- Footprint of the local run: uv cache grew by the app packages; my pytest process (PID 73118) has exited; coverage.json and .coverage are left in the repo root (git-ignored).
