"""The follow-up gate (app/gate.py): one decision on a clip heard in the follow-up window without "hey Void". The
owner is kept, a clip Whisper heard nothing in is dropped, and the gate can be switched off in the config. Nothing in it
judges whose voice a clip is: the voiceprint could not tell the owner from Void's echo, so it is gone.

    python3 -m unittest tests.test_gate -v
"""
import ast
import sys
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
SCENES = ROOT / "tests" / "fixtures" / "scenes"
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "tests"))
import suite_data  # noqa: E402,F401  (Void's data folder: the suite's own, set before server.py settles it)
import fakes  # noqa: E402

try:
    import server
except Exception as e:  # noqa: BLE001
    server = None
    IMPORT_ERR = e
else:
    IMPORT_ERR = None

try:
    import gate
except Exception as e:  # noqa: BLE001
    gate, GATE_ERR = None, e
else:
    GATE_ERR = None

OWNER = ["you_overlap.wav", "you_long_pauses.wav"]
MUSIC = "room_music.wav"


def pcm(name):
    with wave.open(str(SCENES / name), "rb") as w:
        return w.readframes(w.getnframes())


def config(**over):
    cfg = dict(server.DEFAULTS)
    cfg.update(over)
    return cfg


def follow_up(clip, heard, text=None):
    """A follow-up burst of `clip`, all of it speech (so the speech share passes), with Whisper's `heard` (None: not
    judged)."""
    seconds = len(clip) / 32000
    return gate.Burst(text=heard.text if text is None else text, heard=heard, speech=seconds, seconds=seconds,
                      kind="follow", talking=False)


