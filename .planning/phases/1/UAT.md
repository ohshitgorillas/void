---
status: testing
phase: 1
fields_version: 1
started: 2026-11-06
updated: 2026-11-07
---

## Items

### 1. tests workflow shape
expected: `.github/workflows/tests.yml` has a job named `tests` with `runs-on: macos-15`, triggered on push to `macos` and `personal`, with no `paths:` filter
criterion: AC1
status: pass
first_pass: pass
source: model
evidence: cat .github/workflows/tests.yml -> `on: push: branches: [macos, personal]` (:6-8), job `tests:` (:10) with `runs-on: macos-15` (:11); `grep -n paths .github/workflows/tests.yml` -> no match (exit 1). Re-pinned from macos-14 after GitHub cancelled run 42335427416 with `The configuration 'macos-14-arm64-us-default' is not supported`

### 2. Policy check finds the gate
expected: `planning.mjs test-policy check --root .` prints `"gate_found":true`
criterion: AC2
status: pass
first_pass: pass
source: model
evidence: node planning.mjs test-policy check --root . -> {"ok":true,"accepted":true,"enforcement":"available","gate_found":true,"problems":[],"publish_authorized":false}

### 3. Accepted coverage commands pass locally
expected: The two accepted commands from `.github/cadence/coverage-policy.json` exit 0, and the second prints a `lines: … meets 85` and a `branches: … meets 85` line for each of the 7 include files
criterion: AC3
status: pass
first_pass: pass
source: model
evidence: PYTEST_ADDOPTS=-rs uvx --with pytest-cov --with-requirements tests/requirements.txt pytest --cov=app --cov-branch --cov-report=json -> `594 passed, 9 skipped in 284.32s`, exit 0 (all 9 skips `slow tier: set VOID_SCENES=1`); node .github/ci/coverage-modules.mjs --report coverage.json -> exit 0, lines/branches meets 85 for all 7: gate 99.06/97.62, hearing 98.12/87.50, agents 100/97.22, langmark 98.06/94.44, macsys 100/100, notifier 100/100, drops 100/100

### 4. tests job passes in CI and uploads coverage.json
expected: The `tests` job on a pushed `personal` commit passes and uploads a `coverage.json` artifact showing all 7 modules meeting 85 (ci: tests)
criterion: AC3
status: fail
job: tests
commit: 4488777abbe18f14f1908fb00aa9a0ab924762e9
first_pass: fail
source: model
evidence: Needs the tests job on a GitHub macos-15 runner; it cannot run on Slate
severity: blocker
cause: tests concluded failure at 4488777 (run 42335490351, macos-15): `21 failed, 571 passed, 11 skipped in 583.43s`; the gate step never ran. Three clusters, root causes unverified: (a) 13 tests in tests/test_launchers.py and tests/test_quit.py whose fake server never writes runtime.json / child.pid / server.pid within 5-8 s (`the foreign fake server didn't start`, `server didn't start`, test_quit.py:207 `False is not true`); the fake server's stderr goes to DEVNULL and server.log is not uploaded, so why it does not start is unknown; (b) 4 tests in tests/test_page_idle.py measure 17.7-29.8 frames a second against a `> 30` floor in headless Chrome on the GPU-less runner; (c) tests/test_page_notch.py NotchShift sees 0 frames of the shift (`0 not greater than 3`) and SplitEyes reads eyes 0.781 during a split, with `GPUInfo not initialized on GpuInfoUpdate` on stderr, and CleanExit fails because those two fail. These are the CONTEXT flagged assumptions about Qt, Chrome and Cocoa on the runner, now falsified.
fix: routed to /cad-plan

### 5. Gate fails when a module's tests are removed
expected: With `tests/test_langmark.py` removed, the two commands exit non-zero and the second prints an `app/langmark.py: FAIL` line
criterion: AC4
status: pass
first_pass: pass
source: model
evidence: tests/test_langmark.py moved aside, both accepted commands run, file restored: pytest -> `576 passed, 9 skipped`, exit 0 (D-02 puts no threshold in pytest); node .github/ci/coverage-modules.mjs --report coverage.json -> `app/langmark.py: FAIL lines: 24.27% is below 85`, `app/langmark.py: FAIL branches: 0.00% is below 85`, exit 1. The pair, run in sequence as the tests job runs it, exits non-zero, through the second command.

### 6. No import or Playwright skips in CI
expected: The `tests` job's pytest `-rs` output shows no test skipped for a missing import or missing Playwright; Windows-only and Linux-only skips allowed (ci: tests)
criterion: AC5
status: pass
job: tests
commit: 4488777abbe18f14f1908fb00aa9a0ab924762e9
first_pass: pass
source: model
evidence: tests job run 42335490351 at 4488777, pytest -rs short summary: all 11 skips read `slow tier: set VOID_SCENES=1` (tests/test_hearing.py:565, :574; tests/test_scenes.py:242-290); no skip for a missing import or missing Playwright.

### 7. No test fetches a speech model in CI
expected: behavior wrong - the suite loads the real Whisper base.en model, which the runner has to download from Hugging Face, against CONTEXT D-07 and the flagged assumption that no test downloads a model
origin: verifier
status: pass
first_pass: fail
source: model
evidence: After 4f95ffb: PYTEST_ADDOPTS=-rs uvx --with pytest-cov --with-requirements tests/requirements.txt pytest --cov=app --cov-branch --cov-report=json -> `592 passed, 11 skipped`, exit 0, with `SKIPPED tests/test_hearing.py:565/574: slow tier: set VOID_SCENES=1`; the gate exits 0, figures unchanged. VOID_SCENES=1 pytest tests/test_hearing.py -k HeardTest -> `2 passed`. grep for WhisperModel(/_whisper reset/model loads in tests/ outside test_scenes.py finds only HeardTest and the tests/make_scenes.py generator (not collected).
reported: behavior wrong - the suite loads the real Whisper base.en model, which the runner has to download from Hugging Face, against CONTEXT D-07 and the flagged assumption that no test downloads a model
severity: major
cause: HeardTest (tests/test_hearing.py:546-577) resets server._whisper to None and calls the real server.transcribe_pcm_heard/run_whisper, so app/server.py:1043 WhisperModel('base.en') fetches the model from Hugging Face on first use. Slate passes because ~/.cache/huggingface already holds it; the macos-14 runner has no cache and tests.yml sets no HF_HUB_OFFLINE, so every push downloads it, against D-07, and the job breaks whenever Hugging Face is unreachable. Unlike the real-Whisper scenes in tests/test_scenes.py:238, it is not gated to the VOID_SCENES=1 slow tier.
fix: 4f95ffb, retest

## Summary

total: 7
passed: 6
failed: 1
pending: 0
skipped: 0
blocked: 0
reworked: 2
