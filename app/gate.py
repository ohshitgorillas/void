"""Every keep-or-drop decision on a heard burst: is it the owner asking for something, or the room (music, other
people, the TV, his own voice coming back)?

Pure: no audio I/O, no model loads. `judge` runs its checks in a fixed order and returns at the first drop:
speech share, echo, stop phrase, noise, while talking, wake word, stray word, Whisper confidence, voiceprint.
Whisper's confidence thresholds live here; the numbers themselves come from run_whisper_heard.
"""
import difflib
import re
from dataclasses import dataclass

NO_SPEECH = 0.8        # Whisper this sure nobody was talking (max no_speech_prob over kept segments): not a request
MIN_LOGPROB = -0.8     # mean avg_logprob below this: Whisper was guessing at the words (sung lyrics, far-off talk)
SEG_LOGPROB = -1.0     # per-segment avg_logprob floor for sure=True
SEG_COMPRESSION = 2.4  # per-segment compression-ratio ceiling
SEG_NO_SPEECH, SEG_NO_SPEECH_LOGPROB = 0.6, -0.5   # a segment over this no_speech_prob and under this avg_logprob: nobody
MIN_SPEECH = 0.25      # seconds of detected speech a burst needs
SPEECH_SHARE = 0.2     # share of the burst that must be speech
# the one filler list: what the speech model "hears" in background noise
NOISE_WORDS = frozenset({"you", "thank you", "thanks", "bye", "thanks for watching", "thank you for watching",
                         "uh", "um", "hmm"})
NOISE_LOOP = 4   # a phrase this many words or longer, said twice or more back to back, is Whisper looping on room sound
ECHO_TAIL = 1.0          # s after he stops talking that the room still rings: a burst starting before then is his own voice
ECHO_RUN = 2.0           # …unless it runs on this long past the ringing: then it's you, answering as he finished
ECHO_KEEP, ECHO_RATIO, ECHO_MIN = 60, 0.55, 3    # remember what he said for 60 s · share of heard words matched · fewest words to judge
ECHO_LIKE, ECHO_SKIP = 0.6, 0.25                 # how alike two words must be to count · cost of each of his words the burst skips
STOP_RE = re.compile(r"(?:ok(?:ay)?\W+|void\W+|hey\W+void\W+)?(?:stop|wait|shush|shh+|quiet|be quiet|shut up|hold on|hang on|"
                     r"enough|stop talking|that's enough|thanks?(?: you)?|got it)(?:\W+(?:void|please|now))?")
# while he talks only these stop him, and only said as a stop: opening or closing a clause of what the mic caught (his
# own voice heard back over him may carry the word inside a sentence, "ready to have a stop on, and it's going")
_STOP_WORDS = r"(?:stop|hold on|hang on|shut up|be quiet|shush|shh+|that's enough)"
_STOP_FILL = r"(?:ok(?:ay)?|oh|no|hey|void|um+|uh+|please|now|so|well)"
STOP_IN_RE = re.compile(rf"^\W*(?:{_STOP_FILL}\W+)*{_STOP_WORDS}\b|\b{_STOP_WORDS}(?:\W+{_STOP_FILL})*\W*$")
WAKE_RE = re.compile(r"^\W*(?:(?:hey|hi|hay|okay|ok|yo|oi)\W+)?(void|voyd|boyd|voi|vod)\b\W*(.*)$", re.I | re.S)
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
    """Enough detected speech to be worth transcribing: MIN_SPEECH seconds for every kind, and for every kind but a
    follow-up also SPEECH_SHARE of the burst (music or noise, not talking, otherwise: Whisper would dream up words)."""
    return speech >= MIN_SPEECH and (kind == "follow" or speech >= seconds * SPEECH_SHARE)


def sure(segments: list) -> list:                              # the one Whisper segment filter
    """The segments Whisper is sure of, in order: not low log-prob, not the same few words looping, not "probably
    nobody talking"."""
    return [s for s in segments if s.avg_logprob >= SEG_LOGPROB and s.compression_ratio <= SEG_COMPRESSION
            and not (s.no_speech_prob > SEG_NO_SPEECH and s.avg_logprob < SEG_NO_SPEECH_LOGPROB)]


def _words(text: str | None) -> list[str]:
    return re.findall(r"[^\W_]+", (text or "").lower())


def word_like(a: str, b: str) -> float:
    """How alike two words are, 0 to 1, forgiving speech-to-text slips ("them"/"'em", "long"/"belongs")."""
    if a == b:
        return 1.0
    r = difflib.SequenceMatcher(None, a, b).ratio()
    if min(len(a), len(b)) >= 2 and (a in b or b in a):
        r = max(r, 0.8)
    return r if r >= ECHO_LIKE else 0.0


