---
phase: 1
plan: 1
requirements:
  - TEST-01
files:
  - .github/cadence/coverage-report-check.mjs
  - .github/ci/coverage-modules.mjs
  - tests/test_coverage_modules.py
  - .gitignore
  - tests/requirements.txt
  - .planning/config.json
  - .github/cadence/coverage-policy.json
  - .github/workflows/tests.yml
---

# Phase 1: Coverage gate - Plan 1: Per-module CI gate

## Goal

The existing suite runs unattended on a macOS runner, and the fork-owned modules meet the accepted 85% lines and branches floor. This plan builds the gate: the `tests` job, its two accepted commands, and the per-module check that judges each of the 7 fork-owned files on its own figures.

## Must be true when done

- `node "${CLAUDE_PLUGIN_ROOT}/cadence-core/bin/planning.mjs" test-policy check --root .` prints `"gate_found":true`.
- `.github/workflows/tests.yml` has a job named `tests` on `macos-14`, triggered on push to `macos` and `personal` with no `paths:` filter, running the two accepted commands verbatim as separate steps and uploading `coverage.json` with `if: always()`.
- `.planning/config.json` `testing.coverage.commands` and `.github/cadence/coverage-policy.json` `coverage.commands` both hold exactly `uvx --with pytest-cov --with-requirements tests/requirements.txt pytest --cov=app --cov-branch --cov-report=json` and `node .github/ci/coverage-modules.mjs --report coverage.json`; thresholds, `include`, `exclude`, `strong_areas` and `required_jobs` are unchanged.
- `node .github/ci/coverage-modules.mjs --report coverage.json` prints, for each of the 7 `include` files, one `<file>: lines: …` and one `<file>: branches: …` line, and exits 1 naming any file below 85 even when the report's total is above 85 (proved by `tests/test_coverage_modules.py`).
- `.github/cadence/coverage-report-check.mjs` is byte-identical to Cadence's template.
- `coverage.json` and `.coverage` are git-ignored, and the owner's own uncommitted `.gitignore` edits are still uncommitted.

## Context

- Binding: CONTEXT D-01, D-02, D-03, D-04, D-05, D-07 and the approved design `docs/superpowers/specs/coverage-gate-design.md` (its Modules, Homes and Order sections). The design names `slice`, `modulePolicy` and `run` as the runner's exports and the seven test names; those are fixed by the design, not invented here.
- Follow: `.github/workflows/macos.yml` (`actions/checkout@v7`, `astral-sh/setup-uv@v6` with cache, `timeout-minutes`) and `.github/workflows/windows.yml` (`actions/upload-artifact@v7`); the checker template's own CLI (`--format`, `--report`, `--policy`).
- Out of scope: the `build` job and anything in `macos.yml`; tests or coverage for upstream's modules; any coverage config file (`.coveragerc`, `setup.cfg`, `pytest.ini`, `pyproject.toml`); pushing.
- Plan 2 builds on this plan's output (the requirements file, the rendered commands and the per-module runner) and runs after it.

## Tasks

### Task 1: Vendor Cadence's coverage report checker

- **Files:** .github/cadence/coverage-report-check.mjs
- **Action:** Copy `${CLAUDE_PLUGIN_ROOT}/cadence-core/templates/coverage-report-check.mjs` to `.github/cadence/coverage-report-check.mjs` byte for byte (design, Modules; CONTEXT D-03). Do not edit it, reformat it or add a header: the design makes it the single home of the floor comparison and report validation, and any local edit forks Cadence's checker.
- **Verify:** `cmp "${CLAUDE_PLUGIN_ROOT}/cadence-core/templates/coverage-report-check.mjs" .github/cadence/coverage-report-check.mjs` exits 0, and `node .github/cadence/coverage-report-check.mjs` with no arguments exits non-zero printing its `usage:` line. Testing scope: a vendored file; identity with the template is the whole evidence, and no test is written for it.

