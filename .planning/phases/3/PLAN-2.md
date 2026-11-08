---
phase: 3
plan: 2
requirements:
  - HEAR-05
files:
  - app/drops.py
  - bin/void
  - tests/test_drops.py
  - tests/test_log_cases.py
---

# Phase 3: Real-log replay - Plan 2: Replay every burst, and the regression table on the owner's rulings

## Goal

Hearing is judged against what the owner actually said. Real `server.log` bursts replay through today's `gate.judge`, and every drop the owner reported is a regression test. Each test still failing is a strict expected failure that names the phase meant to fix it.

## Must be true when done

- `void drops ~/.local/share/void/server.log` prints one row for each stamped verdict line, kept or dropped. Each row shows its text, the verdict as logged, and today's `gate.judge` verdict (KEPT or the reason it drops) or "as logged". Two runs give identical output
- `pytest tests/test_log_cases.py -rxX -v` lists one test per regression row: every `YOURS` text, "It's good", "Yes, do it", "Yes, God damn", and every owner row in `DROPS.md`. Each test passes, or is an expected failure whose reason names Phase 4, 5 or 6. None is skipped
- Setting one expected-failure row's expected verdict to today's verdict turns the suite red
- `app/gate.py` is unchanged over the phase, and every kept or dropped verdict `app/drops.py` prints comes from a `gate.judge` call
- Both accepted coverage commands exit 0, with `app/drops.py` and `app/gate.py` at or above 85% lines and branches. The code is on local `macos` and has reached `personal` by a merge, and nothing is pushed

## Context

- Starts only after Plan 1 ends with every borderline row in `.planning/phases/3/DROPS.md` ruled. That file is read here and never written.
- Locked: D-01 (strict expected failure naming the phase; never skip), D-02 (only short request texts in committed data), D-03 (no widening of `gate.Burst`, and no drop logic in `drops.py` or the tests), D-04 (extend `app/drops.py` and `bin/void drops`, with no second replay path), D-05 (every burst by default, with no new flag), D-06 (verdicts the text cannot re-derive print "as logged"), D-07 (a determinism test), D-08 (no test reads the real log), D-09 (one table extending `YOURS`, one test per row), D-11 (land on local `macos`, merge into `personal`).
- Patterns: `app/drops.py` `parse`, `now`, `replay`, `report`, `main`; `tests/test_drops.py` inline `LOG` with `Replay`, `Report` and `Main`; `tests/test_log_cases.py` `YOURS`, `HIS_*`, `heard()`, `burst()`, `CFG` and its own `Replay` over an inline `LOG`. The suite is unittest-style and runs under `uvx pytest`.
- Out: rewording or removing the `HIS_*` lines; any change to `app/gate.py` or `app/server.py`; `stream/replies-after-quiet` and `stream/stop-echo`; any push.

## Tasks

### Task 1: Open the build worktree on local `macos`

- **Files:** none (worktree only)
- **Action:** Check that every borderline row in `/Users/atom/dev/void/.planning/phases/3/DROPS.md` carries a ruling. If one does not, stop and report it. Record `S`, the `git rev-parse macos` at the start (`226ed6a` when this was planned), so later tasks can diff the phase. Create a worktree at `/Users/atom/dev/void-replay` with `macos` checked out. The sibling path follows Phase 2's `~/dev/void-fixes`, and the name says what is built there. Tasks 2 to 6 work and commit there, on `macos`, under D-11. Never push.
- **Verify:** `git -C /Users/atom/dev/void-replay rev-parse --abbrev-ref HEAD` prints `macos`, and `git -C /Users/atom/dev/void-replay status --porcelain` is empty. `S` is in the task report. Testing scope: no test. The ref checks are the evidence.

### Task 2: `void drops` prints every judged burst, kept as well as dropped

