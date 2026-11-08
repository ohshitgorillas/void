---
phase: 5
plan: 2
requirements:
  - HEAR-03
  - HEAR-04
files:
  - app/server.py
  - app/static/index.html
  - tests/test_wake_loop.py
  - tests/test_page_played.py
  - tests/scenes.py
  - tests/test_scenes.py
---

# Phase 5: Own stop is echo - Plan 2: The page's player reports its played words, and scenes play through it

## Goal

When Void speaks through the page's own player, the server records the stop phrases he plays, timed on the Phase 4 record, so the same own-stop rule holds on both voice paths. The scene harness can play his line through the page's player as well as the native `Speaker`.

## Must be true when done

- The page's `/api/speaking` post that starts a sentence's sound in the record (`{"on": true, "left": s, "paid": 1}`) also carries that sentence's text, played length and word times, and no other post or route carries them
- The server notes that sentence's stop phrases timed from where its sound starts on the record: the end the post records, less the sentence's played length. `{"on": false}` removes every noted stop phrase that had not yet started
- A malformed or missing text, length or word-times field never fails the post, and never stops the post from updating the record
- A scene can play Void's line through the page's player. His sound reaches the room and `Wake.talked` through the server's own `/api/tts` and `/api/speaking` code, and his line heard back on that path is judged as it is on the native one

## Context

- Runs after Plan 1, in `/Users/atom/dev/void-own-stop` on `macos`. Uses Plan 1's `note_played`, `played_cut` and `played_lately` (look them up in `app/server.py`).
- Locked: D-02 (the page path's word offsets count from where `Wake.talked` records the sentence's sound starting; no second clock of his sound), D-05 (the played words ride the same `/api/speaking` post; the design's `POST /api/played` is not built; `sounding()` and the page's hold unchanged), D-07, D-08 (page tests on installed Chrome).
- The page's `pump` posts `{on: true, left, paid: 1}` with `left` = the sentence's end on the audio clock less `currentTime`, plus `outputLatency` or `baseLatency`. `dur` is `item.b.duration / r` there, and `X-Void-Words` holds seconds into the WAV as served, before the rate `r` (`app/server.py` `/api/tts`, `tidy_and_time`). `speaking` posts whatever the hearing settings are, and skips native voice (Phase 4).

## Tasks

### Task 1: The server takes a sentence's played words on the page's `/api/speaking` post

