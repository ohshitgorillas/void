# Roadmap: Void (macOS fork)

## Overview

v1.6.3.3 is mostly about hearing. Since 22 Oct, about 50 commits under four designs kept fixing one hearing failure
by causing another, and the real bugs kept turning up in the owner's logs rather than in the tests. The coverage gate
comes first, because every later phase lands code that it holds, and the branch split second, so fixes have a clean
path to `macos`. Hearing then starts with a replay of the owner's real logs, so every later hearing change is judged
against what actually went wrong, not against the old rules. The two in-flight streams follow, each built on one
record of when Void's sound played. Last is the follow-up window's music problem, which nothing has addressed since
the voiceprint was removed. The release ships the fixes. Instant commands and the notebook props stay on `personal` and come
after it.

## Phases

- [ ] **Phase 1: Coverage gate** - CI runs the suite on macOS and holds the fork's own modules to 85% lines and branches
- [ ] **Phase 2: Branch split** - every `personal` commit classed; fixes on a branch off `macos`; fixes flow `macos` -> `personal` from now on
- [ ] **Phase 3: Real-log replay** - the owner's logged bursts replayed through hearing; every reported drop a regression test
- [ ] **Phase 4: Replies after quiet** - one record of when Void is making sound; a reply once he is quiet is heard, and none talks over him
- [ ] **Phase 5: Own stop is echo** - Void's own "stop" heard back never stops him; the owner's still does
- [ ] **Phase 6: Music in the follow-up window** - music and other voices start no Claude turn, and the owner is never dropped for it
- [ ] **Phase 7: Release v1.6.3.3** - the fixes on `macos`, tagged, with a DMG Mac users can download
- [ ] **Phase 8: Instant commands** - the owner's own spoken commands and overrides for the built-ins, on `personal`
- [ ] **Phase 9: Notebook and pencil** - spiral flip notebook for reading markdown, wiggling pencil for writing it, on `personal`

## Phase Details

### Phase 1: Coverage gate
**Goal:** The existing suite runs unattended on a macOS runner, and the fork-owned modules meet the accepted 85% lines and branches floor
**Depends on:** Nothing (first phase)
**Requirements:** TEST-01
**Success Criteria:**
1. A workflow under `.github/workflows/` has a job named `tests` on `macos-15` that runs both accepted commands from `.github/cadence/coverage-policy.json` on pushes to `macos` and `personal`
2. `planning.mjs test-policy check --root .` returns `gate_found: true`
3. `coverage.json` from that job shows every file in `testing.coverage.include` at or above 85% lines and 85% branches, and the report check exits 0
4. A commit that removes the tests for one fork-owned module makes the `tests` job fail, naming that module

### Phase 2: Branch split
**Goal:** The 113 commits on `personal` are sorted into fixes and personal-only work, the fixes sit on a branch off `macos`, and new fixes reach `personal` by merging from `macos`
**Depends on:** Phase 1
**Requirements:** SPLIT-01, SPLIT-02, SPLIT-03
**Success Criteria:**
1. A written classification lists every commit in `macos..personal` exactly once, as fix, visual, feature or dev tooling, with each borderline call listed for the owner's ruling
2. The fix branch, based on `macos`, contains every commit classed as a fix and no change under `CLAUDE.md`, `.claude/`, `queues/`, `docs/superpowers/` or `docs/design/`, and adds no visual or feature commit
3. The `tests` job and `python3 -m py_compile app/*.py` pass on the fix branch
4. Merging `macos` (with the fix branch merged in) into `personal` gives no conflicts and changes no file that only `personal`'s own work touched

### Phase 3: Real-log replay
**Goal:** Hearing is judged against what the owner actually said: real `server.log` bursts replay through today's `gate.judge`, and each drop the owner reported is a test that fails until it is fixed
**Depends on:** Phase 2
**Requirements:** HEAR-05
**Success Criteria:**
1. `void drops` run on a real `server.log` prints, for each burst, its text, kept or dropped, and the `gate.judge` reason, and replaying the same log twice prints the same lines
2. A regression set holds every drop the owner reported ("It's good", "Yes, do it", "Yes, God damn", the 26 Oct follow-ups and the rest found in the logs), each marked with the verdict the owner expects
3. The suite runs that set; each case that today's hearing still gets wrong fails, naming the phase meant to fix it, and none is skipped
4. `gate.judge` is still the one place a burst is dropped

