"""Void must not hear his own voice as yours: any transcript that mostly repeats what he said in the last minute is
dropped. While he talks (and in his echo just after) only "stop" / "hey Void" and the like cut him off: anything else
the mic catches then is taken for his own voice, however garbled, and dropped. Push-to-talk still works.

    python3 -m unittest discover -s tests
"""
import contextlib
import inspect
import io
import re
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import suite_data  # noqa: E402  (Void's data folder: the suite's own, set before server.py settles it)
import fakes  # noqa: E402
from test_hearing import SPK_RATE, FakePlayer, FakeRef  # noqa: E402  (the Speaker player stand-ins)

try:
    import server
except Exception as e:  # noqa: BLE001
    server, IMPORT_ERR = None, e
else:
    IMPORT_ERR = None

try:
    import gate
except Exception as e:  # noqa: BLE001
    gate, GATE_ERR = None, e
else:
    GATE_ERR = None

REPLY = "Sure, I moved the meeting to Thursday at three and told Sam about it."
PCM = bytes(32000)


@unittest.skipIf(server is None, f"server.py doesn't import here: {IMPORT_ERR}")
class Echo(unittest.TestCase):
    def setUp(self):
        W = server.Wake
        self._saved = {k: W.__dict__[k] for k in ("talked",)}
        self.addCleanup(self._restore)
        W.talked = []
        server.SPOKEN.clear()
        self.addCleanup(server.SPOKEN.clear)
        self.pub = mock.Mock()
        self.text = ""
        ears = fakes.ears(server, lambda pcm: self.text, lambda pcm: 2.0)
        self.addCleanup(ears.close)
        for p in (mock.patch.object(server.MicAuto, "learn", lambda pcm: None),
                  mock.patch.object(server.BUS, "pub", self.pub),
                  mock.patch.object(server.Speaker, "idle", classmethod(lambda cls: True))):
            p.start()
            self.addCleanup(p.stop)

    def _restore(self):
        for k, v in self._saved.items():
            setattr(server.Wake, k, v)

    def burst(self, text, started=None, ended=None):
        self.text = text
        server.Wake.check(PCM, time.monotonic() if started is None else started, ended=ended)
        return [c.kwargs for c in self.pub.call_args_list if c.kwargs.get("t") != "voice"]   # (voice: the record's copies)

    def after_speech(self, ago):             # he finished talking `ago` seconds ago, follow window open
        now = time.monotonic()
        server.Wake.talked = [[now - ago - 3, now - ago, now + 30]]

    def last_word(self):                     # when he stopped talking
        return server.Wake.talked[-1][1]

    # the echo match: what is heard against what he said lately (server.py keeps SPOKEN and expires it)
    def test_match_expires(self):
        server.SPOKEN.append((time.monotonic() - 120, REPLY))
        self.after_speech(server.ECHO_TAIL + 0.6)
        self.assertFollowUp(self.burst("I moved the meeting to Thursday at three"),
                            "I moved the meeting to Thursday at three")

    # anything said after he has gone quiet gets through: past his ring, words lining up with his are not his echo
    # (docs/superpowers/specs/quiet-replies-design.md:23, :27: 0.6 s past the ring, these change to kept)
    def test_badly_misheard_echo_heard_after_the_ring_is_a_follow_up(self):
        server.note_spoken("Kill 'Em All really belongs in the 30K rolloff folder.")
        server.note_spoken("The other two albums are already sorted, but you might want to check that.")
        got = []
        for heard in ("I can kill them all really long in a 30K bonus folder", "But you might want to check me."):
            self.pub.reset_mock()
            self.after_speech(server.ECHO_TAIL + 0.6)
            got.append((heard, [(e.get("t"), str(e.get("text")).strip(" .,!?"), e.get("follow"))
                                for e in self.burst(heard)]))
        self.assertEqual(got, [(heard, [("wake", heard.strip(" .,!?"), True)]) for heard in
                               ("I can kill them all really long in a 30K bonus folder", "But you might want to check me.")],
                         "(heard, the (event, text sent on, follow-up) it was sent on as): kept whole, not dropped as echo")

    def test_request_sharing_his_words_gets_through(self):
        server.note_spoken("Kill 'Em All really belongs in the 30K rolloff folder.")
        server.note_spoken("The other two albums are already sorted, but you might want to check that.")
        self.after_speech(server.ECHO_TAIL + 0.6)
        self.assertFollowUp(self.burst("please move Reload to the 30K folder too"),
                            "please move Reload to the 30K folder too")

    def test_his_said_words_heard_after_the_ring_are_a_follow_up(self):
        with mock.patch.object(server.Speaker, "_start", classmethod(lambda cls: None)):
            server.Speaker.say(REPLY, 1)
        self.addCleanup(server.Speaker.todo.clear)
        self.after_speech(server.ECHO_TAIL + 0.6)
        self.assertFollowUp(self.burst("I moved the meeting to Thursday at three"),
                            "I moved the meeting to Thursday at three")
        # (what Speaker.say noted, heard back in the ring after his last sound, is still his echo)
        air, ev, log = self.aired((1000.0, 1003.0), 1003.2, 1005.1, 1005.5, "I moved the meeting to Thursday at three")
        self.assertEqual((air, [e.get("t") for e in ev], any(" echo (follow): " in ln for ln in log)),
                         ((False, True), ["gate_drop"], True),
                         "(talking, rang) over the burst, events, logged as an echo drop")

    # the time gate: his spans hold his sound only, and the ring is not talking
    def test_span_at_is_the_span_of_his_sound_without_the_ring(self):
        now = time.monotonic()
        with mock.patch.dict(server.CFG, {"follow_up": 30}):
            server.Wake.talking(now - 3, now)
        span = server.Wake.span_at(now - 0.1)
        self.assertIsNotNone(span, "no span while his sound is coming out")
        self.assertAlmostEqual(span[0], now - 3, delta=1e-6)
        self.assertAlmostEqual(span[1], now, delta=1e-6)
        outside = (now - 3.05, now + 0.05, now + server.ECHO_TAIL - 0.05, now + server.ECHO_TAIL + 0.5)
        self.assertEqual([server.Wake.span_at(t) is None for t in outside], [True] * len(outside),
                         "a span found before his sound or after it, in the ring")

    def test_follow_window_opens_at_the_end_of_his_sound_and_closes_at_until(self):
        now = time.monotonic()
        until = now + server.ECHO_TAIL + 30                 # end + ECHO_TAIL + follow_up
        with mock.patch.dict(server.CFG, {"follow_up": 30}):
            server.Wake.talking(now - 1, now)
            at = (now - 0.5, now + 0.05, now + server.ECHO_TAIL, until - 0.05, until + 0.05)
            self.assertEqual([server.Wake.window_at(t) for t in at], [False, True, True, True, False],
                             "the window: shut while he sounds, open from his last sound to `until`, shut after")

    def assertFollowUp(self, ev, text="please add milk to the shopping list"):
        self.assertEqual([(e.get("t"), e.get("text"), e.get("follow")) for e in ev], [("wake", text, True)])

    def assertDropped(self, ev, msg=None):          # a dropped follow-up: shown on the page, never a request or a barge
        self.assertEqual([e.get("t") for e in ev], ["gate_drop"], msg)

    def test_words_in_tail_dropped(self):          # still his echo ringing: not a request
        self.after_speech(0.3)
        self.assertEqual(self.burst("please add milk to the shopping list", time.monotonic() - 0.5), [])

    def test_echo_in_tail_dropped(self):
        self.after_speech(0.3)
        server.note_spoken(REPLY)
        self.assertEqual(self.burst("I moved the meeting to Thursday at three", time.monotonic() - 0.5), [])

    def test_stray_word_in_tail_ignored(self):
        self.after_speech(0.3)
        self.assertEqual(self.burst("um", time.monotonic() - 0.5), [])

    # what the log showed swallowing your reply: "heard 9.9s, 26 words" -> "ignored while talking"
    ANSWER = ("no leave the remaster where it is and move Reload into the 30K folder next to Kill Em All then tell me "
              "when the copy to the card has finished")

    def test_answer_begun_as_he_finished_is_a_follow_up(self):
        server.note_spoken(REPLY)
        self.after_speech(10)                    # you started in his last second and talked on 10 s after he stopped
        ev = self.burst(self.ANSWER, self.last_word() - 0.5)
        self.assertFollowUp(ev, self.ANSWER)

    def test_echo_running_on_after_he_finished_dropped(self):
        server.note_spoken(REPLY)
        self.after_speech(10)
        self.assertDropped(self.burst("Sure I moved the meeting to Thursday at three and told Sam about it",
                                      self.last_word() - 0.5))

    def test_words_ending_in_tail_dropped(self):     # began as he finished, over by the time the room stopped ringing
        self.after_speech(10)
        su = self.last_word()
        self.assertEqual(self.burst("I can kill them all really long in a 30K bonus folder", su - 0.5,
                                    su + server.ECHO_TAIL), [])

    def test_answer_begun_as_he_finished_needs_follow_ups_on(self):
        self.after_speech(10)
        s, e, _ = server.Wake.talked[-1]
        server.Wake.talked = [[s, e, e + server.ECHO_TAIL]]          # (follow-ups off: no window after him)
        self.assertEqual(self.burst(self.ANSWER, self.last_word() - 0.5), [])

    def test_follow_up_after_tail_accepted(self):
        self.after_speech(server.ECHO_TAIL + 0.6)
        ev = self.burst("please add milk to the shopping list")
        self.assertEqual([e.get("t") for e in ev], ["wake"])
        self.assertTrue(ev[0]["follow"])

    def test_follow_up_while_claude_works_heard(self):      # the page holds it until his reply is done
        self.after_speech(server.ECHO_TAIL + 0.6)
        self.assertTrue(server.ST.lock.acquire(blocking=False))
        self.addCleanup(server.ST.lock.release)
        self.assertTrue(server.Wake.window_open())
        self.assertFollowUp(self.burst("please add milk to the shopping list"))

    def test_follow_up_repeating_his_reply_after_the_ring_is_kept(self):
        self.after_speech(server.ECHO_TAIL + 0.6)
        server.note_spoken(REPLY)
        self.assertFollowUp(self.burst("I moved the meeting to Thursday at three"),
                            "I moved the meeting to Thursday at three")

    def test_wake_word_burst_repeating_his_words_with_no_sound_of_his_is_kept(self):
        server.note_spoken("Okay. Hey Void, you can ask me anything about the calendar this week.")
        ev = self.burst("Hey Void, you can ask me anything about the calendar")
        self.assertEqual([e.get("t") for e in ev], ["wake"])

    def test_wake_word_still_works(self):
        ev = self.burst("Hey Void, what is the weather like")
        self.assertEqual([e.get("t") for e in ev], ["wake"])

    # a burst is judged by when it was heard, not by whether he talks when Whisper is done with it
    def clocked(self, at=1000.0):
        clock = [at]
        p = mock.patch.object(server, "time", mock.Mock(monotonic=lambda: clock[0], time=time.time))
        p.start()
        self.addCleanup(p.stop)
        return clock

    def judged(self):
        calls = []
        p = mock.patch.object(server.gate, "judge", side_effect=lambda b, *a: calls.append(b) or self.real_judge(b, *a))
        self.real_judge = server.gate.judge
        p.start()
        self.addCleanup(p.stop)
        return calls

    def test_burst_over_him_cut_off_before_judged_is_still_over_him(self):
        clock = self.clocked()
        server.Wake.talking_until(1010.0)              # he talks from 1000 s to 1010 s…
        clock[0] = 1006.0
        server.Wake.hush()                             # …and is stopped at 1006 s, while the burst is being judged
        clock[0] = 1006.5
        calls = self.judged()
        self.burst("I can kill them all really long in a 30K bonus folder", 1002.0, 1005.5)
        self.assertEqual([(b.kind, b.talking) for b in calls], [("over", True)],
                         "a burst heard while he talked was judged as if he had been quiet")

    def test_reply_in_window_judged_while_his_next_sentence_plays_is_a_follow_up(self):
        clock = self.clocked()
        with mock.patch.dict(server.CFG, {"follow_up": 30}):
            server.Wake.talking_until(1000.5)          # his sentence ends; the window opens once his echo has gone
            clock[0] = 1004.1
            server.Wake.talking_until(1008.0)          # his next sentence starts after you stopped, before you're judged
            clock[0] = 1004.5
            self.assertFollowUp(self.burst("please add milk to the shopping list", 1002.0, 1004.0))

    def test_check_classifies_a_burst_by_when_it_began(self):
        T = server.ECHO_TAIL
        cases = (  # (kind, his sound from/to, burst began/ended, judged at)
            ("over", (1000.0, 1010.0), (1002.0, 1005.0), 1011.0),              # began while he made sound
            ("follow", (1000.0, 1003.0), (1003.2, 1005.1), 1005.5),            # began in the ring after his sound
            ("follow", (1000.0, 1003.0), (1003.0 + T + 0.5, 1005.4 + T), 1005.8 + T),   # began after the ring
            ("follow", (1000.0, 1003.0), (1002.5, 1013.0), 1013.3),            # began in his last words and ran on
            ("wake", (1000.0, 1003.0), (1003.0 + T + 32, 1004.9 + T + 32), 1005.3 + T + 32),  # window shut by then
        )
        clock = self.clocked()
        calls = self.judged()
        got = []
        with mock.patch.dict(server.CFG, {"follow_up": 30}):
            for _, (s, e), (began, ended), judged_at in cases:
                server.Wake.talked = []
                clock[0] = s
                server.Wake.talking(s, e)
                clock[0] = judged_at
                calls.clear()
                self.burst("please add milk to the shopping list", began, ended)
                got.append([b.kind for b in calls])
        self.assertEqual(got, [[kind] for kind, *_ in cases])

    # echo is only his voice heard while he makes sound, or in the room's ring after it (gate.ECHO_TAIL)
    def aired(self, his, began, ended, judged_at, text):
        """His sound over `his` (from, to), then a burst heard as `text` from `began` to `ended`, judged at `judged_at`.
        The lines he was noted saying are re-stamped to `his[0]`: they were noted on the real clock, which on a freshly
        booted host reads far below this scene's clock, so `said_lately` would forget them as older than ECHO_KEEP.
        → (Wake.air over the burst, bus events, '[void]' log lines)."""
        clock = self.clocked()
        server.Wake.talked = []
        self.pub.reset_mock()
        said = [line for _t, line in server.SPOKEN]
        server.SPOKEN.clear()
        server.SPOKEN.extend((his[0], line) for line in said)
        with mock.patch.dict(server.CFG, {"follow_up": 30}):
            clock[0] = his[0]
            server.Wake.talking(*his)
            clock[0] = judged_at
            air = server.Wake.air(began, ended)
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                ev = self.burst(text, began, ended)
        return tuple(air), ev, [ln for ln in err.getvalue().splitlines() if ln.startswith("[void]")]

    def test_real_echo_begun_while_he_made_sound_is_still_dropped_as_echo(self):
        server.note_spoken(REPLY)
        for line in ALBUMS:
            server.note_spoken(line)
        cases = (  # (kind, his sound, burst began/ended, judged at, heard)
            ("over", (1000.0, 1010.0), (1002.0, 1005.0), 1005.5, "I moved the meeting to Thursday at three"),
            ("over", (1000.0, 1010.0), (1004.0, 1007.0), 1007.4, "I can kill them all really long in a 30K bonus folder"),
            ("follow", (1000.0, 1003.0), (1002.5, 1013.0), 1013.3,
             "Sure I moved the meeting to Thursday at three and told Sam about it"),
        )
        got = []
        for kind, his, (began, ended), judged_at, heard in cases:
            air, ev, log = self.aired(his, began, ended, judged_at, heard)
            got.append((heard, air, [e.get("t") for e in ev if e.get("t") != "gate_drop"],
                        any(f" echo ({kind}): " in ln for ln in log)))
        self.assertEqual(got, [(heard, (True, True), [], True) for *_, heard in cases],
                         "(heard, (talking, rang) over the burst, events other than a drop, logged as an echo drop)")

    def test_his_own_words_heard_in_the_ring_after_his_last_sound_are_dropped_as_echo(self):
        T = server.ECHO_TAIL
        server.note_spoken(REPLY)
        for line in ALBUMS:
            server.note_spoken(line)
        cases = (  # (burst began/ended, judged at, heard): begun after his sound stopped, while the room still rang
            ((1003.2, 1005.1), 1005.5, "I moved the meeting to Thursday at three"),
            ((1003.1, 1003.0 + T - 0.1), 1003.0 + T + 0.3, "I can kill them all really long in a 30K bonus folder"),
        )
        got = []
        for (began, ended), judged_at, heard in cases:
            air, ev, log = self.aired((1000.0, 1003.0), began, ended, judged_at, heard)
            got.append((heard, air, [e.get("t") for e in ev], any(" echo (follow): " in ln for ln in log)))
        self.assertEqual(got, [(heard, (False, True), ["gate_drop"], True) for *_, heard in cases],
                         "(heard, (talking, rang) over the burst, events, logged as an echo drop)")

    def stamped_clock(self, at=1000.0):
        """The clock as `clocked` sets it, with the rest of `time` real, so log lines keep their date stamps."""
        clock = [at]
        p = mock.patch.object(server, "time", mock.Mock(wraps=time, monotonic=lambda: clock[0]))
        p.start()
        self.addCleanup(p.stop)
        return clock

    # the 27 Oct follow-up: "Anything I say after you go quiet gets through."
    YES = "Yes, do it"

    def yes_do_it(self):
        """Void has said a line holding "yes, do it" and finished speaking more than ECHO_TAIL ago, follow-ups on;
        then a 3.0 s burst heard as "Yes, do it". → (bus events, '[void]' log lines with their stamps cut off)."""
        T = server.ECHO_TAIL
        server.note_spoken("Both albums can go in the 30K folder. If that sounds right, say yes, do it.")
        clock = self.stamped_clock()
        self.pub.reset_mock()
        began = 1003.0 + T + 0.5
        err = io.StringIO()
        with mock.patch.dict(server.CFG, {"follow_up": 30}), \
                fakes.ears(server, lambda pcm: self.YES), contextlib.redirect_stderr(err):
            clock[0] = 1000.0
            server.Wake.talking(1000.0, 1003.0)
            clock[0] = began + 3.0 + 0.4
            server.Wake.check(bytes(int(server.RATE * 2 * 3.0)), began, ended=began + 3.0)
        stamp = re.compile(r"^\[void\] \d{4}-\d\d-\d\d \d\d:\d\d:\d\d ")
        log = [stamp.sub("", ln) for ln in err.getvalue().splitlines() if stamp.match(ln)]
        return [c.kwargs for c in self.pub.call_args_list if c.kwargs.get("t") != "voice"], log

    def test_yes_do_it_said_after_he_went_quiet_is_sent_on_as_a_follow_up(self):
        ev, _ = self.yes_do_it()
        self.assertFollowUp(ev, self.YES)

    def test_yes_do_it_after_he_went_quiet_is_heard_as_a_follow_up_and_kept_not_dropped_as_echo(self):
        _, log = self.yes_do_it()
        self.assertEqual(([ln for ln in log if ln.startswith("heard ")],
                          [ln for ln in log if ln.endswith(f": {self.YES}")]),
                         (["heard 3.0s, 3 words, follow-up"], [f"kept (follow): {self.YES}"]),
                         "(the heard line, the verdict line) of the 27 Oct follow-up")

    # Wake.air: the one timing of a burst, (his sound at some moment of it, his sound or its ring at some moment of it)
    def test_air_says_whether_his_sound_and_its_ring_were_in_the_air_over_a_burst(self):
        T = server.ECHO_TAIL
        cases = (  # (burst began/ended, (talking, rang)) against his sound from 1000 s to 1003 s
            ((1002.0, 1005.0), (True, True)),                   # begun while he made sound
            ((995.0, 1001.0), (True, True)),                    # begun before him, heard into his sound
            ((1003.2, 1005.1), (False, True)),                  # begun in the ring after his sound
            ((1003.0 + T + 0.5, 1006.0 + T), (False, False)),   # begun after the ring
            ((990.0, 999.0), (False, False)),                   # over before he made a sound
        )
        clock = self.clocked()
        with mock.patch.dict(server.CFG, {"follow_up": 30}):
            clock[0] = 1000.0
            server.Wake.talking(1000.0, 1003.0)
            clock[0] = 1010.0 + T
            got = [tuple(server.Wake.air(began, ended)) for (began, ended), _ in cases]
        self.assertEqual(got, [want for _, want in cases], "(talking, rang) per burst")

    def test_check_takes_talking_and_rang_from_air_over_the_burst_as_it_began(self):
        clock = self.clocked()
        calls = self.judged()
        got = []
        for aired in ((False, True), (False, False), (True, True)):
            timed = []
            with mock.patch.dict(server.CFG, {"follow_up": 30}), \
                    mock.patch.object(server.Wake, "air",
                                      classmethod(lambda cls, s, e, r=aired: timed.append((s, e)) or r)):
                server.Wake.talked = []
                clock[0] = 1000.0
                server.Wake.talking(1000.0, 1003.0)
                clock[0] = 1013.3
                calls.clear()
                self.burst("please add milk to the shopping list", 1002.5, 1013.0)   # begun in his last words, ran on
            got.append((sorted(set(timed)), [(b.talking, b.rang) for b in calls]))   # (every call over the burst)
        self.assertEqual(got, [([(1002.5, 1013.0)], [aired]) for aired in ((False, True), (False, False), (True, True))],
                         "(Wake.air's calls over the burst, the (talking, rang) the burst was judged with)")

    # the heard line says when a burst rang without overlapping his sound
    def test_heard_line_says_in_his_echo_only_when_the_burst_rang_without_his_sound(self):
        T = server.ECHO_TAIL
        cases = (  # (his sound, burst began/ended, judged at, (", in his echo", ", while talking") on the heard line)
            ((1000.0, 1003.0), (1003.2, 1005.1), 1005.5, (True, False)),                  # in the ring
            ((1000.0, 1010.0), (1002.0, 1005.0), 1005.5, (False, True)),                  # over his sound
            ((1000.0, 1003.0), (1003.0 + T + 0.5, 1005.4 + T), 1005.8 + T, (False, False)),  # after the ring
        )
        clock = self.stamped_clock()
        stamp = re.compile(r"^\[void\] \d{4}-\d\d-\d\d \d\d:\d\d:\d\d heard ")
        got = []
        for his, (began, ended), judged_at, _ in cases:
            server.Wake.talked = []
            err = io.StringIO()
            with mock.patch.dict(server.CFG, {"follow_up": 30}), contextlib.redirect_stderr(err):
                clock[0] = his[0]
                server.Wake.talking(*his)
                clock[0] = judged_at
                self.burst("please add milk to the shopping list", began, ended)
            heard = [ln for ln in err.getvalue().splitlines() if stamp.match(ln)]
            got.append([(", in his echo" in ln, ", while talking" in ln) for ln in heard])
        self.assertEqual(got, [[flags] for *_, flags in cases],
                         "(', in his echo', ', while talking') on each burst's heard line")

    # barge-in
    def test_barge_in_while_talking(self):
        server.Wake.talking_until(time.monotonic() + 5)
        ev = self.burst("stop")
        self.assertEqual([e.get("t") for e in ev], ["barge"])

    def test_wake_word_barge_in_while_talking(self):
        server.Wake.talking_until(time.monotonic() + 5)
        ev = self.burst("Hey Void, never mind that")
        self.assertEqual([e.get("t") for e in ev], ["barge"])

    def test_barge_in_echo_dropped(self):
        server.note_spoken("Hey Void, you can ask me anything about the calendar this week.")
        server.Wake.talking_until(time.monotonic() + 5)
        self.assertEqual(self.burst("Hey Void, you can ask me anything about the calendar"), [])

    def test_stop_said_with_his_name_while_talking(self):
        server.Wake.talking_until(time.monotonic() + 5)
        self.assertEqual([e.get("t") for e in self.burst("Void, stop")], ["barge"])
        self.assertFalse(server.Wake.speaking())          # hushed

    def test_stop_inside_longer_burst_while_talking(self):
        server.Wake.talking_until(time.monotonic() + 5)
        self.assertEqual([e.get("t") for e in self.burst("okay okay hold on a second")], ["barge"])

    # mid-burst: a burst begun over him is peeked at while it's still going (Wake.stop_in), then heard out (Wake.check)
    def test_owner_stop_over_him_stops_him_mid_burst(self):
        for said in ("Stop", "Shut up", "Hold on"):
            with self.subTest(said=said):
                self.pub.reset_mock()
                server.Wake.talking_until(time.monotonic() + 5)
                self.text = said
                self.assertTrue(server.Wake.stop_in(PCM, time.monotonic()), f"{said!r} over him didn't stop him mid-burst")
                self.assertEqual([c.kwargs.get("t") for c in self.pub.call_args_list if c.kwargs.get("t") != "voice"], ["barge"])
                self.assertFalse(server.Wake.speaking())          # hushed

    def test_stop_word_buried_in_his_own_speech_heard_over_him_never_stops_him(self):
        # the live log: "barge-in mid-burst: you told him to stop: It goes to the time to realize that it's ready to
        # have a stop on, and it's going" (his own voice heard back over him; the owner said no stop)
        heard = "It goes to the time to realize that it's ready to have a stop on, and it's going."
        server.Wake.talking_until(time.monotonic() + 5)
        started = time.monotonic()
        self.text = heard
        self.assertFalse(server.Wake.stop_in(PCM, started), "stopped mid-burst by a stop word inside his own speech")
        self.assertEqual(self.burst(heard, started), [])
        self.assertTrue(server.Wake.speaking())   # still talking

    def test_stop_begun_while_talking_stops_him_after_his_sentence_ends(self):
        # what the owner's log showed: "stop" over and over for 12 s, heard once his sentence had finished playing
        now = time.monotonic()
        server.Wake.talking(now - 13, now - 1)
        ev = self.burst("Stop, stop, stop, stop stop, stop Void stop, Void stop, Void, shut the", started=now - 12)
        self.assertEqual([e.get("t") for e in ev], ["barge"])

    def test_stop_while_talking_stops_native_voice(self):
        server.Wake.talking_until(time.monotonic() + 5)
        stop = mock.Mock()
        with mock.patch.object(server.Speaker, "idle", classmethod(lambda cls: False)), \
                mock.patch.object(server.Speaker, "stop", stop):
            self.assertEqual([e.get("t") for e in self.burst("shut up")], ["barge"])
        stop.assert_called_once()

    def test_words_while_talking_never_barge_in(self):
        server.Wake.talking_until(time.monotonic() + 5)
        stop = mock.Mock()
        with mock.patch.object(server.Speaker, "stop", stop):
            self.assertEqual(self.burst("please add milk to the shopping list"), [])
        stop.assert_not_called()
        self.assertTrue(server.Wake.speaking())   # still talking

    # what the log showed cutting him off: his own sentences, too garbled for the echo match
    def test_garbled_echo_while_talking_no_barge_in(self):
        server.note_spoken("Kill 'Em All really belongs in the 30K rolloff folder.")
        server.Wake.talking_until(time.monotonic() + 5)
        self.assertEqual(self.burst("I can kill them all really long in a 30K bonus folder"), [])
        self.assertTrue(server.Wake.speaking())

    def test_garbled_tail_of_his_sentence_no_barge_in(self):   # "heard 7.0s, 22 words, while talking"
        server.note_spoken("The other two albums are already sorted, and the remaster sits next to the original "
                           "pressing so you can compare them side by side whenever you like.")
        server.Wake.talking_until(time.monotonic() + 5)
        tail = ("sorted in the remaster since next to the regional pressing so you can compare them, "
                "side by side when ever you like")
        self.assertEqual(len(tail.split()), 22)
        self.assertEqual(self.burst(tail), [])
        self.assertEqual(self.burst("But you might want to check me."), [])
        self.assertTrue(server.Wake.speaking())

    def test_echo_while_talking_dropped(self):
        server.note_spoken(REPLY)
        server.Wake.talking_until(time.monotonic() + 5)
        self.assertEqual(self.burst("I moved the meeting to Thursday at three"), [])

    def test_noise_while_talking_ignored(self):
        server.Wake.talking_until(time.monotonic() + 5)
        self.assertEqual(self.burst("thank you for watching"), [])
        self.assertEqual(self.burst("okay"), [])

    # "void is still dropping my responses": a short phrase you say over and over is you, answering him; only the
    # sentence Whisper makes up and repeats on room sound (and nothing at all) is noise in the follow-up window
    def test_your_repeated_phrase_reaches_void_and_whispers_repeat_is_noise(self):
        for said in ("Not yet, not yet", "Wait, wait, wait, wait, wait, wait"):
            self.pub.reset_mock()
            self.after_speech(server.ECHO_TAIL + 0.6)
            self.assertFollowUp(self.burst(said), said)
        for junk in ("The two of them were the two of them. The two of them were the two of them",
                     "It is a pleasure to be here. It is a pleasure to be here", "", "   "):
            self.pub.reset_mock()
            self.after_speech(server.ECHO_TAIL + 0.6)
            self.assertDropped(self.burst(junk), junk)

    def test_mic_gain_learns_only_from_your_requests(self):
        learn = mock.Mock()
        with mock.patch.object(server.MicAuto, "learn", learn):
            self.after_speech(server.ECHO_TAIL + 0.6)
            self.burst("")                                   # "heard 2.0s, 0 words"
            self.burst("It is a pleasure to be here. It is a pleasure to be here")
            learn.assert_not_called()
            self.pub.reset_mock()
            self.assertFollowUp(self.burst("please add milk to the shopping list"))
            learn.assert_called_once()


