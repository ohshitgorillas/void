---
phase: 1
plan: 2
requirements:
  - TEST-01
files:
  - tests/test_gate.py
  - tests/test_hearing.py
  - tests/fakes.py
  - tests/test_drops.py
  - tests/test_agents.py
  - tests/test_macsys.py
  - tests/test_window_mac.py
  - tests/test_langmark.py
  - tests/test_notifier.py
---

# Phase 1: Coverage gate - Plan 2: Fork modules at the floor

## Goal

The existing suite runs unattended on a macOS runner, and the fork-owned modules meet the accepted 85% lines and branches floor. This plan brings each of the 7 fork-owned modules to the floor with tests that assert real behavior, so the gate Plan 1 built passes.

## Must be true when done

- From the repo root with `UV_PYTHON=3.12`, the two accepted commands from `.github/cadence/coverage-policy.json` exit 0, and the second prints `<file>: lines: … meets 85` and `<file>: branches: … meets 85` for all 7 `include` files (AC3, local half).
- With `tests/test_langmark.py` moved aside, the same two commands exit non-zero and the second prints an `app/langmark.py: FAIL` line; with it restored, they exit 0 again (AC4). If langmark stays at or above 85 without its file (it is also imported through `app/server.py`), `tests/test_agents.py` and `app/agents.py` are used instead, and the module used is named in the report.
- No module reaches the floor by narrowing what is measured: nothing under `app/` changed, no `pragma: no cover`, no coverage config file, and `.planning/config.json` and `.github/cadence/coverage-policy.json` are unchanged by this plan.
- After the owner authorizes a push of `personal`, the `tests` job passes, uploads a `coverage.json` showing the same 14 meets lines, and its `-rs` output shows no skip for a missing import or missing Playwright (AC3 and AC5, ci: tests).

## Context

- Builds on Plan 1's output and runs after it: `tests/requirements.txt`, the rendered accepted commands and `.github/ci/coverage-modules.mjs` must exist, and Plan 1 Task 7's 21 baseline lines (14 `lines`/`branches` figures plus 7 `statements: disabled (threshold 0)`) are where each task starts.
- Binding: CONTEXT D-08 (85/85 for all 7 modules; the floor is not lowered and no module leaves `include`), D-06 (Cocoa and Qt tests do not skip on the runner; `macsys.py` stays in `include`), D-07 (no speech model in any test), and the design's rule that no module test adds a coverage setting, threshold or file list.
- `testing.strong_areas` is `app/gate.py`, `app/hearing.py`, `app/agents.py`; Key Decision "Hearing test doubles live only in `tests/fakes.py`". Phase 3 owns the real-log regression set and new `void drops` output; this plan tests existing behavior only.
- Every task follows one loop: measure the module's gap (Plan 1's baseline lines, then `missing_lines` and `missing_branches` for `files["app/<module>.py"]` in `coverage.json`), add tests only for those gaps, stop at 85/85. A module already at or above 85/85 in the baseline gets no new tests; its task reports the baseline lines and commits nothing.
- A subset run, `UV_PYTHON=3.12 uvx --with pytest-cov --with-requirements tests/requirements.txt pytest <the module's test files> --cov=app --cov-branch --cov-report=json` followed by the second accepted command, gives a lower bound on the module's full-suite figure, so a subset `meets 85` settles a task; the full run is needed only for the plan's closing truths. Each task lists its module's test files.

## Tasks

### Task 1: Bring `app/gate.py` to the floor

