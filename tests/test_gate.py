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
                      kind="follow", talking=False, rang=False)


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
        b.setdefault("rang", b["talking"])     # (his sound in the burst puts his voice in the air)
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
        v = self.judge(self.burst(speech=gate.MIN_SPEECH * 0.9, rang=True), spoken=[REQUEST])   # (echo, were it run)
        self.dropped(v, "no speech")

    # ---- 2. echo (only when his voice was in the air)
    def test_his_own_voice_heard_back_is_dropped_as_echo(self):
        said = "I have added milk to your shopping list"
        self.dropped(self.judge(self.burst(text=said, rang=True), spoken=[said]), "echo")

    def test_echo_comes_before_noise(self):
        said = "It is a pleasure to be here"
        v = self.judge(self.burst(text=f"{said}. {said}", rang=True), spoken=[said, said])
        self.dropped(v, "echo")

    def test_his_words_heard_after_he_went_quiet_are_never_echo(self):
        # docs/superpowers/specs/quiet-replies-design.md, app/gate.py: step 2 runs is_echo only when b.rang
        said = "I have added milk to your shopping list"
        self.dropped(self.judge(self.burst(text=said, rang=True), spoken=[said]), "echo")
        self.kept_follow_up(self.judge(self.burst(text=said, rang=False), spoken=[said]), said)
        for kind in KINDS:
            with self.subTest(kind):
                v = self.judge(self.burst(text=said, kind=kind, rang=False), spoken=[said])
                self.assertNotEqual(v.why, "echo", f"a {kind} burst heard after he went quiet dropped as echo")

    def test_step_two_on_both_sides_for_follow_wake_over_and_listen(self):
        # (the wake and over kinds need his name to be kept at all; his line is read back with it, so only rang differs)
        for kind, text, act in (("follow", "I have added milk to your shopping list", "follow"),
                                ("listen", "I have added milk to your shopping list", "request"),
                                ("wake", "Hey Void, I have added milk to your shopping list", "request"),
                                ("over", "Hey Void, I have added milk to your shopping list", "request")):
            with self.subTest(kind):
                self.dropped(self.judge(self.burst(text=text, kind=kind, rang=True), spoken=[text]), "echo")
                v = self.judge(self.burst(text=text, kind=kind, rang=False), spoken=[text])
                self.assertEqual((v.keep, v.why, v.act), (True, "kept", act), f"a {kind} burst with no ring was not kept")

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


# ---- Void's own stop phrase (the played stop phrases, timed, and the heard words, timed)
ECHO_WORD = gate.ECHO_WORD if gate is not None else 0.0   # s either side of a played stop phrase; read, never restated
EPS = 0.01                                                # a hundredth of a second, to sit just inside or past it
T = 100.0  # a monotonic moment while Void talks


def timed(text, start=T, step=0.3):
    """`text`'s words as gate.Words, each `step` s long, back to back from `start`."""
    return tuple(gate.Word(text=w, start=start + i * step, end=start + (i + 1) * step)
                 for i, w in enumerate(text.split()))


def played_stop(start=T, end=T + 0.4, text="stop"):
    """A stop phrase Void played, as gate.Word."""
    return gate.Word(text=text, start=start, end=end)


# every alternative of the STOP_RE and _STOP_WORDS alternations as they stood before STOP_PHRASES (as "fragment, a
# phrase it matches"), so the rebuild from one list can be held to the same answers
OLD_STOP_RE_ALTERNATIVES = (("stop", "stop"), ("wait", "wait"), ("shush", "shush"), ("shh+", "shhhh"), ("quiet", "quiet"),
                            ("be quiet", "be quiet"), ("shut up", "shut up"), ("hold on", "hold on"),
                            ("hang on", "hang on"), ("enough", "enough"), ("stop talking", "stop talking"),
                            ("that's enough", "that's enough"), ("thanks?(?: you)?", "thank you"),
                            ("thanks?(?: you)?", "thanks"), ("got it", "got it"))