@unittest.skipIf(server is None or gate is None, f"server.py or gate.py doesn't import here: {IMPORT_ERR or GATE_ERR}")
class OwnStop(unittest.TestCase):
    """Void's own stop phrase, heard back while it plays or in the room's ring after, never stops him; the owner's stop
    said past ECHO_WORD after his, while he talks, still barges. Whisper's word times are stood in by fakes.ears."""

    TIMER = "Okay, I will stop the timer now."      # "stop" plays 0.7 s to 1.1 s into the line
    TIMER_WORDS = [[0.0, 0.3], [0.3, 0.5], [0.5, 0.7], [0.7, 1.1], [1.1, 1.3], [1.3, 1.8], [1.8, 2.2]]
    WHEN = "Tell me when to stop."                  # "stop" is his last word, 1.0 s to 1.6 s into the line
    WHEN_WORDS = [[0.0, 0.3], [0.3, 0.5], [0.5, 0.8], [0.8, 1.0], [1.0, 1.6]]

    def setUp(self):
        W = server.Wake
        for p in (mock.patch.multiple(W, talked=[], cut=None),
                  mock.patch.object(server, "time", mock.Mock(monotonic=lambda: self.clock[0], time=time.time)),
                  mock.patch.object(server.MicAuto, "learn", lambda pcm: None),
                  mock.patch.object(server.BUS, "pub", mock.Mock()),
                  mock.patch.object(server.Speaker, "idle", classmethod(lambda cls: True)),
                  mock.patch.object(server.Speaker, "stop", mock.Mock())):
            p.start()
            self.addCleanup(p.stop)
        self.clock = [1000.0]
        server.SPOKEN.clear()
        self.addCleanup(server.SPOKEN.clear)
        server.PLAYED.clear()
        self.addCleanup(server.PLAYED.clear)
        self.text, self.timed, self.ats = "", [], []

        def words_for(pcm, at):        # (keeps each `at` the server hands transcribe_pcm_heard)
            self.ats.append(at)
            return tuple(gate.Word(w, at + a, at + b) for w, a, b in self.timed)

        ears = fakes.ears(server, lambda pcm: self.text, words_for=words_for)
        self.addCleanup(ears.close)
        self.verdicts = []              # each (kind, why) as gate.judge hands it back to server.py
        real = server.gate.judge

        def judge(*a, **k):
            v = real(*a, **k)
            self.verdicts.append(((a[0] if a else k["b"]).kind, v.why))
            return v

        p = mock.patch.object(server.gate, "judge", judge)
        p.start()
        self.addCleanup(p.stop)

    def hear(self, text, timed):        # what the mic catches: `text`, its words timed from the clip's first sample
        self.text, self.timed = text, timed

    def events(self):
        return [c.kwargs.get("t") for c in server.BUS.pub.call_args_list if c.kwargs.get("t") != "voice"]   # (not the record's copies)

    def assertNotStopped(self, msg, kinds):
        # gate.judge step 2: his own stop phrase heard back is dropped as "echo", whichever kind it was heard as
        self.assertNotIn("barge", self.events(), msg)
        self.assertNotIn("wake", self.events(), msg)
        server.Speaker.stop.assert_not_called()
        self.assertEqual(self.verdicts[-len(kinds):], [(k, "echo") for k in kinds], f"{msg}: not dropped as echo")

    def test_his_stop_heard_back_while_it_plays_never_stops_him(self):
        server.Wake.talking_until(1005.0)                                # he talks from 1000 s to 1005 s
        server.note_played(self.TIMER, 1000.0, 2.2, self.TIMER_WORDS)   # his "stop" plays 1000.7 s to 1001.1 s
        self.hear("Stop.", [("Stop.", 0.1, 0.4)])                        # heard back 1000.9 s to 1001.2 s
        self.clock[0] = 1001.5
        self.assertFalse(server.Wake.stop_in(PCM, 1000.8, 1000.8), "his own stop, heard as it played, stopped him")
        self.assertNotStopped("his own stop, heard as it played, stopped him mid-burst", ["peek"])
        self.assertTrue(server.Wake.speaking())
        self.clock[0] = 1001.9
        server.Wake.check(PCM, 1000.8, ended=1001.8, at=1000.8)
        self.assertNotStopped("his own stop, heard as it played, stopped him once heard out", ["peek", "over"])
        self.assertEqual(self.ats, [1000.8, 1000.8], "the stop check and the burst heard out weren't timed from `at`")
        self.assertTrue(server.Wake.speaking())

    def test_his_stop_heard_back_in_the_ring_after_never_stops_him_or_wakes_anything(self):
        for follow_up, kind in ((0, "follow"), (30, "follow")):         # (his ring is a window, however long the follow-up one)
            with self.subTest(follow_up=follow_up), mock.patch.dict(server.CFG, {"follow_up": follow_up}):
                server.Wake.talked = []
                server.BUS.pub.reset_mock()
                server.Wake.talking(1000.0, 1001.6)                     # his line ends on "stop", 1001.0 s to 1001.6 s
                server.note_played(self.WHEN, 1000.0, 1.6, self.WHEN_WORDS)
                self.hear("Stop.", [("Stop.", 0.1 + gate.ECHO_WORD / 2, 0.4 + gate.ECHO_WORD / 2)])   # (the room rings it)
                self.clock[0] = 1002.8
                server.Wake.check(PCM, 1001.7, ended=1002.7, at=1001.7)
                self.assertNotStopped("his own stop, rung back by the room, was taken", [kind])

    def test_his_stop_heard_back_while_he_talks_and_heard_out_after_is_echo_as_over(self):
        server.Wake.talking(1000.0, 1001.6)
        server.note_played(self.WHEN, 1000.0, 1.6, self.WHEN_WORDS)
        self.hear("Stop.", [("Stop.", 0.1, 0.4)])
        self.clock[0] = 1002.3
        server.Wake.check(PCM, 1001.3, ended=1002.2, at=1001.3)          # (begun in his sound, ended in the ring)
        self.assertNotStopped("his own stop, heard out after he stopped, was taken", ["over"])

    def owners_stop(self):
        """The owner's "Stop." said 0.1 s after ECHO_WORD past the end of his played stop (1001.1 s). → the clip's `at`."""
        server.Wake.talking_until(1005.0)
        server.note_played(self.TIMER, 1000.0, 2.2, self.TIMER_WORDS)
        at = 1001.1 + gate.ECHO_WORD
        self.hear("Stop.", [("Stop.", 0.1, 0.4)])
        self.clock[0] = at + 0.7
        return at

    def test_owner_stop_past_echo_word_after_his_own_stops_him_mid_burst(self):
        at = self.owners_stop()
        self.assertTrue(server.Wake.stop_in(PCM, at, at), "the owner's stop past ECHO_WORD after his own didn't stop him")
        self.assertEqual(self.events(), ["barge"])
        self.assertFalse(server.Wake.speaking())                        # hushed

    def test_owner_stop_past_echo_word_after_his_own_stops_him_once_heard_out(self):
        at = self.owners_stop()
        self.clock[0] = at + 1.1
        server.Wake.check(PCM, at, ended=at + 1.0, at=at)
        self.assertEqual(self.events(), ["barge"])
        self.assertFalse(server.Wake.speaking())

    def test_owner_stop_in_the_same_burst_as_his_own_echo_stops_him(self):
        # one burst catches his "stop" played back and then the owner's "Stop, stop.": the owner's is not his own
        server.Wake.talking_until(1005.0)
        server.note_played(self.TIMER, 1000.0, 2.2, self.TIMER_WORDS)
        late = 0.4 + gate.ECHO_WORD                                      # (past ECHO_WORD after his stop ended at 1001.1)
        self.hear("Stop. Stop, stop.", [("Stop.", 0.1, 0.4), ("Stop,", late, late + 0.3), ("stop.", late + 0.3, late + 0.6)])
        self.clock[0] = 1003.0 + gate.ECHO_WORD
        server.Wake.check(bytes(64000), 1000.8, ended=1002.8 + gate.ECHO_WORD, at=1000.8)
        self.assertEqual(self.events(), ["barge"])
        self.assertFalse(server.Wake.speaking())

    def test_a_burst_cut_free_of_his_voice_is_timed_from_the_clip_after_the_cut(self):
        # Wake.check cuts the front off a burst that ran on past his sound: the cut bytes' length moves `at`
        with mock.patch.dict(server.CFG, {"follow_up": 30}):
            server.Wake.talking(1000.0, 1003.0)
        self.hear("Yes, do it", [])
        self.clock[0] = 1011.5
        server.Wake.check(bytes(server.RATE * 2 * 9), 1002.0, ended=1011.0, at=1001.9)
        self.assertEqual(len(self.ats), 1, self.ats)
        self.assertAlmostEqual(self.ats[0], 1003.0, places=6, msg="not timed from where the cut clip begins")
        self.ats.clear()
        server.Wake.talked = []
        server.Wake.check(bytes(server.RATE * 2 * 3), 1020.0, ended=1023.0, at=1019.9)
        self.assertEqual(self.ats, [1019.9], "an uncut burst wasn't timed from `at`")