### Task 2: Build the per-module coverage runner

- **Files:** .github/ci/coverage-modules.mjs
- **Action:** Write `.github/ci/coverage-modules.mjs` exactly as the design's Modules section specifies: exports `slice(report, file)`, `modulePolicy(policy, file)` and `run(argv)`; `process.exit(run(process.argv))` only when executed directly; node builtins only (`node:fs`, `node:os`, `node:path`, `node:child_process`). For each `include` entry, in policy order, it runs the Task 1 checker (resolved as `../cadence/coverage-report-check.mjs` from the script's own location, launched with `process.execPath`, cwd the repo root) with `--format python --report <slice> --policy <module policy>`, prints every checker line prefixed with `<file>: `, never stops at the first failure, and returns 1 if any file failed. Glob-shaped include entries (any of `*?[{`) print the design's `FAIL <entry>: include entries must be file paths for per-module coverage` line and count as failed. A report that does not parse or has no `files` object goes unsliced, with the real policy, to one checker run whose output and exit code are returned as they are. Temp slices and policies live in one `fs.mkdtempSync` directory removed in a `finally`. Hold no threshold, percentage comparison or file list in this script: the design's Homes table gives those to the policy and the checker alone, and a second copy is how the floor drifts.
- **Verify:** `node -e "import('./.github/ci/coverage-modules.mjs').then(m => console.log(typeof m.slice, typeof m.modulePolicy, typeof m.run))"` prints `function function function` and exits without running the gate; `node .github/ci/coverage-modules.mjs --report /nonexistent.json` exits non-zero and prints the checker's own failure text; `grep -nE '85|lines *[<>]|branches *[<>]' .github/ci/coverage-modules.mjs` finds no threshold or comparison. Testing scope: the behavioral proof is Task 3's suite; this task's check stops at the module shape and the pass-through of an unreadable report.

### Task 3: Test the per-module runner on hand-built reports

- **Files:** tests/test_coverage_modules.py
- **Action:** Write `tests/test_coverage_modules.py` as the design specifies: `unittest`, the helpers `run_modules` and `summary`, and the class `CoverageModules` with its seven tests (every module at floor passes; lines below floor fails naming it; branches below floor fails naming it; a high total hides no low module; a module absent from the report fails naming it; a glob include entry fails; an unreadable report fails). Reports and policies are written under a temporary directory; include paths are tracked files (`app/gate.py`, `app/langmark.py`) because the checker confirms them with `git ls-files`. Run `node` from `PATH`, and let a missing `node` fail the test rather than skip it: a skip would let CI go green without the gate ever being tested. Assert exit codes and the `<file>: …` lines by module name; expected pass/fail comes from the hand-built percentages against 85, not from captured output.
- **Verify:** `uvx pytest tests/test_coverage_modules.py -rs` runs 7 tests, all passing, none skipped. Running the same command with `node` removed from `PATH` fails the tests (not skips). Temporarily making `run` judge the whole report instead of each slice makes `test_high_total_hides_no_low_module` fail; revert, and `git diff .github/ci/` is empty. Testing scope: outcomes are pass at floor, per-module failure on either metric, failure hidden by no total, absent file, glob entry and unreadable report; nothing covers them today; these seven are the design's set and testing stops there.

### Task 4: Ignore the coverage outputs

- **Files:** .gitignore
- **Action:** Append exactly two lines, `coverage.json` and `.coverage`, to `.gitignore` (design, Homes). The file carries the owner's uncommitted edits (todo.txt and the Cadence trace and read-record entries), which must stay uncommitted: stage only the two new lines against HEAD's version of the file (for example with `git apply --cached` of a patch that adds just those lines), never `git add .gitignore`, and leave the working tree holding the owner's edits plus the two lines.
- **Verify:** `git check-ignore coverage.json .coverage` prints both names; the task's commit changes `.gitignore` by exactly two added lines (`git show --stat HEAD -- .gitignore` shows `2 +`, and `git show HEAD -- .gitignore` adds only `coverage.json` and `.coverage`); `git diff .gitignore` still shows the owner's todo.txt and `.planning/trace.jsonl` lines as unstaged. Testing scope: ignore rules only; no test.