- **Files:** tests/test_gate.py
- **Action:** Close the measured gap in `app/gate.py` (`judge`, `is_echo`, `is_noise`, `is_filler`, `stop_said`, `spoken_enough`, `sure`, `word_like`) with tests in `tests/test_gate.py` that assert the `Verdict` and drop reason each uncovered branch produces for a constructed `Burst`. Take expected verdicts from the rule the code documents (gate.py's comments and the hearing-verdict design under `docs/superpowers/specs/`) and the owner's 26 Oct ruling that a dropped real request is the worst hearing failure, never from running the code and copying its output. If an uncovered branch drops what those sources say must be kept, write no test that encodes it: stop the task and raise it as a 6.1 question quoting the burst and the reason. No change to `app/`.
- **Verify:** Subset run over `tests/test_gate.py tests/test_echo.py tests/test_log_cases.py tests/test_listen_verdict.py tests/test_scenes.py tests/test_wake_loop.py` prints `app/gate.py: lines: … meets 85` and `app/gate.py: branches: … meets 85`, with every test passing. Testing scope (strong area): outcomes are each uncovered verdict path with its reason; the existing gate, echo, log-case and scene tests already cover the main keep and drop paths; the added checks are one assertion of verdict and reason per uncovered branch, and testing stops at 85/85 with no new hearing scenario.

### Task 2: Bring `app/hearing.py` to the floor

- **Files:** tests/test_hearing.py, tests/fakes.py
- **Action:** Close the measured gap in `app/hearing.py` (`PlayRef.played`, `cut`, `span`, `_resample`; `Linear`; `Canceller` with `forget`, `_pick`, `process`; `Voicing.frame`) with tests in `tests/test_hearing.py` that assert observable results: the reference span returned after a cut or a resample, the canceller's output length and which signal `_pick` chooses for constructed mic and reference audio, `Voicing.frame`'s returned levels. Reset `PlayRef` and `Canceller` class state between tests (`Canceller.forget` exists for it) so tests do not depend on order. Any new test double goes in `tests/fakes.py`, the one home the project decided for hearing doubles. Use synthetic numpy signals; no speech model and no audio device. If a path behaves against its documented intent, stop and raise it as a 6.1 question rather than asserting it. No change to `app/`.
- **Verify:** Subset run over `tests/test_hearing.py tests/test_echo_diagnostics.py tests/test_scenes.py tests/test_speaker_switch.py tests/test_wake_loop.py` prints both `app/hearing.py` lines as `meets 85`, every test passing and none skipped for livekit or hearing import. Testing scope (strong area): outcomes are the uncovered reference, cancel and voicing paths; the livekit and scene tests cover the main capture path; the added checks assert one result per uncovered path on synthetic signals, and testing stops at 85/85.

### Task 3: Bring `app/drops.py` to the floor

- **Files:** tests/test_drops.py
- **Action:** Create `tests/test_drops.py` covering the measured gap in `app/drops.py` (`parse`, `_kind`, `now`, `replay`, `report`, `main`): feed inline server-log lines, including the older drop wordings the module maps, and assert the `Drop` records and the printed report; drive `main` with a temporary log file and assert its output and exit. Expected results come from the log lines' meaning and the module's documented mapping, not from captured output. Test only what `drops.py` does today; new `void drops` output belongs to Phase 3. Point Void's data folder at the suite's own by importing `suite_data` first, as the other test files do. No change to `app/`.
- **Verify:** Subset run over `tests/test_drops.py tests/test_echo.py tests/test_log_cases.py tests/test_wake_loop.py` prints both `app/drops.py` lines as `meets 85`, every test passing. Testing scope: outcomes are parsing each log form, replaying through `gate.judge`, the report text and the CLI entry; `test_log_cases.py` covers replay of the fixture logs; the added checks cover the uncovered forms and `main`, and testing stops at 85/85.

### Task 4: Bring `app/agents.py` to the floor

- **Files:** tests/test_agents.py
- **Action:** Close the measured gap in `app/agents.py` (`Stream.feed` and its `_system`, `_result`, `_answer` handling; `Brain` `ask`, `stop`, `shutdown`, `idle_check`, `_restart_reason`, `_spawn`, `_route`, `_read`, `_died_locked`, `_watch`; `kill_tree`; the helpers `result_text`, `tool_output`, `tool_images`, `notes_prefix`) with tests in `tests/test_agents.py`. Drive `Brain` through its existing `popen` and `killer` injection points with stream-JSON events and assert what it publishes and when it restarts or stops; no real `claude` process. Any test exercising `kill_tree` for real spawns its own child, kills only that child's group, and reaps it, so no process outlives the test. Expected events come from the documented stream protocol and the context-bleed design's rules, not captured output; a path that contradicts them is a 6.1 question, not an assertion. No change to `app/`.
- **Verify:** Subset run over `tests/test_agents.py` prints both `app/agents.py` lines as `meets 85`, every test passing; `ps` after the run shows no leftover child of the test process. Testing scope (strong area): outcomes are the uncovered stream event kinds, restart and stop paths, and tree kill; existing agents tests cover the main ask and answer path; the added checks are one assertion per uncovered path, and testing stops at 85/85.

### Task 5: Bring `app/macsys.py` to the floor

- **Files:** tests/test_macsys.py, tests/test_window_mac.py
- **Action:** Create `tests/test_macsys.py` covering the measured gap in `app/macsys.py`. For everything that acts on the machine (`osa`, `volume_get`, `volume_set`, `media`, `now_playing`, `brightness`, `lock`, `open_app`, `notify`, `set_clipboard`, `clipboard`, `screenshot`, `active_window`, `mic_level`, `set_mic_level`), replace the process boundary (`_run`, or `subprocess` where `_run` is not used) and assert the command or AppleScript built and how its output is parsed. The tests must never lock the screen, change volume, brightness, media or the mic level, open an app, post a notification, set the clipboard or take a screenshot on the machine running them: on Slate that is damage to the owner's session. Pure functions (`data_dir`, `config_dir`, `cache_dir`, `bundle_launcher`, `edge_insets`) are asserted directly from their documented results. Cocoa window calls are already exercised by `tests/test_window_mac.py`; add to them only where the gap is there, and skip only for non-macOS (D-06). No change to `app/`.
- **Verify:** Subset run over `tests/test_macsys.py tests/test_audio_devices.py tests/test_mac_autostart.py tests/test_window_poll.py tests/test_quit.py tests/test_window_mac.py` prints both `app/macsys.py` lines as `meets 85`, every test passing; during the run the machine's volume, brightness, clipboard and lock state are unchanged and no app opens. Testing scope: outcomes are the command each system action builds and the parsing of its reply; the window tests cover the Cocoa calls; the added checks stop at the process boundary and at 85/85.

### Task 6: Bring `app/langmark.py` to the floor

- **Files:** tests/test_langmark.py
- **Action:** Close the measured gap in `app/langmark.py` (`unmark`, `lang_of`, `spans`, `romaji`, `guess`, `phonemes` and the `_runs`, `_mark_runs`, `_mark_free` helpers) with tests in `tests/test_langmark.py`, using the file's existing `fake_phonemize` and asserting the marked spans and phoneme runs expected for each input. With `tests/requirements.txt` installed, `RealPhonemes` must run, not skip: if Kokoro's tokenizer still fails to load, stop and report the import error rather than accepting the skip (AC5). No change to `app/`.
- **Verify:** Subset run over `tests/test_langmark.py` with `-rs` prints both `app/langmark.py` lines as `meets 85`, every test passing, and no `RealPhonemes` skip. Testing scope: outcomes are each uncovered mark, guess and phoneme path; the existing markup and phoneme tests cover the main cases; testing stops at 85/85.

### Task 7: Bring `app/notifier.py` to the floor

- **Files:** tests/test_notifier.py
- **Action:** Close any measured gap in `app/notifier.py` (`PingBatch.add`, `PingBatch.due`, `digest`) with tests in `tests/test_notifier.py` driving `PingBatch` through its injected `clock`, asserting when a batch is due (quiet time since the last line, hold time since the first) and the digest's line order. No sleeps and no change to `app/`.
- **Verify:** Subset run over `tests/test_notifier.py tests/test_inbox.py` prints both `app/notifier.py` lines as `meets 85`, every test passing. Testing scope: outcomes are the quiet and hold due rules and digest order; existing notifier and inbox tests likely cover most of it already; testing stops at 85/85.

## Notes

- Closing checks for the plan (no files of their own; run after Task 7 and report the output): the full two-command run for AC3's local half, then AC4 by moving `tests/test_langmark.py` aside, running both commands, quoting the `app/langmark.py: FAIL` line and restoring the file (`git status tests/` clean afterwards). Name the full run's footprint before it runs, as Plan 1 Task 7 does.
- The CI halves of AC3 and AC5 need a push of `personal`, which only the owner can authorize in the turn it happens; no task here pushes.
- If closing a module's gap materially exceeds a task's effort (most likely `macsys` or `agents`), the executor reports the measured gap and the tradeoff once, per the testing policy, rather than lowering the floor or widening the task.
- Recalled D-08 (phases/1/CONTEXT.md, phase 1) sets this plan's floor and module list.
