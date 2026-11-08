---
phase: 5
plan: 1
requirements:
  - HEAR-03
  - HEAR-04
files:
  - app/gate.py
  - app/server.py
  - tests/fakes.py
  - tests/scenes.py
  - tests/test_gate.py
  - tests/test_log_cases.py
  - tests/test_echo.py
  - tests/test_wake_loop.py
---

# Phase 5: Own stop is echo - Plan 1: The own-stop rule, the played-words record and timed hearing on the native path

## Goal

Void's own stop phrase, heard back from his speakers, is dropped as echo by when its words played, timed on the Phase 4 record, and the owner's stop phrase said past `ECHO_WORD` still stops him. This plan does the gate rule, the server's record of the stop phrases Void played through the native `Speaker`, and the timed hearing that `Wake.stop_in` and `Wake.check` judge.

## Must be true when done

- A burst whose every heard stop phrase overlaps a stop phrase Void played, widened by `ECHO_WORD` on each side, is dropped by `gate.judge` as "echo" for every kind but `listen`. A burst holding one stop phrase that overlaps none of his still barges as it does today
- A sentence played through the native `Speaker` puts its stop phrases in the played-words record, timed from the moment `Wake.talked` records that sentence's first sound. Cutting him off (`Wake.hush`) removes every recorded stop phrase that had not yet started
- A burst whose span comes within `ECHO_WORD` of a stop phrase Void played is transcribed with word timestamps, and its `Heard.words` carry monotonic times. Every other burst is transcribed as today, with `Heard.words` None
- `Wake.heard`, `Wake.stop_in` and `Wake.check` hand `gate.judge` the burst's timed words and the played-words record, so his own "Stop." heard back while he plays never stops him, and the owner's "Stop" heard past `ECHO_WORD` does
- `tests/test_log_cases.py` has own-stop rows of its own, each setting `kind`, `talking` and `rang`, and all pass with no expected-failure mark

## Context

