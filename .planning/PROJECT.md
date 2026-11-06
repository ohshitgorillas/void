# Void (macOS fork)

## What This Is

Void is a voice-first desktop companion for Claude Code: a little orb on the desktop that hears "hey Void", gets
Claude Code to do the work in your project, shows it on a tiny terminal, and says how it went. Upstream is
PLAYER99-void/void (Windows and Linux); this repository, ohshitgorillas/void, is the macOS port, kept by its macOS
maintainer, who builds and tests Void on a Mac because upstream's author has none. The `macos` branch is what Mac
users install; the `personal` branch is the maintainer's own build, carrying unapproved visual changes and work in
progress on top of `macos`.

## Core Value

Void never throws away a real request from the owner and never acts on his own voice, and the fixes that get him
there reach Mac users on `macos` without anything unapproved riding along.

## Requirements

### Validated

- ✓ Voice loop: "hey Void", click or push-to-talk; follow-ups without the wake word; "stop" interrupts - v1.6.3.2
- ✓ Local speech: faster-whisper hearing and Kokoro voice (piper and espeak-ng fallbacks), nothing leaves the machine - v1.6.3.2
- ✓ Claude Code driver: one long-lived Claude per chat, approval before commands ("yes", "no", "always"), the little terminal held up while he works - v1.6.3.2
- ✓ Helpers: little Voids orbit him for subagents; a helper no longer brings up his terminal - v1.6.3.2
- ✓ Face and props: moods follow his words, skins and colours, petting, the notch at any screen edge - v1.6.3.2
- ✓ Screen: "what's on my screen", live view, explain what I copied - v1.6.3.2
- ✓ Instant commands built in (timer, volume, open app, reminders, media) and remembered facts ("remember my blog is in ...") - v1.6.3.2
- ✓ macOS port: PySide6 window, sounddevice audio, login item, Void.app and an unnotarized arm64 Void.dmg built in CI - v1.6.3.2
- ✓ Speaker and mic switching mid-sentence; quitting never hangs on the mic permission prompt - v1.6.3.2
- ✓ Upstream sync: `macos` merges upstream daily, tags a new version when app/VERSION changes, and builds its DMG - v1.6.3.2
- ✓ Hearing verdict: every heard burst is judged once by `gate.judge` (speech share, echo, stop phrase, noise, while talking, wake word, Whisper confidence); per-frame voice detection in `hearing.Voicing` - personal
- ✓ Pings from other Claude sessions batched into one turn with no model call (`notifier.PingBatch`); dropped clips shown as a faint spark - personal
- ✓ Markdown files read in a little notebook whose leaves flip; images in a window of their own - personal

### Active

Milestone v1.6.3.3.

- [ ] Separate `personal` from `macos`: bug fixes ship to `macos`, unapproved visual changes and features stay on `personal`
- [ ] Hearing judged against real logs: the owner's reported drops replayed as regression tests
- [ ] Replies after Void goes quiet are heard, and a reply never talks over him
- [ ] Void's own stop phrase, heard back from his speakers, never stops him
- [ ] Music and other voices in the follow-up window start no Claude turn, without dropping the owner
- [ ] The owner's own instant voice commands, and overrides for the built-ins (roonctl for music)
- [ ] A spiral flip notebook for reading markdown and a pencil for writing it
- [ ] A coverage gate in CI over the modules this fork added
- [ ] Ship v1.6.3.3 to Mac users with the fixes

### Out of Scope

- Pushing visual or feature changes to `macos` without upstream's approval - the maintainer ports and fixes; design is upstream's call
- Tests or coverage for upstream's own modules (server.py, window.py, quick.py, recall.py, approve.py, ...) - upstream ships no tests, and the code is not this fork's
- The voiceprint - removed by the owner's 26 Oct ruling: it could not tell the owner from Void's own echo (0.02-0.43 against 0.04-0.17)
- Notarizing the DMG - the README documents the Open Anyway path; not part of this milestone
- Windows and Linux builds - upstream owns them

## Context

- **Stack:** Python. `app/server.py` (4,153 lines, a stdlib `ThreadingHTTPServer`) serves one page,
  `app/static/index.html` (3,314 lines), shown in a PySide6 window (`app/window.py`; `window_win.py` on Windows).
  Hearing is faster-whisper; voice is kokoro-onnx. Install is `install.sh` with uv; the Mac app is built by
  `packaging/macos/build.sh` in `.github/workflows/macos.yml`.
