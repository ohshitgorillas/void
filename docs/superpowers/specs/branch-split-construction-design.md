Status: approved.

# Branch split: how `macos-fixes` is built

## Why

Phase 2 builds `macos-fixes` off local `macos` (`c895ced`) from the `fix` rows of `.planning/phases/2/CLASSIFICATION.md`. The construction of each row, the test that a row is present, and the merge-back conditions are each written in more than one place, and several copies are wrong for this tree.

- Per-row construction: 3 copies. `.planning/phases/2/PLAN-1.md:48` (plain pick or path-split, skip on conflict), `.planning/phases/2/PLAN-2.md:43` (plain pick or path-split), `.planning/phases/2/CLASSIFICATION.md:186` (path-split recipe). None covers `044e7f9`, which conflicts as a plain pick with fix row `6120ace` (`CLASSIFICATION.md:96`): `6120ace` rewrites the `is_noise` comment beside the line `044e7f9` changes, `6120ace` is on neither `c895ced` nor `044e7f9`'s history, and the only resolution is merge `8cacc1d` (parents `2f1d75d`, `044e7f9`; `2f1d75d..044e7f9` is `044e7f9` alone). None covers the six `fix` rows `c895ced` already holds (`CLASSIFICATION.md:202-209`).
- Presence test: 4 copies. `.planning/phases/2/CONTEXT.md:70`, `.planning/phases/2/PLAN-2.md:27`, `.planning/phases/2/PLAN-2.md:44`, `.planning/phases/2/CLASSIFICATION.md:188-190`. All rest on `git cherry` printing `-`, which fails for the six rows (`git cherry macos 74af430` prints `+` for each, with identical author, author date, subject and changed-line bytes to their `c895ced` copies), for `044e7f9` (its context differs), and for every path-split row.
- Path-split list: 4 copies. `.planning/phases/2/PLAN-1.md:19`, `PLAN-1.md:42`, `PLAN-1.md:84`, `CLASSIFICATION.md:176`. The first three name four rows; `CLASSIFICATION.md:184` holds a fifth, `bb02446`, whose `tests/test_page_sparks.py` hunk edits a file only the visual `87344d3` (`CLASSIFICATION.md:25`) creates and `c895ced` lacks.
- Merge-back cleanliness: 7 copies. `CONTEXT.md:76`, `PLAN-1.md:22`, `PLAN-1.md:61`, `PLAN-1.md:73`, `PLAN-2.md:30`, `PLAN-2.md:62`, `PLAN-2.md:68`. None allows for the one probe conflict (`CLASSIFICATION.md:240`): `8935491` inserts personal-only ignore lines at the same point (after `installer/art/`) where `5a4f07d` inserts `coverage.json` and `.coverage`.

## Modules

Each module is a recipe in `.planning/phases/2/CLASSIFICATION.md`, written once by Plan 1 and run by Plan 1's trials and Plan 2's build.

**Row construction** (Trial section, "Construction"): turns each `fix` row, in table order, into zero or one commit on the branch. Replaces `PLAN-1.md:48`, `PLAN-2.md:43` and `CLASSIFICATION.md:186` as the statement of how a row is built.

```
# kind: present   (ad1da73, 0ba0fec, 16b5829, f3b2947, 3935571, 7ef0a99)
#   no command; c895ced already holds 975c918, 16d33c7, fabc753, 8c064eb, c63fdea, 5033bce
# kind: plain     (every fix row not named below)
git cherry-pick <sha>
# kind: path-split (c378787, d015d26, 45d4f02, 4488777, bb02446)
git cherry-pick -n <sha>
#   then each left-behind path of that row's Path-split entry goes back to its pre-pick state:
#   restored from HEAD where HEAD has it; removed from index and tree where it does not
git commit -C <sha>
# kind: vehicle   (044e7f9 only)
git cherry-pick -n -m 1 8cacc1d
git commit -C 044e7f9
```

A conflict, an empty pick or a non-empty `git status --porcelain` after `commit` in any kind is a stop, never a resolution. The count of commits made is the number of `fix` rows less the `present` rows (87 at snapshot `74af430`).

**Presence test** (Trial section, "Presence"): decides whether a `fix` row is on a branch. Replaces `git cherry ... -` as presence evidence at `CONTEXT.md:70`, `PLAN-2.md:27`, `PLAN-2.md:44`, `CLASSIFICATION.md:188-190`.

