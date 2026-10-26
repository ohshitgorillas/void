Status: approved by the owner.

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

`app/notifier.py` (new) — pings in, at most one turn out per quiet spell. No model call.

```python
class PingBatch:                                  # pure: clock injected, no threads
    def __init__(self, quiet_s: float, hold_s: float, clock=time.monotonic): ...
    def add(self, line: str) -> None: ...
    def due(self) -> list[str] | None: ...        # the batch once quiet_s passed since the last line, or hold_s since the first

def digest(lines: list[str]) -> str: ...          # the batch as one message, one line per ping, in arrival order
```

`DEFAULTS["voice_prompt"]` in `app/server.py` — tells the main session to run long jobs as detached `claude -p`
processes (Claude only) that report with `claude-ping`, not as background subagents, so their results arrive through
the batch.

`app/static/index.html` — a faint spark when the gate drops a clip, on a new bus event `{"t": "gate_drop"}`.

## Homes

| Concern | Home | Not allowed elsewhere |
|---|---|---|
| Whisper confidence numbers and thresholds | `run_whisper_heard` (numbers), `gate.judge` (thresholds for follow-ups) | No caller reads segments itself |
| Owner's voice | `voiceprint.Voiceprint`; enrolled only beside `MicAuto.learn` on wake-word and Listen clips | Never enrolled from follow-ups or clips the gate judged |
| Keep/drop of a follow-up | `gate.judge`, called once in `Wake.check`'s follow branch | Wake-word clips never reach it; `Handler.ask` adds no filter |
| Ping batching | `notifier.PingBatch` and `notifier.digest` | `InboxFollower` only feeds it and delivers its result |
| Showing a dropped clip | `Wake.check` publishes `gate_drop` with the log line; the page draws the spark | No other code path publishes it |
| How long jobs report back | `DEFAULTS["voice_prompt"]` | |
| Config | `DEFAULTS` in `app/server.py`: `voice_gate` (on), `voice_min`, `ping_quiet_s`, `ping_hold_s` | |
| "off/unavailable and why" | `Voiceprint.why`, reported by `void doctor` and diagnostics the way `echo_report` does | |

The echo canceller is untouched: the gate runs on the same cleaned PCM `Wake.check` already gets, after `is_echo`.

Latency: the follow branch already waits for one Whisper pass; the embedding runs on the same clip once (unmeasured;
target under 100 ms on the Mac CPU, checked by step 4's test).

## Order

Each step: one worker, one done-check, one commit. Two streams; within a stream the steps run in order.

Gate stream:

1. `Heard` and `run_whisper_heard` / `transcribe_pcm_heard`; `run_whisper` keeps its signature. Files: `app/server.py`,
   `tests/test_hearing.py`. Done: suite green, `Heard` numbers present for a fixture clip.
2. `voiceprint.py` with model fetch and `why`. Files: `app/voiceprint.py`, `tests/test_voiceprint.py`,
   installers only if the model must ship. Done: the owner-voice fixtures score above the Kokoro and room-music
   fixtures.
3. `gate.judge` wired into `Wake.check`'s follow branch; enrollment beside the three `MicAuto.learn` calls; confidence
   only until 5 clips are enrolled; config keys; doctor line; `gate_drop` published with the log line. Files:
   `app/gate.py`, `app/server.py`, `tests/test_gate.py`, `tests/test_wake_loop.py`. Done: room-music follow-up
   dropped, owner follow-up kept, wake-word clip never judged, judge+score under budget.
4. The faint spark on `gate_drop`. Files: `app/static/index.html`, `tests/test_page_sparks.py`. Done: a `gate_drop`
   event draws one faint spark that fades; existing spark tests green.

Ping stream:

5. `PingBatch` and `digest`. Files: `app/notifier.py`, `tests/test_notifier.py`. Done: fake-clock tests for quiet
   (20 s) and hold (2 min).
6. `InboxFollower` feeds `PingBatch` and delivers one `session_message` of `digest(batch)` per due batch. Files:
   `app/server.py`, `tests/test_inbox.py`. Done: five lines in one quiet spell give exactly one turn.
7. `DEFAULTS["voice_prompt"]` tells the main session to run long jobs as detached Claude processes that report with
   `claude-ping`. Files: `app/server.py`, one test of the prompt text. Done: the prompt says it; suite green.