- **Fork-owned modules** (absent upstream): `agents.py`, `langmark.py`, `macsys.py`, `gate.py`, `hearing.py`,
  `notifier.py`, `drops.py`. Everything else in `app/` is upstream's and merges in daily.
- **Branches:** `main` mirrors upstream; `macos` = upstream + the port + fixes, released through v1.6.3.2;
  `personal` is 113 commits ahead of `macos`, mixing fixes, unapproved visuals, features and dev tooling
  (`CLAUDE.md`, `.claude/`, `queues/`, `docs/superpowers/`, `docs/design/`). A 24 Oct triage of older branches is
  at `~/dev/void-branch-triage.md`.
- **In flight:** `stream/replies-after-quiet` (worktree `~/dev/void-replies`, 5 commits) and `stream/stop-echo`
  (worktree `~/dev/void-stop-echo`, design approved, not started). The instant-commands design
  (`docs/superpowers/specs/instant-commands-design.md`) is still marked proposed.
- **Tests:** about 38 pytest files, all the fork's (upstream has none): red tests written first for each design step,
  scene tests through the real hearing path (`tests/scenes.py`), page tests on installed Chrome, Cocoa window tests.
  Run with `uvx pytest`. No workflow runs them, and no coverage is measured.
- **Hearing is the project's major issue.** Between 22 Oct and 5 Nov about 50 commits touched the 9 hearing files and
  their tests, under four designs (context-bleed, hearing verdict, quiet replies, own stop) and three queues. Text-only
  echo matching gave way to two echo cancellers (livekit's APM turned the owner's first second down 6-20 dB, so the
  fork wrote its own NLMS canceller in 597e094), then to timing spans. The voiceprint lasted about a day (c378787).
  "Only stop words while he talks" (cb86ec3) fixed Void stopping himself, but it dropped the owner's words. The same
  failures kept coming back: Void acting on his own voice, the owner's words dropped, stop failing or Void stopping
  himself, and music let through. What the history points to: no single record of when Void's sound played, which is
  why "talking" is guessed separately by `Speaker` and in five places on the page; heard bursts with no word times
  (Whisper runs without them); and a test harness that proved the old rules while the real bugs turned up in the
  owner's logs. `void drops` (`app/drops.py`) replays a log. In flight: `stream/replies-after-quiet` (5 commits, not
  merged) and `stream/stop-echo` (18 files changed, +1686/-105, uncommitted in `~/dev/void-stop-echo`). After the
  voiceprint was removed, nothing local tells the owner from music in the follow-up window. The owner, 26 Oct, on
  earlier agents: they "added more machinery instead: a verdict gate, a voiceprint, enrolment rules, echo rules."
  This is a lesson from that episode, not a standing rule.
- **Rough edges:** `server.py` is one large file that upstream also edits, so fixes there have to merge cleanly with
  upstream's daily changes. The upstream-sync tags only when app/VERSION changes, so a fork-only release such as
  v1.6.3.3 is not tagged by it.

## Constraints

- **Upstream compatibility**: changes to upstream's files stay small and merge cleanly - `macos` merges upstream every day
- **Approval**: visual and feature changes need upstream's approval before reaching `macos` - Mac users get upstream's design
- **Platform**: Apple Silicon, macOS 14+ for the DMG - the CI runner and the README's stated target
- **Privacy**: speech stays on the machine - a promise in the README
- **A dropped real request is the worst hearing failure**: hearing something it shouldn't is the lesser cost - the owner's 26 Oct ruling

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| `macos` tracks upstream by a daily merge, not a rebase | Mac users get upstream's fixes within a day; history stays mergeable both ways | ✓ good |
| Fork releases carry a fourth version part (v1.6.3.2) | Upstream owns the three-part version; the fork ships between upstream releases | ✓ good |
| Every heard burst is judged once, by pure `gate.judge` | Drops scattered over `server.py` made hearing bugs untraceable (hearing-verdict design) | ✓ good |
| The voiceprint is gone from the follow-up decision | Owner ruling 26 Oct: its scores overlapped Void's own echo | ✓ good |
| Pings are batched into one turn with no model call | Each ping woke the long main session (context-bleed design) | ✓ good |
| Hearing test doubles live only in `tests/fakes.py` | One home stops test doubles drifting apart (hearing-verdict design step 4) | ✓ good |
| Coverage is measured on fork-owned modules only, 85% lines and branches | Upstream's code is not this fork's to test; the floor matches the owner's other repos | - pending |

---
*Last updated: 2026-11-05 after /cad-adopt*
