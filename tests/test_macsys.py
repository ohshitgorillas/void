"""app/macsys.py: what Void does to the Mac (volume, music, apps, lock, notifications, clipboard, screenshots), checked
at the process boundary. Every test replaces `subprocess` (and `threading.Thread` where macsys starts one) before it
calls anything, so no test locks the screen, changes the volume, opens an app, posts a notification, sets the
clipboard or takes a screenshot of the machine running it. The Cocoa window calls are tests/test_window_mac.py's.

    python3 -m unittest tests.test_macsys -v
"""
import ctypes
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "app"))

MAC = sys.platform == "darwin"
if MAC:
    import macsys  # noqa: E402


class Sealed(unittest.TestCase):
    """Nothing started here reaches the machine: any process a test did not stand in for fails it."""

    def setUp(self):
        for target, name in ((macsys.subprocess, "run"), (macsys.subprocess, "Popen")):
            p = mock.patch.object(target, name, side_effect=AssertionError(f"a real subprocess.{name} was started"))
            p.start()
            self.addCleanup(p.stop)

    def patch(self, name, *a, **kw):
        p = mock.patch.object(macsys, name, *a, **kw)
        m = p.start()
        self.addCleanup(p.stop)
        return m

    def sends(self, **replies):
        s = Sends(replies)
        self.patch("_send", new=s)
        return s

    def tmp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        return Path(d.name)


def done(returncode=0, stdout=""):
    return SimpleNamespace(returncode=returncode, stdout=stdout)


@unittest.skipUnless(MAC, "macOS only")
class Running(Sealed):
    def test_a_command_that_succeeds_gives_its_trimmed_output(self):
        with mock.patch.object(macsys.subprocess, "run", return_value=done(0, "  hello \n")) as run:
            self.assertEqual(macsys._run(["tool", "a"], timeout=4), (True, "hello"))
        args, kw = run.call_args
        self.assertEqual(args[0], ["tool", "a"])
        self.assertEqual(kw["timeout"], 4)
        self.assertEqual(kw["env"]["LANG"], "en_US.UTF-8")          # (no LANG → pbpaste hands back MacRoman)

    def test_a_failing_command_is_not_ok_and_one_that_cannot_run_says_why(self):
        for result, want in ((done(1, "no"), (False, "no")), (done(0, None), (True, ""))):
            with mock.patch.object(macsys.subprocess, "run", return_value=result):
                self.assertEqual(macsys._run(["x"]), want)
        for err in (FileNotFoundError("no such tool"), subprocess.TimeoutExpired(["x"], 1)):
            with mock.patch.object(macsys.subprocess, "run", side_effect=err):
                self.assertEqual(macsys._run(["x"]), (False, str(err)))

    def test_applescript_is_wrapped_in_a_handler_and_its_arguments_ride_along_as_argv(self):
        run = self.patch("_run", return_value=(True, "r"))
        self.assertEqual(macsys.osa("\n  line one\nline two\n", "a b", 7, timeout=3), (True, "r"))
        run.assert_called_once_with(["osascript", "-e", "on run argv", "-e", "line one", "-e", "line two",
                                     "-e", "end run", "a b", "7"], timeout=3)


@unittest.skipUnless(MAC, "macOS only")
class Folders(Sealed):
    def test_each_folder_follows_its_xdg_variable_and_falls_back_to_the_home_one(self):
        for fn, var, home in ((macsys.data_dir, "XDG_DATA_HOME", ".local/share"),
                              (macsys.config_dir, "XDG_CONFIG_HOME", ".config"),
                              (macsys.cache_dir, "XDG_CACHE_HOME", ".cache")):
            with mock.patch.dict(os.environ, {var: "/elsewhere"}):
                self.assertEqual(fn(), Path("/elsewhere/void"))
            env = {k: v for k, v in os.environ.items() if k != var}
            with mock.patch.dict(os.environ, env, clear=True):
                self.assertEqual(fn(), Path.home() / home / "void")
            with mock.patch.dict(os.environ, {var: ""}):          # (set but empty is unset)
                self.assertEqual(fn(), Path.home() / home / "void")

    def test_the_launcher_of_the_app_bundle_a_folder_is_inside(self):
        root = self.tmp()
        res = root / "Void.app" / "Contents" / "Resources" / "app"
        res.mkdir(parents=True)
        self.assertIsNone(macsys.bundle_launcher(res))             # the bundle has no launcher yet
        launcher = root / "Void.app" / "Contents" / "MacOS" / "Void"
        launcher.parent.mkdir(parents=True)
        launcher.write_text("#!/bin/sh\n")
        self.assertEqual(macsys.bundle_launcher(res), str(launcher))
        self.assertIsNone(macsys.bundle_launcher(root / "checkout" / "app"))


