"""Cases from the owner's own server.log of 26 Oct: the follow-ups of his that were thrown away must get through, and
Void's own voice heard back must not. Every heard text below is copied from that log as it was logged (the log keeps
the first 80 characters); his lines are copied from history.jsonl, what he had just said when the owner answered.
`void drops` (app/drops.py) reads such a log back: every heard burst, kept or dropped, and what gate.judge does with it now.

    uvx pytest tests/test_log_cases.py -rxX -v

`YOURS` is the regression table: one row per thing the owner said, and one test per row. A row today's hearing gets
wrong is a strict expected failure naming the phase meant to fix it (never a skip): it turns the suite red as soon as a
fix makes it pass, and that phase removes the mark.
"""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import NamedTuple

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
import gate  # noqa: E402
import drops  # noqa: E402

CFG = {"voice_gate": True}

# what he said just before (history.jsonl)
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


# the phases meant to fix what the gate gets wrong today
AFTER_QUIET = "Phase 4: a reply of his after Void went quiet is dropped as echo (HEAR-01)"
AFTER_SPOKE = "Phase 4: a reply right after Void spoke is dropped for no wake word (HEAR-01)"
WHILE_TALKING = "Phase 4: a reply made while Void was still talking is dropped, where it should wait (HEAR-02)"
NO_WAKE = dict(keep=False, why="no wake word", act="drop")    # right by design: outside the follow-up window


class Row(NamedTuple):
    """One thing the owner said, as logged, and the verdict it should get."""
    text: str                     # what was heard (the log keeps the first 80 characters)
    kind: str = "follow"          # "listen" | "wake" | "follow" | "over" | "peek"
    talking: bool = False         # he was talking when it was heard
    recent: tuple = ()            # what he had just said (history.jsonl), oldest first
    keep: bool = True             # the verdict it should get: kept or dropped…
    why: str = "kept"             # …and which of gate.WHY
    act: str = "follow"           # …and what is done with it ("drop" for a drop)
    phase: str = ""               # empty: today's gate gets it right; else "Phase N: …", the phase meant to fix it

    @property
    def rest(self):
        return self.text if self.keep else ""


