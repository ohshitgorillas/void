design docs/superpowers/specs/hearing-verdict-design.md | HEAD ac58d4b
section s1 | lead | steps: 1 | size: lead: tokens: 716251.6 seconds: 580.4 overruns: 0 refusals: 0
  s1.d1 | general-purpose | steps: 1 | writes: app/gate.py | size: general-purpose: tokens: 732415.7 seconds: 191.3 overruns: 0 refusals: 0
    stub
    design: docs/superpowers/specs/hearing-verdict-design.md 1
    behavior: Build the stubs above
    files: app/gate.py
  s1.d2 | test-writer | steps: 1 | writes: tests/test_gate.py, tests/test_echo.py | size: test-writer: tokens: 542985.5 seconds: 164.4 overruns: 0 refusals: 0
    red
    design: docs/superpowers/specs/hearing-verdict-design.md 1
    behavior: Echo, noise and stop-phrase tests | `gate.is_echo`, `gate.is_noise`, `gate.stop_said`
    view: app/gate.py
    behavior: Filler words | `gate.NOISE_WORDS`
    view: app/gate.py
  s1.d3 | general-purpose | steps: 1 | writes: app/gate.py, app/server.py | size: general-purpose: tokens: 732415.7 seconds: 191.3 overruns: 0 refusals: 0
    design: docs/superpowers/specs/hearing-verdict-design.md 1
    behavior: move the echo, noise and stop tests and the thresholds into `gate`, and make `server.py` import them.
    red: s1.d2 report BEHAVIOR test ids
    files: app/gate.py, app/server.py
  s1.d4 | test-writer | steps: 1 | writes: tests/test_gate.py, tests/test_echo.py | size: test-writer: tokens: 542985.5 seconds: 164.4 overruns: 0 refusals: 0
    port
    design: docs/superpowers/specs/hearing-verdict-design.md 1
    files: tests/test_gate.py, tests/test_echo.py
    view: app/gate.py
    view: app/server.py
section s2 | lead | steps: 2 | size: lead: tokens: 716251.6 seconds: 580.4 overruns: 0 refusals: 0
  s2.d1 | general-purpose | steps: 2 | writes: app/server.py | size: general-purpose: tokens: 732415.7 seconds: 191.3 overruns: 0 refusals: 0
    stub
    design: docs/superpowers/specs/hearing-verdict-design.md 2
    behavior: def verdict_out(v: "gate.Verdict", said: str, voice: float | None, kind: str) -> None:
    files: app/server.py
  s2.d2 | test-writer | steps: 2 | writes: tests/test_gate.py | size: test-writer: tokens: 542985.5 seconds: 164.4 overruns: 0 refusals: 0
    red
    design: docs/superpowers/specs/hearing-verdict-design.md 2
    behavior: `judge` runs its checks in a fixed order and returns at the first drop
    view: app/gate.py
    behavior: Speech share and minimum speech | `gate.spoken_enough`
    view: app/gate.py
    behavior: Whisper confidence thresholds | `gate` constants and `gate.sure`
    view: app/gate.py
  s2.d3 | general-purpose | steps: 2 | writes: app/gate.py | size: general-purpose: tokens: 732415.7 seconds: 191.3 overruns: 0 refusals: 0
    design: docs/superpowers/specs/hearing-verdict-design.md 2
    behavior: `judge` runs its checks in a fixed order and returns at the first drop
    red: s2.d2 report BEHAVIOR test ids
    files: app/gate.py
  s2.d4 | test-writer | steps: 2 | writes: tests/test_wake_loop.py, tests/test_listen_enrol.py | size: test-writer: tokens: 542985.5 seconds: 164.4 overruns: 0 refusals: 0
    red
    design: docs/superpowers/specs/hearing-verdict-design.md 2
    behavior: One stderr line per verdict
    view: app/server.py
    behavior: Never a file, store or count.
    view: app/server.py
    behavior: `run_whisper_heard` blanks nothing
    view: app/server.py
  s2.d5 | general-purpose | steps: 2 | writes: app/server.py | size: general-purpose: tokens: 732415.7 seconds: 191.3 overruns: 0 refusals: 0
    design: docs/superpowers/specs/hearing-verdict-design.md 2
    behavior: One stderr line per verdict
    behavior: `run_whisper_heard` uses `gate.sure` and blanks nothing.
    red: s2.d4 report BEHAVIOR test ids
    files: app/server.py
  s2.d6 | test-writer | steps: 2 | writes: tests/test_wake_loop.py, tests/test_listen_enrol.py | size: test-writer: tokens: 542985.5 seconds: 164.4 overruns: 0 refusals: 0
    red
    design: docs/superpowers/specs/hearing-verdict-design.md 2
    behavior: transcribes, scores and acts on the `Verdict`; decides nothing itself
    view: app/server.py
  s2.d7 | general-purpose | steps: 2 | writes: app/server.py | size: general-purpose: tokens: 732415.7 seconds: 191.3 overruns: 0 refusals: 0
    design: docs/superpowers/specs/hearing-verdict-design.md 2
    behavior: `Wake.check`, `Wake.heard`, `Wake.stop_in` and `Listen.run` build a `Burst`, call `gate.judge`, act on the `Verdict` and print through `verdict_out`.
    red: s2.d6 report BEHAVIOR test ids
    files: app/server.py