@unittest.skipUnless(MAC, "macOS only")
class CoreAudioAsks(Sealed):
    def test_a_device_list_core_audio_will_not_give_is_an_error_naming_it(self):
        ca = self.patch("_ca")
        ca.AudioObjectGetPropertyDataSize.return_value = 1         # it won't even say how big the list is
        with self.assertRaisesRegex(OSError, r"Core Audio won't say \(dOut\)"):
            macsys._ca_ids("dOut")
        ca.AudioObjectGetPropertyDataSize.return_value = 0
        ca.AudioObjectGetPropertyData.return_value = 1             # …or the list itself
        with self.assertRaisesRegex(OSError, r"Core Audio won't say \(dIn \)"):
            macsys._ca_ids("dIn ")


@unittest.skipUnless(MAC, "macOS only")
class MicLevel(Sealed):
    def test_the_mic_level_is_left_to_void_himself(self):
        self.assertIsNone(macsys.mic_level("any mic"))
        self.assertFalse(macsys.set_mic_level(0.5, "any mic"))


@unittest.skipUnless(MAC, "macOS only")
class Windows(Sealed):
    def front(self, ok, out):
        return self.patch("osa", return_value=(ok, out))

    def test_the_front_window_is_x_y_w_h_in_points(self):
        osa = self.front(True, "10,20.7,800,600")
        self.assertEqual(macsys.active_window(), (10, 20, 800, 600))
        self.assertEqual(osa.call_args.kwargs, {"timeout": 3})
        self.assertIn('"Void"', osa.call_args.args[0])             # (his own window is never the answer)

    def test_no_window_when_it_is_void_when_macos_will_not_say_or_when_it_is_a_sliver(self):
        for ok, out in ((True, ""), (False, "boom"), (True, "1,2,3"), (True, "10,20,15,600"), (True, "10,20,800,15"),
                        (False, "10,20,800,600")):
            self.front(ok, out)
            self.assertIsNone(macsys.active_window(), (ok, out))


@unittest.skipUnless(MAC, "macOS only")
class Screenshots(Sealed):
    def shoot(self, kind, active=None, ok=True, err="", write=True):
        out = self.tmp() / "shot.png"
        cmds = []

        def run(cmd, timeout=10):
            cmds.append((cmd, timeout))
            if write:
                out.write_bytes(b"png")
            return ok, err
        self.patch("_run", side_effect=run)
        self.patch("active_window", return_value=active)
        return out, cmds

    def test_a_region_is_dragged_out_and_esc_cancels(self):
        out, cmds = self.shoot("region")
        self.assertEqual(macsys.screenshot("region", out), "region")
        self.assertEqual(cmds, [(["screencapture", "-x", "-i", str(out)], 120)])
        out, _ = self.shoot("region", write=False)
        with self.assertRaisesRegex(RuntimeError, "cancelled"):
            macsys.screenshot("region", out)

    def test_a_window_is_captured_by_its_rectangle_and_falls_back_to_the_screen(self):
        out, cmds = self.shoot("window", active=(1, 2, 300, 400))
        self.assertEqual(macsys.screenshot("window", out), "window")
        self.assertEqual(cmds[0][0], ["screencapture", "-x", "-R1,2,300,400", str(out)])
        out, cmds = self.shoot("window", active=None)
        self.assertEqual(macsys.screenshot("window", out), "screen")
        self.assertEqual(cmds[0][0], ["screencapture", "-x", "-m", str(out)])

    def test_a_screen_shot_never_asks_which_window_is_in_front(self):
        out, cmds = self.shoot("screen", active=(1, 2, 300, 400))
        self.assertEqual(macsys.screenshot("screen", out), "screen")
        self.assertEqual(cmds[0], (["screencapture", "-x", "-m", str(out)], 30))
        macsys.active_window.assert_not_called()

    def test_a_failed_capture_points_at_the_screen_recording_permission(self):
        out, _ = self.shoot("screen", ok=False, err="x" * 300 + "denied", write=False)
        with self.assertRaises(RuntimeError) as cm:
            macsys.screenshot("screen", out)
        self.assertIn("Screen Recording", str(cm.exception))
        self.assertTrue(str(cm.exception).endswith("x" * 154 + "denied"))     # (the last 160 characters of the error)


