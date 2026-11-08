"""You answer Void while he's still working on the last thing (over him, or between his sentences): the page keeps
what you said and sends it as a follow-up once his reply is done, instead of throwing it away.
The real page in headless Chromium (Playwright under node), from file://: its fetches just fail.

    python3 -m unittest discover -s tests
"""
import unittest

from test_page_idle import INIT, NODE_PATH, run_page
from test_page_sound import SINIT

SCRIPT = r"""const { chromium } = require('playwright');
(async () => {
  const out = {errors: []}, b = await chromium.launch(LAUNCH);
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


# "A reply waits for him, on the page": a follow-up kept while he works or while he is still speaking is held, never
# shush()ed, and goes out as one follow-up once he is done working and the server's record of his sound has ended; only a
# barge stops him. "He is still speaking" is the record fed to the page through onEvent (a 'voice' event: left · owed · n):
# sound ahead, or a sentence owed that has not begun to sound (the pause between two sentences while the next is made),
# and the page's native voice besides. send is stubbed, shush is counted (and still runs) by stage, and the page's
# /api/say/stop posts are kept (the wrapped fetch of test_page_sound).
MODES = ("ahead", "owed", "native")
WSCRIPT = r"""const { chromium } = require('playwright');
(async () => {
  const MODES = ['ahead', 'owed', 'native'];
  // a scene that throws is recorded under out.broken (never out.fatal, which would skip the whole class)
  const out = {errors: [], broken: {}}, b = await chromium.launch(LAUNCH);
  const scene = async (name, mode, body, real) => {
    const key = name + '/' + mode;
    try {
      const p = await b.newPage({viewport: {width: 340, height: 460}});
      p.on('pageerror', e => out.errors.push(key + ': ' + String(e && e.message || e)));
      await p.addInitScript(INIT);
      await p.goto('file://' + PAGE);
      await p.waitForFunction(() => typeof onEvent === 'function' && window.__loop.calls > 5, null, {timeout: 10000});
      await p.evaluate(([mode, real]) => {
        const H = window.__h = {sent: [], shush: [], stage: 'start', n: 0};
        if (!real) window.send = (text, opts) => { H.sent.push([H.stage, text, !!(opts && opts.follow)]); };
        const orig = window.shush;
        window.shush = function () { H.shush.push(H.stage); return orig.apply(this, arguments); };
        // the record, newest copy each time; his voice still to come as 'ahead' (sound runs on), 'owed' (the next
        // sentence is still being made) or 'native' (sound ahead, and the page's native player holds a sentence too)
        H.feed = (left, owed) => onEvent({t: 'voice', left, owed, n: ++H.n});
        H.speak = () => { if (mode === 'owed') H.feed(0, 1); else H.feed(60, 0);
          if (mode === 'native') { info.voice_native = true; playing = true; spkMap.set(7, {cap: '', fresh: false}); } };
        H.hush = () => { H.feed(0, 0); spkMap.delete(7); };            // the record ends (the player's own state follows)
        H.rest = () => sounding();
      }, [mode, !!real]);
      out[key] = await p.evaluate(body);
      await p.close();
    } catch (e) { out.broken[key] = String(e && e.stack || e); }
  };
  for (const mode of MODES) {
    // 1: two follow-ups while he works and speaks; he stops working, still speaking; then his sound ends
    await scene('working', mode, async () => {
      const H = window.__h, wait = ms => new Promise(r => setTimeout(r, ms));
      busy = true; H.speak(); H.stage = 'working';
      onEvent({t: 'wake', follow: true, text: 'please add milk'});
      onEvent({t: 'wake', follow: true, text: 'and eggs too'});
      await wait(800); const working = H.sent.slice(), stillPlaying = H.rest();
      busy = false; H.stage = 'speaking';
      await wait(800); const speaking = H.sent.slice();
      H.hush(); H.stage = 'quiet';
      await wait(800);
      return {working, stillPlaying, speaking, sent: H.sent.slice(), shush: H.shush.slice(), stops: window.__s.stops.slice()};
    });
    // 2: a follow-up while he is not working but still speaking; then his sound ends
    await scene('speaking', mode, async () => {
      const H = window.__h, wait = ms => new Promise(r => setTimeout(r, ms));
      busy = false; H.speak(); H.stage = 'speaking';
      onEvent({t: 'wake', follow: true, text: 'can you hear me'});
      await wait(800); const speaking = H.sent.slice(), stillPlaying = H.rest();
      H.hush(); H.stage = 'quiet';
      await wait(800);
      return {speaking, stillPlaying, sent: H.sent.slice(), shush: H.shush.slice(), stops: window.__s.stops.slice()};
    });
  }
  // 3: he is quiet and not working: straight out
  await scene('quiet', 'ahead', async () => {
    const H = window.__h, wait = ms => new Promise(r => setTimeout(r, ms));
    onEvent({t: 'wake', follow: true, text: 'thanks a lot'});
    await wait(500);
    return {sent: H.sent.slice(), shush: H.shush.slice()};
  });
  // 4: the pause between two sentences, not working: a reply kept while the next is still being made (owed, no sound
  // yet) is not sent; nor while that sentence sounds; it goes out once that sound has ended
  await scene('pause', 'ahead', async () => {
    const H = window.__h, wait = ms => new Promise(r => setTimeout(r, ms)), r = {};
    busy = false; H.feed(0, 1); H.stage = 'owed';
    onEvent({t: 'wake', follow: true, text: 'yes do it'});
    await wait(800); r.owed = H.sent.slice();
    H.stage = 'sounding'; H.feed(0.8, 0);                              // the sentence begins: sound ahead, nothing owed
    await wait(400); r.sounding = H.sent.slice();
    H.stage = 'ended';
    await wait(1500); r.sent = H.sent.slice(); r.shush = H.shush.slice();
    return r;
  });
  // 5: a follow-up held while he works and speaks, then a barge over him (the record still holds his sound)
  await scene('barge', 'ahead', async () => {
    const H = window.__h, wait = ms => new Promise(r => setTimeout(r, ms));
    busy = true; playing = true; H.speak(); H.stage = 'held';
    onEvent({t: 'wake', follow: true, text: 'one more thing'});
    await wait(500); const before = sounding();
    H.stage = 'barge';
    onEvent({t: 'barge'});
    await wait(300);
    return {shush: H.shush.slice(), before};
  });
  // 6: send itself: a follow-up never shushes him, every other road through it does (the page's fetches fail: no server)
  await scene('send', 'ahead', async () => {
    const H = window.__h;
    H.stage = 'follow'; await send('thanks a lot', {follow: true}); const follow = H.shush.slice();
    busy = false; H.stage = 'typed'; await send('thanks a lot'); const typed = H.shush.slice();
    return {follow, typed};
  }, true);
  await b.close(); process.stdout.write(JSON.stringify(out));
})();"""


@unittest.skipUnless(NODE_PATH, "node with a global playwright only")
class WaitsForHim(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = run_page(WSCRIPT, INIT + SINIT)

    def scenes(self, name, modes=MODES):
        """Each way he can still be speaking (sound ahead, a sentence owed, native voice besides), its result."""
        for mode in modes:
            self.assertNotIn(f"{name}/{mode}", self.r["broken"], self.r["broken"].get(f"{name}/{mode}"))
            self.assertIn(f"{name}/{mode}", self.r, f"{name}/{mode}: no result")
        return [self.r[f"{name}/{mode}"] for mode in modes]

    def one(self, name, mode="ahead"):
        return self.scenes(name, (mode,))[0]

    def test_waits_scenes_run_without_errors(self):
        self.assertEqual(self.r["broken"], {})
        self.assertEqual(self.r["errors"], [])

    def test_held_while_working_not_sent_and_answer_not_cut_off(self):
        for w in self.scenes("working"):
            self.assertEqual(w["working"], [])
            self.assertEqual(w["shush"], [])
            self.assertEqual(w["stops"], [])
            self.assertTrue(w["stillPlaying"])

    def test_held_while_working_waits_until_his_sound_has_ended(self):
        for w in self.scenes("working"):
            self.assertEqual(w["speaking"], [])

    def test_held_while_working_goes_out_as_one_follow_up_once_quiet(self):
        for w in self.scenes("working"):
            self.assertEqual(w["sent"], [["quiet", "please add milk and eggs too", True]])
            self.assertEqual(w["shush"], [])

    def test_kept_while_speaking_not_sent_and_speech_not_cut_off(self):
        for s in self.scenes("speaking"):
            self.assertEqual(s["speaking"], [])
            self.assertEqual(s["shush"], [])
            self.assertEqual(s["stops"], [])
            self.assertTrue(s["stillPlaying"])

    def test_kept_while_speaking_goes_out_once_his_sound_has_ended(self):
        for s in self.scenes("speaking"):
            self.assertEqual(s["sent"], [["quiet", "can you hear me", True]])

    def test_quiet_and_not_working_goes_straight_out(self):
        q = self.one("quiet")
        self.assertEqual(q["sent"], [["start", "thanks a lot", True]])
        self.assertEqual(q["shush"], [])

    def test_a_reply_in_the_pause_between_two_sentences_waits_for_the_one_being_made(self):
        r = self.one("pause")
        self.assertEqual(r["owed"], [])                       # (his next sentence is owed, not yet sounding)
        self.assertEqual(r["sounding"], [])                   # (it sounds)
        self.assertEqual(r["sent"], [["ended", "yes do it", True]])
        self.assertEqual(r["shush"], [])

    def test_barge_is_what_stops_him_mid_speech(self):
        g = self.one("barge")
        self.assertNotIn("held", g["shush"])               # still speaking with a follow-up held ...
        self.assertTrue(g["before"])
        self.assertIn("barge", g["shush"])                 # ... until the barge stops him (shush(), on a barge)

    def test_send_never_shushes_a_follow_up_and_still_shushes_every_other_road(self):
        g = self.one("send")
        self.assertEqual(g["follow"], [])
        self.assertEqual(g["typed"], ["typed"])



if __name__ == "__main__":
    unittest.main()
