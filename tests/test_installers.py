"""livekit (the echo canceller) is installed by every installer, the way each installs its other
Python packages, and a missing livekit never fails an install: Void runs without it, uncancelled."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# installer -> the command it uses to install Python packages
INSTALLERS = {
    "install.sh": r"uv pip install\b",
    "install.ps1": r"RunUv pip install\b",
    "packaging/macos/build.sh": r"uv pip install\b",
}


def lines_of(rel):
    return (ROOT / rel).read_text().splitlines()


def livekit_install_index(rel):
    """Index of the line that installs livekit with this installer's own install command, or None."""
    pat = re.compile(INSTALLERS[rel] + r".*\blivekit\b(?!-)")
    for i, line in enumerate(lines_of(rel)):
        if not line.lstrip().startswith("#") and pat.search(line):
            return i
    return None


class LivekitInstalled(unittest.TestCase):
    def test_every_installer_installs_livekit_its_usual_way(self):
        for rel in INSTALLERS:
            with self.subTest(installer=rel):
                self.assertIsNotNone(livekit_install_index(rel),
                                     f"{rel} does not install livekit")

    def test_livekit_shares_a_line_with_no_other_required_package(self):
        # one install line carrying livekit and, say, PySide6 would take PySide6 down with it
        for rel in INSTALLERS:
            with self.subTest(installer=rel):
                i = livekit_install_index(rel)
                self.assertIsNotNone(i, f"{rel} does not install livekit")
                line = lines_of(rel)[i]
                for other in ("faster-whisper", "pillow", "PySide6", "sounddevice",
                              "piper-tts", "kokoro-onnx", "pycaw", "comtypes"):
                    self.assertNotIn(other, line, f"{rel}: livekit is installed together with {other}")

    def test_a_failed_livekit_install_does_not_fail_the_install(self):
        for rel in INSTALLERS:
            with self.subTest(installer=rel):
                i = livekit_install_index(rel)
                self.assertIsNotNone(i, f"{rel} does not install livekit")
                lines = lines_of(rel)
                line = lines[i]
                nxt = lines[i + 1] if i + 1 < len(lines) else ""
                if rel.endswith(".ps1"):
                    # RunUv leaves its result in $LASTEXITCODE; it must be checked and only warned on
                    ok = "LASTEXITCODE" in (line + nxt) and "Warn" in (line + nxt)
                else:
                    # set -e: the install is an if-condition or is followed by || (warn / true)
                    ok = "||" in line or "||" in nxt or re.match(r"\s*(if|elif)\b", line) is not None
                self.assertTrue(ok, f"{rel}: a failing livekit install is not made harmless: {line.strip()}")


if __name__ == "__main__":
    unittest.main()
