# Phase 3: Real-log replay - Context

Gathered: 2026-11-07
Feeds: /cad-plan 3

## Scope boundary

In: `void drops` extended to print every burst of a real `server.log` (kept and dropped) with its `gate.judge` verdict
and reason, stable across replays; a regression table of the owner's reported drops, seeded from `YOURS` and the real
log, with a borderline list for the owner's ruling; each case today's hearing gets wrong marked with the phase meant to
fix it.
Out: fixing any case (Phases 4-6); widening `gate.Burst` or adding a sound record or word times (Phases 4-5); music
and other voices (Phase 6); `stream/replies-after-quiet` and `stream/stop-echo`; rewording or removing the existing
`HIS_*` lines in `tests/test_log_cases.py`; pushing any branch.
Deferred: None
Plan shape: multiple plans, same phase - plan 1 mines the real log and writes the borderline list for the owner's
ruling; plan 2 builds the regression table, the `void drops` change and the expected-failure marks on those rulings.

## Durable decisions

- D-01 (Still-wrong cases): A regression case today's hearing gets wrong is a strict expected failure
  (`xfail(strict=True)` or the suite's equivalent) whose reason names the fixing phase (4, 5 or 6); never `skip`, never
  a plain failing test, never a module CI does not run. It turns the suite red as soon as a fix makes it pass, so the
  fixing phase must remove the mark. This rewords ROADMAP Phase 3 criterion 3's "fails": a plain failure would hold
  the `tests` job red on `macos` and `personal` until Phase 6. Technical call under the 26 Oct ruling, confirmed by
  the owner 2026-11-07. Evidence: `.github/workflows/tests.yml`; `tests/test_coverage_modules.py:2`; Phase 1 concern
  that a skip reads green.
- D-02 (Public text): Committed test data carries only the owner's short request texts ("It's good", "Yes, do it");
  no `server.log` excerpts and no session or `history.jsonl` content. Owner ruling 2026-11-07 ("Short phrases only").
  Evidence: `tests/test_log_cases.py` `YOURS`; README privacy promise; `tests/` ships on public `macos` (Phase 2 D-02).
- D-03 (One drop site): Every regression case runs through today's `gate.judge` with the inputs as logged; Phase 3
  does not widen `gate.Burst`, since the sound record and word times are Phases 4-5's design; `drops.py` and the tests
  add no drop logic of their own. Evidence: `app/gate.py` `Burst` (text, heard, speech, seconds, kind, talking); ROADMAP
  Phase 3 criterion 4, Phases 4-6.

## Decisions

- D-04 (Replay command): Phase 3 extends the existing `app/drops.py` / `bin/void drops [LOG] [--day]`, which already
  re-judges each logged burst with `gate.judge`; no second replay path. Evidence: `app/drops.py` `now()` calls
  `gate.judge(b, [], {"voice_gate": True})`; `bin/void:83`; `tests/test_drops.py`, `tests/test_log_cases.py` `Replay`.
- D-05 (Replay output): `void drops` prints every burst by default, kept as well as dropped, each with its text, kept
  or dropped, and the `gate.judge` reason. Evidence: `app/drops.py` `parse()` discards `kept` lines today
  (`m.group("why") != "kept"`); 1452 `kept (...)` lines in the real log.
- D-06 (Replay limit): Replay is text-only: a verdict that rests on what the log never recorded (echo, no speech, low
  confidence, text cut at 80 characters) prints "as logged" rather than being re-judged. Evidence: `app/drops.py`
  `UNSEEN`, `CUT`; `app/server.py` ~1807 logs only duration, word count and flags.
- D-07 (Determinism): Replaying one log twice prints identical lines, asserted by a test. Evidence: `app/gate.py` is
  pure; `replay()` is a function of the lines alone.
- D-08 (Test data): No test reads the real `~/.local/share/void/server.log`; tests use inline or fixture logs. Evidence:
  `tests/test_log_cases.py` inline `LOG`; Phase 1 D-07 (no user data in CI).
- D-09 (Regression table): One table extends `tests/test_log_cases.py` (`YOURS`), one test case per row, each row
  holding text, kind, talking state, recent lines, expected verdict and fixing phase. Evidence: `YourFollowUps`
  `subTest` over `YOURS` with `CFG` and `burst()`.
- D-10 (Seeding): The table starts from `YOURS` and the reported drops located in the real log (pre-stamp lines 10475,
  14747, 15123; stamped 27 Oct lines 32226, 32963, 32970); a candidate where it is unclear whether the owner, the room
  or Void's own echo spoke goes on a borderline list for the owner's ruling, as in Phase 2. Evidence: `grep -n` of
  `~/.local/share/void/server.log` (2026-11-07); junk hits such as "Drink it. It's good..." (line 36695).
- D-11 (Landing): Code and tests land on local `macos` first and reach `personal` by merge; `origin/macos` is pushed
  only at the version bump; this CONTEXT and `.planning/` stay on `personal`. Evidence: Phase 2 D-03, D-04, D-02.

## Acceptance criteria

- [ ] AC1: `void drops ~/.local/share/void/server.log` prints one line per stamped burst, kept and dropped alike, each
  showing its text, kept or dropped, and the `gate.judge` reason or "as logged"; running it twice and diffing the two
  outputs shows no difference
- [ ] AC2: The regression table holds a row for "It's good", "Yes, do it", "Yes, God damn", every `YOURS` follow-up and
  every drop the owner rules theirs from the borderline list, each with an expected verdict, and each row where today's
  `gate.judge` disagrees names Phase 4, 5 or 6
- [ ] AC3: A full suite run reports every regression row as passed or as an expected failure whose reason names Phase 4,
  5 or 6, and none as skipped; changing one expected-failure row's expected verdict to today's verdict makes the suite
  fail
- [ ] AC4: `git diff` over the phase shows `gate.Burst`'s fields unchanged, and every kept or dropped verdict
  `drops.py` prints comes from a `gate.judge` call
- [ ] AC5: Every row text this phase adds is at most 80 characters, and no file added or changed under `tests/` in this
  phase contains a line found verbatim in the real `server.log`
- [ ] AC6: The two accepted commands from `.github/cadence/coverage-policy.json` exit 0 on the phase's final tree, with
  `app/drops.py` and `app/gate.py` at or above 85% lines and branches

## Flagged assumptions

- About 110k of the log's ~126k drops (no speech 76611, echo 1419 among them) can only print "as logged"; a regression
  case that needs echo or confidence carries hand-supplied recent lines and `Heard` values, as `HIS_*` does - Confident;
  if wrong: the replay promises verdicts it cannot re-derive.
- Some reported drops may need state `gate.Burst` lacks to be judged right (reply timing, own-stop echo, music); under
  D-03 they are expressed with today's inputs and marked for their phase - Unclear; if wrong: a case fails or passes
  for a reason unrelated to the bug it stands for, and the fixing phase re-states it.
- `~/.local/share/void/server.log` is the only real log (198000 lines, stamped 26 Oct 20:30 to 5 Nov 21:26, no
  rotation); a disk-wide search for other copies did not finish - Likely; if wrong: older drops are missed.
- The existing `HIS_*` lines in `tests/test_log_cases.py` are longer than D-02 allows for new data; they are left as
  they are this phase - Likely; if wrong: the owner wants them shortened, which is a small follow-up.
- Printing kept bursts changes `void drops`'s counts and the existing `Replay` expectations; the planner updates those
  tests rather than adding a flag - Likely; if wrong: an `--all` flag keeps the old default.