@unittest.skipUnless(MAC, "macOS only")
class Clipboard(Sealed):
    def grab(self, value=None, error=None):
        from PIL import ImageGrab
        p = mock.patch.object(ImageGrab, "grabclipboard", return_value=value, side_effect=error)
        p.start()
        self.addCleanup(p.stop)

    def test_a_copied_picture_is_saved_where_asked(self):
        from PIL import Image
        out = self.tmp() / "clip.png"
        self.grab(Image.new("RGB", (2, 2), "red"))
        self.assertEqual(macsys.clipboard(out), ("image", str(out)))
        self.assertEqual(Image.open(out).size, (2, 2))

    def test_copied_text_is_read_with_pbpaste(self):
        self.grab(None)
        run = self.patch("_run", return_value=(True, "some words"))
        self.assertEqual(macsys.clipboard(self.tmp() / "c.png"), ("text", "some words"))
        run.assert_called_once_with(["pbpaste"])

    def test_text_is_still_read_when_looking_for_a_picture_goes_wrong(self):
        self.grab(error=OSError("no pasteboard"))
        self.patch("_run", return_value=(True, "still here"))
        self.assertEqual(macsys.clipboard(self.tmp() / "c.png"), ("text", "still here"))

    def test_a_clipboard_pbpaste_cannot_read_is_empty_text(self):
        self.grab(None)
        self.patch("_run", return_value=(False, "pbpaste: error"))
        self.assertEqual(macsys.clipboard(self.tmp() / "c.png"), ("text", ""))

    def test_text_is_put_on_the_clipboard_with_pbcopy(self):
        with mock.patch.object(macsys.subprocess, "run", return_value=done(0)) as run:
            self.assertTrue(macsys.set_clipboard("héllo"))
        args, kw = run.call_args
        self.assertEqual((args[0], kw["input"], kw["env"]["LANG"]), (["pbcopy"], "héllo", "en_US.UTF-8"))
        with mock.patch.object(macsys.subprocess, "run", return_value=done(1)):
            self.assertFalse(macsys.set_clipboard("x"))

    def test_a_pbcopy_that_will_not_run_is_just_false(self):
        for err in (OSError("gone"), subprocess.TimeoutExpired(["pbcopy"], 10)):
            with mock.patch.object(macsys.subprocess, "run", side_effect=err):
                self.assertFalse(macsys.set_clipboard("x"))


class Inline:
    """A Thread that runs its target at once, where it is started."""

    def __init__(self, target, args=(), daemon=None):
        self.target, self.args, self.daemon = target, args, daemon

    def start(self):
        self.target(*self.args)


@unittest.skipUnless(MAC, "macOS only")
class Notifications(Sealed):
    def test_a_notification_is_posted_in_the_background_with_its_text_as_argv(self):
        osa = self.patch("osa")
        with mock.patch.object(macsys.threading, "Thread", Inline):
            macsys.notify("Void", "b" * 400)
        osa.assert_called_once_with("display notification (item 2 of argv) with title (item 1 of argv)", "Void", "b" * 300)

    def test_posting_does_not_wait_for_osascript(self):
        started = []

        class Held(Inline):
            def start(self):
                started.append(self)                               # (started, not run: notify() has already returned)
        osa = self.patch("osa")
        with mock.patch.object(macsys.threading, "Thread", Held):
            macsys.notify("t", "b")
        self.assertEqual((len(started), started[0].daemon), (1, True))
        osa.assert_not_called()


