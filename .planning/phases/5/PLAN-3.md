---
phase: 5
plan: 3
requirements:
  - HEAR-03
  - HEAR-04
files:
  - tests/make_scenes.py
  - tests/fixtures/scenes/void_stop.wav
  - tests/fixtures/scenes/manifest.json
  - tests/scenes.py
  - tests/test_scenes.py
  - app/gate.py
---

# Phase 5: Own stop is echo - Plan 3: Scenes of Void saying stop, measured, set `ECHO_WORD`

## Goal

Through the real hearing path, on both the native `Speaker` and the page's player, Void's own stop phrase heard back never stops him, and the owner's stop said just past `ECHO_WORD` after his does. `ECHO_WORD` is the measured value, not the design's guess.

## Must be true when done

- On both voice paths, Void's line holding stop phrases is heard back while it plays and in the ring after. Both bursts pass through `Wake.stop_in` and `Wake.check`, his line plays to its last chunk, and no Claude turn starts (AC1)
- On both voice paths, the owner's "Stop, stop." whose first word begins just past `ECHO_WORD` after the end of Void's played stop phrase stops his playback before his line ends (AC2)
- The heard-versus-played offsets of Void's stop phrases are measured in the own-stop scenes, from the fixture's word times and through real Whisper. `ECHO_WORD` in `app/gate.py` is no smaller than the largest of them, and a test fails if it ever is (AC3)
- Every existing clip under `tests/fixtures/scenes/` is byte-identical. The phase adds only the new Void clip and word-time keys in `manifest.json`

## Context

- Runs after Plans 1 and 2, in `/Users/atom/dev/void-own-stop` on `macos`. Uses Plan 1's `gate.stop_phrases`, `Burst` words, `played_lately` and `fakes.ears`' `words_for`, and Plan 2's page-path choice in `scenes.play`.
- Locked: D-04 (`ECHO_WORD` from measured scenes, fixture word times then real Whisper; a stop within `ECHO_WORD` of his counts as his; `ECHO_TAIL` stays 1.0 s), D-08 (scenes through the real hearing path on both voice paths; hearing doubles only in `tests/fakes.py`), D-09 (existing clips byte-identical; short phrases only; the worktree's rewritten `you_*.wav` not copied).
- Source: the worktree's `tests/make_scenes.py`, `tests/scenes.py` and `tests/test_scenes.py` hunks, and the design's sections on `tests/make_scenes.py` and `tests/scenes.py`. The worktree times only the owner's clips and leaves `void_from`, Void's word times and `void_stops` unbuilt.
- Fixtures are written only with `~/.local/share/void/venv/bin/python tests/make_scenes.py`. Real-Whisper scenes run with `VOID_SCENES=1`.

## Tasks

### Task 1: The new clip of Void saying stop, with its word times

- **Files:** tests/make_scenes.py (`VOID_LINES`, `SCENES`, `generate`, `check`), tests/fixtures/scenes/void_stop.wav, tests/fixtures/scenes/manifest.json
- **Action:** `VOID_LINES` gains `void_stop.wav`: a short Void line, written so that the scenes can test the rule rather than the text-echo check. It opens with a stop phrase heard on its own, in fewer than `gate.ECHO_MIN` words, the case `is_echo` never judges (D-01). It runs on for at least 4 s after that phrase, so an owner's cut-in past `ECHO_WORD` can stop him before the line ends, whatever value Task 6 measures. It ends on a stop phrase. Beyond the stop phrases, it shares no word with `you_stop.wav`'s text, so `is_echo` cannot take the owner's words for his (Phase 4 SUMMARY, de50846, phase 4). `SCENES` gains the line alone and the line with `you_stop.wav`. Add `clip_words` as the design gives it. It returns each word's `[start, end]` from the clip's first sample, and the lead `server.tidy_full` trims. It finds the lead by locating the trimmed samples inside the WAV it gave `tidy_full`, never by re-deriving `tidy_full`'s threshold, and it raises when the word times are None, their count differs from the text's, or the slice is not found. The manifest gets `"words"` and `"lead"` for `void_stop.wav`, and `"words"` for `you_stop.wav`, the owner clip whose first word places the AC2 cut-in. Every other clip's entry is unchanged. Time `you_stop.wav` from the committed WAV file itself, not a fresh render: piper does not reproduce its bytes, and D-09 keeps them. Writing the fixtures must leave every existing WAV byte-identical, so the generator gains whatever flow writes only the new clip and the manifest keys. Overwriting the clips and then checking them back out is not that flow. `--check` compares each clip's `"words"` and `"lead"` as it compares frames. For a fresh render that is not byte-identical (piper's clips), word times are compared within one `tidy_full` analysis step, a tolerance named in the code. The generator loads Kokoro and piper and holds a core for well over 10 s, so name each run before it starts.
- **Verify:** In the worktree, `~/.local/share/void/venv/bin/python tests/make_scenes.py --check` exits 0, with every clip `ok`. `git status --porcelain tests/fixtures/scenes/` shows only `void_stop.wav` added and `manifest.json` modified. `git diff S --stat -- 'tests/fixtures/scenes/*.wav'` lists no existing WAV. `git diff S -- tests/fixtures/scenes/manifest.json` adds only the new clip's entry (`words` count equal to its text's word count, plus `lead`), `you_stop.wav`'s `words`, and the two new scenes. `gate.stop_phrases` over the new clip's timed words finds a phrase ending before its first second and one ending its last word, at least 4 s apart. Testing scope: the fixture and `--check`. The scenes are Tasks 3 and 4. Stop there.

