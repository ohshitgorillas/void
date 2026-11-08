"""The page's own voice, told to the server's record of when Void is making sound: each sentence it is handed (an owe),
each it schedules (a pay, with how long its sound runs) or finds has no audio (a pay), and the queue running dry
(on: false), in the order the page made them, whatever the hearing settings are. And the page's one test of "is he making
sound", sounding(), which reads that record (the newest copy the server sent) and nothing of the player's own state.
The real page in headless Chromium (Playwright under node), from file://: there is no server, so the record is fed to
the page through onEvent, and the page's own /api/speaking posts are recorded by wrapping fetch (an observation of
what the page does, not a stand-in for any hearing).

    python3 -m unittest discover -s tests
"""
import unittest

from test_page_idle import INIT, NODE_PATH, run_page

# fetch, wrapped: every /api/speaking post's body is kept in order, and /api/tts gives a short silent clip while
# __s.tts is 'audio' (else it fails, as from file://: a sentence with no audio). Nothing else is touched.
SINIT = r"""(() => {
  const f = window.fetch && window.fetch.bind(window);
  const S = window.__s = {posts: [], tts: 'audio'};
  const wav = () => { const n = 3200, b = new ArrayBuffer(44 + n * 2), v = new DataView(b);   // 0.4 s, 8 kHz, mono, silence
    const w = (o, s) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
    w(0, 'RIFF'); v.setUint32(4, 36 + n * 2, true); w(8, 'WAVE'); w(12, 'fmt '); v.setUint32(16, 16, true);
    v.setUint16(20, 1, true); v.setUint16(22, 1, true); v.setUint32(24, 8000, true); v.setUint32(28, 16000, true);
    v.setUint16(32, 2, true); v.setUint16(34, 16, true); w(36, 'data'); v.setUint32(40, n * 2, true); return b; };
  window.fetch = (u, o) => { const url = String(u);
    if (url.includes('/api/speaking')) S.posts.push(JSON.parse(o.body));
    if (url.includes('/api/tts') && S.tts === 'audio')
      return Promise.resolve(new Response(wav(), {status: 200, headers: {'X-Void-Rate': '1', 'X-Void-Pause': '0.08'}}));
    return f ? f(u, o) : Promise.reject(new Error('no fetch')); };
})();"""

# one page per scene: the scene's body runs in the page after it has loaded
HEAD = r"""const { chromium } = require('playwright');
(async () => {
  const out = {errors: [], broken: {}}, b = await chromium.launch(Object.assign({args: ['--autoplay-policy=no-user-gesture-required']}, LAUNCH));
  const scene = async (key, body) => {
    try {
      const p = await b.newPage({viewport: {width: 340, height: 460}});
      p.on('pageerror', e => out.errors.push(key + ': ' + String(e && e.message || e)));
      await p.addInitScript(INIT);
      await p.goto('file://' + PAGE);
      await p.waitForFunction(() => typeof onEvent === 'function' && window.__loop.calls > 5, null, {timeout: 10000});
      out[key] = await p.evaluate(body);
      await p.close();
    } catch (e) { out.broken[key] = String(e && e.stack || e); }
  };
"""
TAIL = r"""
  await b.close(); process.stdout.write(JSON.stringify(out));
})();"""

SOUND = HEAD + r"""
  // page voice plays two scheduled sentences, with the hearing settings both off
  await scene('two', async () => {
    const S = window.__s, wait = ms => new Promise(r => setTimeout(r, ms));
    info.wake_word = false; info.barge_in = false; info.voice_native = false;
    enqueue('The first sentence is here.'); enqueue('And the second sentence follows.');
    for (let i = 0; i < 100 && !S.posts.some(x => x.on === false); i++) await wait(100);
    await wait(200);
    return {posts: S.posts.slice()};
  });
  // a sentence whose /api/tts gives no audio
  await scene('none', async () => {
    const S = window.__s, wait = ms => new Promise(r => setTimeout(r, ms));
    S.tts = 'none'; enqueue('Nothing comes back for this one.');
    await wait(1000);
    return {posts: S.posts.slice()};
  });
""" + TAIL