section s3 | lead | steps: 3 | size: lead: tokens: 716251.6 seconds: 580.4 overruns: 0 refusals: 0
  s3.d1 | general-purpose | steps: 3 | writes: app/hearing.py | size: general-purpose: tokens: 732415.7 seconds: 191.3 overruns: 0 refusals: 0
    stub
    design: docs/superpowers/specs/hearing-verdict-design.md 3
    behavior: `app/hearing.py`: gains the per-frame voice detector
    files: app/hearing.py
  s3.d2 | test-writer | steps: 3 | writes: tests/test_hearing.py | size: test-writer: tokens: 542985.5 seconds: 164.4 overruns: 0 refusals: 0
    red
    design: docs/superpowers/specs/hearing-verdict-design.md 3
    behavior: Per-frame voice detection | `hearing.Voicing`
    view: app/hearing.py
    behavior: Each caller keeps its own constants and passes them in.
    view: app/hearing.py
  s3.d3 | general-purpose | steps: 3 | writes: app/hearing.py | size: general-purpose: tokens: 732415.7 seconds: 191.3 overruns: 0 refusals: 0
    design: docs/superpowers/specs/hearing-verdict-design.md 3
    behavior: Per-frame voice detection | `hearing.Voicing`
    red: s3.d2 report BEHAVIOR test ids
    files: app/hearing.py
  s3.d4 | general-purpose | steps: 3 | writes: app/server.py | size: general-purpose: tokens: 732415.7 seconds: 191.3 overruns: 0 refusals: 0
    design: docs/superpowers/specs/hearing-verdict-design.md 3
    behavior: `speech_span`, `Listen.run` and `Wake.session` use it, and `Floor` leaves `server.py`.
    red: s3.d2 report BEHAVIOR test ids
    files: app/server.py
section s4 | lead | steps: 4 | size: lead: tokens: 716251.6 seconds: 580.4 overruns: 0 refusals: 0
  s4.d1 | test-writer | steps: 4 | writes: tests/fakes.py, tests/test_gate.py, tests/test_echo.py | size: test-writer: tokens: 542985.5 seconds: 164.4 overruns: 0 refusals: 0
    port
    design: docs/superpowers/specs/hearing-verdict-design.md 4
    files: tests/fakes.py, tests/test_gate.py, tests/test_echo.py
    view: app/gate.py
    view: app/server.py
  s4.d2 | test-writer | steps: 4 | writes: tests/fakes.py, tests/test_wake_loop.py, tests/test_listen_enrol.py | size: test-writer: tokens: 542985.5 seconds: 164.4 overruns: 0 refusals: 0
    port
    design: docs/superpowers/specs/hearing-verdict-design.md 4
    files: tests/fakes.py, tests/test_wake_loop.py, tests/test_listen_enrol.py
    view: app/server.py
section s5 | lead | steps: 5 | size: lead: tokens: 716251.6 seconds: 580.4 overruns: 0 refusals: 0
  s5.d1 | test-writer | steps: 5 | writes: tests/scenes.py, tests/fakes.py | size: test-writer: tokens: 542985.5 seconds: 164.4 overruns: 0 refusals: 0
    port
    design: docs/superpowers/specs/hearing-verdict-design.md 5
    files: tests/scenes.py, tests/fakes.py
    view: app/server.py
