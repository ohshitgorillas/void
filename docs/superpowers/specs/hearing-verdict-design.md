Status: approved.

# Hearing verdict: one decision on every burst the mic hears

## Why

A burst the owner says can be dropped in 14 places, in 5 functions. Each one decides on its own, with its own checks and its own log line:

- `Wake.check`: speech share `app/server.py:1877`, transcription error `app/server.py:1890`, echo `app/server.py:1898`, noise `app/server.py:1907`, "ignored while talking" `app/server.py:1919`, voice gate `app/server.py:1934`, "ignored stray word" `app/server.py:1944`, "ignored: no hey Void" `app/server.py:1946`.
- `Wake.session`: bursts of 0.35 s or less are discarded unchecked `app/server.py:1747`.
- `Listen.run`: speech share `app/server.py:1478`, echo `app/server.py:1490`.
- `run_whisper_heard`: filler blanked for every caller `app/server.py:1104`. Unsure segments cut before any gate sees them `app/server.py:1100`.
- `session_message`: Claude's `[ignore]` drops the reply `app/server.py:3526`.

The same logic is copied in several places:

| Concern | Copies |
|---|---|
| "Enough speech to transcribe" check | 4: `app/server.py:1478`, `app/server.py:1816`, `app/server.py:1828`, `app/server.py:1877` |
| Filler word lists, which differ from each other | 2: `app/server.py:1103`, `app/gate.py:20` |
| Echo check, each caller with its own drop handling | 3: `app/server.py:1489`, `app/server.py:1834`, `app/server.py:1897` |
| Per-frame voice detector (rms, `Floor`, threshold, voiced count), with different constants | 3: `app/server.py:1196`, `app/server.py:1428`, `app/server.py:1741` |
| Drop output | 4 forms: `app/server.py:1490`, `app/server.py:1898`, `app/server.py:1903`, `app/server.py:1935`. Only 2 drops reach the page: `app/server.py:1491`, `app/server.py:1937` |
| Fake `Heard` in tests | 5: `tests/test_gate.py:59`, `tests/test_wake_loop.py:341`, `tests/test_echo.py:49`, `tests/test_listen_enrol.py:110`, `tests/scenes.py:628` |
| Speech-to-text patch sets in tests | 3: `tests/test_wake_loop.py:345`, `tests/test_echo.py:46`, `tests/scenes.py:734` |
| `hiss` test helper | 2: `tests/test_wake_loop.py:288`, `tests/test_listen_enrol.py:53` |
| `pieces` test helper | 2: `tests/test_wake_loop.py:296`, `tests/test_listen_enrol.py:95` |

The voiceprint stays on. Its check becomes one step of the single verdict.

## Modules

### `app/gate.py`: every keep-or-drop decision on a heard burst

It stays pure: no audio I/O and no model loads. `judge` runs its checks in a fixed order and returns at the first drop:

1. speech share: every kind, `"listen"` included, needs `MIN_SPEECH`; every kind but `"follow"` also needs `SPEECH_SHARE` of the burst
2. echo
3. stop phrase: a burst of kind `"over"` or `"peek"` whose text `stop_said` passes, or a burst heard while `talking` whose whole text matches `STOP_RE` and is not filler (`is_filler`), returns `Verdict(True, "kept", "barge", "")`; a filler such as "thanks" heard while he talks goes on to 4 and drops as noise
4. noise, every kind, `"listen"` included: empty text and a looping sentence always drop; filler drops unless `voice` is not None and at or above `cfg["voice_min"]`
5. while talking, skipped for `"listen"`: a `"peek"` drops as "while talking"; an `"over"` without a `WAKE_RE` match drops as "while talking"
6. wake word, skipped for `"listen"`, which is kept as `Verdict(True, "kept", "request", <the full text>)`: a `WAKE_RE` match while `talking` is `Verdict(True, "kept", "barge", "")`; a match otherwise is a `"request"` with the words after the wake word as `rest`; no match on any kind but `"follow"` drops as "no wake word"
7. stray word: a follow-up of one whitespace-separated word (`len(text.split()) < 2`) drops unless `cfg["voice_gate"]` is on and `voice` is not None and at or above `cfg["voice_min"]`; it then goes on to 8 and 9 like any follow-up
8. Whisper confidence, only when `cfg["voice_gate"]` is on, and skipped when `heard` is None: `heard.no_speech` at or above `NO_SPEECH` drops as "no speech"; `heard.logprob` below `MIN_LOGPROB` drops as "low confidence"
9. voiceprint, only when `cfg["voice_gate"]` is on: `voice` not None and below `cfg["voice_min"]` drops as "not your voice"

