"""Tests for the notch on the page: docked, when it moves to hang at another depth (the menu bar slid down over a
full-screen app, or went), the liquid starts and ends exactly where the real notch is, so nothing snaps when the real
notch takes over again. And a little Void split in two has no eyes until it's whole again. The real page in Qt's web
view, offscreen: no window on the desktop.

    python3 -m unittest discover -s tests
"""
import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path

PAGE = Path(__file__).resolve().parent.parent / "app" / "static" / "index.html"
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu --num-raster-threads=1 --renderer-process-limit=1")
try:
    from PySide6.QtCore import QEvent, QUrl
    from PySide6.QtWebEngineCore import QWebEngineScript
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QApplication
except ImportError:
    QWebEngineView = None

# Full motion whatever the host's accessibility setting: the tests below prove the page's full-motion path (the liquid
# shift, the eyes through a split with the glow on), and a host with Reduce Motion on (a CI runner's, or a Mac's) sends
# the page down its reduced-motion path instead. Runs in the page's own world before its script, so the page's
# `RM = matchMedia('(prefers-reduced-motion: reduce)')` reads "no". The reduced-motion path is covered by SWEEP's
# explicit `rm` cases, not by the host.
FULL_MOTION = """(()=>{ const real=window.matchMedia.bind(window);
  window.matchMedia=q=>real(/prefers-reduced-motion\\s*:\\s*reduce/.test(q)?'not all':q); })();"""

# every frame while the liquid stands in for the notch: where its bar reaches and where the real notch is
WATCH = """(()=>{ window.__seen=[]; const bar=$('#gooBar'), pill=$('#barPill');
  (function f(){ const b=document.body.classList; if(b.contains('goohide')){ const r=bar.getBoundingClientRect();
      window.__seen.push([r.top,r.bottom,r.left,r.right]); }
    if(window.__seen) requestAnimationFrame(f); })();
  return 1; })()"""
PILL = "JSON.stringify((r=>[r.top,r.bottom,r.left,r.right])($('#barPill').getBoundingClientRect()))"


