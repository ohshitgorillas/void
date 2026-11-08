---
status: testing
phase: 5
fields_version: 1
started: 2026-11-08
updated: 2026-11-08
---

## Items

### 1. Clean start: the server boots from clean state
expected: (ci: tests) The tests job starts Void's server fresh on a clean runner (launcher and quit tests start a real server with no prior state) and the suite exits 0
origin: smoke
status: pending_ci
job: tests
commit: bb843a8a7649820c06314ad04a952ec83112e28d
first_pass: fail
source: model
evidence: Moved from ffac991 to HEAD bb843a8; ffac991..HEAD touches only .planning/phases/5/ (UAT.md, FINDINGS.json, verifier-findings.json), so the local half stands: 'uvx --with pytest-cov --with-requirements tests/requirements.txt pytest --cov=app --cov-branch --cov-report=json' -> '813 passed, 15 skipped in 283.38s'. The clean-runner boot is the CI tests job's to show; nothing is pushed.
reported: unverified, not observed failing: no automated check was exercised on HEAD in this verification. The boot tests start a real server, which is outside the verifier's allowance, the suite run was reserved for the main session, and the CI tests job has never run on this code (nothing pushed; SUMMARY says 'not CI-verified').
severity: minor

### 2. His own stop heard back never stops him, both paths
expected: Through tests/scenes.py's real hearing path, on the native Speaker and the page's player, a Void line containing "stop" heard back during the line and again within ECHO_TAIL after his sound ends passes through Wake.stop_in and Wake.check, his line plays to its last chunk, and no Claude turn starts
criterion: AC1
status: pass
first_pass: pass
source: verifier
evidence: FastScenes::test_his_own_stop_phrase_heard_back_never_stops_him_on_the_native_path and _on_the_page_path PASSED. Each asserts the peek and Wake.check echo drops, no barge or turn, and play to the last chunk, then reruns with own_stop patched to False and requires a barge. Callers wiring: app/server.py:1901, :1918, :1987.

### 3. The owner's stop just past ECHO_WORD still stops him, both paths
expected: On both voice paths, the owner's "Stop, stop." whose first word begins just past ECHO_WORD after the end of Void's played "stop" stops his playback before the line ends
criterion: AC2
status: pass
first_pass: pass
source: verifier
evidence: FastScenes::test_stop_said_just_past_echo_word_after_his_own_stop_phrase_stops_him_on_the_native_path and _on_the_page_path PASSED (ECHO_WORD < gap <= ECHO_WORD+0.1, barge, playback ended before the line). The OWN_STOPS BARGE row passed.

### 4. ECHO_WORD covers the measured offsets
expected: The phase SUMMARY lists the heard-versus-played offsets measured in the own-stop scenes (fixture word times and real Whisper), and ECHO_WORD in app/gate.py is no smaller than the largest of them
criterion: AC3
status: pass
first_pass: fail
source: model
evidence: SUMMARY.md '## Measured offsets' (ffac991) lists every own-stop offset: fast tier +0.020/+0.020 native and page; slow tier real Whisper native opening -0.090/+0.120 max, closing -0.560/-0.290 .. -0.520/-0.350; page opening -0.060/+0.130 max, closing -0.530/-0.300 .. -0.510/-0.340. Largest |offset| 0.56 s. `grep -n 'ECHO_WORD = ' app/gate.py` -> '30:ECHO_WORD = 0.60', and 0.60 >= 0.56.
reported: missing: the phase SUMMARY does not list the measured heard-versus-played offsets that AC3 and D-04 require it to record. It gives only the 0.56 s maximum and a 0.50-0.56 s range for the closing phrase, and no fixture-word-time offsets at all. The value itself (0.60 >= 0.56) holds.
severity: minor
cause: The offsets were measured and recorded, but only in .planning/phases/5/reports/plan-3.md (Task 5 and Task 6 rows: fast tier +0.020/+0.020 on both paths; slow tier real Whisper, native opening -0.090/+0.100..+0.120 and closing up to -0.560/-0.350, page opening -0.060/+0.090..+0.130 and closing up to -0.530/-0.340). SUMMARY.md's write-up carried only the 0.56 s maximum and the 0.50-0.56 s closing range, so the AC3 record half is missing from the SUMMARY. The code half holds: app/gate.py:30 ECHO_WORD = 0.60 >= 0.56. Fix is docs-only: add the per-scene offset table to SUMMARY.md.
fix: ffac991, retest

### 5. Only a burst near a played stop phrase is word-timed
expected: A test shows a burst near no stop phrase Void played is transcribed with Heard.words None, and one overlapping a played stop phrase has its words timed
criterion: AC4
status: pass
first_pass: pass
source: verifier
evidence: tests/test_echo.py::HeardWordTimes 9 passed, including test_a_burst_near_no_played_stop_is_untimed (words None, no word_timestamps) and test_a_burst_overlapping_a_played_stop_gets_its_kept_words_at_monotonic_times.

### 6. Replay rows and scenes still pass; own-stop rows pass unmarked
expected: In a full suite run, every tests/test_log_cases.py row and scene that passed at bf7b120 still passes, and the new own-stop rows pass with no expected-failure mark
criterion: AC5
status: pass
first_pass: pass
source: model
evidence: Full suite in this session: 'uvx --with pytest-cov --with-requirements tests/requirements.txt pytest --cov=app --cov-branch --cov-report=json' -> '813 passed, 15 skipped in 283.38s', the 15 skips all 'slow tier: set VOID_SCENES=1'; no xfail. Covers every tests/test_log_cases.py row (8 OWN_STOPS unmarked) and every fast-tier scene.

### 7. Phase diff stays off docs, merges clean, coverage floors hold
expected: The phase's diff on macos touches nothing under docs/superpowers/, docs/design/, .claude/, queues/, .planning/ or CLAUDE.md; merging macos into personal gives no conflicts; the two accepted coverage commands exit 0 with app/gate.py, app/hearing.py and app/drops.py at or above 85% lines and branches
criterion: AC6
status: pass
first_pass: pass
source: model
evidence: Paths: c2bf596..macos touches only app/ and tests/ (verifier). Merge: 691f604 second parent macos, 0 conflicts (verifier). Coverage, run in this session: the accepted pytest command -> '813 passed, 15 skipped', then 'node .github/ci/coverage-modules.mjs --report coverage.json' -> exit 0: gate.py lines 99.27% / branches 97.92%, hearing.py 98.59% / 89.29%, drops.py 100% / 100%.

## Summary

total: 7
passed: 6
failed: 0
pending: 0
pending_ci: 1
skipped: 0
blocked: 0
reworked: 2