- **Files:** app/drops.py, bin/void, tests/test_drops.py, tests/test_log_cases.py
- **Action:** Make `replay` return a row for every stamped verdict line, `kept (<kind>): <text>` included, beside the drops it lists today. `parse` today discards `kept` (D-05). A kept row's today's verdict comes from the same `now` path as a drop: a `gate.Burst` built from what the log holds, judged by `gate.judge` with `{"voice_gate": True}`. `gate.Burst` gets no new field, and no keep or drop decision is made anywhere but `gate.judge` (D-03). Extend D-06's limit to kept rows. Today's `now` prints "as logged" for a logged noise drop whose text is at `CUT`. A kept row's text at `CUT` that `gate.judge` now calls noise also prints "as logged", because that verdict rests on characters the log cut. Every other kept row prints what `gate.judge` says. Pre-stamp kept lines in the old wording ("follow-up request ...") are not added: AC1 asks for stamped bursts, and the old drop forms keep being listed as now. Each verdict line is one row, so a doubled wake verdict (the wake check, then the full burst) prints as two rows, as the log holds two `gate.judge` calls. The summary rows count every row by its logged verdict. They also give the number of rows, how many the log dropped, and how many of those today's gate keeps. Update the module docstring of `app/drops.py` and the `void drops` usage comment in `bin/void` so both say every heard burst is listed, not only drops. Update the expectations of `tests/test_drops.py` (`Replay`, `test_a_kept_line_is_not_a_drop`, `Report`, `Main`) and of the `Replay` class in `tests/test_log_cases.py` to the new output, rather than adding a flag (CONTEXT flagged assumption). Add a kept line at `CUT` that re-judges as noise to `tests/test_drops.py`'s inline `LOG`. Every new fixture line must be invented. Stamped fixture lines use dates outside 26 Oct to 5 Nov 2026, so none can match a real log line (D-02, AC5).
- **Verify:** `uvx --with-requirements tests/requirements.txt pytest tests/test_drops.py tests/test_log_cases.py -v` passes in the worktree. In it, `Replay` lists the stamped kept lines of both inline logs as rows (line 8 of `tests/test_drops.py`'s `LOG` and line 18 of `tests/test_log_cases.py`'s `LOG`), each with today's verdict, and the kept line at `CUT` that re-judges as noise reads "as logged". Run `python3 /Users/atom/dev/void-replay/app/drops.py ~/.local/share/void/server.log`, which is what `bin/void drops` execs. The number of rows with a stamp equals `grep -cE '^\[void\] [0-9]{4}-[0-9]{2}-[0-9]{2} [0-9:]{8} (kept|no speech|echo|noise|while talking|no wake word|low confidence) \((listen|wake|follow|over|peek)\)' ~/.local/share/void/server.log`. `git diff S -- app/gate.py` is empty. Testing scope: covered already are every old and stamped drop form, `--day`, the default log, undecodable bytes and the script entry. New checks: kept rows in `replay`, the kept-at-the-cut "as logged" case, and the new summary rows. Stop there.

### Task 3: Test that one log replays to identical lines

- **Files:** tests/test_drops.py
- **Action:** Add a test that runs `main` twice on the same fixture log and asserts the two printed outputs are equal line for line (D-07). Use the `Main` class's temporary log, which holds old, stamped, kept and dropped lines, so every row form goes through both runs. The test reads no real log (D-08).
- **Verify:** `uvx --with-requirements tests/requirements.txt pytest tests/test_drops.py -v` shows the new test passing. Run `python3 /Users/atom/dev/void-replay/app/drops.py ~/.local/share/void/server.log` twice into two scratchpad files: `diff` between them prints nothing and exits 0 (AC1). Testing scope: one test. `gate.judge` is pure, so a single equality check over every row form is enough. Stop there.

### Task 4: Turn `YOURS` into the regression table, one test per row