A follow-up past 9 is `Verdict(True, "kept", "follow", <the full text>)`. With `cfg["voice_gate"]` off, 8 and 9 keep everything.

It replaces:

- the old follow-up gate `_follow_legacy` (`app/gate.py:185`) and the bridge to it in `judge` (`app/gate.py:130`)
- the filler blanking at `app/server.py:1104`
- the four speech-share checks
- the drop branches of `Wake.check`, `Wake.stop_in` and `Listen.run`

`SPOKEN` and `note_spoken` stay in `server.py`, and `server.py` passes their text in.

```python
# app/gate.py
NO_SPEECH: float          # Whisper sure nobody talked
MIN_LOGPROB: float        # mean avg_logprob floor for a follow-up
SEG_LOGPROB: float        # per-segment floor for sure=True (now -1.0)
SEG_COMPRESSION: float    # per-segment compression-ratio ceiling (now 2.4)
MIN_SPEECH: float         # seconds of detected speech a burst needs (now 0.25)
SPEECH_SHARE: float       # share of the burst that must be speech (now 0.2)
NOISE_WORDS: frozenset    # the one filler list
STOP_RE: re.Pattern       # a whole text that is a stop phrase
WAKE_RE: re.Pattern       # "hey Void" and its mishearings; group 2 is the words after it
WHY = ("kept", "no speech", "echo", "noise", "while talking", "stray word",
       "no wake word", "low confidence", "not your voice")

@dataclass(frozen=True)
class Burst:
    text: str                  # what Whisper heard
    heard: object | None       # server.Heard, for a judged follow-up; else None
    speech: float              # speech_seconds of the burst
    seconds: float             # the burst's length
    voice: float | None        # voiceprint cosine, follow-ups only; None: not scored
    kind: str                  # "listen" | "wake" | "follow" | "over" | "peek"
    talking: bool              # he is talking now

@dataclass(frozen=True)
class Verdict:
    keep: bool
    why: str                   # one of WHY
    act: str                   # "request" | "follow" | "barge" | "drop"
    rest: str                  # the request text to send on ("" for barge and drop)

def spoken_enough(speech: float, seconds: float, kind: str) -> bool: ...
def sure(segments: list) -> list: ...                         # the one Whisper segment filter
def is_echo(heard: str, spoken: list[str]) -> bool: ...
def is_noise(heard: str) -> bool: ...                         # empty, filler or a looping sentence
def is_filler(heard: str) -> bool: ...                        # the whole text is a NOISE_WORDS phrase
def stop_said(text: str) -> bool: ...
def judge(b: Burst, spoken: list[str], cfg: dict) -> Verdict: ...
```

### `app/hearing.py`: gains the per-frame voice detector

It replaces `Floor` (`app/server.py:1172`) and the three frame loops' rms, threshold and voiced arithmetic. Each caller keeps its own constants and passes them in.

```python
# app/hearing.py
class Voicing:
    def __init__(self, low: float, over: float): ...          # threshold = max(low, floor * over)
    def frame(self, fr: bytes, soft: float, hold: bool = False) -> tuple[float, float, float, int]:
        """→ (rms, floor, threshold, voiced count 0–4)"""
```

### `app/server.py`: transcribes, scores and acts on the `Verdict`; decides nothing itself

On a `"barge"` verdict it stops him and publishes BUS `barge`. Where `gate.WAKE_RE` matches the burst's text, that event carries `listen=True` and `text` set to the match's group 2 stripped of `" .,!?"`, which the page sends on as a request (`app/static/index.html:1918`); otherwise `listen=False, text=""`.

It has one output function for verdicts:

