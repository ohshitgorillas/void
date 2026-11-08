# Phase 5: Own stop is echo - Context

Gathered: 2026-11-08
Feeds: /cad-plan 5

## Scope boundary

In: the own-stop rule in `gate.judge`. A heard stop phrase that overlaps one Void played is dropped as echo; the
owner's stop phrase past `ECHO_WORD` still barges. Also in: a record of when Void's words played, timed from the
Phase 4 record on both the native `Speaker` and the page's player; Whisper word timestamps for bursts near a played
stop phrase, with `Wake.stop_in` and `Wake.check` judging timed words; `ECHO_WORD` set from measured scenes; own-stop
regression rows and scenes on both voice paths. The design (`~/dev/void-stop-echo/docs/superpowers/specs/own-stop-design.md`)
and the worktree's uncommitted code are re-applied onto local `macos` and merged into `personal`.
Out: music and other voices (Phase 6); changing `ECHO_TAIL`; word-timing every burst; any change to the Phase 4 record's
"is he making sound" readers (`Wake.air`, `sounding()`, the page's hold); fixing the replay's carry-over of the last
`heard` line's flags; removing or committing the `~/dev/void-stop-echo` worktree or `stream/stop-echo`; pushing any
branch.
Deferred: None
Plan shape: multiple plans, same phase - /cad-plan breaks it down (e.g. the gate rule and the server's played-words
record first, then the page path, then the measured scenes that set `ECHO_WORD`).

## Durable decisions

- D-01 (Rule): A stop phrase heard in a burst is Void's own when every stop phrase in the burst overlaps a stop phrase
  Void played, widened by `ECHO_WORD` on each side. `gate.judge` drops it as echo, and stays the one place a burst is
  dropped. Any stop phrase matches any other: his "hold on" heard as "stop" is still his. One heard stop phrase that
  overlaps none is the owner's, and the burst barges as today. Push-to-talk (`listen`) is exempt. The rule is needed
  because a short "Stop." Void plays is under `ECHO_MIN` words: `is_echo` never judges it, so it reaches step 3 and
  barges. Phase 4's `Wake.talked`/`rang` say only that his sound was in the air, not which words. Technical call under
  the 26 Oct ruling, confirmed by the owner 2026-11-08. Evidence: `own-stop-design.md:21`; `app/gate.py:27`
  (`ECHO_MIN=3`), `app/gate.py:139-145`; HEAR-03, HEAR-04.
- D-02 (Clock): The time Void's words played is anchored on the Phase 4 record. A sentence's word offsets count from
  the moment `Wake.talked` records that sentence's sound starting, on both voice paths. There is no second clock of his
  sound, and nothing reads the played-words record for "is he talking": `Wake.air` and the gate's `talking`/`rang`
  still read `Wake.talked` alone. Technical call, confirmed by the owner 2026-11-08. Evidence: Phase 4 D-01, D-10;
  `app/server.py:1508-1625` (`talked` spans, no words); `app/server.py:1472-1484` (`SPOKEN` text only, stamped at queue
  time); ROADMAP Phase 5 goal ("on the Phase 4 record").
- D-03 (Heard word times): Whisper runs with word timestamps only for a burst whose span comes near a stop phrase Void
  played; every other burst stays untimed, as today. `run_whisper_heard` and `transcribe_pcm_heard` gain the timed
  form, and `Wake.stop_in` moves from untimed `transcribe_pcm` to it. Word-timing every burst was rejected for its
  Whisper cost on Slate. Technical call, confirmed by the owner 2026-11-08. Evidence: `own-stop-design.md:72`;
  `app/server.py:1084`, `:1130`, `:1804-1815`.
- D-04 (`ECHO_WORD`): `ECHO_WORD` is set from measured scenes, not the design's unmeasured 0.5 s. Scenes with fixture
  word times measure Void's heard-versus-played stop-phrase offsets, and a scene through real Whisper confirms them.
  The offsets and the chosen value are recorded in the phase SUMMARY. A stop the owner says within `ECHO_WORD` of Void's
  own counts as Void's (HEAR-04 reworded to match, 2026-11-08). `ECHO_TAIL` stays 1.0 s. Evidence:
  `own-stop-design.md:23` ("none of these is measured"); ROADMAP Phase 5 criterion 2; `app/gate.py:25`;
  `.planning/REQUIREMENTS.md` HEAR-04.
- D-05 (Page path): The page's player reports each sentence's played words on the same `/api/speaking` post that
  starts that sentence's sound in the record (Phase 4 D-10's `{"on": true, "left": s, "paid": 1}`). The design's
  separate `POST /api/played` is not built. `sounding()` and the page's hold are unchanged. Technical call, confirmed
  by the owner 2026-11-08. Evidence: `app/server.py:3941-3957` (`/api/speaking`); `app/static/index.html:1859-1871`,
  `:1889` (`pump`); `own-stop-design.md` "Page path".

## Decisions