def is_echo(heard: str, spoken: list[str]) -> bool:
    """The mic caught his own voice: most of the heard words, however garbled, line up with a stretch of what he said
    lately (`spoken`, his lines, oldest first). Words may be misheard, dropped or added, but the stretch must run in
    his order and mostly unbroken."""
    h = _words(heard)
    if len(h) < ECHO_MIN:
        return False
    lines = list(spoken)
    for said in lines + [" ".join(lines)]:     # (he speaks a sentence at a time; one burst can catch several)
        s = _words(said)
        row = [0.0] * (len(s) + 1)           # best alignment of the heard words so far, ending at each of his words
        for w in h:
            prev, row = row, [0.0]
            for j, x in enumerate(s):        # match (by likeness) · drop a heard word · skip one of his, at a cost
                row.append(max(prev[j] + word_like(w, x), prev[j + 1], row[j] - ECHO_SKIP))
        if max(row) >= ECHO_RATIO * len(h):
            return True
    return False


def is_noise(heard: str) -> bool:                              # empty, filler or a looping sentence
    """Nothing, a stock filler, or a whole sentence over and over ("It is a pleasure to be here. It is a pleasure to be
    here"): Whisper makes up and repeats a sentence on room sound. A short phrase repeated ("Not yet, not yet", "Wait,
    wait, wait") is you, answering him, and is not noise."""
    w = _words(heard)
    if not w or is_filler(heard):
        return True
    # the shortest phrase whose repeats make up the whole (a cut-off last repeat allowed)
    loop = next(n for n in range(1, len(w) + 1) if all(x == w[i % n] for i, x in enumerate(w)))
    return loop >= NOISE_LOOP and len(w) >= 2 * loop


def is_filler(heard: str) -> bool:                             # the whole text is a NOISE_WORDS phrase
    return " ".join(_words(heard)) in NOISE_WORDS


def stop_said(text: str) -> bool:
    """A stop phrase said as one: some clause of the transcript opens or closes with it (filler and his name aside)."""
    return any(STOP_IN_RE.search(c) for c in re.split(r"[.,!?;]+", (text or "").lower()))


def judge(b: Burst, spoken: list[str], cfg: dict) -> Verdict:
    """Keep or drop one heard burst, and what to do with a kept one. `spoken`: his lines lately, oldest first (for the
    echo test) · `cfg`: voice_gate (off: follow-ups are not judged on Whisper's confidence or the voiceprint),
    voice_min (the lowest voice score that is still the owner)."""
    def drop(why):
        return Verdict(False, why, "drop", "")
    text = b.text or ""
    said = text.strip(" .,!?")
    gated = bool(cfg.get("voice_gate", True))
    owner = b.voice is not None and b.voice >= float(cfg.get("voice_min", 0.5))
    # 1. speech share: music or noise, not talking
    if not spoken_enough(b.speech, b.seconds, b.kind):
        return drop("no speech")
    # 2. echo: his own voice through the mic
    if is_echo(text, spoken):
        return drop("echo")
    # 3. stop phrase, said over him or while he talks (a filler "thanks" heard while he talks is the room: 4 has it)
    if b.kind in ("over", "peek") or b.talking:
        if ((b.kind in ("over", "peek") and stop_said(said))
                or (b.talking and STOP_RE.fullmatch(said.lower()) and not is_filler(said))):
            return Verdict(True, "kept", "barge", "")
    # 4. noise: nothing, or a sentence looping, always; filler unless it is the owner's own voice
    if is_noise(text) and not (is_filler(text) and owner):
        return drop("noise")
    # 5. while talking: a peek only ever stops him; anything else begun over him without his name is most likely his
    # own voice, garbled
    m = WAKE_RE.match(text) if b.kind != "listen" else None
    if b.kind == "peek" or (b.kind == "over" and not m):
        return drop("while talking")
    # 6. wake word ("listen" is push-to-talk: no wake word needed)
    if b.kind == "listen":
        return Verdict(True, "kept", "request", text)
    if m:
        if b.talking:
            return Verdict(True, "kept", "barge", "")
        return Verdict(True, "kept", "request", m.group(2).strip(" .,!?"))
    if b.kind != "follow":
        return drop("no wake word")
    # 7. stray word: one word is not a request, unless the voiceprint says it is the owner
    if len(said.split()) < 2 and not (gated and owner):
        return drop("stray word")
    if gated:
        # 8. Whisper confidence
        if b.heard is not None:
            if b.heard.no_speech >= NO_SPEECH:
                return drop("no speech")
            if b.heard.logprob < MIN_LOGPROB:
                return drop("low confidence")
        # 9. voiceprint
        if b.voice is not None and not owner:
            return drop("not your voice")
    return Verdict(True, "kept", "follow", text)

