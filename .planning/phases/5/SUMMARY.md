---
phase: 5
status: complete
completed: 2026-11-08
---

# Phase 5: Own stop is echo - Summary

A stop phrase Void plays is recorded with its word times, on the native `Speaker` and on the page's player, and a heard "stop" within `ECHO_WORD` (0.60 s, measured with real Whisper) of one he played is dropped as echo. The owner's own stop, said just past that window, still barges him.

## What shipped

- Own-stop rule: `gate.Word`, `STOP_PHRASES`, `stop_phrases`, `stop_near`, `own_stop`, `judge(..., played=())`, and `ECHO_WORD = 0.60` - `app/gate.py` (`:30`, `:163`, `:168`)
- The played record: `PLAYED` and `PLAYED_LOCK`, with one writer (`note_played`), one reader (`played_lately`) and `played_cut` on a hush. The native `Speaker` notes each sentence at the chunk that starts its sound - `app/server.py:1488-1572`
- The page path: the `/api/speaking` post carries the sentence's text, played length and word times. `note_page_played` and `speaking_post` take them into the same record - `app/static/index.html`, `app/server.py:1525`, `:1540`
- Timed hearing: `Heard.words`. `Wake.heard`, `Wake.stop_in` and `Wake.check` judge timed words against `played_lately()`. Whisper asks for `word_timestamps` only when a burst falls near a played stop phrase (`run_whisper_heard`) - `app/server.py`
- Replay rows `OWN_STOPS` (8) - `tests/test_log_cases.py`. Scene clip `tests/fixtures/scenes/void_stop.wav` with word times in the manifest. Scenes on both paths, fast and slow tier - `tests/test_scenes.py:375-401`, `:617-636`
- Merged into `personal` (691f604) with no conflict. Nothing pushed. Build worktree `~/dev/void-own-stop` removed.

## Commits

| Plan | Task | Commit | Description |
|---|---|---|---|
| 1 | 1 | none | Build worktree opened at S = c2bf596. Baselines: macos 678 passed / 11 skipped, personal 700 / 11, slow tier 26 OK (1 expected failure) |
| 1 | 2 | 842c85d | gate judges a stop phrase Void played as echo |
| 1 | 3 | b5105ec | Own-stop rows in the replay table |
| 1 | 4 | 4f135fe | The server records when each of Void's stop phrases played |
| 1 | 5 | c17dc86 | The hearing callers judge timed words against the played record |
| 1 | 6 | 5daefee | Whisper times only a burst near a stop phrase Void played |
| 2 | 1 | ed2b892 | The page's `/api/speaking` post notes the sentence's stop phrases |
| 2 | 2 | 59ec78d | The page sends each sentence's text, length and word times |
| 2 | 3 | 7faa47b | A scene can play Void's line through the page's player |
| 3 | 1 | 64818a8, 4c338f1, dbbfaca | Clip of Void saying stop with its word times; text reworded twice |
| 3 | 2 | ca0367a | The scene harness times the words it hears, his and the owner's |
| 3 | 3 | 1fae58d | His own stop phrase heard back never stops him, both paths |
| 3 | 4 | 7c0c335 | The owner's stop just past ECHO_WORD still stops him, both paths |
| 3 | 5 | 7d847ba | Heard-minus-played offsets measured in every own-stop scene |
| 3 | 6 | 6f2f6e7, 2de8032 | Real Whisper confirms the offsets; ECHO_WORD set to 0.60 s |
| 4 | 1 | none | Gates on macos: 791 passed / 15 skipped (all slow tier); gate.py 99.27/97.92, hearing.py 98.59/89.29, drops.py 100/100 |
| 4 | 2 | 691f604 | Merge macos into personal: no conflict; personal 813 passed / 15 skipped |
| 4 | 3 | none | Build worktree removed; stream/stop-echo and stream/replies-after-quiet untouched |

