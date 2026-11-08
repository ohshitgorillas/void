---
status: testing
phase: 2
fields_version: 1
started: 2026-11-08
updated: 2026-11-08
---

## Items

### 1. Classification covers macos..snapshot exactly once
expected: CLASSIFICATION.md's SHA column matches `git rev-list macos..74af430` (the Plan 1 snapshot) with no SHA missing and none duplicated; every class is fix, visual, feature, dev tooling or merge; a Borderline section lists each call with the owner's ruling
criterion: AC1
status: pass
first_pass: pass
source: verifier
evidence: 157 table SHAs == `git rev-list c895ced..74af430` (157): 0 missing, 0 extra, 0 duplicates; classes 99 fix / 5 feature / 35 dev tooling / 18 merge, and the merge rows == the 18 merges; B-01..B-10 each quote the owner's ruling.

### 2. Fix branch carries no personal-only path
expected: `git diff --name-only c895ced..macos-fixes` prints no path under CLAUDE.md, .claude/, queues/, docs/superpowers/, docs/design/ or .planning/
criterion: AC2
status: pass
first_pass: pass
source: verifier
evidence: `git diff --name-only c895ced..macos-fixes` (65 paths): grep for CLAUDE.md, .claude/, queues/, docs/superpowers/, docs/design/, .planning/ exits 1; app/voiceprint.py is absent from macos-fixes.

### 3. Fix rows present, visual and feature rows absent on the fix branch
expected: every fix row has exactly one author, author-date and subject match in `git log macos-fixes`; every visual or feature row has none (f3b2947 present through 8c064eb is the amended exception)
criterion: AC3
status: pass
first_pass: pass
source: verifier
evidence: All 99 fix rows match exactly once by %an/%aI/%s in `git log macos-fixes`; 283432f, fb16e92, 6537fdb, 7a57ff3 have 0 matches and are '+' in `git cherry macos-fixes 74af430`; f3b2947 matches 8c064eb, an ancestor of c895ced; there are no visual rows; all 94 made commits map to fix rows.

### 4. Fix branch compiles and meets the coverage gate
expected: on macos-fixes, `python3 -m py_compile app/*.py` exits 0 and both coverage-policy commands exit 0 with all 7 include modules meeting 85 for lines and branches
criterion: AC4
status: pass
first_pass: pass
source: verifier
evidence: Observed: py_compile app/*.py on an export of macos-fixes exits 0; the 7 include modules exist; the policy, CI and tests.yml equal personal's. Cited: plan-2 report row 2 records both policy commands at exit 0, 570 passed / 11 skipped, 14 'meets 85' lines with per-module figures, on the unmoved tip 226ed6a (tree efde2a3 == Ruled trial tree).

### 5. Fix branch is in local macos and origin/macos is untouched
expected: `git merge-base --is-ancestor macos-fixes macos` exits 0 and `origin/macos` resolves to 29e22ae
criterion: AC5
status: pass
first_pass: pass
source: verifier
evidence: `git merge-base --is-ancestor macos-fixes macos` exit 0 (both 226ed6a); origin/macos == 29e22ae.

### 6. personal merged macos cleanly with no net change
expected: merge 85c4809 has parents H (6786c66) and macos, `git diff --name-only 6786c66 85c4809` is empty, and `git diff --name-only a3598ed personal` is empty
criterion: AC6
status: pass
first_pass: pass
source: verifier
evidence: 85c4809 parents 6786c66 and 226ed6a; `git diff --name-only 6786c66 85c4809` is empty; `git merge-tree --write-tree 6786c66 226ed6a` exits 0 with H's tree; `git diff --name-only a3598ed a47eb27` is empty. At the tip 1cf90a3 the same diff lists only 7 .planning/ paths from the later docs commit 1cf90a3.

### 7. Later fixes reach personal by a plain merge
expected: `git rev-list --count personal..macos` prints 0 and origin/personal is still 9b309e0 (nothing pushed)
status: pass
first_pass: pass
source: verifier
evidence: `git rev-list --count personal..macos` = 0; merge-base personal macos = 226ed6a = macos; origin/personal == 9b309e0.

## Summary

total: 7
passed: 7
failed: 0
pending: 0
skipped: 0
blocked: 0
reworked: 0