# the phrases of STOP_RE that stop_said (the old _STOP_WORDS) never took: only the first words of "stop talking" count
NOT_SAID_IN_A_CLAUSE = ("wait", "quiet", "enough", "thank you", "thanks", "got it")
NOT_STOPS = ("please add milk to the shopping list", "", "stopping", "hold the door", "it's ready to have a stop on")


@unittest.skipIf(gate is None, f"app/gate.py doesn't import here: {GATE_ERR}")
class StopPhrasesList(unittest.TestCase):
    """STOP_RE and STOP_IN_RE are built from the one STOP_PHRASES list and match the phrases they matched before."""

    def test_stop_re_matches_every_old_alternative_and_its_wrappers(self):
        for fragment, said in OLD_STOP_RE_ALTERNATIVES:
            for text in (said, f"okay {said}", f"hey void {said}", f"{said} please", f"void {said} now"):
                with self.subTest(text=text):
                    self.assertTrue(gate.STOP_RE.fullmatch(text), f"{fragment!r}: {text!r}")

    def test_stop_re_matches_no_other_phrase(self):
        for text in NOT_STOPS:
            with self.subTest(text=text):
                self.assertFalse(gate.STOP_RE.fullmatch(text))

    def test_stop_said_takes_the_clause_phrases_only(self):
        for _, text in OLD_STOP_RE_ALTERNATIVES:
            with self.subTest(text=text):
                self.assertEqual(gate.stop_said(text), text not in NOT_SAID_IN_A_CLAUSE)
        for text in NOT_STOPS:
            with self.subTest(text=text):
                self.assertFalse(gate.stop_said(text))


@unittest.skipIf(gate is None, f"app/gate.py doesn't import here: {GATE_ERR}")
class StopPhrases(unittest.TestCase):
    """gate.stop_phrases: each run of consecutive words making up a STOP_PHRASES phrase (case and punctuation aside),
    as one Word from its first word's start to its last word's end."""

    def spans(self, words):
        found = gate.stop_phrases(words)
        self.assertIsInstance(found, list)
        for w in found:
            self.assertIsInstance(w, gate.Word)
        return [(round(w.start, 6), round(w.end, 6)) for w in found]

    def span(self, *words):
        return (round(words[0].start, 6), round(words[-1].end, 6))

    def test_a_one_word_stop_phrase_is_one_word_with_its_times(self):
        words = timed("okay so stop now")
        self.assertEqual(self.spans(words), [self.span(words[2])])

    def test_a_two_word_phrase_is_one_word_from_its_first_start_to_its_last_end(self):
        words = timed("okay hold on a second")
        self.assertEqual(self.spans(words), [self.span(words[1], words[2])])

    def test_the_guides_stop_words_are_each_found(self):
        # docs/GUIDE.md "Interrupting him": "stop" (or "wait", "shh", "be quiet")
        words = timed("wait okay be quiet")
        self.assertEqual(self.spans(words), [self.span(words[0]), self.span(words[2], words[3])])

    def test_case_and_punctuation_are_set_aside(self):
        for text in ("HOLD, on!", "That's enough.", "Shhh!", "Stop?"):
            words = timed(text)
            self.assertEqual(self.spans(words), [self.span(*words)], text)

    def test_each_run_is_its_own_word_in_order(self):
        words = timed("stop it hold on that's enough")
        self.assertEqual(self.spans(words),
                         [self.span(words[0]), self.span(words[2], words[3]), self.span(words[4], words[5])])

    def test_words_with_no_stop_phrase_find_nothing(self):
        for text in ("please hold the door", "add milk to the shopping list", ""):
            self.assertEqual(self.spans(timed(text)), [], repr(text))


