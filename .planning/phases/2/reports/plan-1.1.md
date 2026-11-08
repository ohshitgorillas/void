PLAN CHECKPOINT: structural
Plan: .planning/phases/2/PLAN-1.md
Tasks: 2 of 8 (Task 3 committed as evidence, its Verify not met as written)
| Task | Commit | Note |
|---|---|---|
| 1 Classification table at snapshot 74af430 | e48283a | 157 rows (93 fix, 35 dev tooling, 18 merge, 7 visual, 4 feature); SHA comm check, uniq -d, merge count 18, class values, personal-only-is-dev-tooling all clean; 7 Borderline rows (B-01..B-07, rulings empty) |
| 2 Path-split section | 1ba17d7 | loop over fix rows found exactly c378787, d015d26, 45d4f02, 4488777 touching personal-only paths; both path lists named |
| 3 Trial build on c895ced | 2c356e4 | Trial section recorded. Plain table-order picks: 76 picked, 6 already on macos, 11 skipped; c378787 skipped so app/voiceprint.py stays. Second pass with the construction below: 87 picks, 0 skipped, voiceprint absent, gate/hearing/drops/notifier present and identical to snapshot, py_compile 0, no personal-only path changed. Worktrees and branches removed afterwards |
Deviations:
- [deviation] Task 3 asserted every fix pick either applies or conflicts on an excluded commit, and that skipped picks get a Borderline row whose options are "carry the prerequisite" or "keep the dependent on personal". Observed: (a) six fix rows (ad1da73, 0ba0fec, 16b5829, f3b2947, 3935571, 7ef0a99) are already on macos under other SHAs (same author date and subject: 975c918, 16d33c7, fabc753, 8c064eb, c63fdea, 5033bce), so they pick empty or conflict; (b) the root of the 10-pick cascade is 044e7f9, whose conflict is a 2-line comment/`stop_said` clash with macos's own 6091587, resolved only inside merge 8cacc1d, not any excluded commit; the Borderline "carry prerequisite" option does not exist for it. Following the plan literally leaves the whole gate/hearing stack (c378787 included, hence voiceprint present) off the fix branch, contradicting D-01. I did not hand-resolve anything and did not add Borderline rows for these; they are in the Trial section as "Construction findings".
- [deviation] Task 5 asserted the merge-back conflicts would be in app/server.py and app/static/index.html. Observed on a probe (not Task 5's run): only `.gitignore` conflicts (8935491 vs 5a4f07d); server.py and index.html auto-merge.
Open items:
- Decide: take 044e7f9 as `git cherry-pick -m 1 8cacc1d` (mechanical, no hand resolution; clears all skips; commit message becomes the merge's, so Plan 2's subject match for that row names 8cacc1d). Alternatives: hand-resolve the 2-line conflict (CONTEXT forbids), or drop the gate stack from fix-bound (contradicts D-01).
- Decide: treat the six already-on-macos fix rows as present (not picked); they stay class fix.
- Decide: .gitignore merge-back conflict needs one prep commit on personal (move the personal-only ignore block above `__pycache__/`; probe merged clean with empty changed-file list) before Plan 2's `git merge macos`; or another way to avoid it. That commit is on personal, outside this plan's lease.
- Path-split now has a fifth row, bb02446 (tests/test_page_sparks.py left behind); Plan 2 must build it that way. Plan 2's "four path-split commits" wording needs updating.
- Remaining plan tasks not started: 4 (suite and per-module gate, about 270 s, footprint to be disclosed first), 5 (trial merge-back as a recorded run), 6 (owner rulings, human-verify; B-01..B-07 owner rows are still open and any real product choice goes to the owner), 7, 8. Task 7's "zero skipped picks" holds only under the construction above.
- Declined: no Borderline rows for the construction findings (technical, architect's per CLAUDE.md rule 3, not product choices).
- Untracked `.planning/phases/2/ADJUDICATION-plan-plan-74af430.json` and this reports dir are the orchestrator's; not committed.