### Task 5: Declare the app's runtime packages for the suite

- **Files:** tests/requirements.txt
- **Action:** Create `tests/requirements.txt` listing the packages `packaging/macos/build.sh` installs into the app's Python: `faster-whisper`, `pillow`, `PySide6`, `sounddevice`, `piper-tts`, `kokoro-onnx` unpinned as build.sh has them, and `livekit==1.1.21` pinned as build.sh pins it (CONTEXT D-04). Add no other package, no version pins beyond livekit's, and no speech model (D-07): this list mirrors what the shipped app imports, so the suite tests the same imports the DMG carries. It lands before the commands are rendered so that no commit names a requirements file that does not exist.
- **Verify:** `uv pip compile tests/requirements.txt --python-version 3.12 --python-platform aarch64-apple-darwin` resolves without error (metadata only, no install) and its output includes `livekit==1.1.21`, `pyside6`, `faster-whisper` and `kokoro-onnx`. Testing scope: the resolution is the evidence; the import-skip proof is Task 7's suite run.

### Task 6: Render the accepted coverage commands

- **Files:** .planning/config.json, .github/cadence/coverage-policy.json
- **Action:** Set `testing.coverage.commands` in `.planning/config.json` to exactly the two commands in the design's Homes section, in order: `uvx --with pytest-cov --with-requirements tests/requirements.txt pytest --cov=app --cov-branch --cov-report=json`, then `node .github/ci/coverage-modules.mjs --report coverage.json`. Then run `node "${CLAUDE_PLUGIN_ROOT}/cadence-core/bin/planning.mjs" test-policy render --root .` to rewrite `.github/cadence/coverage-policy.json`; never hand-edit the policy file. Change nothing else in either file: `--cov=app`, the thresholds, `include`, `exclude`, `strong_areas` and `required_jobs` stay as they are (CONTEXT D-04 and D-08 are the owner's explicit policy adjustment; nothing beyond them is). Commit the rendered policy in this task, since CI and `check` read it from git.
- **Verify:** `node "${CLAUDE_PLUGIN_ROOT}/cadence-core/bin/config.mjs" get testing.coverage.commands` returns the two strings exactly; the task's commit (`git show HEAD -- .planning/config.json .github/cadence/coverage-policy.json`) changes only the `commands` entries; `test-policy check --root .` now names the two new command texts as missing from the workflows (expected until Task 7) and no longer names the old ones. Testing scope: configuration text only; no test.

### Task 7: Add the `tests` workflow

