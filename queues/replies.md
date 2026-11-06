design /Users/atom/dev/void-replies/docs/superpowers/specs/quiet-replies-design.md | order /Users/atom/dev/void-replies/docs/superpowers/specs/quiet-replies-design.md | main 3ef6fbc
section s1 | lead | steps: 1 | size: lead: tokens: 1080209.0 seconds: 684.7 overruns: 0 refusals: 0
  s1.d1 | test-writer | steps: 1 | writes: tests/test_echo.py, tests/test_wake_loop.py | size: test-writer: tokens: 551389.2 seconds: 164.7 overruns: 0 refusals: 0
    queue /Users/atom/dev/void/queues/replies.md s1.d1
    red
    design: docs/superpowers/specs/quiet-replies-design.md, Order step 1
    behavior: anything the owner says after Void has gone quiet gets through.
    view: stubgen .pyi of app/server.py
    behavior: `Wake.span_at(t)` is the span whose sound covers `t`, with no `ECHO_TAIL`.
    view: stubgen .pyi of app/server.py
    behavior: `Wake.window_at(t)` is open from the end of his sound to `until`, and closed while he makes sound.
    view: stubgen .pyi of app/server.py
    behavior: A burst begun in the ring is therefore a `"follow"` or a `"wake"`
    view: stubgen .pyi of app/server.py
    behavior: the pause counts as sound only when his next sentence is already made.
    view: stubgen .pyi of app/server.py
    behavior: `/api/speaking` takes `{"on": true, "left": <s>}` and records `Wake.talking_until(now + left)`.
    view: stubgen .pyi of app/server.py
    behavior: It takes `{"on": false}` and records `Wake.talking_until(now)`, which ends his sound now and leaves the follow-up window open.
    view: stubgen .pyi of app/server.py
    behavior: No placeholder span is ever recorded.
    view: stubgen .pyi of app/server.py
  s1.d2 | builder | steps: 1 | writes: app/server.py, app/static/index.html | size: builder: tokens: 326666.7 seconds: 179.3 overruns: 0 refusals: 0
    queue /Users/atom/dev/void/queues/replies.md s1.d2
    design: docs/superpowers/specs/quiet-replies-design.md
    step: 1
    paths: app/server.py, app/static/index.html
    check: PYTHONDONTWRITEBYTECODE=1 uvx pytest -p no:cacheprovider --tb=no -rA -vv --assert=plain tests/test_echo.py tests/test_wake_loop.py
