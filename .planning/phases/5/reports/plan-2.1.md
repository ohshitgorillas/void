PLAN CHECKPOINT: blocked
Plan: /Users/atom/dev/void/.planning/phases/5/PLAN-2.md
Tasks: 1 of 3
| Task | Commit | Note |
|---|---|---|
| 1 The server takes a sentence's played words on the page's /api/speaking post | ed2b892 | note_page_played(b, end) + _page_words in app/server.py; the on-true branch notes before Wake.talking_until(end); on-false calls played_cut at the time it ends the record. 5 new tests in PageSpeaking (fake server clock, so t_before == t_after). tests/test_wake_loop.py: 78 passed. git grep "/api/played" app/ prints nothing |
| 2 The page sends each sentence's text, length and word times | NOT COMMITTED | Working tree of /Users/atom/dev/void-own-stop (uncommitted, unstaged): app/static/index.html (enqueue keeps `text`; pump's on-true post carries text, dur, words/r or null), new tests/test_page_played.py (7 tests), and a one-line edit to tests/test_page_sound.py. Targeted run (test_page_played + test_page_sound + test_page_held): 31 passed, none skipped. Blocked at the commit: lease-check says undeclared-files: tests/test_page_sound.py |
| 3 A scene can play Void's line through the page's player | not started | |
Deviations: none
Open items: Task 2 is blocked on a lease gap. The page's post now carries text, dur and words, so tests/test_page_sound.py's existing order assertion (test_posts_follow_the_order_the_page_made_them_with_the_hearing_settings_off) fails on the extra keys (observed: expected [['left','on','paid']...], got ['dur','left','on','paid','text','words']). Fix is one line there (ignore text/dur/words in the key sort); the plan's `files:` does not name tests/test_page_sound.py. Needs either that path added to PLAN-2.md's files: list, or a ruling to commit the red test (not proposed).
