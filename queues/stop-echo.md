design docs/superpowers/specs/own-stop-design.md | order docs/superpowers/specs/own-stop-design.md | main 3ef6fbc
section s1 | lead | steps: 1, 2 | size: lead: tokens: 1078253.8 seconds: 682.0 overruns: 0 refusals: 0
  s1.d1 | builder | steps: 1 | writes: app/gate.py, app/server.py | size: builder: tokens: 311441.7 seconds: 169.4 overruns: 0 refusals: 0
    queue /Users/atom/dev/void/queues/stop-echo.md s1.d1
    stub
    design: docs/superpowers/specs/own-stop-design.md
    step: 1
    paths: app/gate.py, app/server.py
    check: app/gate.py and app/server.py import with the step's Modules signatures raise-only
  s1.d2 | test-writer | steps: 2 | writes: tests/fakes.py, tests/test_echo.py | size: test-writer: tokens: 563646.7 seconds: 168.2 overruns: 0 refusals: 0
    queue /Users/atom/dev/void/queues/stop-echo.md s1.d2
    red
    design: docs/superpowers/specs/own-stop-design.md step 2
    behavior: The self-trigger first: Void plays a line with a stop phrase, the mic hears that phrase back while it plays and in the ring after, through `Wake.stop_in` and `Wake.check`, and Void is not stopped
    view: stubgen .pyi of app/server.py
    behavior: then the owner's stop said while Void talks, soon after Void's own stop phrase, barges.
    view: stubgen .pyi of app/server.py
  s1.d3 | test-writer | steps: 2 | writes: tests/test_gate.py | size: test-writer: tokens: 563646.7 seconds: 168.2 overruns: 0 refusals: 0
    queue /Users/atom/dev/void/queues/stop-echo.md s1.d3
    red
    design: docs/superpowers/specs/own-stop-design.md step 2
    behavior: each run of consecutive words making up a STOP_PHRASES phrase (case and punctuation aside), as one Word
    view: stubgen .pyi of app/gate.py
    behavior: a played stop phrase overlaps [a - ECHO_WORD, b + ECHO_WORD]
    view: stubgen .pyi of app/gate.py
    behavior: heard holds a stop phrase, and every one overlaps a played one widened by ECHO_WORD
    view: stubgen .pyi of app/gate.py
    behavior: Any stop phrase matches any other
    view: stubgen .pyi of app/gate.py
    behavior: A stop phrase the owner says within `ECHO_WORD` of Void playing one is taken as Void's; past that, it barges.
    view: stubgen .pyi of app/gate.py
    behavior: `judge` step 2, echo, becomes: `is_echo(text, spoken)`, or, for every kind but `"listen"`, `b.words` not None and `own_stop(b.words, played)`
    view: stubgen .pyi of app/gate.py
  s1.d4 | test-writer | steps: 2 | writes: tests/test_wake_loop.py | size: test-writer: tokens: 563646.7 seconds: 168.2 overruns: 0 refusals: 0
    queue /Users/atom/dev/void/queues/stop-echo.md s1.d4
    red
    design: docs/superpowers/specs/own-stop-design.md step 2
    behavior: `note_played` is its one writer: it times each word of `langmark.unmark(text).split()` from `start` plus that word's `[start, end]` pair, or with `words` None spreads the words evenly over `dur`, and keeps `gate.stop_phrases` of the result.
    view: stubgen .pyi of app/server.py
    behavior: `played_lately` drops entries that ended more than `ECHO_KEEP` ago and returns the rest.
    view: stubgen .pyi of app/server.py
    behavior: Native path: `Speaker._player_loop` calls `note_played(text, start + Speaker.LAT, dur, words)` where it publishes `spk`
    view: stubgen .pyi of app/server.py
    behavior: Page path: `POST /api/played {text, at, dur, words}` calls `note_played(text, time.monotonic() + at / 1000, dur, words)`; `at` is ms from now until the sentence is heard, `words` its word times in playback seconds or null.
    view: stubgen .pyi of app/server.py
    behavior: `played_cut(at)` drops every entry starting at or after `at`: a sentence cut off never plays.
    view: stubgen .pyi of app/server.py
    behavior: `Wake.hush(at)` calls `played_cut(at)`, so `Speaker.stop` and `Wake.barge` cut both paths.
    view: stubgen .pyi of app/server.py
  s1.d5 | test-writer | steps: 2 | writes: tests/test_wake_loop.py | size: test-writer: tokens: 563646.7 seconds: 168.2 overruns: 0 refusals: 0
    queue /Users/atom/dev/void/queues/stop-echo.md s1.d5
    red
    design: docs/superpowers/specs/own-stop-design.md step 2
    behavior: `Wake.heard` returning a `Heard`
    view: stubgen .pyi of app/server.py
    behavior: `Wake.check`'s third argument is the `Heard` from `Wake.heard`, in place of its text
    view: stubgen .pyi of app/server.py
