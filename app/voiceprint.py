"""The owner's voiceprint: local speaker embeddings, so a follow-up without "hey Void" can be checked against the voice
that has been saying "hey Void".

The embedding model is WeSpeaker's ResNet34 trained on VoxCeleb (ONNX, ~26 MB, 256-dim), fetched on first use into
`model_dir` the way kokoro_fetch.py fetches Kokoro: sherpa-onnx's GitHub release first, its Hugging Face mirror if that's
blocked. It runs on onnxruntime, which faster-whisper already installed. Its input is Kaldi-style log mel filterbanks
(80 bins, 25 ms frames every 10 ms, mean-normalised per clip), computed here in numpy.

The print is the running mean of the enrolled clips' unit embeddings, at most 30 clips' worth (after that each new clip
moves it by 1/30), saved to `path` after every enrolment together with FORMAT, the print's format version. A saved print whose version is
missing or isn't FORMAT is treated as absent: the load starts from zero and says so once on stderr, so a print made by an
older embedding or averaging is never scored against. Change FORMAT whenever the saved print's meaning changes. `score` is the cosine between a clip and the print, or None
until MIN_ENROLL clips are in. Without the model, `available` is False, `why` says why, and nothing is enrolled or scored.
"""
import io
import sys
import urllib.request
from pathlib import Path

import numpy as np

SR = 16000
MIN_ENROLL = 5           # no score below this many clips
MAX_ENROLL = 30          # the running mean counts at most this many clips
FORMAT = 1               # the saved print's format version; a print saved under another (or none) is not used
MODEL = "wespeaker_en_voxceleb_resnet34.onnx"
SOURCES = ["https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/",
           "https://huggingface.co/csukuangfj/speaker-embedding-models/resolve/main/"]
MAX_SAMPLES = 3 * SR     # embed at most the first 3 s of a clip
MIN_SAMPLES = SR // 4    # shorter than this, there's too little voice to embed

_said = set()            # why-not lines already printed this process


def fetch(folder):
    """Fetch the model into `folder` if it's missing. → the model's path. Raises when every source fails."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / MODEL
    if dest.exists():
        return dest
    errors = []
    for base in SOURCES:
        try:
            with urllib.request.urlopen(base + MODEL, timeout=60) as r:
                data = r.read()
            part = dest.with_name(dest.name + ".part")
            part.write_bytes(data)
            part.rename(dest)
            return dest
        except Exception as e:  # noqa: BLE001
            errors.append(f"{base.split('/')[2]}: {e}")
    raise RuntimeError("couldn't download the voiceprint model (" + "; ".join(errors) + ")")


def _mel_banks(n_fft=512, n_mels=80, low=20.0, high=SR / 2):
    """Kaldi's triangular mel filters, on the mel scale 1127 ln(1 + f/700). → (n_mels, n_fft//2) weights."""
    mel = lambda f: 1127.0 * np.log(1.0 + np.asarray(f) / 700.0)  # noqa: E731
    lo, hi = mel(low), mel(high)
    delta = (hi - lo) / (n_mels + 1)
    bins = mel(np.arange(n_fft // 2) * SR / n_fft)
    left = lo + np.arange(n_mels)[:, None] * delta
    centre, right = left + delta, left + 2 * delta
    up, down = (bins - left) / (centre - left), (right - bins) / (right - centre)
    return np.maximum(0.0, np.minimum(up, down)).astype(np.float32)


_BANKS = _mel_banks()
_WINDOW = np.hamming(400).astype(np.float32)


def fbank(pcm: bytes) -> np.ndarray:
    """16 kHz 16-bit mono PCM → (frames, 80) log mel filterbanks, as Kaldi computes them (no dither), mean-normalised."""
    x = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)   # WeSpeaker feeds samples at int16 scale
    n = 1 + (len(x) - 400) // 160
    frames = np.lib.stride_tricks.sliding_window_view(x, 400)[::160][:n].copy()
    frames -= frames.mean(axis=1, keepdims=True)
    frames[:, 1:] -= 0.97 * frames[:, :-1]
    frames[:, 0] -= 0.97 * frames[:, 0]
    power = np.abs(np.fft.rfft(frames * _WINDOW, n=512)) ** 2
    feats = np.log(np.maximum(power[:, :256] @ _BANKS.T, np.finfo(np.float32).eps))
    return (feats - feats.mean(axis=0)).astype(np.float32)


class Voiceprint:
    def __init__(self, path: Path, model_dir: Path):
        self.path, self.model_dir = Path(path), Path(model_dir)
        self.session, self.why = None, ""
        self.print, self.enrolled = None, 0
        try:
            import onnxruntime as ort
            opts = ort.SessionOptions()
            opts.intra_op_num_threads = 1
            opts.log_severity_level = 3
            self.session = ort.InferenceSession(str(fetch(self.model_dir)), opts,
                                                providers=["CPUExecutionProvider"])
        except Exception as e:  # noqa: BLE001
            self.why = f"voiceprint unavailable: {e}"
            if self.why not in _said:
                _said.add(self.why)
                print(f"[void] {self.why}", file=sys.stderr)
        self.available = self.session is not None
        self._load()

    def _load(self):
        try:
            with np.load(io.BytesIO(self.path.read_bytes())) as f:
                if "version" not in f.files or int(f["version"]) != FORMAT:
                    found = int(f["version"]) if "version" in f.files else "none"
                    print(f"[void] voiceprint at {self.path} is format version {found}, not {FORMAT}: starting over",
                          file=sys.stderr)
                    return
                self.print, self.enrolled = f["print"].astype(np.float32), int(f["enrolled"])
        except FileNotFoundError:
            pass
        except Exception as e:  # noqa: BLE001
            print(f"[void] voiceprint at {self.path} unreadable, starting over: {e}", file=sys.stderr)

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        buf = io.BytesIO()
        np.savez(buf, print=self.print, enrolled=np.int64(self.enrolled), version=np.int64(FORMAT))   # a file object: no ".npz" tacked on
        part = self.path.with_name(self.path.name + ".part")
        part.write_bytes(buf.getvalue())
        part.replace(self.path)

    def embed(self, pcm: bytes) -> np.ndarray | None:
        """The clip's unit-length speaker embedding, or None without the model or with too little audio."""
        if not self.available or len(pcm) // 2 < MIN_SAMPLES:
            return None
        pcm = pcm[:MAX_SAMPLES * 2]
        e = self.session.run(None, {"feats": fbank(pcm)[None]})[0][0].astype(np.float32)
        norm = float(np.linalg.norm(e))
        return e / norm if norm > 0 else None

    def enroll(self, pcm: bytes) -> None:
        e = self.embed(pcm)
        if e is None:
            return
        n = min(self.enrolled + 1, MAX_ENROLL)
        self.print = e if self.print is None else self.print + (e - self.print) / n
        self.enrolled = n
        self._save()

    def score(self, pcm: bytes) -> float | None:
        if self.enrolled < MIN_ENROLL or self.print is None:
            return None
        e = self.embed(pcm)
        if e is None:
            return None
        return float(e @ self.print / (np.linalg.norm(self.print) or 1.0))
