---
phase: 4
status: complete
completed: 2026-11-08
---

# Phase 4: Replies after quiet - Summary

The native `Speaker` and the page's player now write to one server record of Void's sound (`Wake.talked`, plus `Wake.owed` for sentences handed over and not yet sounding). Echo is judged only on `Burst.rang`, and the page's single `sounding()` check reads the server's numbered copy of the record. All of this is ported from `stream/replies-after-quiet` onto `macos` and merged into `personal`.

## What shipped

- Spans hold only his sound; the 60 s and 0.8 s placeholder spans and `ECHO_TAIL` on spans are gone; `/api/speaking` takes `{on, left}`. See `app/server.py`.
- `Burst.rang`: echo is judged only when his voice or its ring was in the air, and `gate.judge` is the only place a drop is decided. See `app/gate.py`.
- `void drops` reads a logged burst's `rang` once and replays echo by it, so an echo drop the log cannot clear prints "as logged". See `app/drops.py`.
- `Wake.owed` beside `Wake.talked`, with owe and pay from the native `Speaker` and from page posts. The `t="voice"` event and the replies to `/api/say`, `/api/say/stop` and `/api/speaking` carry `left`, `owed` and `n`. See `app/server.py`.
- The page owes each sentence it is handed and pays each one it schedules or skips, with posts chained in order. Its one `sounding()` check (`handing > 0 || owed > 0 || end > now`) is what `untilQuiet`, `whenQuiet`, `followTry`, `heldTry` and `quietNative` wait on. A follow-up is held and sent once, after he finishes, and never shushes him. See `app/static/index.html`.
- Tests:
  - three echo scenes, a pause-hold scene and two stop scenes (`tests/test_scenes.py`, `tests/scenes.py`);
  - `tests/test_page_sound.py` (new) and `tests/test_page_held.py`;
  - `NativeOwed` and the record-event cases in `tests/test_wake_loop.py`;
  - the 23 Phase 4 rows in `tests/test_log_cases.py`, now passing with no mark.

## Commits

| Plan | Task | Commit | Description |
|---|---|---|---|
| 1 | 1 | - | Worktree `/Users/atom/dev/void-quiet` on `macos` (S = b457a58); baselines: `macos` 591 passed / 23 xfailed, `personal` 613 passed / 23 xfailed |
| 1 | 2 | 01d2024 | his spans hold his sound only, and the ring is not talking |
| 1 | 3 | 4f16da1 | echo is judged only when his voice or its ring was in the air |
| 1 | 4 | a491b09 | void drops reads a logged burst's rang once and replays echo by it |
| 1 | 5 | 7587534 | echo scenes through the real hearing path |
| 1 | 6 | 8e1642a | the record also holds the sentences he still owes |
| 1 | 7 | 715f524 | the server tells the page how long his sound runs and what he owes |
| 1 | 8 | defda1e | the Phase 4 marks come off every row the new code gets right |
| 2 | 1 | 1301c65 | page tells the server each sentence it is handed and each it schedules |
| 2 | 2 | 7873bef | one sounding() test reads the server's record of his sound |
| 2 | 3 | 48d172f | a follow-up waits until he has finished speaking and never shushes him |
| 2 | 4 | de50846 | a reply kept while his next sentence is made leaves his line playing |
| 2 | 5 | - | Gates on `macos`: 678 passed, 0 failed, 11 skipped (slow tier); coverage-modules exit 0 |
| 2 | 6 | 53baa07 | Merge `macos` into `personal`, no conflicts; on `personal` 700 passed, 0 failed, 11 skipped |
| 2 | 7 | - | Build worktree `/Users/atom/dev/void-quiet` removed |

Also committed on `personal`: fe86856 `docs(4): cursor after plan 1`. Plan 2 had stopped at Task 6 because the orchestrator's uncommitted STATE.md write left the tree dirty; fe86856 cleared it, and a fresh dispatch continued from Task 6.

## Deviations

None - plans executed as written. Both executors reported 0 deviations. Choices that went beyond the plan's wording:
- [beyond plan] A `hello` event resets the page's copy of the record. Without it, a restarted server that numbers `n` from 1 would be ignored. (7873bef)
- [beyond plan] `quietNative` re-checks `sounding()` every 150 ms before it clears `playing` and the face. (7873bef)
- [beyond plan] The pause-hold scene's reply has its own stand-in words. The recorded words of `you_answer.wav` appear in his question and were rightly dropped as echo; the words were changed, not the gate. (de50846)
- [beyond plan] `drops.replay` pairs a heard line with the first line that parses as a verdict, not with any next log line as the branch did. (a491b09)

## Open items

- Slow tier not run (it needs `VOID_SCENES=1` and real Whisper). `SlowScenes.test_answering_just_after_void_finishes_is_a_follow_up` is still a bare `expectedFailure`; with echo now judged on `rang` its result is unchecked.
- In `tests/test_log_cases.py` (defda1e), O-05 "I don't..." is the weakest restatement: the log line has no stamp and no flags, so it was restated as a follow with `rang` False. `Row.rang` defaults to True, so a future row with no evidence of being clear of him still runs the echo check.
- `lease-check` reads the plan from the cwd's `.planning/`, so both plans ran it from the worktree against a temporary copy of the plan file, which was never staged and was removed. This is Cadence friction for builds in a sibling worktree.
- `app/static/index.html` and `app/agents.py` still differ between `macos` and `personal` because of `personal`'s own earlier work; the Phase 4 code is present on both.
- No layer answers `review.triggers.risk_surface.surfaces`. This run passed all eight categories per check rather than saving a choice. Plan 2's range matched `untrusted_input` (a `JSON.parse` in the test fetch wrapper), and the blocking review returned 0 findings.
- Nothing is pushed. `origin/macos` (29e22ae) and `origin/personal` (9b309e0) are behind.

## Goal check

The commits plausibly deliver the goal and all four success criteria.
1. The replay rows: `tests/test_log_cases.py` went from 28 passed / 23 xfailed to 56 passed, and the three Phase 4 mark constants are gone (defda1e, plan-1 report Task 8). That includes "It's good" (O-24) and "Yes, do it" (O-23, O-25).
2. Echo during his line and in the ring: three echo scenes run through the real hearing path, with a mutation check showing the 1.5 s case depends on `gate.judge` (7587534). One check is missing: the slow-tier scene of the same case was not run.
3. A follow-up held until his line ends, while "stop" and "hey Void" still cut him off: the pause scene and the two stop scenes (de50846), plus `tests/test_page_held.py` (14 passed, two mutations caught, 48d172f).
4. One record:
   - `/api/speaking` passes only `now + left` or `now` to `talking_until`, with no literal span (Plan 2 Task 5, AC4 grep).
   - The page's waits all go through `sounding()`, and the plan's grep for waits on `playing`, `q.length` or `spkMap` matches nothing (7873bef).

The suite on `personal` after the merge: 700 passed, 0 failed, 11 skipped (slow tier), exit 0 (53baa07, plan-2 report Task 6). Nothing shows the page and native paths working together in a live session; that is for UAT.

complete locally, not CI-verified