# the server's record fed to the page through onEvent (a 'voice' event: left · owed · n), as the page gets it from the server
RECORD = HEAD + r"""
  // sounding() reads the record and nothing of the player's own state
  await scene('record', async () => {
    const wait = ms => new Promise(r => setTimeout(r, ms)), r = {};
    r.page0 = [playing, q.length, spkMap.size, sounding()];
    onEvent({t: 'voice', left: 0.6, owed: 0, n: 1}); r.ahead = sounding();
    await wait(300); r.mid = sounding();
    await wait(600); r.ended = sounding();
    onEvent({t: 'voice', left: 0, owed: 1, n: 2}); r.owed = sounding();
    onEvent({t: 'voice', left: 0, owed: 0, n: 1}); r.stale = sounding();            // an older copy: nothing changes
    playing = true; spkMap.set(99, {cap: '', fresh: false});
    onEvent({t: 'voice', left: 0, owed: 0, n: 3}); r.page1 = [playing, q.length, spkMap.size, sounding()];
    return r;
  });
  // askAloud's untilQuiet, straight after enqueue, waits for his question to play
  await scene('until', async () => {
    const S = window.__s, wait = ms => new Promise(r => setTimeout(r, ms)), r = {};
    S.tts = 'none'; let done = null;
    enqueue('Can I run this for you?'); onEvent({t: 'voice', left: 0, owed: 1, n: 10});
    untilQuiet().then(() => { done = performance.now(); });
    await wait(1000); r.after1s = done;
    for (let i = 0; i < 50 && !S.posts.some(x => x.paid === 1 && !x.on); i++) await wait(50);
    await wait(500); r.afterPaid = done; r.paid = S.posts.some(x => x.paid === 1 && !x.on);
    const t0 = performance.now(); onEvent({t: 'voice', left: 0, owed: 0, n: 11});
    for (let i = 0; i < 20 && done === null; i++) await wait(50);
    r.lag = done === null ? null : done - t0;
    return r;
  });
""" + TAIL


@unittest.skipUnless(NODE_PATH, "node with a global playwright only")
class PageTellsItsSound(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = run_page(SOUND, INIT + SINIT)

    def scene(self, key):
        self.assertNotIn(key, self.r["broken"], self.r["broken"].get(key))
        self.assertIn(key, self.r, f"{key}: no result")
        return self.r[key]

    def test_scenes_run_without_errors(self):
        self.assertEqual(self.r["broken"], {})
        self.assertEqual(self.r["errors"], [])

    def test_each_sentence_handed_over_is_owed_before_any_sound(self):
        self.assertEqual(self.scene("two")["posts"][:2], [{"owe": 1}, {"owe": 1}])

    def test_posts_follow_the_order_the_page_made_them_with_the_hearing_settings_off(self):
        posts = self.scene("two")["posts"]
        self.assertEqual([sorted(p) for p in posts],
                         [["owe"], ["owe"], ["left", "on", "paid"], ["left", "on", "paid"], ["on"]], posts)
        for p in posts[2:4]:
            self.assertIs(p["on"], True)
            self.assertEqual(p["paid"], 1)
            self.assertGreater(p["left"], 0)
        self.assertIs(posts[4]["on"], False)

    def test_a_sentence_with_no_audio_is_owed_then_paid(self):
        self.assertEqual(self.scene("none")["posts"], [{"owe": 1}, {"paid": 1}, {"on": False}])   # (then the queue runs dry)


@unittest.skipUnless(NODE_PATH, "node with a global playwright only")
class SoundingReadsTheRecord(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = run_page(RECORD, INIT + SINIT)

    def scene(self, key):
        self.assertNotIn(key, self.r["broken"], self.r["broken"].get(key))
        self.assertIn(key, self.r, f"{key}: no result")
        return self.r[key]

    def test_scenes_run_without_errors(self):
        self.assertEqual(self.r["broken"], {})
        self.assertEqual(self.r["errors"], [])

    def test_sound_ahead_holds_until_the_reported_end_with_the_player_idle(self):
        r = self.scene("record")
        self.assertEqual(r["page0"], [False, 0, 0, False])
        self.assertTrue(r["ahead"])
        self.assertTrue(r["mid"])
        self.assertFalse(r["ended"])

    def test_a_sentence_owed_keeps_it_true_with_no_sound_ahead(self):
        self.assertTrue(self.scene("record")["owed"])

    def test_an_older_copy_changes_nothing(self):
        self.assertTrue(self.scene("record")["stale"])

    def test_player_state_does_not_decide_it(self):
        self.assertEqual(self.scene("record")["page1"], [True, 0, 1, False])

    def test_until_quiet_after_enqueue_waits_for_the_record_not_the_hand_off_or_the_pay(self):
        r = self.scene("until")
        self.assertIsNone(r["after1s"], r)
        self.assertTrue(r["paid"], r)                        # (the page's own pay went out: it is not what ends the wait)
        self.assertIsNone(r["afterPaid"], r)
        self.assertIsNotNone(r["lag"], r)
        self.assertLess(r["lag"], 300, r)


if __name__ == "__main__":
    unittest.main()
