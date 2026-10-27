"""No test writes Void's real data folder (~/.local/share/void). The suite as a whole keeps the app's data folder, and
with it the owner's memory (MEM_PATH), somewhere of its own, whichever module first imports app/server.py.

The suite is loaded here the way it is run, from the owner's own environment, in a fresh interpreter; loading imports
the test modules (and app/server.py with them) without running a single test, so nothing is written by this check.

    python3 -m unittest discover -s tests
"""
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PROBE = r"""
import json, sys, unittest
unittest.defaultTestLoader.discover(start_dir="tests", pattern=sys.argv[1])
server = sys.modules.get("server")
print(json.dumps(None if server is None else {"DATA_DIR": str(server.DATA_DIR), "memory": str(server.MEM_PATH)}))
"""


def real_data_dir() -> Path:
    """The owner's real Void data folder, from the account's own home (not $HOME, which a test may have moved)."""
    import pwd
    return Path(pwd.getpwuid(os.getuid()).pw_dir) / ".local" / "share" / "void"


@unittest.skipIf(os.name == "nt", "the ~/.local/share/void data folder is the macOS and Linux one")
class SuiteDataDir(unittest.TestCase):
    def loaded_paths(self, pattern):
        """Load the suite (only the modules matching `pattern`) as the owner's shell would, → where server.py's data
        folder and memory resolved to."""
        env = {k: v for k, v in os.environ.items() if k not in ("XDG_DATA_HOME", "XDG_CONFIG_HOME")}
        env["HOME"] = str(real_data_dir().parent.parent.parent)
        out = subprocess.run([sys.executable, "-c", PROBE, pattern], cwd=ROOT, env=env, capture_output=True,
                             text=True, timeout=120)
        self.assertEqual(out.returncode, 0, out.stderr[-2000:])
        paths = json.loads(out.stdout.strip().splitlines()[-1])
        self.assertIsNotNone(paths, f"no test module matching {pattern} imported app/server.py")
        return paths

    def test_the_echo_tests_keep_the_owners_memory_out_of_the_real_data_folder(self):
        real = real_data_dir().resolve()
        for name, p in self.loaded_paths("test_echo.py").items():
            with self.subTest(name):
                self.assertFalse(Path(p).resolve().is_relative_to(real),
                                 f"under the suite, server.py's {name} is in the real data folder: {p}")


if __name__ == "__main__":
    unittest.main()
