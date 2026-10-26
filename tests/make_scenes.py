"""Make the replay harness's audio fixtures in tests/fixtures/scenes/ (16 kHz mono 16-bit WAVs plus manifest.json).

Void's lines are made by app/server.py's own synth(): Kokoro with the "cute" preset (af_bella, its kpitch), and the
WAV is played back at the rate synth returns, then resampled to 16 kHz. "You" is a piper voice, en_GB-alan-medium.
Run with Void's venv, which has kokoro_onnx and piper and whose voices are under ~/.local/share/void/voices/:

    ~/.local/share/void/venv/bin/python tests/make_scenes.py           # write the fixtures
    ~/.local/share/void/venv/bin/python tests/make_scenes.py --check   # regenerate elsewhere, compare to committed

The user's Void config and data are never touched: app/server.py is imported with XDG_CONFIG_HOME and XDG_DATA_HOME
pointed at a throwaway folder whose voices/kokoro is a link to the real Kokoro model. ONNX and BLAS are held to
THREADS threads. Piper's duration noise is off (noise_w_scale=0), and Kokoro has none, so every clip's length is the
same on every run; --check proves it against the files in the tree.
"""
import argparse
import io
import json
import os
import sys
import tempfile
import wave
from pathlib import Path

THREADS = 6
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS",
           "NUMEXPR_NUM_THREADS", "ORT_NUM_THREADS"):
    os.environ[_v] = str(THREADS)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "tests" / "fixtures" / "scenes"
REAL_VOICES = Path.home() / ".local" / "share" / "void" / "voices"
RATE = 16000
VOID_PRESET = "cute"
YOU_VOICE = "en_GB-alan-medium"
PAUSE = 0.55          # silence put between the parts of a long turn (piper's own edges make it ~0.8 s of quiet)

VOID_LINES = {
    "void_question.wav": "Okay, I found three photos from last summer in your Downloads folder. "
                         "Do you want me to move them into Pictures, or leave them where they are?",
}
YOU_LINES = {
    "you_stop.wav": "Stop, stop, that's not what I asked for.",
    "you_hold_on.wav": "Hold on, I need to check something first.",
    "you_shut_up.wav": "Shut up for a second, please.",
    "you_hey_void.wav": "Hey Void, open my Downloads folder instead.",
    "you_answer.wav": "Move them into Pictures, please.",
    "you_overlap.wav": "Yeah, move them, and while you're at it, make a new folder called summer for them.",
}
LONG_TURN = ("you_long_pauses.wav", ["So what I'd really like you to do is, um,",
                                     "go through all of last week's photos and",
                                     "pick out the ones from the beach, the ones with the dog in them,",
                                     "and then put those in a new folder called summer, on the desktop."])
VOID_CLIP = "void_question.wav"
SCENES = {
    "void_alone": {"void": VOID_CLIP, "you": None},
    "interrupt_stop": {"void": VOID_CLIP, "you": "you_stop.wav"},
    "interrupt_hold_on": {"void": VOID_CLIP, "you": "you_hold_on.wav"},
    "interrupt_shut_up": {"void": VOID_CLIP, "you": "you_shut_up.wav"},
    "interrupt_hey_void": {"void": VOID_CLIP, "you": "you_hey_void.wav"},
    "answer_after": {"void": VOID_CLIP, "you": "you_answer.wav"},
    "overlap_last_second": {"void": VOID_CLIP, "you": "you_overlap.wav"},
    "long_pauses": {"void": None, "you": LONG_TURN[0]},
}


def cap_onnx_threads():
    """Every ONNX session made from here on runs on at most THREADS threads, without busy-waiting."""
    import onnxruntime as rt
    orig = rt.InferenceSession

    def capped(path, sess_options=None, **kw):
        so = sess_options or rt.SessionOptions()
        so.intra_op_num_threads, so.inter_op_num_threads = THREADS, 1
        so.add_session_config_entry("session.intra_op.allow_spinning", "0")
        return orig(path, sess_options=so, **kw)
    rt.InferenceSession = capped


def import_server(scratch):
    """app/server.py, imported against a throwaway config and data folder, set to Kokoro and the cute preset."""
    data, conf = scratch / "data", scratch / "config"
    (data / "void" / "voices").mkdir(parents=True)
    (data / "void" / "voices" / "kokoro").symlink_to(REAL_VOICES / "kokoro")
    os.environ["XDG_DATA_HOME"], os.environ["XDG_CONFIG_HOME"] = str(data), str(conf)
    sys.path.insert(0, str(ROOT / "app"))
    import server
    assert str(server.DATA_DIR).startswith(str(scratch)) and str(server.CONF_PATH).startswith(str(scratch))
    server.CFG.update(tts="kokoro", voice=VOID_PRESET, kokoro_voice="")
    assert server.tts_engine() == "kokoro", "Kokoro isn't ready in this interpreter"
    return server


