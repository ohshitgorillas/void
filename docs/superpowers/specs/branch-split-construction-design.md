Status: approved.

# Branch split: how `macos-fixes` is built

## Why

Phase 2 builds `macos-fixes` off local `macos` (`c895ced`) from the `fix` rows of `.planning/phases/2/CLASSIFICATION.md`. The recipes live in its Trial section (Construction `CLASSIFICATION.md:238`, Presence `:259`, Merge-back prep `:271`); the ruled set breaks them in three places, and the plans copy the parts that break.

- Row construction: the four kinds (`CLASSIFICATION.md:242-256`) cannot build the ruled set. `0e6cd82` (fix, `:76`) stops at `DU tests/test_voice_prompt.py` (`:343`): it adds two lines to a file only `fb16e92` (feature, `:64`) creates, and seven later rows need the `tests/suite_data.py` it creates (`:345`). `f4acc7d` (`:145`) adds all its tests in one 322-line hunk of `tests/test_agents.py`; three of them test `283432f`'s `tool_images` (`:318-320`; `283432f` is feature, `:34`), and no path-level kind leaves only those behind. With the whole row out, `app/agents.py` is 82.38% branches, under 85 (`:357`); with it in, 97.14 (`:308`).
- Kind list: 2 copies, `.planning/phases/2/PLAN-1.md:49` and `.planning/phases/2/PLAN-2.md:43`, both naming four kinds. Path-split list: 2 copies, `PLAN-1.md:19` and `CLASSIFICATION.md:176`, both still naming `bb02446`, a plain pick since `87344d3` is fix (`:176`); neither names `0e6cd82`.
- Commit count: `PLAN-2.md:44` says 87 made and six `present`; the ruled set makes 92 of 97 with five `present` (`CLASSIFICATION.md:339`), and this design's set makes 94.
- Merge-back: 7 copies of "after the reorder, no conflict", `PLAN-1.md:22`, `:61-62`, `:73-74`, `PLAN-2.md:30`, `:68`, `:74`, `.planning/phases/2/CONTEXT.md:78-80`. A personal-only line next to a line both sides add conflicts: `fb16e92`'s two `VOICE_PROMPT` lines (`app/server.py:94-95` on `personal`) after `e53ea7b`'s hover-off lines (`CLASSIFICATION.md:379`), and `89f4bfe`'s `loopback_http` import in `tests/test_wake_loop.py` (`:380`). `89f4bfe` (`:168`) changes no thumbnail code: it moves three test files onto `6271a78`'s `loopback_http` servers (`6271a78` is fix, `:167`). Once the rest of `f4acc7d` is on the branch, its 21 thumbnail-test lines sit inside a block both sides add, which is the same shape as the `VOICE_PROMPT` conflict (not yet measured).

## Modules

Each module is a recipe in `.planning/phases/2/CLASSIFICATION.md`, written once by Plan 1 and run by Plan 1's trials and Plan 2's build.

**Row construction** (Trial section, "Construction"): turns each `fix` row, in table order, into zero or one commit on the branch. Replaces the kind lists at `PLAN-1.md:49` and `PLAN-2.md:43` as the statement of how a row is built.

```
# kind: present    (ad1da73, 0ba0fec, 16b5829, 3935571, 7ef0a99; f3b2947, class feature, is held the same way)
#   no command; c895ced already holds 975c918, 16d33c7, fabc753, c63fdea, 5033bce, and 8c064eb for f3b2947
# kind: plain      (every fix row not named below, 89f4bfe included)
git cherry-pick <sha>
# kind: path-split (every row of the Path-split table: c378787, d015d26, 45d4f02, 4488777, 0e6cd82)
git cherry-pick -n <sha>
#   then each left-behind path of that row's Path-split entry goes back to its pre-pick state:
#   restored from HEAD where HEAD has it; removed from index and tree where it does not
git commit -C <sha>
# kind: line-split (every row of the Line-split table: f4acc7d)
#   before the pick: git rev-parse HEAD:<path> equals the row's base blob, else stop
git cherry-pick -n <sha>
git show <sha>:<path> | sed -e '<range 1>d' -e '<range 2>d' > <path>
git add <path>
git commit -C <sha>
#   after: git diff HEAD <sha> -- <path> has no '-' line, and its '+' lines are exactly the row's left-behind lines
# kind: vehicle    (044e7f9 only)
git cherry-pick -n -m 1 8cacc1d
git commit -C 044e7f9
```

A conflict, an empty pick, a failed line-split check or a non-empty `git status --porcelain` after `commit` in any kind is a stop, never a resolution. A modify/delete conflict on a left-behind path (`0e6cd82` on `tests/test_voice_prompt.py`) is cleared by the path-split restore step, which removes the path; any other conflict is a stop. Every line a kind puts on the branch comes from its own row's diff (from `8cacc1d`'s for the vehicle); line-split only drops named `+` lines of its row. The count of commits made is the number of `fix` rows less the five `present` fix rows: 94 (99 - 5): 87 plain, 5 path-split, 1 line-split, 1 vehicle.

