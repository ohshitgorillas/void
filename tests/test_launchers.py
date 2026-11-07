"""The launchers start their own server and never attach to another Void's that happens to hold their port.

    python3 -m unittest discover tests
"""
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(HERE))
import launch_win  # noqa: E402
from loopback_http import LoopbackThreadingHTTPServer  # noqa: E402

# a stand-in for app/server.py: the same port rule, runtime.json and /api/state and /api/id answers, nothing else. Like the real
# one with the mic waiting on Core Audio, the full state (with the window's token) doesn't answer for a long while.
FAKE_SERVER = (HERE / "loopback_http.py").read_text() + r'''
import json, os, secrets, signal, sys, time
from http.server import BaseHTTPRequestHandler
PORT = int(os.environ["FAKE_PORT"])
if "--print-port" in sys.argv:
    print(PORT); sys.exit()
signal.alarm(30)                                   # never outlives the test, whatever happens to it
data = os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"), "void")
tok, rid = secrets.token_urlsafe(24), secrets.token_hex(8)
old = {} if os.environ.get("FAKE_OLD") else {"id": rid}    # FAKE_OLD: a server from before run ids

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.headers.get("X-Void-Token") == tok:
            time.sleep(20)
        if self.path == "/api/id" and not old:     # (a server from before run ids has no /api/id)
            self.send_response(404); self.end_headers(); return
        body = json.dumps(old if self.path == "/api/id" else {"version": "0"}).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers()
        self.wfile.write(body)
    def log_message(self, *a): pass

srv = LoopbackThreadingHTTPServer(("127.0.0.1", PORT), H)     # (port taken → dies here, like the real one)
os.makedirs(data, exist_ok=True)
open(os.path.join(data, "server.pid"), "w").write(str(os.getpid()))
json.dump({"port": PORT, "token": tok, "tool_token": "t", **old}, open(os.path.join(data, "runtime.json"), "w"))
srv.serve_forever()
'''
FAKE_WINDOW = r'''
import os, sys
open(os.path.join(os.environ["XDG_DATA_HOME"], "window.args"), "w").write(" ".join(sys.argv[1:]))
'''


KEEP_LOGS = "VOID_TEST_LOGS"            # a directory the CI workflow names; a failed start copies its logs there
TAIL = 3000


