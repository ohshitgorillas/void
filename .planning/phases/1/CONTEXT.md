# Phase 1: Coverage gate - Context

Gathered: 2026-11-06
Feeds: /cad-plan 1

## Scope boundary

In: a `tests` workflow on `macos-14` that runs the existing suite unattended on pushes to `macos` and `personal`;
the two accepted coverage commands and Cadence's report checker; the runtime packages the suite needs in CI; new
tests for any of the 7 fork-owned modules below 85% lines or branches, until all 7 meet the floor.
Out: tests or coverage for upstream's modules (`server.py`, `window.py`, ...); `build` job changes in `macos.yml`;
merging anything to `macos` (Phase 2); pushing, which needs the owner's word in the turn it happens.
Deferred: None
Plan shape: multiple plans, same phase - /cad-plan splits it (e.g. the CI workflow and checker, then per-module tests).

## Durable decisions

- D-04 (CI environment): The app's runtime packages come from a new `tests/requirements.txt` (the `packaging/macos/build.sh` set: faster-whisper, pillow, PySide6, sounddevice, piper-tts, kokoro-onnx, and `livekit==1.1.21`), and the accepted pytest command gains `--with-requirements tests/requirements.txt`, changed in config `testing.coverage.commands` and re-rendered into the policy with `planning.mjs test-policy render`. In the same render, the second accepted command becomes `node .github/ci/coverage-modules.mjs --report coverage.json`. `--cov=app` is unchanged. A bare `uvx --with pytest-cov` builds an env with none of them, and the tests skip on import failure, so the suite would go green over silent skips. Evidence: `packaging/macos/build.sh:22-23`; `skipIf(LIVEKIT_ERR ...)`, `skipIf(hearing is None ...)` in `tests/test_hearing.py`, `tests/test_gate.py`; no pyproject or requirements file in the repo.
- D-08 (Floor and scope): The 85% lines and 85% branches floor holds for all 7 fork-owned modules (`gate`, `hearing`, `agents`, `langmark`, `macsys`, `notifier`, `drops`); a module below it gets new tests in this phase. The floor is not lowered and no module leaves `include`. This settles PROJECT.md's pending Key Decision. Evidence: `.planning/config.json` `testing.coverage`; no `tests/test_macsys.py` or `tests/test_drops.py`; `app/macsys.py` 497 lines, `app/agents.py` 637 lines are the likely gaps.

## Decisions

- D-01 (Workflow shape): A new `.github/workflows/tests.yml` holds a job named `tests` on `macos-14`, on push to `macos` and `personal`, with no `paths:` filter; it is not folded into `macos.yml`. Evidence: `.github/workflows/macos.yml` triggers only on `macos` and `v*` tags behind a paths filter, which would hide a test-only commit.
- D-02 (Workflow shape): Both accepted commands appear in the workflow verbatim, as separate steps with no `continue-on-error`. The floor is compared only by Cadence's checker, which `.github/ci/coverage-modules.mjs` (the second accepted command) runs once per `include` file on that file's slice of `coverage.json`; no pytest `--fail-under`, no `.coveragerc`, no totals-only checker step. `coverage.json` is uploaded as an artifact with `if: always()`. Design: `docs/superpowers/specs/coverage-gate-design.md`. Evidence: `planning.mjs test-policy check --root .` today reports both commands and the `tests` job missing from every workflow; `.github/workflows/windows.yml` upload pattern.
- D-03 (Checker): Cadence's `cadence-core/templates/coverage-report-check.mjs` is copied unmodified to `.github/cadence/coverage-report-check.mjs`; the workflow never calls it directly, `.github/ci/coverage-modules.mjs` runs it once per `include` file. Evidence: Cadence `references/test-policy.md:84`; `.github/cadence/` holds only `coverage-policy.json`.
- D-05 (CI environment): CI installs Playwright so the page tests (`tests/test_page_*.py`) run rather than skip; Chrome is preinstalled on `macos-14`. Evidence: `tests/test_page_idle.py` `node_path()` skips without a Playwright install.
- D-06 (CI environment): The Cocoa and Qt tests run on the runner and must not skip there; `macsys.py` stays in `include`. Evidence: `tests/test_window_mac.py` (44 `macsys` references) is the module's main coverage; `skipUnless(MAC ...)` gates.
- D-07 (CI environment): No speech models are fetched or cached in CI; the tests use `tests/fakes.py` and `tests/fixtures`. Evidence: `app/hearing.py` imports only numpy and livekit at top level.
- D-09 (Branches): The work commits on `personal`; the workflow already lists `macos` so it runs there once Phase 2 merges it, after which upstream-sync's daily merges run the tests too. Evidence: `.github/workflows/upstream-sync.yml` pushes merges to `macos`.

## Acceptance criteria

- [ ] AC1: `.github/workflows/tests.yml` has a job named `tests` with `runs-on: macos-14`, triggered on `push` to `macos` and `personal`, with no `paths:` filter
- [ ] AC2: `node "${CLAUDE_PLUGIN_ROOT}/cadence-core/bin/planning.mjs" test-policy check --root .` prints `"gate_found":true`
- [ ] AC3: Running the two accepted commands from `.github/cadence/coverage-policy.json` exits 0, and the second command prints, for each of the 7 `include` files, an `<file>: lines: … meets 85` and an `<file>: branches: … meets 85` line; the `tests` job on a pushed `personal` commit passes and uploads a `coverage.json` artifact showing the same (ci: tests)
- [ ] AC4: With one fork-owned module's test file removed (e.g. `tests/test_langmark.py`), the two commands exit non-zero and the second command prints a `<file>: FAIL` line naming that module. The module used is one whose figure falls below 85% without its test file; `langmark` is also imported through `app/server.py:43`, so its figure without `tests/test_langmark.py` is unmeasured until the first run.
- [ ] AC5: The `tests` job's pytest output (`-rs`) shows no test skipped for a missing import or missing Playwright; Windows-only and Linux-only skips are allowed (ci: tests)

## Flagged assumptions

- Qt and QtWebEngine run headless on GitHub's `macos-14` runner, with or without an offscreen platform setting - Unclear; if wrong: the Cocoa tests skip or crash and `macsys.py` falls below 85%.
- Playwright's `channel: "chrome"` finds the runner's preinstalled Chrome - Likely; if wrong: the page tests fail or need `BROWSERS` set to a Playwright-installed browser.
- `coverage.json` keys files as `app/<module>.py`, matching `include`, despite the tests' bare `import gate` after `sys.path` edits - Likely; if wrong: the checker reports a module missing, fixed with a coverage config, not by changing `include`.
- The current per-module gap below 85% is unmeasured; a local coverage run is heavy on Slate, so the plan discloses it before running - Unclear; if wrong: more test-writing than one plan per module expects.
- No test downloads a model (not every test was traced, e.g. `tests/test_echo.py`) - Likely; if wrong: the job hangs and needs a timeout or model cache.