@unittest.skipIf(server is None or gate is None, f"server.py or gate.py doesn't import here: {IMPORT_ERR or GATE_ERR}")
class Callers(unittest.TestCase):
    """Each caller builds its Burst with the Heard's words and calls gate.judge(burst, said_lately(), CFG,
    played_lately())."""

    def setUp(self):
        for p in (mock.patch.multiple(server.Wake, talked=[], cut=None),
                  mock.patch.object(server, "time", mock.Mock(monotonic=lambda: 1001.5, time=time.time)),
                  mock.patch.object(server.MicAuto, "learn", lambda pcm: None),
                  mock.patch.object(server.BUS, "pub", mock.Mock()),
                  mock.patch.object(server.Speaker, "idle", classmethod(lambda cls: True)),
                  mock.patch.object(server.Speaker, "stop", mock.Mock())):
            p.start()
            self.addCleanup(p.stop)
        server.SPOKEN.clear()
        self.addCleanup(server.SPOKEN.clear)
        server.PLAYED.clear()
        self.addCleanup(server.PLAYED.clear)
        server.note_spoken("Okay, I will stop the timer now.")
        server.note_played("Okay, I will stop the timer now.", 1000.0, 2.2,
                           [[0.0, 0.3], [0.3, 0.5], [0.5, 0.7], [0.7, 1.1], [1.1, 1.3], [1.3, 1.8], [1.8, 2.2]])
        self.words = (gate.Word("Hey", 1000.9, 1001.1), gate.Word("Void,", 1001.1, 1001.4))
        ears = fakes.ears(server, lambda pcm: "Hey Void, what is the weather like", words_for=lambda pcm, at: self.words)
        self.addCleanup(ears.close)
        self.calls = []
        real = gate.judge
        sig = inspect.signature(real)

        def judge(*a, **k):
            self.calls.append(sig.bind(*a, **k).arguments)
            return real(*a, **k)

        p = mock.patch.object(server.gate, "judge", judge)
        p.start()
        self.addCleanup(p.stop)

    def assertJudgedAsDesigned(self, caller):
        self.assertEqual(len(self.calls), 1, f"{caller}: gate.judge called {len(self.calls)}x on one burst")
        got = self.calls[0]
        self.assertEqual(got["b"].words, self.words, f"{caller}: the Burst not built with the Heard's words")
        self.assertEqual(got["spoken"], server.said_lately(), f"{caller}: not judged against said_lately()")
        self.assertIs(got["cfg"], server.CFG, f"{caller}: not judged with CFG")
        self.assertEqual(tuple(got.get("played", ())), server.played_lately(),
                         f"{caller}: not judged against played_lately()")
        self.assertTrue(server.played_lately(), "(the played stop phrase this test needs was not kept)")

    def test_the_quick_listen_judges_its_heard_words_against_what_he_said_and_played(self):
        with contextlib.redirect_stderr(io.StringIO()):
            server.Wake.heard(PCM, 1000.9, 1000.9)
        self.assertJudgedAsDesigned("Wake.heard")

    def test_the_peek_judges_its_heard_words_against_what_he_said_and_played(self):
        server.Wake.talking_until(1005.0)
        with contextlib.redirect_stderr(io.StringIO()):
            server.Wake.stop_in(PCM, 1000.9, 1000.9)
        self.assertJudgedAsDesigned("Wake.stop_in")

    def test_check_judges_its_heard_words_against_what_he_said_and_played(self):
        with contextlib.redirect_stderr(io.StringIO()):
            server.Wake.check(PCM, 1000.9, ended=1001.4, at=1000.9)
        self.assertJudgedAsDesigned("Wake.check")

    def test_a_follow_up_burst_carries_its_heard_and_the_others_do_not(self):
        with mock.patch.dict(server.CFG, {"follow_up": 30}):
            server.Wake.talking(1000.0, 1000.3)          # (his sound over: the burst below begins inside the window)
        with contextlib.redirect_stderr(io.StringIO()):
            server.Wake.check(PCM, 1000.9, ended=1001.4, at=1000.9)
        b = self.calls[0]["b"]
        self.assertEqual(b.kind, "follow")
        self.assertIsNotNone(b.heard, "a follow-up burst lost its Heard")
        self.calls.clear()
        server.Wake.talked = []
        with contextlib.redirect_stderr(io.StringIO()):
            server.Wake.check(PCM, 1000.9, ended=1001.4, at=1000.9)
        self.assertIsNone(self.calls[0]["b"].heard, "a burst that is not a follow-up carries a Heard")