```
key(<sha>)      = git log -1 --format='%an%x00%aI%x00%s' <sha>
present(<sha>, <branch>) = exactly one line of `git log --format='%an%x00%aI%x00%s' <branch>` equals key(<sha>)
absent(<sha>, <branch>)  = no line equals key(<sha>), and `git cherry <branch> <snapshot>` prints `+ <sha>`
```

Every `fix` row, of every kind, is `present` on the built branch; every `visual` and `feature` row is `absent`. `commit -C` keeps the key of path-split and vehicle rows, and the `present` rows match their `c895ced` copies.

**Ignore reorder** (Trial section, "Merge-back prep"): one commit on `personal`, made after `macos` carries `macos-fixes` and before any merge of `macos` into `personal`. It touches `.gitignore` alone and changes line order only:

```
<the 8935491 block: "# macOS maintainer's todo list" through ".planning/reads.1.jsonl.evict.*",
 then a blank line, then "# Claude Code agent worktrees - each is its own git checkout", ".claude/worktrees/">
<blank line>
<lines from "__pycache__/" to end, byte-identical to `git show macos-fixes:.gitignore`>
```

Message: `chore: list personal-only ignores above the shared ones, so macos merges in cleanly`. Plan 1's trial merges apply the same reorder as a commit on their detached scratch worktree only.

## Homes

| Concern | Home | Forbidden elsewhere |
|---|---|---|
| How a `fix` row becomes a commit | Row construction, `CLASSIFICATION.md` Trial section | a plan restating a recipe, a per-row exception outside the four kinds, `-m` on any merge but `8cacc1d`, any hand edit or conflict resolution |
| Which rows are path-split | `CLASSIFICATION.md` Path-split table | a plan or note enumerating path-split rows; a plan's lines cite the section |
| Whether a row is on a branch | Presence test | `git cherry` `-` as the sole evidence a `fix` row is present; a `+` read as absence of a `fix` row |
| Merge-back conflict prep | Ignore reorder, built by Plan 2 under its `.gitignore` lease | any other commit on `personal` touching `.gitignore` in this phase; Plan 1 committing to `personal` |
| What counts as "no changed file" | `git diff --name-only <the ignore reorder commit> personal` after the merge | measuring from the commit before the reorder |
| Owner rows | `CLASSIFICATION.md` Borderline section | Borderline rows for any construction above: the four kinds and the reorder are technical and settled here |

`f3b2947` (Borderline B-06) is a `present` row: `c895ced` holds it as `8c064eb`. B-06 tells the owner so; its ruling changes the table class, and no build step picks, skips or reverts it.

## Order

1. Plan wording: replace the Verify and must-be-true lines of `.planning/phases/2/PLAN-1.md` and `.planning/phases/2/PLAN-2.md`, `CONTEXT.md` AC3, and add Plan 2's reorder task. Writes `.planning/phases/2/PLAN-1.md`, `.planning/phases/2/PLAN-2.md`, `.planning/phases/2/CONTEXT.md`. Agent: the phase lead.
2. Plan 1 recipes: write Row construction, Presence test and Merge-back prep into the Trial section, correct `044e7f9`'s cause at `CLASSIFICATION.md:217` and `:238` to fix row `6120ace`, and drop the "Borderline row" requirement for `bb02446`. Writes `.planning/phases/2/CLASSIFICATION.md`. Agent: Plan 1 executor.
3. Plan 1 Tasks 4 to 8 on the Row-construction tree, trial merges with the reorder applied in scratch. Writes `.planning/phases/2/CLASSIFICATION.md`. Agent: Plan 1 executor.
4. Plan 2 Tasks 1 to 3: build `macos-fixes` by Row construction, gate it, fast-forward `macos`. Writes `app/`, `bin/`, `tests/`, `.github/`, `packaging/`, `install.sh`, `install.ps1`, `.gitignore` on `macos-fixes` and `macos`. Agent: Plan 2 executor.
5. Plan 2 reorder task: the Ignore reorder commit on `personal`. Writes `.gitignore` on `personal`. Agent: Plan 2 executor.
6. Plan 2 Tasks 4 to 6: trial merge, real merge of `macos` into `personal`, worktree removal. Writes no file. Agent: Plan 2 executor.