YOURS = [  # the owner's follow-ups the voiceprint (or the one-word rule) dropped on 26 Oct: all kept as he said them
    Row("Yes, God damn", recent=(HIS_STOPPED,)),
    Row("What? What", recent=(HIS_ARCHITECT,)),
    Row("Why doesn't it have history? There is plenty of fucking history"),
    Row("Keep it moving"),
    Row("Yes, I give my approval"),
    Row("Why the fuck would that need my okay"),
    Row("I've already fucking been perfectly clear"),
    Row("Why is that my call? Why would I recommend what"),
    Row("No, the road map is utterly fucked. The road map cannot stay like it is, but thi"),
    Row("Ah yes, I want you to use a helper to do that"),
    Row("Why the fuck isn't it on the board to begin with"),
    Row("Yes"),                                     # (dropped as a stray word: a one-word answer to his question)
    # the rest of what he said that the gate threw away or got right, 26 Oct to 5 Nov (server.log), judged on what the
    # log holds. The Void lines are written for the test, short, to give the echo check something to overlap
    Row("Yes, do it. Goddamn. Yes, do it"),         # (kept in the log too)
    Row("See what's on my clipboard", "wake", **NO_WAKE),
    Row("In the right direction", "wake", **NO_WAKE),
    Row("Tidy up", "wake", **NO_WAKE),
    Row("God damn it", "wake", **NO_WAKE),
    Row("Changes sound like bullshit that doesn't solve the fucking problem", "wake", **NO_WAKE),
    Row("I'm gonna shut up", "wake", True, **NO_WAKE),
    Row("I'm afraid to stop, fix up the fix. I'm not afraid to stop, fix up the fix. Cont", "wake", True, **NO_WAKE),
    # a reply of his after Void went quiet, dropped as echo
    Row("I don't...", "wake", recent=("Should I leave it? I don't think it matters either way.",), act="request",
        phase=AFTER_QUIET),
    Row("That's retarded!", recent=("The test is failing again. That's what I found.",), phase=AFTER_QUIET),
    Row("Yes, commit it", recent=("Want me to commit it? Say yes and I'll commit it.",), phase=AFTER_QUIET),
    Row("Yes, do it", recent=("Shall I merge it? Say yes, do it, or no.",), phase=AFTER_QUIET),
    Row("Yes, merge it", recent=("Ready to merge? Say yes, merge it, and I will.",), phase=AFTER_QUIET),
    Row("Yes, please put that on my clipboard", recent=("Want me to put that on your clipboard? Say yes, please.",),
        phase=AFTER_QUIET),
    # a reply right after Void spoke, with no wake word: dropped for it
    Row("Fuck it retard", "wake", act="request", phase=AFTER_SPOKE),
    Row("Yes, do it", "wake", act="request", phase=AFTER_SPOKE),
    Row("Go ahead. Yeah, that's fine", "wake", act="request", phase=AFTER_SPOKE),
    Row("Yes, what the fuck? God damn it. I'm getting sick of this shit", "wake", act="request", phase=AFTER_SPOKE),
    Row("Cool, so you're just going to keep fucking up and I have to deal with it. Not ev", "wake", act="request",
        phase=AFTER_SPOKE),
    Row("Yes, give me that prompt. Are you even listening to your little cunt? Yes, do it", "wake", act="request",
        phase=AFTER_SPOKE),
    Row("Cool, good talk. Super useful", "wake", True, act="request", phase=AFTER_SPOKE),
    Row("Jesus Christ you are fucking worthy", "wake", True, act="request", phase=AFTER_SPOKE),
    # a reply made while Void was still talking: dropped as "while talking", where it should wait and be answered
    Row("Yeah, that's fine. Go ahead", "over", phase=WHILE_TALKING),
    Row("It's good", "over", True, phase=WHILE_TALKING),
    Row("Yes, that's fine", "over", True, phase=WHILE_TALKING),
    Row("Yes and yes", "over", phase=WHILE_TALKING),
    Row("Just send the message to the lead itself", "over", phase=WHILE_TALKING),
    Row("Yes, go ahead", "over", phase=WHILE_TALKING),
    Row("So you're gonna keep fucking up", "over", phase=WHILE_TALKING),
    Row("Cool, good talk", "over", phase=WHILE_TALKING),
    Row("How about any fucking where else", "over", phase=WHILE_TALKING),
]


def heard(text, logprob=-0.3, no_speech=0.05):
    """Whisper, sure of what it heard (these follow-ups were past its confidence check when the voiceprint dropped them)."""
    return SimpleNamespace(text=text, logprob=logprob, no_speech=no_speech, seconds=2.0)


def burst(text, kind="follow", talking=False):
    return gate.Burst(text=text, heard=heard(text) if kind == "follow" else None, speech=1.5, seconds=2.5, kind=kind,
                      talking=talking, rang=True)


def row(r):
    """A table row as a test case: one with a phase is a strict expected failure naming it, so a fix that makes it pass
    turns the suite red until that phase removes the mark. Only a wrong verdict counts (`raises`): a crash fails."""
    marks = [pytest.mark.xfail(strict=True, raises=AssertionError, reason=r.phase)] if r.phase else []
    return pytest.param(r, id=f"{r.text} ({r.kind})", marks=marks)


@pytest.mark.parametrize("r", [row(r) for r in YOURS])
def test_the_row_gets_the_verdict_the_owner_expects(r):
    v = gate.judge(burst(r.text, r.kind, r.talking), list(r.recent), CFG)
    assert (v.keep, v.why, v.act, v.rest) == (r.keep, r.why, r.act, r.rest), f"got {v}"


def test_every_row_text_fits_what_the_log_keeps():
    assert [r.text for r in YOURS if len(r.text) > drops.CUT] == []


