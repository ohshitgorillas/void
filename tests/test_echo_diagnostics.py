"""`void doctor` and the 'Copy diagnostics' report say whether the echo canceller is on, off by the setting, or
unavailable and why.

    python3 -m unittest tests.test_echo_diagnostics -v
"""
import contextlib
import io
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import suite_data  # noqa: E402  (Void's data folder: the suite's own, set before server.py settles it)

try:
    import server
except Exception as e:  # noqa: BLE001
    server, IMPORT_ERR = None, e
else:
    IMPORT_ERR = None

NO_LIVEKIT = "No module named 'livekit'"
NO_START = "AEC3 refused to initialise"


def echo_lines(text):
    return [ln for ln in text.splitlines() if "echo" in ln.lower()]


@unittest.skipIf(server is None, f"server.py doesn't import here: {IMPORT_ERR}")
class EchoReport(unittest.TestCase):
    """Each surface is run with the canceller in one of its three states; what it prints is read back."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        said = set(server.hearing.Canceller.said)
        self.addCleanup(lambda: (server.hearing.Canceller.said.clear(), server.hearing.Canceller.said.update(said)))
        for p in (mock.patch.object(server, "DATA_DIR", Path(tmp.name)),
                  mock.patch.object(server, "claude_bin", lambda: None),
                  mock.patch.object(server, "tts_engine", lambda: None),
                  mock.patch.object(server, "WIN", False),
                  mock.patch.object(server, "OSYS", None),
                  mock.patch.object(server, "mic_cmds", lambda: []),
                  mock.patch.object(server, "open_mic", mock.Mock(side_effect=RuntimeError("no mic in tests"))),
                  mock.patch.object(server.shutil, "which", lambda *a, **k: None)):
            p.start()
            self.addCleanup(p.stop)

    def state(self, setting, rtc, err=None):
        """echo_cancel = setting; livekit's rtc module is `rtc` (None: it didn't import, with `err`)."""
        for p in (mock.patch.dict(server.CFG, {"echo_cancel": setting}),
                  mock.patch.object(server.hearing, "rtc", rtc),
                  mock.patch.object(server.hearing, "RTC_ERR", err)):
            p.start()
            self.addCleanup(p.stop)

    def working_rtc(self):
        return mock.Mock()

    def broken_rtc(self):
        rtc = mock.Mock()
        rtc.AudioProcessingModule.side_effect = RuntimeError(NO_START)
        return rtc

    def doctor_text(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            server.doctor()
        return out.getvalue()

    def diagnostics_text(self):
        with contextlib.redirect_stderr(io.StringIO()):
            return server.diagnostics()

    # --- the three states, checked the same way on either surface

    def check_on(self, text):
        lines = echo_lines(text)
        self.assertTrue(lines, f"nothing about the echo canceller in:\n{text}")
        self.assertTrue(any(re.search(r"\bon\b", ln) and not re.search(r"\boff\b|unavailable|\bnot\b", ln, re.I)
                            for ln in lines), f"doesn't say the echo canceller is on: {lines}")

    def check_off(self, text):
        lines = echo_lines(text)
        self.assertTrue(lines, f"nothing about the echo canceller in:\n{text}")
        self.assertTrue(any(re.search(r"\boff\b", ln) and ("echo_cancel" in ln or "setting" in ln.lower())
                            for ln in lines), f"doesn't say it's off by the echo_cancel setting: {lines}")

    def check_unavailable(self, text, why):
        lines = echo_lines(text)
        self.assertTrue(lines, f"nothing about the echo canceller in:\n{text}")
        self.assertTrue(any(why in ln for ln in lines), f"doesn't say it's unavailable because {why!r}: {lines}")

    # --- `void doctor`

    def test_doctor_says_on(self):
        self.state(True, self.working_rtc())
        self.check_on(self.doctor_text())

    def test_doctor_says_off_by_the_setting(self):
        self.state(False, self.working_rtc())
        self.check_off(self.doctor_text())

    def test_doctor_says_unavailable_and_why(self):
        with self.subTest("livekit doesn't load"):
            self.state(True, None, ImportError(NO_LIVEKIT))
            self.check_unavailable(self.doctor_text(), NO_LIVEKIT)
        with self.subTest("livekit's canceller doesn't start"):
            self.state(True, self.broken_rtc())
            self.check_unavailable(self.doctor_text(), NO_START)

    # --- diagnostics() ('Copy diagnostics')

    def test_diagnostics_says_on(self):
        self.state(True, self.working_rtc())
        self.check_on(self.diagnostics_text())

    def test_diagnostics_says_off_by_the_setting(self):
        self.state(False, self.working_rtc())
        self.check_off(self.diagnostics_text())

    def test_diagnostics_says_unavailable_and_why(self):
        with self.subTest("livekit doesn't load"):
            self.state(True, None, ImportError(NO_LIVEKIT))
            self.check_unavailable(self.diagnostics_text(), NO_LIVEKIT)
        with self.subTest("livekit's canceller doesn't start"):
            self.state(True, self.broken_rtc())
            self.check_unavailable(self.diagnostics_text(), NO_START)


if __name__ == "__main__":
    unittest.main()
