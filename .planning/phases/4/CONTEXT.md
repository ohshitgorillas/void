# Phase 4: Replies after quiet - Context

Gathered: 2026-11-07
Feeds: /cad-plan 4

## Scope boundary

In: one record of when Void's sound is coming out, `Wake.talked`, fed by the native `Speaker` and the page's player and
read by every "is he making sound" test on both paths; `gate.Burst` gains `rang` so echo is judged only while his sound
or its ring was in the air; a follow-up kept while he speaks or works waits until he has finished speaking and is then
answered; the approved `stream/replies-after-quiet` design and code ported onto local `macos` and merged into
`personal`; the Phase 4 expected-failure marks in `tests/test_log_cases.py` removed for every row the new code gets right.
Out: own-stop echo and `ECHO_WORD` (Phase 5, `~/dev/void-stop-echo`); music and other voices (Phase 6); word times from
Whisper; changing `ECHO_TAIL`; pushing any branch.
Deferred: None
Plan shape: multiple plans, same phase - /cad-plan breaks it down (e.g. the server record and gate first, then the
page's hold and its tests).

## Durable decisions

- D-01 (One record; amended by D-10 and D-11): `Wake.talked` in `app/server.py` is the one record of when Void's sound is coming out of the
  speakers; it holds his sound only, never the ring. Two writers feed it: `Speaker._write` (sound chunks) and
  `/api/speaking` (`{"on": true, "left": <s>}` from the page's player, `{"on": false}` ends it now). Every "is he making
  sound" test reads it: the server's `Burst` timing through `Wake.air`, and the page's hold, which gets it from the
  server rather than from its own `playing`/`q.length`/`spkMap` state. The 60 s placeholder span in `/api/speaking`
  (`Wake.talking_until(time.monotonic() + (60 if b.get("on") else 0.8))`, what ROADMAP criterion 4 calls
  `speaking_until`) and the page's separate "finished speaking" tests are gone. This goes one step past the branch
  design, whose page-side `sounding()` stays page-local. Technical call under the 26 Oct ruling, confirmed by the owner
  2026-11-07. Evidence: `git show stream/replies-after-quiet:docs/superpowers/specs/quiet-replies-design.md`;
  `app/server.py:1551`, `app/server.py:3855`; `app/static/index.html` `untilQuiet`, `followTry`, `whenQuiet`, `heldTry`,
  `quietNative`; ROADMAP Phase 4 criterion 4.
- D-02 (Burst `rang`): `gate.Burst` gains `rang` (his sound, or its ring `ECHO_TAIL` after it, was in the air at some
  moment of the burst); `judge` runs the echo test only when `rang` is true; `gate.judge` stays the one place a burst is
  dropped. This is the widening Phase 3 D-03 held back for this phase. Evidence: branch design "`app/gate.py`" section;
  `app/gate.py` `Burst`, `ECHO_TAIL` (`app/gate.py:25`); Phase 3 D-03.
- D-03 (A reply never cuts him off): a follow-up kept while Void is speaking or still working on his answer is held
  until he has finished speaking, then sent once and answered; no follow-up shushes him; only a stop phrase or "Void"
  said over him cuts him off. Something like "no wait" said over him therefore waits for the line to end. Owner ruling
  27 Oct (branch commit 89962b0), re-confirmed 2026-11-07. Evidence: HEAR-02; branch design "Why" items 1-5;
  `app/static/index.html` `onEvent` follow branch, `send`'s `shush()`, `heldTry`.

## Decisions

- D-04 (Starting point): planning starts from the approved branch design and its three code commits (3da6d90,
  493426a, ce5b1e5); no second record is built beside `Wake.talked`. Evidence: `git log macos..stream/replies-after-quiet`;
  branch design `Status: approved`.
- D-05 (Landing): the branch forks from `3ef6fbc`, a pre-split `personal` 116 commits off `macos`, so its code changes
  are re-applied onto local `macos`, not merged or cherry-picked wholesale; its design docs (a701027, 89962b0, under
  `docs/superpowers/`) stay off `macos`; the work reaches `personal` by merging `macos`; nothing is pushed. Evidence:
  `git merge-base macos stream/replies-after-quiet` = `c895ced`; Phase 3 D-11; Phase 2 D-02, D-03.
- D-06 (Timing): `ECHO_TAIL` stays 1.0 s; the ring is not talking; `Wake.span_at` covers his sound only; the follow-up
  window opens when his sound ends and `until` stays `end + ECHO_TAIL + follow_up`; `Wake.check` classes a burst over,
  follow or wake by when it began; the pause after a sentence counts as sound only when his next sentence is already
  made; push-to-talk (`Listen.run`) keeps `talking=False` and judges `rang` over its recording. Evidence: branch design
  "`app/server.py`" section; `app/gate.py:25`.
- D-07 (Phase 4 marks): the `AFTER_QUIET`, `AFTER_SPOKE` and `WHILE_TALKING` marks come off every row the ported code
  gets right; a row it still gets wrong keeps a strict expected failure naming the phase meant to fix it, with the reason
  stated in the phase SUMMARY; Phase 5 and 6 marks are untouched. Evidence: `tests/test_log_cases.py:42-44`, `Row`/`row()`;
  Phase 3 D-01.
- D-08 (Tests): the branch's tests (`test_echo.py`, `test_wake_loop.py`, `test_page_held.py`, `test_listen_verdict.py`,
  `test_gate.py`) are carried onto today's `tests/fakes.py` and `tests/scenes.py`; the echo and hold scenes run through
  the real hearing path; page tests run on installed Chrome; no test double lives outside `tests/fakes.py`. Evidence:
  branch diffstat; `tests/scenes.py`, `tests/fakes.py`.
- D-09 (Replay): `drops.py` builds each replayed `Burst` with `rang` from one reading of the logged flags; a verdict
  resting on what the log never recorded still prints "as logged". Evidence: branch diff of `app/drops.py`
  (`drops.rang`); `app/drops.py:77`; Phase 3 D-06.
- D-10 (D-01 amended: what he still owes): the record of Void's voice has two parts, both in `Wake`. `Wake.talked`
  holds his sound only, never the ring; `Wake.air` and the gate read nothing else, and D-06's rule on the pause after a
  sentence stands for it. `Wake.owed` holds every sentence handed to a player whose sound has not begun. Native:
  `Speaker.say` adds it; it is paid inside the same `Wake.talking` call that records its first sound chunk, or when it
  is skipped or dropped. Page voice: `enqueue` posts `/api/speaking {"owe": 1}`, and `pump` posts
  `{"on": true, "left": s, "paid": 1}` for each sentence it schedules, or `{"paid": 1}` for one with no audio.
  `Wake.hush` and `{"on": false}` clear what is owed. Each record change publishes Plan 1 Task 7's event, carrying
  `left`, `owed` and a sequence number `n`; `/api/say`, `/api/say/stop` and `/api/speaking` return the same fields. The
  page's one test `sounding()` is true while the newest record copy shows sound ahead or `owed > 0`, or while one of its
  own hand-off posts is unanswered (`handing > 0`, raised in `enqueue`, lowered when that post settles or is skipped).
  Nothing tests `playing`, `q.length` or `spkMap.size` as a wait for him. Closes the mid-answer gap the plan review
  found (a reply held while his next sentence is still being made going out before his line ends; AC3). Architect
  ruling under the 26 Oct ruling, 2026-11-07. Evidence: `app/server.py:1535`-`1546` (paid and first span under
  `talk_lock`), `app/server.py:2380`, `:2402`, `:2488` (sentence waiting before sound), `app/server.py:2406`, `:2496`,
  `:3680` (native skips); `app/static/index.html:1754` (chained `/api/say` posts), `:2229`, `:2241` (`busy=false`
  before the last `flush(true)`).
- D-11 (No start-bound): `untilQuiet` and `whenQuiet` wait only while `sounding()`, which is already true right after
  `enqueue` (D-10); their 40 s and 60 s caps remain the only time limits. A sentence with no audio ends the wait by its
  paid mark. Architect ruling, 2026-11-07. Evidence: `app/static/index.html:1907`, `:2282` (caps), `:1881` (no-audio
  sentence).

## Acceptance criteria

- [ ] AC1: In a full suite run, every `tests/test_log_cases.py` row whose reason named Phase 4 ("It's good" and "Yes, do
  it" included) passes with no expected-failure mark, kept and answered
- [ ] AC2: Through the real hearing path (`tests/scenes.py`), Void's own line heard back while it plays is dropped as
  echo, the same line heard 0.5 s after his sound ends is dropped as echo, and the same text heard 1.5 s after his sound
  ends is kept
- [ ] AC3: A follow-up kept while Void is speaking leaves his line playing to its last chunk and is sent exactly once,
  after the line ends; "stop" or "Void" said over him stops his playback before the line ends
- [ ] AC4: Sound written through the native `Speaker` and sound reported through `/api/speaking` both make `Wake.air`
  over that time report talking; the page's hold reads that same record; `app/static/index.html` has one "is he making
  sound" test and `/api/speaking` records no placeholder span
- [ ] AC5: The phase's diff on `macos` touches no path under `docs/superpowers/`, `docs/design/`, `.claude/`, `queues/`
  or `CLAUDE.md`, and merging `macos` into `personal` gives no conflicts
- [ ] AC6: The two accepted commands from `.github/cadence/coverage-policy.json` exit 0 on the phase's final tree, with
  `app/gate.py`, `app/hearing.py` and `app/drops.py` at or above 85% lines and branches

## Flagged assumptions

- `rang` is a required `Burst` field as the design says, so every positional `Burst(...)` in `tests/`, `drops.py` and
  `server.py` is updated; a default of True is the planner's call if that churn is too wide - Likely; if wrong: callers
  break or an old caller silently skips the echo test.
- Every `AFTER_SPOKE` row (logged `kind="wake"`, dropped for "no wake word") becomes a kept follow-up under the new
  `window_at`; `WHILE_TALKING` rows may need the hold modelled to show "kept and waits" through `gate.judge` - Unclear;
  if wrong: some Phase 4 rows keep a mark and AC1 fails until they are re-stated.
- The page reading the server record (D-01) adds no audible lag to the held reply going out; the transport (state poll
  or event stream) is the planner's call - Likely; if wrong: a held reply goes out late after his line ends.
- The branch design's line references (e.g. `app/static/index.html:1962`, `:2204`) are stale: `index.html` changed
  about 228 lines between `3ef6fbc` and `macos` - Confident; if wrong: none, they are re-located at plan time.
- The pause after a sentence counts as sound only when his next sentence is made (D-06) - Likely; if wrong: a reply in a
  long pause mid-answer is heard as a new request, or a reply in a gap is held too long.
- The Phase 3 merge was not followed by a full suite run on `personal`, so the planner takes a baseline before Phase 4
  changes land - Likely; if wrong: an earlier regression is charged to Phase 4.
