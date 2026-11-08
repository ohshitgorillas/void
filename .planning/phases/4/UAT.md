---
status: testing
phase: 4
fields_version: 1
started: 2026-11-08
updated: 2026-11-08
---

## Items

### 1. Clean start: the server boots from clean state
expected: (ci: tests) The tests job starts Void's server fresh on a clean runner (launcher and quit tests start a real server with no prior state) and the suite exits 0
origin: smoke
status: pass
job: tests
commit: c9d64cb6f776635490b3e8163d212c46c1e77066
first_pass: fail
source: model
evidence: tests concluded success at c9d64cb6f776635490b3e8163d212c46c1e77066 (run 42473887752): '700 passed, 11 skipped in 519.02s' on a clean macos-15 runner
severity: major
cause: tests concluded failure at 84d09e8 (run 42472682814): 3 failed, 697 passed - tests/test_echo.py test_real_echo_begun_while_he_made_sound_is_still_dropped_as_echo, test_his_own_words_heard_in_the_ring_after_his_last_sound_are_dropped_as_echo, test_his_said_words_heard_after_the_ring_are_a_follow_up. Root cause is a test clock defect, not app code: the tests note his lines (server.note_spoken -> SPOKEN stamped with the REAL time.monotonic) before aired()'s clocked() pins the mocked clock at 1000-1013 s, and said_lately() ages SPOKEN against that mocked clock. On a host up for days (local, 29 days) the age is negative so the lines stay; on a freshly booted CI runner they are older than ECHO_KEEP, are forgotten, and the echo text match never fires. Reproduced locally: the three pass plainly and all three fail with time.monotonic offset to ~300 s of uptime (scratch pytest plugin).
fix: c9d64cb, retest

### 2. Phase 4 replay rows pass unmarked
expected: Full suite: every tests/test_log_cases.py row whose reason named Phase 4, including "It's good" and "Yes, do it", passes with no expected-failure mark, kept and answered
criterion: AC1
status: pass
first_pass: pass
source: verifier
evidence: Phase 4 mark constants removed, no row has phase=. tests/test_log_cases.py run on its own: all rows PASSED, 0 xfailed, including It's good (follow, logged over), Yes, do it (follow) and Yes, do it (follow, logged wake). The re-statement is backed by real Wake.check tests (test_its_good_said_after_the_page_went_quiet_is_a_follow_up, test_yes_do_it_after_he_went_quiet_is_heard_as_a_follow_up_and_kept_not_dropped_as_echo), both passing.

### 3. Echo judged by when his sound ended
expected: Through tests/scenes.py's real hearing path: his own line heard while it plays is dropped as echo, the same line 0.5 s after his sound ends is dropped as echo, and the same text 1.5 s after is kept
criterion: AC2
status: pass
first_pass: pass
source: verifier
evidence: gate.judge echo test gated on b.rang (app/gate.py:139). tests/test_scenes.py FastScenes 17 passed, 0 skipped, including the three echo scenes at during-play, +0.5 s (dropped) and +1.5 s (kept as follow-up).

### 4. A follow-up waits for his line; stop and Void cut it
expected: A follow-up kept while he speaks leaves his line playing to its last chunk and is sent exactly once after it ends; "stop" or "Void" said over him stops playback before the line ends
criterion: AC3
status: pass
first_pass: pass
source: verifier
evidence: Native: the FastScenes pause-hold scene passed (one kept follow-up, no barge, line plays to its last chunk), as did the stop and 'hey Void' scenes (barge, playback ended early). Page: test_page_held.py ran against the real index.html in Chrome. test_kept_while_speaking_goes_out_once_his_sound_has_ended (sent exactly once, after quiet) and test_barge_is_what_stops_him_mid_speech passed, 24/24 page tests in all.

### 5. One record of his sound
expected: Sound through the native Speaker and through /api/speaking both make Wake.air report talking over that time; the page's hold reads that record; index.html has one 'is he making sound' test; /api/speaking records no placeholder span
criterion: AC4
status: pass
first_pass: pass
source: verifier
evidence: Speaker._write and /api/speaking both write Wake.talked, and Wake.air reads only it. /api/speaking has no 60/0.8 literal span. The page's single sounding() reads the server's numbered copy (voice event plus post replies) and is the only wait in untilQuiet, whenQuiet, followTry, heldTry and quietNative. Passing tests: PageSpeaking.test_speaking_on_records_talking_until_now_plus_left, NativeOwed.test_its_first_sound_chunk_pays_it_in_the_same_change_as_the_span, test_air_says_whether_his_sound_and_its_ring_were_in_the_air_over_a_burst, test_page_sound.py SoundingReadsTheRecord.test_player_state_does_not_decide_it.

### 6. Phase diff stays off docs and merges clean
expected: The phase's diff on macos touches nothing under docs/superpowers/, docs/design/, .claude/, queues/ or CLAUDE.md, and merging macos into personal gives no conflicts
criterion: AC5
status: pass
first_pass: pass
source: verifier
evidence: git diff --name-only b457a58..macos touches only app/ and tests/, with 0 paths under the five forbidden roots. git merge-tree --write-tree fe86856 de50846 exits 0 and gives tree f2111ae8 == 53baa07^{tree}.

### 7. Coverage commands pass
expected: The two accepted coverage-policy commands exit 0 on the final tree, with app/gate.py, app/hearing.py and app/drops.py at or above 85% lines and branches
criterion: AC6
status: pass
first_pass: pass
source: model
evidence: Main session on 413760a: `uvx --with pytest-cov --with-requirements tests/requirements.txt pytest --cov=app --cov-branch --cov-report=json` -> exit 0, '700 passed, 11 skipped in 355.92s' (all 11 'slow tier: set VOID_SCENES=1'); `node .github/ci/coverage-modules.mjs --report coverage.json` -> exit 0, 'app/gate.py: lines: 99.07% meets 85', 'branches: 97.62% meets 85'; 'app/hearing.py: lines: 98.12% meets 85', 'branches: 87.50% meets 85'; 'app/drops.py: lines: 100.00% meets 85', 'branches: 100.00% meets 85'

## Summary

total: 7
passed: 7
failed: 0
pending: 0
skipped: 0
blocked: 0
reworked: 1