- D-06 (Starting point): The worktree's design and code are the source. They are re-applied by hand onto local `macos`,
  not merged or patched, and restated against Phase 4's code: `gate.Burst` now ends `kind, talking, rang`, so the new
  words field follows `rang`; `judge`'s echo step is gated on `rang`; `Wake.hush(at)` trims `talked` and zeroes
  `owed`, so the played-words cut hangs off it; `Wake.check` already takes `at` and classes by burst start. The
  worktree's `Wake.session`/`seg_at` plumbing and its page talking-flag hunks are dropped as already covered by
  Phase 4. Evidence: `git apply --check` of the worktree diff fails in `app/gate.py`, `app/server.py`,
  `app/static/index.html`, `tests/scenes.py`, `tests/test_echo.py`, `tests/test_scenes.py`, `tests/test_wake_loop.py`;
  `app/gate.py:39-50`; `app/server.py:1650-1660`, `:1841-1895`; `app/static/index.html:1859-1871`.
- D-07 (Landing): Code and tests land on local `macos` first and reach `personal` by merging `macos`. The design doc,
  `docs/superpowers/` and `.planning/` stay off `macos`. Nothing is pushed. Evidence: Phase 2 D-02, D-03, D-04;
  Phase 4 D-05.
- D-08 (Tests): Own stop gets rows of its own in `tests/test_log_cases.py`, each setting `kind`, `talking` and `rang`
  explicitly instead of relying on `Row.rang`'s default or the replay's flag carry-over. Scene cases go through the
  real hearing path in `tests/scenes.py` on both the native `Speaker` and the page's player. Test doubles live only in
  `tests/fakes.py`, and page tests run on installed Chrome. Evidence: Phase 3 SUMMARY (no row assigned to Phase 5;
  replay flag carry-over); Phase 4 SUMMARY (`Row.rang` defaults True); `tests/test_log_cases.py:46-62`.
- D-09 (Fixtures): The existing clips under `tests/fixtures/scenes/` stay byte-identical. The phase adds only the new
  clip of Void saying stop and its word-time keys in `manifest.json`. The worktree's 7 rewritten `you_*.wav` clips are
  not copied. Committed test data carries short phrases only. Evidence: worktree `git status` (7 modified
  `you_*.wav`, `manifest.json`); Phase 4 SUMMARY (de50846, `you_answer.wav` stand-in words); Phase 3 D-02.

## Acceptance criteria

- [ ] AC1: Through `tests/scenes.py`'s real hearing path, on both the native `Speaker` and the page's player, a Void
  line containing "stop" is heard back during the line, and again within `ECHO_TAIL` after his sound ends. Both bursts
  pass through `Wake.stop_in` and `Wake.check`, his line plays to its last chunk, and no Claude turn starts
- [ ] AC2: On both voice paths, the owner's "Stop, stop." whose first word begins just past `ECHO_WORD` after the end
  of Void's played "stop" stops his playback before the line ends
- [ ] AC3: The phase SUMMARY lists the heard-versus-played offsets measured in the own-stop scenes (fixture word times
  and real Whisper), and `ECHO_WORD` in `app/gate.py` is no smaller than the largest of them
- [ ] AC4: A test shows that a burst near no stop phrase Void played is transcribed with `Heard.words` None, and that
  one overlapping a played stop phrase has its words timed
- [ ] AC5: In a full suite run, every `tests/test_log_cases.py` row and scene that passed at `bf7b120` still passes,
  and the new own-stop rows pass with no expected-failure mark
- [ ] AC6: The phase's diff on `macos` touches no path under `docs/superpowers/`, `docs/design/`, `.claude/`,
  `queues/`, `.planning/` or `CLAUDE.md`. Merging `macos` into `personal` gives no conflicts. The two accepted commands
  from `.github/cadence/coverage-policy.json` exit 0 with `app/gate.py`, `app/hearing.py` and `app/drops.py` at or
  above 85% lines and branches

## Flagged assumptions

- Where the page path's word times come from is the planner's call: the server's `/api/tts` computing them (the
  design's `X-Void-Words` header) and the page echoing them back, or the page sending them itself - Likely; if wrong:
  the page path reports word times the server cannot trust, and AC1 fails on the page's player.
- The extra Whisper cost of word-timing bursts near a played stop phrase is unmeasured; the timed run may be heavy on
  Slate and is disclosed before it runs - Likely; if wrong: a timed burst is judged late and his line plays on past
  the owner's stop.
- On the fast tier, the server's `tidy_full` trim can differ from the generator's `"lead"` by up to one frame, which
  feeds into Void's heard word times; that difference is unmeasured and sits inside what the AC3 measurement sees -
  Likely; if wrong: `ECHO_WORD` is set too narrow for real playback.
- The replay's carry-over of the last `heard` line's flags (about 14 kept "stops him" rows, Phase 3 SUMMARY) is not
  fixed here - Confident; if wrong: a replayed own-stop verdict leans on a neighbour's flags, which D-08 avoids for
  the new rows only.
- The worktree's line references and its positional `Burst(..., talking, words=...)` are stale against Phase 4 and are
  re-located at plan time - Confident; if wrong: none.
- The analyzer checked whether the worktree's diff applies and read the design; it did not read the diff hunk by
  hunk, so a worktree change not named in D-06 may still be needed - Likely; if wrong: the planner finds it while
  re-applying, and it is judged against D-01 to D-05.