section s2.1 | lead | steps: 3 | size: lead: tokens: 1107947.7 seconds: 687.2 overruns: 0 refusals: 0
  s2.1.d1 | builder | steps: 3 | writes: app/gate.py | size: builder: tokens: 309800.3 seconds: 167.7 overruns: 0 refusals: 0
    queue /Users/atom/dev/void/queues/stop-echo.md s2.1.d1
    resume a73095c9311f7c787
    design: docs/superpowers/specs/own-stop-design.md
    step: 3
    paths: app/gate.py
    check: PYTHONDONTWRITEBYTECODE=1 uv run --no-project --python ~/.local/share/void/venv/bin/python --with pytest python -m pytest -p no:cacheprovider --tb=no -q tests/test_gate.py
section s2.2 | lead | steps: 4 | size: lead: tokens: 1107947.7 seconds: 687.2 overruns: 0 refusals: 0
  s2.2.d1 | builder | steps: 4 | writes: app/server.py | size: builder: tokens: 309800.3 seconds: 167.7 overruns: 0 refusals: 0
    queue /Users/atom/dev/void/queues/stop-echo.md s2.2.d1
    design: docs/superpowers/specs/own-stop-design.md
    step: 4
    work: `PLAYED` and its functions, `Speaker._player_loop`'s `note_played`, `/api/played`, `played_cut` in `Wake.hush` and `/api/speaking`
    paths: app/server.py
    check: PYTHONDONTWRITEBYTECODE=1 uv run --no-project --python ~/.local/share/void/venv/bin/python --with pytest python -m pytest -p no:cacheprovider --tb=no -q tests/test_wake_loop.py -k 'Played or Hush or PagePath or NativePath'
  s2.2.d2 | test-writer | steps: 4 | writes: tests/test_echo.py, tests/test_wake_loop.py | size: test-writer: tokens: 590821.7 seconds: 178.3 overruns: 0 refusals: 0
    queue /Users/atom/dev/void/queues/stop-echo.md s2.2.d2
    red
    design: docs/superpowers/specs/own-stop-design.md step 4
    behavior: one stop phrase that does not is the owner's, and the burst barges as before.
    view: stubgen .pyi of app/server.py
    replaces: tests/test_echo.py::Echo::test_owner_stop_over_him_stops_him_mid_burst
    behavior: `SPOKEN`, `note_spoken` and `said_lately` stay as they are and still feed `is_echo`.
    view: stubgen .pyi of app/server.py
    replaces: tests/test_echo.py::Echo::test_stop_word_buried_in_his_own_speech_heard_over_him_never_stops_him
    behavior: Each caller builds its `Burst` with `words=heard.words` and calls `gate.judge(burst, said_lately(), CFG, played_lately())`.
    view: stubgen .pyi of app/server.py
    replaces: tests/test_echo.py::Burst::test_answer_begun_as_he_finished_heard_out
    behavior: one stop phrase that does not is the owner's, and the burst barges as before.
    view: stubgen .pyi of app/server.py
    replaces: tests/test_wake_loop.py::FollowUpGate::test_a_stop_said_over_him_is_judged_as_a_peek_and_stops_him
    behavior: The other steps are unchanged.
    view: stubgen .pyi of app/server.py
    replaces: tests/test_wake_loop.py::FollowUpGate::test_anything_else_said_over_him_is_dropped_by_the_peek
    behavior: `Wake.check`'s third argument is the `Heard` from `Wake.heard`, in place of its text
    view: stubgen .pyi of app/server.py
    replaces: tests/test_wake_loop.py::FollowUpGate::test_the_quick_listen_for_his_name_is_judged_as_a_wake_burst
  s2.2.d3 | builder | steps: 4 | writes: app/server.py | size: builder: tokens: 309800.3 seconds: 167.7 overruns: 0 refusals: 0
    queue /Users/atom/dev/void/queues/stop-echo.md s2.2.d3
    design: docs/superpowers/specs/own-stop-design.md
    step: 4
    work: word timestamps in `run_whisper_heard` and `transcribe_pcm_heard`, and `Wake.session`, `Wake.heard`, `Wake.stop_in`, `Wake.check` passing `at`, `Heard` and `played_lately()`
    paths: app/server.py
    check: PYTHONDONTWRITEBYTECODE=1 uv run --no-project --python ~/.local/share/void/venv/bin/python --with pytest python -m pytest -p no:cacheprovider --tb=no -q tests/test_echo.py tests/test_gate.py tests/test_wake_loop.py