- Locked: D-01 (the rule, `gate.judge` the one drop, any stop phrase matches any other, `listen` exempt), D-02 (the clock is the Phase 4 record; nothing reads the played-words record for "is he talking"), D-03 (word timestamps only near a played stop phrase; `Wake.stop_in` moves to the timed form), D-06 (re-apply by hand onto `macos`, restated against Phase 4's code), D-07 (land on `macos`; `docs/superpowers/` and `.planning/` stay off it), D-08 (own rows set `kind`, `talking`, `rang`; hearing doubles only in `tests/fakes.py`).
- Source: the uncommitted diff in `/Users/atom/dev/void-stop-echo` (`git -C /Users/atom/dev/void-stop-echo diff`) and its design `/Users/atom/dev/void-stop-echo/docs/superpowers/specs/own-stop-design.md`. Read both; copy neither the design doc nor the 7 rewritten `you_*.wav` clips. The worktree's `Wake.session` `seg_at` plumbing and its page talking-flag hunks are already covered by Phase 4 (D-06), except as Task 5 states.
- Out of scope: `ECHO_TAIL`, `Wake.air`, `sounding()`, the page's hold, the replay's flag carry-over (`app/drops.py`), and the `~/dev/void-stop-echo` worktree and `stream/stop-echo` branch, which stay as they are.

## Tasks

### Task 1: Open the build worktree on `macos` and take the baselines

- **Files:** none (worktree and measurement only)
- **Action:** Record `S`, the output of `git rev-parse macos` at the start (`c2bf596` when this was planned). Create a worktree at `/Users/atom/dev/void-own-stop` with `macos` checked out. Every later task in all four plans works and commits there, on `macos`, until Plan 4 merges it. Do not use `/Users/atom/dev/void-stop-echo`, which is the source and stays untouched. Then take the baselines AC5 compares against. In the worktree, run both accepted commands from `.github/cadence/coverage-policy.json` verbatim, with `PYTEST_ADDOPTS="-rsxX"`. In `/Users/atom/dev/void` on `personal` (whose code is `bf7b120`'s, since `b1d4f12` is docs only), run the same pytest command. Then, in the worktree, run the slow scene tier once with `VOID_SCENES=1 OMP_NUM_THREADS=6 ~/.local/share/void/venv/bin/python -m unittest tests.test_scenes`, because Plan 3 adds real-Whisper scenes beside the existing ones and needs their prior state. Write into the task report the pass, fail, skip, xfail and xpass counts of each run, and the per-module coverage lines. Quote any failure with its shortest decisive line, as found before Phase 5. Each run holds a core for well over 10 s, and the slow tier runs Whisper on up to 6 threads (half of Slate's 12), so name each run before it starts. Never push.
- **Verify:** `git -C /Users/atom/dev/void-own-stop rev-parse --abbrev-ref HEAD` prints `macos`, and `git -C /Users/atom/dev/void-own-stop status --porcelain` is empty. The report holds `S`, the three runs' counts, and the coverage lines for `app/gate.py`, `app/hearing.py` and `app/drops.py`. Testing scope: no new test. The baseline runs are the evidence.

### Task 2: `gate` judges a stop phrase Void played as echo

- **Files:** app/gate.py (`STOP_RE`, `_STOP_WORDS`, `STOP_IN_RE`, `Burst`, `judge`), tests/test_gate.py
- **Action:** Re-apply the worktree's `app/gate.py` hunks by hand, restated against Phase 4's `gate`. Add the frozen `Word` (text, start, end, in monotonic seconds) and `ECHO_WORD`. Add `STOP_PHRASES`, the one list of stop phrases. `STOP_RE` is built from all of it and `STOP_IN_RE` from the clause subset that `_STOP_WORDS` names today. Each regex must match exactly the phrases it matches now. Add `stop_phrases`, which finds each run of consecutive words making up a stop phrase, case and punctuation aside, longest run first, as one `Word` from its first start to its last end. Add `stop_near`, true when a played stop phrase overlaps the span widened by `ECHO_WORD`. Add `own_stop`, true when the heard words hold a stop phrase and every one is near a played one. `Burst` gains the heard words as its last field, after `rang`, defaulting to None (not timed). `judge` gains the played stop phrases as a last argument defaulting to empty, so `app/drops.py` and every existing caller keep working unchanged. Step 2 drops as "echo" when `b.rang and is_echo(text, spoken)` holds, as today, or when the kind is not `listen` and the burst's timed words make `own_stop` true against the played stop phrases. The own-stop test is not gated on `rang`. D-01 states the rule on word times alone, and both records are timed from the same Phase 4 spans. `ECHO_WORD` takes the design's 0.5 s at this step. Plan 3 Task 6 sets it from the measured scenes (D-04), so no test or code may restate the number: read `gate.ECHO_WORD`. Keep `judge` the one place a burst is dropped. Port the worktree's `StopPhrases`, `StopNear`, `OwnStop`, `AnyStopMatches`, `OwnersStop` and `JudgeOwnStop` test classes into `tests/test_gate.py`, rewriting every "half a second" expectation in terms of `gate.ECHO_WORD`.
- **Verify:** `uvx --with-requirements tests/requirements.txt pytest tests/test_gate.py tests/test_log_cases.py tests/test_drops.py -rsxX` in the worktree passes. Among the passes:
  - a table test shows `STOP_RE.fullmatch` and `stop_said` give the same answers as at `S` for every alternative of the old `STOP_RE` and `_STOP_WORDS` alternations and for a few non-stop phrases;
  - `judge` drops a timed own stop as "echo" for `wake`, `follow`, `over` and `peek`, and not for `listen`;
  - an untimed burst, or one with nothing played, is judged as at `S`;
  - a played "stop" heard as "hold on" is his own;
  - a peek "Stop, stop" whose first word starts just past `ECHO_WORD` after his played stop phrase barges, while the same burst holding one stop phrase of his and that one of the owner's also barges;
  - an own stop on a burst with `rang` False is dropped as "echo".
  - `grep -n "0\.5" tests/test_gate.py` shows no new own-stop expectation written as a literal.
  Testing scope: these are the rule's outcomes and its one regression risk, the regex rebuild. The suite's existing `Judge` and `StopSaid` tests cover the unchanged steps. Stop there.

### Task 3: Own-stop rows in the replay table

- **Files:** tests/test_log_cases.py (`Row`, `burst`, `test_the_row_gets_the_verdict_the_owner_expects`)
- **Action:** Give own stop rows of their own (D-08), in a table beside `YOURS`. Each row carries the heard text, its heard words with times, the stop phrases Void played with times, `kind`, `talking`, `rang`, and the verdict it should get. The row type for this table has no default for `kind`, `talking` or `rang`, so a row cannot lean on `Row.rang`'s True default or on the replay's carried-over flags (Phase 3 SUMMARY, phase 3; Phase 4 SUMMARY, phase 4). Times are written relative to `gate.ECHO_WORD`, never as a literal width. The rows: his "Stop." heard as a peek while he talks; his "Stop." heard in the ring after, as `over` and as `follow`, with `talking` False and `rang` True; his "stop" heard as "hold on"; the owner's "Stop, stop." just past `ECHO_WORD` after his, as a peek; the owner's stop within `ECHO_WORD` of his, which counts as his under the reworded HEAR-04; a burst holding his stop and the owner's past `ECHO_WORD`; and push-to-talk "Stop" as `listen`. Each row is judged through `gate.judge` with its played stop phrases. No row carries an expected-failure mark. Leave `YOURS` and its rows untouched.
- **Verify:** `uvx --with-requirements tests/requirements.txt pytest tests/test_log_cases.py -rsxX` passes. Every new row is listed as passed, with no xfail or xpass among them. The existing rows' counts are as Task 1's `macos` baseline gave them. Constructing a row of the new type without `rang` raises `TypeError`. Testing scope: one row per D-01 and HEAR-04 outcome. The gate's own tests are Task 2's. Stop there.

### Task 4: The server records when each stop phrase of Void's played, on the native path

- **Files:** app/server.py (the `SPOKEN` / `note_spoken` / `said_lately` block, `Wake.hush`, `Speaker._write`, `Speaker._player_loop`), tests/test_wake_loop.py, tests/scenes.py (`play`'s per-scene patches)
- **Action:** Re-apply the worktree's played-words record: `PLAYED` with its lock, `note_played` as its one writer, `played_lately` as its one reader, and `played_cut`. `note_played` times each word of `langmark.unmark(text).split()` from a start plus that word's `[start, end]` pair, or spreads the words evenly over the sentence's length when there are no word times or their count differs. It keeps only `gate.stop_phrases` of the result. Entries that ended more than `ECHO_KEEP` ago are pruned on every write and read, so the record stays bounded. Restate the native anchor against Phase 4 (D-02). The worktree noted at `_player_loop`'s `start + LAT`, an estimate made before writing, which an underrun in `_write` can move. Instead, the sentence's start is the `at` of its first sound chunk, the chunk `_write` hands to `Wake.talking` with the sentence's `owe` pay. That is the moment `Wake.talked` records that sentence's sound starting. Pass the sentence's text and word times down so they are noted there, the re-opened-player retry in `_write` included. Nothing is noted for the silent pause write or for a sentence that never sounds. `Wake.hush(at)` calls `played_cut(at)` beside its trim of `talked`, so `Speaker.stop` and `Wake.barge` cut it too. `Wake.air`, `Wake.heard_him`, `span_at` and the gate's `talking`/`rang` keep reading `Wake.talked` alone. In `tests/scenes.py`, `play` gives each scene an empty played-words record, as it already does for `SPOKEN`, because every scene's clock starts at `T0` and must not hear another scene's stop phrases. Port the worktree's `Played`, `Hush` and `NativePath` classes into `tests/test_wake_loop.py`, restated to the first-chunk anchor.
- **Verify:** `uvx --with-requirements tests/requirements.txt pytest tests/test_wake_loop.py tests/test_scenes.py -rsxX` in the worktree passes, with the fast scene tier counts as in Task 1's baseline. Among the passes:
  - a sentence holding "stop", played through `Speaker` to a fake player, leaves one played phrase whose start equals that sentence's first-chunk time in `Wake.talked` plus the word's offset;
  - a sentence with no stop phrase leaves nothing;
  - entries older than `ECHO_KEEP` are gone after either call;
  - `Wake.hush(at)` and `Speaker.stop()` remove the entries starting at or after the cut and keep the earlier ones.
  `git grep -n "PLAYED\|played_lately" app/server.py` shows no reader in `Wake.air`, `heard_him`, `span_at` or `speaking`. Testing scope: the record's write, prune, cut and anchor. The callers are Task 5's. Stop there.

### Task 5: The hearing callers judge timed words against the played record

- **Files:** app/server.py (`Heard`, `transcribe_pcm_heard`, `Wake.session`, `Wake.heard`, `Wake.stop_in`, `Wake.check`), tests/fakes.py (`heard`, `ears`), tests/test_echo.py, tests/test_wake_loop.py
- **Action:** Wire the whole native path end to end, with Whisper's word times stood in by `tests/fakes.py` until Task 6 makes them real. `Heard` gains `words`, the heard words as `gate.Word`s in monotonic seconds, defaulting to None. `transcribe_pcm_heard` takes `at`, when the clip's first sample was caught. Every transcription in `Wake.heard`, `Wake.stop_in` and `Wake.check` goes through `transcribe_pcm_heard` with `at` and the arguments each uses today (D-03: `Wake.stop_in` moves off the untimed `transcribe_pcm` onto `transcribe_pcm_heard`; no `transcribe_pcm(` call is left in `Wake`). `Wake.heard` hands back its `Heard`, or None when it had too little speech, and `Wake.session` reads `.text` for its `WAKE_RE` test and hands the `Heard` to `Wake.check` in place of its text. `Wake.check` judges the words of the `Heard` it is given, and still transcribes a `follow` burst itself as today. A follow-up's `Burst.heard` stays as today, and only the follow kind carries it. Each caller builds its `Burst` with the heard words after `rang` and calls `gate.judge(burst, said_lately(), CFG, played_lately())`. `Listen.run` keeps `transcribe_pcm` and passes nothing played. Word times must count from the clip's first sample. `Wake.check` already gets that as `at`, plus the bytes `ran_on` cut off its front. `Wake.heard` and `Wake.stop_in` get only `started` today, which is when the burst was detected, after the pre-roll in `seg`. So `Wake.session` also hands them its `seg_at`. `started` keeps feeding `Wake.air`. This one piece of the worktree's `seg_at` plumbing is still needed after Phase 4. In `tests/fakes.py`, `heard` takes `words`, and `ears` takes a `words_for(pcm, at)` that its `transcribe_pcm_heard` calls when given `at`. With `words_for` None, every `Heard` has `words` None, so every existing caller of `ears` is unchanged. Port the worktree's `OwnStop` and `Callers` classes in `tests/test_echo.py` and its caller tests in `tests/test_wake_loop.py`, restated to `rang` and the Phase 4 `Burst`.
- **Verify:** `uvx --with-requirements tests/requirements.txt pytest tests/test_echo.py tests/test_wake_loop.py tests/test_gate.py tests/test_scenes.py -rsxX` in the worktree passes. Among the passes, through `Wake.session` or the callers with `fakes.ears` and a `words_for`:
  - his "Stop." heard back while a played "stop" is in the record is judged "echo (peek)" and "echo (over)", and no `barge` event is published;
  - the same in the ring after his sound ends, judged by `Wake.check`, publishes no `wake` event;
  - the owner's "Stop, stop" whose first word starts just past `ECHO_WORD` after his played stop barges, both mid-burst through `Wake.stop_in` and once heard out through `Wake.check`;
  - `Wake.heard` returns a `Heard`, and `Wake.check` given it judges its words without transcribing again;
  - the `at` each caller passes equals the burst's `seg_at`, plus the cut bytes' length for `check`.
  `git grep -n "transcribe_pcm(" app/server.py` shows no call left in `Wake`. Testing scope: the wiring of each caller, and the rule end to end through the native path with doubled Whisper. Whisper's own timing is Task 6's. Stop there.

### Task 6: Whisper times only a burst that comes near a stop phrase Void played

- **Files:** app/server.py (`run_whisper_heard`, `transcribe_pcm_heard`), tests/test_echo.py
- **Action:** `run_whisper_heard` takes `words` and passes it to faster-whisper as `word_timestamps`. When on, `Heard.words` holds the kept segments' words as `gate.Word`s, times relative to the clip. When off, `Heard.words` is None. `transcribe_pcm_heard`, given `at`, asks for word times only when `gate.stop_near(played_lately(), at, at + the clip's length)`. It then shifts each word time by `at` to monotonic seconds. Without `at`, or with no played stop phrase near, it runs Whisper exactly as today. The under-0.3 s early return keeps `words` None. Word-timing every burst was rejected for its Whisper cost on Slate (D-03), so nothing else may turn `word_timestamps` on. `word_timestamps` appears nowhere but `run_whisper_heard`, and the shift to monotonic time happens nowhere but `transcribe_pcm_heard`. Port the worktree's `HeardWordTimes` class, with its `TimedWord`/`TimedSeg` stand-ins for faster-whisper's segments, which patch the model object the way `tests/test_echo.py`'s `Sure` class already does.
- **Verify:** `uvx --with-requirements tests/requirements.txt pytest tests/test_echo.py tests/test_wake_loop.py -rsxX` in the worktree passes. Among the passes (AC4):
  - a burst near no played stop phrase is transcribed with `word_timestamps` False and `Heard.words` None;
  - a burst overlapping one, or whose end comes within `ECHO_WORD` of one, is transcribed with `word_timestamps` True and its kept words at `at` plus Whisper's times;
  - words of segments `gate.sure` drops are not in `Heard.words`;
  - a call without `at` is untimed.
  `git grep -n "word_timestamps" app/` lists only `run_whisper_heard`. Testing scope: the timing decision and the shift, on stand-in segments. Real Whisper is measured in Plan 3. Stop there.

## Notes

- Four plans, run in order (SEQUENTIAL: they share `app/server.py`, `app/gate.py`, `tests/scenes.py`, `tests/test_scenes.py` and `tests/test_wake_loop.py`). Plan 1: rule, record, native hearing. Plan 2: the page path and a page-player scene mode. Plan 3: the own-stop scenes, the measurement and `ECHO_WORD`. Plan 4: gates, merge into `personal`, worktree removal. The CONTEXT plan shape named three slices. The fourth plan exists because Plan 3's six scene and measurement tasks, plus the gates, merge and worktree removal, exceed the 8-task ceiling for one plan.
- Choice (D-01, planner's discretion): the own-stop test in `judge` step 2 is not gated on `rang`, while `is_echo` stays gated on it as Phase 4 left it. D-01 defines own stop by word times alone. Gating it on `rang` too would add a condition D-01 does not state, and would miss a heard stop that Whisper times just before his played one.
- Choice (D-02): the native anchor is the first sound chunk's `at`, not the worktree's `start + LAT`, so that the played record and `Wake.talked` cannot disagree after an underrun.
- Choice: `Wake.heard` hands back its `Heard`. CONTEXT names `Wake.stop_in` and `Wake.check`. But a burst begun over him and heard out after he stops goes `Wake.heard` → `Wake.check` with the text alone, and would reach step 3 untimed and barge, failing AC1.
- Task 5 also hands `seg_at` to `Wake.heard` and `Wake.stop_in`. D-06 counts the worktree's `seg_at` plumbing as covered by Phase 4, but Phase 4 passes them `started`, which lies after the pre-roll and would put every timed word late.
- Re-applied work gets new SHAs on `macos`. Commit subjects say what changed, in this repo's `hearing:` style. Nothing is pushed.
