"""Cases from the owner's own server.log of 26 Oct: the follow-ups of his that were thrown away must get through, and
Void's own voice heard back must not. Every heard text below is copied from that log as it was logged (the log keeps
the first 80 characters); his lines are copied from history.jsonl, what he had just said when the owner answered.
`void drops` (app/drops.py) reads such a log back: every drop, and what gate.judge does with it now.

    python3 -m unittest tests.test_log_cases -v
"""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
import gate  # noqa: E402
import drops  # noqa: E402

CFG = {"voice_gate": True}

# what he said just before (history.jsonl), and the owner's follow-ups the voiceprint dropped (with the score it gave)
HIS_ARCHITECT = ("The architect finished the design, and it really is one rebuilt board rather than fifteen bolted-on "
                 "features. It stopped with two choices that are genuinely yours, so here's the first. The new usage "
                 "tracking needs a status line in every Claude Code session. Should it show one short line in your "
                 "terminal, like context 41 percent, five-hour 62 percent, seven-day 80 percent, or stay hidden so the "
                 "numbers only appear on the board?")
HIS_STOPPED = ("You're right, I shouldn't have started it. I've stopped it: the design and your two answers are saved, "
               "but nothing is building. Want to fix Foreman's token leaks first, then build the work board?")
HIS_STEP_ONE = ("Step one is measuring, so we fix the real leaks and not guesses. I've sent an Opus helper through the g7 "
                "build's logs to add up where every token went and rank the leaks, biggest first.")
HIS_PROMPT = ("No, I'm not fixing it myself. I only read today's voice log so the prompt would have real evidence in it, "
              "not the same generic instructions again. The new prompt is on your clipboard.")

YOURS = [  # (what was heard, the voice score that dropped it, what he had just said)
    ("Yes, God damn", 0.43, HIS_STOPPED),
    ("What? What", 0.34, HIS_ARCHITECT),
    ("Why doesn't it have history? There is plenty of fucking history", 0.02, ""),
    ("Keep it moving", None, ""),
    ("Yes, I give my approval", None, ""),
    ("Why the fuck would that need my okay", None, ""),
    ("I've already fucking been perfectly clear", 0.11, ""),
    ("Why is that my call? Why would I recommend what", 0.06, ""),
    ("No, the road map is utterly fucked. The road map cannot stay like it is, but thi", 0.06, ""),
    ("Ah yes, I want you to use a helper to do that", None, ""),
    ("Why the fuck isn't it on the board to begin with", None, ""),
    ("Yes", None, ""),                                   # (dropped as a stray word: a one-word answer to his question)
]


def heard(text, logprob=-0.3, no_speech=0.05):
    """Whisper, sure of what it heard (these follow-ups were past its confidence check when the voiceprint dropped them)."""
    return SimpleNamespace(text=text, logprob=logprob, no_speech=no_speech, seconds=2.0)


def burst(text, kind="follow", talking=False):
    return gate.Burst(text=text, heard=heard(text) if kind == "follow" else None, speech=1.5, seconds=2.5, kind=kind,
                      talking=talking)


class YourFollowUps(unittest.TestCase):
    """Each follow-up of yours the voiceprint (or the one-word rule) dropped is sent on, as you said it."""

    def test_every_follow_up_of_yours_from_the_log_is_kept(self):
        for text, score, his in YOURS:
            with self.subTest(text, score=score):
                v = gate.judge(burst(text), [his] if his else [], CFG)
                self.assertEqual((v.keep, v.act, v.rest), (True, "follow", text), f"dropped as {v.why!r}")

    def test_no_check_judges_whose_voice_it_is(self):
        self.assertNotIn("not your voice", gate.WHY)
        self.assertNotIn("voice", gate.Burst.__dataclass_fields__)