### Task 2: The scene harness times the words it hears, his and the owner's, on both paths

- **Files:** tests/scenes.py (`_texts`, `_whisper`, `Scene`, `FakePlayer.write`, `play`, the page-path actor), tests/test_scenes.py
- **Action:** Re-apply and finish the design's harness section. `_clips` becomes the one reader of `manifest.json`'s clips, and `_texts`, `_words` and `_leads` read through it. Add `Scene.void_from`: the scene sample at which the first sample Void's player writes comes out of the speakers, set once. On the native path that is the start of the first run of the scene's first `FakePlayer`. On the page path it is where the page-path actor puts the trimmed audio. It is not `void_start`'s first loud sample. Add `void_stops(name)`: each stop phrase of Void's clip `name` as `(start, end)` seconds after his voice starts coming out of the speakers, from the clip's `"words"` less its `"lead"`, grouped by `gate.stop_phrases`. `_whisper` returns a third stand-in, `words(pcm, at)`, which `play` hands to `fakes.ears` as `words_for`. It times exactly the words `hear` returns for the burst. When the owner wins the burst, it times the owner's kept words wholly inside the burst, at `at + (you_from / SR + start - a / SR)`. When Void wins, it times his words wholly inside it, at `at + (void_from / SR + start - lead + room.delay - a / SR)`. It returns None when the music or no one wins, when the winner's clip has no `"words"`, and for Void after a speaker switch. With `you_only`, the owner's words are the clip's opening words. One change goes past the design: when Void wins and his clip has `"words"`, `hear` returns only his words lying in the burst, as real Whisper hears only what the burst holds. The design returned his whole line, which `is_echo` would drop by text before `own_stop` was ever asked. A clip without `"words"` (`void_question.wav`) is heard exactly as today, so every existing scene hears what it heard at `S`. No word time is estimated in `tests/scenes.py`, and it never calls `tidy_full`.
- **Verify:** `uvx --with-requirements tests/requirements.txt pytest tests/test_scenes.py -rsxX` in the worktree passes, with every scene that passed in Plan 2 Task 3 still passing. Among the passes, new harness tests show:
  - `void_stops("void_stop.wav")` equals the manifest's grouped stop-phrase times less `"lead"`;
  - on both paths, a scene of the new line alone records `void_from`;
  - its `words` stand-in returns, for a burst over his first stop phrase, that phrase's words in order, inside `[at, at + burst length]`, while `hear` returns those same words and not the whole line;
  - `void_question.wav`'s scenes get `words` None.
  Testing scope: the stand-in's timing on the clips that have word times. The rule's outcomes are Tasks 3 and 4. Stop there.

### Task 3: His own stop phrase heard back never stops him, on both paths

- **Files:** tests/test_scenes.py
- **Action:** Add fast-tier scenes of the new line alone, one per voice path (AC1). On the native path, his echo must actually reach the hearing path, so run as the overlap scenes do with the canceller off (`server.hearing.rtc` None). Otherwise the warm canceller removes him and the scene proves nothing. The page path gives the canceller no reference, as in the app. Each scene asserts four things. A `Wake.stop_in` peek on a burst holding his opening stop phrase is judged "echo (peek)". A burst holding his closing stop phrase, whose words end within `ECHO_TAIL` after his sound ends, is judged by `Wake.check` and dropped as "echo". No `barge` and no `wake` event is published. His sound plays to his line's last chunk. Each scene also runs once more with `gate.own_stop` patched to return False, and that run must show a `barge`, which proves the rule is what holds him. The pattern follows Phase 4's echo scenes, where his own line heard 0.5 s after his sound ends was dropped (Phase 4 UAT, phase 4).
- **Verify:** `uvx --with-requirements tests/requirements.txt pytest tests/test_scenes.py -rsxX -k "own"` (or the names chosen) in the worktree passes both scenes, and the whole file passes. Each scene's failure message prints `instead(t, log)`. With `own_stop` patched False, both paths show a `barge`. Testing scope: AC1 on both paths, plus the one mutation that shows the rule decides. Stop there.

### Task 4: The owner's stop just past `ECHO_WORD` still stops him, on both paths

