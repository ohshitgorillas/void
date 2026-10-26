"""Tests for the context cloud of sparks around Void: how many there are is linear in the tokens in the context
(none in a fresh chat, all of them when it's full), and a new spark starts hidden behind his ball.
The real page in headless Chromium (Playwright under node), from file://: its fetches just fail.

    python3 -m unittest discover -s tests
"""
import unittest

from test_page_idle import INIT, NODE_PATH, run_page

SCRIPT = r"""const { chromium } = require('playwright');
(async () => {
  const out = {errors: []}, b = await chromium.launch(LAUNCH);
  try {
    const p = await b.newPage({viewport: {width: 340, height: 460}});
    p.on('pageerror', e => out.errors.push(String(e && e.message || e)));
    await p.addInitScript(INIT);
    await p.goto('file://' + PAGE);
    await p.waitForFunction(() => typeof sparkTarget === 'function' && window.__loop.calls > 5, null, {timeout: 10000});
    out.map = await p.evaluate(() => [0, 25000, 50000, 112500, 200000, 400000].map(u => [u, sparkTarget(u, 200000)]));
    out.max = await p.evaluate(() => ORB_MAX);
    out.spawns = await p.evaluate(() => { const o = ORBS[0], r = [];
      for (let i = 0; i < 200; i++) { orbSpawn(o, 110); r.push([Math.hypot(o.p[0], o.p[1]), o.p[2], Math.hypot(...o.p)]); } return r; });
    // fill the context: sparks come in one at a time, and never over his face
    out.ramp = await p.evaluate(async () => { info.context = {used: 200000, max: 200000}; const seen = [], over = [];
      for (let k = 0; k < 40; k++) { await new Promise(r => setTimeout(r, 100)); seen.push(orbN);
        for (const o of ORBS) if (o.pr > 0 && o.pr < 1 && o.back === false) over.push(o.p.slice()); }
      return {seen, over: over.filter(q => Math.hypot(q[0], q[1]) < 76).length}; });
  } catch (e) { out.fatal = String(e && e.stack || e); }
  await b.close(); process.stdout.write(JSON.stringify(out));
})();"""


@unittest.skipUnless(NODE_PATH, "node with a global playwright only")
class Sparks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = run_page(SCRIPT, INIT)

    def test_page_loads_without_errors(self):
        self.assertNotIn("fatal", self.r, self.r.get("fatal"))
        self.assertEqual(self.r["errors"], [])

    def test_count_is_linear_in_tokens(self):
        m = dict((u, n) for u, n in self.r["map"])
        top = self.r["max"]
        self.assertEqual(m[0], 0)
        self.assertEqual(m[25000], 0)                                  # (a fresh chat's own setup)
        self.assertEqual(m[200000], top)
        self.assertEqual(m[400000], top)                               # (never past the maximum)
        self.assertAlmostEqual(m[112500], top / 2, delta=1)
        self.assertAlmostEqual(m[50000], top * 25000 / 175000, delta=1)

    def test_new_sparks_start_behind_the_ball(self):
        for flat, z, r in self.r["spawns"]:
            self.assertLess(flat, 76)                                  # (inside his outline)
            self.assertLess(z, 0)                                      # (behind him)
            self.assertAlmostEqual(r, 110, delta=1)

    def test_they_come_in_one_at_a_time(self):
        seen = self.r["ramp"]["seen"]
        self.assertTrue(all(b - a in (0, 1) for a, b in zip(seen, seen[1:])), seen)
        self.assertGreater(seen[-1], seen[0])
        self.assertEqual(self.r["ramp"]["over"], 0)


if __name__ == "__main__":
    unittest.main()