section s3.1.1 | lead | steps: 5 | size: lead: tokens: 1127995.3 seconds: 696.1 overruns: 0 refusals: 0
  s3.1.1.d1 | test-writer | steps: 5 | writes: tests/test_page_played.py | size: test-writer: tokens: 612913.9 seconds: 185.2 overruns: 0 refusals: 0
    queue /Users/atom/dev/void/queues/stop-echo.md s3.1.1.d1
    resume ad754ac2219c82231
    red
    design: docs/superpowers/specs/own-stop-design.md step 5
    behavior: The page, playing its own voice with `barge_in` on, posts `/api/played` for each sentence it schedules, with the text it sent, its start, length and word times.
    view: stubgen .pyi of app/server.py
    behavior: The page's global `enqueue(text)` (`app/static/index.html:1748`), with `info.voice_native` off, posts `/api/tts` with `{text}` and queues the answer for `pump`; each queued sentence keeps that `text`.
    view: stubgen .pyi of app/server.py
    behavior: When `pump` schedules a sentence at `when` (`app/static/index.html:1889`), it calls `played(text, (when - a.currentTime + lat) * 1000, dur, words)`, with `lat` the output latency the captions already use (`app/static/index.html:1891`), `dur` the played length (`app/static/index.html:1884`), and each `X-Void-Words` time divided by the playback rate `X-Void-Rate`.
    view: stubgen .pyi of app/server.py
    behavior: `played` and `speaking` (`app/static/index.html:1853`) post only when `info.voice_native` is off and `info.wake_word` or `info.barge_in` is on.
    view: stubgen .pyi of app/server.py
section s3.1.2 | lead | steps: 6 | size: lead: tokens: 1127995.3 seconds: 696.1 overruns: 0 refusals: 0
  s3.1.2.d1 | builder | steps: 6 | writes: app/static/index.html | size: builder: tokens: 294961.3 seconds: 159.4 overruns: 0 refusals: 0
    queue /Users/atom/dev/void/queues/stop-echo.md s3.1.2.d1
    design: docs/superpowers/specs/own-stop-design.md
    step: 6
    paths: app/static/index.html
    check: PYTHONDONTWRITEBYTECODE=1 uv run --no-project --python ~/.local/share/void/venv/bin/python --with pytest python -m pytest -p no:cacheprovider --tb=no -q tests/test_page_played.py
section s3.2 | lead | steps: 7, 8 | size: lead: tokens: 1127615.6 seconds: 695.2 overruns: 0 refusals: 0
  s3.2.d1 | test-writer | steps: 7 | writes: tests/make_scenes.py, tests/scenes.py | size: test-writer: tokens: 602108.8 seconds: 181.8 overruns: 0 refusals: 0
    queue /Users/atom/dev/void/queues/stop-echo.md s3.2.d1
    port
    design: docs/superpowers/specs/own-stop-design.md step 7
    files: tests/make_scenes.py, tests/scenes.py
    view: stubgen .pyi of app/server.py
    view: stubgen .pyi of app/gate.py
  s3.2.d2 | builder | steps: 8 | writes: tests/fixtures/scenes/ | size: builder: tokens: 300248.5 seconds: 161.9 overruns: 0 refusals: 0
    queue /Users/atom/dev/void/queues/stop-echo.md s3.2.d2
    design: docs/superpowers/specs/own-stop-design.md
    step: 8
    paths: tests/fixtures/scenes/
    check: ~/.local/share/void/venv/bin/python tests/make_scenes.py --check
  s3.2.d3 | test-writer | steps: 7 | writes: tests/test_scenes.py | size: test-writer: tokens: 602108.8 seconds: 181.8 overruns: 0 refusals: 0
    queue /Users/atom/dev/void/queues/stop-echo.md s3.2.d3
    red
    design: docs/superpowers/specs/own-stop-design.md step 7
    behavior: Void's own stop phrase, heard back while it plays or in the room's ring after, is dropped as "echo"
    view: stubgen .pyi of app/server.py
    behavior: the owner's stop phrase said while Void talks, soon after Void said the word itself included, still barges.
    view: stubgen .pyi of app/server.py