class Mic:
    """Plays a script of (seconds, loud?) to Wake.session, 0.2 s per read, moving the clock on as it goes."""

    def __init__(self, clock, script):
        tone = (b"\x00\x20" + b"\x00\xe0") * 20            # (a square wave, a quarter of full scale)
        self.clock, self.pcm = clock, b"".join((tone if loud else bytes(len(tone))) * round(sec / 0.0025)
                                               for sec, loud in script)

    def read(self, sec):
        if not self.pcm:
            raise EOFError
        n = int(server.RATE * 2 * sec)
        chunk, self.pcm = self.pcm[:n], self.pcm[n:]
        self.clock[0] += sec
        return chunk

    def close(self):
        pass


QUIET = [(2, False)]
PREROLL = 8 * 0.04                              # s of mic kept ahead of a burst's detection (Wake.session: 8 frames of 40 ms)


def talk(sec, pause=0.0):                       # words (0.2 s on, 0.2 s off), then that much more quiet
    return [(0.2, i % 2 == 0) for i in range(round(sec / 0.2))] + ([(pause, False)] if pause else [])


@unittest.skipIf(server is None, f"server.py doesn't import here: {IMPORT_ERR}")
class Burst(unittest.TestCase):
    """The always-on mic keeps one spoken turn as one burst, short pauses and all, and ends it once you've stopped."""

    def run_mic(self, script, window=False, talk_till=0.0):
        clock, ended = [1000.0], []
        talk_till = 1000.0 + talk_till if talk_till else 0.0       # (he talks for the script's first `talk_till` s)
        W = server.Wake
        with mock.patch.object(server, "time", mock.Mock(monotonic=lambda: clock[0])), \
                mock.patch.object(server, "open_mic", lambda: (Mic(clock, script), "fake", b"")), \
                mock.patch.object(server, "last_speech_end", lambda pcm: False), \
                mock.patch.object(server.BUS, "pub", mock.Mock()), \
                mock.patch.object(server.Speaker, "idle", classmethod(lambda cls: True)), \
                mock.patch.object(W, "should_run", classmethod(lambda cls: True)), \
                mock.patch.object(W, "window_open", classmethod(lambda cls: window)), \
                mock.patch.object(W, "heard", staticmethod(lambda pcm, started, at=None: None)), \
                mock.patch.object(W, "check", classmethod(lambda cls, pcm, started, heard=None, **kw:
                    ended.append((round(len(pcm) / (server.RATE * 2), 1), round(clock[0] - 1000.0, 1), heard)))), \
                mock.patch.multiple(W, talked=[[1000.0, talk_till, talk_till + server.ECHO_TAIL + 60]] if talk_till
                                    else [], cut=None):
            W.session()
        return ended                            # (seconds heard, when it ended, the Heard it was given) per burst

    def test_long_turn_with_pauses_is_one_burst(self):
        turn = QUIET + sum((talk(4, 0.6) for _ in range(5)), []) + talk(3.4) + [(4, False)]
        for window in (False, True):            # listening for "hey Void" / in the follow-up window
            with self.subTest(window=window):
                bursts = self.run_mic(turn, window)
                self.assertEqual(len(bursts), 1, bursts)
                self.assertGreater(bursts[0][0], 25)

    def run_mic_at(self, script, talk_till):
        """Wake.session on `script`, he talking its first `talk_till` s, Wake.heard, Wake.stop_in and Wake.check stood
        in for. → (started, at) each was handed, as three lists of tuples."""
        clock, got = [1000.0], {"heard": [], "stop_in": [], "check": []}
        W = server.Wake
        with mock.patch.object(server, "time", mock.Mock(monotonic=lambda: clock[0])), \
                mock.patch.object(server, "open_mic", lambda: (Mic(clock, script), "fake", b"")), \
                mock.patch.object(server, "last_speech_end", lambda pcm: False), \
                mock.patch.object(server.BUS, "pub", mock.Mock()), \
                mock.patch.object(server.Speaker, "idle", classmethod(lambda cls: True)), \
                mock.patch.object(W, "should_run", classmethod(lambda cls: True)), \
                mock.patch.object(W, "window_open", classmethod(lambda cls: False)), \
                mock.patch.object(W, "heard", staticmethod(
                    lambda pcm, started, at=None: got["heard"].append((started, at)))), \
                mock.patch.object(W, "stop_in", classmethod(
                    lambda cls, pcm, started, at=None: got["stop_in"].append((started, at)) or False)), \
                mock.patch.object(W, "check", classmethod(
                    lambda cls, pcm, started, heard=None, ended=None, at=None: got["check"].append((started, at)))), \
                mock.patch.multiple(W, talked=[[1000.0, 1000.0 + talk_till, 1000.0 + talk_till + server.ECHO_TAIL + 60]]
                                    if talk_till else [], cut=None):
            W.session()
        return got

    def test_every_caller_session_hands_a_burst_to_is_given_when_its_first_sample_was_caught(self):
        # started is when the burst was detected, after the pre-roll; `at` is the clip's first sample, before it
        got = self.run_mic_at(QUIET + talk(11) + [(4, False)], talk_till=20)      # (he talks all through it: a peek)
        self.assertTrue(got["stop_in"], "the burst begun over him was never peeked at")
        self.assertTrue(got["check"], "the burst was never heard out")
        for name in ("stop_in", "check"):
            for started, at in got[name]:
                self.assertIsNotNone(at, f"Wake.{name} was not handed when the clip's first sample was caught")
                self.assertLess(at, started, f"Wake.{name}: `at` is not before the burst was detected")
                self.assertLessEqual(started - at, PREROLL + 0.2 + 1e-6,
                                     f"Wake.{name}: `at` is further back than the pre-roll and one read")
        self.assertEqual({at for _, at in got["stop_in"]} | {at for _, at in got["check"]},
                         {got["check"][0][1]}, "the peeks and the check were handed different `at`s for one burst")

    def test_the_quick_listen_is_given_when_the_burst_first_sample_was_caught_too(self):
        got = self.run_mic_at(QUIET + talk(2.5) + [(4, False)], talk_till=0)   # (he is quiet: a wake listen)
        self.assertTrue(got["heard"], "Wake.heard was never called")
        started, at = got["heard"][0]
        self.assertIsNotNone(at)
        self.assertLess(at, started)
        self.assertEqual(got["check"][0][1], at, "Wake.heard and Wake.check were handed different `at`s")

    def test_answer_begun_as_he_finished_heard_out(self):     # his last second, then 10 s more: one whole burst
        bursts = self.run_mic(QUIET + talk(11) + [(4, False)], talk_till=3)
        self.assertEqual(len(bursts), 1, bursts)
        self.assertGreater(bursts[0][0], 10.5)
        self.assertIsNone(bursts[0][2])                   # (a request: transcribed in full, not a quick name check)

    def test_turn_then_silence_ends_promptly(self):
        for window in (False, True):
            with self.subTest(window=window):
                bursts = self.run_mic(QUIET + talk(5) + [(6, False)], window)
                self.assertEqual(len(bursts), 1, bursts)
                self.assertLess(bursts[0][1] - 7, 2.0)        # within 2 s of your last word