@unittest.skipUnless(MAC, "macOS only")
class Volume(Sealed):
    def setUp(self):
        super().setUp()
        self.osa = self.patch("osa", return_value=(True, "50,false"))

    def test_the_volume_and_whether_it_is_muted(self):
        self.assertEqual(macsys.volume_get(), (50, False))
        self.osa.return_value = (True, "7,true")
        self.assertEqual(macsys.volume_get(), (7, True))

    def test_a_volume_macos_will_not_say_is_none_and_not_muted(self):
        for out in ("", "missing value,false", "50"):
            self.osa.return_value = (False, out)
            self.assertEqual(macsys.volume_get(), (None, False), out)

    def test_mute_and_unmute_set_the_muted_flag(self):
        self.assertTrue(macsys.volume_set("mute"))
        self.assertEqual(self.osa.call_args.args, ("set volume output muted true",))
        macsys.volume_set("unmute")
        self.assertEqual(self.osa.call_args.args, ("set volume output muted false",))
        self.osa.return_value = (False, "")
        self.assertFalse(macsys.volume_set("mute"))

    def test_a_level_is_set_within_0_and_100(self):
        for val, want in ((40, 40), (150, 100), (-5, 0)):
            macsys.volume_set("set", val)
            self.assertEqual(self.osa.call_args.args, ("set volume output volume (item 1 of argv as integer)", want))

    def test_up_and_down_step_from_the_current_level_by_10_unless_told_otherwise(self):
        steps = ((("up", None), 60), (("up", 5), 55), (("down", None), 40), (("down", 8), 42), (("up", 80), 100))
        for (op, val), want in steps:
            self.osa.reset_mock()
            self.osa.side_effect = [(True, "50,false"), (True, "")]
            macsys.volume_set(op, val)
            self.assertEqual(self.osa.call_args.args[1], want, (op, val))
        self.osa.side_effect = [(True, "5,false"), (True, "")]
        macsys.volume_set("down", 20)
        self.assertEqual(self.osa.call_args.args[1], 0)

    def test_up_with_an_unreadable_volume_changes_nothing(self):
        self.osa.reset_mock()
        self.osa.side_effect = [(False, "")]
        self.assertFalse(macsys.volume_set("up"))
        self.assertEqual(self.osa.call_count, 1)


@unittest.skipUnless(MAC, "macOS only")
class Music(Sealed):
    def players(self, installed=("Spotify", "Music"), running=("Music",)):
        self.patch("_apps", return_value=[(n, Path(f"/Applications/{n}.app")) for n in installed])
        asked = []

        def run(cmd, timeout=10):
            asked.append(cmd)
            return cmd[:2] == ["pgrep", "-xq"] and cmd[2] in running, ""
        self.patch("_run", side_effect=run)
        return asked

    def test_the_player_is_the_first_one_that_is_installed_and_open(self):
        self.players()
        self.assertEqual(macsys._player(), "Music")
        self.players(running=("Spotify", "Music"))
        self.assertEqual(macsys._player(), "Spotify")

    def test_an_app_that_is_not_installed_is_never_asked_about(self):
        asked = self.players(installed=("Music",), running=("Spotify", "Music"))
        self.assertEqual(macsys._player(), "Music")
        self.assertEqual(asked, [["pgrep", "-xq", "Music"]])       # (AppleScript would pop up "Where is Spotify?")

    def test_no_player_open_means_no_media_and_nothing_playing(self):
        self.players(running=())
        osa = self.patch("osa")
        self.assertIsNone(macsys._player())
        self.assertFalse(macsys.media("play"))
        self.assertEqual(macsys.now_playing(), "")
        osa.assert_not_called()

    def test_each_media_key_is_the_players_own_verb(self):
        self.players()
        osa = self.patch("osa", return_value=(True, ""))
        for op, verb in (("pause", "pause"), ("play", "play"), ("toggle", "playpause"), ("next", "next track"),
                         ("previous", "previous track")):
            self.assertTrue(macsys.media(op))
            osa.assert_called_with(f'tell application "Music" to {verb}')

    def test_what_is_playing_is_title_by_artist_or_nothing(self):
        self.players()
        osa = self.patch("osa", return_value=(True, "Song by Band"))
        self.assertEqual(macsys.now_playing(), "Song by Band")
        self.assertIn('tell application "Music"', osa.call_args.args[0])
        osa.return_value = (False, "error text")
        self.assertEqual(macsys.now_playing(), "")


