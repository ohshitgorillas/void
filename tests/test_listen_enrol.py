"""Listen.run teaches the voiceprint only from a request in words: a recording that came back empty, as noise, as a
stock filler, or as an echo of his own voice enrols nothing. What is enrolled is the recording's speech alone, without
the lead-in silence and the chime before it, and each enrolment logs one line saying what was enrolled.

Every Listen recording is kept or dropped by gate.judge alone, as a "listen" burst: a dropped one (too little speech,
noise or filler, his own echo) is never sent on as a request, and each verdict logs one '[void] <why>: <said>' line.

The mic is a fake that plays one recording (a lead-in of room hiss, a chime, then a real clip of you) and Whisper is
replaced by what it "hears", so the tests need neither a microphone nor the speech model.

    python3 -m unittest tests.test_listen_enrol -v
"""
import contextlib
import io
import math
import re
import sys
import time
import types
import unittest
import wave
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "tests"))
import suite_data  # noqa: E402,F401  (Void's data folder: the suite's own, set before server.py settles it)
import gate  # noqa: E402
from fakes import hiss, pieces, ears  # noqa: E402

try:
    import server
except Exception as e:  # noqa: BLE001
    server, SERVER_ERR = None, e
else:
    SERVER_ERR = None

SR = 16000
SCENES = ROOT / "tests" / "fixtures" / "scenes"
SPEECH = "you_stop.wav"                          # "Stop, stop, that's not what I asked for."
REQUEST = "Stop, stop, that's not what I asked for."
LEAD_IN, CHIME, GAP, TAIL = 1.0, 0.4, 0.3, 0.6   # seconds: hiss before the chime, the chime, hiss before you, hiss after


def fixture(name):
    with wave.open(str(SCENES / name), "rb") as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, SR), name
        return w.readframes(w.getnframes())


def s16(samples):
    return b"".join(int(max(-32768, min(32767, round(x * 32768)))).to_bytes(2, "little", signed=True)
                    for x in samples)


def chime(seconds):
    """Two bright tones dying away, as a listening chime sounds."""
    n = int(seconds * SR)
    return s16(0.3 * math.exp(-4.0 * i / SR) * (math.sin(2 * math.pi * 880 * i / SR)
                                                + math.sin(2 * math.pi * 1320 * i / SR)) / 2 for i in range(n))


class Recording:
    """One Listen recording, in order: lead-in hiss, chime, a short gap, your speech, a tail."""

    def __init__(self):
        self.lead_in = hiss(LEAD_IN, 1)
        self.chime = chime(CHIME)
        self.speech = fixture(SPEECH)
        self.pcm = self.lead_in + self.chime + hiss(GAP, 2) + self.speech + hiss(TAIL, 3)


class FakeMic:
    """open_clean_mic's mic, playing `pcm` 0.1 s per read and then ending."""

    def __init__(self, pcm):
        self.pcm, self.at = pcm, 0

    def read(self, seconds):
        if self.at >= len(self.pcm):
            raise EOFError
        n = int(seconds * SR) * 2
        out, self.at = self.pcm[self.at:self.at + n], self.at + n
        return out

    def close(self):
        pass

    def err(self):
        return ""


