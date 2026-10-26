"""Committed audio fixtures for the replay harness: small 16 kHz mono WAVs in tests/fixtures/scenes/, made once by a
committed generator script so CI never needs Kokoro or piper. Void's lines are in Void's real voice: Kokoro with the
"cute" preset, made through Void's own synth path in app/server.py. "You" is a clearly different voice (piper is
fine). The clips serve these scenes: Void talking alone; "stop", "hold on", "shut up" and "hey Void" (each with a few
more words) said over him; you answering just after he finishes; you starting in his last second and
carrying on; a long turn of yours with mid-thought pauses. The whole set stays small (under 3 MB).

Contract with the generator (tests/fixtures/scenes/manifest.json):
    {"generator": "<repo-relative path of the committed script>",
     "voices": {"void": {"engine": "kokoro", "preset": "cute", "voice": "<VOICES['cute']['kokoro']>",
                         "kpitch": <VOICES['cute']['kpitch']>},
                "you": {"engine": ..., "voice": ...}},
     "clips":  {"<file>.wav": {"speaker": "void"|"you"|<other, e.g. room music>, "text": "<words spoken>"}, ...},
     "scenes": {"<scene>": {"void": "<file>.wav" | null, "you": "<file>.wav" | null}, ...}}
Every WAV in the folder is listed under "clips"; clips and scenes beyond the required ones (room music) are allowed.

    python3 -m unittest discover -s tests
"""
import ast
import json
import re
import unittest
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCENES = ROOT / "tests" / "fixtures" / "scenes"
MANIFEST = SCENES / "manifest.json"
RATE = 16000
MAX_BYTES = 3 * 1024 * 1024

INTERRUPTS = {"interrupt_stop": "stop", "interrupt_hold_on": "hold on",
              "interrupt_shut_up": "shut up", "interrupt_hey_void": "hey void"}
REQUIRED = {"void_alone": ("void",), **{s: ("void", "you") for s in INTERRUPTS},
            "answer_after": ("void", "you"), "overlap_last_second": ("void", "you"), "long_pauses": ("you",)}

TURN_QUIET = 1.2           # app/server.py: this much quiet ends your turn, so a mid-thought pause is shorter
BARGE_MAX = 12             # app/server.py: the old cut-off a long turn has to outlast
PAUSE_MIN = 0.6            # a pause, not a breath between words


