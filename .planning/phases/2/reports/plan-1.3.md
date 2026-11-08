PLAN CHECKPOINT: decision
Plan: .planning/phases/2/PLAN-1.md
Tasks: 6 of 8 (Task 6 rulings recorded; Task 7 stopped, three stops; Task 8 not run)
| Task | Commit | Note |
|---|---|---|
| 1 Classification table at snapshot 74af430 | e48283a | 157 rows |
| 2 Path-split section | 1ba17d7 | c378787, d015d26, 45d4f02, 4488777 |
| 3 Trial build (first pass, evidence) | 2c356e4 | prior dispatch |
| 3 (amended) recipes, Row-construction pass | 0355af5 | 93 fix rows = 87 made + 6 present |
| 4 Suite and per-module gate | c3cf7c5 | 3 failed (agents tests needing 283432f), gate green |
| 5 Trial merge-back | 7550035 | clean with the ignore reorder |
| 6 Borderline list in plain words | e917930 | rulings pending |
| 6 (continued) Owner's rulings recorded in B-01..B-08 with the quote; 14 table classes changed | b6f154d | a3021dd, 14b64bf, ed2fa27, 8c38409, 61975ea, 6bd5629, b554fd0, 87344d3 to fix; f3b2947, fb16e92, f4acc7d, 89f4bfe to feature; e53ea7b stays fix, 283432f stays feature (reasons say the owner ruled). Table now 97 fix, 7 feature, 35 dev tooling, 18 merge. bb02446 rechecked: plain pick once 87344d3 is on the branch, no longer path-split (Path-split row removed). Presence/Construction text updated for f3b2947 (feature, still present via 8c064eb). New Ruled trial section; new Borderline rows B-09 and B-10 (rulings empty) |
| 7 Ruled trial | b6f154d (same commit) | NOT clean: three stops, below. Task 8 not run |
Stops in the Ruled trial (all follow from rulings B-07 and B-08):
1. Row construction conflicts at 0e6cd82 (40 made, 5 present): `DU tests/test_voice_prompt.py`. The file is created by fb16e92 (feature after B-07); 0e6cd82 edits it. Cascade if skipped: 62c3f33, ff2c7b4, c7a7ef7, 87d1faa, 941d5c1, c378787, 74e983f. Evidence pass: building 0e6cd82 as a path-split pick (drop the test_voice_prompt.py hunk) makes all 92 commits with zero conflicts and zero empty picks (tip b684b76, tree c34c589; Presence: 97 fix once, features absent except f3b2947; no personal-only path; no voiceprint; py_compile 0). Not entered in Path-split. Raised in B-10.
2. Suite on that evidence tree: cmd 1 exit 0 (536 passed, 11 skipped, 243.66 s); cmd 2 exit 1: `app/agents.py: FAIL branches: 82.38% is below 85` (lines 89.39). Other six include modules at or above 85 (gate 99.06/97.62, hearing 98.12/87.50, langmark 98.06/94.44, macsys 100/100, notifier 100/100, drops 100/100). Cause: B-08 option B leaves out f4acc7d. Raised in B-09.
3. Merge-back (reorder committed first on the scratch worktree) conflicts in `app/server.py` (VOICE_PROMPT: fb16e92's lines beside e53ea7b's hover-off lines; B-10) and `tests/test_wake_loop.py` (89f4bfe's loopback_http import line; B-09). Task 5 was clean before the rulings.
Deviations:
- [deviation] Task 7 asserted the ruled set builds, passes the per-module gate and merges back cleanly. Observed: a Row-construction conflict at 0e6cd82, `app/agents.py` at 82.38% branches, and two merge-back conflicts. Recorded, nothing absorbed; no test, `app/` file or policy value changed.
- [deviation] Task 5 (earlier) merge-back was clean; with the rulings applied it is not (Stop 3).
Open items:
- Decision needed: B-09 and B-10 (and the technical calls under them): reverse B-07/B-08 to carry fb16e92 and 283432f/f4acc7d/89f4bfe (my default for B-09, and for B-10 if the architect does not settle the technical changes), or keep the rulings, which needs 0e6cd82 as a path-split pick, a Merge-back prep addition for VOICE_PROMPT and the test_wake_loop import line (architect), and a way past the `app/agents.py` 85 branch bar that is not a threshold edit by this plan.
- Task 8 not run. `split-trial` and both scratch worktrees were removed after the evidence runs (nothing left behind; `macos` c895ced, `origin/macos` 29e22ae, `personal` e917930 before this commit); the Task 8 closing line (tip and tree of a clean ruled trial) is not written.
- The Ruled trial section's evidence tree is exploratory (0e6cd82 path-split); it is not the Ruled trial. Rebuild scripts: /private/tmp/claude-501/-Users-atom-dev-void/42211a74-5354-433a-98cf-306ac660d2e9/scratchpad/build2.sh (stops at the first conflict) and explore.sh (skip-and-log).
- Untracked `.planning/phases/2/ADJUDICATION-plan-plan-74af430.json` and this reports dir (plan-1.1.md, plan-1.2.md rotated) are the orchestrator's; not committed.