- **Files:** app/server.py (`Handler.do_POST`, the `/api/speaking` branch), tests/test_wake_loop.py
- **Action:** The `/api/speaking` body with `on` true may also carry `text` (the text the page posted to `/api/tts`), `dur` (the sentence's played length in seconds) and `words` (its `[start, end]` pairs in played seconds, or null). These are the field names the design gave its `/api/played` body. When `text` and `dur` are present, the branch calls `note_played` on `speakable(text)`, so its words line up with the ones `/api/tts` timed. The sentence's start is the end the branch hands `Wake.talking_until` for this post, less `dur`. That end, `now + left`, is where the record says this sentence's sound runs to (D-02). The post's arrival time is not the start: a sentence the page schedules behind the one still playing starts up to that sentence's length later. When `on` is false, the branch also calls `played_cut` at the time it ends the record, as `Wake.hush` does for the native path. Validate before use. A `text` that is not a string, or a `dur` that is not a positive finite number, notes nothing. `words` that are not a list of number pairs are treated as absent, so `note_played` spreads the words evenly. None of this may raise, and the record update and its reply happen whatever these fields hold. Add no route.
- **Verify:** `uvx --with-requirements tests/requirements.txt pytest tests/test_wake_loop.py -rsxX` in the worktree passes. Among the passes, over real HTTP posts to the loopback `Handler` this file already starts:
  - `{"on": true, "left": 1.2, "paid": 1, "text": "Okay, I'll stop.", "dur": 1.0, "words": [...]}` leaves one played "stop" whose start lies between `t_before + 0.2 + w` and `t_after + 0.2 + w`, where `w` is that word's offset and `t_before`/`t_after` are `time.monotonic()` around the post;
  - the same with `words` null or malformed spreads the words over `dur`, and the reply is 200;
  - a `text` with markdown is noted as `speakable` makes it;
  - an `on`-true post without `text` notes nothing and still records his sound;
  - `{"on": false}` removes a noted stop phrase that had not yet started and keeps one that had.
  `git grep -n "/api/played" app/` prints nothing. Testing scope: the branch's parsing, anchor and cut. The page's half is Task 2. Stop there.

### Task 2: The page sends each sentence's text, length and word times when it schedules it

- **Files:** app/static/index.html (`enqueue`, `pump`), tests/test_page_played.py
- **Action:** For page voice, `enqueue` keeps, with each queued item, the text it posted to `/api/tts`. When `pump` schedules a sentence, its existing `speaking({on:true,left,paid:1})` post also carries that `text`, its `dur`, and its `X-Void-Words` pairs each divided by the playback rate `r`, or null when the header was absent or did not parse. These are played seconds, as `dur` already is. Add no post and no function that posts. `sounding()`, `vrec`, `handing`, the captions (`capSpeak` still gets the undivided words and `r`), the native branch and `quietCheck`/`shush` stay as they are. Create `tests/test_page_played.py` on the `tests/test_page_idle.py` harness (`INIT`, `NODE_PATH`, `run_page`, installed Chrome through `LAUNCH`), reusing `tests/test_page_sound.py`'s `HEAD`/`TAIL` scene runner by import where it fits. Its init script wraps `fetch` to record `/api/speaking` bodies and the `/api/tts` request bodies. It answers `/api/tts` with a short WAV, an `X-Void-Words` header and an `X-Void-Rate` other than 1. That wrapper observes the page's own calls and is not a hearing double. Wait on `window.__loop.calls` as `tests/test_page_held.py` does.
- **Verify:** `uvx --with-requirements tests/requirements.txt pytest tests/test_page_played.py tests/test_page_sound.py tests/test_page_held.py -rsxX` in the worktree passes, with no page test skipped. Among the passes:
  - for two sentences enqueued with page voice, each `on`-true post carries the `text` that sentence's `/api/tts` request carried;
  - its `dur` equals the WAV's length over the rate to within 1 ms;
  - its `words` equal the header's pairs over the rate to within 1 ms;
  - with no header its `words` is null;
  - a sentence with no audio still posts `{paid: 1}` with no `text`;
  - the order of owe, on and off posts is as `tests/test_page_sound.py` asserts.
  Testing scope: what the page puts on the post. The existing page tests cover the hold and the record, and must stay green. Stop there.

### Task 3: A scene can play Void's line through the page's player

- **Files:** tests/scenes.py (`play`, `Scene`), tests/test_scenes.py, app/server.py (only where the `/api/tts` or `/api/speaking` branch body moves into a server function the route calls)
- **Action:** `play` gains a choice of voice path. The native `Speaker` stays the default and is unchanged. On the page path, a scene actor stands in for the page's player. It is room harness beside `FakePlayer`, not a hearing double. It does to the server what Task 2's page does, through the server's own code for `/api/tts` and `/api/speaking`, never a copy of their logic in the harness. If reaching that code from the simulated clock needs a route's body moved into a server function the route then calls, the move is part of this task and changes no route's behaviour. When the line is handed over, the actor runs the `/api/tts` work (`speakable`, `note_spoken`, `synth`, the word timing) and posts the owe. When it schedules the sentence, at hand-over plus the page's 0.05 s, it posts `on` true. That post's `left` runs to the sentence's end plus the speakers' latency (`scene.lat`), and it carries the `text`, `dur` and `words` Task 2's page sends. It puts the trimmed audio into the room from that moment plus `scene.lat`, and posts `on` false when the audio has played. The page's voice gives the echo canceller no reference, as in the app, so nothing is handed to `PlayRef`. The page path takes the arguments the own-stop scenes need (`void`, `you`, `you_at`, `you_only`, `hear`, `seconds`). Any other argument given with it raises `ValueError` rather than being ignored. In `tests/test_scenes.py`, add page-path runs of `test_him_talking_alone_does_nothing`, `test_his_line_heard_back_while_it_plays_is_dropped_as_echo`, and the fast tier's `interrupt_stop` cut-in.
- **Verify:** `uvx --with-requirements tests/requirements.txt pytest tests/test_scenes.py -rsxX` in the worktree passes, with the native scenes' counts as in Plan 1 Task 1's baseline. Among the passes:
  - on the page path, no fake player is opened;
  - the `voice` events show his sound recorded from the page's posts, with `owed` back to 0 at the end;
  - his line alone gives no `barge` or `wake` event;
  - his line heard back while it plays is judged "echo";
  - the owner's "Stop, stop." over him gives a `barge` event.
  `git diff S -- app/server.py` shows any moved route body called from its route, with that route's tests in `tests/test_wake_loop.py` still passing. Testing scope: the page path proven end to end on existing clips. Own stop on it is Plan 3's. Stop there.

## Notes

- Plans run in order; this one shares `app/server.py`, `tests/test_wake_loop.py`, `tests/scenes.py` and `tests/test_scenes.py` with Plans 1 and 3.
- Choice (CONTEXT's flagged assumption on where the page path's word times come from): the page echoes back the `X-Void-Words` the server's `/api/tts` computed, divided by the rate it plays at. The server cannot compute played times itself, because only the page knows its playback rate and when it schedules. The pairs are the server's own `tidy_and_time` output, and `note_played` falls back to spreading the words evenly when their count does not match the text.
- Choice (D-02): the page path's start is derived from the record's own end for that post (`now + left - dur`), because `left` is measured from the same audio clock that schedules the sentence. This adds no second clock of his sound.
- The page-player stand-in lives in `tests/scenes.py` with `FakePlayer`, `FakeMic` and `Room`. D-08's "test doubles only in `tests/fakes.py`" is read as the hearing doubles (Whisper, speech detection, `Heard`), the reading Phase 4 held for the scene harness.