@unittest.skipUnless(QWebEngineView and sys.platform == "darwin", "macOS with PySide6's web view only")
class Page(unittest.TestCase):
    """The page in a web view of its own, for each class of tests."""
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.view = QWebEngineView()
        script = QWebEngineScript()
        script.setName("full-motion")
        script.setSourceCode(FULL_MOTION)
        script.setInjectionPoint(QWebEngineScript.DocumentCreation)
        script.setWorldId(QWebEngineScript.MainWorld)
        cls.view.page().scripts().insert(script)
        cls.view.resize(340, 460)
        cls.view.show()                                                 # (offscreen: it only animates shown)
        cls.view.load(QUrl.fromLocalFile(str(PAGE)))
        cls.wait_for(lambda: cls.js("typeof voidBarInset==='function'&&typeof voidDock==='function'"))

    @classmethod
    def tearDownClass(cls):
        # the page and the view really gone while the app is still alive: one left for the app's own end is torn down
        # with the default profile, after Qt Quick, and crashes on exit (macOS: "Python quit unexpectedly")
        page, gone = cls.view.page(), []
        page.destroyed.connect(lambda: gone.append("page"))
        cls.view.destroyed.connect(lambda: gone.append("view"))
        cls.view.close()
        page.deleteLater()                                               # (the page before the profile it uses)
        cls.view.deleteLater()
        end = time.monotonic() + 5
        while len(gone) < 2 and time.monotonic() < end:
            cls.app.sendPostedEvents(None, QEvent.DeferredDelete)
            cls.app.processEvents()
            time.sleep(0.01)
        for _ in range(10):                                              # (and what deleting them left to delete)
            cls.app.sendPostedEvents(None, QEvent.DeferredDelete)
            cls.app.processEvents()
            time.sleep(0.01)
        cls.view = None
        assert len(gone) == 2, f"only {gone} gone: the web view outlived the test"

    @classmethod
    def js(cls, code, timeout=5.0):
        got = []
        cls.view.page().runJavaScript(code, 0, got.append)
        end = time.monotonic() + timeout
        while not got and time.monotonic() < end:
            cls.app.processEvents()
            time.sleep(0.005)
        return got[0] if got else None

    @classmethod
    def conditions(cls, frames):
        """What a failure message says the page ran under: its own reduced-motion state and lowFx (a CI runner's
        accessibility setting or slow frames change what the notch and the eyes do), and the frames the test saw."""
        return f"page: {cls.js('`RM.matches=${RM.matches} lowFx=${lowFx}`')}, {frames} frames seen"

    @classmethod
    def wait_for(cls, cond, timeout=15.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if cond():
                return True
            cls.app.processEvents()
            time.sleep(0.02)
        raise AssertionError("the page never got there")



@unittest.skipUnless(QWebEngineView and sys.platform == "darwin", "macOS with PySide6's web view only")
class NotchShift(Page):
    def pill(self):
        return json.loads(self.js(PILL))

    def shift(self, px):
        """Hang the docked notch px in, as the window says when the menu bar comes or goes: → (the real notch before,
        every frame of the liquid, the real notch after)."""
        before = self.pill()
        self.js(WATCH)
        self.js(f"voidBarInset({px},true)")
        self.wait_for(lambda: self.js("document.body.classList.contains('goohide')") is False)
        seen = self.js("JSON.stringify(window.__seen)")
        self.js("window.__seen=null")
        return before, json.loads(seen), self.pill()

    def test_drip_down_and_slurp_up_start_and_end_on_the_notch(self):
        self.js("voidBarInset(0,false); voidDock('top','')")
        self.wait_for(lambda: self.js("document.body.classList.contains('bar-done')"))
        for px in (30, 0):                                               # under the menu bar, and back to the edge
            before, seen, after = self.shift(px)
            why = f"shift to {px}, {self.conditions(len(seen))}"
            self.assertGreater(len(seen), 3, why)
            self.assertAlmostEqual(after[1], 52 + px, delta=1, msg=why)  # (the real notch: at the new depth)
            # the liquid's bar: its first frame no longer than the notch was, its last exactly the notch now (a
            # longer one is cut back in one frame when the real notch takes over: a snap)
            self.assertAlmostEqual(seen[0][1], before[1], delta=2, msg=why)
            self.assertAlmostEqual(seen[-1][1], after[1], delta=1, msg=why)
            self.assertLessEqual(seen[-1][0], after[0] + 1, why)         # (and hangs from at least as high)


# every frame of a little Void's life (its state, how far it's split, its eyes' opacity) while it buds, splits for a
# helper of its own, comes back together and is drunk back in
LIFE = """(()=>{ window.__life=[]; const id='t-split';
  onEvent({t:'sub_start', id, type:'Explore', kids:1});
  (function f(){ const m=MINIS.get(id); if(!m){ window.__life.push(null); return; }
      window.__life.push([m.st, m.sv, +m.eyes.getAttribute('opacity')]);
      if(m.st==='orbit'&&m.sv>=1&&m.kids) miniKids({id, n:0});                        // its helper's done
      if(m.st==='orbit'&&!m.kids&&!m.sv&&!m.status) onEvent({t:'sub_end', id, status:'done'});
      requestAnimationFrame(f); })();
  return 1; })()"""
# its eyes' opacity drawn at each split (sv) in each mode: rm reduced motion, goo the glow on
SWEEP = """JSON.stringify((()=>{ const m=miniAdd({id:'t-sweep'}), out=[];
  m.st='orbit'; m.kids=1;
  for(const [rm,goo] of [[false,true],[false,false],[true,false]])
    for(const sv of [0,.05,.1,.16,.3,.6,.76,.9,1]){
      Object.assign(m,{sv, svDir:1, phi:0, pinchAt:0});
      orbDraw(m,performance.now(),.016,1,rm,goo); out.push([rm,goo,sv,+m.eyes.getAttribute('opacity')]); }
  miniGone(m); return out; })())"""


@unittest.skipUnless(QWebEngineView and sys.platform == "darwin", "macOS with PySide6's web view only")
class SplitEyes(Page):
    """A little Void split in two has no eyes: shut, they'd be a sliver of eye-white over both halves."""

    def test_no_eyes_while_split_and_back_after(self):
        for rm, goo, sv, op in json.loads(self.js(SWEEP)):
            with self.subTest(rm=rm, goo=goo, sv=sv):
                if sv == 0 or (not rm and sv <= .1):
                    self.assertEqual(op, 1)                              # (whole, or only starting to shut its eyes)
                elif not rm and sv >= .16 or sv == 1:
                    self.assertEqual(op, 0)

    def test_eyes_gone_through_a_real_split_and_back_at_merge(self):
        self.js(LIFE)
        self.wait_for(lambda: self.js("window.__life.at(-1)===null"), timeout=20)
        life = json.loads(self.js("JSON.stringify(window.__life)"))[:-1]
        self.js("window.__life=null")
        why = self.conditions(len(life))
        split = [op for st, sv, op in life if sv >= .16]
        self.assertTrue(split and life[0][0] == "bud" and any(sv == 1 for _, sv, _ in life), why)
        self.assertEqual(max(split), 0, why)                             # split: no eyes at all
        bud = [i for i, (st, _, _) in enumerate(life) if st == "bud"]
        self.assertEqual(life[bud[-1]][2], 1, why)                       # budded out: eyes on
        whole = [op for st, sv, op in life[bud[-1] + 1:] if st in ("orbit", "done") and sv == 0]
        self.assertTrue(whole, why)
        self.assertEqual(min(whole), 1, why)                             # together again, before it's drunk in
        self.assertEqual(next(op for st, _, op in life if st == "merge"), 1, why)


@unittest.skipUnless(QWebEngineView and sys.platform == "darwin", "macOS with PySide6's web view only")
class CleanExit(unittest.TestCase):
    def test_passes_and_then_exits_cleanly(self):
        """The web view's tests on their own, in a fresh Python: they pass and then it exits without crashing (a crash on
        the way out leaves a report and puts 'Python quit unexpectedly' on screen, after the tests said OK)."""
        r = subprocess.run([sys.executable, "-m", "unittest", "test_page_notch.NotchShift", "test_page_notch.SplitEyes"],
                           cwd=Path(__file__).parent, capture_output=True, text=True, timeout=60)
        self.assertIn("OK", r.stderr)
        self.assertEqual(r.returncode, 0, r.stderr[-500:])               # (a crash: -11, SIGSEGV)


if __name__ == "__main__":
    unittest.main()