Path-split table row added (`CLASSIFICATION.md` Path-split section; `bb02446`'s row stays out):

| Commit | Carried onto the fix branch | Left behind on `personal` |
|---|---|---|
| 0e6cd82 | `tests/suite_data.py`, `tests/test_suite_data_dir.py` (both created), and `tests/` `test_audio_devices.py`, `test_echo.py`, `test_echo_diagnostics.py`, `test_gate.py`, `test_hearing.py`, `test_inbox.py`, `test_langmark.py`, `test_mac_autostart.py`, `test_portable_paths.py`, `test_scenes.py`, `test_speaker_switch.py`, `test_voiceprint.py`, `test_wake_loop.py` | `tests/test_voice_prompt.py` (its 2-line `import suite_data` hunk; the file is created by `fb16e92`, class feature) |

A path-split row is a `fix` row whose diff touches a personal-only path or a path only a non-`fix` row creates.

Line-split table (new `CLASSIFICATION.md` section "Line-split", after Path-split):

| Commit | Path | Base blob | Left behind on `personal`: lines of `<sha>:<path>` | Carried |
|---|---|---|---|---|
| f4acc7d | `tests/test_agents.py` | `f772b07` (`c895ced`'s and `f4acc7d^`'s) | `661,674` (`    @staticmethod`, `def pic`, `test_pictures_become_data_uris_and_unusable_ones_are_left_out`, `test_at_most_three_pictures`, trailing blank line) and `763,769` (`test_a_tool_result_carries_its_pictures`, trailing blank line): 21 lines, the tests of `283432f`'s `tool_images` and `images` field | the other 301 added lines |

For `f4acc7d` the command is `git show f4acc7d:tests/test_agents.py | sed -e '661,674d' -e '763,769d' > tests/test_agents.py`. `89f4bfe` then applies as a plain pick over the shorter file. `283432f` stays off the branch, and nothing on the branch tests it.

**Coverage proof for `app/agents.py`**: Plan 1's Task 7 rerun on the tree this construction builds (it differs from Task 4's and the Ruled trial's, so the suite reruns). The first accepted command exits 0 with no failed test, and `node .github/ci/coverage-modules.mjs --report coverage.json` prints `meets 85` for `app/agents.py` lines and branches. The expected value is near Task 4's 100.00 lines and 97.14 branches (`CLASSIFICATION.md:308`); it is unmeasured. Plan 2's Task 2 repeats the gate on `macos-fixes`, whose tree equals the rerun's.

**Presence test** (Trial section, "Presence"): decides whether a `fix` row is on a branch. Replaces `git cherry ... -` as presence evidence at `CONTEXT.md:70-71`, `PLAN-2.md:27`, `PLAN-2.md:44`.

```
key(<sha>)      = git log -1 --format='%an%x00%aI%x00%s' <sha>
present(<sha>, <branch>) = exactly one line of `git log --format='%an%x00%aI%x00%s' <branch>` equals key(<sha>)
absent(<sha>, <branch>)  = no line equals key(<sha>), and `git cherry <branch> <snapshot>` prints `+ <sha>`
```

Every `fix` row, of every kind, is `present` on the built branch. `f3b2947` (class feature) is `present` through `8c064eb`. Every other `feature` row (`283432f`, `fb16e92`, `6537fdb`, `7a57ff3`; `CLASSIFICATION.md:34`, `:64`, `:77`, `:78`) and every `visual` row is `absent`. `commit -C` keeps the key of path-split, line-split and vehicle rows, and the five `present` fix rows and `f3b2947` match their `c895ced` copies.

**Merge-back prep** (Trial section, "Merge-back prep"): three commits on `personal` around the one merge of `macos`, so that merge has no conflict and `personal` ends with the tree it had before it. Replaces the "after the reorder, no conflict" lines at `PLAN-1.md:22`, `:61-62`, `:73-74`, `PLAN-2.md:30`, `:68`, `:74`, `CONTEXT.md:78-80`.

```
# R, Ignore reorder: after macos carries macos-fixes, before H (recipe below)
# H, Hold-back: on personal at R
git checkout macos -- <each Hold-back path>
git commit -m 'chore: take the Hold-back paths from macos for one merge; reverted right after it'
#   check: git show --stat --format= H lists the Hold-back paths alone;
#          git diff --name-only macos H -- <each Hold-back path> prints nothing
git merge macos          # personal at H; no conflict, git diff --name-only H personal prints nothing
git revert --no-edit H   # check: git diff --name-only R personal prints nothing
```

Hold-back paths (new `CLASSIFICATION.md` table "Hold-back", in Merge-back prep):

| Path | Personal-only lines it holds back |
|---|---|
| `app/server.py` | `fb16e92`'s two `VOICE_PROMPT` lines (`74af430:app/server.py:94-95`), after `e53ea7b`'s hover-off lines that both sides add |
| `tests/test_agents.py` | `f4acc7d`'s 21 Line-split lines (`74af430:tests/test_agents.py:663-676`, `:765-771`), inside the block both sides add |

H makes each Hold-back path equal on both sides, so the merge takes it unchanged; the revert puts back `personal`'s lines, and `personal`'s tree equals R's. The `tests/test_agents.py` conflict is predicted, not measured, and `tests/test_wake_loop.py` is predicted to merge cleanly once `89f4bfe` is on the branch; Plan 1's Task 7 trial merge proves both. A conflict on any path, Hold-back or not, is a stop. Plan 1's trial merges make R and H on their detached scratch worktree, with `split-trial` in place of `macos`, commit the trial merge there, revert H and check `git diff --name-only R HEAD`; none of it reaches `personal`.

**Ignore reorder** (R): one commit on `personal`, made after `macos` carries `macos-fixes` and before H. It touches `.gitignore` alone and changes line order only:

```
<the 8935491 block: "# macOS maintainer's todo list" through ".planning/reads.1.jsonl.evict.*",
 then a blank line, then "# Claude Code agent worktrees - each is its own git checkout", ".claude/worktrees/">
<blank line>
<lines from "__pycache__/" to end, byte-identical to `git show macos-fixes:.gitignore`>
```

Message: `chore: list personal-only ignores above the shared ones, so macos merges in cleanly`.

## Homes

| Concern | Home | Forbidden elsewhere |
|---|---|---|
| How a `fix` row becomes a commit | Row construction, `CLASSIFICATION.md` Trial section "Construction" | a plan restating a recipe; a per-row exception outside the five kinds; any branch line not from its own row's diff (or `8cacc1d`'s for the vehicle); `-m` on any merge but `8cacc1d`; any hand edit or conflict resolution |
| Which rows are path-split | `CLASSIFICATION.md` Path-split table | a plan or note enumerating path-split rows; a plan's lines cite the section |
| Which lines a line-split row leaves behind | `CLASSIFICATION.md` Line-split table | a plan or note restating a row's line ranges or base blob |
| Whether a row is on a branch | Presence test, `CLASSIFICATION.md` Trial section "Presence" | `git cherry` `-` as the sole evidence a `fix` row is present; a `+` read as absence of a `fix` row |
| Merge-back conflict prep | Merge-back prep (R, H, revert of H) and its Hold-back table, built by Plan 2 on `personal` under its `.gitignore`, `app/` and `tests/` leases | any other commit on `personal` touching `.gitignore` or a Hold-back path in this phase; Plan 1 committing to `personal`; any conflict resolution, `-s ours` or `-X` on the merge |
| What counts as "no changed file" | `git diff --name-only H <the merge>` after the merge, and `git diff --name-only R personal` after the revert of H | measuring from any commit before R |
| Owner rows | `CLASSIFICATION.md` Borderline section | Borderline rows for any construction above: the five kinds, R and H are technical and settled here |

