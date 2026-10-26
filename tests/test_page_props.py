"""What Void holds while he works: reading a markdown file, a little cream notebook (a two-page spread whose leaves
flip, the file's real lines on it as tiny text) instead of the terminal; every other file still the terminal. A Bash
right after swaps the notebook back for the terminal without the holder ever leaving his hand; a helper (Agent / Task)
brings up nothing; the notebook faces the way the "terminal faces you" setting says, same as the terminal.
The real page in headless Chromium (Playwright under node), from file://: its fetches just fail.

    python3 -m unittest discover -s tests
"""
import unittest

from test_page_idle import INIT, NODE_PATH, run_page

KINDS = ("terminal", "nb-read", "nb-write", "image")

SCRIPT = r"""const { chromium } = require('playwright');
(async () => {
  const out = {errors: []}, b = await chromium.launch(LAUNCH);
  try {
    const p = await b.newPage({viewport: {width: 340, height: 460}});
    p.on('pageerror', e => out.errors.push(String(e && e.message || e)));
    await p.addInitScript(INIT);
    await p.goto('file://' + PAGE);
    await p.waitForFunction(() => typeof onEvent === 'function' && window.__loop.calls > 5, null, {timeout: 10000});
    await p.evaluate(() => {
      const H = window.__h = {kinds: ['terminal', 'nb-read', 'nb-write', 'image'], pages: []};
      H.holder = () => document.getElementById('prop');
      H.child = k => { const h = H.holder(); if (!h) return null;
        for (const c of h.children) if (c.classList.contains(k) || c.dataset.kind === k || c.id === k) return c;
        return null; };
      const op = n => { let o = 1; for (let e = n; e && e.nodeType === 1; e = e.parentElement) o *= parseFloat(getComputedStyle(e).opacity); return o; };
      H.showing = k => { const h = H.holder(), c = H.child(k); if (!h || !c || !h.classList.contains('on')) return false;
        const s = getComputedStyle(c); return s.display !== 'none' && s.visibility !== 'hidden' && op(c) > 0.05; };
      // the sign of the x axis as drawn: < 0 is turned away from you (mirrored), > 0 is facing you
      H.facing = k => { const c = H.child(k); if (!c) return null; let m = new DOMMatrix();
        for (let e = c; e && e.nodeType === 1; e = e.parentElement) { const t = getComputedStyle(e).transform;
          if (t && t !== 'none') m = new DOMMatrix(t).multiply(m); }
        return m.a; };
      // two side-by-side pages: a pair of boxes inside the notebook, each a third to two thirds of its width and most of
      // its height, next to each other at the same height (layout boxes, so a leaf mid-flip doesn't matter)
      const abs = e => { let x = 0, y = 0; for (let n = e; n; n = n.offsetParent) { x += n.offsetLeft; y += n.offsetTop; } return [x, y]; };
      H.spread = () => { const nb = H.child('nb-read'); if (!nb || !nb.offsetWidth) return null;
        const [nx, ny] = abs(nb), W = nb.offsetWidth, Hh = nb.offsetHeight, boxes = [];
        for (const e of nb.querySelectorAll('*')) { if (!(e instanceof HTMLElement) || !e.offsetWidth) continue;
          const [x, y] = abs(e), w = e.offsetWidth, h = e.offsetHeight;
          if (w >= W * .33 && w <= W * .67 && h >= Hh * .6) boxes.push([x - nx, y - ny, w, h]); }
        for (const a of boxes) for (const c of boxes)
          if (a !== c && a[0] + a[2] <= c[0] + 2 && Math.abs(a[1] - c[1]) <= 4) return {w: W, h: Hh, left: a, right: c};
        return {w: W, h: Hh, boxes: boxes.length}; };
      H.text = k => { const c = H.child(k); return c ? c.textContent : ''; };
      H.wrapPages = () => { if (typeof PROPS === 'undefined' || !PROPS['nb-read'] || typeof PROPS['nb-read'].page !== 'function') return false;
        const orig = PROPS['nb-read'].page;
        PROPS['nb-read'].page = function (lines) { H.pages.push({shown: H.showing('nb-read'),
          lines: Array.isArray(lines) ? lines.map(String) : null}); return orig.apply(this, arguments); };
        return true; };
      H.sample = () => ({on: !!(H.holder() && H.holder().classList.contains('on')),
        shown: H.kinds.filter(H.showing), nbText: H.text('nb-read'), termText: H.text('terminal'),
        nbFacing: H.facing('nb-read'), termFacing: H.facing('terminal')});
      H.watch = async (ms, until) => { const s = []; const t0 = performance.now();
        while (performance.now() - t0 < ms) { const x = H.sample(); s.push(x); if (until && until(x)) break;
          await new Promise(r => setTimeout(r, 50)); } return s; };
    });
    out.holder = await p.evaluate(() => !!__h.holder());
    out.kids = await p.evaluate(() => __h.kinds.filter(k => !!__h.child(k)));
    out.wrapped = await p.evaluate(() => __h.wrapPages());

    // what a Read result looks like: each line behind its number and a tab
    const MD = Array.from({length: 40}, (_, i) => `${String(i + 1).padStart(6)}\t` +
      (i % 10 === 0 ? `# notes part ${i / 10 + 1}` : `- remember thing number ${i + 1}`)).join('\n');
    const PY = Array.from({length: 12}, (_, i) => `${String(i + 1).padStart(6)}\tvalue_${i + 1} = compute(${i + 1})`).join('\n');
    const read = (id, file, text) => p.evaluate(([id, file, text]) => { busy = true;
      CP.tool({t: 'tool', name: 'Read', id, input: {file_path: file}, busy: true});
      CP.result({t: 'toolres', id, text, is_error: false, busy: true}); }, [id, file, text]);
    const bash = id => p.evaluate(id => { busy = true;
      CP.tool({t: 'tool', name: 'Bash', id, input: {command: 'ls -la docs', description: 'listing docs'}, busy: true});
      CP.result({t: 'toolres', id, text: 'GUIDE.md\ndesign', is_error: false, busy: true}); }, id);
    const settle = async () => { await p.evaluate(() => { CP.done(); busy = false; }); await p.waitForTimeout(1200); };
    const termUp = 'x => x.shown.includes("terminal") && /ls -la docs/.test(x.termText)';

    // 1: notes.md, faced the default way (toward him), then a Bash right after it
    await read('r1', '/work/void/notes.md', MD);
    out.md = await p.evaluate(() => __h.watch(5000));
    await bash('b1');
    out.bash = await p.evaluate(u => __h.watch(3000, eval(u)), termUp);
    out.bashTail = await p.evaluate(() => __h.watch(600));
    await settle();
    out.idle = await p.evaluate(() => __h.sample());

    // 2: helpers bring up nothing
    await p.evaluate(() => { busy = true;
      CP.tool({t: 'tool', name: 'Agent', id: 'a1', input: {description: 'look around'}, busy: true});
      CP.tool({t: 'tool', name: 'Task', id: 't1', input: {description: 'look around'}, busy: true}); });
    out.helpers = await p.evaluate(() => __h.watch(1200));
    await settle();

    // 3: app.py is still the terminal
    await read('r2', '/work/void/app.py', PY);
    out.py = await p.evaluate(() => __h.watch(3000));
    await settle();

    // 4: the setting turned to face you
    await p.evaluate(() => { info.code_face = 'you'; document.body.classList.add('faceyou'); });
    await read('r3', '/work/void/notes.md', MD);
    out.mdYou = await p.evaluate(() => __h.watch(2500));
    out.spread = await p.evaluate(() => __h.spread());
    await bash('b2');
    out.bashYou = await p.evaluate(u => __h.watch(3000, eval(u)), termUp);
    await settle();
    out.pages = await p.evaluate(() => __h.pages);
  } catch (e) { out.fatal = String(e && e.stack || e); }
  await b.close(); process.stdout.write(JSON.stringify(out));
})();"""