Docs: 5ac57f1 (plan 2's lease widened to `tests/test_page_sound.py`, a declined plan-2 finding, cursor).

## Measured offsets

Each offset is the heard time minus the played time, in seconds, given as start / end, for Void's own stop phrases in the own-stop scenes (AC1). The values come from the final run with `ECHO_WORD` = 0.60 (plan 3, Tasks 5 and 6, `reports/plan-3.md`).

| Tier | Path | Phrase | Offsets (start / end) |
|---|---|---|---|
| Fast (fixture word times) | native | opening "Stop", closing "Stop" | +0.020 / +0.020 (peek, wake, over) |
| Fast (fixture word times) | page | opening "Stop", closing "Stop" | +0.020 / +0.020 (peek, wake, over) |
| Slow (real Whisper base.en) | native | opening "Stop" | -0.090 / +0.100 to +0.120 |
| Slow (real Whisper base.en) | native | closing "Stop" | -0.560 / -0.290, -0.540 / -0.350, -0.520 / -0.350 (peek); -0.540 / -0.350 (wake, over) |
| Slow (real Whisper base.en) | page | opening "Stop" | -0.060 / +0.090 to +0.130 |
| Slow (real Whisper base.en) | page | closing "Stop" | -0.530 / -0.300, -0.530 / -0.340, -0.510 / -0.340 (peek); -0.510 / -0.340 (wake, over) |

The fast tier's +0.020 is the room's delay. The largest |offset| of his own is 0.56 s (slow, native, closing phrase start). Rounded up to the next 0.05 s, that gives `ECHO_WORD` = 0.60 (`app/gate.py:30`). The owner's stop phrases in the AC2 scenes are not his own, so they are not counted. They land 0.72 s or more past the played phrase: fast +0.780 / +0.850 on both paths, slow native +0.930 / +1.080, slow page +0.720 / +0.830.

## Deviations

- [deviation] Plan 2, Task 2's first run stopped `blocked` on a lease gap. The page post's new keys broke the order assertion in `tests/test_page_sound.py`, which `PLAN-2.md`'s `files:` did not name. That path was added to the lease, and the re-run committed 59ec78d. The blocked run's report is kept as `reports/plan-2.1.md`.
- [deviation 2] Plan 3, Task 1/3: with the first fixture text, the first stop peek held three words ("Stop there. Your"), which `is_echo` drops by text, and the closing burst fell under `SPEECH_SHARE`. The line was reworded at 4c338f1 and dbbfaca, and again after real Whisper at 6f2f6e7. The text was the executor's to choose, and no criterion was redefined.
- [deviation 3] Plan 3, Task 2: the stand-in Whisper heard a 0.1 s slice of the owner as his whole "Stop, stop." with empty word times, and the page scene barged on that. `hear` now returns only the words the burst wholly holds for any clip with word times, so `hear` and `words` agree.
- [deviation] Plan 3, Task 1: piper re-renders move `you_stop.wav`'s word times by up to 0.06 s, so `--check` now compares each clip's `words` and `lead` against what `tidy_full` makes of the committed WAV. Fresh renders are still compared for frames.
- No context decision (D-NN) was refuted, so CONTEXT.md is unchanged.

## Open items

- `ECHO_WORD`'s 0.60 s is set by `tidy_full`'s drift on played times (closing phrase estimated 0.50-0.56 s late over a 7.9 s line), not by Whisper jitter. The drift grows with line length, so a line much longer than the fixture's could put his own closing stop outside the window (plan 3 report, open item 2).
- A hallucinated "stop" far from any played one still barges him. Real Whisper once heard "Absolutely, stop." as "Stop, absolutely. Absolutely." 1.08 s before any played stop. The fixture was reworded, and `ECHO_WORD` correctly does not absorb this (plan 3 open item 3).
- Page path: with no canceller reference, Void's uncancelled echo turns the owner's early cut-in down. The page-path stop scenes run the owner at +6 dB (`PAGE_STOP_DB`), a harness setting, not a gate change (plan 2 and plan 3 open item 1).
- Each risk review (plans 1-4) settled with nothing raised. Plan 3's and plan 4's came back after 5-6 tool calls. Plan 4's main question (lock discipline and the speaking post after the merge) was spot-checked by hand: every `PLAYED` access goes through the three locked functions (`app/server.py:1509`, `:1562`, `:1569`).

## Goal check

The commits deliver the phase goal. A played stop phrase is judged as echo by when its words played: `gate.own_stop` and `stop_near` (`app/gate.py:163`, `:168`) run against the `PLAYED` record (`app/server.py:1488`), which the native `Speaker` (4f135fe) and the page's `/api/speaking` post (ed2b892, 59ec78d) both fill. Criterion 1, his own stop heard back during the line or in the ring through `Wake.stop_in` and `Wake.check` does not stop him: `tests/test_scenes.py:375`, `:379` (fast) and `:617`, `:620` (slow, real Whisper). Each also reruns with `gate.own_stop` patched to False and shows a barge (plan 3 Task 3). Criterion 2, the owner's stop past `ECHO_WORD` stops him, and a measurement sets `ECHO_WORD`: `:397`, `:401`, `:633`, `:636`, and `ECHO_WORD = 0.60` at `app/gate.py:30`, from the largest measured own offset of 0.56 s rounded up (plan 3 Task 6). Criterion 3, both voice paths: every scene above has a native and a page twin. Criterion 4, the replay set still passes: plan 4 Task 2's run on `personal` after the merge gave 813 passed, 15 skipped (all slow tier), 0 failed, 0 xfail, against the `personal` baseline of 700 passed, 11 skipped. The weak spot is the length-dependent drift named in Open items, which a longer line could push past 0.60 s.

complete locally, not CI-verified