`f3b2947` (Borderline B-06) is a `present` row: `c895ced` holds it as `8c064eb`. Its class is feature, and no build step picks, skips or reverts it.

## Order

1. Plan wording: the must-be-true, Action and Verify lines of Plan 1 and Plan 2 that name the kinds, the path-split list, the commit count, the presence exceptions and the merge-back; `CONTEXT.md` AC6; Plan 2's new Task 3b (H) and Task 5b (revert of H); Plan 2's Notes lease line, to cover `personal`. Writes `.planning/phases/2/PLAN-1.md`, `.planning/phases/2/PLAN-2.md`, `.planning/phases/2/CONTEXT.md`. Agent: the phase lead.
2. Classification text: `f4acc7d` and `89f4bfe` to class `fix`; the `0e6cd82` Path-split row; the Line-split section; the Construction text (five kinds, 94 commits); the Presence text; the Merge-back prep text with its Hold-back table; the B-08, B-09 and B-10 ruling text. Writes `.planning/phases/2/CLASSIFICATION.md`. Agent: Plan 1 executor.
3. Plan 1 Task 7 rerun and Task 8: Row construction on `c895ced`, the suite and per-module gate on its tree, the scratch merge-back with R and H then the revert of H, then removal. Writes `.planning/phases/2/CLASSIFICATION.md`. Agent: Plan 1 executor.
4. Plan 2 Tasks 1 to 3: build `macos-fixes` by Row construction, gate it, fast-forward `macos`. Writes `app/`, `bin/`, `tests/`, `.github/`, `packaging/`, `install.sh`, `install.ps1`, `.gitignore` on `macos-fixes` and `macos`. Agent: Plan 2 executor.
5. Plan 2 Task 3a: R on `personal`. Writes `.gitignore` on `personal`. Agent: Plan 2 executor.
6. Plan 2 Task 3b: H on `personal`. Writes `app/server.py`, `tests/test_agents.py` on `personal`. Agent: Plan 2 executor.
7. Plan 2 Tasks 4 and 5: trial merge and real merge of `macos` into `personal` at H. Writes no file. Agent: Plan 2 executor.
8. Plan 2 Task 5b: `git revert --no-edit H`; `git diff --name-only R personal` prints nothing. Writes `app/server.py`, `tests/test_agents.py` on `personal`. Agent: Plan 2 executor.
9. Plan 2 Task 6: worktree removal. Writes no file. Agent: Plan 2 executor.
