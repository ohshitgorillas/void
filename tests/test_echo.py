"""Void must not hear his own voice as yours: any transcript that mostly repeats what he said in the last minute is
dropped. While he talks (and in his echo just after) only "stop" / "hey Void" and the like cut him off: anything else
the mic catches then is taken for his own voice, however garbled, and dropped. Push-to-talk still works.

    python3 -m unittest discover -s tests
"""
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

try:
    import server
except Exception as e:  # noqa: BLE001
    server, IMPORT_ERR = None, e
else:
    IMPORT_ERR = None

REPLY = "Sure, I moved the meeting to Thursday at three and told Sam about it."
PCM = bytes(32000)


@unittest.skipIf(server is None, f"server.py doesn't import here: {IMPORT_ERR}")
class Echo(unittest.TestCase):
    def setUp(self):
        W = server.Wake
        self._saved = {k: W.__dict__[k] for k in ("speaking_until", "follow_from", "follow_until")}
        self.addCleanup(self._restore)
        W.speaking_until = W.follow_from = W.follow_until = 0.0
        server.SPOKEN.clear()
        self.addCleanup(server.SPOKEN.clear)
        self.pub = mock.Mock()
        self.text = ""
        for p in (mock.patch.object(server, "speech_seconds", lambda pcm: 2.0),
                  mock.patch.object(server, "transcribe_pcm", lambda pcm, **kw: self.text),
                  mock.patch.object(server.MicAuto, "learn", lambda pcm: None),
                  mock.patch.object(server.BUS, "pub", self.pub),
                  mock.patch.object(server.Speaker, "idle", classmethod(lambda cls: True))):
            p.start()
            self.addCleanup(p.stop)

    def _restore(self):
        for k, v in self._saved.items():
            setattr(server.Wake, k, v)

    def burst(self, text, started=None):
        self.text = text
        server.Wake.check(PCM, time.monotonic() if started is None else started)
        return [c.kwargs for c in self.pub.call_args_list]

    def after_speech(self, ago):             # he finished talking `ago` seconds ago, follow window open
        now = time.monotonic()
        server.Wake.talking_until(now - ago)
        server.Wake.follow_until = now + 30

    # the echo match
    def test_match_repeat_and_partial(self):
        server.note_spoken(REPLY)
        self.assertTrue(server.is_echo("I moved the meeting to Thursday at three"))
        self.assertTrue(server.is_echo("Sure I moved the meeting to thursday, at 3 and told Sam"))

    def test_match_spans_sentences(self):         # one burst can catch several of his sentences
        for line in ("There are three things going on in Gauntlet.",
                     "The checkpoint work has two steps committed, and its lead is still running.",
                     "It fixed the three review findings, and is waiting on the checks before it commits."):
            server.note_spoken(line)
        self.assertTrue(server.is_echo("There are three things going on in government. The checkpoint work has two "
                                       "steps committed, and its lead is still running. It fixed the three review "
                                       "findings, and is waiting on the checks before it commits"))
        self.assertFalse(server.is_echo("Can you check on the three review findings for me"))

    def test_match_ignores_real_questions(self):
        server.note_spoken(REPLY)
        self.assertFalse(server.is_echo("Can you move the meeting to Friday instead"))
        self.assertFalse(server.is_echo("meeting Thursday"))          # too short to judge
        self.assertFalse(server.is_echo("what is the weather like today"))

    def test_match_in_order_and_expires(self):
        server.note_spoken(REPLY)
        self.assertFalse(server.is_echo("Sam about told and three at Thursday to meeting the moved"))
        server.SPOKEN.clear()
        server.SPOKEN.append((time.monotonic() - 120, REPLY))
        self.assertFalse(server.is_echo("I moved the meeting to Thursday at three"))

    # what the log showed slipping through just after his echo: his own words, badly misheard
    def test_badly_misheard_echo_after_tail_dropped(self):
        server.note_spoken("Kill 'Em All really belongs in the 30K rolloff folder.")
        server.note_spoken("The other two albums are already sorted, but you might want to check that.")
        self.assertTrue(server.is_echo("I can kill them all really long in a 30K bonus folder"))
        self.assertTrue(server.is_echo("But you might want to check me."))
        for heard in ("I can kill them all really long in a 30K bonus folder", "But you might want to check me."):
            self.after_speech(server.ECHO_TAIL + 0.6)
            server.Wake.follow_from = 0.0
            self.assertEqual(self.burst(heard), [], heard)

    def test_request_sharing_his_words_gets_through(self):
        server.note_spoken("Kill 'Em All really belongs in the 30K rolloff folder.")
        server.note_spoken("The other two albums are already sorted, but you might want to check that.")
        for ask in ("please move Reload to the 30K folder too", "can you check the 30K folder for me",
                    "move all of the other albums to the rolloff folder"):
            self.assertFalse(server.is_echo(ask), ask)
        self.after_speech(server.ECHO_TAIL + 0.6)
        server.Wake.follow_from = 0.0
        self.assertFollowUp(self.burst("please move Reload to the 30K folder too"),
                            "please move Reload to the 30K folder too")

    def test_speaker_say_records(self):
        with mock.patch.object(server.Speaker, "_start", classmethod(lambda cls: None)):
            server.Speaker.say(REPLY, 1)
        self.addCleanup(server.Speaker.todo.clear)
        self.assertTrue(server.is_echo("I moved the meeting to Thursday at three"))

    # the time gate
    def test_follow_window_waits_for_tail(self):
        server.Wake.talking_until(time.monotonic())
        self.assertGreaterEqual(server.Wake.follow_from, server.Wake.speaking_until + server.ECHO_TAIL)

    def assertFollowUp(self, ev, text="please add milk to the shopping list"):
        self.assertEqual([(e.get("t"), e.get("text"), e.get("follow")) for e in ev], [("wake", text, True)])

    def test_words_in_tail_dropped(self):          # still his echo ringing: not a request
        self.after_speech(0.3)
        self.assertEqual(self.burst("please add milk to the shopping list", time.monotonic() - 0.5), [])

    def test_words_started_before_tail_end_dropped(self):
        self.after_speech(1.6)
        started = server.Wake.speaking_until + server.ECHO_TAIL - 0.2
        server.Wake.follow_from = 0.0
        self.assertEqual(self.burst("please add milk to the shopping list", started), [])

    def test_echo_in_tail_dropped(self):
        self.after_speech(0.3)
        server.note_spoken(REPLY)
        self.assertEqual(self.burst("I moved the meeting to Thursday at three", time.monotonic() - 0.5), [])

    def test_stray_word_in_tail_ignored(self):
        self.after_speech(0.3)
        self.assertEqual(self.burst("um", time.monotonic() - 0.5), [])

    def test_follow_up_after_tail_accepted(self):
        self.after_speech(server.ECHO_TAIL + 0.6)
        server.Wake.follow_from = 0.0
        ev = self.burst("please add milk to the shopping list")
        self.assertEqual([e.get("t") for e in ev], ["wake"])
        self.assertTrue(ev[0]["follow"])

    def test_follow_up_while_claude_works_heard(self):      # the page holds it until his reply is done
        self.after_speech(server.ECHO_TAIL + 0.6)
        server.Wake.follow_from = 0.0
        self.assertTrue(server.ST.lock.acquire(blocking=False))
        self.addCleanup(server.ST.lock.release)
        self.assertTrue(server.Wake.window_open())
        self.assertFollowUp(self.burst("please add milk to the shopping list"))

    def test_follow_up_echo_dropped_after_tail(self):
        self.after_speech(server.ECHO_TAIL + 0.6)
        server.note_spoken(REPLY)
        self.assertEqual(self.burst("I moved the meeting to Thursday at three"), [])

    def test_wake_word_echo_dropped(self):
        server.note_spoken("Okay. Hey Void, you can ask me anything about the calendar this week.")
        self.assertEqual(self.burst("Hey Void, you can ask me anything about the calendar"), [])

    def test_wake_word_still_works(self):
        ev = self.burst("Hey Void, what is the weather like")
        self.assertEqual([e.get("t") for e in ev], ["wake"])

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
        self.assertEqual(server.Wake.speaking_until, 0.0)          # hushed

    def test_stop_inside_longer_burst_while_talking(self):
        server.Wake.talking_until(time.monotonic() + 5)
        self.assertEqual([e.get("t") for e in self.burst("okay okay hold on a second")], ["barge"])

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
        self.assertGreater(server.Wake.speaking_until, time.monotonic())   # still talking

    # what the log showed cutting him off: his own sentences, too garbled for the echo match
    def test_garbled_echo_while_talking_no_barge_in(self):
        server.note_spoken("Kill 'Em All really belongs in the 30K rolloff folder.")
        server.Wake.talking_until(time.monotonic() + 5)
        self.assertEqual(self.burst("I can kill them all really long in a 30K bonus folder"), [])
        self.assertGreater(server.Wake.speaking_until, time.monotonic())

    def test_garbled_tail_of_his_sentence_no_barge_in(self):   # "heard 7.0s, 22 words, while talking"
        server.note_spoken("The other two albums are already sorted, and the remaster sits next to the original "
                           "pressing so you can compare them side by side whenever you like.")
        server.Wake.talking_until(time.monotonic() + 5)
        tail = ("sorted in the remaster since next to the regional pressing so you can compare them, "
                "side by side when ever you like")
        self.assertEqual(len(tail.split()), 22)
        self.assertEqual(self.burst(tail), [])
        self.assertEqual(self.burst("But you might want to check me."), [])
        self.assertGreater(server.Wake.speaking_until, time.monotonic())

    def test_echo_while_talking_dropped(self):
        server.note_spoken(REPLY)
        server.Wake.talking_until(time.monotonic() + 5)
        self.assertEqual(self.burst("I moved the meeting to Thursday at three"), [])

    def test_noise_while_talking_ignored(self):
        server.Wake.talking_until(time.monotonic() + 5)
        self.assertEqual(self.burst("thank you for watching"), [])
        self.assertEqual(self.burst("okay"), [])

    # noise in the follow-up window (what the log showed turning into requests)
    def test_repeated_phrase_is_noise(self):
        for junk in ("Oh my god, oh my god", "Go. Go. Go.", "", "   "):
            self.after_speech(server.ECHO_TAIL + 0.6)
            server.Wake.follow_from = 0.0
            self.assertEqual(self.burst(junk), [], junk)
        self.assertFalse(server.is_noise("please add milk to the shopping list"))
        self.assertFalse(server.is_noise("very very good"))

    def test_mic_gain_learns_only_from_your_requests(self):
        learn = mock.Mock()
        with mock.patch.object(server.MicAuto, "learn", learn):
            self.after_speech(server.ECHO_TAIL + 0.6)
            server.Wake.follow_from = 0.0
            self.burst("")                                   # "heard 2.0s, 0 words"
            self.burst("Go. Go. Go.")
            learn.assert_not_called()
            self.assertFollowUp(self.burst("please add milk to the shopping list"))
            learn.assert_called_once()


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


