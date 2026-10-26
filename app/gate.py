"""The follow-up gate: the one decision on a clip heard in the follow-up window without "hey Void" — is it the owner
asking for something, or the room (music, other people, the TV)?

Pure: no audio I/O, no model loads. Wake.check hands it what Whisper heard (server.Heard) and the clip's voiceprint
score (None until the voiceprint knows the owner's voice, or without the model), and calls it once per follow-up.
Whisper's confidence thresholds for follow-ups live here; the numbers themselves come from run_whisper_heard.
"""
from dataclasses import dataclass

NO_SPEECH = 0.8        # Whisper this sure nobody was talking (max no_speech_prob over kept segments): not a request
MIN_LOGPROB = -0.8     # mean avg_logprob below this: Whisper was guessing at the words (sung lyrics, far-off talk)


@dataclass
class Verdict:
    keep: bool
    why: str              # "low confidence", "no speech", "not your voice", "kept"


def judge(heard, voice: float | None, cfg: dict) -> Verdict:
    """Keep or drop a follow-up. `heard`: server.Heard · `voice`: cosine to the owner's voiceprint, or None (not
    enrolled enough yet, or no model: Whisper's confidence alone decides) · `cfg`: voice_gate (off keeps everything),
    voice_min (the lowest voice score that is still the owner)."""
    if not cfg.get("voice_gate", True):
        return Verdict(True, "kept")
    if not (heard.text or "").strip() or heard.no_speech >= NO_SPEECH:
        return Verdict(False, "no speech")
    if heard.logprob < MIN_LOGPROB:
        return Verdict(False, "low confidence")
    if voice is not None and voice < float(cfg.get("voice_min", 0.5)):
        return Verdict(False, "not your voice")
    return Verdict(True, "kept")