- **Files:** tests/test_log_cases.py
- **Action:** Give `YOURS` the D-09 row fields: text, kind, talking, recent lines, expected verdict and fixing phase. Each `YOURS` text keeps its word-for-word text and its `HIS_*` recent line, which stay unchanged (CONTEXT Out). Its expected verdict is kept, act "follow", rest equal to the text, as today's `test_every_follow_up_of_yours_from_the_log_is_kept` asserts. Its phase is none. Replace that `subTest` loop with one collected pytest test per row, its id carrying the row text, built through the existing `burst()` and `heard()` helpers and `CFG`. The test judges the row's burst with `gate.judge` and asserts the row's expected verdict: keep and why, plus act and rest where the row states them. The row's phase alone decides its mark. A row with a phase gets pytest's `xfail(strict=True, raises=AssertionError, reason=...)`, with a reason that opens with the phase ("Phase 4: ..."). `strict` turns an unexpected pass red (D-01). `raises=AssertionError` keeps a crashing row from passing as an expected failure. A row with no phase gets no mark. Never use `skip`. Import pytest in this module, and change the module docstring's run line to `uvx pytest`, because pytest's marks are what carry the reason. Add a test that every row text is at most `drops.CUT` (80) characters (AC5, D-02).
- **Verify:** `uvx --with-requirements tests/requirements.txt pytest tests/test_log_cases.py -rxX -v` lists 12 row tests, one per `YOURS` text, all passing, plus the length test. Temporarily setting one row's expected why to "echo" fails that row's test alone, and restoring it passes again. `git diff S -- tests/test_log_cases.py` shows no `HIS_*` line changed. Testing scope: the row tests replace the loop with the same assertion per row. The only new checks are the length test and the mark mechanism. Stop there.

### Task 5: Add the owner's reported drops to the table, marked by fixing phase

- **Files:** tests/test_log_cases.py
- **Action:** Add one row for every owner row in `/Users/atom/dev/void/.planning/phases/3/DROPS.md`, ruled borderline rows included, whose text is not already a `YOURS` row. "It's good", "Yes, do it" and "Yes, God damn" are among them. Each row takes its inputs as logged from `DROPS.md` (kind, talking) and its expected verdict and fixing phase from `DROPS.md` (D-03). Where `DROPS.md` says a row needs inputs the log never held, supply them as the row's recent lines or a `heard()` value. Recent lines reproduce echo, and `heard()` values reproduce confidence. Write them for the test, never copied from `history.jsonl` or the log, and keep them short (D-02; CONTEXT flagged assumption). The row then reproduces the verdict the log shows. If a row needs state `gate.Burst` lacks, such as reply timing, own-stop echo or music, it is expressed with today's inputs and its phase, as CONTEXT allows. Never by a new field. A row's text is the owner's short request, at most 80 characters. Where `DROPS.md`'s phase disagrees with what `gate.judge` returns for the row's inputs, the suite says so (a strict XPASS, or a plain failure). Then fix the row's inputs against `DROPS.md`'s evidence and report the disagreement. Never change the expected verdict or phase to make the suite agree.
- **Verify:** `uvx --with-requirements tests/requirements.txt pytest tests/test_log_cases.py -rxX -v` reports one test per row: every `YOURS` text and every owner row in `DROPS.md`. Rows with no phase pass. Every phased row shows as XFAIL, its reason opening "Phase 4", "Phase 5" or "Phase 6". Zero are skipped, failed or XPASS. Then, in the worktree, set one phased row's expected verdict to today's verdict and run `pytest tests/test_log_cases.py`: the output shows that row as `[XPASS(strict)]` and the run fails. Restore the file with `git checkout -- tests/test_log_cases.py` (AC3). Testing scope: one row per reported drop, plus the one mutation run. Stop there.

### Task 6: Prove the phase gates on `macos`

