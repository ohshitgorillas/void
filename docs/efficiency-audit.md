# Void efficiency audit (idle, listening, talking)

Base: origin/macos @ 248e46b. Nothing here changes code.

## What was measured vs inferred
- **Measured** (Linux, headless Chromium 1194, software rendering, 4 cores, page served without the server):
  the face page idles at **4.5 CPU-seconds per 10 s (≈45% of one core)** at a steady 60 fps.
  With every SVG `filter` removed: **2.6 s (≈26%)**. With `requestAnimationFrame` stubbed out: **0.13 s (≈1%)**.
  CDP metrics: 601 style recalcs + 601 layouts in 10 s, i.e. one full recalc/layout per frame.
- **Measured**: the Python RMS per 40 ms mic frame costs ~37 µs (≈0.1% of a core). Not worth touching.
- **Inferred from code** (not run): everything else below, including all Mac/Windows numbers, memory, and wakeups.
  The 37% Mac figure is the owner's; my headless number is a different setup but points the same way.

## Ranked by payoff for an always-on laptop app

1. **Face animates at 60 fps forever, even idle or hidden.** `app/static/index.html:1071-1264` (`frame()`
   re-queues itself at 1262 with no exit). Every frame rewrites ~60+ SVG attributes (40 orb lines 1194-1222,
   eye paths 1157/1166, voice ring 1179-1182, transforms), forcing style+layout+repaint of blurred layers.
   `voidHidden()` (2760) sets `hiddenNow` but the loop never checks it. Costs CPU, GPU and battery all the time.
   Fix: (a) stop the loop in `voidHidden`/`visibilitychange`, restart in `voidShown` — ~10 lines, removes all
   cost while hidden. (b) when idle (mood idle, no fidget, no mic/speaker level, no particles), drop to ~20-30 fps
   or pause between fidgets/blinks with a `setTimeout` — ~30-60 lines, likely halves idle cost. **Biggest win.**
2. **Blur filters repainted every frame.** `index.html:461,471,485,493` (`feGaussianBlur` glow/goo) on
   `orbBack/orbFront/vring/workW` and the notch goo. Measured ≈42% of idle page CPU. The auto fallback at 1073-1074
   only trips when frames exceed 32 ms, which a fast Mac never hits, so it never helps there.
   Fix: drop the glow while idle, or fake it with a static pre-blurred halo / CSS `drop-shadow` on a non-moving
   group; keep goo only during the morph. ~20-40 lines.
3. **Wake word is on by default and runs whisper on any sound.** `app/server.py:157` (`wake_word: True`),
   loop 1342-1408, `check()` 1410-1435. The mic stays open whenever shown; every voiced segment ≥0.35 s
   (up to 12 s, line 1394) is sent to faster-whisper (beam 1) just to look for "hey Void". With a TV, music,
   calls or people talking nearby this means near-continuous whisper inference on CPU, plus the mic indicator
   and audio hardware never sleeping. Fix, cheap: cap wake checks to the first ~2.5 s of a segment and skip
   segments that start mid-speech — ~10 lines. Fix, proper: gate with a tiny keyword model (openWakeWord /
   Porcupine, a few ms per frame) and only call whisper after a hit — ~100-200 lines plus a model file.
4. **Models kept warm for the whole session.** Whisper loaded at start (`server.py:3412`, base.en on CPU,
   small.en on CUDA); TTS warmed at start (`warm_tts` 1759 → Kokoro 1660 or piper 1738 stay in memory).
   Likely a few hundred MB of RAM resident forever. Whisper is needed while wake word is on; Kokoro/piper are not.
   Fix: load TTS on first speech and drop it after ~10 min unused; unload whisper when wake word is off and idle.
   ~30 lines.
5. **Window mouse poll 30×/s forever (Qt: Mac + Windows).** `app/window_win.py:310-312` 33 ms PreciseTimer;
   `_poll_mouse` 642 still fires while hidden (646) and runs ~120×/s in hover mode. That is 30+ wakeups/s that
   stop the CPU from deep-idling. Fix: stop the timer in `hide_me` (663), start in `show_me`; use a coarse timer
   when the cursor is far from his rects. ~10-20 lines.
6. **Page timers that never stop.** `index.html:2484` `convoCheck` every 50 ms (20 wakeups/s) though it only
   matters in bar mode; `2818` `sendRegion` every 400 ms (layout reads + JSON); `3036` `/api/state` every 15 s.
   Fix: run `convoCheck` from `frame()` or only in bar mode; make `sendRegion` event-driven (it already has
   resize/transitionend hooks); pause all three while hidden. ~20 lines.
7. **`/api/state` redoes discovery every 15 s.** `state_info()` `server.py:2817-2847` calls `tts_engine()`
   (find_spec + voices glob), `mic_cmds()` (`shutil.which` ×3 on Linux), `claude_bin()`, six `shutil.which`
   for screenshot tools (2835), and `mem_load()` re-reads memory.json (277). Small each time, but it is PATH
   scanning and disk reads forever. Fix: cache these, refresh on settings change. ~20 lines.
8. **Wake loop polls while asleep.** `server.py:1344-1346` sleeps 0.2 s in a loop when it should not run
   (hidden, busy) — 5 wakeups/s. Fix: wait on an Event set by `/api/sleep` and config changes. ~10 lines.
9. **Mic callback every 20 ms.** `app/winsys.py:252` `blocksize=rate*0.02` (Mac/Windows) → 50 callbacks/s
   while the mic is open. Fix: 80-100 ms blocks for wake-word sessions. ~3 lines; small battery win.
10. **One `claude -p` process per approval prompt.** `server.py:463` spawns a full Claude Code (Node start-up,
    tens of MB, network) to describe a command. Only on approvals. Fix: cache by command text, or ask the live
    brain. ~15 lines; low payoff.
11. **Talking fallback: piper CLI per sentence.** `server.py:1712-1723` reloads the voice model every sentence
    when in-process piper is unavailable (and may try two flag spellings first). Only when that fallback is hit.
12. **Minor:** `rms()` allocates a new Float32Array every frame (`index.html:984`) — reuse one buffer, 2 lines.
    `hist_load` re-reads the whole history file per call (`server.py:319`) — fine unless called often.
    WebKitGTK forced repaint every frame (`index.html:1259-1260`) is Linux-only, but doubles the cost there.

## Per state, in short
- **Idle, shown:** items 1, 2, 5, 6, 7 always; 3 whenever there is sound in the room. 1+2 dominate.
- **Hidden:** 1 may keep running (depends on whether the webview throttles hidden pages — not verified on Mac),
  5, 6, 8 keep waking the CPU. Mic is closed (`/api/sleep`, 2951). Items 1, 5, 6 are the cheap fixes here.
- **Listening:** Python per-frame work is negligible (measured). Face loop as above plus mic levels.
- **Talking:** TTS synthesis is the real work and is fine when in-process; barge-in keeps the wake loop and
  whisper running on his own voice through the speakers (1338) — another reason for item 3's gate.

## Suggested order
Items 1a, 5, 6, 8 first (an hour, no visual change). Then 1b + 2 (needs eyeballing the look). Then 3 and 4.