@unittest.skipUnless(MAC, "macOS only")
class Machine(Sealed):
    def test_brightness_is_not_on_macos_yet(self):
        self.assertIsNone(macsys.brightness("up", 10))

    def test_lock_sleeps_the_display_and_says_whether_it_worked(self):
        run = self.patch("_run", return_value=(True, ""))
        self.assertTrue(macsys.lock())
        run.assert_called_once_with(["pmset", "displaysleepnow"])
        run.return_value = (False, "denied")
        self.assertFalse(macsys.lock())

    def test_there_is_no_cuda_on_a_mac(self):
        self.assertFalse(macsys.gpu_ok())


@unittest.skipUnless(MAC, "macOS only")
class Apps(Sealed):
    def setUp(self):
        super().setUp()
        self.saved = dict(macsys._apps_cache)
        self.addCleanup(lambda: macsys._apps_cache.update(self.saved))

    def test_every_app_in_the_usual_folders_is_listed_and_a_missing_folder_is_skipped(self):
        root = self.tmp()
        a, b = root / "A", root / "B"
        for d, names in ((a, ["Safari.app", "notes.txt"]), (b, ["Music.app"])):
            d.mkdir()
            for n in names:
                (d / n).mkdir() if n.endswith(".app") else (d / n).write_text("x")
        macsys._apps_cache.update(t=-1e9, apps=[])
        with mock.patch.object(macsys, "APP_DIRS", (a, root / "missing", b)):
            self.assertEqual(sorted(macsys._apps()), [("Music", b / "Music.app"), ("Safari", a / "Safari.app")])
            (a / "Late.app").mkdir()
            self.assertEqual(len(macsys._apps()), 2)               # (the list is kept for 5 minutes)
            macsys._apps_cache["t"] -= 301
            self.assertEqual(len(macsys._apps()), 3)

    def test_the_best_match_by_name_is_opened_and_named(self):
        apps = [(n, Path(f"/Applications/{n}.app")) for n in ("Safari", "Safari Technology Preview", "Visual Studio Code")]
        self.patch("_apps", return_value=apps)
        with mock.patch.object(macsys.subprocess, "Popen") as popen:
            for said, want, path in ((" Safari. ", "Safari", "Safari"),                  # whole name beats a longer one
                                     ("technology", "Safari Technology Preview", "Safari Technology Preview"),  # a word
                                     ("safa", "Safari", "Safari"),                      # a start; the first of equals
                                     ("isual", "Visual Studio Code", "Visual Studio Code")):    # anywhere in it
                popen.reset_mock()
                self.assertEqual(macsys.open_app(said), want, said)
                self.assertEqual(popen.call_args.args[0], ["open", f"/Applications/{path}.app"])
            popen.reset_mock()
            self.assertIsNone(macsys.open_app("nothing like it"))
            popen.assert_not_called()


class Sends:
    """A stand-in for macsys._send that records every message and answers from `replies` (selector → value or callable)."""

    def __init__(self, replies=None):
        self.calls, self.replies = [], replies or {}

    def __call__(self, obj, sel, *args, restype=ctypes.c_void_p, argtypes=()):
        self.calls.append((obj, sel, *args))
        r = self.replies.get(sel)
        return r(obj, *args) if callable(r) else r


