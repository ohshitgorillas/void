"""The voice prompt tells the main session to run long jobs as detached claude -p processes that report with claude-ping."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import suite_data  # noqa: E402  (Void's data folder: the suite's own, set before server.py settles it)
import server


class VoicePrompt(unittest.TestCase):
    def test_long_jobs_run_detached_and_report_with_claude_ping(self):
        prompt = server.DEFAULTS["voice_prompt"]
        self.assertIn("claude -p", prompt)
        self.assertIn("claude-ping", prompt)
        self.assertIn("detached", prompt.lower())
        self.assertIn("subagent", prompt.lower())


if __name__ == "__main__":
    unittest.main()