@unittest.skipIf(gate is None, f"app/gate.py doesn't import here: {GATE_ERR}")
class StopNear(unittest.TestCase):
    """gate.stop_near(played, a, b): a played stop phrase overlaps [a - ECHO_WORD, b + ECHO_WORD]."""

    def test_a_span_on_a_played_stop_is_near(self):
        self.assertTrue(gate.stop_near([played_stop()], T + 0.1, T + 0.3))

    def test_a_span_just_after_a_played_stop_within_echo_word_is_near(self):
        p = played_stop()
        self.assertTrue(gate.stop_near([p], p.end + ECHO_WORD - EPS, p.end + ECHO_WORD + 0.2))

    def test_a_span_just_before_a_played_stop_within_echo_word_is_near(self):
        p = played_stop()
        self.assertTrue(gate.stop_near([p], p.start - ECHO_WORD - 0.2, p.start - ECHO_WORD + EPS))

    def test_a_span_past_echo_word_after_a_played_stop_is_not_near(self):
        p = played_stop()
        self.assertFalse(gate.stop_near([p], p.end + ECHO_WORD + EPS, p.end + ECHO_WORD + 0.4))

    def test_a_span_past_echo_word_before_a_played_stop_is_not_near(self):
        p = played_stop()
        self.assertFalse(gate.stop_near([p], p.start - ECHO_WORD - 0.4, p.start - ECHO_WORD - EPS))

    def test_nothing_played_is_never_near(self):
        self.assertFalse(gate.stop_near([], T, T + 0.4))

    def test_one_played_stop_near_is_enough(self):
        played = [played_stop(), played_stop(T + 5.0, T + 5.4)]
        self.assertTrue(gate.stop_near(played, T + 5.4 + ECHO_WORD - EPS, T + 6.5))
        self.assertFalse(gate.stop_near(played, T + 0.4 + ECHO_WORD + EPS, T + 5.0 - ECHO_WORD - EPS))


@unittest.skipIf(gate is None, f"app/gate.py doesn't import here: {GATE_ERR}")
class OwnStop(unittest.TestCase):
    """gate.own_stop(heard, played): heard holds a stop phrase, and every one overlaps a played one widened by
    ECHO_WORD."""

    def test_a_stop_heard_back_on_a_played_one_is_voids_own(self):
        self.assertTrue(gate.own_stop(timed("okay stop", start=T + 0.2), [played_stop()]))

    def test_a_stop_heard_in_the_ring_within_echo_word_is_voids_own(self):
        p = played_stop()
        self.assertTrue(gate.own_stop(timed("stop", start=p.end + ECHO_WORD - EPS), [p]))

    def test_words_with_no_stop_phrase_are_not_an_own_stop(self):
        self.assertFalse(gate.own_stop(timed("okay then", start=T), [played_stop()]))

    def test_nothing_heard_is_not_an_own_stop(self):
        self.assertFalse(gate.own_stop((), [played_stop()]))

    def test_a_stop_with_nothing_played_is_not_an_own_stop(self):
        self.assertFalse(gate.own_stop(timed("stop", start=T), []))

    def test_one_stop_past_echo_word_of_every_played_one_is_the_owners(self):
        heard = timed("stop", start=T + 0.1) + timed("stop", start=T + 0.4 + ECHO_WORD + 1.0)
        self.assertFalse(gate.own_stop(heard, [played_stop()]))

    def test_every_stop_near_a_played_one_is_voids_own(self):
        heard = timed("stop", start=T + 0.1) + timed("hold on", start=T + 3.1)
        played = [played_stop(), played_stop(T + 3.0, T + 3.6, "hold on")]
        self.assertTrue(gate.own_stop(heard, played))

    def test_a_played_stop_phrase_heard_as_another_is_voids_own(self):
        # any stop phrase matches any other: Void's "hold on" heard as "stop" is still his
        for said, heard in (("hold on", "stop"), ("stop", "that's enough"), ("that's enough", "shh")):
            played = [played_stop(T, T + 0.6, said)]
            self.assertTrue(gate.own_stop(timed(heard, start=T + 0.2), played), f"{said!r} heard as {heard!r}")


