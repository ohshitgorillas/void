# Declined: findings this repository said no to

Written by `issue-filing.mjs file` when a gate's finding is DECLINED, read by
`issue-filing.mjs unfixed` as the set it must never ask about again. Same row
grammar as FILED.md: the date, the provider, the repository slug, the finding's
(file, claim) fingerprint and its title.

NOT part of the recall corpus and not a queue. `planning.mjs recall` reads
CAPTURE.md, ARCHIVE.md, the task records and FILED.md by explicit path, and
this file is deliberately absent from that list - a decline is a closed
question, and putting closed questions in front of a planner is the
accumulation the corpus rules exist to prevent. Query it, do not load it.

A line that is not a row is skipped, so a human note added here changes nothing
the seam reads.

- 2026-11-07 github ohshitgorillas/void 917afabf19510a7e: [cadence 917afabf19510a7e] Task 7 adds a second always-running requestAnimationFrame loop to the page the test measures, and its replacement band and minimum are left to the executor with no number.
- 2026-11-08 github ohshitgorillas/void aa267b4292b385f7: [cadence aa267b4292b385f7] The `g == cls.gen` check and the `note_played` call that follows it are not atomic with `Speaker.stop` bumping `gen` and `Wake.hush` calling `played_cut`. A hushed sentence'
