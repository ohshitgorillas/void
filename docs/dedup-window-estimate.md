# Estimate: a shared window_core.py for window.py and window_win.py

Read on origin/macos at 248e46b. window.py (GTK, Linux) is 1149 lines, window_win.py (Qt, Windows + macOS) is 987.

## What really can be shared

Only small pure functions with no toolkit in them:

- The size constants W, H, WIDE, CODE_SIDE, BAR_SIDE, GLIDE, BALL (about 7 lines each side).
- The room math in set_wide: the two `max(...)` lines that work out L and R from want_panel/code/bar and hover.
  Clamping after that differs: GTK clamps on the layer-shell monitor or lets an X11 window grow only to the right;
  Qt keeps a fixed ROOM on the left and tells the page through voidRoom. That part stays per toolkit.
- Dock position per edge, as `dock_xy(edge, area_x, area_y, area_w, area_h)`. GTK uses width/height, Qt uses
  center()/right()+1, which come out the same numbers.
- The drop-at-edge test: distance to each edge, nearest one, closer than 40 px. Qt also skips it if the window
  moved less than 12 px; GTK does not. That check stays in Qt.
- The ghost rect on the wall, as `ghost_rect(bx, y, edge, inset=0)`. GTK has no inset; Qt has bar_inset (macOS menu
  bar). Same numbers otherwise (280x52, 68x230).
- The ghost's melting shape at k (rect and corner radius). Drawing it stays per toolkit (cairo arcs vs QPainter).
- Easing `1 - (1 - k) ** 3` and the -40 px swoop on the way home, as a helper.
- Hover follow: the velocity smoothing (0.8 / 0.2) and the voidLook numbers (/900, clamped to -1..1). Not the
  loop: GTK runs a thread with idle_add and a 0.7 lag; Qt runs on a QTimer with no lag.
- _authed_url: the same loop; only the runtime.json path differs, so pass it in.
- The socket command names as one tuple. launch_win.py can import it. bin/void is bash and cannot; the most
  it gets is a test that its list matches. The lists already differ on purpose (bin/void has restart and handles
  ptt-* earlier; launch_win.py takes ptt-*), so "one list" is really two or three named lists.
- The selftest-bar report line, as one format function.

## What only looks alike and must stay per toolkit

- barShape in index.html is JavaScript and cannot import Python. Its numbers also differ from the ghost on
  purpose (260 / 210 vs 280 / 230). Leave it; at most a comment pointing at the Python side.
- The message table from the page. Same keys, different handlers: GTK has keyboard grab/release and a full
  drag_end; Qt has ptt:, _pmove, a one-line dragend, kbd:release does nothing. A shared parser for region:,
  dragby: and reauth plus a per-window dict saves maybe 6 lines and adds a layer of indirection.
- The glide loops, show/hide/toggle, drag, click-through, the socket server (unix socket vs port + secret),
  log() (GTK prints each message once; Qt prints every one). Sharing log() would change Qt's behaviour.
- The selftest-bar output itself: GTK prints `layer=...`, Qt does not. barcheck.py needs `layer=`; smoke.ps1's
  regex does not. One format function is fine only if both parsers keep matching.

## Honest line count

About 50-60 lines leave each window, so ~110 lines removed. window_core.py with docstrings is ~70-80 lines.
Net saving: about 30-40 lines, not 250-300. The audit counted look-alike code that is toolkit glue.
The real gain is not lines: the shared bits become unit-testable on any machine, which today they are not.

## Steps (each a small diff with one test command)

1. Add app/window_core.py with constants, ease_out, room(), dock_xy(), nearest_edge(), ghost_rect(),
   ghost_shape(), look(), authed_url(path, url), COMMANDS; add tests/test_window_core.py. Nothing uses it yet.
   ~80 + ~80 lines. `python3 -m unittest tests.test_window_core`
2. window_win.py imports from it (keep W, H etc. as names in window_win, test_window_mac reads them).
   ~-50 / +10. On a Mac: `python3 -m unittest tests.test_window_mac tests.test_quit`; Windows: the windows workflow.
3. window.py imports from it. ~-55 / +10. `python3 -m py_compile app/window.py`
   locally, then the installer workflow's Xvfb and sway selftest-bar steps (run it by hand: workflow_dispatch).
4. launch_win.py takes its command list from window_core; add a test that bin/void's case list matches.
   ~-3 / +20. `python3 -m unittest tests.test_launchers`
5. (Optional) one selftest-bar format function. ~-6 / +8. Windows smoke + installer workflow.

## Risks

- window.py has no unit tests at all. Its only check is the selftest-bar run in installer.yml, which triggers
  on main and tags only, not on macos. Hover, drag, ghost and Hyprland paths are never run anywhere.
- test_window_mac.py and test_qt_identity.py skip unless on macOS with PySide6; CI (macos.yml) only builds the
  app and runs none of them. On Linux they all skip.
- Windows gets only smoke.ps1: selftest and selftest-bar, no hover, drag or click-through.
- Desktop-only things: drag-to-edge docking, the ghost melt, hover follow and glide feel, layer-shell vs X11 vs
  XWayland vs Hyprland, macOS menu bar inset, Windows taskbar work area. None of these can be checked headless.
- window.py runs on the system Python; window_core.py must stay stdlib-only and work on old system Pythons,
  and must be shipped by every package (deb, Arch, installer, the .app). They copy app/, but check.
- Off-by-one: GTK and Qt measure screen right/bottom differently; dock_xy must be fed the right numbers per side.

## Recommendation

Later, and smaller than proposed. ~35 net lines is not worth touching window.py while it has no tests and its
CI does not run on this branch. Do step 1 (pure module + tests) and step 4 (command list) when next touching
those areas: they add coverage and catch drift between bin/void and launch_win.py. Do steps 2-3 only when a
change has to land in both windows anyway, so the desktop test pass it needs is paid once.