ALBUMS = ["Kill 'Em All really belongs in the 30K rolloff folder.",
          "The other two albums are already sorted, but you might want to check that."]


@unittest.skipIf(gate is None, f"app/gate.py doesn't import here: {GATE_ERR}")
class EchoMatch(unittest.TestCase):
    """gate.is_echo(heard, spoken): does what the mic heard mostly repeat what he said lately (`spoken`, his lines)?"""

    def test_match_repeat_and_partial(self):
        self.assertTrue(gate.is_echo("I moved the meeting to Thursday at three", [REPLY]))
        self.assertTrue(gate.is_echo("Sure I moved the meeting to thursday, at 3 and told Sam", [REPLY]))

    def test_match_spans_sentences(self):         # one burst can catch several of his sentences
        said = ["There are three things going on in Gauntlet.",
                "The checkpoint work has two steps committed, and its lead is still running.",
                "It fixed the three review findings, and is waiting on the checks before it commits."]
        self.assertTrue(gate.is_echo("There are three things going on in government. The checkpoint work has two "
                                     "steps committed, and its lead is still running. It fixed the three review "
                                     "findings, and is waiting on the checks before it commits", said))
        self.assertFalse(gate.is_echo("Can you check on the three review findings for me", said))

    def test_match_ignores_real_questions(self):
        self.assertFalse(gate.is_echo("Can you move the meeting to Friday instead", [REPLY]))
        self.assertFalse(gate.is_echo("meeting Thursday", [REPLY]))          # too short to judge
        self.assertFalse(gate.is_echo("what is the weather like today", [REPLY]))

    def test_match_in_order(self):
        self.assertFalse(gate.is_echo("Sam about told and three at Thursday to meeting the moved", [REPLY]))

    def test_nothing_said_lately_is_no_echo(self):
        self.assertFalse(gate.is_echo("I moved the meeting to Thursday at three", []))

    def test_badly_misheard_echo_matches(self):
        self.assertTrue(gate.is_echo("I can kill them all really long in a 30K bonus folder", ALBUMS))
        self.assertTrue(gate.is_echo("But you might want to check me.", ALBUMS))

    def test_request_sharing_his_words_is_no_echo(self):
        for ask in ("please move Reload to the 30K folder too", "can you check the 30K folder for me",
                    "move all of the other albums to the rolloff folder"):
            self.assertFalse(gate.is_echo(ask, ALBUMS), ask)