- **Files:** none (verification only)
- **Action:** In `/Users/atom/dev/void-replay`, run the repo gate and the phase's acceptance checks on the final tree. Run `python3 -m py_compile app/*.py`. Run both accepted commands from `.github/cadence/coverage-policy.json` verbatim, with `PYTEST_ADDOPTS="-rsxX"` as in `.github/workflows/tests.yml`, so skips, expected failures and their reasons print. Diff `app/gate.py` against `S` (AC4). For AC5, write a scratchpad script, never committed, that collects every added line under `tests/` in `git diff S..macos`. Build a pattern file of every unique WHOLE real-log line of 20 or more characters, each with its stamp and kind prefix as logged; never a verdict line's bare text, because D-02 commits the owner's short request texts ("It's good", "Yes, do it") word for word and AC5 forbids only a log line found verbatim. Run `grep -F -f` with those patterns over the added lines. A hit is a log excerpt. Stop, and report the hit and its file. Then replace it with invented text under the lease of the task that wrote it (Task 2 or 5), and run this task again. A failing gate is not committed past. Report it, quoting its shortest decisive line.
- **Verify:** `py_compile` exits 0. The pytest command exits 0, and its summary shows no skip for a `test_log_cases.py` or `test_drops.py` test. Every `test_log_cases.py` xfail reason names Phase 4, 5 or 6. `node .github/ci/coverage-modules.mjs --report coverage.json` exits 0, and its lines for `app/drops.py` and `app/gate.py` show 85 or more for lines and for branches (AC6). `git diff S..macos -- app/gate.py` prints nothing. `git grep -n 'gate\.judge' app/drops.py` shows the one call in `now`, which every kept or dropped verdict the report prints goes through (AC4). The AC5 `grep -F` prints no line, and the row-length test passed in the run above. Testing scope: no new test. These are the repo's own gates.

### Task 7: Merge `macos` into `personal`

- **Files:** none (a merge commit on `personal`; the files are those of Tasks 2 to 5)
- **Action:** In `/Users/atom/dev/void` on `personal`, first check that `git status --porcelain --untracked-files=no` is empty, and stop if it is not. Run `git merge macos` with git's default message (D-11; Phase 2 D-04). On a conflict, stop and run `git merge --abort`, and never resolve it by hand. Never push `personal` or `macos`.
- **Verify:** `git merge macos` exits 0 with no conflict. `git diff macos personal -- app/drops.py bin/void tests/test_drops.py tests/test_log_cases.py` prints nothing. `git rev-list --count personal..macos` prints 0. `uvx --with-requirements tests/requirements.txt pytest tests/test_drops.py tests/test_log_cases.py -rxX` in `/Users/atom/dev/void` reports the same pass and xfail counts as Task 5. `git rev-parse origin/macos origin/personal` is unchanged from before the merge. Testing scope: no new test. The re-run of the two files on `personal` is the evidence.

### Task 8: Remove the build worktree

- **Files:** none (worktree removal only)
- **Action:** Remove `/Users/atom/dev/void-replay` with `git worktree remove`. Touch no other worktree or branch. Report the final SHAs of `macos`, `personal` and `origin/macos`.
- **Verify:** `git worktree list` no longer shows `/Users/atom/dev/void-replay`. `git rev-parse origin/macos` is `29e22ae…`. The `stream/replies-after-quiet`, `stream/stop-echo` and `ci-debug/fake-servers` tips are unchanged (`ce5b1e5`, `3ef6fbc`, `e667dad`). Testing scope: no test. The ref checks are the evidence.

## Notes

- Interpretation, recorded rather than taken silently: AC1's "one line per stamped burst" is read as one row per logged verdict line. That is one per `gate.judge` call, so the wake check's doubled verdict prints twice, as the log holds it. Pre-stamp kept lines in the old wording are not added; only the old drop forms stay listed. Either can be revisited if the owner wants it otherwise.
- `stream/replies-after-quiet` changes `tests/test_log_cases.py`, `app/drops.py` and `app/gate.py` from an older base (`git diff --stat macos stream/replies-after-quiet`). Phase 4 will meet this table in its merge and must remove the marks it fixes, as D-01 requires.
- Footprint: Task 6 runs the full suite with coverage, page tests on Chrome and Qt included. It holds a core for well over 10 s and is named before it runs. Every other run is two test files, or one `drops.py` pass over the real log, which takes seconds.
- Nothing is pushed, so the `tests` job does not run on these commits. Task 6's local run stands for CI until the version bump pushes `macos` (Phase 7; Phase 2 D-03).
- Recalled: D-01 and D-03 (`phases/3/CONTEXT.md`, phase 3) shape Tasks 4 and 5. D-01 (`phases/2/CONTEXT.md`, phase 2) classes `gate.judge`, `hearing.Voicing` and `void drops` as fix-bound, which is why the work lands on `macos`. The worktree, merge and removal tasks follow Phase 2's Plan 2 (`phases/2/PLAN-2.md`, phase 2).