@unittest.skipIf(server is None, f"server.py doesn't import here: {IMPORT_ERR}")
class Gate(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(gate, f"app/gate.py doesn't import: {GATE_ERR}")

    def judge(self, b, cfg=None):
        v = gate.judge(b, [], config() if cfg is None else cfg)
        self.assertIsInstance(v, gate.Verdict)
        self.assertIsInstance(v.keep, bool)
        self.assertIn(v.why, gate.WHY)
        return v

    def test_owner_follow_up_is_kept(self):
        for n in OWNER:
            with self.subTest(n):
                clip = pcm(n)
                v = self.judge(follow_up(clip, fakes.heard(seconds=len(clip) / 32000)))
                self.assertTrue(v.keep, f"the owner's {n} dropped ({v.why})")
                self.assertEqual(v.why, "kept")

    def test_a_clip_whisper_heard_nothing_in_is_dropped_as_noise(self):
        v = self.judge(follow_up(pcm(MUSIC), fakes.heard("", sure=False)))
        self.assertFalse(v.keep, "a clip with no kept segment was kept")
        self.assertEqual(v.why, "noise")

    # ---- switched off in the config
    def test_the_gate_switched_off_keeps_an_unjudged_follow_up_but_not_nothing(self):
        clip = pcm(MUSIC)
        cfg = config(voice_gate=False)
        v = self.judge(follow_up(clip, None, text="something was said here"), cfg)
        self.assertTrue(v.keep, f"dropped ({v.why}) with voice_gate off")
        v = self.judge(follow_up(clip, fakes.heard("", sure=False)), cfg)
        self.assertFalse(v.keep, "a clip with no kept segment kept with voice_gate off")
        self.assertEqual(v.why, "noise")


@unittest.skipIf(server is None, f"server.py doesn't import here: {IMPORT_ERR}")
class Config(unittest.TestCase):
    def test_config_has_the_gate_on_by_default_and_no_voice_threshold(self):
        self.assertIs(server.DEFAULTS.get("voice_gate"), True, "DEFAULTS has no voice_gate switched on")
        self.assertNotIn("voice_min", server.DEFAULTS, "DEFAULTS still has a voiceprint threshold")

    def test_the_voiceprint_is_gone(self):
        self.assertFalse((ROOT / "app" / "voiceprint.py").exists(), "app/voiceprint.py is still there")
        self.assertFalse(hasattr(server, "Voice"), "server.Voice is still there")


@unittest.skipIf(gate is None, f"app/gate.py doesn't import here: {GATE_ERR}")
class Noise(unittest.TestCase):
    """gate.is_noise: nothing, a stock filler, or a whole sentence Whisper repeats on room sound; a short phrase you
    say over and over is you, answering him."""

    def test_nothing_is_noise(self):
        for heard in ("", "   ", " . "):
            self.assertTrue(gate.is_noise(heard), repr(heard))

    def test_filler_is_noise(self):
        for heard in sorted(gate.NOISE_WORDS) + ["Thank you for watching.", "Um."]:
            self.assertTrue(gate.is_noise(heard), heard)

    def test_whispers_looping_sentence_is_noise(self):
        for heard in ("The two of them were the two of them. The two of them were the two of them",
                      "It is a pleasure to be here. It is a pleasure to be here"):
            self.assertTrue(gate.is_noise(heard), heard)

    def test_your_repeated_phrase_is_not_noise(self):
        for heard in ("Not yet, not yet", "Wait, wait, wait, wait, wait, wait"):
            self.assertFalse(gate.is_noise(heard), heard)

    def test_a_request_is_not_noise(self):
        for heard in ("please add milk to the shopping list", "thank you, now add eggs"):
            self.assertFalse(gate.is_noise(heard), heard)


@unittest.skipIf(gate is None, f"app/gate.py doesn't import here: {GATE_ERR}")
class StopSaid(unittest.TestCase):
    """gate.stop_said: a stop phrase said as one, opening or closing a clause of what was heard."""

    def test_stop_phrases_said_as_stops(self):
        for heard in ("Stop", "Shut up", "Hold on", "Void, stop", "okay okay hold on a second",
                      "Stop, stop, stop, stop stop, stop Void stop, Void stop, Void, shut the"):
            self.assertTrue(gate.stop_said(heard), heard)

    def test_stop_word_inside_a_sentence_is_not_a_stop(self):
        self.assertFalse(gate.stop_said("It goes to the time to realize that it's ready to have a stop on, and it's going."))

    def test_no_stop_phrase(self):
        for heard in ("please add milk to the shopping list", ""):
            self.assertFalse(gate.stop_said(heard), repr(heard))


SERVER_PY = ROOT / "app" / "server.py"
MOVED = ("is_echo", "is_noise", "stop_said")
SEGMENT_FIELDS = {"avg_logprob", "compression_ratio", "no_speech_prob", "logprob", "no_speech"}


class Homes(unittest.TestCase):
    """The echo, noise and stop-phrase tests and Whisper's confidence thresholds live in gate; server.py imports them."""

    @classmethod
    def setUpClass(cls):
        cls.tree = ast.parse(SERVER_PY.read_text(encoding="utf-8"))

    def test_server_defines_no_echo_noise_or_stop_test(self):
        defined = sorted({n.name for n in ast.walk(self.tree)
                          if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in MOVED})
        self.assertEqual(defined, [], f"still defined in server.py: {defined}")

    @unittest.skipIf(server is None or gate is None, f"server.py / gate.py don't import here: {IMPORT_ERR or GATE_ERR}")
    def test_server_names_are_gates_own(self):
        for name in MOVED:
            with self.subTest(name):
                if hasattr(server, name):
                    self.assertIs(getattr(server, name), getattr(gate, name), f"server.{name} is not gate.{name}")

    def test_server_compares_no_whisper_confidence(self):
        hits = []
        for n in ast.walk(self.tree):
            if isinstance(n, ast.Compare):
                fields = {a.attr for side in [n.left, *n.comparators] for a in ast.walk(side)
                          if isinstance(a, ast.Attribute) and a.attr in SEGMENT_FIELDS}
                if fields:
                    hits.append(f"server.py:{n.lineno} compares {', '.join(sorted(fields))}")
        self.assertEqual(hits, [], "a segment filter or logprob comparison in server.py")


KINDS = ("listen", "wake", "follow", "over", "peek")


@unittest.skipIf(gate is None, f"app/gate.py doesn't import here: {GATE_ERR}")
class SpokenEnough(unittest.TestCase):
    """gate.spoken_enough: every kind needs MIN_SPEECH; every kind but "follow" also needs SPEECH_SHARE of the burst."""

    def test_too_little_speech_is_not_enough_for_any_kind(self):
        speech = gate.MIN_SPEECH * 0.9
        for kind in KINDS:
            with self.subTest(kind):
                self.assertFalse(gate.spoken_enough(speech, speech, kind), f"{speech}s of speech enough for {kind}")

    def test_enough_speech_and_share_is_enough_for_every_kind(self):
        for kind in KINDS:
            with self.subTest(kind):
                self.assertTrue(gate.spoken_enough(gate.MIN_SPEECH, gate.MIN_SPEECH / gate.SPEECH_SHARE, kind))
                self.assertTrue(gate.spoken_enough(1.0, 2.0, kind))

    def test_a_small_share_is_enough_for_a_follow_up_only(self):
        speech, seconds = 1.0, 1.0 / gate.SPEECH_SHARE * 2      # (half the share needed)
        self.assertTrue(gate.spoken_enough(speech, seconds, "follow"), "a follow-up dropped for its speech share")
        for kind in set(KINDS) - {"follow"}:
            with self.subTest(kind):
                self.assertFalse(gate.spoken_enough(speech, seconds, kind), f"{kind} kept at half the speech share")


REQUEST = "please add milk to the shopping list"


def whisper(text=REQUEST, logprob=-0.2, no_speech=0.02):
    """A follow-up's Whisper result, the fields gate reads off server.Heard."""
    return SimpleNamespace(text=text, logprob=logprob, no_speech=no_speech, seconds=2.0)


@unittest.skipIf(gate is None, f"app/gate.py doesn't import here: {GATE_ERR}")
class Judge(unittest.TestCase):
    """gate.judge runs its checks in a fixed order and returns at the first drop: speech share, echo, stop phrase,
    noise, while talking, wake word, Whisper confidence."""

    def burst(self, **over):
        b = dict(text=REQUEST, heard=None, speech=2.0, seconds=3.0, kind="follow", talking=False)
        b.update(over)
        if b["kind"] == "follow" and "heard" not in over:
            b["heard"] = whisper(b["text"])
        return gate.Burst(**b)

    def judge(self, b, spoken=(), **cfg):
        v = gate.judge(b, list(spoken), {"voice_gate": True, **cfg})
        self.assertIsInstance(v, gate.Verdict)
        self.assertIn(v.why, gate.WHY)
        return v

    def dropped(self, v, why):
        self.assertEqual((v.keep, v.why, v.act, v.rest), (False, why, "drop", ""))

    def kept_follow_up(self, v, text):
        self.assertEqual((v.keep, v.why, v.act, v.rest), (True, "kept", "follow", text))

    # ---- the legacy bridge is gone
    def test_the_old_follow_up_gate_is_gone(self):
        self.assertFalse(hasattr(gate, "_follow_legacy"), "gate._follow_legacy is still there")

    # ---- 1. speech share
    def test_too_little_speech_is_dropped_for_every_kind(self):
        for kind in KINDS:
            with self.subTest(kind):
                self.dropped(self.judge(self.burst(kind=kind, speech=gate.MIN_SPEECH * 0.9)), "no speech")

    def test_a_small_share_drops_every_kind_but_a_follow_up(self):
        speech, seconds = 1.0, 1.0 / gate.SPEECH_SHARE * 2
        self.kept_follow_up(self.judge(self.burst(speech=speech, seconds=seconds)), REQUEST)
        for kind in set(KINDS) - {"follow"}:
            with self.subTest(kind):
                self.dropped(self.judge(self.burst(kind=kind, speech=speech, seconds=seconds)), "no speech")

    def test_speech_share_comes_before_echo(self):
        v = self.judge(self.burst(speech=gate.MIN_SPEECH * 0.9), spoken=[REQUEST])
        self.dropped(v, "no speech")

    # ---- 2. echo
    def test_his_own_voice_heard_back_is_dropped_as_echo(self):
        said = "I have added milk to your shopping list"
        self.dropped(self.judge(self.burst(text=said), spoken=[said]), "echo")

    def test_echo_comes_before_noise(self):
        said = "It is a pleasure to be here"
        v = self.judge(self.burst(text=f"{said}. {said}"), spoken=[said, said])
        self.dropped(v, "echo")

    # ---- 4. noise
    def test_empty_text_is_noise(self):
        for text in ("", " . "):
            with self.subTest(repr(text)):
                self.dropped(self.judge(self.burst(text=text)), "noise")

    def test_a_looping_sentence_is_noise(self):
        text = "It is a pleasure to be here. It is a pleasure to be here"
        self.dropped(self.judge(self.burst(text=text)), "noise")

    def test_filler_is_noise(self):
        self.dropped(self.judge(self.burst(text="Thank you.")), "noise")

    # ---- 5. while talking
    def test_a_request_heard_while_he_talks_is_dropped(self):
        self.dropped(self.judge(self.burst(kind="over", talking=True)), "while talking")

    def test_noise_comes_before_while_talking(self):
        self.dropped(self.judge(self.burst(kind="over", talking=True, text="Um.")), "noise")

    # ---- 6. wake word
    def test_a_wake_burst_without_hey_void_is_dropped(self):
        self.dropped(self.judge(self.burst(kind="wake")), "no wake word")

    def test_a_wake_burst_with_hey_void_is_a_request(self):
        v = self.judge(self.burst(kind="wake", text="Hey Void, add milk to the list."))
        self.assertEqual((v.keep, v.why, v.act), (True, "kept", "request"))
        self.assertEqual(v.rest.strip(" .,!?"), "add milk to the list")

    # ---- 7. Whisper confidence
    def test_a_one_word_follow_up_is_kept(self):
        for on in (True, False):
            with self.subTest(voice_gate=on):
                self.kept_follow_up(self.judge(self.burst(text="Yes.", heard=whisper("Yes.")), voice_gate=on), "Yes.")

    def test_a_one_word_follow_up_still_needs_whispers_confidence(self):
        b = self.burst(text="Milk.", heard=whisper("Milk.", logprob=gate.MIN_LOGPROB - 0.5))
        self.dropped(self.judge(b), "low confidence")

    def test_a_follow_up_whisper_guessed_at_is_dropped(self):
        b = self.burst(heard=whisper(logprob=gate.MIN_LOGPROB - 0.5))
        self.dropped(self.judge(b), "low confidence")

    def test_a_confident_follow_up_is_kept(self):
        self.kept_follow_up(self.judge(self.burst()), REQUEST)


if __name__ == "__main__":
    unittest.main()