### Phase 4: Replies after quiet
**Goal:** Land `stream/replies-after-quiet` on one record of when Void is making sound, shared by the native `Speaker` and the page's player, replacing the separate guesses
**Depends on:** Phase 3
**Requirements:** HEAR-01, HEAR-02
**Success Criteria:**
1. The replay set's "replied after he went quiet" cases ("It's good", "Yes, do it") pass: kept and answered, not dropped as echo
2. A scene where Void's own line is heard back while it plays, or within `ECHO_TAIL` after, is dropped as echo
3. A follow-up kept while Void is still speaking is answered only after his line ends, and the line plays to its end; a stop phrase or "Void" said over him still cuts him off
4. Both voice paths read "is he making sound" from one record: the page's five separate "finished speaking" tests and `speaking_until` are gone

### Phase 5: Own stop is echo
**Goal:** Finish the own-stop work started in `~/dev/void-stop-echo`: a stop phrase Void plays is judged as echo by when its words played, on the Phase 4 record, and the owner's own stop still barges
**Depends on:** Phase 4
**Requirements:** HEAR-03, HEAR-04
**Success Criteria:**
1. A scene where Void says a line containing "stop" and the mic hears it back, during the line or in the ring after, through `Wake.stop_in` and `Wake.check`, does not stop him
2. A scene where the owner says "stop" over Void more than `ECHO_WORD` after Void played that word stops him, and a measured scene, not a guess, sets `ECHO_WORD`
3. The same holds on both voice paths, the native `Speaker` and the page's own player
4. Every replay-set case passes that passed at the end of Phase 4

### Phase 6: Music in the follow-up window
**Goal:** Music with lyrics and other people's voices in the follow-up window start no Claude turn, without dropping the owner
**Depends on:** Phase 5
**Requirements:** HEAR-06
**Success Criteria:**
1. A scene of room music with lyrics and no wake word, played through the follow-up window, starts no Claude turn
2. A scene of another person talking nearby in the follow-up window starts no Claude turn
3. Every owner reply in the replay set is still kept; a change that drops one fails the suite
4. A burst dropped as music or another voice is logged with one `gate.judge` verdict line naming why, and `void drops` replays it with the same verdict

### Phase 7: Release v1.6.3.3
**Goal:** Every fix is on `macos`, tagged v1.6.3.3, with its DMG attached to the fork's release
**Depends on:** Phase 6
**Requirements:** REL-01
**Success Criteria:**
1. `macos` contains the fix branch and phases 3 to 6, and `git log macos` shows no commit classed visual, feature or dev tooling
2. Tag `v1.6.3.3` points at a commit on `macos`, and `app/VERSION` there still reads upstream's `1.6.3` (the `macos` workflow writes the tag's version into the build)
3. The `macos` workflow's `build` and `tests` jobs both pass for the tag, and the fork's latest release offers `Void.dmg`
4. A Void.app installed from that DMG reports version 1.6.3.3 in `/api/state`

### Phase 8: Instant commands
**Goal:** The owner can add their own instant voice commands and point the built-ins at other programs; the work stays on `personal`
**Depends on:** Phase 2
**Requirements:** CMD-01, CMD-02
**Success Criteria:**
1. With an entry mapping "pause the music" to `roonctl pause`, saying "hey Void, pause the music" runs `roonctl pause` and no Claude turn starts
2. A new phrase added by the owner runs its command, and saying it never reaches Claude
3. A built-in with no override still behaves as before (its existing tests pass unchanged)
4. None of this phase's commits appear on `macos`

### Phase 9: Notebook and pencil
**Goal:** Void holds a spiral flip notebook when reading markdown and scribbles with a pencil when writing it, following the "terminal faces me" setting; the work stays on `personal`
**Depends on:** Phase 2
**Requirements:** PROP-01, PROP-02
**Success Criteria:**
1. A page test reading a markdown file shows a notebook with a spiral along its top whose page flips up and over it, not the black-backed notebook
2. With "terminal faces me" off the notebook's text renders reversed, and with it on the text reads normally
3. A page test writing a markdown file shows a pencil that moves while writing, drawn behind the notebook with "terminal faces me" off and in front with it on
4. None of this phase's commits appear on `macos`