class Seg:
    def __init__(self, text, avg_logprob=-0.3, no_speech_prob=0.1, compression_ratio=1.4):
        self.text, self.avg_logprob, self.no_speech_prob, self.compression_ratio = (text, avg_logprob, no_speech_prob,
                                                                                    compression_ratio)


@unittest.skipIf(server is None, f"server.py doesn't import here: {IMPORT_ERR}")
class Sure(unittest.TestCase):
    """transcribe_pcm(sure=True), what the always-on mic uses: drops what Whisper itself isn't sure it heard."""

    def run_on(self, segs, **kw):
        model = mock.Mock()
        model.transcribe.return_value = (iter(segs), None)
        with mock.patch.object(server, "whisper", lambda: model):
            return server.run_whisper(server.pcm_audio(PCM), **kw)

    def test_unsure_segments_dropped(self):
        segs = [Seg("Please add milk."), Seg("Oh my god.", avg_logprob=-1.4), Seg("Go go go go go.", compression_ratio=3.1),
                Seg("Hmm.", avg_logprob=-0.8, no_speech_prob=0.9)]
        self.assertEqual(self.run_on(segs, sure=True), "Please add milk.")

    def test_push_to_talk_keeps_everything(self):
        self.assertEqual(self.run_on([Seg("Please add milk."), Seg("to the list", avg_logprob=-1.4)]),
                         "Please add milk. to the list")


