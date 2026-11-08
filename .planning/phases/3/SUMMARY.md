---
phase: 3
status: complete
completed: 2026-11-07
---

# Phase 3: Real-log replay - Summary

`void drops` now replays every judged burst of a real `server.log` through today's `gate.judge`. The owner's reported drops are a 43-row regression table in `tests/test_log_cases.py`: 20 rows pass today, and 23 are strict expected failures that name Phase 4.

## What shipped

- `.planning/phases/3/DROPS.md` - the owner's reported drops, mined from the real log. Each row gives the log line, the logged and today's verdict, a class, evidence, the expected verdict and the fixing phase (Plan 1)
- `void drops` prints every judged burst, kept as well as dropped, with today's verdict or "as logged" - `app/drops.py`, `bin/void`
- A determinism test showing one log replays to identical lines - `tests/test_drops.py`
- The regression table: `YOURS` extended with every owner row in `DROPS.md`, one test per row, and each failing row an `xfail(strict=True)` naming its phase - `tests/test_log_cases.py`
- Built on local `macos` (`77d89cc..98eac42`), merged into `personal` as `2552790`. Nothing was pushed: `origin/macos` is still `29e22ae` and `origin/personal` is still `9b309e0`

## Commits

| Plan | Task | Commit | Description |
|---|---|---|---|
| 1 | 1-3 | 001744b | DROPS.md: seeds, mined candidates, classes, expected verdicts and phases |
| 1 | 4 | 3f1dd05 | Owner's reply recorded on the 38 borderline rows; they move to an Unconfirmed table under Not his |
| - | - | b9de3a5 | Coordinator: cursor after plan 1, committed to clear the tree for task 7's merge |
| 2 | 1 | none | Build worktree `~/dev/void-replay` on `macos` |
| 2 | 2 | 77d89cc | `void drops` prints every judged burst, kept as well as dropped |
| 2 | 3 | d54b5db | Determinism test: one log replays to identical lines |
| 2 | 4 | 00326c0 | `YOURS` becomes the regression table, one test per row |
| 2 | 5 | 98eac42 | Owner's reported drops added to the table, marked by fixing phase |
| 2 | 6 | none | Gates on `macos`: full suite 591 passed / 11 skipped (slow tier) / 23 xfailed; coverage `app/drops.py` 100/100, `app/gate.py` 99.06/97.62 |
| 2 | 7 | 2552790 | Merge `macos` into `personal` |
| 2 | 8 | none | Build worktree removed |

## Deviations

- [coordinator] Plan 1 task 4: the owner was shown the 38 borderline rows and replied "....what? I'm not going through that nor do I remember". No borderline row was confirmed as his, so none became an owner row. All 38 are kept, with their evidence and lean, in an Unconfirmed table under Not his (`3f1dd05`)
- [coordinator] The mid-run cursor write left `.planning/STATE.md` modified and blocked plan 2 task 7's clean-tree precondition. It was committed as `b9de3a5` and the merge then ran

## Open items

- 38 unconfirmed drops (B-01 to B-38) are outside the regression set. The five leaning his (B-12, B-17, B-18, B-29, B-37) are the first to revisit if Phase 4 needs more cases
- Replay keeps the last `heard` line's flags until the next one, so a verdict line with no `heard` line of its own is judged with the previous burst's "while talking". About 14 kept "stops him" rows are affected, and drop rows were already judged this way before this phase. Not fixed
- Every failing row names Phase 4, and no row lands on Phase 5 or 6. Phase 5's own-stop cases and Phase 6's music cases will need rows of their own. One example: line 36666, where "Thank you for watching. Thank you" was kept as a follow-up, is a Phase 6 case and is not in the table
- D-10 seeds line 10475, but the evidence shows Void reading aloud, so it was filed as Not his (N-01)
- `history.jsonl` starts on 30 Oct 23:31, so it could not date the pre-stamp lines. Their rows rest on the log's neighbouring lines
- The full suite was not re-run after the merge. Task 6 ran it on the identical tree, and the two touched test files were re-run on `personal` (41 passed, 23 xfailed)

## Goal check

The commits deliver the phase goal. Criterion 1: `bin/void drops ~/.local/share/void/server.log` run twice gave byte-identical output (`cmp` silent, 126733 lines). Each row shows the text, the logged verdict and today's `gate.judge` verdict or "as logged" (`77d89cc`). `d54b5db` pins the determinism in a test that does not read the real log. Criterion 2: `uvx pytest tests/test_drops.py tests/test_log_cases.py -rxX` gives 41 passed and 23 xfailed, with 0 skipped. Every xfail reason opens with "Phase 4", including "It's good (over)", "Yes, do it (follow)" and "Yes, do it (wake)". "Yes, God damn" is O-15 (log line 15123) and passes today, because the voiceprint check that dropped it is gone. Plan 2 task 5 showed a strict xfail turns the run red when its row is set to today's verdict. `git diff c01be68 HEAD -- app/gate.py` is empty. The weakness is coverage of what the owner actually said. The set holds only drops the evidence could pin to him. The 38 he could not recall are left out, so the table under-states what Phase 4 must fix rather than over-stating it.

complete locally, not CI-verified
