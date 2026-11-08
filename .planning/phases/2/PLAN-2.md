---
phase: 2
plan: 2
requirements:
  - SPLIT-02
  - SPLIT-03
files:
  - app/
  - bin/
  - tests/
  - .github/
  - packaging/
  - install.sh
  - install.ps1
  - .gitignore
---

# Phase 2: Branch split - Plan 2: Build the fix branch, land it on macos, merge back

## Goal

The ruled fix set sits on a branch off local `macos` and passes the repo gate. Local `macos` carries it, and `personal` takes it by one clean merge that changes no file, so every later fix flows `macos` -> `personal` by merge.

## Must be true when done

- Branch `macos-fixes`, based on `c895ced` and built by the Trial section's Row construction, holds every `fix` row of `.planning/phases/2/CLASSIFICATION.md` by the Presence test (the five `present` fix rows through `c895ced`), and no change under `CLAUDE.md`, `.claude/`, `queues/`, `docs/superpowers/`, `docs/design/` or `.planning/`
- For every `fix` row, exactly one line of `git log --format='%an%x00%aI%x00%s' macos-fixes` equals `git log -1 --format='%an%x00%aI%x00%s' <sha>`; for every `visual` and `feature` row but `f3b2947` (present through `8c064eb`), no line equals it and `git cherry macos-fixes <snapshot>` prints `+`
- On `macos-fixes`, `python3 -m py_compile app/*.py` and both accepted coverage commands exit 0, with all 7 `include` modules at or above 85 for lines and branches
- Local `macos` contains `macos-fixes`, and `origin/macos` is still `29e22ae`
- `personal` carries the Merge-back prep commits `R` (`.gitignore` only, line order only) and `H` (the Hold-back paths taken from `macos`), merges `macos` at `H` with no conflict and no file changed from `H`, then reverts `H`, so that `git diff --name-only R personal` prints nothing and `git rev-list personal..macos` is empty, and the next fix on `macos` reaches `personal` by a plain merge

## Context

- Starts only after Plan 1 ends with every Borderline row ruled and a clean Ruled trial. The classification file is read here and never written.
- Locked: D-03 (merge into local `macos` at any time; `origin/macos` pushed only at a version bump), D-04 (from now on, fixes land on local `macos` first and reach `personal` by merge), D-07 (fix branch into local `macos`, then `macos` into `personal`; no push of `personal` or the fix branch), D-08 (cherry-pick in table order; path-splits as Plan 1 recorded them), D-09 (`tests` job and coverage policy unchanged), D-10.
- Out: any push, fetch or other remote touch; `stream/*`, `ci-debug/fake-servers` and agent worktree branches; hand-resolving any conflict.

## Tasks

### Task 1: Build `macos-fixes` from the ruled classification

- **Files:** app/, bin/, tests/, .github/, packaging/, install.sh, install.ps1, .gitignore
- **Action:** First confirm the classification still holds. Every commit in `<snapshot>..personal` (the snapshot named in `CLASSIFICATION.md`) touches only `.planning/`. Every Borderline row has a ruling, and the Ruled trial section records zero skips. If any of these fails, stop and report it without building. Then create a worktree at `/Users/atom/dev/void-fixes` on a new branch `macos-fixes` at local `macos` (`c895ced`). The name is my choice: it says what the branch holds and where it goes, and the sibling path follows `~/dev/void-replies`. Build every `fix` row in table order by the Trial section's Row construction (`present`, `plain`, `path-split`, `line-split` and `vehicle` kinds). Leave out `-x`, because the classification is the SHA map and the messages ship to `macos` unchanged. A conflict or an empty pick here contradicts the Ruled trial. Stop at it, `git cherry-pick --abort`, and report the commit and the shortest decisive line. Never resolve it by hand.
- **Verify:** `git diff --name-only c895ced..macos-fixes` lists no path under `CLAUDE.md`, `.claude/`, `queues/`, `docs/superpowers/`, `docs/design/` or `.planning/` (AC2). `git rev-list --count c895ced..macos-fixes` equals the number of `fix` rows less the five `present` fix rows (94 at snapshot `74af430`). `git rev-parse macos-fixes^{tree}` equals the ruled trial's tree SHA recorded in the Ruled trial section. For every `fix` row, exactly one line of `git log --format='%an%x00%aI%x00%s' macos-fixes` equals `git log -1 --format='%an%x00%aI%x00%s' <sha>`; for every `visual` and `feature` row but `f3b2947` (present through `8c064eb`), no line equals it and `git cherry macos-fixes <snapshot>` prints `+` (AC3 by the Presence test). A `fix` row with no match or two matches is a missing or doubled commit: stop and report it, and never reclassify it. `git cat-file -e macos-fixes:app/voiceprint.py` fails. Testing scope: no test. The ref and path checks are the evidence, and the gate runs in Task 2.