class TimedWord:
    """A word Whisper timed, as faster-whisper hands it back with word_timestamps: seconds into the clip."""

    def __init__(self, word, start, end, probability=0.9):
        self.word, self.start, self.end, self.probability = word, start, end, probability


class TimedSeg(Seg):
    def __init__(self, text, words, **kw):
        super().__init__(text, **kw)
        self.words = words


@unittest.skipIf(server is None or gate is None, f"server.py or gate.py doesn't import here: {IMPORT_ERR or GATE_ERR}")
class HeardWordTimes(unittest.TestCase):
    """transcribe_pcm_heard given `at`, with a stop phrase of his played near the clip, runs Whisper with word
    timestamps, and Heard.words holds the kept segments' words at `at` plus each word's time; otherwise Heard.words is
    None and Whisper runs untimed. run_whisper_heard passes `words` to Whisper as word_timestamps."""

    SEGS = [TimedSeg(" Okay, stop.", [TimedWord(" Okay,", 0.1, 0.4), TimedWord(" stop.", 0.5, 0.8)]),
            TimedSeg(" Oh my god.", [TimedWord(" Oh", 0.9, 1.0), TimedWord(" my", 1.0, 1.1),
                                     TimedWord(" god.", 1.1, 1.3)], avg_logprob=-1.4)]
    SECS = len(PCM) / (server.RATE * 2) if server else 0.0           # the clip PCM is this long

    def setUp(self):
        server.PLAYED.clear()
        self.addCleanup(server.PLAYED.clear)
        self.model = mock.Mock()
        self.model.transcribe.side_effect = lambda *a, **k: (iter(self.SEGS), None)
        p = mock.patch.object(server, "whisper", lambda: self.model)
        p.start()
        self.addCleanup(p.stop)

    def asked_for_word_times(self):
        return [bool(c.kwargs.get("word_timestamps", False)) for c in self.model.transcribe.call_args_list]

    def times(self, words):
        return [(w.text.strip(), round(w.start, 6), round(w.end, 6)) for w in words]

    def test_a_burst_overlapping_a_played_stop_gets_its_kept_words_at_monotonic_times(self):
        at = time.monotonic()
        server.note_played("Stop.", at + 0.2, 0.4, [[0.0, 0.4]])     # his "stop" plays at+0.2 s to at+0.6 s
        heard = server.transcribe_pcm_heard(PCM, at=at, sure=True)
        self.assertEqual(self.asked_for_word_times(), [True], "Whisper not asked for word times near his stop")
        self.assertIsNotNone(heard.words, "a burst near his played stop came back untimed")
        self.assertEqual(self.times(heard.words),                    # (the segment gate.sure dropped is not in it)
                         [("Okay,", round(at + 0.1, 6), round(at + 0.4, 6)),
                          ("stop.", round(at + 0.5, 6), round(at + 0.8, 6))])
        for w in heard.words:
            self.assertIsInstance(w, gate.Word)
        self.assertEqual(heard.text, "Okay, stop.")

    def test_a_burst_ending_within_echo_word_of_a_played_stop_is_timed(self):
        at = time.monotonic()
        server.note_played("Stop.", at + self.SECS + gate.ECHO_WORD / 2, 0.4, [[0.0, 0.4]])
        heard = server.transcribe_pcm_heard(PCM, at=at, sure=True)
        self.assertEqual(self.asked_for_word_times(), [True])
        self.assertIsNotNone(heard.words)

    def test_a_burst_begun_within_echo_word_after_a_played_stop_is_timed(self):
        at = time.monotonic()
        server.note_played("Stop.", at - gate.ECHO_WORD / 2 - 0.4, 0.4, [[0.0, 0.4]])
        heard = server.transcribe_pcm_heard(PCM, at=at, sure=True)
        self.assertEqual(self.asked_for_word_times(), [True])
        self.assertIsNotNone(heard.words)

    def test_a_played_stop_at_the_end_of_a_long_clip_makes_it_timed(self):
        # "near" spans the clip's whole length, from `at` to `at` plus len(pcm) / (16 kHz * 2 bytes)
        seconds = gate.ECHO_WORD + 6.0
        pcm = bytes(int(seconds * 16000) * 2)
        at = time.monotonic() - seconds
        server.note_played("Stop.", at + seconds - 0.6, 0.4, [[0.0, 0.4]])
        heard = server.transcribe_pcm_heard(pcm, at=at, sure=True)
        self.assertEqual(self.asked_for_word_times(), [True], "Whisper not asked for word times near the clip's end")
        self.assertIsNotNone(heard.words)

    def test_a_burst_near_no_played_stop_is_untimed(self):
        # one stop he played past ECHO_WORD after the clip ends, one that ended past ECHO_WORD before it began (both
        # kept, inside ECHO_KEEP): the burst is untimed because neither is near it, not because one expired
        at = time.monotonic()
        server.note_played("Stop.", at + self.SECS + gate.ECHO_WORD + 0.1, 0.4, [[0.0, 0.4]])
        server.note_played("Stop.", at - gate.ECHO_WORD - 0.1 - 0.4, 0.4, [[0.0, 0.4]])
        self.assertEqual(len(server.played_lately()), 2, "(the played stops this test needs were not kept)")
        heard = server.transcribe_pcm_heard(PCM, at=at, sure=True)
        self.assertIsNone(heard.words)
        self.assertEqual(self.asked_for_word_times(), [False])
        self.assertEqual(heard.text, "Okay, stop.")                  # (heard as before)

    def test_a_burst_with_nothing_played_is_untimed(self):
        heard = server.transcribe_pcm_heard(PCM, at=time.monotonic(), sure=True)
        self.assertIsNone(heard.words)
        self.assertEqual(self.asked_for_word_times(), [False])

    def test_a_burst_without_at_is_untimed(self):
        server.note_played("Stop.", time.monotonic(), 0.4, [[0.0, 0.4]])
        heard = server.transcribe_pcm_heard(PCM, sure=True)
        self.assertIsNone(heard.words)
        self.assertEqual(self.asked_for_word_times(), [False])

    def test_a_clip_too_short_to_send_keeps_words_none(self):
        at = time.monotonic()
        server.note_played("Stop.", at, 0.4, [[0.0, 0.4]])
        heard = server.transcribe_pcm_heard(bytes(1000), at=at, sure=True)
        self.assertIsNone(heard.words)
        self.assertEqual(self.model.transcribe.call_count, 0)

    def test_run_whisper_heard_passes_words_as_word_timestamps(self):
        audio = server.pcm_audio(PCM)
        timed = server.run_whisper_heard(audio, sure=True, words=True)
        untimed = server.run_whisper_heard(audio, sure=True)
        server.run_whisper_heard(audio, sure=True, words=False)
        self.assertEqual(self.asked_for_word_times(), [True, False, False])
        self.assertEqual(self.times(timed.words), [("Okay,", 0.1, 0.4), ("stop.", 0.5, 0.8)],
                         "run_whisper_heard's word times are not the clip's own")
        self.assertIsNone(untimed.words)


