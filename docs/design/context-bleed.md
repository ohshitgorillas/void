Status: proposed, for the owner's approval.

# Context bleed: keep the long main session asleep

## Why

Every turn of Void's main session re-reads its whole context. Two things wake it that rarely need it:

- **Follow-ups without "hey Void".** `Wake.check` (`app/server.py:1745-1754`) publishes any 2+ word clip heard in the
  follow window as `wake follow=True`; `Handler.ask` (`app/server.py:3902`) prefixes `FOLLOW_NOTE` and sends a full
  turn so Claude can answer `[ignore]`. The only local filters are `speech_seconds`, the `sure` thresholds in
  `run_whisper` (`app/server.py:1075-1077`), `is_echo` and `is_noise`. Music lyrics and other people pass all four.
- **Pings.** `InboxFollower.deliver` (`app/server.py:3456`) sends every `claude-ping` line as its own turn. 480 lines
  today; the biggest sources are `[claude] void Stop` (every Claude session in this repo ending), `opal:hqp-*`, and
  lead step pings. Separately, Claude Code itself runs a turn in the main process for each background subagent's
  `task-notification` (`app/agents.py:265`); Void cannot hold those back from outside the process.

Shared concerns and their current copies:

- Whisper's confidence signal: computed per segment inside `run_whisper` (`app/server.py:1070-1077`) and thrown away;
  callers get a string.
- One-shot fast-model calls: `summarize_command` (`app/server.py:538`) is the only copy; the notifier would be the second.
- "Is this the owner talking": `MicAuto.learn` call sites (`app/server.py:1405, 1744, 1750`) are already the only
  places a clip is known to be the owner's.

## Modules

`app/server.py` — STT result carries its confidence (replaces the string-only path).

```python
@dataclass
class Heard:
    text: str
    logprob: float        # mean avg_logprob over kept segments (-inf when none)
    no_speech: float      # max no_speech_prob over kept segments (1.0 when none)
    seconds: float        # speech_seconds of the clip

def run_whisper_heard(audio, beam=None, hint=None, sure=False) -> Heard: ...
def run_whisper(audio, **kw) -> str:          # unchanged signature: run_whisper_heard(...).text
def transcribe_pcm_heard(pcm: bytes, **kw) -> Heard: ...
```

`app/voiceprint.py` (new) — the owner's voiceprint: local speaker embeddings via onnxruntime (already installed with
faster-whisper), model fetched on first use like `kokoro_fetch.py`.

```python
class Voiceprint:
    def __init__(self, path: Path, model_dir: Path): ...
    available: bool; why: str                  # like hearing.Canceller: off/unavailable and why, said once
    enrolled: int                              # clips folded into the print
    def enroll(self, pcm: bytes) -> None: ...  # running mean, capped at 30 clips; saved to path
    def score(self, pcm: bytes) -> float | None:   # cosine to the print; None when unavailable or enrolled < MIN_ENROLL
```

`app/gate.py` (new) — the one decision on a follow-up clip without the wake word. Pure: no audio I/O, no model loads.

```python
@dataclass
class Verdict:
    keep: bool
    why: str              # "low confidence", "no speech", "not your voice", "kept"

def judge(heard: Heard, voice: float | None, cfg: dict) -> Verdict: ...
```

`app/notifier.py` (new) — pings in, at most one turn out per quiet spell.

```python
class PingBatch:                                  # pure: clock injected, no threads
    def __init__(self, quiet_s: float, hold_s: float, clock=time.monotonic): ...
    def add(self, line: str) -> None: ...
    def due(self) -> list[str] | None: ...        # the batch once quiet_s passed since the last line, or hold_s since the first

def triage(lines: list[str], ask=oneshot) -> str | None: ...   # None: nothing needs the owner; else one short digest
```

`app/agents.py` — gains the one home for fast-model one-shots.

```python
def oneshot(prompt: str, *, binary: str, cwd: str, model="haiku", timeout=15) -> str | None: ...
```

## Homes