### Task 2: Prove the repo gate on `macos-fixes`

- **Files:** none (runs checks only; the `coverage.json` it writes is git-ignored and removed)
- **Action:** In `/Users/atom/dev/void-fixes`, run `python3 -m py_compile app/*.py`. Before the suite, tell the user its footprint (rule 3.1): about 270 s on Slate, about one core, and Qt windows and Chrome on Slate's screen. Then, with `UV_PYTHON=3.12` set, run the two accepted commands from `.github/cadence/coverage-policy.json` verbatim, in order. Change no test, no `app/` file and no policy value to make them pass (D-09, rule 6.3). A failure is reported with its shortest decisive line as a 6.1 question, and Tasks 3-6 do not run. After the run, check with `ps` that the run left no process, and kill any leftover by PID (rule 4.1). Remove the generated `coverage.json` from the worktree. It is ignored by `5a4f07d`'s `.gitignore` line, and removing it keeps the worktree clean.
- **Verify:** `python3 -m py_compile app/*.py` exits 0. The first accepted command exits 0 with no failed test, and every skip reason is the `VOID_SCENES` slow tier. `node .github/ci/coverage-modules.mjs --report coverage.json` exits 0 and prints 14 `meets 85` lines covering `app/gate.py`, `app/hearing.py`, `app/agents.py`, `app/langmark.py`, `app/macsys.py`, `app/notifier.py` and `app/drops.py` (AC4). `git -C /Users/atom/dev/void-fixes status --porcelain` is empty. Testing scope: the existing suite and per-module gate are the whole evidence. The phase changes no behavior, so no test is added, and testing stops at this run.

### Task 3: Land `macos-fixes` on local `macos`

- **Files:** app/, bin/, tests/, .github/, packaging/, install.sh, install.ps1, .gitignore
- **Action:** In `/Users/atom/dev/void-fixes`, switch to `macos` and run `git merge --ff-only macos-fixes`. I chose a fast-forward: `macos-fixes` is built directly on `macos`, so it is `macos`'s next state, and a merge commit would add nothing. Never push `macos` or `macos-fixes`, and never fetch (D-03, D-07). Then switch the worktree back to `macos-fixes`, so `macos` is not held checked out.
- **Verify:** `git merge-base --is-ancestor macos-fixes macos` exits 0, and `git rev-parse macos` equals `git rev-parse macos-fixes`. `git rev-parse origin/macos` prints `29e22aead6f2667079097d2c238fdd3c284d0936` (AC5). Testing scope: no test. The ref checks are the evidence.

### Task 3a: Reorder `.gitignore` on `personal`

- **Files:** .gitignore
- **Action:** In `/Users/atom/dev/void` on `personal`, make the Merge-back prep reorder commit `R` exactly as the Trial section's "Merge-back prep" recipe states, with the message `chore: list personal-only ignores above the shared ones, so macos merges in cleanly`. It changes line order only. Never push `personal`.
- **Verify:** `git show --stat --format= R` lists `.gitignore` alone. `git show R:.gitignore | sort` equals `git show R^:.gitignore | sort`. The lines of `git show R:.gitignore` from `__pycache__/` to the end equal `git show macos-fixes:.gitignore` byte for byte. `git rev-parse origin/personal` is unchanged. Testing scope: no test. The diff checks are the evidence.

### Task 3b: Hold back the Merge-back prep paths on `personal`

- **Files:** app/server.py, tests/test_agents.py
- **Action:** In `/Users/atom/dev/void` on `personal` at `R`, make the Merge-back prep Hold-back commit `H` exactly as the Trial section's "Merge-back prep" recipe states: `git checkout macos -- <each path of its Hold-back table>`, then `git commit -m 'chore: take the Hold-back paths from macos for one merge; reverted right after it'`. Task 5b reverts it. Never push `personal`.
- **Verify:** `git rev-parse H^` equals `R`. `git show --stat --format= H` lists the Hold-back paths alone. `git diff --name-only macos H -- <each Hold-back path>` prints nothing. `git rev-parse origin/personal` is unchanged. Testing scope: no test. The diff checks are the evidence.

### Task 4: Trial-merge `macos` into a scratch copy of `personal`