def server_literal(name):
    """The literal value assigned to `name` at the top of app/server.py, read without importing it."""
    tree = ast.parse((ROOT / "app" / "server.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return node.value
    raise LookupError(name)


VOID_PRESET = "cute"         # Void's real voice is this preset, spoken by Kokoro


def void_voices():
    """Void's real voice: the app/server.py VOICES entry for his preset (its Kokoro voice and kpitch)."""
    return ast.literal_eval(server_literal("VOICES"))[VOID_PRESET]


def calls_server_synth(path):
    """Whether the script at `path` imports app/server.py and calls its synth path (synth(...) or server.synth(...))."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = any(isinstance(n, ast.Import) and any(a.name.split(".")[-1] == "server" for a in n.names)
                  or isinstance(n, ast.ImportFrom) and (n.module or "").split(".")[-1] == "server"
                  for n in ast.walk(tree))
    called = any(isinstance(n, ast.Call) and (getattr(n.func, "id", None) == "synth"
                                              or getattr(n.func, "attr", None) == "synth")
                 for n in ast.walk(tree))
    return imports and called


def load(path):
    """→ (samples as ints, seconds), asserting 16 kHz, mono, 16-bit."""
    with wave.open(str(path), "rb") as w:
        fmt = (w.getframerate(), w.getnchannels(), w.getsampwidth())
        raw = w.readframes(w.getnframes())
    if fmt != (RATE, 1, 2):
        raise AssertionError(f"{path.name}: rate/channels/width {fmt}, want {(RATE, 1, 2)}")
    samples = memoryview(raw).cast("h").tolist()
    return samples, len(samples) / RATE


def frame_levels(samples, frame=320):
    """RMS per 20 ms frame."""
    return [(sum(x * x for x in samples[i:i + frame]) / frame) ** 0.5 for i in range(0, len(samples) - frame + 1, frame)]


def pauses(samples):
    """Lengths in seconds of the quiet stretches between the first and last spoken frame."""
    levels = frame_levels(samples)
    loud = [lv > 0.05 * max(levels) for lv in levels]
    first, last = loud.index(True), len(loud) - 1 - loud[::-1].index(True)
    out, run = [], 0
    for x in loud[first:last + 1]:
        if x:
            if run:
                out.append(run * 0.02)
            run = 0
        else:
            run += 1
    return out


def median_pitch(samples):
    """Median fundamental (Hz) over the loud frames, by autocorrelation over 70-400 Hz."""
    import numpy as np
    x = np.asarray(samples, dtype=np.float64)
    n, lo, hi = 640, RATE // 400, RATE // 70
    frames = [x[i:i + n] for i in range(0, len(x) - n, n)]
    rms = np.array([np.sqrt(np.mean(f * f)) for f in frames])
    f0 = []
    for f in (f for f, r in zip(frames, rms) if r > 0.3 * rms.max()):
        f = f - f.mean()
        ac = np.correlate(f, f, "full")[n - 1:]
        if ac[0] <= 0:
            continue
        lag = lo + int(np.argmax(ac[lo:hi]))
        if ac[lag] / ac[0] > 0.3:
            f0.append(RATE / lag)
    if not f0:
        raise AssertionError("no voiced frames found")
    return float(np.median(f0))


def words(text):
    return re.findall(r"[a-z']+", text.lower())


class SceneFixtures(unittest.TestCase):
    def manifest(self):
        if not MANIFEST.exists():
            self.fail(f"no scene fixtures: {MANIFEST.relative_to(ROOT)} is missing")
        return json.loads(MANIFEST.read_text(encoding="utf-8"))

    def clip(self, scene, who):
        m = self.manifest()
        name = m["scenes"][scene][who]
        self.assertIn(name, m["clips"], f"{scene}.{who} names {name}, which isn't a listed clip")
        self.assertEqual(m["clips"][name]["speaker"], who, f"{scene}.{who} is {name}")
        return name, m["clips"][name], *load(SCENES / name)

    def test_generator_is_committed(self):
        gen = ROOT / self.manifest()["generator"]
        self.assertTrue(gen.is_file(), gen)
        self.assertEqual(gen.suffix, ".py")

    def test_every_fixture_loads_at_16k_mono(self):
        m = self.manifest()
        wavs = sorted(p.name for p in SCENES.glob("*.wav"))
        self.assertTrue(wavs, "no WAVs")
        self.assertEqual(sorted(n for n in m["clips"] if n.endswith(".wav")), wavs, "manifest and folder disagree")
        for name in wavs:
            with self.subTest(name):
                samples, sec = load(SCENES / name)
                self.assertGreater(sec, 0.5)
                self.assertGreater(max(map(abs, samples)), 1000, "silent")

    def test_set_is_small(self):
        total = sum(p.stat().st_size for p in SCENES.rglob("*") if p.is_file()) if SCENES.exists() else 0
        self.manifest()
        self.assertLess(total, MAX_BYTES, f"{total / 1e6:.2f} MB")

    def test_every_scene_is_served(self):
        scenes = self.manifest()["scenes"]
        for scene, who in REQUIRED.items():
            with self.subTest(scene):
                self.assertIn(scene, scenes)
                for part in ("void", "you"):
                    if part in who:
                        self.clip(scene, part)
                    else:
                        self.assertIsNone(scenes[scene].get(part), f"{scene} is Void alone")

    def test_void_speaks_in_his_real_voice(self):
        m = self.manifest()
        v, real = m["voices"]["void"], void_voices()
        self.assertEqual(v["engine"], "kokoro", "Void speaks with Kokoro, not piper")
        self.assertEqual(v.get("preset"), VOID_PRESET)
        self.assertEqual(v["voice"], real["kokoro"])
        self.assertEqual(v.get("kpitch"), real["kpitch"])
        gen = ROOT / m["generator"]
        self.assertTrue(calls_server_synth(gen), f"{m['generator']} doesn't make Void's lines with app/server.py's synth")
        you = m["voices"]["you"]
        self.assertNotEqual((you["engine"], you["voice"]), ("kokoro", real["kokoro"]), "you speak in Void's voice")

    def test_you_are_a_clearly_different_voice(self):
        m = self.manifest()
        self.assertNotEqual(m["voices"]["you"]["voice"], m["voices"]["void"]["voice"])
        void_f0 = median_pitch(self.clip("void_alone", "void")[2])
        you_f0 = median_pitch(self.clip("answer_after", "you")[2])
        ratio = max(void_f0, you_f0) / min(void_f0, you_f0)
        self.assertGreater(ratio, 1.3, f"Void ~{void_f0:.0f} Hz, you ~{you_f0:.0f} Hz: too alike")

    def test_void_talks_long_enough_to_be_talked_over(self):
        self.assertGreaterEqual(self.clip("void_alone", "void")[3], 4.0)

    def test_interrupts_are_said_as_people_say_them(self):
        for scene, phrase in INTERRUPTS.items():
            with self.subTest(scene):
                _, meta, _, sec = self.clip(scene, "you")
                w, p = words(meta["text"]), phrase.split()
                at = next((i for i in range(len(w)) if w[i:i + len(p)] == p), None)
                self.assertIsNotNone(at, f"{phrase!r} not in {meta['text']!r}")
                self.assertGreaterEqual(len(w) - at - len(p), 2, f"{meta['text']!r}: a few words after {phrase!r}")
                self.assertLess(sec, 6.0)

    def test_answer_starting_in_his_last_second_carries_on(self):
        self.assertGreaterEqual(self.clip("overlap_last_second", "you")[3], 3.0)

    def test_long_turn_has_mid_thought_pauses(self):
        _, _, samples, sec = self.clip("long_pauses", "you")
        self.assertGreater(sec, BARGE_MAX)
        gaps = pauses(samples)
        self.assertGreaterEqual(sum(g >= PAUSE_MIN for g in gaps), 2, f"pauses {gaps}")
        self.assertLess(max(gaps), TURN_QUIET, f"a pause that long ends the turn: {gaps}")


if __name__ == "__main__":
    unittest.main()