@unittest.skipIf(server is None, f"server.py doesn't import here: {SERVER_ERR}")
class ListenEnrolTest(unittest.TestCase):

    def setUp(self):
        self.rec = Recording()
        self.enrolled = []
        vp = types.SimpleNamespace(available=True, enrolled=0, enroll=self.enrolled.append)
        self.heard = REQUEST
        for p in (mock.patch.object(server, "open_clean_mic", lambda: (FakeMic(self.rec.pcm), "fake mic", b"")),
                  mock.patch.object(server.MicAuto, "learn", lambda pcm: None),
                  mock.patch.object(server.Voice, "get", lambda: vp),
                  mock.patch.object(server, "SPOKEN", type(server.SPOKEN)(maxlen=200))):
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(ears(server, lambda pcm: self.heard).close)

    def listen(self, heard):
        """Run one Listen session that Whisper hears as `heard`. → what it logged to stderr."""
        self.heard = heard
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            server.Listen("ptt").run(lambda **k: None)
        return err.getvalue()

    # ---- only a request in words enrols
    def test_a_request_in_words_enrols_once(self):
        self.listen(REQUEST)
        self.assertEqual(len(self.enrolled), 1, "a request in words was not enrolled exactly once")

    def test_an_empty_transcript_enrols_nothing(self):
        for heard in ("", "  "):
            with self.subTest(heard=heard):
                self.enrolled.clear()
                self.listen(heard)
                self.assertEqual(len(self.enrolled), 0, f"enrolled a recording heard as {heard!r}")

    def test_noise_and_filler_enrol_nothing(self):
        # A sentence Whisper hallucinates and repeats on room sound is still noise.
        for heard in ("Thank you.", "Thanks for watching!", "Um.", "Uh", "Hmm.",
                      "The two of them were the two of them. The two of them were the two of them."):
            with self.subTest(heard=heard):
                self.enrolled.clear()
                self.listen(heard)
                self.assertEqual(len(self.enrolled), 0, f"enrolled a recording heard as {heard!r}")

    def test_a_short_real_phrase_he_repeats_is_him_speaking(self):
        for heard in ("Not yet, not yet.", "Go. Go. Go."):
            with self.subTest(heard=heard):
                self.enrolled.clear()
                self.listen(heard)
                self.assertEqual(len(self.enrolled), 1, f"a short real phrase heard as {heard!r} was not enrolled once")

    def test_an_echo_of_his_own_voice_enrols_nothing(self):
        said = "The build finished and all forty tests passed on the first run."
        server.SPOKEN.append((time.monotonic(), said))
        self.listen(said)
        self.assertEqual(len(self.enrolled), 0, "enrolled an echo of his own voice")

    # ---- only the speech is embedded
    def test_only_the_speech_is_enrolled_without_lead_in_or_chime(self):
        self.listen(REQUEST)
        self.assertEqual(len(self.enrolled), 1, "a request in words was not enrolled exactly once")
        clip = bytes(self.enrolled[0])
        lead = sum(1 for p in pieces(self.rec.lead_in, 20) if p in clip)
        self.assertEqual(lead, 0, f"{lead * 20} ms of the lead-in silence went into the voiceprint")
        ring = sum(1 for p in pieces(self.rec.chime, 20) if p in clip)
        self.assertEqual(ring, 0, f"{ring * 20} ms of the chime went into the voiceprint")
        spoken = pieces(self.rec.speech, 20)
        kept = sum(1 for p in spoken if p in clip)
        self.assertGreaterEqual(kept / len(spoken), 0.8, f"only {kept} of {len(spoken)} 20 ms pieces of your speech "
                                                         "went into the voiceprint")

    # ---- each enrolment logs one line
    def test_each_enrolment_logs_one_line_saying_what_was_enrolled(self):
        log = self.listen(REQUEST)
        self.assertEqual(len(self.enrolled), 1, "a request in words was not enrolled exactly once")
        lines = [ln for ln in log.splitlines() if re.search(r"enrol", ln, re.I)]
        self.assertEqual(len(lines), 1, f"enrolment logged {len(lines)} lines, not one: {log!r}")
        secs = len(self.enrolled[0]) / (SR * 2)
        says_text = "that's not what i asked" in lines[0].lower()
        says_secs = any(abs(float(x) - secs) <= 0.1 for x in re.findall(r"(\d+(?:\.\d+)?)\s*s\b", lines[0]))
        self.assertTrue(says_text or says_secs, f"the enrolment line doesn't say what was enrolled: {lines[0]!r}")

    # ---- every recording is kept or dropped by gate.judge, and its verdict logged in one line
    def run_listen(self, heard):
        """One Listen session heard as `heard`. → (the events it emitted, its '[void]' log lines)."""
        self.heard = heard
        events, err = [], io.StringIO()
        with contextlib.redirect_stderr(err):
            server.Listen("ptt").run(lambda **k: events.append(k))
        return events, [ln for ln in err.getvalue().splitlines() if ln.startswith("[void]")]

    @staticmethod
    def verdicts(log):
        """The verdict lines in `log`: '[void] <why>' (any reason gate.WHY names, maybe a note in brackets), ': ', said."""
        return [(w, ln) for ln in log for w in gate.WHY if re.match(rf"\[void\] {re.escape(w)}(?: \([^)]*\))?: ", ln)]

    @staticmethod
    def sent(events):
        """What the recording sent on as a request: every 'text' event with words in it."""
        return [e for e in events if e.get("t") == "text" and (e.get("text") or "").strip()]

    def test_a_recording_is_judged_once_as_a_listen_burst(self):
        calls, real = [], gate.judge
        with mock.patch.object(gate, "judge", lambda *a, **k: calls.append(a) or real(*a, **k)):
            self.run_listen(REQUEST)
        self.assertEqual(len(calls), 1, f"gate.judge called {len(calls)}x on one Listen recording")
        b = calls[0][0]
        self.assertIsInstance(b, gate.Burst, f"gate.judge not handed a gate.Burst: {b!r}")
        self.assertEqual((b.kind, b.text, b.voice), ("listen", REQUEST, None),
                         f"not judged as an unscored 'listen' burst of what Whisper heard: {b!r}")

    def test_a_kept_request_is_sent_and_logs_one_kept_line(self):
        events, log = self.run_listen(REQUEST)
        self.assertEqual([e["text"] for e in self.sent(events)], [REQUEST], f"the request wasn't sent on once: {events}")
        got = self.verdicts(log)
        self.assertEqual(len(got), 1, f"{len(got)} verdict lines, not one:\n" + "\n".join(log))
        self.assertEqual(got[0][0], "kept", f"a request in words not logged as kept: {got[0][1]!r}")
        self.assertIn("that's not what i asked", got[0][1].lower(), f"the verdict line doesn't say what was heard: {got[0][1]!r}")

    def test_noise_and_filler_are_dropped_not_sent(self):
        for heard in ("Thank you.", "Um.", "The two of them were the two of them. The two of them were the two of them."):
            with self.subTest(heard=heard):
                events, log = self.run_listen(heard)
                self.assertEqual(self.sent(events), [], f"a recording heard as {heard!r} was sent on as a request")
                got = self.verdicts(log)
                self.assertEqual([w for w, _ in got], ["noise"], f"{heard!r} not logged as one noise verdict:\n"
                                 + "\n".join(log))

    def test_an_echo_of_his_own_voice_is_dropped_and_logged_as_echo(self):
        said = "The build finished and all forty tests passed on the first run."
        server.SPOKEN.append((time.monotonic(), said))
        events, log = self.run_listen(said)
        self.assertEqual(self.sent(events), [], "an echo of his own voice was sent on as a request")
        got = self.verdicts(log)
        self.assertEqual([w for w, _ in got], ["echo"], "the echo not logged as one echo verdict:\n" + "\n".join(log))

    def test_a_recording_with_too_little_speech_is_dropped_untranscribed(self):
        whispered = []
        with ears(server, lambda pcm: whispered.append(pcm) or REQUEST, speech_for=lambda pcm: 0.1):
            events, log = self.run_listen(REQUEST)
        self.assertEqual(self.sent(events), [], "a push-to-talk recording with 0.1 s of speech was sent on as a request")
        self.assertEqual(whispered, [], "a recording with too little speech was still sent to Whisper")
        got = self.verdicts(log)
        self.assertEqual([w for w, _ in got], ["no speech"], "not logged as one 'no speech' verdict:\n" + "\n".join(log))

    def test_nothing_enrolled_logs_no_enrolment(self):
        log = self.listen("Um.")
        self.assertEqual([ln for ln in log.splitlines() if re.search(r"\benrolled\b", ln, re.I)], [],
                         f"logged an enrolment for a filler: {log!r}")


if __name__ == "__main__":
    unittest.main()