def read_wav(data):
    """wav bytes → (float samples, rate)."""
    import numpy as np
    with wave.open(io.BytesIO(data)) as w:
        assert w.getsampwidth() == 2, "16-bit WAV expected"
        x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float64) / 32768
        return x[::w.getnchannels()], w.getframerate()


def resample(x, rate):
    """FFT resample from `rate` to 16 kHz (band-limited; length fixed by the input length alone)."""
    import numpy as np
    m = int(round(len(x) * RATE / rate))
    spec = np.fft.rfft(x)
    keep = m // 2 + 1
    spec = spec[:keep] if len(spec) >= keep else np.concatenate([spec, np.zeros(keep - len(spec))])
    return np.fft.irfft(spec, m) * (m / len(x))


def to_wav(x):
    import numpy as np
    pcm = (np.clip(x, -1, 1) * 32767).round().astype("<i2").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE); w.writeframes(pcm)
    return buf.getvalue()


def void_clip(server, text):
    """Void saying `text` exactly as he would: synth()'s WAV played at the rate it returns, at 16 kHz."""
    data, rate = server.synth(text)
    x, sr = read_wav(data)
    return resample(x, sr * rate)


def you_voice():
    import piper
    voice = piper.PiperVoice.load(REAL_VOICES / f"{YOU_VOICE}.onnx")
    cfg = piper.SynthesisConfig(noise_w_scale=0.0)          # no random word lengths: same duration every run

    def say(text):
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            voice.synthesize_wav(text, w, syn_config=cfg)
        x, sr = read_wav(buf.getvalue())
        return resample(x, sr)
    return say


def generate(dest):
    """Write every clip and manifest.json into `dest`. → {file: frames}."""
    import numpy as np
    dest.mkdir(parents=True, exist_ok=True)
    cap_onnx_threads()
    with tempfile.TemporaryDirectory(prefix="void-scenes-") as tmp:
        server = import_server(Path(tmp).resolve())
        audio = {name: void_clip(server, text) for name, text in VOID_LINES.items()}
        say = you_voice()
        audio.update({name: say(text) for name, text in YOU_LINES.items()})
        gap = np.zeros(int(PAUSE * RATE))
        parts = [say(t) for t in LONG_TURN[1]]
        audio[LONG_TURN[0]] = np.concatenate([p for part in parts for p in (part, gap)][:-1])
        preset = server.VOICES[VOID_PRESET]
    texts = {**VOID_LINES, **YOU_LINES, LONG_TURN[0]: " ".join(LONG_TURN[1])}
    clips = {}
    for name, x in audio.items():
        (dest / name).write_bytes(to_wav(x))
        clips[name] = {"speaker": "void" if name in VOID_LINES else "you", "text": texts[name],
                       "seconds": round(len(x) / RATE, 4)}
    manifest = {"generator": str(Path(__file__).resolve().relative_to(ROOT)),
                "rate": RATE,
                "voices": {"void": {"engine": "kokoro", "preset": VOID_PRESET, "voice": preset["kokoro"],
                                    "kpitch": preset["kpitch"]},
                           "you": {"engine": "piper", "voice": YOU_VOICE}},
                "clips": clips, "scenes": SCENES}
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {name: len(x) for name, x in audio.items()}


def frames(path):
    with wave.open(str(path), "rb") as w:
        return w.getnframes()


def check():
    """Regenerate into a scratch folder and compare each clip's length with the committed one. → exit status."""
    with tempfile.TemporaryDirectory(prefix="void-scenes-check-") as tmp:
        fresh, bad = generate(Path(tmp)), 0
        for name, n in sorted(fresh.items()):
            have = OUT / name
            old = frames(have) if have.exists() else None
            same_bytes = have.exists() and have.read_bytes() == (Path(tmp) / name).read_bytes()
            ok = old == n
            bad += not ok
            print(f"{'ok  ' if ok else 'DIFF'} {name:24} committed {old if old is not None else '-':>7} "
                  f"fresh {n:>7} frames ({n / RATE:.4f} s){'  bytes identical' if same_bytes else ''}")
    print("durations match" if not bad else f"{bad} clip(s) differ in duration")
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="regenerate elsewhere and compare durations to the tree")
    args = ap.parse_args()
    if args.check:
        sys.exit(check())
    for name, n in sorted(generate(OUT).items()):
        print(f"{name:24} {n / RATE:7.3f} s {(OUT / name).stat().st_size:>8} bytes")


if __name__ == "__main__":
    main()
