# Phase 2: Branch split - Context

Gathered: 2026-11-07
Feeds: /cad-plan 2

## Scope boundary

In: a written classification of every commit in `macos..personal` (155: 137 non-merge plus 18 merges, not the
roadmap's 113, since Phase 1 landed on `personal`), with a borderline list for the owner's ruling; a fix branch off
local `macos` (c895ced) carrying every commit classed fix; the fix branch merged into local `macos`, and local `macos`
merged into `personal`.
Out: pushing `origin/macos` (only at a version bump, once verified and tested - Phase 7); pushing `personal` or the
fix branch without the owner's word in that turn; `stream/replies-after-quiet` (Phase 4), `stream/stop-echo`,
`ci-debug/fake-servers` and the `.claude/worktrees/agent-*` branches; changes to the Phase 1 `tests` job or coverage
policy.
Deferred: None
Plan shape: multiple plans, same phase - /cad-plan splits it (e.g. classification with the owner's borderline
rulings first, then build, verify and merge).

## Durable decisions

- D-01 (Classification): The hearing stack is fix-bound: `gate.judge`, `hearing.Voicing`, `void drops`
  (`drops.py`), the echo cancellers and ping batching (`notifier.py`) go on the fix branch and ship to Mac users at
  the version bump once phases 3-6 have verified them. Owner ruling 2026-11-07 ("we ship when the version bumps, aka
  when things are done and verified"). Evidence: `git cat-file -e macos:app/{gate,hearing,drops,notifier}.py` fails
  for all four; 14 non-merge commits in `macos..personal` touch them; ROADMAP Phase 7 criterion 1; Phase 1 D-08 floor
  names all 7 modules.
- D-02 (Classification): The Phase 1 CI and tests ride the fix branch - `.github/workflows/tests.yml`,
  `.github/ci/`, `.github/cadence/`, `tests/`, `tests/requirements.txt` - so the `tests` job runs on `macos` and
  after upstream-sync merges (Phase 1 D-09). `.planning/` is dev tooling and stays on `personal`, though SPLIT-02's
  path list does not name it. Owner ruling 2026-11-07. Evidence: `.planning/phases/1/CONTEXT.md` D-09;
  `.planning/REQUIREMENTS.md` SPLIT-02.
- D-03 (Landing): Work may merge into local `macos` at any time, but `origin/macos` is pushed only at a version bump,
  when the work is done, verified and thoroughly tested. Owner ruling 2026-11-07 ("it can go into macos locally, it
  just doesn't get pushed until verified and tested"). Evidence: `.github/workflows/upstream-sync.yml` publishes from
  `macos`; `origin/macos` is 29e22ae, local `macos` c895ced (one unpushed commit already).
- D-04 (Flow): From now on a new fix, including phases 3-6, lands on local `macos` first and reaches `personal` by
  merging `macos` into `personal`; the split is never redone by hand (SPLIT-03). Evidence:
  `.planning/REQUIREMENTS.md` SPLIT-03; ROADMAP Phase 7 criterion 1.

## Decisions

- D-05 (Population): The classification covers all 155 commits in `macos..personal`, each exactly once; each of the
  18 merges is its own row, classed "merge: follows its parents". Evidence: `git rev-list --count macos..personal`
  (155); `git log --merges macos..personal` (18).
- D-06 (Classification): Visual and feature commits stay on `personal` - the notebook leaves (`6537fdb`), the image
  window and the other `app/static` visuals among them. Each borderline call is listed in the classification for the
  owner's ruling; the planner makes the technical class calls. Evidence: PROJECT.md Constraints (upstream approval);
  15 non-merge commits touch `app/static`.
- D-07 (Landing): Phase 2 merges the fix branch into local `macos`, then local `macos` into `personal`; pushing
  `personal` or the fix branch needs the owner's word in that turn. Evidence: ROADMAP Phase 2 criterion 4.
- D-08 (Construction): The fix branch is built by cherry-picking the fix commits onto local `macos` (c895ced) in
  their original order. `c378787` (voiceprint removal) is the one commit mixing app code with personal-only paths and
  goes in without its personal-only changes. The branch is never cut from `personal` and reverted: 18 merges sit in
  the range. Evidence: per-commit path map from the analyzer pass; `git log --merges macos..personal`.
- D-09 (Gate): The `tests` job and `.github/cadence/coverage-policy.json` are unchanged; under D-01 and D-02 all 7
  `include` modules exist on the fix branch. Evidence: `.github/cadence/coverage-policy.json`;
  `.github/ci/coverage-modules.mjs`.
- D-10 (Scope): `stream/replies-after-quiet` (5 commits ahead, 44 behind `personal`), `stream/stop-echo` (0 ahead,
  already in `personal`), `ci-debug/fake-servers` and the agent worktree branches are not touched; the replies
  commits are Phase 4's. Evidence: `git rev-list --count personal..<branch>`; `git worktree list`.

## Acceptance criteria

- [ ] AC1: A classification file lists each SHA in `macos..personal` exactly once with a class of fix, visual,
  feature, dev tooling or merge; comparing its SHA column with `git rev-list macos..personal` shows no SHA missing
  and none duplicated; a "Borderline" section lists each call for the owner's ruling
- [ ] AC2: `git diff --name-only c895ced..<fix branch>` lists no path under `CLAUDE.md`, `.claude/`, `queues/`,
  `docs/superpowers/`, `docs/design/` or `.planning/`
- [ ] AC3: every commit classed fix has exactly one author, author-date and subject match in `git log <fix branch>`,
  and every commit classed visual or feature has none and is marked `+` by `git cherry <fix branch> personal`
  [amended by docs/superpowers/specs/branch-split-construction-design.md: `git cherry` `-` fails for path-split,
  already-on-macos and context-drifted fix rows]
- [ ] AC4: On the fix branch, `python3 -m py_compile app/*.py` exits 0, and the two accepted commands from
  `.github/cadence/coverage-policy.json` exit 0 with the checker reporting all 7 `include` modules meeting 85 for
  lines and branches
- [ ] AC5: `git merge-base --is-ancestor <fix branch> macos` exits 0, and `origin/macos` still points at 29e22ae
- [ ] AC6: `git merge macos` on `personal` completes with no conflict, and `git diff <personal before merge> personal`
  shows no changed file [`<personal before merge>` is Plan 2's `.gitignore` reorder commit `R`, per
  docs/superpowers/specs/branch-split-construction-design.md]

## Flagged assumptions

- The cherry-picks are copies of commits already on `personal`, so merging `macos` back can still conflict, or
  re-apply a hunk, wherever a later personal-only commit changed the same lines - likely in `app/server.py` (+512) and
  `app/static/index.html` (+309) - Likely; if wrong: AC6 fails, and the plan needs a trial merge in a scratch
  worktree before the real one, with the cherry-pick set or order adjusted rather than resolving conflicts by hand.
- The fix branch's name is the planner's call - Confident; if wrong: renaming it is one command.
- The local coverage run for AC4 is heavy on Slate and is disclosed before it runs - Likely; if wrong: AC4 is proved
  from the `tests` job instead, which runs only once `macos` or `personal` is pushed.
- The ROADMAP's Phase 2 goal still says 113 commits; the real count is 155 (D-05) - Confident; if wrong: nothing,
  the wording is stale and `/cad-phase edit 2` can correct it.
- Whether upstream (PLAYER99-void/void) would take fixes as PRs rather than only through `macos` is unknown - Unclear;
  if wrong: nothing in this phase, since it touches no remote.
