---
phase: 5
plan: 4
requirements:
  - HEAR-03
  - HEAR-04
files: []
---

# Phase 5: Own stop is echo - Plan 4: Prove the gates, merge into `personal`, remove the build worktree

## Goal

The own-stop work reaches `macos` green and `personal` by a merge, with every replay row and scene that passed at the end of Phase 4 still passing, and nothing pushed.

## Must be true when done

- On `macos`, the full suite and both accepted coverage commands exit 0, with `app/gate.py`, `app/hearing.py` and `app/drops.py` at or above 85% lines and branches (AC6)
- Every `tests/test_log_cases.py` row and scene that passed at `bf7b120` still passes, and the new own-stop rows pass with no expected-failure mark (AC5)
- The phase's diff on `macos` touches nothing under `docs/superpowers/`, `docs/design/`, `.claude/`, `queues/` or `.planning/`, and no `CLAUDE.md`. Merging `macos` into `personal` gives no conflicts (AC6)
- No branch is pushed, and the `~/dev/void-stop-echo` worktree and `stream/stop-echo` are untouched

## Context

- Runs after Plan 3. `S` is Plan 1 Task 1's recorded `git rev-parse macos`. The baselines are Plan 1 Task 1's (`macos`, `personal`, and the slow scene tier).
- Locked: D-07 (code lands on `macos` first and reaches `personal` by merging `macos`; nothing pushed). Out of scope: removing or committing `~/dev/void-stop-echo` or `stream/stop-echo`.
- `macos` holds `c2bf596`, a cherry-pick of `personal`'s `c9d64cb` (the same test change). The merge sees the same change on both sides and should not conflict on it.
- This plan writes no file. A failing gate is not fixed here: it is reported, and the phase stops before the merge.

## Tasks

### Task 1: Prove the phase gates on `macos`

- **Files:** none (measurement only)
- **Action:** In `/Users/atom/dev/void-own-stop`, run `python3 -m py_compile app/*.py`. Then run both accepted commands from `.github/cadence/coverage-policy.json` verbatim, with `PYTEST_ADDOPTS="-rsxX"`. That is the full suite, Chrome page tests included, holding a core for well over 10 s, so name it before it starts. Compare its counts and per-test results with Plan 1 Task 1's `macos` baseline. List `git diff --name-only S..macos`. A failing gate is not committed past or fixed in this plan. Report it with its shortest decisive line, name the plan and task whose change it traces to, and stop.
- **Verify:**
  - `py_compile` exits 0.
  - The pytest command exits 0, with no `test_page_*.py`, fast-tier `test_scenes.py` or `test_log_cases.py` test skipped.
  - Every test that passed in the `macos` baseline passes, and every own-stop row in `tests/test_log_cases.py` passes with no xfail or xpass.
  - `node .github/ci/coverage-modules.mjs --report coverage.json` exits 0, with `app/gate.py`, `app/hearing.py` and `app/drops.py` each at 85 or more for lines and branches.
  - `git diff --name-only S..macos` lists no path under `docs/superpowers/`, `docs/design/`, `.claude/`, `queues/` or `.planning/`, and no `CLAUDE.md`.
  - `git grep -n "word_timestamps" app/` lists only `run_whisper_heard`, and `git grep -n "/api/played" app/` prints nothing.
  Testing scope: no new test. These are the repo's gates.

### Task 2: Merge `macos` into `personal` and re-run the suite there

- **Files:** none (merge only)
- **Action:** In `/Users/atom/dev/void` on `personal`, first check that `git status --porcelain --untracked-files=no` is empty, and stop if it is not. The untracked `.planning/phases/*/ADJUDICATION-*.json` files are not in the way. Run `git merge macos` with git's default message (D-07). On a conflict, run `git merge --abort` and stop. Never resolve it by hand. Then run the accepted pytest command with `PYTEST_ADDOPTS="-rsxX"` on `personal`, naming the run before it starts. Phase 3 skipped this step (Phase 3 SUMMARY, phase 3). Compare its results with Plan 1 Task 1's `personal` baseline, which is `bf7b120`'s code, for AC5. Never push `personal` or `macos`.
- **Verify:**
  - `git merge macos` exits 0 with no conflict, and `git rev-list --count personal..macos` prints 0.
  - The `personal` run exits 0. Every `tests/test_log_cases.py` row and every scene that passed in the `personal` baseline still passes, and the own-stop rows pass with no mark.
  - `git rev-parse origin/macos origin/personal` prints `29e22ae…` and `c9d64cb…`, unchanged.
  Testing scope: no new test. The full run on `personal` is the evidence.

### Task 3: Remove the build worktree

- **Files:** none (worktree removal only)
- **Action:** Remove `/Users/atom/dev/void-own-stop` with `git worktree remove`. Touch no other worktree or branch. `/Users/atom/dev/void-stop-echo` with `stream/stop-echo`, and `/Users/atom/dev/void-replies` with `stream/replies-after-quiet`, stay as they are, because retiring them is out of this phase. Report the final SHAs of `macos`, `personal` and `origin/macos`.
- **Verify:**
  - `git worktree list` no longer shows `/Users/atom/dev/void-own-stop`.
  - `git rev-parse stream/stop-echo stream/replies-after-quiet` prints `3ef6fbc…` and `ce5b1e5…`, unchanged.
  - `git -C /Users/atom/dev/void-stop-echo status --porcelain` still lists the worktree's 18 modified and 3 untracked paths.
  Testing scope: no test. The ref checks are the evidence.

## Notes

- This plan exists because Plan 3's six scene and measurement tasks, plus these three, exceed the 8-task ceiling for one plan.
- Footprint: Task 1 and Task 2 each run the full suite once (a core for minutes, Chrome and Qt included). Name each before it runs.