@unittest.skipIf(gate is None, f"app/gate.py doesn't import here: {GATE_ERR}")
class GateSure(unittest.TestCase):
    """gate.sure(segments), the one Whisper segment filter: keeps only the segments Whisper is sure of, in order."""

    def texts(self, segs):
        return [s.text for s in gate.sure(segs)]

    def test_unsure_segments_dropped(self):
        segs = [Seg("Please add milk."), Seg("Oh my god.", avg_logprob=-1.4), Seg("Go go go go go.", compression_ratio=3.1),
                Seg("Hmm.", avg_logprob=-0.8, no_speech_prob=0.9)]
        self.assertEqual(self.texts(segs), ["Please add milk."])

    def test_sure_segments_all_kept_in_order(self):
        segs = [Seg("Please add milk."), Seg("And eggs."), Seg("Thanks.")]
        self.assertEqual(self.texts(segs), ["Please add milk.", "And eggs.", "Thanks."])

    def test_thresholds_are_gates_own(self):
        at = [Seg("at the floor", avg_logprob=gate.SEG_LOGPROB),
              Seg("at the ceiling", compression_ratio=gate.SEG_COMPRESSION)]
        under = [Seg("under the floor", avg_logprob=gate.SEG_LOGPROB - 0.01),
                 Seg("over the ceiling", compression_ratio=gate.SEG_COMPRESSION + 0.01)]
        self.assertEqual(self.texts(at + under), ["at the floor", "at the ceiling"])

    def test_nothing_in_nothing_out(self):
        self.assertEqual(gate.sure([]), [])


@unittest.skipIf(server is None, f"server.py doesn't import here: {IMPORT_ERR}")
class HisSound(unittest.TestCase):
    """Wake.talked holds the time his sound is coming out of the speakers, and nothing else: Speaker._write records a
    chunk as talking only when it is sound, and a reply begun once his sound has stopped is his owner's follow-up."""

    @classmethod
    def setUpClass(cls):
        """His reply played as a scene through the real Speaker player path (_maker and _player_loop: his last sentence
        and the pause after it): the spans it left in Wake.talked, and when his last sound came out of the room's
        speakers, read off the room's own output rather than off any time the code stamped."""
        super().setUpClass()
        import scenes                                                   # (needs numpy, as server.py does)
        W, spans = server.Wake, []
        real = scenes.Sim.run

        def run(sim, end):                                              # (the scene over, before its patches unwind)
            r = real(sim, end)
            spans[:] = [list(s) for s in W.talked]
            return r
        scenes.new_run()
        try:
            with mock.patch.object(scenes.Sim, "run", run), contextlib.redirect_stderr(io.StringIO()):
                t = scenes.play(scenes.Room(), void="void_question.wav")
        finally:
            scenes.new_run()
        cls.reply_talked = spans
        cls.reply_last_sound = None if t.void_end is None else scenes.T0 + t.void_end

    def setUp(self):
        S, W = server.Speaker, server.Wake
        saved = {k: W.__dict__[k] for k in ("talked",)}
        self.addCleanup(lambda: [setattr(W, k, v) for k, v in saved.items()])
        W.talked = []
        self.clock = [100.0]
        self.ref = FakeRef()
        self.player = FakePlayer(self.clock)
        self.pub = mock.Mock()
        self.text = ""
        for k, v in (("gen", 7), ("proc", self.player), ("prate", SPK_RATE), ("written", 1000), ("t0", 100.0),
                     ("filled", False), ("stats", {}), ("todo", []), ("ready", [])):
            self.patch(S, k, v)
        self.patch(server, "time", mock.Mock(wraps=time, monotonic=lambda: self.clock[0],
                                             sleep=lambda s: self.clock.__setitem__(0, self.clock[0] + s)))
        self.patch(server, "make_player", lambda rate: FakePlayer(self.clock))
        self.patch(server.hearing, "PlayRef", self.ref)
        self.patch(server.Wake, "hush", classmethod(lambda cls, at=None: None))
        self.patch(server.MicAuto, "learn", lambda pcm: None)
        self.patch(server.BUS, "pub", self.pub)
        self.patch(server.Speaker, "idle", classmethod(lambda cls: True))
        self.patch(server, "SPOKEN", type(server.SPOKEN)())
        ears = fakes.ears(server, lambda pcm: self.text)
        self.addCleanup(ears.close)

    def patch(self, obj, name, value):
        p = mock.patch.object(obj, name, value)
        p.start()
        self.addCleanup(p.stop)

    def talking_calls(self):
        """Spy on Wake.talking. → the list each call's arguments are appended to."""
        calls, real = [], server.Wake.__dict__["talking"].__func__
        self.patch(server.Wake, "talking", classmethod(lambda cls, *a, **k: calls.append(a) or real(cls, *a, **k)))
        return calls

    def test_write_records_talking_only_for_sound(self):
        self.assertIn("sound", inspect.signature(server.Speaker._write).parameters, "Speaker._write takes no `sound`")
        calls = self.talking_calls()
        data = bytes(range(256)) * 19
        self.assertTrue(server.Speaker._write(data, 7, sound=False))
        silent = list(calls)
        self.assertEqual(server.Wake.talked, [], "a chunk that is not sound was recorded in Wake.talked")
        self.assertEqual(self.player.got, data, "the silent chunk wasn't played")
        self.assertEqual(b"".join(c[0] for c in self.ref.calls), data, "PlayRef wasn't told the silent chunk played")
        self.assertTrue(server.Speaker._write(data, 7, sound=True))
        self.assertEqual((silent, bool(calls[len(silent):])), ([], True),
                         "talking recorded for a chunk that is not sound, or not for one that is")

    def test_its_good_said_after_his_last_sentence_and_its_pause_is_a_follow_up(self):
        """The 27 Oct reply: 'while talking (over): It's good', said after his last sound, in the ring and after it."""
        self.assertIn("sound", inspect.signature(server.Speaker._write).parameters, "Speaker._write takes no `sound`")
        self.assertTrue(self.reply_talked, "his reply, played through the player, left nothing in Wake.talked")
        self.assertIsNotNone(self.reply_last_sound, "his reply never came out of the room's speakers")
        burst = bytes(int(server.RATE * 2 * 1.9))
        got = []
        for after in (0.1, server.ECHO_TAIL + 0.2):                    # began in the ring / after it
            server.Wake.talked = [list(s) for s in self.reply_talked]  # (what the player left: his sentence, its pause)
            server.note_spoken("Both albums are in the 30K folder now, next to the original pressing.")
            with mock.patch.dict(server.CFG, {"follow_up": 30}):
                began = self.reply_last_sound + after
                self.clock[0] = began + 1.9 + 0.4
                judged = []
                real = server.gate.judge
                err = io.StringIO()
                self.text = "It's good"
                self.pub.reset_mock()
                with mock.patch.object(server.gate, "judge", lambda b, *a: judged.append(b) or real(b, *a)), \
                        contextlib.redirect_stderr(err):
                    server.Wake.check(burst, began, ended=began + 1.9)
            events = [(c.kwargs.get("t"), c.kwargs.get("text"), c.kwargs.get("follow")) for c in self.pub.call_args_list
                      if c.kwargs.get("t") != "voice"]
            log = [ln for ln in err.getvalue().splitlines() if ln.startswith("[void]")]
            got.append((round(after, 1), events, [b.kind for b in judged],
                        any("while talking" in ln for ln in log)))
        self.assertEqual(got, [(round(after, 1), [("wake", "It's good", True)], ["follow"], False)
                               for after in (0.1, server.ECHO_TAIL + 0.2)])


if __name__ == "__main__":
    unittest.main()
