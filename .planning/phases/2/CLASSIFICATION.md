# Phase 2: Branch split - Classification

Snapshot: 74af430f7fc9e210d229beaf0e6a43d9389e0f63 (`personal` when Plan 1 started). This file covers `git rev-list --reverse --date-order macos..74af430` (157 commits: 139 non-merge, 18 merges).
Base: `c895ced`, local `macos`. Date order keeps every parent before its children and follows the order the work was written (D-08's original order).

Every commit after the snapshot that the orchestrator adds to `personal` touches only `.planning/` (dev tooling); Plan 2 checks this before it builds.

Classes: `fix` (bound for `macos`), `visual`, `feature`, `dev tooling` (stays on `personal`), `merge` (follows its parents).
Personal-only paths: `CLAUDE.md`, `.claude/`, `queues/`, `docs/superpowers/`, `docs/design/`, `.planning/`.
Path columns show directories at the depth the decision needs (`tests/` and `.planning/` collapsed).

## Table

| SHA | Subject | Class | Paths | Reason |
|---|---|---|---|---|
| 61975ea467ecd700d5b4930d8ffe8313cd905c59 | Local only: spark cloud density and fog follow the context meter | visual | app/static/index.html | Local only: context-meter sparks on the page; look and motion, no defect |
| 6bd562957f63d51adb09411ce7bbcbbec8c8657c | Local only: drop the fog; sparks alone follow the context meter | visual | app/static/index.html | Local only: context-meter sparks on the page; look and motion, no defect |
| b554fd0326c4a7e13fb0d024243adb57800c9fcc | Local only: count sparks from a fresh chat's baseline, fewer and slower to build | visual | app/static/index.html | Local only: context-meter sparks on the page; look and motion, no defect |
| ad1da733e36738cc1dc284c8603228249a1b9c9c | Hear out a whole follow-up or "hey Void, ..." request | fix | app/server.py | hearing and inbox-turn defect in server.py |
| 0ba0fec9e2752aa1eb6036c37513ac4d1b9e1211 | Keep showing the follow-up as heard while you're still saying it; log each heard burst | fix | app/server.py | hearing and inbox-turn defect in server.py |
| 16b582995ac797a36aeb0f08455818cfeafe38b9 | Hear "Void, tidy up" as tidy-up, not only "hey Void, tidy up" | fix | app/static/index.html | wake phrase "Void, tidy up" was not recognised: a one-line regex defect |
| f3b294746f75dec8e6976560170c8bbb1a8987f8 | Deliver inbox alerts to Void's Claude session | fix | app/server.py, tests/ | inbox alerts reach his session; ping batching sits on it (borderline B-06) |
| 3935571f3cf114eab8582900c4b832db14465d3d | Reload the window for real after a server restart, so it stops sending a dead token | fix | app/window_win.py, tests/ | window reload after a server restart sent a dead token |
| 7ef0a997bbc0d957a2d05f8fbe6eb2720a2cbdb4 | Don't turn you away while he answers an inbox alert, and show he's on it | fix | app/server.py, tests/ | hearing and inbox-turn defect in server.py |
| 87344d3be9209f80d14e5e42d953f6cf90aa516b | Local only: sparks linear in context tokens, one at a time, never appearing over his face | visual | app/static/index.html, tests/ | Local only: context-meter sparks on the page; look and motion, no defect |
| 88e8b7d0502fcae956db882a86c7381d2c08d3d6 | Keep sources out of the spoken reply, and drop a follow-up on record start instead of r... | fix | app/server.py, app/static/index.html | sources were read aloud; a follow-up was re-queued after record start |
| 7293746523f549c0ed15e10545abe87bb771f2dd | Merge mine/context-cloud-v2 (continuous sparks) | merge | - | follows its parents (D-05) |
| 18b449056014ff0e8f233d328fa9a0ee0abf59ce | Merge macos | merge | - | follows its parents (D-05) |
| 442fc7872b48c4058e03d14f5015bfcc66e87461 | Merge branch 'macos' into mine/context-cloud | merge | - | follows its parents (D-05) |
| 7117e88a0383ef63978a1357112efb7401205dac | Merge remote-tracking branch 'origin/macos' into mine/context-cloud | merge | - | follows its parents (D-05) |
| d8f55976b4997bacef64250d9a910cd44c7e83e9 | Merge remote-tracking branch 'origin/macos' into mine/context-cloud | merge | - | follows its parents (D-05) |
| 089ac26bfa1c30223839634f4aa45adf77519873 | Merge branch 'macos' into mine/context-cloud | merge | - | follows its parents (D-05) |
| e53ea7b4b2fb438b801eb41af1f013ef70edb13d | Hover mode: Esc takes him off your pointer, and Claude knows `void hover-off` | fix | app/macsys.py, app/server.py, app/static/index.html, app/window_win.py, tests/ | no way out of hover mode on macOS (borderline B-01) |
| 283432f103622d39b09537fcd89ea230fffe7e65 | Show a thumbnail of images Claude reads in the code panel | feature | app/agents.py, app/static/index.html | code-panel thumbnails of images: a capability macos lacks |
| 14b64bfd26f47b34aae8c747919c97ac627df537 | Asleep, his helpers no longer catch his eye | visual | app/static/index.html | helper gaze while asleep: page motion (borderline B-04) |
| ed2fa27b950f92ac4353df307b70ab80aaf61781 | Face: the glow takes his lift and squish, so a stretch no longer pushes his head up ove... | visual | app/static/index.html | glow follows his lift and squish: page motion (borderline B-05) |
| 52cd2e56773926edb4756963af41b673338b3c48 | "Tidy up" works again: Void.app opens your installed Void, not its own older copy | fix | app/static/index.html, packaging/macos/launcher | Void.app opened its own older copy so tidy up failed; launcher hands off |
| fc024cd0678226a2d9924959635c86a339d74e14 | Void.app opened from the Dock hands off with the full PATH, so his Claude still finds H... | fix | packaging/macos/launcher | Dock launch lost the full PATH, so his Claude missed Homebrew tools |
| ab00e93de2db392ed55775ee34c9c0c024a8f0ef | Answer him while he's talking, just as he stops, or while he's still working, and he he... | fix | app/server.py, app/static/index.html, tests/ | hearing defect (follow-up, echo, own-voice, noise) |
| fd0f59a952516319ba1260b2ed8bc9da82344598 | He knows his own voice when the mic catches several of his sentences at once, not just one | fix | app/server.py, tests/ | hearing defect (follow-up, echo, own-voice, noise) |
| 36bbb24051b2a1d02cc237b526c16bb0fd84db26 | The always-on mic ignores noise and only tunes itself to your requests | fix | app/server.py, tests/ | hearing defect (follow-up, echo, own-voice, noise) |
| cb86ec32d0e31f807d2a7b266154c2a23862e1b5 | Void can't cut himself off any more: while he talks, only "stop", "hold on", "shut up" ... | fix | app/server.py, tests/ | hearing defect (follow-up, echo, own-voice, noise) |
| 7ed1765abe2f3a9b0165253eca3d14321923025d | He knows his own voice even when the mic mishears it badly, so a garbled echo just afte... | fix | app/server.py, tests/ | hearing defect (follow-up, echo, own-voice, noise) |
| 2efad48780bf70fe2aafd76c76482efe3c21a4e7 | Talk as long as you like: the always-on mic waits for you to finish, pauses and all, in... | fix | app/server.py, tests/ | hearing defect (follow-up, echo, own-voice, noise) |
| 45f0556ef2a4fa2d810a4c9c536befa10edb077e | Answering him as he finishes counts again: if you start talking in his last second and ... | fix | app/server.py, tests/ | hearing defect (follow-up, echo, own-voice, noise) |
| 744ea1a1d0ab9b1126a26ab5f15b4aa247165cbc | Quitting with a stuck mic open keeps sounddevice's Pa_Terminate from running on Python ... | fix | app/winsys.py, tests/ | quitting with a stuck mic open: Pa_Terminate on Python 3.14+ |
| 25c97a3e2fa3a45d5c996bb5848c09851ff962d5 | PlayRef: hearing.py keeps what the speakers play, by monotonic time, at 16 kHz mono, so... | fix | app/hearing.py, tests/ | echo canceller and PlayRef, hearing stack (D-01) |
| 7c1b94354e0aa3ad81be2f02b7946ae2fa9ec8b7 | Canceller: livekit's WebRTC echo canceller takes his own voice out of the mic against P... | fix | app/hearing.py, app/server.py, tests/ | echo canceller and PlayRef, hearing stack (D-01) |
| 07a9ac36bac15065153a14f21711ed993a2660e7 | Void hears you through the echo canceller: the speakers tell PlayRef what they play and... | fix | app/server.py, tests/ | echo canceller and PlayRef, hearing stack (D-01) |
| 1f5096efdf1775001309831f1d35a71f7a3062ca | Picking other speakers mid-sentence keeps the echo reference true: what the dead player... | fix | app/server.py, tests/ | echo canceller and PlayRef, hearing stack (D-01) |
| 3fe188cf3b0f39ea7fd8702fe1b49f077339811b | Voice fixtures for the replay harness: Void's lines in his own cute Kokoro voice, yours... | fix | tests/ | scene and fixture test harness for the hearing stack (D-02 tests/) |
| 92342b8e3634116e19faf0a1ef0fc8aad0c2fbb2 | Room-music fixture: a synthesized song with a sung voice and no echo reference, made by... | fix | tests/ | scene and fixture test harness for the hearing stack (D-02 tests/) |
| fd588b51ff6b1c68556617d0aa3afac9bc88a4fa | Every installer puts in livekit 1.1.21 for the echo canceller; a failed install only wa... | fix | install.ps1, install.sh, packaging/macos/build.sh, tests/ | installer and doctor for the echo canceller |
| c71af44d4aad53aa47de8ab0138f7ffd7c145232 | void doctor and Copy diagnostics say whether the echo canceller is on, off by echo_canc... | fix | app/hearing.py, app/server.py, tests/ | installer and doctor for the echo canceller |
| b95a40f1fbfdc4d38e4412aa4d262af99de83b1b | Design for the context bleed: a local gate on follow-ups without "hey Void", and pings ... | dev tooling | docs/design/ | design doc under docs/design/ |
| bbef5e21b188b5b4116c0d6d15a5cd84c056aa04 | Scene harness: Void's voice and yours in a simulated room on a simulated clock, through... | fix | tests/ | scene and fixture test harness for the hearing stack (D-02 tests/) |
| 8f8e90d171a262041ed512c7cbac3dbf6094d4f8 | Slow scene tier (VOID_SCENES=1, real speech detection and Whisper): Void alone, hold on... | fix | tests/ | scene and fixture test harness for the hearing stack (D-02 tests/) |
| 6750ac996daeaeb9e048b929ce59a9cdfb6a5c00 | Speaker-switch scene: the speakers go away mid-sentence, Speaker._write opens a new pla... | fix | tests/ | scene and fixture test harness for the hearing stack (D-02 tests/) |
| a149608140179e8047a4e514a78af866dbf55c2c | Context-bleed design approved: dropped clips show a faint spark, pings are batched with... | dev tooling | docs/design/ | design doc under docs/design/ |
| 3d52d1116907bf14c3bb613dde206220c0c2d6f2 | Pings batch with no model: PingBatch hands back the lines once 20 s pass quiet or 2 min... | fix | app/notifier.py, tests/ | ping batching and Whisper confidence, hearing stack (D-01) |
| b00ef0e4c1e15a8fb496cf954fb7d8bcf1117cdd | Heard: speech-to-text carries Whisper's confidence (logprob, no_speech, speech seconds)... | fix | app/server.py, tests/ | ping batching and Whisper confidence, hearing stack (D-01) |
| 8441f85adaa0b6400e5e002e152c141522ad6012 | A burst of claude-ping alerts reaches him as one message: InboxFollower feeds notifier.... | fix | app/server.py, tests/ | ping batching and Whisper confidence, hearing stack (D-01) |
| 33dfe5cfe45b23d9f7f73caaa99d79b6c3e68590 | Voiceprint: the owner's voice as a local WeSpeaker ResNet34 embedding on onnxruntime, f... | fix | app/voiceprint.py, tests/ | voiceprint, fix-bound because c378787 removes it and later hearing commits sit on it (D-01) |
| fb16e92df03b3b1dd77e6fd93fb18af8571f38d1 | The voice prompt tells him to run long jobs as detached claude -p processes that report... | fix | app/server.py, tests/ | voice prompt sends long jobs through claude-ping; pairs with ping batching (borderline B-07) |
| 9e6e338795cc2071a0d68b2360bbc9c9ad44509a | Context-bleed design: the voiceprint embeds at most 3 s and scores alongside Whisper so... | dev tooling | docs/design/ | design doc under docs/design/ |
| 5fed3f3593743cab4e0661d655fbdcd3e83facc0 | Bring in the amended context-bleed design (9e6e338): step 2a caps the voiceprint at 3 s... | dev tooling | docs/design/ | design doc under docs/design/ |
| 10c2d6401929edd70633e997d7b2ffdb7bb841a1 | Voiceprint embeds at most the first 3 s of a clip: a warm score of the 18 s room-music ... | fix | app/voiceprint.py, tests/ | voiceprint, fix-bound because c378787 removes it and later hearing commits sit on it (D-01) |
| 047b54f7f826a9162f794a4ec08e47c54892d308 | Follow-up gate: gate.judge in Wake.check's follow branch, voice scored alongside Whispe... | fix | app/gate.py, app/server.py, tests/ | follow-up gate and hearing defects in server.py (D-01) |
| aa91f2072cb1f461f9dccae4bf0d3cb685363588 | Merge the follow-up gate (context-bleed steps 1-3) into mine/context-cloud | merge | - | follows its parents (D-05) |
| 8e01299e91a0c978f37ff056444e408296ce0267 | One echo canceller per process, kept warm across mic sessions: once Void has spoken, ev... | fix | app/hearing.py, app/server.py, tests/ | echo canceller and PlayRef, hearing stack (D-01) |
| bb024466222cb6d7501edeed0af9d54310fb6288 | Page tests: find brew playwright-cli's Playwright, launch installed Chrome | fix | tests/ | page tests find the Playwright browser; test harness fix |
| d24b2b64079c17731df307455bb3176de1113dd3 | Page tests: keep /opt/pw-browsers' Chromium where it exists, else installed Chrome | fix | tests/ | page tests find the Playwright browser; test harness fix |
| 2845fa02305492db5b7fc9568ec90a2974627dc0 | Merge page tests on installed Chrome into mine/context-cloud | merge | - | follows its parents (D-05) |
| 8c3840934f55dbed70043f2cfdabef4182796d30 | Draw a faint spark on a gate_drop bus event | visual | app/static/index.html, tests/ | gate_drop spark drawn on the page (borderline B-03) |
| b210fea4dc4cf13d07d2452b9e9f8b485d581588 | Scenes run with the follow-up gate on and "you" enrolled as the owner through Wake.chec... | fix | tests/ | scene and fixture test harness for the hearing stack (D-02 tests/) |
| 0e6cd827323139f2206990ea23ee60aea43d7d14 | No test writes Void's real data folder: tests/suite_data.py points the suite's data fol... | fix | tests/ | no test writes Void's real data folder; test harness fix |
| 6537fdb182d4900801888029ccbc815bb2cad950 | Void reads a markdown file in a little notebook whose leaves flip; other files keep the... | feature | app/static/index.html, tests/ | notebook for markdown files: a capability macos lacks |
| 7a57ff3e44cc5fa581386396b2eadd2bddc42b60 | Void views an image in a light rounded window of its own, never in the terminal; any re... | feature | app/static/index.html, tests/ | image window: a capability macos lacks |
| 597e0949e0472171fe5278ba3dabbbd3c623aaa1 | "Stop" and "shut up" said over Void stop him: a linear echo canceller of Void's own run... | fix | app/hearing.py, app/server.py, tests/ | echo canceller and PlayRef, hearing stack (D-01) |
| 188cc2c1ae7eba5ed2fc126c7e4a2f772a4ea8b3 | A stop phrase begun over Void stops him even when the check runs after his sentence has... | fix | app/server.py, tests/ | echo canceller and PlayRef, hearing stack (D-01) |
| 6d0ea8bfab4a530b712c5a64324b0805345d91b2 | A write killed by stopping Void is not taken for the speakers changing: Speaker._write ... | fix | app/server.py, tests/ | echo canceller and PlayRef, hearing stack (D-01) |
| c6276e180b4ce4533b80d4b58ed78b0b498485a2 | Linear's docstring states its real reach: K = 10 blocks of 10 ms is 100 ms of room, not... | fix | app/hearing.py | echo canceller and PlayRef, hearing stack (D-01) |
| 62c3f33d07626fd14de2a1f26f9dcb2966b733e1 | A voiceprint saved before prints carried a version is not used: enrolment starts over, ... | fix | app/voiceprint.py, tests/ | voiceprint, fix-bound because c378787 removes it and later hearing commits sit on it (D-01) |
| 9e10bc6be1ee443fe723b50873c92e88d04e10d4 | Every BUS event a scene records carries its scene time `at`, in seconds from the scene'... | fix | tests/ | scene and fixture test harness for the hearing stack (D-02 tests/) |
| 391980bd9344e0cc14637f3628b8c3e6c0491ccf | Merge commit '62c3f33' into mine/context-cloud | merge | - | follows its parents (D-05) |
| d6887af01c5843ff553938693d6989ae7bdb9600 | Merge commit '9e10bc6' into mine/context-cloud | merge | - | follows its parents (D-05) |
| 9cb005fea83efb0e2990ae520b7680d8616a6700 | A Listen recording enrols into the voiceprint only when it came back as a request in wo... | fix | app/server.py, tests/ | voiceprint, fix-bound because c378787 removes it and later hearing commits sit on it (D-01) |
| e16fd2d15f93facb88c1ee8cf81a5fb58282d297 | Merge commit '9cb005f' into mine/context-cloud | merge | - | follows its parents (D-05) |
| 1ef7f4437dddc63cccff9237cd79c8a7b9f3aaa1 | Scenes: stamp scene time as scene_at, leaving the server's own at on spk events | fix | tests/ | scene and fixture test harness for the hearing stack (D-02 tests/) |
| 752f00e1ee83ff17bb992cd77e6666e5120145ac | Wake: stop him on a stop phrase said over him while you're still talking | fix | app/server.py, tests/ | follow-up gate and hearing defects in server.py (D-01) |
| 6948ea4077845e4e8d4e7a69a3d7749d33eb213e | Merge commit '752f00e' into mine/context-cloud | merge | - | follows its parents (D-05) |
| 821039525cd5e8fc045cfbd815fa86688fef3ff8 | Design: owner's own instant voice commands and overrides for the built-ins (proposed) | dev tooling | docs/superpowers/ | design doc under docs/superpowers/ |
| 489cc3c3a156ad2f55c25342c37a0e5080c677b9 | Design: record the owner's five rulings on instant commands | dev tooling | docs/superpowers/ | design doc under docs/superpowers/ |
| e5dcde0894a94b54d78fdf4d83f29ef528c630f6 | Design: example entries use roonctl's real subcommands; volume stays with HQPlayer | dev tooling | docs/superpowers/ | design doc under docs/superpowers/ |
| a64d04750ddcd0c680cf7fd90894ca014f71f552 | Log the voice score on every follow-up verdict | fix | app/server.py, tests/ | follow-up gate and hearing defects in server.py (D-01) |
| 6120ace8eeb3f7b45861f75e0cf971570641cd23 | Hear your short repeated phrases; drop only a sentence Whisper loops on room sound | fix | app/server.py, tests/ | follow-up gate and hearing defects in server.py (D-01) |
| 2f1d75d216f356754da1d92899725fed7c7dd10a | Merge commit '6120ace' into mine/context-cloud | merge | - | follows its parents (D-05) |
| 044e7f9e51e7767406ce05f9afd5cbe16884d602 | Stop only on a stop said as one, not one buried in his own echo | fix | app/server.py, tests/ | follow-up gate and hearing defects in server.py (D-01) |
| 8cacc1dbc9534a521f9edb1fc9726f1022b59a5d | Merge commit '044e7f9' into mine/context-cloud | merge | - | follows its parents (D-05) |
| fb71f110d2181e5b9ffc2242a4fea18f8dbf2deb | Score follow-ups and enrol the voiceprint on the spoken stretch only | fix | app/server.py, tests/ | follow-up gate and hearing defects in server.py (D-01) |
| 1292ee7fc90c67433c80c9fb912371f31205a53d | Merge commit 'fb71f11' into mine/context-cloud | merge | - | follows its parents (D-05) |
| ff2c7b4be348c8a24f1e78ee644a9b3ec227bdbc | Never enrol a voiceprint clip under 1.5 s; bump FORMAT to 2 | fix | app/voiceprint.py, tests/ | voiceprint, fix-bound because c378787 removes it and later hearing commits sit on it (D-01) |
| 93c66c885bd954bfec45bb76196aab51defa3d93 | Merge commit 'ff2c7b4' into mine/context-cloud | merge | - | follows its parents (D-05) |
| ac58d4bc3e284952f89b92df670485552bb6445f | A reply begun over Void is heard and scored without his voice in front of it | fix | app/server.py, tests/ | follow-up gate and hearing defects in server.py (D-01) |
| 3ef2eb64d7726339925406e9429fc1057c8fcee0 | docs: add the approved hearing verdict design | dev tooling | docs/superpowers/ | design doc under docs/superpowers/ |
| 5825f01db0be4be0e58c1f45f57e55060774e572 | gate: stubs for the hearing verdict core (design step 1) | fix | app/gate.py | gate.judge and hearing.Voicing (D-01) |
| ae3ff8bb4f2a04b4703b437eb6db94aa828ddf3d | gate: echo, noise and stop tests and Whisper's thresholds move into gate; server.py imp... | fix | app/gate.py, app/server.py, tests/ | gate.judge and hearing.Voicing (D-01) |
| 6c837d6cac87d3a318977e4ec21ce3403521cdb7 | Design: step 2 builds gate.judge and gate.spoken_enough | dev tooling | docs/superpowers/ | design doc under docs/superpowers/ |
| bfef46ce7b7d147b7715f0f3994990c9e4b82ff2 | gate: red tests for judge and spoken_enough (design step 2, section s2.1) | fix | tests/ | gate.judge and hearing.Voicing (D-01) |
| 7688517c6f56fa86c76df9b81eb2cabb15ed0617 | gate: build spoken_enough and judge, nine checks in order (design step 2, section s2.2) | fix | app/gate.py, app/server.py | gate.judge and hearing.Voicing (D-01) |
| a756afca47cedb25ed82d582ef99881972bdd0b2 | design: record lead rulings from s2.2 (stop phrase, wake barge, listen, no-speech reaso... | dev tooling | docs/superpowers/ | design doc under docs/superpowers/ |
| f0e1cdc777b72076da7d82eb53a553acb33df598 | tests: red tests for every drop going through judge (design step 2, section s2.3) | fix | tests/ | gate.judge and hearing.Voicing (D-01) |
| c7a7ef715afeedfbd893cff675734698a2328949 | hearing: every drop goes through gate.judge (design step 2, section s2.4) | fix | app/gate.py, app/server.py, tests/ | gate.judge and hearing.Voicing (D-01) |
| b33118e2fbcf04978cbb4a0b1852e973b8a101a8 | design: record lead rulings from s2.3 and s2.4 (verdict lines, kinds per caller, Wake.h... | dev tooling | docs/superpowers/ | design doc under docs/superpowers/ |
| 805ed9b6cbe86e04ee0f8a99a3f020a8f66e8eb7 | tests: red tests for Voicing (design step 3, section s3) | fix | tests/ | gate.judge and hearing.Voicing (D-01) |
| 5c25612d7fa331971697b1dfba5dff3b28ca5900 | hearing: Voicing does per-frame voice detection; speech_span, Listen.run and Wake.sessi... | fix | app/hearing.py, app/server.py | gate.judge and hearing.Voicing (D-01) |
| ee1c6ac8762276fd1dbcf41f737b2478980cc998 | design: record lead rulings from s3 (hold, first frame, clip counting, build order) | dev tooling | docs/superpowers/ | design doc under docs/superpowers/ |
| f3aa090f8022a53cf9184409d6bc2c8b33a9a6fa | tests: fakes.py is the one home of hearing test doubles (design step 4, section s4.d1) | fix | tests/ | scene and fixture test harness for the hearing stack (D-02 tests/) |
| 87d1faa5d2717e9f979298d32a5e9cd03d013f80 | tests: test_gate and test_echo use fakes.heard and fakes.ears (design step 4, section s... | fix | tests/ | scene and fixture test harness for the hearing stack (D-02 tests/) |
| 941d5c13ebc669955013482a93f5638864d15a98 | tests: test_wake_loop and test_listen_enrol use fakes.hiss, fakes.pieces and fakes.ears... | fix | tests/ | scene and fixture test harness for the hearing stack (D-02 tests/) |
| c01ed32f2ab9645a09c60918fe30ac4bf47aab92 | tests: scenes use fakes.heard through fakes.ears; no Heard literal or STT patch set of ... | fix | tests/ | scene and fixture test harness for the hearing stack (D-02 tests/) |
| d3c141fe0c4d27eeca8193a456d06b0fb104099c | design: record lead rulings from s4 (fakes.heard values, ears defaults, scenes numbers) | dev tooling | docs/superpowers/ | design doc under docs/superpowers/ |
| c3787873895ba1390f7a148645a17d5682a83121 | hearing: take the voiceprint out; stamp every hear line; void drops replays a log | fix | app/drops.py, app/gate.py, app/server.py, app/voiceprint.py, bin/void, docs/superpowers/, tests/ | voiceprint removal and void drops; path-split (D-08) |
| 74e983f0db690b1f2d2fe88c91b840e7e091be6f | hearing: keep when he talked, judge each burst by when it was heard | fix | app/server.py, tests/ | gate.judge and hearing.Voicing (D-01) |
| 1baa17df1dcdd8fd3b8e04131b06f557a89d2728 | Merge branch 'stream/quick-commands' into personal | merge | - | follows its parents (D-05) |
| 3ef6fbcb71a6f74211d4d74fa38ccafd44b98052 | Merge branch 'stream/void-image' into personal | merge | - | follows its parents (D-05) |
| a3021ddade9deee6faf0a5e8ebf3bd9b3cfb1c7b | Start Void's Claude sessions smaller: cap Bash output, drop unused tools, hide unused a... | feature | app/server.py | smaller Claude sessions: a tuning change, no defect (borderline B-02) |
| 94e41d6ade3259042c3da015767f65cc27a7c14c | Scope the foreground, doc-budget and worker-brief rules to Void | dev tooling | .claude/, CLAUDE.md | agent rules: CLAUDE.md, .claude/ |
| d015d2654552edfe6d22e93ea5ab642fae3ac27b | docs: adopt existing project into Cadence | fix | .github/cadence/coverage-policy.json, .planning/ | carries .github/cadence/coverage-policy.json (D-02); path-split |
| 3b2990421ce8ca63f50eaf6713b94168cf98af39 | Scope the 'never brief workers directly' rule to Void the app, not agents working in th... | dev tooling | CLAUDE.md | agent rules: CLAUDE.md, .claude/ |
| 72944434ea7b35e42486e279b9c208432fdc8bf6 | docs: capture context for phase 1 | dev tooling | .planning/ | only .planning/ (and docs/superpowers/) paths |
| 2fd08d099ec82a60e17a15e8a56acb4232aa1474 | docs: plan phase 1 - Coverage gate | dev tooling | .planning/, docs/superpowers/ | only .planning/ (and docs/superpowers/) paths |
| 74d2740c1628bdbeb6c9429ca86333ac1f96783e | docs: record phase 1 plan review adjudication | dev tooling | .planning/ | only .planning/ (and docs/superpowers/) paths |
| 710b687adcc6152aa364313397862d2733b45eb1 | chore(1-1): vendor Cadence coverage report checker | fix | .github/cadence/coverage-report-check.mjs | Phase 1 CI and tests (D-02) |
| 74394fcfca95aba5b4bccbbb30f28adc7b9a55dc | feat(1-1): add per-module coverage runner | fix | .github/ci/coverage-modules.mjs | Phase 1 CI and tests (D-02) |
| 55d87a87ca400808d0c0ae395035d6295c6fee30 | test(1-1): prove the per-module coverage gate on hand-built reports | fix | tests/ | Phase 1 CI and tests (D-02) |
| 5a4f07d11d80a6e3a5a923444d08b4c09406c7a4 | chore(1-1): ignore coverage outputs | fix | .gitignore | Phase 1 CI and tests (D-02) |
| 03ef50e0dac8ea5c6adf026f7d11c641ab4fbbb1 | chore(1-1): declare the app's runtime packages for the suite | fix | tests/ | Phase 1 CI and tests (D-02) |
| 45d4f0293104fa6dea39fbba76dc2ede9901b28f | chore(1-1): render the accepted coverage commands | fix | .github/cadence/coverage-policy.json, .planning/ | renders the accepted coverage commands (D-02); path-split |
| 0e1d85db4b734e11812a4b2e297f01a5389217cd | docs(1): move the tests workflow commit to the end of Plan 2 | dev tooling | .planning/ | only .planning/ (and docs/superpowers/) paths |
| 1ce278c769915ed1193093dfdee6d077022412bb | test(1-1): import macsys afresh in the Core Audio test so it ignores collection order | fix | tests/ | Phase 1 CI and tests (D-02) |
| 2f4b0f3eca4db77fab1c06b6567a968397a4fe63 | fix(1-1): fail the per-module coverage gate when the policy includes no module | fix | .github/ci/coverage-modules.mjs, tests/ | Phase 1 CI and tests (D-02) |
| 18c56ef9322e0bf060590cb8540de5c4b8d8bbaf | docs(1): carry the missing-include runner fix into Plan 2 | dev tooling | .planning/ | only .planning/ (and docs/superpowers/) paths |
| cc0e7b931239f679e753c75dcde8e857811792dd | test(1-2): cover the drops log forms, report text and command entry | fix | tests/ | Phase 1 CI and tests (D-02) |
| f4acc7d57bb5e57d48681d27c8a4ee37d686a060 | test(1-2): cover the agents stream events, kill tree and Brain restart and stop paths | fix | tests/ | Phase 1 CI and tests (D-02) |
| 4aac55c01b1c800143f22b3f3cb8d8c24deb6458 | test(1-2): cover macsys at the process boundary and its Cocoa helpers | fix | tests/ | Phase 1 CI and tests (D-02) |
| 3ad520933453a6cfff9378b98cb7b41bc1d29b77 | fix(1-2): fail the per-module coverage gate when the policy has no usable include list | fix | .github/ci/coverage-modules.mjs, tests/ | Phase 1 CI and tests (D-02) |
| 13a1d40a74de614c1a21f626f3a06135dcc70b7f | test(1-2): run the suite and the per-module coverage gate on macos-14 | fix | .github/workflows/tests.yml | Phase 1 CI and tests (D-02) |
| bb0bc235aa4377e1938173cc863af03cf293c095 | docs(1): phase 1 summary | dev tooling | .planning/ | only .planning/ (and docs/superpowers/) paths |
| 8935491c58e0da6ec7c934303c20075486a7dad6 | chore: ignore Cadence run records, the todo list and agent worktrees | dev tooling | .gitignore | ignore lines for Cadence records, the todo list and agent worktrees: serve personal-only paths |
| 0cee55af41f4ce96b30a4a7d43fdbac8f8c79c31 | docs: drop the Void-only worker-brief rule from CLAUDE.md | dev tooling | CLAUDE.md | agent rules: CLAUDE.md, .claude/ |
| 91834ae4b4c2246040eb9ec62c613ec6d84b03ac | chore: add the hearing, replies and stop-echo build queues | dev tooling | queues/ | queues/ build queues |
| 4f95ffb574c13d6a674704e6c482e62742f883c8 | test(1): keep the real-Whisper HeardTest in the VOID_SCENES slow tier | fix | tests/ | slow-tier marker on the real-Whisper test; test harness fix |
| 0b1d0cdedf454f1b642c4ebb802c812f464da3d8 | docs: phase 1 UAT - 5 passed, 0 failed | dev tooling | .planning/ | only .planning/ (and docs/superpowers/) paths |
| 4488777abbe18f14f1908fb00aa9a0ab924762e9 | ci: run the tests and macos workflows on macos-15 | fix | .github/workflows/macos.yml, .github/workflows/tests.yml, .planning/ | tests and macos workflows on macos-15 (D-02, D-09); path-split |
| de4d1cd63e43cc6382f87cb90e3068d10538242a | docs: phase 1 UAT - 6 passed, 1 failed | dev tooling | .planning/ | only .planning/ (and docs/superpowers/) paths |
| ed5da4e33512d6f7863ee9eda728c774deca6e73 | docs: plan phase 1 - Coverage gate | dev tooling | .planning/ | only .planning/ (and docs/superpowers/) paths |
| 74b9aa5a14e05cc0573594b01a08b3fd2a9d3b8d | docs: record the phase 1 gap plan review | dev tooling | .planning/ | only .planning/ (and docs/superpowers/) paths |
| e433e999c0ba6d02357ce4f3d74a073fc9a03756 | test(1-3): show a fake server's own log when its start fails | fix | tests/ | Phase 1 CI and tests (D-02) |
| d158c189b0fd54d4277237f030c7c1c2eafdb884 | chore(1-3): upload the failed-start logs from the tests job | fix | .github/workflows/tests.yml | Phase 1 CI and tests (D-02) |
| 72e9dadb1553cc0881fcf14a6a42645efb1db753 | test(1-3): report the conditions the page tests ran under | fix | tests/ | Phase 1 CI and tests (D-02) |
| 80fa8e880223e71481b79dd623e00b667d5277fb | test(1-3): run the Qt page tests with full motion on any host | fix | tests/ | Phase 1 CI and tests (D-02) |
| 75b8a6cf4a050261ad0c0d19ef0909cd2a47aa51 | test(1-3): judge the page's frame loop against the browser's own rate | fix | tests/ | Phase 1 CI and tests (D-02) |
| 4f583e2cdf27f8431f2e4c62186f9f170bfe47ee | docs(1): phase 1 summary | dev tooling | .planning/ | only .planning/ (and docs/superpowers/) paths |
| 486b45e015aea93f9370e9b0414572ad8745b393 | docs: plan phase 1 - Coverage gate (plan 4: fake servers that bind without a name lookup) | dev tooling | .planning/ | only .planning/ (and docs/superpowers/) paths |
| f7cef2529fd0a43ac4640c24b1156ff305925442 | test(1-4): record the diagnosed cause of the fake-server failures in UAT item 4 | dev tooling | .planning/ | only .planning/ (and docs/superpowers/) paths |
| 6271a78456f741b5c18d7ad944ea3f4169fa1eb6 | test(1-4): bind the child-process fake servers without a name lookup | fix | tests/ | Phase 1 CI and tests (D-02) |
| 89f4bfe451bf296c9196708243f1a86cca7d03fe | test(1-4): bind the in-process test servers without a name lookup | fix | tests/ | Phase 1 CI and tests (D-02) |
| 9b309e085a37533cf7362e4ed8238cd91b52d057 | docs(1): phase 1 summary | dev tooling | .planning/ | only .planning/ (and docs/superpowers/) paths |
| ae7042a5d4bbfb1ef22b8de00b30ed9a58b356cf | docs: phase 1 UAT - 7 passed, 0 failed | dev tooling | .planning/ | only .planning/ (and docs/superpowers/) paths |
| a44878021fc5f68ccee1b8c7e8d9ee401abed9dc | docs: capture context for phase 2 | dev tooling | .planning/ | only .planning/ (and docs/superpowers/) paths |
| 74af430f7fc9e210d229beaf0e6a43d9389e0f63 | docs: plan phase 2 - Branch split | dev tooling | .planning/ | only .planning/ (and docs/superpowers/) paths |

## Path-split

A path-split commit is a `fix` row whose diff also touches a personal-only path. Task 2 looped over every `fix` row and found exactly four; no other `fix` row touches `CLAUDE.md`, `.claude/`, `queues/`, `docs/superpowers/`, `docs/design/` or `.planning/`.

| Commit | Carried onto the fix branch | Left behind on `personal` |
|---|---|---|
| c378787 | `app/drops.py`, `app/gate.py`, `app/server.py`, `app/voiceprint.py` (deleted), `bin/void`, and the `tests/` paths (`scenes.py`, `suite_data.py`, `test_gate.py`, `test_hearing.py`, `test_listen_enrol.py` renamed to `test_listen_verdict.py`, `test_log_cases.py`, `test_scenes.py`, `test_suite_data_dir.py`, `test_voiceprint.py` deleted, `test_wake_loop.py`) | `docs/superpowers/specs/hearing-verdict-design.md` (its 2-line hunk; D-08) |
| d015d26 | `.github/cadence/coverage-policy.json` (D-02, D-09) | `.planning/PROJECT.md`, `.planning/REQUIREMENTS.md`, `.planning/ROADMAP.md`, `.planning/STATE.md`, `.planning/config.json` |
| 45d4f02 | `.github/cadence/coverage-policy.json` | `.planning/config.json` |
| 4488777 | `.github/workflows/macos.yml`, `.github/workflows/tests.yml` (the `macos-15` runner; D-02, D-09) | `.planning/ROADMAP.md`, `.planning/phases/1/CONTEXT.md`, `.planning/phases/1/UAT.md` |

Construction (Plan 2 builds each the same way): `git cherry-pick -n <sha>`, then every personal-only path is put back to its pre-pick state (restored from `HEAD` where it exists there, removed from the index and tree where the commit created it or where the pick leaves a modify/delete conflict on a path the fix branch never had), then `git commit -C <sha>` keeps the original author and message. 45d4f02 and 4488777 modify `.planning/` files that d015d26 left behind, so on the fix branch their `.planning/` paths come out of `cherry-pick -n` as modify/delete conflicts; the restore step removes them. That is the construction, not a hand resolution.

`git cherry` marks every path-split commit `+` (absent), because the fix branch carries a different patch than `personal` has. AC3's exception therefore covers each commit this section names, not only c378787.

A non-path-split `fix` pick can also print `+` by context drift: patch-id hashes context lines, and an excluded neighbour changes them. Plan 2 matches such a commit by author, author date and subject instead.

## Borderline

Each row is a call for the owner's ruling. "Default" is the class the table holds until the owner rules. The ruling column stays empty until Task 6.

| Id | Commit | Option A | Option B | Evidence | Default | Ruling |
|---|---|---|---|---|---|---|
| B-01 | e53ea7b | fix: Esc leaves hover mode on macOS | feature: hover mode gains a key, a `void hover-off` prompt line and new settings-hint text | The message says that as the cursor he takes no click or key, so on macOS "nothing you could do reached him"; touches `app/macsys.py`, `app/window_win.py`, one `app/server.py` prompt line and one `app/static/index.html` hint line | fix | |
| B-02 | a3021dd | feature: smaller Claude sessions (cap Bash output, drop Grep/Glob/WebFetch, deny unused agent roles) | fix: it removes about 5.9k tokens a session | The message measures a saving; no defect is named; it changes which tools Mac users' Void sessions get | feature | |
| B-03 | 8c38409 | visual: a faint spark on the page for a gate_drop event | fix: it shows the owner a dropped clip, part of the fix-bound gate | The message calls it "context-bleed step 4"; it edits `app/static/index.html` and `tests/test_page_sparks.py`, a file created by the Local-only 87344d3 | visual | |
| B-04 | 14b64bf | visual: helper gaze motion on the page | fix: eyes follow helpers while his eyes are shut | One-line condition in `app/static/index.html`; the message calls it a stand-down fix | visual | |
| B-05 | ed2fa27 | visual: the glow ring on the page | fix: his head no longer rises over the glow on a stretch | Two lines in `app/static/index.html`; the message says "since fd7f83e it held still" | visual | |
| B-06 | f3b2947 | fix: delivers inbox alerts to his Claude session, which ping batching (8441f85, fix-bound) builds on | feature: inbox alerts are a capability macos lacks | One commit with no body; `app/server.py` and `tests/test_inbox.py`; `8441f85` and `7ef0a99` edit the same inbox code | fix | |
| B-07 | fb16e92 | fix: pairs with ping batching (context-bleed step 7) | feature: changes what Claude is told to do with long jobs | Two `app/server.py` prompt lines and one test | fix | |
