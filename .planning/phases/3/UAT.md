---
status: testing
phase: 3
fields_version: 1
started: 2026-11-08
updated: 2026-11-08
---

## Items

### 1. Replay prints every burst, deterministically
expected: `bin/void drops ~/.local/share/void/server.log` prints one line per stamped burst, kept and dropped, each with text, kept/dropped, and the gate.judge reason or "as logged"; two runs diffed show no difference
criterion: AC1
status: pass
first_pass: fail
source: model
evidence: After copying app/drops.py into ~/.local/share/void/app (cmp equal): `bin/void drops ~/.local/share/void/server.log` run twice -> `cmp` identical, 128186 lines, last '128175  heard in all; 126723 dropped, 24 of them kept now'; kept rows listed (e.g. ' 15452  2026-10-26 20:30:06  kept (listen)  ->  KEPT  tidy up'); unseen verdicts print 'as logged' (e.g. ' 9271 ... echo (over)  ->  as logged ...')
reported: behavior wrong: the command AC1 names still runs the pre-phase app. The phase's code does print every burst (truth 1), but `void drops` does not reach it
severity: major
cause: Deployment gap, not a code defect: bin/void:26 sets APP to ~/.local/share/void/app whenever that folder exists, and the installed drops.py (27 Oct 20:54) predates the phase; it is the only source file that differs between the install and app/. The phase's app/drops.py itself prints every burst and replays identically (verifier truth 1: 128186 lines, cmp identical). SUMMARY.md's criterion-1 evidence (126733 lines) is a run of the old installed copy.
fix: 26ca43b + app/drops.py copied into ~/.local/share/void/app, retest

### 2. Regression table holds the owner's drops
expected: tests/test_log_cases.py table has rows for "It's good", "Yes, do it", "Yes, God damn", every YOURS follow-up and every owner-ruled drop, each with an expected verdict; each row today's gate.judge disagrees with names Phase 4, 5 or 6
criterion: AC2
status: pass
first_pass: pass
source: verifier
evidence: tests/test_log_cases.py YOURS has 43 rows covering all 12 YOURS texts and owner rows O-01 to O-46, including 'It's good', 'Yes, do it' (follow and wake) and 'Yes, God damn'. Every row has keep/why/act, and all 23 rows today's gate gets wrong are xfail with a reason opening 'Phase 4'. No borderline row was ruled his (DROPS.md line 120).

### 3. Suite reports rows as pass or strict xfail, none skipped
expected: Full suite run shows every regression row passed or xfailed with a Phase 4/5/6 reason, none skipped; flipping one xfail row's expected verdict to today's makes the suite fail
criterion: AC3
status: pass
first_pass: pass
source: verifier
evidence: pytest tests/test_drops.py tests/test_log_cases.py -rxXs: 41 passed, 23 xfailed, 0 skipped. Marks are xfail(strict=True, raises=AssertionError). In a scratch copy, the 'It's good' row with its expectation set to today's verdict gives XPASS(strict), reported as 1 failed.

### 4. gate.Burst unchanged and verdicts come from gate.judge
expected: git diff over the phase leaves gate.Burst's fields unchanged; every kept/dropped verdict drops.py prints comes from a gate.judge call
criterion: AC4
status: pass
first_pass: pass
source: verifier
evidence: git diff c01be68 HEAD -- app/gate.py is empty. In app/drops.py now(), every verdict is gate.judge's except 'as logged' (UNSEEN, or a loop cut at 80 characters).

### 5. Added test text is short and not from the real log
expected: Every row text this phase adds is <= 80 characters; no line of a tests/ file added or changed this phase appears verbatim in the real server.log
criterion: AC5
status: pass
first_pass: pass
source: verifier
evidence: test_every_row_text_fits_what_the_log_keeps passes. None of the 141 added tests/ lines equals any of the 198000 lines of ~/.local/share/void/server.log (scratch check).

### 6. Coverage commands pass with drops.py and gate.py >= 85%
expected: The two coverage-policy commands exit 0 on the final tree, with app/drops.py and app/gate.py at or above 85% lines and branches
criterion: AC6
status: pass
first_pass: pass
source: model
evidence: `uvx --with pytest-cov --with-requirements tests/requirements.txt pytest --cov=app --cov-branch --cov-report=json` -> exit 0, '613 passed, 11 skipped, 23 xfailed, 160 subtests passed' (11 skips all 'slow tier: set VOID_SCENES=1'); `node .github/ci/coverage-modules.mjs --report coverage.json` -> exit 0, 'app/drops.py: lines: 100.00% meets 85', 'branches: 100.00% meets 85'; coverage.json app/gate.py 105/106 lines (99.06%), 41/42 branches (97.62%)

### 7. Regression row 'Yeah, that's fine. Go ahead' (O-21) carries the talking state as logged
expected: behavior wrong: the row's input differs from the log, against D-03 ('inputs as logged') and D-09 (each row holds its talking state)
origin: verifier
status: pass
first_pass: fail
source: model
evidence: tests/test_log_cases.py:108 is now Row("Yeah, that's fine. Go ahead", "over", phase=WHILE_TALKING) (talking=False, as server.log line 20939 logs it). A scripted check of every Row against DROPS.md's talking column finds no mismatch. `uvx --with-requirements tests/requirements.txt pytest tests/test_log_cases.py tests/test_drops.py -q` on personal -> '41 passed, 23 xfailed, 9 subtests passed'
reported: behavior wrong: the row's input differs from the log, against D-03 ('inputs as logged') and D-09 (each row holds its talking state)
severity: minor
cause: tests/test_log_cases.py:108 passes talking=True for O-21, but its heard line (server.log 20939, 'heard 3.0s, 5 words') carries no 'while talking' flag and DROPS.md's talking column says 'no'; DROPS.md's own 'Plan 2 must supply' note for O-21 wrongly says 'talking=True as logged', which the row copied. No result changes today (kind 'over' already gives 'while talking').
fix: b457a58 (merged f1dbff8) + 33b6dd9, retest

## Summary

total: 7
passed: 7
failed: 0
pending: 0
skipped: 0
blocked: 0
reworked: 2
