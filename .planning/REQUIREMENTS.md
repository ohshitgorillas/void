# Requirements: Void (macOS fork)

**Defined:** 2026-11-05
**Core Value:** Void never throws away a real request from the owner and never acts on his own voice, and the fixes that get him there reach Mac users on `macos` without anything unapproved riding along.

## Active

Committed scope. Each maps to exactly one roadmap phase.

### Test gate

- [ ] **TEST-01**: Maintainer sees every push to `macos` or `personal` run the test suite in CI, and a red suite or a fork-owned module below 85% lines or branches fails the run

### Branch split

- [ ] **SPLIT-01**: Maintainer can read, for every commit on `personal` not in `macos`, whether it is a bug fix bound for `macos` or stays on `personal` (visual, feature or dev tooling), with each borderline call listed for a ruling
- [ ] **SPLIT-02**: Maintainer has a branch off `macos` carrying every commit classed as a fix, and none of the visual changes, features or dev tooling (`CLAUDE.md`, `.claude/`, `queues/`, `docs/superpowers/`, `docs/design/`)
- [ ] **SPLIT-03**: Maintainer can land a new fix on `macos` first and bring it to `personal` by a merge, so the split never has to be redone by hand

### Hearing

- [ ] **HEAR-05**: Owner can replay the bursts of a real `server.log` through today's hearing and see each one kept or dropped and why, and the requests the owner has reported dropped ("It's good", "Yes, do it", "Yes, God damn" and the rest) run as regression tests
- [ ] **HEAR-01**: User's reply said after Void has gone quiet is heard, unless his voice or its room ring was in the air when it was said
- [ ] **HEAR-02**: User's reply heard while Void is still speaking waits until he finishes and is then answered; only a stop phrase or his name said over him cuts him off
- [ ] **HEAR-03**: User never sees Void stop himself because the mic heard his own stop phrase played back, during the line or in its ring after
- [ ] **HEAR-04**: User can still stop Void by saying a stop phrase over him, even right after Void said that word himself
- [ ] **HEAR-06**: User playing music with lyrics, or with other people talking nearby, does not start a Claude turn in the follow-up window, and none of the owner's replies in the replay corpus is dropped because of it

### Instant commands

- [ ] **CMD-01**: User can add a spoken phrase that runs a command of their choosing at once, without going to Claude
- [ ] **CMD-02**: User can point a built-in instant command, such as "pause the music", at a different command, such as `roonctl`

### Props

- [ ] **PROP-01**: User sees Void hold a spiral-topped flip notebook while he reads a markdown file, its pages flipping up and over, with the text reversed when "terminal faces me" is off
- [ ] **PROP-02**: User sees a pencil wiggle as if scribbling on that notebook while Void writes a markdown file, behind the notebook when "terminal faces me" is off and in front when it is on

### Release

- [ ] **REL-01**: Mac user can download a v1.6.3.3 Void.dmg from the fork's latest release that carries the fixes on `macos`

## v2 Requirements

Deferred. Tracked, not in the current roadmap.

### Props

- **PROP-03**: User sees Void do something of his own while Claude Code compacts ("tidy up") - the owner has not yet decided what it looks like

## Out of Scope

| Feature | Reason |
|---------|--------|
| Visual or feature changes on `macos` | They need upstream's approval first; they stay on `personal` |
| Tests or coverage for upstream's modules | Upstream ships no tests and the code is not this fork's |
| The voiceprint | Removed by the owner's 26 Oct ruling: it could not tell the owner from Void's own echo |
| Notarizing the DMG | The README documents Open Anyway; not this milestone |
| Windows and Linux builds | Upstream owns them |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| TEST-01 | Phase 1 | Complete |
| SPLIT-01 | Phase 2 | Complete |
| SPLIT-02 | Phase 2 | Complete |
| SPLIT-03 | Phase 2 | Complete |
| HEAR-05 | Phase 3 | Complete |
| HEAR-01 | Phase 4 | Complete |
| HEAR-02 | Phase 4 | Complete |

Bare headers - `/cad-plan` seeds a row per requirement when its phase is planned (`references/req-traceability.md`).

---
*Last updated: 2026-11-05 after /cad-adopt*