- **Files:** tests/test_scenes.py
- **Action:** Add fast-tier scenes of the new line with the owner's "Stop, stop." (`you_stop.wav`'s opening, through `you_only`, its length taken from that clip's `"words"`), one per voice path (AC2). The cut-in is placed from `scenes.void_stops` and `scenes._words`, never from a hand-written time. The owner's first word begins `gate.ECHO_WORD` plus a stated margin of at most 0.1 s after the end of Void's opening played stop phrase, so his line is still playing. Each scene asserts that a `barge` event comes, that his playback ends before his line ends, that the placement on the scene's clock is past `ECHO_WORD`, and that the burst that barged was judged with timed words. The last assertion means the owner's stop reached the rule and was found not his.
- **Verify:** `uvx --with-requirements tests/requirements.txt pytest tests/test_scenes.py -rsxX` in the worktree passes, the new scenes included. Each asserts `t.void_end - t.void_start` below his line's played length. Placing the cut-in inside `ECHO_WORD` instead (a local check, not committed) turns the barge into an echo drop. Testing scope: AC2 on both paths. Stop there.

### Task 5: The heard-versus-played offsets are measured in every own-stop scene

- **Files:** tests/scenes.py (`play`, `Take`), tests/test_scenes.py
- **Action:** `play` records, on its `Take`, every timed stop phrase the hearing judged: each heard stop phrase, and the nearest stop phrase in `played_lately()` at that moment, as the heard-minus-played start offset and end offset in seconds. It gets them by observing `gate.judge`'s calls through a call-through wrapper, which changes no verdict and is not a hearing double. The AC1 scenes on both paths assert that at least one offset of his own was measured, and the task report lists every offset by scene and path for the phase SUMMARY (AC3). The fast tier's offsets come from the fixture's word times (D-04). They carry the room's delay and the difference between the server's trim and the fixture's `"lead"` (CONTEXT's third flagged assumption).
- **Verify:** `uvx --with-requirements tests/requirements.txt pytest tests/test_scenes.py -rsxX` in the worktree passes. A test asserts that each AC1 scene's `Take` holds at least one offset pair for each path. The task report holds the table of offsets. Testing scope: the measurement exists and is not empty. Its use is Task 6's. Stop there.

### Task 6: Real Whisper confirms the offsets, and `ECHO_WORD` is set from them

- **Files:** tests/test_scenes.py (`SlowScenes`), app/gate.py (`ECHO_WORD`)
- **Action:** Add slow-tier runs of the Task 3 and Task 4 scenes on both paths to `SlowScenes`, hearing with real speech detection and Whisper, with Plan 1 Task 6's word timing (D-04). Run the slow tier with `VOID_SCENES=1 OMP_NUM_THREADS=6 ~/.local/share/void/venv/bin/python -m unittest tests.test_scenes -v`. That is half of Slate's 12 cores, held for minutes, so name it before it runs and check with `ps` that it stays within 6 cores. Collect the offsets of both tiers and both paths. Set `ECHO_WORD` to the largest absolute offset, rounded up to the next 0.05 s, and state that rounding in the comment beside it. Add, in both tiers, an assertion that `gate.ECHO_WORD` is no smaller than every offset the scene measured, so a later change that widens the offsets fails the suite. The scenes and the value land in one commit: the real-Whisper scenes are only green once the value is set from them. If the measured value leaves Task 4's cut-in no room before the line ends, or if real Whisper's offsets on the owner's stop and his own overlap so that no value separates them, stop and report it with the numbers. Do not lengthen the line or widen a scene silently.
- **Verify:** The slow-tier command exits 0, with every `SlowScenes` test that passed in Plan 1 Task 1's slow baseline still passing, and the new own-stop scenes passing on both paths. `uvx --with-requirements tests/requirements.txt pytest tests/test_scenes.py tests/test_gate.py tests/test_log_cases.py tests/test_echo.py -rsxX` passes with the new value. The report lists every offset (fast and real Whisper, both paths, start and end), the largest, and the value set (AC3). `git diff S -- app/gate.py` shows `ECHO_TAIL` unchanged. Testing scope: the real-Whisper confirmation and the guard on the value. Stop there.

## Notes

- Plans run in order; this one shares `tests/scenes.py`, `tests/test_scenes.py` and `app/gate.py` with Plans 1 and 2.
- Choice (D-09): "its word-time keys" is read as the word-time keys the new scenes read. Those are the new clip's `"words"` and `"lead"`, and `you_stop.wav`'s `"words"`, without which the AC2 cut-in could not be placed from a measured word start. No existing WAV changes. If D-09 means the new clip's keys alone, AC2's placement has no source, so this is surfaced rather than worked around.
- Choice: the new line's text is the executor's. Its constraints are fixed in Task 1 so the scenes test `own_stop` and not `is_echo`, and so AC2 has room.
- Choice: Task 6 joins the real-Whisper scenes and the value, because neither can be committed green without the other. `ECHO_WORD` is rounded up to 0.05 s above the largest measured offset. A larger margin would let more of the owner's stops count as Void's (HEAR-04).
- Footprint: Task 1 loads Kokoro and piper, and Task 6 runs Whisper scenes on up to 6 threads. Every other task runs one test file. Name each heavy run before it starts.