class Logs:
    """The failure message of a start that didn't happen: the tail of each log that bears on it. Built only when the
    assertion fails (unittest formats `msg` then), and then, with KEEP_LOGS set, copies each log whole into that
    directory under the test's id before cleanup deletes self.tmp."""

    def __init__(self, test, head, *paths):
        self.test, self.head, self.paths = test, head, paths

    def __str__(self):
        keep = os.environ.get(KEEP_LOGS)
        out = [str(self.head)] if self.head else []
        for p in map(Path, self.paths):
            try:
                raw = p.read_bytes()
            except OSError:
                out.append(f"--- {p.name}: not written")
                continue
            if keep:
                os.makedirs(keep, exist_ok=True)
                (Path(keep) / f"{self.test.id()}.{'_'.join(p.relative_to(self.test.tmp).parts)}").write_bytes(raw)
            out.append(f"--- {p.name} (last {TAIL} bytes):\n" + raw[-TAIL:].decode(errors="replace"))
        return "\n".join(out)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Launchers(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.port = free_port()
        self.pids = []
        self.extra = {}
        self.addCleanup(self.kill_servers)

    def kill_servers(self):
        for pid in self.pids:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

    def env(self, home):
        return {"HOME": str(home), "XDG_DATA_HOME": str(home / "data"), "PATH": "/usr/bin:/bin",
                "FAKE_PORT": str(self.port), **self.extra}

    def fake_app(self, app):
        app.mkdir(parents=True)
        (app / "server.py").write_text(FAKE_SERVER)
        (app / "window_win.py").write_text(FAKE_WINDOW)

    def mac_bundle(self):
        """A Void.app with the real launcher, a link to this python and the fake app."""
        c = self.tmp / "Void.app" / "Contents"
        (c / "MacOS").mkdir(parents=True)
        shutil.copy(ROOT / "packaging/macos/launcher", c / "MacOS/Void")
        (c / "Resources/python/bin").mkdir(parents=True)
        (c / "Resources/python/bin/python3").symlink_to(sys.executable)
        self.fake_app(c / "Resources/app")
        return c / "MacOS/Void"

    def home_install(self):
        """bin/void with its app and venv in ~/.local/share/void, as install.sh lays them out."""
        void = self.tmp / "home/data/void"
        self.fake_app(void / "app")
        (void / "venv/bin").mkdir(parents=True)
        (void / "venv/bin/python").symlink_to(sys.executable)
        (self.tmp / "bin").mkdir()
        shutil.copy(ROOT / "bin/void", self.tmp / "bin/void")
        return self.tmp / "bin/void"

    def foreign_server(self):
        """Another Void (its own data folder) already serving on our port."""
        home = self.tmp / "other"
        self.fake_app(home / "app")
        log = home / "fake-server.log"
        with open(log, "wb") as out:
            p = subprocess.Popen([sys.executable, str(home / "app/server.py")], env=self.env(home),
                                 stdout=out, stderr=subprocess.STDOUT)
        self.pids.append(p.pid)
        rt = home / "data/void/runtime.json"
        for _ in range(50):
            if rt.exists():
                return
            time.sleep(0.1)
        self.fail(str(Logs(self, "the foreign fake server didn't start", log)))

    def launch(self, launcher):
        r = subprocess.run([str(launcher), "show"], env=self.env(self.tmp / "home"), capture_output=True, text=True,
                           timeout=30)
        pidf = self.tmp / "home/data/void/server.pid"
        if pidf.exists():
            self.pids.append(int(pidf.read_text()))
        args = self.tmp / "home/data/window.args"
        for _ in range(30):                                  # (bin/void hands the window off in the background)
            if args.exists():
                break
            time.sleep(0.1)
        return r, args

    def check_own_server(self, launcher):
        r, args = self.launch(launcher)
        mine = self.tmp / "home/data/void/server.log"
        self.assertEqual(r.returncode, 0, Logs(self, r.stderr, mine))
        self.assertTrue((self.tmp / "home/data/void/server.pid").exists(),
                        Logs(self, "it didn't start its own server", mine))
        self.assertIn(f"http://127.0.0.1:{self.port}/?native=1", args.read_text())

    def check_never_attaches(self, launcher):
        self.foreign_server()
        r, args = self.launch(launcher)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("server didn't start", r.stderr)
        self.assertFalse(args.exists(), "it opened a window on another Void's server")

    def test_mac_bundle_starts_its_own_server(self):
        self.check_own_server(self.mac_bundle())

    def test_mac_bundle_never_attaches_to_another_void(self):
        self.check_never_attaches(self.mac_bundle())

    def test_bin_void_starts_its_own_server(self):
        self.check_own_server(self.home_install())

    def test_bin_void_never_attaches_to_another_void(self):
        self.check_never_attaches(self.home_install())

    def test_mac_bundle_takes_its_older_server_from_before_an_update(self):
        self.extra = {"FAKE_OLD": "1"}
        self.check_own_server(self.mac_bundle())

    def test_bin_void_takes_its_older_server_from_before_an_update(self):
        self.extra = {"FAKE_OLD": "1"}
        self.check_own_server(self.home_install())


class WindowsLauncherUp(unittest.TestCase):
    """launch_win.up(): the same rule as the shell launchers, in Python."""

    def setUp(self):
        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                body = json.dumps({"version": "0", "id": "0123abcd"}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        srv = LoopbackThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        url = f"http://127.0.0.1:{srv.server_address[1]}/"
        for p in (mock.patch.object(launch_win, "URL", url), mock.patch.object(launch_win, "DATA", self.tmp)):
            p.start()
            self.addCleanup(p.stop)

    def runtime(self, **rid):
        (self.tmp / "runtime.json").write_text(json.dumps({"port": 0, "token": "x", "tool_token": "t", **rid}))

    def test_up_when_its_own_server_answers(self):
        self.runtime(id="0123abcd")
        self.assertTrue(launch_win.up())

    def test_not_up_when_another_void_answers(self):
        self.runtime(id="ffff0000")
        self.assertFalse(launch_win.up())

    def test_up_for_its_older_server_from_before_an_update(self):
        self.runtime()
        self.assertTrue(launch_win.up())

    def test_not_up_without_runtime_json(self):
        self.assertFalse(launch_win.up())


if __name__ == "__main__":
    unittest.main()