class YourFollowUps(unittest.TestCase):
    """Each follow-up of yours the voiceprint (or the one-word rule) dropped is sent on, as you said it (the rows of
    `YOURS`, above)."""

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
    """`void drops` lists every verdict in a log, old drops and stamped lines, and what today's gate does with each."""

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
            (18, "2026-10-27 09:16:00", "kept", "follow", "Keep it moving", "kept"),
        ])

    def test_one_day_alone(self):
        self.assertEqual([d[0] for d in self.drops("2026-10-27")], [15, 17, 18])

    def test_the_report_counts_the_bursts_the_drops_and_those_kept_now(self):
        lines = drops.report(drops.replay(LOG.splitlines()))
        self.assertEqual(lines[-1], "     8  heard in all; 7 dropped, 2 of them kept now")
        self.assertIn("KEPT", lines[0])


class Rang(unittest.TestCase):
    """drops.rang: a logged burst was heard with his sound or its ring in the air when its kind is "over" or "peek", or
    its heard line's flags hold "while talking", "after his last word" or "in his echo"."""

    def test_a_burst_heard_over_him_or_peeked_rang(self):
        for kind in ("over", "peek"):
            self.assertTrue(drops.rang("", kind), f"a {kind} burst not taken as heard with his voice in the air")

    def test_flags_that_place_his_voice_in_the_air(self):
        for flags in ("while talking", "follow-up, after his last word (3.2s of him cut)", "follow-up, in his echo"):
            for kind in ("listen", "wake", "follow"):
                self.assertTrue(drops.rang(flags, kind), f"{flags!r} on a {kind} burst not taken as rang")

    def test_a_burst_clear_of_him_did_not_ring(self):
        for flags in ("", "follow-up"):
            for kind in ("listen", "wake", "follow"):
                self.assertFalse(drops.rang(flags, kind), f"{flags!r} on a {kind} burst taken as rang")


ECHO_LOG = """\
[void] 2026-12-02 10:05:30 heard 2.1s, 4 words, follow-up, in his echo
[void] 2026-12-02 10:05:30 echo (follow): I'll start the build
[void] 2026-12-02 10:06:10 heard 2.4s, 5 words, follow-up, after his last word (0.8s of him cut)
[void] 2026-12-02 10:06:10 echo (follow): the board is ready now
[void] 2026-12-02 10:07:00 heard 2.0s, 4 words, while talking
[void] 2026-12-02 10:07:00 echo (over): the board is ready now
[void] 2026-12-02 10:08:20 heard 2.6s, 4 words, follow-up
[void] 2026-12-02 10:08:20 echo (follow): Put it on the board
[void] 2026-12-02 10:09:45 heard 2.2s, 4 words
[void] 2026-12-02 10:09:45 echo (wake): Put it on the board
"""

# (the two lines of the owner's 27 Oct 16:11:24 reply, the stamp moved: a short phrase is all a test file keeps)
YES_DO_IT = """\
[void] 2026-12-02 16:11:24 heard 3.0s, 3 words, follow-up
[void] 2026-12-02 16:11:24 echo (follow): Yes, do it
"""


class EchoReplay(unittest.TestCase):
    """`void drops` replays an echo drop the log shows was heard with his voice in the air as logged (the log does not
    keep his words), and judges every other echo drop again as heard after he went quiet."""

    def drops(self, log):
        return [(d.line, d.at, d.why, d.kind, d.text, d.now) for d in drops.replay(log.splitlines())]

    def test_an_echo_drop_is_judged_again_only_when_the_burst_was_clear_of_him(self):
        self.assertEqual(self.drops(ECHO_LOG), [
            (2, "2026-12-02 10:05:30", "echo", "follow", "I'll start the build", "as logged"),
            (4, "2026-12-02 10:06:10", "echo", "follow", "the board is ready now", "as logged"),
            (6, "2026-12-02 10:07:00", "echo", "over", "the board is ready now", "as logged"),
            (8, "2026-12-02 10:08:20", "echo", "follow", "Put it on the board", "kept"),
            (10, "2026-12-02 10:09:45", "echo", "wake", "Put it on the board", "no wake word"),
        ])

    def test_yes_do_it_is_kept_now(self):
        self.assertEqual(self.drops(YES_DO_IT), [(2, "2026-12-02 16:11:24", "echo", "follow", "Yes, do it", "kept")])


if __name__ == "__main__":
    unittest.main()
