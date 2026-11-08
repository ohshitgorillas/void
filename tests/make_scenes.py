"""Make the replay harness's audio fixtures in tests/fixtures/scenes/ (16 kHz mono 16-bit WAVs plus manifest.json).

Void's lines are made by app/server.py's own synth(): Kokoro with the "cute" preset (af_bella, its kpitch), and the
WAV is played back at the rate synth returns, then resampled to 16 kHz. "You" is a piper voice, en_GB-alan-medium.
Run with Void's venv, which has kokoro_onnx and piper and whose voices are under ~/.local/share/void/voices/:

    ~/.local/share/void/venv/bin/python tests/make_scenes.py           # write the fixtures (every clip, anew)
    ~/.local/share/void/venv/bin/python tests/make_scenes.py --missing # write only what the tree lacks: WAVs there stay as they are
    ~/.local/share/void/venv/bin/python tests/make_scenes.py --check   # regenerate elsewhere, compare to committed

The user's Void config and data are never touched: app/server.py is imported with XDG_CONFIG_HOME and XDG_DATA_HOME
pointed at a throwaway folder whose voices/kokoro is a link to the real Kokoro model. ONNX and BLAS are held to
THREADS threads. Piper's duration noise is off (noise_w_scale=0), and Kokoro has none, so every clip's length is the
same on every run; --check proves it against the files in the tree.

The room music (music playing in the room that Void didn't play, so it has no echo reference) is made here from
nothing recorded: a little song in C at 96 bpm, keys, bass and drums synthesized note by note, with a third voice,
Kokoro's bf_emma (neither Void's nor yours), singing the words in SONG to its melody. Each sung word is Kokoro saying
it, its spectral envelope stretched over the note (vowels long, consonants kept) and laid on a harmonic tone at the
note's pitch with vibrato, so it keeps the words' formants but carries the tune. Its length is fixed by the score.
"""
import argparse
import contextlib
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
    # his own stop phrases, for the own-stop scenes: it opens with one heard on its own (the first stop check, 0.8 s
    # in, holds only "Stop there": under ECHO_MIN words, so is_echo never judges it; "Whatever" is a long word that
    # ends after it), runs on for 4 s and more, and ends on one ("Stop there, please": the opening's words again, which real Whisper hears as
    # it hears the opening, and long enough that its burst holds the speech share the check wants); beyond them it shares
    # no word with you_stop.wav's text
    "void_stop.wav": "Stop there. Whatever you decide, tell me where the three pictures from summer should go "
                     "and carry on whenever you like. Stop there, please.",
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
ROOM_CLIP = "room_music.wav"
SINGER = "bf_emma"
LEVELS = {"keys": 0.35, "bass": 0.4, "drums": 0.35, "voice": 1.0}   # by RMS: the singer up front, as a lead vocal
BPM, BARS, TAIL = 96, 7, 0.5           # 7 bars of 4/4 at 96 bpm plus a ring-out: 18 s, longer than your longest turn
CHORDS = ["C", "C", "Am", "C", "Am", "F", "G C"]   # one per bar; "G C" splits the bar
CHORD_NOTES = {"C": (48, 52, 55, 60), "Am": (45, 48, 52, 57), "F": (41, 45, 48, 53), "G": (43, 47, 50, 55)}
SONG = [  # (bar it starts in, [(word, MIDI note, beats)]); a word of None is a rest
    (1, [("take", 64, .5), ("me", 67, .5), ("down", 69, 1), ("to", 67, .5), ("the", 64, .5), ("river", 67, 1.5),
         ("tonight", 72, 2)]),
    (3, [("where", 64, .5), ("the", 67, .5), ("summer", 69, 1), ("lights", 72, 1), ("are", 69, .5),
         ("shining", 67, 1.5), ("bright", 64, 2)]),
    (5, [("hold", 65, 1), ("my", 65, .5), ("hand", 69, 1), ("and", 67, .5), ("sing", 64, 1), ("along", 62, 1),
         ("with", 62, .5), ("me", 60, 2)]),
]
VOID_CLIP = "void_question.wav"
VOID_STOP_CLIP = "void_stop.wav"
TIMED = ("void_stop.wav", "you_stop.wav")   # the clips whose manifest entries carry "words" (Void's also "lead")
SCENES = {
    "void_alone": {"void": VOID_CLIP, "you": None},
    "interrupt_stop": {"void": VOID_CLIP, "you": "you_stop.wav"},
    "interrupt_hold_on": {"void": VOID_CLIP, "you": "you_hold_on.wav"},
    "interrupt_shut_up": {"void": VOID_CLIP, "you": "you_shut_up.wav"},
    "interrupt_hey_void": {"void": VOID_CLIP, "you": "you_hey_void.wav"},
    "answer_after": {"void": VOID_CLIP, "you": "you_answer.wav"},
    "overlap_last_second": {"void": VOID_CLIP, "you": "you_overlap.wav"},
    "void_stop_alone": {"void": VOID_STOP_CLIP, "you": None},
    "stop_after_his_stop": {"void": VOID_STOP_CLIP, "you": "you_stop.wav"},
    "long_pauses": {"void": None, "you": LONG_TURN[0]},
    "room_music": {"void": None, "room": ROOM_CLIP},
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


N_FFT, HOP, LIFTER = 512, 128, 30


def stft(x):
    import numpy as np
    win = np.hanning(N_FFT)
    x = np.concatenate([x, np.zeros(N_FFT)])
    idx = np.arange(0, len(x) - N_FFT + 1, HOP)[:, None] + np.arange(N_FFT)
    return np.fft.rfft(x[idx] * win, axis=1)


def istft(spec, length):
    import numpy as np
    win = np.hanning(N_FFT)
    frames = np.fft.irfft(spec, N_FFT, axis=1) * win
    out, norm = np.zeros(len(frames) * HOP + N_FFT), np.zeros(len(frames) * HOP + N_FFT)
    for i, f in enumerate(frames):
        out[i * HOP:i * HOP + N_FFT] += f
        norm[i * HOP:i * HOP + N_FFT] += win * win
    return (out / np.maximum(norm, 1e-3))[:length]


def envelope(spec):
    """Log spectral envelope per frame: the cepstrum's first LIFTER coefficients (formants, not harmonics)."""
    import numpy as np
    cep = np.fft.irfft(np.log(np.abs(spec) + 1e-6), N_FFT, axis=1)
    cep[:, LIFTER:N_FFT - LIFTER + 1] = 0
    return np.fft.rfft(cep, axis=1).real


def voicing(x, n_frames):
    """Per STFT frame, 1 where the speech is voiced (a clear pitch in 70-400 Hz), else 0, lightly smoothed."""
    import numpy as np
    x = np.concatenate([x, np.zeros(N_FFT)])
    lo, hi, peak, v = RATE // 400, RATE // 70, np.abs(x).max(), np.zeros(n_frames)
    for i in range(n_frames):
        f = x[i * HOP:i * HOP + N_FFT]
        f = f - f.mean()
        ac = np.correlate(f, f, "full")[N_FFT - 1:]
        v[i] = ac[0] > 0 and np.sqrt(ac[0] / N_FFT) > 0.02 * peak and ac[lo:hi].max() / ac[0] > 0.4
    return np.convolve(v, np.ones(3) / 3, "same")


def sing(word_audio, midi, seconds, rng):
    """`word_audio` (the word spoken, 16 kHz) sung at `midi` for `seconds`: its envelope over a vibrato tone."""
    import numpy as np
    loud = np.flatnonzero(np.abs(word_audio) > 0.02 * np.abs(word_audio).max())
    x = word_audio[loud[0]:loud[-1] + 1]
    src = stft(x)
    env, v = envelope(src), voicing(x, len(src))
    m = int(seconds * RATE) // HOP + 1
    step = np.ones(len(src))                        # stretch the voiced frames (the vowels), keep the consonants
    if v.sum() > 0 and m > (v < 0.5).sum():
        step[v >= 0.5] = (m - (v < 0.5).sum()) / (v >= 0.5).sum()
    else:
        step[:] = m / len(src)
    pos = np.interp(np.arange(m) + 0.5, np.concatenate([[0], np.cumsum(step)]), np.arange(len(src) + 1)) - 0.5
    pos = np.clip(pos, 0, len(src) - 1)
    i0 = np.floor(pos).astype(int)
    i1, frac = np.minimum(i0 + 1, len(src) - 1), (pos - i0)[:, None]
    env_t, v_t = env[i0] * (1 - frac) + env[i1] * frac, (v[i0] * (1 - frac[:, 0]) + v[i1] * frac[:, 0])[:, None]
    n = (m - 1) * HOP
    t = np.arange(n) / RATE
    depth = 0.3 * np.clip((t - 0.15) / 0.2, 0, 1)                         # vibrato comes in after the onset
    f0 = 440 * 2 ** ((midi - 69 + depth * np.sin(2 * np.pi * 5.5 * t)) / 12)
    phase = 2 * np.pi * np.cumsum(f0) / RATE
    tone = sum(np.sin(k * phase) * (k * f0 < 7600) for k in range(1, int(7600 / f0.min()) + 1))
    noise = rng.standard_normal(n)
    tone_s, noise_s = stft(tone)[:m], stft(noise)[:m]
    win = np.hanning(N_FFT)              # a unit harmonic peaks at sum(win)/2 in the STFT, unit noise at |win|
    out = (tone_s / (win.sum() / 2) * v_t + 0.6 * noise_s / np.sqrt((win ** 2).sum()) * (1 - v_t)) * np.exp(env_t)
    y = istft(out, n)
    fade = np.minimum(1, np.minimum(np.arange(n), np.arange(n)[::-1]) / (0.012 * RATE))
    return y * fade


def room_tracks(server, rng):
    """The song's parts, each the clip's full length: {"keys", "bass", "drums", "voice": samples}."""
    import numpy as np
    beat = 60 / BPM
    bar = 4 * beat
    n = int((BARS * bar + TAIL) * RATE)
    keys, bass, drums, voice = (np.zeros(n) for _ in range(4))

    def hz(m):
        return 440 * 2 ** ((m - 69) / 12)

    def put(track, at, x):
        i = int(at * RATE)
        x = x[:n - i]
        track[i:i + len(x)] += x

    def pluck(m, sec, decay):
        t = np.arange(int(sec * RATE)) / RATE
        tone = sum(np.sin(2 * np.pi * k * hz(m) * t) * np.exp(-t * decay * k) / k for k in range(1, 7))
        return tone * np.minimum(1, t / 0.004)

    for b, name in enumerate(CHORDS):
        parts = name.split()
        for half, chord in enumerate(parts):
            notes, start, beats = CHORD_NOTES[chord], b * bar + half * bar / len(parts), 4 // len(parts)
            for e in range(2 * beats):                                  # eighth-note arpeggio, up and back
                put(keys, start + e * beat / 2, pluck(notes[(0, 1, 2, 3, 2, 1, 2, 3)[e]] + 12, 0.6, 4.0))
            for q in range(0, beats, 2):                                # bass on the root, every half bar
                put(bass, start + q * beat, pluck(notes[0] - 12, beat * 1.9, 1.5))
    t = np.arange(int(0.25 * RATE)) / RATE
    kick = np.sin(2 * np.pi * (45 * t + 60 * (1 - np.exp(-t * 30)) / 30)) * np.exp(-t * 14)
    for q in range(BARS * 4):
        if q % 2 == 0:
            put(drums, q * beat, kick)
        else:
            put(drums, q * beat, (0.5 * rng.standard_normal(len(t)) + np.sin(2 * np.pi * 185 * t)) * np.exp(-t * 22))
        for e in (0, 1):
            hat = np.diff(rng.standard_normal(int(0.05 * RATE) + 1)) * np.exp(-np.arange(int(0.05 * RATE)) / 80)
            put(drums, q * beat + e * beat / 2, 0.25 * hat)
    for start_bar, line in SONG:
        at = start_bar * bar
        for word, midi, beats in line:
            if word:
                x, sr = read_wav(server.kokoro_synth(word, SINGER, 0.9))
                put(voice, at, sing(resample(x, sr), midi, beats * beat * 0.94, rng))
            at += beats * beat
    return {"keys": keys, "bass": bass, "drums": drums, "voice": voice}


def room_mix(tracks, rng):
    """The parts at LEVELS (by RMS over their sounding stretches), in a small room, peaking at 0.6."""
    import numpy as np
    mix = sum(LEVELS[k] * x / np.sqrt(np.mean(x[np.abs(x) > 1e-4] ** 2)) for k, x in tracks.items())
    ir_t = np.arange(int(0.35 * RATE)) / RATE
    ir = rng.standard_normal(len(ir_t)) * np.exp(-ir_t / 0.07) * 0.08
    ir[0] = 1.0
    size = 1 << int(np.ceil(np.log2(len(mix) + len(ir))))
    wet = np.fft.irfft(np.fft.rfft(mix, size) * np.fft.rfft(ir, size), size)[:len(mix)]
    return 0.6 * wet / np.abs(wet).max()


def room_music(server):
    """The room-music clip: the song in SONG over synthesized keys, bass and drums, in a small room. → samples."""
    import numpy as np
    rng = np.random.default_rng(1996)
    return room_mix(room_tracks(server, rng), rng)


def song_words():
    return " ".join(w for _, line in SONG for w, _, _ in line if w)


def wav_words(server, wav, text):
    """`wav` (16 kHz WAV bytes) saying `text`: → (each word of text.split() as [start, end] in s from the first sample of
    `wav`, the lead in s that server.tidy_full trims off its front). tidy_full is the tree's one word-timing estimate; its
    times count from the trimmed clip, so they are shifted by the lead. The lead is where the trimmed samples sit inside
    `wav`, found by locating them, never by re-deriving tidy_full's threshold. Raises when tidy_full has no word times,
    times another number of words than `text` has, or its trimmed clip is no slice of `wav`."""
    trimmed, times, _level = server.tidy_full(wav, text)
    if times is None:
        raise ValueError(f"tidy_full could not time the words of {text!r}")
    if len(times) != len(text.split()):
        raise ValueError(f"tidy_full timed {len(times)} words of {text!r}, which has {len(text.split())}")
    with wave.open(io.BytesIO(wav)) as w:
        whole = w.readframes(w.getnframes())
    with wave.open(io.BytesIO(trimmed)) as w:
        part = w.readframes(w.getnframes())
    at = whole.find(part) if part else -1
    while at > 0 and at % 2:                            # (a frame offset: on a 16-bit sample boundary)
        at = whole.find(part, at + 1)
    if at < 0:
        raise ValueError(f"tidy_full's trimmed clip of {text!r} is not a slice of the clip it was given")
    lead = at // 2 / RATE
    return [[lead + s, lead + e] for s, e in times], lead


def clip_words(server, x, text):
    """`x`, 16 kHz samples of `text`, timed as wav_words does its WAV. → (words, lead)"""
    return wav_words(server, to_wav(x), text)


def entry(name, text, seconds, timed=None):
    """One clip's manifest entry; `timed`: its (words, lead) when it has word times."""
    clip = {"speaker": "void" if name in VOID_LINES else "room" if name == ROOM_CLIP else "you", "text": text,
            "seconds": seconds}
    if timed is not None:
        clip["words"] = [[round(s, 3), round(e, 3)] for s, e in timed[0]]
        if name in VOID_LINES:
            clip["lead"] = round(timed[1], 3)
    return clip


def clip_texts():
    return {**VOID_LINES, **YOU_LINES, LONG_TURN[0]: " ".join(LONG_TURN[1]), ROOM_CLIP: song_words()}


def render(server, say, names=None):
    """The clips named in `names` (None: all of them), rendered. → {file: samples}; `say` (piper) is only called for
    yours."""
    import numpy as np
    want = (lambda n: True) if names is None else (lambda n: n in names)
    audio = {name: void_clip(server, text) for name, text in VOID_LINES.items() if want(name)}
    audio.update({name: say()(text) for name, text in YOU_LINES.items() if want(name)})
    if want(LONG_TURN[0]):
        gap, say_ = np.zeros(int(PAUSE * RATE)), say()
        parts = [say_(t) for t in LONG_TURN[1]]
        audio[LONG_TURN[0]] = np.concatenate([p for part in parts for p in (part, gap)][:-1])
    if want(ROOM_CLIP):
        audio[ROOM_CLIP] = room_music(server)
    return audio


def manifest_of(clips, preset, scenes):
    return {"generator": str(Path(__file__).resolve().relative_to(ROOT)),
            "rate": RATE,
            "voices": {"void": {"engine": "kokoro", "preset": VOID_PRESET, "voice": preset["kokoro"],
                                "kpitch": preset["kpitch"]},
                       "you": {"engine": "piper", "voice": YOU_VOICE},
                       "room": {"engine": "kokoro", "voice": SINGER, "sung": True}},
            "clips": clips, "scenes": scenes}


def piper_once():
    """A `say` for render() that loads piper on its first use only."""
    voice = []

    def get():
        if not voice:
            voice.append(you_voice())
        return voice[0]
    return get


@contextlib.contextmanager
def void_server():
    """app/server.py imported against a throwaway config and data folder (import_server), ONNX capped."""
    cap_onnx_threads()
    with tempfile.TemporaryDirectory(prefix="void-scenes-") as tmp:
        yield import_server(Path(tmp).resolve())


def generate(dest, server):
    """Write every clip and manifest.json into `dest`. → {file: frames}."""
    dest.mkdir(parents=True, exist_ok=True)
    audio = render(server, piper_once())
    preset = server.VOICES[VOID_PRESET]
    texts, clips = clip_texts(), {}
    for name, x in audio.items():
        wav = to_wav(x)
        (dest / name).write_bytes(wav)
        timed = wav_words(server, wav, texts[name]) if name in TIMED else None
        clips[name] = entry(name, texts[name], round(len(x) / RATE, 4), timed)
    (dest / "manifest.json").write_text(json.dumps(manifest_of(clips, preset, SCENES), indent=2) + "\n", encoding="utf-8")
    return {name: len(x) for name, x in audio.items()}


def write_missing():
    """Write only what the tree lacks: each clip with no WAV in OUT, and the "words" and "lead" of each TIMED clip whose
    manifest entry has none (timed from the WAV in the tree, a clip piper cannot reproduce included); the scenes come
    from SCENES. A WAV already in the tree is never rewritten, and every other manifest entry is kept as it stands.
    → the names of the clips written."""
    manifest = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
    missing = [n for n in clip_texts() if not (OUT / n).exists()]
    with void_server() as server:
        audio = render(server, piper_once(), set(missing))
        preset = server.VOICES[VOID_PRESET]
        texts, clips = clip_texts(), {}
        for name in missing:
            (OUT / name).write_bytes(to_wav(audio[name]))
        for name in texts:
            old = None if name in missing else manifest["clips"].get(name)    # (a clip rewritten here is timed anew)
            have = old if old is not None else entry(name, texts[name], round(len(audio[name]) / RATE, 4))
            if name in TIMED and "words" not in have:
                wav = (OUT / name).read_bytes()
                have = entry(name, texts[name], have["seconds"], wav_words(server, wav, texts[name]))
            clips[name] = have
    manifest = dict(manifest, clips=clips, scenes=SCENES)
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return missing


def frames(path):
    with wave.open(str(path), "rb") as w:
        return w.getnframes()


def check():
    """Regenerate into a scratch folder and compare each clip's length with the committed one, and each TIMED clip's
    "words" and "lead" with what tidy_full makes of the committed WAV itself: a re-render of a piper clip is not
    byte-identical and moves its word times by up to 60 ms, so a fresh render cannot vouch for them, where the file
    they were taken from can (tidy_full is deterministic). → exit status."""
    old = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))["clips"]
    texts, bad = clip_texts(), 0
    with void_server() as server, tempfile.TemporaryDirectory(prefix="void-scenes-check-") as tmp:
        fresh = generate(Path(tmp), server)
        for name, n in sorted(fresh.items()):
            have = OUT / name
            was = frames(have) if have.exists() else None
            same_bytes = have.exists() and have.read_bytes() == (Path(tmp) / name).read_bytes()
            want = {}
            if name in TIMED and have.exists():
                want = {k: v for k, v in entry(name, texts[name], 0, wav_words(server, have.read_bytes(), texts[name])).items()
                        if k in ("words", "lead")}
            timed = {k: v for k, v in old.get(name, {}).items() if k in ("words", "lead")} == want
            ok = was == n and timed
            bad += not ok
            print(f"{'ok  ' if ok else 'DIFF'} {name:24} committed {was if was is not None else '-':>7} "
                  f"fresh {n:>7} frames ({n / RATE:.4f} s){'  bytes identical' if same_bytes else ''}"
                  f"{'' if timed else '  word times differ'}")
    print("durations and word times match" if not bad else f"{bad} clip(s) differ in duration or word times")
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true",
                    help="regenerate elsewhere and compare durations and word times to the tree")
    ap.add_argument("--missing", action="store_true",
                    help="write only the clips and word times the tree lacks, leaving every WAV already there as it is")
    args = ap.parse_args()
    if args.check:
        sys.exit(check())
    if args.missing:
        print("wrote " + (", ".join(write_missing()) or "no clip") + " (word times and scenes brought up to date)")
        return
    with void_server() as server:
        written = generate(OUT, server)
    for name, n in sorted(written.items()):
        print(f"{name:24} {n / RATE:7.3f} s {(OUT / name).stat().st_size:>8} bytes")


if __name__ == "__main__":
    main()
