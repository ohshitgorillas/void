"""Inbox alerts use the voice session path, wait for Claude, and never replay old alerts."""
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
import notifier
import server


class Inbox(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "inbox.log"
        self.messages = []
        self.history = []
        self.replies = []
        self.during = []
        self.lock = threading.Lock()
        for patch in (
            mock.patch.object(server.ST, "lock", self.lock),
            mock.patch.object(server.ST, "auto_pick", ""),
            mock.patch.object(server.ST, "stopped", False),
            mock.patch.object(server.ST, "alerting", False),
            mock.patch.object(server.ST, "compacting", False),
            mock.patch.object(server.ST, "last_worked", False),
            mock.patch.dict(server.CFG, {"long_lived": True, "auto_compact": False,
                                         "ping_quiet_s": 0.2, "ping_hold_s": 5}),   # short spells, not 20 s / 2 min
            mock.patch.dict(server.LONG, {"ok": True}),
            mock.patch.object(server, "claude_bin", return_value="claude"),
            mock.patch.object(server, "brain_launch", return_value={"session": "existing-session"}),
            mock.patch.object(server.BRAIN, "ask", side_effect=self.ask),
            mock.patch.object(server, "hist_add", side_effect=self.history.append),
            mock.patch.object(server.recall, "add"),
            mock.patch.object(server.BUS, "pub", side_effect=lambda **ev: self.replies.append(ev)),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def ask(self, launch, prompt, emit):
        self.assertEqual(launch["session"], "existing-session")
        self.assertTrue(self.lock.locked())
        self.messages.append(prompt)
        self.during.append((server.ST.alerting, server.lock_wait()))
        emit(t="result", text="Alert received", is_error=False)

    def append(self, text):
        with self.path.open("a", encoding="utf-8") as f:
            f.write(text)

    def start(self):
        follower = server.InboxFollower(self.path)
        follower.start()
        self.addCleanup(follower.close)
        return follower

    def followups(self):
        return [ev for ev in self.replies if ev["t"] == "followup"]

    def wait_for_replies(self, count):
        until = time.monotonic() + 3
        while len(self.followups()) < count and time.monotonic() < until:
            time.sleep(0.01)
        self.assertEqual(len(self.followups()), count)

    def test_appended_alerts_reach_session_in_order_after_busy_and_skip_own_stop(self):
        self.append("2026-10-23 10:00:00 [worker] old alert\n")
        self.lock.acquire()
        try:
            follower = self.start()
            first = "2026-10-23 10:01:00 [builder] tests passed"
            second = "2026-10-23 10:01:01 [claude] other session finished"
            third = "2026-10-23 10:01:02 [worker] atom Stop is not our echo"
            self.append(first + "\n2026-10-23 10:01:00 [claude] atom Stop hook echo\n" + second + "\n" + third + "\n")
            time.sleep(0.8)                   # the watcher reads the file and the quiet spell ends while the session is occupied
            self.assertEqual(self.messages, [])
        finally:
            self.lock.release()
        self.wait_for_replies(1)
        follower.close()
        self.assertEqual(self.messages, [notifier.digest([first, second, third])])
        self.assertEqual([rec["you"] for rec in self.history], self.messages)
        self.assertTrue(all(ev == {"t": "followup", "text": "Alert received", "ok": True} for ev in self.followups()))

    def test_your_message_waits_for_an_alert_and_he_shows_he_is_on_it(self):
        follower = self.start()
        self.assertEqual(server.lock_wait(), 0)          # his own answer to you: a second message is refused
        line = "2026-10-23 10:01:00 [worker] done"
        self.append(line + "\n")
        self.wait_for_replies(1)
        follower.close()
        self.assertEqual(self.messages, [notifier.digest([line])])
        alerting, wait = self.during[0]
        self.assertTrue(alerting)
        self.assertGreater(wait, 0)
        self.assertEqual([ev["t"] for ev in self.replies], ["followup_soon", "followup"])
        self.assertFalse(server.ST.alerting)
        self.assertEqual(server.lock_wait(), 0)

    def test_missing_inbox_and_partial_line(self):
        follower = self.start()
        line = "2026-10-23 10:01:00 [worker] ready café"
        self.append(line)
        time.sleep(0.8)                   # longer than a read plus the quiet spell
        self.assertEqual(self.messages, [])
        self.append("\n")
        self.wait_for_replies(1)
        follower.close()
        self.assertEqual(self.messages, [notifier.digest([line])])

    def test_preexisting_partial_line_is_not_delivered(self):
        self.append("2026-10-23 10:00:00 [worker] old partial")
        follower = self.start()
        line = "2026-10-23 10:01:00 [worker] new alert"
        self.append(" completed\n" + line + "\n")
        self.wait_for_replies(1)
        follower.close()
        self.assertEqual(self.messages, [notifier.digest([line])])

    def test_close_while_busy_does_not_deliver(self):
        self.lock.acquire()
        try:
            follower = self.start()
            self.append("2026-10-23 10:01:00 [worker] waiting\n")
            time.sleep(0.8)               # the batch is due and its delivery is waiting on the lock
            follower.close()
            self.assertFalse(follower.thread.is_alive())
        finally:
            self.lock.release()
        self.assertEqual(self.messages, [])


class Batching(unittest.TestCase):
    """Pings arriving close together reach the session as one turn: notifier.PingBatch decides when, notifier.digest
    writes it, and the spells come from ping_quiet_s and ping_hold_s."""
    setUp_inbox = Inbox.setUp
    ask = Inbox.ask
    append = Inbox.append
    start = Inbox.start
    followups = Inbox.followups
    wait_for_replies = Inbox.wait_for_replies

    def setUp(self):
        self.setUp_inbox()
        self.spells(quiet=0.6, hold=30)

    def spells(self, *, quiet, hold):
        patch = mock.patch.dict(server.CFG, {"ping_quiet_s": quiet, "ping_hold_s": hold})
        patch.start()
        self.addCleanup(patch.stop)

    def bind(self, name, value):
        """Replace notifier.<name> wherever server can reach it."""
        for module in (notifier, server):
            if module is notifier or hasattr(module, name):
                patch = mock.patch.object(module, name, value)
                patch.start()
                self.addCleanup(patch.stop)

    def test_spells_default_to_twenty_seconds_quiet_and_two_minutes_hold(self):
        self.assertEqual(server.DEFAULTS["ping_quiet_s"], 20)
        self.assertEqual(server.DEFAULTS["ping_hold_s"], 120)

    def test_five_lines_in_one_quiet_spell_give_exactly_one_turn(self):
        follower = self.start()
        lines = [f"2026-10-25 10:00:0{i} [worker] step {i} done" for i in range(5)]
        for line in lines:                       # spread over several reads, never quiet for a whole spell
            self.append(line + "\n")
            time.sleep(0.1)
        self.wait_for_replies(1)
        time.sleep(1.0)                          # nothing more follows the one turn
        follower.close()
        self.assertEqual(len(self.followups()), 1)
        self.assertEqual(self.messages, [notifier.digest(lines)])
        self.assertEqual([rec["you"] for rec in self.history], self.messages)

    def test_a_ping_waits_out_the_quiet_spell(self):
        self.spells(quiet=1.5, hold=30)
        follower = self.start()
        line = "2026-10-25 10:00:00 [worker] ready"
        self.append(line + "\n")
        time.sleep(0.8)
        self.assertEqual(self.messages, [])      # the spell is still running
        self.wait_for_replies(1)
        follower.close()
        self.assertEqual(self.messages, [notifier.digest([line])])

    def test_the_hold_spell_cuts_a_batch_that_never_goes_quiet(self):
        self.spells(quiet=0.8, hold=1.0)
        follower = self.start()
        lines = [f"2026-10-25 10:00:{i:02d} [worker] tick {i}" for i in range(12)]
        for line in lines:
            self.append(line + "\n")
            time.sleep(0.2)
        self.assertGreaterEqual(len(self.messages), 1)   # a turn went out before the pings stopped
        until = time.monotonic() + 3
        while sum(m.count("\n") + 1 for m in self.messages) < len(lines) and time.monotonic() < until:
            time.sleep(0.01)
        follower.close()
        self.assertGreaterEqual(len(self.messages), 2)
        self.assertLess(len(self.messages), len(lines))  # batched, not one turn per ping
        self.assertEqual("\n".join(self.messages), notifier.digest(lines))

    def test_batching_is_notifiers_and_the_follower_only_feeds_and_delivers(self):
        made = []
        real = notifier.PingBatch

        class Spy(real):
            def __init__(self, quiet_s, hold_s, *a, **kw):
                super().__init__(quiet_s, hold_s, *a, **kw)
                self.spells, self.fed = (quiet_s, hold_s), []
                made.append(self)

            def add(self, line):
                self.fed.append(line)
                super().add(line)

        self.bind("PingBatch", Spy)
        self.bind("digest", lambda batch: "DIGEST:" + "|".join(batch))
        follower = self.start()
        lines = [f"2026-10-25 10:00:0{i} [worker] part {i}" for i in range(3)]
        self.append("".join(line + "\n" for line in lines))
        self.wait_for_replies(1)
        follower.close()
        self.assertEqual(len(made), 1)
        self.assertEqual(made[0].spells, (0.6, 30))
        self.assertEqual(made[0].fed, lines)
        self.assertEqual(self.messages, ["DIGEST:" + "|".join(lines)])


if __name__ == "__main__":
    unittest.main()