@unittest.skipUnless(MAC, "macOS only")
class CocoaCalls(Sealed):
    """The small Cocoa calls, against a recorded `_send`: no real window, screen or application is touched."""

    def test_the_app_becomes_an_accessory_with_no_dock_icon(self):
        s = self.sends(sharedApplication=77)
        macsys.no_dock_icon()
        self.assertEqual([c[1:] for c in s.calls], [("sharedApplication",), ("setActivationPolicy:", 1)])
        self.assertEqual(s.calls[1][0], 77)                        # (the policy goes to the shared application)

    def test_a_windows_native_handle_is_asked_of_qts_view(self):
        s = self.sends(window=0x55)
        self.assertEqual(macsys._nswindow("1234"), 0x55)
        self.assertEqual((s.calls[0][0].value, s.calls[0][1]), (1234, "window"))

    def test_click_through_follows_the_flag_and_needs_a_window(self):
        self.patch("_nswindow", side_effect=lambda w: 0x1234 if w else None)
        s = self.sends()
        macsys.set_click_through(1, True)
        macsys.set_click_through(1, 0)
        macsys.set_click_through(0, True)
        self.assertEqual(s.calls, [(0x1234, "setIgnoresMouseEvents:", True), (0x1234, "setIgnoresMouseEvents:", False)])

    def test_the_window_stays_on_every_space_and_does_not_hide(self):
        self.patch("_nswindow", side_effect=lambda w: 0x1234 if w else None)
        s = self.sends()
        macsys.keep_on_all_spaces(1)
        # canJoinAllSpaces | stationary | fullScreenAuxiliary | ignoresCycle
        self.assertEqual(s.calls, [(0x1234, "setCollectionBehavior:", 1 | 16 | 256 | 64),
                                   (0x1234, "setHidesOnDeactivate:", False)])
        s.calls.clear()
        macsys.keep_on_all_spaces(0)
        self.assertEqual(s.calls, [])

    def test_the_left_button_is_asked_of_the_session_state(self):
        with mock.patch.object(macsys._cg, "CGEventSourceButtonState", return_value=True) as q:
            self.assertIs(macsys.mouse_down(), True)
        q.assert_called_once_with(0, 0)


def rect(x, y, w, h):
    return macsys._Rect(x, y, w, h)


@unittest.skipUnless(MAC, "macOS only")
class Screens(Sealed):
    def test_every_screen_is_its_frame_its_visible_frame_and_the_camera_housing(self):
        frames = {201: rect(0, 0, 1512, 982), 202: rect(1512, 0, 1920, 1080)}
        visible = {201: rect(0, 0, 1512, 944), 202: rect(1512, 40, 1920, 1000)}
        self.sends(screens=100, count=2, **{"objectAtIndex:": lambda o, i: 201 + i, "frame": lambda o: frames[o],
                                            "visibleFrame": lambda o: visible[o],
                                            "respondsToSelector:": lambda o, sel: o == 201,
                                            "safeAreaInsets": lambda o: macsys._Insets(32, 0, 0, 0)})
        self.assertEqual(macsys._screens(), [((0, 0, 1512, 982), (0, 0, 1512, 944), 32.0),
                                             ((1512, 0, 1920, 1080), (1512, 40, 1920, 1000), 0.0)])

    def test_no_screens_is_an_empty_list(self):
        self.sends(screens=None)
        self.assertEqual(macsys._screens(), [])

    def test_the_insets_now_are_those_of_the_screens_and_bars_as_they_are(self):
        self.patch("_screens", return_value=[((0, 0, 1512, 982), (0, 0, 1512, 944), 32.0)])
        self.patch("_bars", return_value=[("menu", (0, 0, 1512, 38))])
        self.assertEqual(macsys.edge_insets_now(0, 0, 1512, 982),
                         {"top": 38, "bottom": 0, "left": 0, "right": 0, "menu": 38})