- **Files:** .github/workflows/tests.yml
- **Action:** Create `.github/workflows/tests.yml` (a new file; `macos.yml` is not touched, CONTEXT D-01) with: `on: push` to branches `macos` and `personal`, no `paths:` filter and no other trigger; one job named `tests`, `runs-on: macos-14`, `timeout-minutes: 45` (my choice: an unattended macOS job otherwise runs up to 6 hours if a test hangs, which CONTEXT's last flagged assumption raises); job-level `env` `UV_PYTHON: "3.12"` (my choice: `install.sh` pins 3.12 because the speech libraries do not all support newer Pythons, and the env leaves the accepted command text verbatim). Steps: `actions/checkout@v7`; `astral-sh/setup-uv@v6` with `enable-cache: true` and `cache-dependency-glob: tests/requirements.txt`; a global Playwright install with `npm install -g playwright@<exact version>`, the version read from `npm view playwright version` when the file is written, so `node_path()` in `tests/test_page_idle.py` finds it under `npm root -g` and the page tests run against the runner's preinstalled Chrome through `channel: "chrome"` (D-05; no browser download); the first accepted command verbatim as a single-line `run:` with step `env` `PYTEST_ADDOPTS: -rs` (my choice: it prints every skip reason for AC5 without altering the accepted text); the second accepted command verbatim as its own single-line `run:`; then `actions/upload-artifact@v7` with `if: always()`, `name: coverage.json`, `path: coverage.json`, `if-no-files-found: warn` (the run has already failed when the report is missing). No `continue-on-error`, no `--cov-fail-under`, no threshold, no file list and no direct call to `coverage-report-check.mjs` anywhere in the file (D-02; design Homes). Fetch no speech model (D-07). Before running the suite locally, name its footprint to the user (rule 3.1): the uv cache gains PySide6, faster-whisper, onnxruntime, kokoro-onnx and the rest (over 1 GB of disk), the run holds one core for minutes, and Qt windows and Chrome open on Slate's screen; run it with `UV_PYTHON=3.12` to match CI.
- **Verify:** `node "${CLAUDE_PLUGIN_ROOT}/cadence-core/bin/planning.mjs" test-policy check --root .` prints `"gate_found":true` (AC2); `grep -c 'continue-on-error\|fail-under\|paths:' .github/workflows/tests.yml` prints 0. Locally, from the repo root with `UV_PYTHON=3.12 PYTEST_ADDOPTS=-rs`, the first accepted command exits 0 (a failing test is quoted and raised as a 6.1 question, never skipped or excluded), and the second prints exactly 21 per-module lines, three for each of the 7 `include` files: a `lines` and a `branches` line, each `meets 85` or `FAIL`, and a `statements: disabled (threshold 0)` line (the policy's statements threshold is 0, `coverage-report-check.mjs:103`); report those 21 lines verbatim as the measured baseline Plan 2 starts from, and a file reported absent from the report is a stop-and-report (CONTEXT's flagged assumption on `app/<module>.py` keys), not a reason to add a coverage config, which this plan does not lease. The CI half (the `tests` job passing on a pushed `personal` commit and uploading `coverage.json`, AC3 and AC5) is (ci: tests), checked after Plan 2 by `ci-status` once the owner authorizes the push. Testing scope: the gate's own logic is tested by Task 3; this task's evidence is the policy check plus one real local run, and no further test is added.

## Notes

- Task order follows the design's Order (checker and runner, runner tests, rendered commands, workflow), with two departures said out loud: the design's step 1 is split into Tasks 1, 2 and 4 (vendored checker, repo-owned runner and ignore rules are three concerns), and `tests/requirements.txt` (Task 5) lands before the render (Task 6) rather than after the workflow, so no commit names a requirements file that does not exist yet. The dispatch asked for the CI job in the first task; the approved design's order puts it last in this plan because its commands need the runner and requirements to exist first, and this plan is the phase's first.
- Rule 11.4 tension for the orchestrator to settle: at Task 7, the second command will likely exit 1 for any module still below 85 in the baseline, so `tests.yml` is committed while the gate it defines would be red. Nothing is pushed until the owner says so, and Plan 2 closes the gap before any push; if 11.4 is read to forbid that commit, Task 7 moves to the end of Plan 2 instead.
- `required_jobs` names `build`, which exists only in `macos.yml`, triggered on `macos` and tags behind a `paths:` filter. A `personal` commit will therefore have no `build` run for `ci-status` to read. CONTEXT puts `build` changes out of scope, so this plan does not touch it; this needs the owner's call.
- Flagged assumptions carried from CONTEXT, unresolved until the first CI run: Qt and Cocoa run on the `macos-14` runner without skipping (D-06; `tests/test_window_mac.py` also skips on "no screen"), and Playwright's `channel: "chrome"` finds the runner's Chrome.
- Recalled D-04 and D-08 (phases/1/CONTEXT.md, phase 1) are applied in Tasks 5 and 6 and in Plan 2 respectively.
