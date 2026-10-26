"""The one home of hearing test doubles: what Whisper reports for a burst, the speech-to-text patch set, quiet room
hiss, and a recording cut into the pieces a mic hands over. (The fake mics differ from test to test and stay with
their tests.)

Everything is s16le 16 kHz mono, as server.py hears it. server.py is imported only when a double is used, so a test
file sets up Void's data folder (suite_data) before it is."""
import contextlib
import random
import sys
from pathlib import Path
from unittest import mock

SR = 16000


def _server():
    app = str(Path(__file__).resolve().parent.parent / "app")
    if app not in sys.path:
        sys.path.insert(0, app)
    import server
    return server


def heard(text: str = "something was said here", sure: bool = True, seconds: float = 0.0):
    """What Whisper reports for a burst: `text`, and either sure of it (confident words, someone talking) or kept no
    segment it was sure of (Heard's documented 'none' numbers). `seconds`: the burst's speech_seconds. → server.Heard"""
    if sure:
        return _server().Heard(text=text, logprob=-0.2, no_speech=0.02, seconds=seconds)
    return _server().Heard(text=text, logprob=float("-inf"), no_speech=1.0, seconds=seconds)


def hiss(seconds: float, seed: int) -> bytes:
    """Quiet room hiss, `seconds` long, the same for the same `seed`."""
    rnd = random.Random(seed)
    return b"".join(int(max(-32768, min(32767, round(rnd.gauss(0.0, 0.003) * 32768)))).to_bytes(2, "little", signed=True)
                    for _ in range(int(seconds * SR)))


def pieces(pcm: bytes, ms: int = 20) -> list[bytes]:
    """Every `ms`-long piece of `pcm`, back to back (a short tail is left off)."""
    n = SR * 2 * ms // 1000
    return [pcm[i:i + n] for i in range(0, len(pcm) - n + 1, n)]


def ears(server, text_for, speech_for=None) -> contextlib.ExitStack:
    """Patch `server`'s speech-to-text: Whisper hears `text_for(pcm)` in a burst, sure of it when it made out any
    words, and `speech_for(pcm)` seconds of it are someone talking (default: all of it). speech_seconds,
    transcribe_pcm and transcribe_pcm_heard all agree. → the open patches; close the stack (or leave its `with`) to
    undo them."""
    if speech_for is None:
        def speech_for(pcm):
            return len(pcm) / (SR * 2)

    def transcribe_heard(pcm, **_kw):
        text = text_for(pcm)
        return heard(text, sure=bool(text), seconds=speech_for(pcm))

    stack = contextlib.ExitStack()
    try:
        stack.enter_context(mock.patch.object(server, "speech_seconds", lambda pcm: speech_for(pcm)))
        stack.enter_context(mock.patch.object(server, "transcribe_pcm_heard", transcribe_heard))
        stack.enter_context(mock.patch.object(server, "transcribe_pcm", lambda pcm, **kw: transcribe_heard(pcm).text))
    except BaseException:
        stack.close()
        raise
    return stack