def stop_burst(kind, words, text="Stop.", rang=True):
    """A burst of `text` of `kind`, its words timed as `words` (None: not timed); over and peek are heard while he
    talks."""
    heard = whisper(text) if kind == "follow" else None
    return gate.Burst(text=text, heard=heard, speech=2.0, seconds=3.0, kind=kind, talking=kind in ("over", "peek"),
                      rang=rang, words=words)


@unittest.skipIf(gate is None, f"app/gate.py doesn't import here: {GATE_ERR}")
class JudgeOwnStop(unittest.TestCase):
    """judge step 2, echo: a stop phrase heard on the time one of his played drops as "echo", for every kind but
    "listen"; one that is past ECHO_WORD of his barges."""

    def judge(self, b, played=()):
        v = gate.judge(b, [], {"voice_gate": True}, played)
        self.assertIsInstance(v, gate.Verdict)
        self.assertIn(v.why, gate.WHY)
        return v

    def dropped_as_echo(self, v):
        self.assertEqual((v.keep, v.why, v.act, v.rest), (False, "echo", "drop", ""))

    def barged(self, v):
        self.assertEqual((v.keep, v.why, v.act, v.rest), (True, "kept", "barge", ""))

    def test_an_own_stop_drops_as_echo_for_every_kind_but_listen(self):
        p = played_stop()
        words = timed("Stop.", start=T + 0.1)
        for kind in ("wake", "follow", "over", "peek"):
            with self.subTest(kind):
                self.dropped_as_echo(self.judge(stop_burst(kind, words), [p]))
        v = self.judge(stop_burst("listen", words), [p])
        self.assertEqual((v.keep, v.why, v.act, v.rest), (True, "kept", "request", "Stop."))

    def test_an_own_stop_is_dropped_as_echo_with_rang_false_too(self):
        # D-01 states the rule on word times alone: a heard stop that sits on his played one needs no ringing flag
        p = played_stop()
        for kind in ("over", "peek"):
            self.dropped_as_echo(self.judge(stop_burst(kind, timed("Stop.", start=T + 0.1), rang=False), [p]))

    def test_an_untimed_burst_or_nothing_played_is_judged_as_before(self):
        p = played_stop()
        words = timed("Stop.", start=T + 0.1)
        for kind in ("over", "peek"):
            self.barged(self.judge(stop_burst(kind, None), [p]))
            self.barged(self.judge(stop_burst(kind, words)))

    def test_a_played_stop_heard_as_hold_on_is_his_own(self):
        p = played_stop()
        self.dropped_as_echo(self.judge(stop_burst("peek", timed("Hold on.", start=T + 0.1), "Hold on."), [p]))

    def test_the_owners_stop_just_past_echo_word_after_his_barges(self):
        p = played_stop()
        words = timed("Stop, stop.", start=p.end + ECHO_WORD + EPS)
        self.barged(self.judge(stop_burst("peek", words, "Stop, stop."), [p]))

    def test_his_stop_and_the_owners_in_one_burst_barges(self):
        p = played_stop()
        words = timed("stop", start=T + 0.1) + timed("stop", start=p.end + ECHO_WORD + 1.0)
        self.barged(self.judge(stop_burst("peek", words, "Stop. Stop."), [p]))

    def test_a_stop_within_echo_word_of_his_either_side_is_his(self):
        p = played_stop()
        for kind in ("over", "peek"):
            for start in (p.end + ECHO_WORD - EPS, p.start - ECHO_WORD - 0.3 + EPS):
                with self.subTest(kind=kind, start=start):
                    self.dropped_as_echo(self.judge(stop_burst(kind, timed("Stop.", start=start)), [p]))
            for start in (p.end + ECHO_WORD + EPS, p.start - ECHO_WORD - 0.3 - EPS):
                with self.subTest(kind=kind, start=start):
                    self.barged(self.judge(stop_burst(kind, timed("Stop.", start=start)), [p]))


if __name__ == "__main__":
    unittest.main()