section s2 | lead | steps: 2 | size: lead: tokens: 1080209.0 seconds: 684.7 overruns: 0 refusals: 0
  s2.d1 | builder | steps: 2 | writes: app/gate.py, app/server.py, app/drops.py | size: builder: tokens: 326666.7 seconds: 179.3 overruns: 0 refusals: 0
    queue /Users/atom/dev/void/queues/replies.md s2.d1
    stub
    design: docs/superpowers/specs/quiet-replies-design.md
    step: 2
    paths: app/gate.py, app/server.py, app/drops.py
    check: PYTHONDONTWRITEBYTECODE=1 uvx pytest -p no:cacheprovider --tb=no -q --collect-only tests/test_gate.py tests/test_log_cases.py tests/test_echo.py tests/test_listen_verdict.py
  s2.d2 | test-writer | steps: 2 | writes: tests/test_gate.py, tests/test_log_cases.py | size: test-writer: tokens: 551389.2 seconds: 164.7 overruns: 0 refusals: 0
    queue /Users/atom/dev/void/queues/replies.md s2.d2
    red
    design: docs/superpowers/specs/quiet-replies-design.md, Order step 2
    behavior: Step 2 of `judge` runs `is_echo` only when `b.rang` is true.
    view: stubgen .pyi of app/gate.py
    behavior: a burst begun while he made sound, judged with no time at all, or recorded by push-to-talk with his voice in the air, is still dropped as echo.
    view: stubgen .pyi of app/gate.py
    behavior: `now()` replays a `rang` echo drop as "as logged", because the log does not keep his words.
    view: stubgen .pyi of app/drops.py
    behavior: It judges every other echo drop through `gate.judge` with `rang=False`
    view: stubgen .pyi of app/drops.py
    behavior: `"echo"` is not in `UNSEEN`.
    view: stubgen .pyi of app/drops.py
    behavior: A replayed `Burst` takes `rang` and `talking` from the flags.
    view: stubgen .pyi of app/drops.py
  s2.d3 | test-writer | steps: 2 | writes: tests/test_echo.py, tests/test_listen_verdict.py | size: test-writer: tokens: 551389.2 seconds: 164.7 overruns: 0 refusals: 0
    queue /Users/atom/dev/void/queues/replies.md s2.d3
    red
    design: docs/superpowers/specs/quiet-replies-design.md, Order step 2
    behavior: Only real echo is dropped as echo.
    view: stubgen .pyi of app/server.py
    behavior: a burst heard after he went quiet is never echo
    view: stubgen .pyi of app/server.py
    behavior: his own words heard in the ring after his last sound are dropped as echo.
    view: stubgen .pyi of app/server.py
    behavior: Every `gate.Burst` built in `server.py` takes `talking` and `rang` from it, over the burst's first-sample time and its last voice:
    view: stubgen .pyi of app/server.py
    behavior: `Wake.heard` and `Wake.stop_in` take `started` from `Wake.session` and judge over `started` to now.
    view: stubgen .pyi of app/server.py
    behavior: `Wake.check`'s `heard …` line gains `, in his echo` when `rang` is true and `talking` is false.
    view: stubgen .pyi of app/server.py
    behavior: recorded by push-to-talk with his voice in the air, is still dropped as echo.
    view: stubgen .pyi of app/server.py
  s2.d4 | builder | steps: 2 | writes: app/gate.py, app/server.py, app/drops.py | size: builder: tokens: 326666.7 seconds: 179.3 overruns: 0 refusals: 0
    queue /Users/atom/dev/void/queues/replies.md s2.d4
    design: docs/superpowers/specs/quiet-replies-design.md
    step: 2
    paths: app/gate.py, app/server.py, app/drops.py
    check: PYTHONDONTWRITEBYTECODE=1 uvx pytest -p no:cacheprovider --tb=no -rA -vv --assert=plain tests/test_gate.py tests/test_log_cases.py tests/test_echo.py tests/test_listen_verdict.py
section s3 | lead | steps: 3 | size: lead: tokens: 1080209.0 seconds: 684.7 overruns: 0 refusals: 0
  s3.d1 | test-writer | steps: 3 | writes: tests/test_page_held.py | size: test-writer: tokens: 551389.2 seconds: 164.7 overruns: 0 refusals: 0
    queue /Users/atom/dev/void/queues/replies.md s3.d1
    red
    design: docs/superpowers/specs/quiet-replies-design.md, Order step 3
    behavior: Follow-ups kept while he works are not sent, and his answer is not cut off; once he is done working and has finished speaking, they go out as one follow-up.
    view: stubgen .pyi of app/server.py
    behavior: A follow-up kept while he is not working but still speaking is not sent, and his speech is not cut off, until he has finished speaking.
    view: stubgen .pyi of app/server.py
    behavior: A follow-up kept while he is quiet and not working goes straight out.
    view: stubgen .pyi of app/server.py
    behavior: A barge still stops him mid-speech.
    view: stubgen .pyi of app/server.py
  s3.d2 | builder | steps: 3 | writes: app/static/index.html | size: builder: tokens: 326666.7 seconds: 179.3 overruns: 0 refusals: 0
    queue /Users/atom/dev/void/queues/replies.md s3.d2
    design: docs/superpowers/specs/quiet-replies-design.md
    step: 3
    paths: app/static/index.html
    check: PYTHONDONTWRITEBYTECODE=1 uvx pytest -p no:cacheprovider --tb=no -rA -vv --assert=plain tests/test_page_held.py
