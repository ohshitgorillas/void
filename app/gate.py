"""Every keep-or-drop decision on a heard burst: is it the owner asking for something, or the room (music, other
people, the TV, his own voice coming back)?

Pure: no audio I/O, no model loads. `judge` runs its checks in a fixed order and returns at the first drop:
speech share, echo, stop phrase, noise, while talking, wake word, stray word, Whisper confidence, voiceprint.
Whisper's confidence thresholds live here; the numbers themselves come from run_whisper_heard.
"""
from dataclasses import dataclass

NO_SPEECH = 0.8        # Whisper this sure nobody was talking (max no_speech_prob over kept segments): not a request
MIN_LOGPROB = -0.8     # mean avg_logprob below this: Whisper was guessing at the words (sung lyrics, far-off talk)
SEG_LOGPROB = -1.0     # per-segment avg_logprob floor for sure=True
SEG_COMPRESSION = 2.4  # per-segment compression-ratio ceiling
MIN_SPEECH = 0.25      # seconds of detected speech a burst needs
SPEECH_SHARE = 0.2     # share of the burst that must be speech
# the one filler list: what the speech model "hears" in background noise
NOISE_WORDS = frozenset({"you", "thank you", "thanks", "bye", "thanks for watching", "thank you for watching",
                         "uh", "um", "hmm"})
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


def spoken_enough(speech: float, seconds: float, kind: str) -> bool:
    raise NotImplementedError


def sure(segments: list) -> list:                              # the one Whisper segment filter
    raise NotImplementedError


def is_echo(heard: str, spoken: list[str]) -> bool:
    raise NotImplementedError


def is_noise(heard: str) -> bool:                              # empty, filler or a looping sentence
    raise NotImplementedError


def is_filler(heard: str) -> bool:                             # the whole text is a NOISE_WORDS phrase
    raise NotImplementedError


def stop_said(text: str) -> bool:
    raise NotImplementedError


def judge(b: Burst, spoken: list[str], cfg: dict) -> Verdict:
    if not isinstance(b, Burst):
        # TEMPORARY bridge, gone when Wake.check builds a Burst (design Order step 2): the old follow-up call
        # judge(heard, voice, cfg) from server.py still lands here.
        return _follow_legacy(b, spoken, cfg)
    raise NotImplementedError


def _follow_legacy(heard, voice: float | None, cfg: dict) -> Verdict:
    """The old follow-up gate, unchanged. `heard`: server.Heard · `voice`: cosine to the owner's voiceprint, or None
    · `cfg`: voice_gate (off keeps everything), voice_min (the lowest voice score that is still the owner)."""
    def out(keep, why):
        return Verdict(keep, why, "follow" if keep else "drop", getattr(heard, "text", "") if keep else "")
    if not cfg.get("voice_gate", True):
        return out(True, "kept")
    if not (heard.text or "").strip() or heard.no_speech >= NO_SPEECH:
        return out(False, "no speech")
    if heard.logprob < MIN_LOGPROB:
        return out(False, "low confidence")
    if voice is not None and voice < float(cfg.get("voice_min", 0.5)):
        return out(False, "not your voice")
    return out(True, "kept")
