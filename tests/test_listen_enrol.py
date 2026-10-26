"""Listen.run teaches the voiceprint only from a request in words: a recording that came back empty, as noise, as a
stock filler, or as an echo of his own voice enrols nothing. What is enrolled is the recording's speech alone, without
the lead-in silence and the chime before it, and each enrolment logs one line saying what was enrolled.

The mic is a fake that plays one recording (a lead-in of room hiss, a chime, then a real clip of you) and Whisper is
replaced by what it "hears", so the tests need neither a microphone nor the speech model.

    python3 -m unittest tests.test_listen_enrol -v
"""
import contextlib
import io
import math
import random
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


def hiss(seconds, seed):
    rnd = random.Random(seed)
    return s16(rnd.gauss(0.0, 0.003) for _ in range(int(seconds * SR)))


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


def pieces(pcm, ms):
    """Every `ms`-long piece of `pcm`, back to back."""
    n = SR * 2 * ms // 1000
    return [pcm[i:i + n] for i in range(0, len(pcm) - n + 1, n)]


@unittest.skipIf(server is None, f"server.py doesn't import here: {SERVER_ERR}")
class ListenEnrolTest(unittest.TestCase):

    def setUp(self):
        self.rec = Recording()
        self.enrolled = []
        vp = types.SimpleNamespace(available=True, enrolled=0, enroll=self.enrolled.append)
        self.heard = REQUEST
        for p in (mock.patch.object(server, "open_clean_mic", lambda: (FakeMic(self.rec.pcm), "fake mic", b"")),
                  mock.patch.object(server, "run_whisper_heard", lambda *a, **k: server.Heard(
                      text=self.heard, logprob=-0.2, no_speech=0.05, seconds=2.0)),
                  mock.patch.object(server.MicAuto, "learn", lambda pcm: None),
                  mock.patch.object(server.Voice, "get", lambda: vp),
                  mock.patch.object(server, "SPOKEN", type(server.SPOKEN)(maxlen=200))):
            p.start()
            self.addCleanup(p.stop)

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
        for heard in ("Thank you.", "Thanks for watching!", "Um.", "Uh", "Hmm.", "Go. Go. Go."):
            with self.subTest(heard=heard):
                self.enrolled.clear()
                self.listen(heard)
                self.assertEqual(len(self.enrolled), 0, f"enrolled a recording heard as {heard!r}")

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

    def test_nothing_enrolled_logs_no_enrolment(self):
        log = self.listen("Um.")
        self.assertEqual([ln for ln in log.splitlines() if re.search(r"\benrolled\b", ln, re.I)], [],
                         f"logged an enrolment for a filler: {log!r}")


if __name__ == "__main__":
    unittest.main()