class HisEcho(unittest.TestCase):
    """His own voice heard back is not sent on as yours, even inside the follow-up window."""

    def test_his_lines_heard_back_are_dropped_as_echo(self):
        for text, his in (("The architect finished the design, and it really is one rebuilt board rather tha",
                           HIS_ARCHITECT),
                          ("The prompt would have real evidence in it, not the same.", HIS_PROMPT)):
            for kind in ("follow", "wake", "over"):
                with self.subTest(text, kind=kind):
                    v = gate.judge(burst(text, kind), [his], CFG)
                    self.assertEqual((v.keep, v.why), (False, "echo"))

    def test_his_garbled_voice_without_hey_void_is_dropped(self):
        # ("Step one is measuring…" as Whisper heard it back, outside the follow-up window)
        v = gate.judge(burst("Staff 1 is measuring it, so we fix the real need by knock-dasses. Unspent an ope", "wake"),
                       [HIS_STEP_ONE], CFG)
        self.assertFalse(v.keep, "his own voice was taken as a request")

    def test_what_whisper_makes_up_over_his_voice_is_dropped(self):
        for text in ("See you in the next video", "I hope you enjoyed this video", "Okay, time to go"):
            with self.subTest(text):
                v = gate.judge(burst(text, "over", talking=True), [], CFG)
                self.assertEqual((v.keep, v.why), (False, "while talking"))


LOG = """\
[void] heard 4.6s, 2 words, follow-up, after his last word (3.2s of him cut)
[void] dropped follow-up, not your voice (voice 0.34): What? What
[void] heard 3.3s, 3 words, follow-up
[void] follow-up request (voice 0.70): Don't expand the fucking spec
[void] heard 2.0s, 1 words, follow-up
[void] ignored stray word: Yes
[void] heard 1.6s, 3 words, while talking
[void] ignored while talking: Oh my god
[void] heard 3.2s, 3 words
[void] ignored: no "hey Void": What happened
[void] heard 12.0s, 35 words, while talking
[void] dropped echo of own speech: The architect finished the design, and it really is one rebuilt board rather tha
[void] voiceprint enrolling 1.2s of your speech: Yes, God damn!
[void] 2026-10-27 09:15:02 heard 2.9s, 3 words, follow-up
[void] 2026-10-27 09:15:02 low confidence (follow): I need my first single
[void] 2026-10-27 09:15:40 heard 2.0s, 2 words
[void] 2026-10-27 09:15:41 no wake word (wake): God damn it
[void] 2026-10-27 09:16:00 kept (follow): Keep it moving
"""


class Replay(unittest.TestCase):
    """`void drops` lists every drop in a log, old lines and stamped ones, and what today's gate does with each."""

    def drops(self, day=None):
        return [(d.line, d.at, d.why, d.kind, d.text, d.now) for d in drops.replay(LOG.splitlines(), day)]

    def test_every_drop_is_listed_with_what_the_gate_does_now(self):
        self.assertEqual(self.drops(), [
            (2, "", "not your voice", "follow", "What? What", "kept"),
            (6, "", "stray word", "follow", "Yes", "kept"),
            (8, "", "while talking", "over", "Oh my god", "while talking"),
            (10, "", "no wake word", "wake", "What happened", "no wake word"),
            (12, "", "echo", "over", "The architect finished the design, and it really is one rebuilt board rather tha",
             "as logged"),
            (15, "2026-10-27 09:15:02", "low confidence", "follow", "I need my first single", "as logged"),
            (17, "2026-10-27 09:15:41", "no wake word", "wake", "God damn it", "no wake word"),
        ])

    def test_one_day_alone(self):
        self.assertEqual([d[0] for d in self.drops("2026-10-27")], [15, 17])

    def test_the_report_counts_the_drops_and_those_kept_now(self):
        lines = drops.report(drops.replay(LOG.splitlines()))
        self.assertEqual(lines[-1].split(), ["7", "dropped", "in", "all;", "2", "of", "them", "kept", "now"])
        self.assertIn("KEPT", lines[0])


if __name__ == "__main__":
    unittest.main()