```python
# app/server.py
def verdict_out(v: "gate.Verdict", said: str, voice: float | None, kind: str) -> None:
    """One stderr line per verdict, '[void] <why>: <said>' with the voice score. A follow-up verdict whose keep is
    false also publishes BUS gate_drop, shown on the page (app/static/index.html:1905). Never a file, store or count."""
```

### `tests/fakes.py`: the one home of hearing test doubles

It replaces the five `Heard` fakes, the three patch sets, and the `hiss` and `pieces` copies. The mics differ in behaviour and are not homed here: `tests/test_listen_enrol.py:75`, `tests/test_echo.py:311`, `tests/scenes.py:464`.

```python
# tests/fakes.py
def heard(text: str = "something was said here", sure: bool = True, seconds: float = 0.0): ...   # → server.Heard
def hiss(seconds: float, seed: int) -> bytes: ...
def pieces(pcm: bytes, ms: int = 20) -> list[bytes]: ...
def ears(server, text_for, speech_for=None) -> contextlib.ExitStack: ...  # patches speech_seconds, transcribe_pcm, transcribe_pcm_heard
```

## Homes

| Concern | Home | Forbidden elsewhere |
|---|---|---|
| Keep or drop a heard burst | `gate.judge` | any `return` that drops a burst in `server.py` other than one taken on a `Verdict` |
| Speech share and minimum speech | `gate.spoken_enough` | a `speech_seconds` comparison outside `gate` |
| Filler words | `gate.NOISE_WORDS` | any other filler list. `run_whisper_heard` blanks nothing |
| Whisper confidence thresholds | `gate` constants and `gate.sure` | a segment filter or logprob comparison in `server.py` |
| Echo, noise, stop-phrase and wake-word tests | `gate.is_echo`, `gate.is_noise`, `gate.stop_said`, `gate.STOP_RE`, `gate.WAKE_RE` | their definitions in `server.py` |
| Per-frame voice detection | `hearing.Voicing` | rms, floor or threshold arithmetic in a frame loop |
| Drop output | `server.verdict_out` | any other `print` of a verdict or `gate_drop` publish; any file, store, counter or history of drops |
| Hearing test doubles | `tests/fakes.py` | a `Heard(...)` literal, STT patch set, `hiss` or `pieces` in a test file |

## Order

Agents are given by role: `test-writer` for the tests, and the roster agent whose Writes holds `app/` for the code. That roster agent is not named because the roster was not surveyed.

1. **`gate` core lands.** Put the stubs above in place, build all of them but `judge` and `spoken_enough`, move the echo, noise and stop tests and the thresholds into `gate`, and make `server.py` import them. Files: `app/gate.py`, `app/server.py`, `tests/test_gate.py`, `tests/test_echo.py`. Agent: the `app/` roster agent; `test-writer` for the two test files.
2. **Every drop goes through `judge`.** Build `gate.spoken_enough` and `gate.judge` in `app/gate.py`, `judge` running the nine checks in the order under Modules, and remove `_follow_legacy` and its bridge. `Wake.check`, `Wake.heard`, `Wake.stop_in` and `Listen.run` build a `Burst`, call `gate.judge`, act on the `Verdict`, take a barge's request text from `gate.WAKE_RE`, and print through `verdict_out`. `run_whisper_heard` uses `gate.sure` and blanks nothing. Files: `app/gate.py`, `app/server.py`, `tests/test_gate.py`, `tests/test_wake_loop.py`, `tests/test_listen_enrol.py`. Agent: the `app/` roster agent; `test-writer` for the tests.
3. **`Voicing` lands.** `speech_span`, `Listen.run` and `Wake.session` use it, and `Floor` leaves `server.py`. Files: `app/hearing.py`, `app/server.py`, `tests/test_hearing.py`. Agent: the `app/` roster agent; `test-writer` for the test.
4. **`tests/fakes.py` lands** and the unit tests use it. Files: `tests/fakes.py`, `tests/test_gate.py`, `tests/test_wake_loop.py`, `tests/test_echo.py`, `tests/test_listen_enrol.py`. Agent: `test-writer`.
5. **Scenes use `fakes.heard`.** Files: `tests/scenes.py`. Agent: `test-writer`.