def talk(sec, pause=0.0):                       # words (0.2 s on, 0.2 s off), then that much more quiet
    return [(0.2, i % 2 == 0) for i in range(round(sec / 0.2))] + ([(pause, False)] if pause else [])


@unittest.skipIf(server is None, f"server.py doesn't import here: {IMPORT_ERR}")
class Burst(unittest.TestCase):
    """The always-on mic keeps one spoken turn as one burst, short pauses and all, and ends it once you've stopped."""

    def run_mic(self, script, window=False):
        clock, ended = [1000.0], []
        W = server.Wake
        with mock.patch.object(server, "time", mock.Mock(monotonic=lambda: clock[0])), \
                mock.patch.object(server, "open_mic", lambda: (Mic(clock, script), "fake", b"")), \
                mock.patch.object(server, "last_speech_end", lambda pcm: False), \
                mock.patch.object(server.BUS, "pub", mock.Mock()), \
                mock.patch.object(server.Speaker, "idle", classmethod(lambda cls: True)), \
                mock.patch.object(W, "should_run", classmethod(lambda cls: True)), \
                mock.patch.object(W, "window_open", classmethod(lambda cls: window)), \
                mock.patch.object(W, "heard", staticmethod(lambda pcm: "")), \
                mock.patch.object(W, "check", classmethod(lambda cls, pcm, started, text=None: ended.append(
                    (round(len(pcm) / (server.RATE * 2), 1), round(clock[0] - 1000.0, 1))))), \
                mock.patch.multiple(W, speaking_until=0.0, follow_from=0.0, follow_until=0.0, cut=None):
            W.session()
        return ended                            # (seconds heard, when it ended) per burst

    def test_long_turn_with_pauses_is_one_burst(self):
        turn = QUIET + sum((talk(4, 0.6) for _ in range(5)), []) + talk(3.4) + [(4, False)]
        for window in (False, True):            # listening for "hey Void" / in the follow-up window
            with self.subTest(window=window):
                bursts = self.run_mic(turn, window)
                self.assertEqual(len(bursts), 1, bursts)
                self.assertGreater(bursts[0][0], 25)

    def test_turn_then_silence_ends_promptly(self):
        for window in (False, True):
            with self.subTest(window=window):
                bursts = self.run_mic(QUIET + talk(5) + [(6, False)], window)
                self.assertEqual(len(bursts), 1, bursts)
                self.assertLess(bursts[0][1] - 7, 2.0)        # within 2 s of your last word


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


if __name__ == "__main__":
    unittest.main()
