"""A helper (Agent / Task tool call) shows as its own little Void and never brings up his terminal; every other tool does.

    python3 -m unittest discover -s tests
"""
import re
import unittest
from pathlib import Path

PAGE = (Path(__file__).resolve().parent.parent / "app" / "static" / "index.html").read_text(encoding="utf-8")


class HelperNeverOpensTerminal(unittest.TestCase):
    def test_terminal_skips_exactly_agent_and_task(self):
        m = re.search(r"NO_TERMINAL=new Set\(\[([^\]]*)\]\)", PAGE)
        self.assertTrue(m)
        self.assertEqual(set(re.findall(r"'([^']+)'", m.group(1))), {"Agent", "Task"})

    def test_tool_entry_checks_it_before_queueing(self):
        m = re.search(r"\n    tool\(ev\)\{([^\n]*)", PAGE)
        self.assertTrue(m)
        body = m.group(1)
        self.assertLess(body.index("NO_TERMINAL.has(ev.name)"), body.index("q.push(ev)"))

    def test_other_views_still_there(self):
        for v in ("Bash", "Edit", "Write", "Read", "Grep"):
            self.assertIn(f"async {v}(ev)", PAGE)

    def test_page_still_counts_helper_as_a_tool(self):
        self.assertIn("case 'tool': tools++;", PAGE)       # chips / mood unchanged; only the terminal skips it


if __name__ == "__main__":
    unittest.main()