- **Files:** none (a scratch worktree, merged with `--no-commit` and aborted)
- **Action:** In a scratch worktree under the executor's scratchpad, detached at the current `personal` tip, run `git merge --no-commit --no-ff macos`. Record whether it conflicts and what `git diff --cached --name-only HEAD` lists. Then `git merge --abort` and remove the worktree. This runs before the real merge (CONTEXT, flagged assumptions). A conflict or a changed file contradicts Plan 1's Ruled trial. Stop, report the paths and the shortest decisive line, and do not run Task 5.
- **Verify:** With `personal` at `H`, the trial merge reports no conflict, `git diff --cached --name-only HEAD` prints nothing, and `git worktree list` no longer shows the scratch path. Testing scope: no test. The trial merge is the evidence.

### Task 5: Merge `macos` into `personal`

- **Files:** none (a merge commit on `personal` that AC6 proves changes no file)
- **Action:** In `/Users/atom/dev/void` on `personal`, first check that `git status --porcelain --untracked-files=no` is empty, and stop if it is not. Record `B`, the `git rev-parse personal` before the merge. Run `git merge macos` with git's default message ("Merge branch 'macos' into personal"). Never push `personal` (D-07). This merge is the flow D-04 and SPLIT-03 name for every later fix. A fix landed on local `macos` reaches `personal` by the same command, and nothing is cherry-picked again.
- **Verify:** `git merge macos` exits 0 with no conflict, `B` equals `H`, and `git diff --name-only $B personal` prints nothing (AC6). `git rev-list --count personal..macos` prints 0, and `git merge-base personal macos` equals `git rev-parse macos`, so the next commit on `macos` merges in alone (SPLIT-03). `git rev-parse origin/personal` is unchanged from before the merge. Testing scope: no test. The diff and ancestry checks are the evidence.

### Task 5b: Revert the Hold-back commit on `personal`

- **Files:** app/server.py, tests/test_agents.py
- **Action:** In `/Users/atom/dev/void` on `personal` at Task 5's merge, run `git revert --no-edit H`. A conflict is a stop (`git revert --abort`, report the shortest decisive line), never a resolution. Never push `personal`.
- **Verify:** `git revert` exits 0 with no conflict. `git diff --name-only R personal` prints nothing. `git rev-list --count personal..macos` prints 0. `git rev-parse origin/personal` is unchanged. Testing scope: no test. The diff and ancestry checks are the evidence.

### Task 6: Remove the build worktree

- **Files:** none (worktree removal only)
- **Action:** Remove `/Users/atom/dev/void-fixes` with `git worktree remove`, and keep the branch `macos-fixes` (it is the SPLIT-02 deliverable). Touch no other worktree or branch (D-10). Report the final SHAs of `macos`, `macos-fixes`, `personal` and `origin/macos`.
- **Verify:** `git worktree list` no longer shows `/Users/atom/dev/void-fixes`, and `git branch --list macos-fixes` prints it. `git rev-parse origin/macos` is `29e22ae…`. The `stream/replies-after-quiet`, `stream/stop-echo` and `ci-debug/fake-servers` tips match their values before the phase (`ce5b1e5`, `3ef6fbc` and `e667dad`). Testing scope: no test. The ref checks are the evidence.

## Notes

- This plan runs after Plan 1: it reads the ruled classification and the Ruled trial tip. The two plans declare no file in common, so their leases are disjoint, but they are sequential, not parallel. That ordering follows from the CONTEXT plan shape (classification with the owner's rulings first, then build, verify and merge).
- The leases are directory leases on the paths the cherry-picks write onto `macos-fixes` and `macos`, and on the paths Tasks 3a, 3b and 5b commit on `personal`: `.gitignore` (R, line order only) and the Hold-back paths `app/server.py` and `tests/test_agents.py` (H and its revert). The fast-forward and the merge into `personal` write no file of their own: the merge changes no file from `H`, and after Task 5b `personal`'s tree equals `R`'s. Tasks 2, 4 and 6 commit nothing. Their `Files` say so.
- Pushing `macos` happens at the version bump (Phase 7, D-03). Pushing `personal` or `macos-fixes` needs the owner's word in that turn (D-07). Neither is in this plan. So the `tests` job does not run on these commits here, and AC4 is proved by the local run in Task 2.
- Recalled: D-03 and D-04 (`phases/2/CONTEXT.md`, phase 2). The `tests` workflow shape (`phases/1/UAT.md`, phase 1) is why the local gate run stands in for CI until a push.