@unittest.skipUnless(MAC, "macOS only")
class Bars(Sealed):
    def test_no_window_list_means_no_answer(self):
        with mock.patch.object(macsys._cg, "CGWindowListCopyWindowInfo", return_value=None):
            self.assertIsNone(macsys._bars())

    def test_the_menu_bar_and_the_docks_own_window_are_the_bars_and_other_windows_are_not(self):
        key = {ctypes.c_void_p.in_dll(macsys._cg, n).value: n for n in
               ("kCGWindowLayer", "kCGWindowOwnerName", "kCGWindowBounds")}
        wins = [(24, b"Window Server", (0, 0, 1512, 38)),          # the menu bar
                (20, b"Dock", (0, 900, 1512, 60)),                 # the Dock
                (20, b"Other", (5, 5, 5, 5)),                      # something else on the Dock's layer
                (0, b"Finder", (0, 0, 800, 600))]                  # an ordinary window
        field = {"kCGWindowLayer": 1, "kCGWindowOwnerName": 2, "kCGWindowBounds": 3}

        def fake_rect(handle, ref):
            ref._obj.x, ref._obj.y, ref._obj.w, ref._obj.h = wins[handle // 10 - 1][2]
            return True
        self.sends(count=len(wins), **{"objectAtIndex:": lambda o, i: i + 1,
                                       "objectForKey:": lambda o, k: o * 10 + field[key[k.value]],
                                       "intValue": lambda o: wins[o // 10 - 1][0],
                                       "UTF8String": lambda o: wins[o // 10 - 1][1]})
        with mock.patch.object(macsys._cg, "CGWindowListCopyWindowInfo", return_value=7), \
                mock.patch.object(macsys._cg, "CGRectMakeWithDictionaryRepresentation", side_effect=fake_rect), \
                mock.patch.object(macsys._cf, "CFRelease") as release:
            self.assertEqual(macsys._bars(), [("menu", (0, 0, 1512, 38)), ("dock", (0, 900, 1512, 60))])
        release.assert_called_once_with(7)                          # (the list is let go)


@unittest.skipUnless(MAC, "macOS only")
class WatchingScreens(Sealed):
    def setUp(self):
        super().setUp()
        saved = dict(macsys._watch)
        macsys._watch.clear()
        self.addCleanup(lambda: (macsys._watch.clear(), macsys._watch.update(saved)))
        self.objc = mock.MagicMock()
        self.patch("_objc", new=self.objc)
        self.s = self.sends()

    def test_two_observers_are_added_and_either_notification_calls_back_once_set_up(self):
        cb = mock.Mock()
        self.assertTrue(macsys.watch_screens(cb))
        names = [c[4].value for c in self.s.calls if c[1] == "addObserver:selector:name:object:"]
        self.assertEqual(names, [ctypes.c_void_p.in_dll(macsys._appkit, n).value for n in
                                 ("NSWorkspaceActiveSpaceDidChangeNotification",
                                  "NSApplicationDidChangeScreenParametersNotification")])
        cb.assert_not_called()
        macsys._watch["imp"](None, None, None)                      # Cocoa delivering a notification
        cb.assert_called_once_with()

    def test_setting_up_twice_keeps_the_first_observer(self):
        first, second = mock.Mock(), mock.Mock()
        macsys.watch_screens(first)
        n = len(self.s.calls)
        self.assertTrue(macsys.watch_screens(second))
        self.assertEqual(len(self.s.calls), n)
        self.assertIs(macsys._watch["cb"], first)

    def test_a_class_that_cannot_be_made_or_a_missing_call_means_poll_instead(self):
        self.objc.objc_allocateClassPair.return_value = None
        self.assertFalse(macsys.watch_screens(mock.Mock()))
        self.objc.objc_getClass.side_effect = AttributeError("no such symbol")
        self.assertFalse(macsys.watch_screens(mock.Mock()))
        self.assertEqual(macsys._watch, {})

    def test_a_callback_that_fails_never_reaches_cocoa(self):
        macsys._watch["cb"] = mock.Mock(side_effect=RuntimeError("page gone"))
        macsys._fire()
        macsys._watch.clear()
        macsys._fire()                                              # (nothing set up yet: still no exception)