| Concern | Home | Not allowed elsewhere |
|---|---|---|
| Whisper confidence numbers and thresholds | `run_whisper_heard` (numbers), `gate.judge` (thresholds for follow-ups) | No caller reads segments itself |
| Owner's voice | `voiceprint.Voiceprint`; enrolled only beside `MicAuto.learn` on wake-word and Listen clips | Never enrolled from follow-ups or clips the gate judged |
| Keep/drop of a follow-up | `gate.judge`, called once in `Wake.check`'s follow branch | Wake-word clips never reach it; `Handler.ask` adds no filter |
| Ping batching | `notifier.PingBatch` | `InboxFollower` only feeds it and delivers its result |
| Fast-model one-shot | `agents.oneshot` | `summarize_command` and `triage` call it; no other `subprocess.run([binary, "-p", ...])` |
| Config | `DEFAULTS` in `app/server.py`: `voice_gate` (on), `voice_min`, `ping_quiet_s`, `ping_hold_s` | |
| "off/unavailable and why" | `Voiceprint.why`, reported by `void doctor` and diagnostics the way `echo_report` does | |

The echo canceller is untouched: the gate runs on the same cleaned PCM `Wake.check` already gets, after `is_echo`.

Latency: the follow branch already waits for one Whisper pass; the embedding runs on the same clip once (unmeasured;
target under 100 ms on the Mac CPU, checked by step 4's test).

## Order

Each step: one worker, one done-check, one commit. A lead dispatches them in this order.

1. `Heard` and `run_whisper_heard` / `transcribe_pcm_heard`; `run_whisper` keeps its signature. Files: `app/server.py`,
   `tests/test_hearing.py`. Done: suite green, `Heard` numbers present for a fixture clip.
2. `agents.oneshot`; `summarize_command` uses it. Files: `app/agents.py`, `app/server.py`, `tests/test_agents.py`.
   Done: no `[binary, "-p", "--model"` left outside `oneshot`; suite green.
3. `voiceprint.py` with model fetch and `why`. Files: `app/voiceprint.py`, `tests/test_voiceprint.py`,
   installers only if the model must ship. Done: the owner-voice fixtures score above the Kokoro and room-music
   fixtures.
4. `gate.judge` wired into `Wake.check`'s follow branch; enrollment beside the three `MicAuto.learn` calls; config
   keys; doctor line. Files: `app/gate.py`, `app/server.py`, `tests/test_gate.py`, `tests/test_wake_loop.py`.
   Done: room-music follow-up dropped, owner follow-up kept, wake-word clip never judged, judge+score under budget.
5. `PingBatch` and `triage`. Files: `app/notifier.py`, `tests/test_notifier.py`. Done: fake-clock tests for quiet and
   hold; `triage` returns None on a SKIP answer and on a failed call falls back to a plain digest.
6. `InboxFollower` feeds `PingBatch` and delivers one `session_message` per due batch (or none). Files:
   `app/server.py`, `tests/test_inbox.py`. Done: five lines in one quiet spell give at most one turn.

## Decisions for the owner

1. **Before the voiceprint has enough of you.** Recommend: confidence-only gate until 5 wake-word/Listen clips are
   enrolled, then voice too, all automatic. Alternative: a one-time "read these three sentences" enrollment in
   settings (sure from day one, but a step you must do).
2. **What you see when a clip is dropped.** Recommend: log line only (`[void] gate dropped: not your voice`).
   Alternative: a faint spark on the page so you know he heard something (costs a page change and a test).
3. **Ping triage.** Recommend: batch over a quiet spell (20 s quiet, 2 min max hold), then one Haiku one-shot decides
   "nothing" or a two-line digest; only a digest wakes the main session. Alternative: batch only, no model, the whole
   batch as one turn (simpler, still wakes the session once per spell).
4. **Background subagent notifications.** Void cannot stop Claude Code running a turn per `task-notification`.
   Recommend: Void's own instructions to the main session say to run long jobs as detached `claude -p` jobs that
   report with `claude-ping`, so they land in the batch. Alternative: leave them (they are usually results you asked
   for).
5. **Speaker model.** Recommend: a small ONNX speaker-embedding model (about 25 MB, fetched on first use) on
   onnxruntime, which faster-whisper already installs. Alternative: resemblyzer (pulls in torch, hundreds of MB).
