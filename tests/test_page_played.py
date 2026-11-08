"""What the page puts on the `/api/speaking` post that starts a sentence's sound in the record: the text it posted to
`/api/tts`, the sentence's played length (`dur`) and the `X-Void-Words` pairs in played seconds (divided by the playback
rate), or null when the header was absent or did not parse. A sentence with no audio still posts {paid: 1} alone.
The real page in headless Chromium (Playwright under node), from file://: there is no server, so `fetch` is wrapped to
keep the page's own `/api/speaking` bodies and `/api/tts` requests and to answer `/api/tts` with a short clip (an
observation of what the page does, not a stand-in for any hearing).

    python3 -m unittest discover -s tests
"""
import unittest

from test_page_idle import INIT, NODE_PATH, run_page
from test_page_sound import HEAD, TAIL

CLIP = 0.4          # s: the clip's length as served
RATE = 1.25         # what X-Void-Rate says, so the played length is CLIP / RATE

# __s.words: 'header' (one pair per word of the text, spread over the clip) · 'none' (no X-Void-Words) · 'bad' (not JSON)
PINIT = r"""(() => {
  const f = window.fetch && window.fetch.bind(window);
  const S = window.__s = {posts: [], tts: [], mode: 'audio', words: 'header'};
  const wav = () => { const n = 3200, b = new ArrayBuffer(44 + n * 2), v = new DataView(b);   // 0.4 s, 8 kHz, mono, silence
    const w = (o, s) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
    w(0, 'RIFF'); v.setUint32(4, 36 + n * 2, true); w(8, 'WAVE'); w(12, 'fmt '); v.setUint32(16, 16, true);
    v.setUint16(20, 1, true); v.setUint16(22, 1, true); v.setUint32(24, 8000, true); v.setUint32(28, 16000, true);
    v.setUint16(32, 2, true); v.setUint16(34, 16, true); w(36, 'data'); v.setUint32(40, n * 2, true); return b; };
  window.fetch = (u, o) => { const url = String(u);
    if (url.includes('/api/speaking')) S.posts.push(JSON.parse(o.body));
    if (url.includes('/api/tts')) { const text = JSON.parse(o.body).text; S.tts.push(text);
      if (S.mode !== 'audio') return Promise.resolve(new Response(null, {status: 204}));
      const h = {'X-Void-Rate': '1.25', 'X-Void-Pause': '0.08'}, n = text.split(/\s+/).length;
      if (S.words === 'header') h['X-Void-Words'] = JSON.stringify(Array.from({length: n}, (_, i) => [i * 0.4 / n, (i + 1) * 0.4 / n]));
      if (S.words === 'bad') h['X-Void-Words'] = 'not json';
      return Promise.resolve(new Response(wav(), {status: 200, headers: h})); }
    return f ? f(u, o) : Promise.reject(new Error('no fetch')); };
})();"""


def scene_js(key, setup, texts):
    """One scene: page voice with the hearing settings off, `setup` run in the page, each text enqueued, and the page's
    posts and /api/tts requests read once his sound is over (or, with no audio, the queue has run dry)."""
    return f"""
  await scene({key!r}, async () => {{
    const S = window.__s, wait = ms => new Promise(r => setTimeout(r, ms));
    info.wake_word = false; info.barge_in = false; info.voice_native = false;
    {setup}
    for (const t of {texts!r}.map(String)) enqueue(t);
    for (let i = 0; i < 100 && !S.posts.some(x => x.on === false); i++) await wait(100);
    await wait(200);
    return {{posts: S.posts.slice(), tts: S.tts.slice()}};
  }});"""


SCRIPT = (HEAD
          + scene_js("header", "", ["Okay, I will stop.", "Then we carry on."])
          + scene_js("absent", "S.words = 'none';", ["No word times came with this one."])
          + scene_js("bad", "S.words = 'bad';", ["The word times here are not JSON."])
          + scene_js("noaudio", "S.mode = 'none';", ["Nothing comes back for this one."])
          + TAIL)


def on_posts(posts):
    return [p for p in posts if p.get("on") is True]


@unittest.skipUnless(NODE_PATH, "node with a global playwright only")
class PagePostsItsPlayedWords(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = run_page(SCRIPT, INIT + PINIT)

    def scene(self, key):
        self.assertNotIn(key, self.r["broken"], self.r["broken"].get(key))
        self.assertIn(key, self.r, f"{key}: no result")
        return self.r[key]

    def test_scenes_run_without_errors(self):
        self.assertEqual(self.r["broken"], {})
        self.assertEqual(self.r["errors"], [])

    def test_each_sentence_s_post_carries_the_text_its_tts_request_carried(self):
        r = self.scene("header")
        self.assertEqual(r["tts"], ["Okay, I will stop.", "Then we carry on."])
        self.assertEqual([p["text"] for p in on_posts(r["posts"])], r["tts"])

    def test_dur_is_the_clip_s_length_over_the_rate(self):
        for p in on_posts(self.scene("header")["posts"]):
            self.assertAlmostEqual(p["dur"], CLIP / RATE, delta=0.001)

    def test_words_are_the_header_s_pairs_over_the_rate(self):
        posts = on_posts(self.scene("header")["posts"])
        for p, n in zip(posts, (4, 4)):
            want = [[i * CLIP / n / RATE, (i + 1) * CLIP / n / RATE] for i in range(n)]
            self.assertEqual(len(p["words"]), n)
            for got, w in zip(p["words"], want):
                self.assertAlmostEqual(got[0], w[0], delta=0.001)
                self.assertAlmostEqual(got[1], w[1], delta=0.001)

    def test_no_header_or_one_that_does_not_parse_gives_null_words(self):
        for key in ("absent", "bad"):
            posts = on_posts(self.scene(key)["posts"])
            self.assertEqual(len(posts), 1, key)
            self.assertIn("words", posts[0])
            self.assertIsNone(posts[0]["words"], key)
            self.assertAlmostEqual(posts[0]["dur"], CLIP / RATE, delta=0.001)

    def test_a_sentence_with_no_audio_posts_paid_alone(self):
        self.assertEqual(self.scene("noaudio")["posts"], [{"owe": 1}, {"paid": 1}, {"on": False}])

    def test_the_posts_keep_the_order_owe_on_off(self):
        posts = self.scene("header")["posts"]
        self.assertEqual([sorted(k for k in p if k not in ("text", "dur", "words")) for p in posts],
                         [["owe"], ["owe"], ["left", "on", "paid"], ["left", "on", "paid"], ["on"]], posts)
        self.assertIs(posts[4]["on"], False)
        self.assertNotIn("text", posts[0])


if __name__ == "__main__":
    unittest.main()