MD_LINES = [f"# notes part {i // 10 + 1}" if i % 10 == 0 else f"- remember thing number {i + 1}" for i in range(40)]


@unittest.skipUnless(NODE_PATH, "node with a global playwright only")
class Props(unittest.TestCase):
    """One page: notes.md then a Bash (facing him), Agent + Task, app.py, notes.md then a Bash (facing you)."""
    @classmethod
    def setUpClass(cls):
        cls.r = run_page(SCRIPT, INIT)

    def setUp(self):
        self.assertNotIn("fatal", self.r, self.r.get("fatal"))

    def nb_samples(self, part):
        return [s for s in self.r[part] if "nb-read" in s["shown"]]

    def test_page_runs_without_errors(self):
        self.assertEqual(self.r["errors"], [])

    def test_one_holder_with_a_child_per_kind(self):
        self.assertTrue(self.r["holder"], "no #prop holder on the page")
        self.assertEqual(sorted(self.r["kids"]), sorted(KINDS))

    def test_reading_markdown_brings_up_the_notebook_not_the_terminal(self):
        md = self.r["md"]
        self.assertTrue(self.nb_samples("md"), "the notebook never came up for notes.md")
        self.assertFalse([s for s in md if "terminal" in s["shown"]], "the terminal came up for notes.md")
        self.assertTrue(all(len(s["shown"]) <= 1 for s in md))          # (one thing in his hand at a time)

    def test_the_notebook_shows_the_files_real_lines(self):
        texts = [s["nbText"] for s in self.nb_samples("md")]
        self.assertTrue(texts, "the notebook never came up for notes.md")
        self.assertTrue(any(l in t for t in texts for l in MD_LINES), texts[:1])
        for t in texts:
            self.assertNotIn("\t", t)                                   # (no Read line-number gutter)

    def test_its_leaf_turns_more_than_once_while_the_text_is_shown(self):
        self.assertTrue(self.r["wrapped"], "no PROPS['nb-read'].page(lines)")
        pages = [g for g in self.r["pages"] if g["shown"]]
        self.assertGreater(len(pages), 1, self.r["pages"])
        for g in pages:
            self.assertIsNotNone(g["lines"])
            for l in g["lines"]:
                self.assertTrue(not l.strip() or any(l.strip() in m for m in MD_LINES), l)
        self.assertTrue(any(l.strip() for g in pages for l in g["lines"]))

    def test_reading_other_files_still_brings_up_the_terminal(self):
        py = self.r["py"]
        self.assertTrue([s for s in py if "terminal" in s["shown"]], "the terminal never came up for app.py")
        self.assertFalse([s for s in py if "nb-read" in s["shown"]], "the notebook came up for app.py")
        self.assertTrue(any("value_1 = compute(1)" in s["termText"] for s in py))

    def test_a_bash_right_after_swaps_back_to_the_terminal(self):
        last = self.r["bash"][-1]
        self.assertIn("terminal", last["shown"], last)
        self.assertNotIn("nb-read", last["shown"], last)
        for s in self.r["bashTail"]:
            self.assertNotIn("nb-read", s["shown"])

    def test_the_holder_never_leaves_his_hand_in_the_swap(self):
        run = self.r["md"] + self.r["bash"]
        first = next((i for i, s in enumerate(run) if s["shown"]), None)
        self.assertIsNotNone(first, "nothing ever came up")
        self.assertTrue(all(s["on"] for s in run[first:]), [s["on"] for s in run[first:]])
        self.assertFalse(self.r["idle"]["on"])                          # (put away once he's done)

    def test_helpers_bring_up_nothing(self):
        self.assertTrue(self.r["holder"], "no #prop holder on the page")
        for s in self.r["helpers"]:
            self.assertFalse(s["on"], s)
            self.assertEqual(s["shown"], [], s)

    def test_the_notebook_is_a_two_page_spread(self):
        sp = self.r["spread"]
        self.assertIsNotNone(sp, "no notebook laid out")
        self.assertIn("right", sp, sp)

    def test_the_notebook_faces_as_the_setting_says(self):
        him = [s["nbFacing"] for s in self.nb_samples("md")]
        you = [s["nbFacing"] for s in self.nb_samples("mdYou")]
        self.assertTrue(him and you, "the notebook didn't come up under both settings")
        self.assertTrue(all(f is not None and f < 0 for f in him), him)    # (faces him: you see its back)
        self.assertTrue(all(f is not None and f > 0 for f in you), you)    # (faces you: readable)
        term_him = [s["termFacing"] for s in self.r["bash"] if "terminal" in s["shown"]]
        term_you = [s["termFacing"] for s in self.r["bashYou"] if "terminal" in s["shown"]]
        self.assertTrue(term_him and term_you, "the terminal didn't come up under both settings")
        self.assertLess(term_him[-1], 0)                                # (and the same way as the terminal)
        self.assertGreater(term_you[-1], 0)


if __name__ == "__main__":
    unittest.main()
