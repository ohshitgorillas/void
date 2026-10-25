"""You answer Void while he's still working on the last thing (over him, or between his sentences): the page keeps
what you said and sends it as a follow-up once his reply is done, instead of throwing it away.
The real page in headless Chromium (Playwright under node), from file://: its fetches just fail.

    python3 -m unittest discover -s tests
"""
import unittest

from test_page_idle import INIT, NODE_PATH, run_page

SCRIPT = r"""const { chromium } = require('playwright');
(async () => {
  const out = {errors: []}, b = await chromium.launch();
  try {
    const p = await b.newPage({viewport: {width: 340, height: 460}});
    p.on('pageerror', e => out.errors.push(String(e && e.message || e)));
    await p.addInitScript(INIT);
    await p.goto('file://' + PAGE);
    await p.waitForFunction(() => typeof onEvent === 'function' && window.__loop.calls > 5, null, {timeout: 10000});
    out.r = await p.evaluate(async () => {
      const sent = [], wait = ms => new Promise(r => setTimeout(r, ms));
      window.send = (text, opts) => { sent.push([text, !!(opts && opts.follow)]); };
      busy = true;
      onEvent({t: 'wake', follow: true, text: 'please add milk'});
      onEvent({t: 'wake', follow: true, text: 'and eggs too'});
      await wait(800); const whileBusy = sent.slice();
      busy = false;
      await wait(800); const after = sent.slice();
      onEvent({t: 'wake', follow: true, text: 'thanks a lot'});      // not busy: straight out, as before
      return {whileBusy, after, idle: sent.slice(after.length)};
    });
  } catch (e) { out.fatal = String(e && e.stack || e); }
  await b.close(); process.stdout.write(JSON.stringify(out));
})();"""


@unittest.skipUnless(NODE_PATH, "node with a global playwright only")
class HeldWhileBusy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = run_page(SCRIPT, INIT)

    def test_page_runs_without_errors(self):
        self.assertNotIn("fatal", self.r, self.r.get("fatal"))
        self.assertEqual(self.r["errors"], [])

    def test_nothing_sent_while_busy(self):
        self.assertEqual(self.r["r"]["whileBusy"], [])

    def test_sent_once_done_as_one_follow_up(self):
        self.assertEqual(self.r["r"]["after"], [["please add milk and eggs too", True]])

    def test_not_busy_goes_straight_out(self):
        self.assertEqual(self.r["r"]["idle"], [["thanks a lot", True]])


if __name__ == "__main__":
    unittest.main()
