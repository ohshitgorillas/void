---
phase: 3
plan: 1
requirements:
  - HEAR-05
files:
  - .planning/phases/3/DROPS.md
---

# Phase 3: Real-log replay - Plan 1: The reported drops, mined from the real log, and the owner's rulings

## Goal

Hearing is judged against what the owner actually said. This plan finds the owner's reported drops in the real `server.log` and gets the owner's ruling on every case where it is unclear who spoke. Plan 2 then turns them into regression tests.

## Must be true when done

- `.planning/phases/3/DROPS.md` gives each of the six seeded log lines (pre-stamp 10475, 14747, 15123; stamped 32226, 32963, 32970) and each `YOURS` text from `tests/test_log_cases.py` its log line, or says in so many words that the line is not in this log
- Every candidate the mining found carries a class (the owner's, the room, Void's own echo, or borderline) and the evidence for that class. "Drink it. It's good..." (line 36695) appears as not his, with its reason
- Every owner row and borderline row shows its inputs as logged (kind, talking), today's verdict, the verdict the owner expects, and the phase meant to fix it (4, 5, 6, or none where today already agrees)
- Every borderline row carries the owner's own ruling
- No file other than `.planning/phases/3/DROPS.md` is changed by this plan

## Context

- Locked: D-10 (seeds: `YOURS` plus the six lines above; an unclear speaker goes on a borderline list for the owner, as in Phase 2), D-02 (only the owner's short request texts ever reach committed test data), D-08 (no test reads the real log). The mining is done locally by the executor and is not a test.
- Sources, read locally and never copied into `tests/`: `~/.local/share/void/server.log` (198000 lines, stamped 26 Oct 20:30 to 5 Nov 21:26, older lines unstamped) and `~/.local/share/void/history.jsonl` (463 rows; `ts` in epoch seconds, `you` holds the owner's request and `him` holds Void's reply). Log stamps are local time, from `server.hear_out`.
- Log shape, read from `app/server.py` `verdict_out`, `Wake.check` and the burst handler. Each verdict line is one `gate.judge` call. A wake burst is often judged twice, by the wake check and then in full: the same `<why> (wake): <text>` line appears twice with a `heard` line between them (lines 32226 and 32228). A `peek` verdict is a partial check of a burst that is still going, and the full burst is judged later as `over`. The `talking` state of a verdict is the `while talking` flag of the `heard` line before it.
- Out: any change under `app/`, `tests/` or `bin/` (Plan 2); fixing any case (Phases 4-6).

## Tasks

### Task 1: Locate the seeded and named drops

- **Files:** .planning/phases/3/DROPS.md
- **Action:** Create the file. Its header says what it is: the owner's reported drops, mined from the named log, for Plan 2's regression table. It also says that heard texts are quoted as logged (at most 80 characters) and that Void's own lines are never quoted. Evidence about what Void had said is written in plain words of your own, never copied from `history.jsonl`. That is my choice: the file lives on `personal`, and D-02's privacy line is kept here too. Write one row for each of the six seed lines and one for each `YOURS` text. Also write a row for every other logged drop of kind `follow`, `over` or `wake` whose text, lower-cased with punctuation dropped, contains "its good", "yes do it" or "yes god damn" (also "yes goddamn"). Pre-stamp lines in the old wording count too ("dropped echo of own speech", "ignored while talking", "dropped follow-up, ..."). A seed that is itself a kept line (14747 is a `follow-up request`) gets a row for the drop or drops it followed, if the lines before it hold one, and the row says what was found. When one burst produced a doubled wake verdict, keep one row for it and name both lines. List `peek` hits under a "Not his" section only when they are seeds or named examples (line 36695). Otherwise leave them out: a peek drop loses no request, because the full burst is judged after it. Each row carries an ID, the log line(s), the stamp (or "-"), the logged verdict as `<why> (<kind>)`, `talking` from the preceding `heard` line, the text as logged, today's verdict, a class and the evidence. Today's verdict is what `app/drops.py` `now()` returns for that line today: "kept", "kept: stops him", the drop reason, or "as logged". Classes are owner, room, echo or borderline. For the evidence, use the `heard` line flags and the `history.jsonl` row nearest in time: what Void had just said or asked, and what the owner said next. Place a pre-stamp line in time by the nearest kept request near it whose text appears in a `history.jsonl` `you` field. A row whose speaker you cannot settle from that evidence is borderline. It is never guessed. Do the mining with scripts in the session scratchpad, and commit none of them.
- **Verify:** `grep -c` on `DROPS.md` finds rows naming log lines 10475, 14747, 15123, 32226, 32963, 32970 and 36695. Each of the 12 `YOURS` texts appears in a row with a log line number or the words "not in this log". Spot-check three rows by `sed -n '<line>p' ~/.local/share/void/server.log`: the logged verdict, kind and text in the row match the log line exactly. `git status --porcelain` shows no change outside `.planning/phases/3/`. Testing scope: no test. This is a record checked against the log.

### Task 2: Mine the rest of the reported drops

- **Files:** .planning/phases/3/DROPS.md
- **Action:** Add the reported drops that Task 1's phrases do not reach, using two signals, and write both signals and their windows into the file's method section. First signal, repeated after a drop: a dropped burst of kind `follow`, `over` or `wake`, with text that is not empty and not `gate.is_filler`, followed by a kept burst holding the same words. The kept burst must come within 60 s on stamped lines, or within 40 log lines on pre-stamp lines: the owner had to say it again. Second signal, the owner complaining he was not heard: a `history.jsonl` `you` entry or a kept log text that says he was dropped or not heard ("dropping", "dropped", "didn't hear", "not listening", "are you listening", "can you hear", "I said", "I just said"). Its candidates are the drops of the same kinds and text rule in the 3 minutes before it (100 log lines before it on pre-stamp lines). The windows are my choice. They are wide enough to cover a re-said request and narrow enough to keep unrelated drops out. Drop candidates that are already rows, and merge doubled wake verdicts as in Task 1. A muttered phrase with no wake word, said outside a follow-up window (such as "God damn it"), is a correct drop and not a reported one. It goes under "Not his" only when a signal named it. Classify each new candidate exactly as Task 1 does, with the same columns.
- **Verify:** The method section names both signals, their windows and the kind and text rule. Rerun the mining script from the scratchpad: the candidate count it prints equals the number of rows the file carries from Task 2, owner, borderline and "Not his" together. Pick two candidates at random and check them against `server.log` and `history.jsonl`: the signal that found each one holds at the stated window. Testing scope: no test. The rerun and the spot-checks are the evidence.

### Task 3: Set the expected verdict and fixing phase on every owner and borderline row

- **Files:** .planning/phases/3/DROPS.md
- **Action:** For each owner and borderline row, write the expected verdict and the fixing phase. The expected verdict is a `gate.WHY` value: "kept" for a request of the owner's that was dropped. A kept row also names the act it expects ("follow" for a follow-up, "request" for a woken request, "barge" for a stop). The fixing phase is "none" when the row's today's verdict already equals the expected verdict. Otherwise use the ROADMAP: Phase 4 for a reply after Void went quiet that was dropped as echo, while talking or no wake word (HEAR-01, HEAR-02; ROADMAP Phase 4 criterion 1 names "It's good" and "Yes, do it"). Phase 5 for the owner's stop phrase, or Void's own (HEAR-03, HEAR-04). Phase 6 for an owner reply dropped by the follow-up window's handling of music or other voices: no speech, low confidence or noise (HEAR-06). This is a technical call under the 26 Oct ruling, not the owner's, and each row says in one clause why its phase fits. A row no phase fits is marked "no phase fits" and named in the file's open-questions section. Never assign it to a phase it does not belong to. For a row that cannot be judged from text alone, note in the row what Plan 2 must supply to reproduce today's verdict with `gate.judge` (hand-written recent lines for echo, a `Heard` value for confidence). That is the flagged assumption in CONTEXT. Write those inputs in your own words, never copied from `history.jsonl`.
- **Verify:** Every owner and borderline row has an expected verdict that is a member of `gate.WHY`, and a phase of 4, 5, 6, "none" or "no phase fits". A row with "none" has today's verdict equal to its expected verdict, and a row with 4, 5 or 6 has them differ, checked row by row. Rows for "It's good" (32963) and "Yes, do it" (32970) name Phase 4 unless their evidence shows otherwise, in which case the row says why. Testing scope: no test. The row-by-row check is the evidence.

### Task 4: Get the owner's ruling on each borderline row

- **Files:** .planning/phases/3/DROPS.md
- **Action:** Order the borderline section so that rows from the same minute sit together. Each row states, in plain words, the text as logged, the moment (what Void had just been doing), the three options (the owner's, the room, Void's own echo), the evidence, and your default. Put the whole list to the owner in one message. Who spoke is a fact only the owner holds, so this is his call. Record each ruling verbatim in its row. A row the owner rules as his becomes an owner row and keeps its expected verdict and phase from Task 3. A row ruled room or echo moves to "Not his" with the ruling as its reason.
- **Verify:** human-verify: the owner reads the borderline list and gives a ruling for every row. Afterwards every borderline row quotes a non-empty ruling, and no row is left unruled. Testing scope: no test. The owner's rulings are the evidence.

## Notes

- Plan 2 starts only after this plan ends with every borderline row ruled, and it reads `DROPS.md` without writing it. The two plans declare no file in common, but they run in order. That follows the CONTEXT plan shape: mining and rulings first, then the table, the `void drops` change and the marks.
- Footprint: the mining reads a 9.8 MB log and a 287 KB history file once per script run. That is seconds of one core, below the 10 s disclosure line.
- Recalled: D-03 and D-01 (`phases/3/CONTEXT.md`, phase 3) bind how Plan 2 uses these rows. The borderline-list form follows Phase 2's Plan 1 Task 6 (`phases/2/PLAN-1.md`, phase 2).
