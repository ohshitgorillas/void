"""PlayRef keeps what the speakers play, by monotonic time, at 16 kHz mono s16le, with silence where nothing plays,
whatever rate the player itself runs at; and once the speakers are stopped, nothing after that moment plays.
Canceller takes Void's own voice out of the mic against that record, leaving yours, whole from its first moment
even when you talk over him; off, or without livekit, it hands
the mic back untouched and says so once.
Speech-to-text hands back what was heard together with Whisper's confidence in it (Heard), while run_whisper still
hands back just the text.

    python3 -m unittest tests.test_hearing -v
"""
import array
import contextlib
import importlib
import inspect
import io
import math
import random
import sys
import unittest
import wave
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import suite_data  # noqa: E402  (Void's data folder: the suite's own, set before server.py settles it)

try:
    import hearing
except Exception as e:  # noqa: BLE001
    hearing, IMPORT_ERR = None, e
else:
    IMPORT_ERR = None

try:
    import server
except Exception as e:  # noqa: BLE001
    server, SERVER_ERR = None, e
else:
    SERVER_ERR = None

SR = 16000                                                  # the rate PlayRef keeps
EDGE = 160                                                  # 10 ms of slack at a resampled edge


def pcm(samples):
    return array.array("h", samples).tobytes()


def samples(b):
    a = array.array("h")
    a.frombytes(b)
    return list(a)


def tone(value, rate, secs):
    """A steady level for `secs` at `rate`: survives any resampling as the same level."""
    return pcm([value] * round(rate * secs))


@unittest.skipIf(hearing is None, f"hearing.py doesn't import here: {IMPORT_ERR}")
class PlayRefTest(unittest.TestCase):
    def setUp(self):
        global hearing
        hearing = importlib.reload(hearing)                 # a fresh PlayRef: no state left by another test
        self.P = hearing.PlayRef

    def assertLevel(self, got, value, msg=""):
        self.assertTrue(got, f"no samples {msg}")
        bad = [x for x in got if abs(x - value) > max(64, abs(value) * 0.05)]
        self.assertFalse(bad, f"{len(bad)} of {len(got)} samples off level {value} {msg}: e.g. {bad[:5]}")

    def test_silence_where_nothing_has_played(self):
        self.assertEqual(self.P.span(100.0, 1600), bytes(3200))

    def test_span_is_n_samples_of_16k_s16le(self):
        self.P.played(tone(5000, 22050, 1.0), 22050, 100.0)
        for at, n in ((100.0, 1), (100.25, 4000), (99.0, 48000)):
            self.assertEqual(len(self.P.span(at, n)), 2 * n, f"span({at}, {n})")

    def test_16k_audio_comes_back_as_played(self):
        src = [(i * 37) % 20000 - 10000 for i in range(SR // 2)]
        self.P.played(pcm(src), SR, 100.0)
        self.assertEqual(samples(self.P.span(100.0, len(src))), src)

    def test_other_rates_come_back_at_16k_with_the_same_duration(self):
        self.P.played(tone(6000, 22050, 0.5), 22050, 100.0)       # half a second at the player's rate
        got = samples(self.P.span(100.0, SR))                      # one second at 16 kHz
        self.assertLevel(got[EDGE:SR // 2 - EDGE], 6000, "inside the half second played")
        self.assertLevel(got[SR // 2 + EDGE:], 0, "after it ends")

    def test_audio_sits_at_its_play_time(self):
        self.P.played(tone(7000, SR, 0.25), SR, 100.5)
        got = samples(self.P.span(100.0, SR))
        self.assertLevel(got[:SR // 2], 0, "before it plays")
        self.assertLevel(got[SR // 2:SR * 3 // 4], 7000, "while it plays")
        self.assertLevel(got[SR * 3 // 4:], 0, "after it ends")

    def test_chunks_follow_each_other_and_gaps_are_silent(self):
        self.P.played(tone(3000, 24000, 0.2), 24000, 100.0)
        self.P.played(tone(-4000, 24000, 0.2), 24000, 100.2)       # straight after the first
        self.P.played(tone(5000, 24000, 0.2), 24000, 100.6)        # after 200 ms of nothing
        got = samples(self.P.span(100.0, SR))
        ms = SR // 1000
        self.assertLevel(got[EDGE:200 * ms - EDGE], 3000, "first chunk")
        self.assertLevel(got[200 * ms + EDGE:400 * ms - EDGE], -4000, "second chunk")
        self.assertLevel(got[400 * ms + EDGE:600 * ms - EDGE], 0, "the gap")
        self.assertLevel(got[600 * ms + EDGE:800 * ms - EDGE], 5000, "third chunk")
        self.assertLevel(got[800 * ms + EDGE:], 0, "after the last")

    def test_cut_silences_everything_after_it(self):
        self.P.played(tone(8000, 22050, 1.0), 22050, 100.0)
        self.P.cut(100.4)
        got = samples(self.P.span(100.0, SR))
        self.assertLevel(got[EDGE:int(0.4 * SR) - EDGE], 8000, "before the cut")
        self.assertLevel(got[int(0.4 * SR) + EDGE:], 0, "after the cut")

    def test_playing_resumes_after_a_cut(self):
        self.P.played(tone(8000, SR, 1.0), SR, 100.0)
        self.P.cut(100.2)
        self.P.played(tone(-6000, SR, 0.2), SR, 100.5)
        got = samples(self.P.span(100.0, SR))
        self.assertLevel(got[:int(0.2 * SR)], 8000, "before the cut")
        self.assertLevel(got[int(0.2 * SR):int(0.5 * SR)], 0, "between the cut and the next chunk")
        self.assertLevel(got[int(0.5 * SR):int(0.7 * SR)], -6000, "the chunk played after the cut")
        self.assertLevel(got[int(0.7 * SR):], 0, "after it ends")


try:
    import livekit.rtc  # noqa: F401
except Exception as e:  # noqa: BLE001
    LIVEKIT_ERR = e
else:
    LIVEKIT_ERR = None

CHUNK = SR // 50                                            # the mic's 20 ms, in samples
T0 = 100.0                                                  # monotonic time the audio starts at


def rms(x):
    return math.sqrt(sum(v * v for v in x) / len(x)) if x else 0.0


def noise(secs, level, seed):
    """Speech-band-ish broadband sound: what Void's voice looks like to an echo canceller."""
    rng = random.Random(seed)
    return [max(-32768, min(32767, round(rng.gauss(0, level)))) for _ in range(round(SR * secs))]


def voice(secs, level):
    """Your voice: voiced harmonics, rising and falling four times a second like syllables."""
    n = round(SR * secs)
    return [round(level * (0.6 + 0.4 * math.sin(2 * math.pi * 4 * i / SR))
                  * (math.sin(2 * math.pi * 180 * i / SR) + 0.5 * math.sin(2 * math.pi * 360 * i / SR)
                     + 0.25 * math.sin(2 * math.pi * 540 * i / SR))) for i in range(n)]


@unittest.skipIf(hearing is None, f"hearing.py doesn't import here: {IMPORT_ERR}")
class CancellerTest(unittest.TestCase):
    def setUp(self):
        global hearing
        hearing = importlib.reload(hearing)                 # a fresh PlayRef: nothing left playing by another test

    def run_mic(self, c, mic):
        """Feed mic (samples from T0) through c in 20 ms chunks at their capture times; the cleaned samples back."""
        out = []
        for i in range(0, len(mic), CHUNK):
            chunk = pcm(mic[i:i + CHUNK])
            got = c.process(chunk, T0 + i / SR)
            self.assertEqual(len(got), len(chunk), f"process() at {T0 + i / SR:.2f} changed the length")
            out += samples(got)
        return out

    def assertPassesThrough(self, make):
        """Whatever `make` builds hands the mic back untouched, says it isn't cancelling, and says so once."""
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            c = make()
            hearing.PlayRef.played(pcm(noise(0.5, 4000, 1)), SR, T0)       # something playing: still untouched
            mic = noise(0.5, 3000, 2)
            for i in range(0, len(mic), CHUNK):
                chunk = pcm(mic[i:i + CHUNK])
                self.assertEqual(c.process(chunk, T0 + i / SR), chunk, f"mic changed at {T0 + i / SR:.2f}")
            self.assertEqual(c.process(pcm([123] * 77), T0 + 1), pcm([123] * 77), "an odd-sized chunk changed")
        self.assertIs(c.available, False)
        said = [ln for ln in err.getvalue().splitlines() if ln.startswith("[void]")]
        self.assertEqual(len(said), 1, f"expected one [void] line saying it passes the mic through, got {said}")

    def test_off_passes_the_mic_through_and_says_so_once(self):
        self.assertPassesThrough(lambda: hearing.Canceller(on=False))

    def test_passes_the_mic_through_when_livekit_cannot_load(self):
        blocked = {m: None for m in list(sys.modules) if m == "livekit" or m.startswith("livekit.")}
        blocked.update({"livekit": None, "livekit.rtc": None})            # None in sys.modules: import fails
        self.addCleanup(importlib.reload, hearing)                        # (after the patch lifts: the real livekit)
        with mock.patch.dict(sys.modules, blocked):
            importlib.reload(hearing)
            self.assertPassesThrough(lambda: hearing.Canceller(on=True))

    @unittest.skipIf(LIVEKIT_ERR is not None, f"livekit doesn't import here: {LIVEKIT_ERR}")
    def test_on_with_livekit_is_available(self):
        self.assertIs(hearing.Canceller().available, True)

    @unittest.skipIf(LIVEKIT_ERR is not None, f"livekit doesn't import here: {LIVEKIT_ERR}")
    def test_returns_the_length_it_was_given(self):
        c = hearing.Canceller(on=True)
        hearing.PlayRef.played(pcm(noise(1.0, 4000, 3)), SR, T0)
        at = T0
        for n in (160, 320, 480, 1, 77, 1000, 3200, 0):              # 10 ms multiples and not
            got = c.process(pcm(noise(n / SR, 3000, n)), at)
            self.assertEqual(len(got), 2 * n, f"process() of {n} samples")
            at += n / SR

    @unittest.skipIf(LIVEKIT_ERR is not None, f"livekit doesn't import here: {LIVEKIT_ERR}")
    def test_takes_his_own_voice_out_of_the_mic(self):
        far = noise(4.0, 4000, 4)
        hearing.PlayRef.played(pcm(far), SR, T0)
        d = SR // 200                                                # the room: 5 ms later, at half the level
        mic = [0] * d + [v // 2 for v in far[:-d]]
        out = self.run_mic(hearing.Canceller(on=True), mic)
        before, after = rms(mic[-SR:]), rms(out[-SR:])
        self.assertLess(after, before / 4, f"his echo in the last second: {after:.0f} RMS out of {before:.0f} in")

    @unittest.skipIf(LIVEKIT_ERR is not None, f"livekit doesn't import here: {LIVEKIT_ERR}")
    def test_leaves_your_voice_whole_from_its_start_when_you_talk_over_him(self):
        far = noise(4.0, 4000, 5)
        hearing.PlayRef.played(pcm(far), SR, T0)
        d, at = SR // 200, 3 * SR                                    # the room: 5 ms later, at half the level
        you = [0] * at + voice(1.0, 1500)
        mic = [e + y for e, y in zip([0] * d + [v // 2 for v in far[:-d]], you)]
        out = self.run_mic(hearing.Canceller(on=True), mic)
        n, u = 3 * SR // 10, you[at:at + 3 * SR // 10]              # your first 0.3 s
        g = max(sum(a * b for a, b in zip(out[at + k:at + k + n], u)) for k in range(0, 400, 2)) / sum(v * v for v in u)
        self.assertGreater(g, 10 ** (-3 / 20), f"your first 0.3 s over him came through at {g:.2f} of how you said it")

    @unittest.skipIf(LIVEKIT_ERR is not None, f"livekit doesn't import here: {LIVEKIT_ERR}")
    def test_leaves_your_voice_in_when_he_is_quiet(self):
        mic = voice(3.0, 3000)
        out = self.run_mic(hearing.Canceller(on=True), mic)
        before, after = rms(mic[-SR:]), rms(out[-SR:])
        self.assertGreater(after, before / 2, f"your voice in the last second: {after:.0f} RMS out of {before:.0f} in")


@unittest.skipIf(server is None, f"server.py doesn't import here: {SERVER_ERR}")
class EchoCancelSettingTest(unittest.TestCase):
    def test_echo_cancel_is_on_by_default(self):
        self.assertIs(server.DEFAULTS.get("echo_cancel"), True)


SPK_RATE = 8000                                             # the player's rate in the Speaker tests
SPK_STEP = 320                                              # bytes Speaker._write hands over at a time: 20 ms at 8 kHz


class FakeRef:
    """Stands in for hearing.PlayRef: records what it is told played, and where it was cut."""
    def __init__(self):
        self.calls, self.cuts, self.moved = [], [], []

    def played(self, pcm, rate, at):
        self.calls.append((bytes(pcm), rate, at))

    def cut(self, at, moved=False):
        self.cuts.append(at)
        self.moved.append(moved)


class FakePlayer:
    """A player that plays in real time (the fake clock moves on as each chunk goes in) and dies after `dies` writes."""
    def __init__(self, clock, dies=None):
        self.clock, self.dies, self.got, self.killed, self.dead = clock, dies, b"", False, False
        self.stdin = self

    def write(self, b):
        if self.dies is not None and len(self.got) // SPK_STEP >= self.dies:
            self.dead = True
            raise BrokenPipeError("the speakers have changed")
        self.got += b
        self.clock[0] += len(b) / 2 / SPK_RATE

    def flush(self):
        pass

    def poll(self):
        return 0 if self.dead else None

    def kill(self):
        self.killed = True


@unittest.skipIf(server is None or hearing is None, f"server.py or hearing.py doesn't import here: {SERVER_ERR or IMPORT_ERR}")
class SpeakerFeedsPlayRefTest(unittest.TestCase):
    """What Void hands the speakers goes into PlayRef at the time it will play; stopping him cuts it there."""
    def setUp(self):
        S = server.Speaker
        self.clock = [100.0]
        self.ref = FakeRef()
        self.made = []
        self.player = FakePlayer(self.clock)
        for k, v in (("gen", 7), ("proc", self.player), ("prate", SPK_RATE), ("written", 1000), ("t0", 100.0),
                     ("filled", False), ("stats", {}), ("todo", []), ("ready", [])):
            self.patch(S, k, v)
        self.patch(server.time, "monotonic", lambda: self.clock[0])
        self.patch(server.time, "sleep", lambda s: self.clock.__setitem__(0, self.clock[0] + s))
        self.patch(server, "make_player", self.make_player)
        self.patch(hearing, "PlayRef", self.ref)
        self.patch(server.Wake, "hush", classmethod(lambda cls, at=None: None))

    def patch(self, obj, name, value):
        p = mock.patch.object(obj, name, value)
        p.start()
        self.addCleanup(p.stop)

    def make_player(self, rate):
        proc = FakePlayer(self.clock)
        self.made.append(proc)
        return proc

    def test_write_feeds_playref_with_everything_it_plays_at_its_rate(self):
        data = bytes(range(256)) * 19
        self.assertTrue(server.Speaker._write(data, 7))
        self.assertTrue(self.ref.calls, "Speaker._write never told PlayRef anything played")
        self.assertEqual(b"".join(c[0] for c in self.ref.calls), self.player.got, "PlayRef wasn't told what played")
        self.assertEqual({c[1] for c in self.ref.calls}, {SPK_RATE}, "PlayRef was told the wrong rate")

    def test_write_stamps_each_chunk_with_when_it_will_play(self):
        data = bytes(range(256)) * 19
        start = 100.0 + 1000 / SPK_RATE                                # t0 + written / prate: after what's queued
        self.assertTrue(server.Speaker._write(data, 7))
        self.assertTrue(self.ref.calls, "Speaker._write never told PlayRef anything played")
        first = self.ref.calls[0][2]
        self.assertGreaterEqual(first, start - 1e-6, "the first chunk is stamped before the queue ahead of it plays")
        self.assertLessEqual(first, start + server.Speaker.LAT + 1e-6, "the first chunk is stamped too late")
        for (a, _, t), (_, _, u) in zip(self.ref.calls, self.ref.calls[1:]):
            self.assertAlmostEqual(u, t + len(a) / 2 / SPK_RATE, delta=1e-6,
                                   msg="consecutive chunks aren't stamped back to back")

    def test_write_doesnt_count_a_chunk_the_dead_player_never_took(self):
        self.player.dies = 5
        data = bytes(range(256)) * 19
        self.assertTrue(server.Speaker._write(data, 7))
        self.assertEqual(len(self.made), 1)
        told = b"".join(c[0] for c in self.ref.calls)
        n = len(self.player.got)
        self.assertEqual(told[:n], self.player.got, "what the old player took isn't what PlayRef was told")
        self.assertEqual(told[n:], self.made[0].got, "what the new player took isn't what PlayRef was told")

    def test_stop_cuts_playref_at_the_moment_of_the_stop(self):
        self.clock[0] = 123.0
        server.Speaker.stop()
        self.assertEqual(len(self.ref.cuts), 1, f"Speaker.stop cut PlayRef {len(self.ref.cuts)} times")
        self.assertGreaterEqual(self.ref.cuts[0], 123.0 - 1e-6)
        self.assertLessEqual(self.ref.cuts[0], 123.0 + server.Speaker.LAT + 1e-6)
        self.assertEqual(self.ref.moved, [False], "stopping him was taken for the speakers changing")

    def test_a_dead_player_cuts_playref_as_the_speakers_changing(self):
        self.player.dies = 5
        self.assertTrue(server.Speaker._write(bytes(range(256)) * 19, 7))
        self.assertEqual(self.ref.moved, [True], "the old speakers dying wasn't told to PlayRef as a change of speakers")

    def test_a_write_killed_by_stop_isnt_taken_for_the_speakers_changing(self):
        player, take = self.player, self.player.write

        def write(b):                                       # stopped while this chunk is going in: the pipe breaks
            if len(player.got) // SPK_STEP >= 5:
                server.Speaker.stop()
                raise BrokenPipeError("killed by the stop")
            take(b)
        player.write = write
        self.assertFalse(server.Speaker._write(bytes(range(256)) * 19, 7))
        self.assertEqual(self.made, [], "a stopped write started a new player")
        self.assertNotIn(True, self.ref.moved, "a write killed by stopping him was taken for the speakers changing")


MIC_RATE = 16000


class FakeMic:
    """A mic that captures in real time: each read hands back the next chunk, the fake clock having moved on by its
    length while it was captured. An empty chunk is "nothing yet"; None is the mic stopping (EOFError)."""
    def __init__(self, clock, chunks):
        self.clock, self.chunks, self.timeouts, self.closed = clock, list(chunks), [], 0
        self.name = "fakemic"

    def read(self, timeout):
        self.timeouts.append(timeout)
        c = self.chunks.pop(0)
        if c is None:
            raise EOFError
        self.clock[0] += len(c) / 2 / MIC_RATE
        return c

    def close(self):
        self.closed += 1

    def err(self):
        return "the mic's last words"


def flip(b):
    return bytes(x ^ 0xFF for x in b)


class FakeCanceller:
    """Stands in for hearing.Canceller: flips every bit of what it's given, and remembers each chunk and its stamp."""
    made = []

    def __init__(self, on=True):
        self.on, self.seen, self.available = on, [], True
        FakeCanceller.made.append(self)

    def process(self, mic, at):
        self.seen.append((bytes(mic), at))
        return flip(mic)


@unittest.skipIf(server is None or hearing is None, f"server.py or hearing.py doesn't import here: {SERVER_ERR or IMPORT_ERR}")
class OpenCleanMicTest(unittest.TestCase):
    """open_clean_mic is open_mic with everything it hands over first put through a Canceller, stamped with when it
    was captured."""
    FIRST = bytes(range(256)) * 12 + bytes(64)                 # 100 ms at 16 kHz, captured just before it returns
    CHUNK = bytes(range(1, 241)) * 2 + bytes(range(160))       # 20 ms

    def setUp(self):
        self.clock = [200.0]
        FakeCanceller.made = []
        self.mic = FakeMic(self.clock, [self.CHUNK, b"", self.CHUNK, None])
        self.opened = 0
        for obj, k, v in ((server.time, "monotonic", lambda: self.clock[0]), (hearing, "Canceller", FakeCanceller),
                          (server, "open_mic", self.open_mic)):
            p = mock.patch.object(obj, k, v)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.dict(server.CFG, {"echo_cancel": True})
        p.start()
        self.addCleanup(p.stop)

    def open_mic(self):
        self.opened += 1
        return self.mic, "fakemic", self.FIRST

    def drain(self, mic):
        """Read until the mic stops: every non-empty chunk handed over."""
        out = []
        with self.assertRaises(EOFError):
            while True:
                c = mic.read(0.2)
                if c:
                    out.append(c)
        return out

    def test_opens_the_mic_through_open_mic_and_keeps_its_name(self):
        _mic, name, first = server.open_clean_mic()
        self.assertEqual(self.opened, 1)
        self.assertEqual(name, "fakemic")
        self.assertEqual(len(first), len(self.FIRST))

    def test_makes_its_canceller_with_the_echo_cancel_setting(self):
        for on in (True, False):
            FakeCanceller.made = []
            with mock.patch.dict(server.CFG, {"echo_cancel": on}):
                server.open_clean_mic()
            self.assertEqual([c.on for c in FakeCanceller.made], [on], f"with echo_cancel {on}")

    def test_first_has_been_through_the_canceller(self):
        _mic, _name, first = server.open_clean_mic()
        self.assertEqual(first, flip(self.FIRST), "first wasn't handed over as the canceller gave it back")

    def test_everything_read_has_been_through_the_canceller_in_order(self):
        mic, _name, first = server.open_clean_mic()
        out = self.drain(mic)
        self.assertEqual(first + b"".join(out), flip(self.FIRST + self.CHUNK * 2))
        self.assertEqual(len(FakeCanceller.made), 1, "one canceller for the whole session")
        fed = b"".join(m for m, _ in FakeCanceller.made[0].seen)
        self.assertEqual(fed, self.FIRST + self.CHUNK * 2, "the canceller wasn't fed the mic's audio, all of it, in order")

    def test_each_chunk_is_stamped_with_when_it_was_captured(self):
        mic, _name, _first = server.open_clean_mic()
        self.drain(mic)
        self.assertEqual(len(FakeCanceller.made), 1, "one canceller for the whole session")
        seen = [(m, at) for m, at in FakeCanceller.made[0].seen if m]
        self.assertEqual([len(m) for m, _ in seen], [len(self.FIRST), len(self.CHUNK), len(self.CHUNK)])
        # FIRST was captured over the 100 ms before open returned at 200.0; each CHUNK over the 20 ms before its read
        for (_, at), want in zip(seen, (199.9, 200.0, 200.02)):
            self.assertAlmostEqual(at, want, delta=0.025, msg="a chunk wasn't stamped with when it was captured")

    def test_read_passes_its_timeout_and_nothing_yet_through(self):
        mic, _name, _first = server.open_clean_mic()
        self.assertEqual(mic.read(0.2), flip(self.CHUNK))
        self.assertEqual(mic.read(0.7), b"")
        self.assertEqual(self.mic.timeouts, [0.2, 0.7])

    def test_close_and_err_are_the_mics(self):
        mic, _name, _first = server.open_clean_mic()
        self.assertIsNot(mic, self.mic, "the mic itself came back, not one that cancels")
        self.assertEqual(mic.err(), "the mic's last words")
        mic.close()
        self.assertEqual(self.mic.closed, 1)


class Opened(Exception):
    pass


@unittest.skipIf(server is None, f"server.py doesn't import here: {SERVER_ERR}")
class SessionsOpenTheCleanMicTest(unittest.TestCase):
    """Listen.run and Wake.session hear the mic with his own voice taken out."""
    def setUp(self):
        def which(name):
            def f(*a, **k):
                raise Opened(name)
            return f
        for k in ("open_mic", "open_clean_mic"):
            p = mock.patch.object(server, k, which(k))
            p.start()
            self.addCleanup(p.stop)

    def test_listen_opens_the_clean_mic(self):
        with self.assertRaises(Opened) as e:
            server.Listen("auto").run(lambda **k: None)
        self.assertEqual(str(e.exception), "open_clean_mic")

    def test_wake_session_opens_the_clean_mic(self):
        with self.assertRaises(Opened) as e:
            server.Wake.session()
        self.assertEqual(str(e.exception), "open_clean_mic")


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "scenes"
try:
    import faster_whisper  # noqa: F401
except Exception as e:  # noqa: BLE001
    WHISPER_ERR = e
else:
    WHISPER_ERR = None


def fixture(name):
    """A committed scene clip as raw s16le 16 kHz mono."""
    with wave.open(str(FIXTURES / name)) as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (SR, 1, 2), name
        return w.readframes(w.getnframes())


@unittest.skipIf(server is None, f"server.py doesn't import here: {SERVER_ERR}")
@unittest.skipIf(WHISPER_ERR is not None, f"faster-whisper doesn't import here: {WHISPER_ERR}")
class HeardTest(unittest.TestCase):
    """What was heard comes back with how sure Whisper was of it, on a real clip of you through real Whisper."""

    @classmethod
    def setUpClass(cls):
        cls.patches = [mock.patch.dict(server.CFG, {"language": "en", "whisper_beam": 5, "whisper_model": "base.en",
                                                    "whisper_device": "cpu"}),
                       mock.patch.object(server, "_whisper", None), mock.patch.object(server, "_whisper_err", None)]
        for p in cls.patches:
            p.start()
        cls.pcm = fixture("you_stop.wav")              # "Stop, stop, that's not what I asked for."

    @classmethod
    def tearDownClass(cls):
        for p in reversed(cls.patches):
            p.stop()

    def test_transcribe_pcm_heard_gives_the_words_and_whispers_numbers(self):
        heard = server.transcribe_pcm_heard(self.pcm)
        self.assertIsInstance(heard, server.Heard)
        self.assertIn("stop", heard.text.lower())
        self.assertTrue(math.isfinite(heard.logprob) and heard.logprob <= 0.0, f"logprob {heard.logprob}")
        self.assertTrue(0.0 <= heard.no_speech <= 1.0, f"no_speech {heard.no_speech}")
        self.assertAlmostEqual(heard.seconds, server.speech_seconds(self.pcm), places=3)
        self.assertGreater(heard.seconds, 1.0)

    def test_run_whisper_keeps_its_signature_and_returns_the_heard_text(self):
        audio = server.pcm_audio(self.pcm)
        kw = {"beam": 5, "hint": "", "sure": True}
        inspect.signature(server.run_whisper).bind(audio, **kw)       # callers' arguments still fit
        text = server.run_whisper(audio, **kw)
        self.assertIsInstance(text, str)
        self.assertEqual(text, server.run_whisper_heard(audio, **kw).text)


VFRAME = 640                                                # samples in one of the mic loops' 40 ms frames


def level(rms_wanted):
    """One 40 ms frame whose level is `rms_wanted` (full scale 1.0): a square wave, so its rms is exactly its height."""
    a = round(rms_wanted * 32768)
    return pcm([a if i % 2 else -a for i in range(VFRAME)])


def feed(v, fr, times, soft=1.0, hold=False):
    out = None
    for _ in range(times):
        out = v.frame(fr, soft, hold)
    return out


QUIET, ROOM, LOUD = 0.002, 0.02, 0.1


@unittest.skipIf(hearing is None, f"hearing.py doesn't import here: {IMPORT_ERR}")
class VoicingTest(unittest.TestCase):
    """Voicing hears, frame by frame, whether someone is talking: the frame's level, the room's noise level (the quiet
    end, 20th percentile, of the last ~3 s), the threshold a voice must clear (never under `low`, else `over` times the
    room), and how many recent frames cleared it, counted up to 4 and back down to 0."""

    def test_a_frame_gives_back_its_level_the_room_the_threshold_and_the_count(self):
        out = hearing.Voicing(0.012, 3.0).frame(level(QUIET), 1.0)
        self.assertEqual(len(out), 4)
        self.assertIsInstance(out[3], int)

    def test_the_level_is_the_frames_rms_scaled_by_soft(self):
        v = hearing.Voicing(0.012, 3.0)
        self.assertAlmostEqual(v.frame(level(LOUD), 1.0)[0], LOUD, places=4)
        self.assertAlmostEqual(hearing.Voicing(0.012, 3.0).frame(level(LOUD), 2.5)[0], LOUD * 2.5, places=4)
        self.assertEqual(hearing.Voicing(0.012, 3.0).frame(pcm([0] * VFRAME), 1.0)[0], 0.0)

    def test_in_a_silent_room_the_threshold_is_low(self):
        for low, over in ((0.012, 3.0), (0.015, 3.2)):
            _rms, floor, thr, _n = feed(hearing.Voicing(low, over), level(0.0), 30)
            self.assertEqual(floor, 0.0)
            self.assertAlmostEqual(thr, low)

    def test_in_a_noisy_room_the_threshold_is_over_times_the_room(self):
        _rms, floor, thr, _n = feed(hearing.Voicing(0.012, 3.0), level(ROOM), 75)
        self.assertAlmostEqual(floor, ROOM, places=4)
        self.assertAlmostEqual(thr, ROOM * 3.0, places=4)
        _rms, floor, thr, _n = feed(hearing.Voicing(0.015, 3.2), level(ROOM), 75)
        self.assertAlmostEqual(thr, ROOM * 3.2, places=4)

    def test_pauses_that_fill_a_fifth_of_the_last_three_seconds_keep_the_room_quiet(self):
        v = hearing.Voicing(0.012, 3.0)
        feed(v, level(QUIET), 20)
        _rms, floor, _thr, _n = feed(v, level(ROOM), 55)
        self.assertAlmostEqual(floor, QUIET, places=4)

    def test_pauses_under_a_fifth_of_the_last_three_seconds_do_not(self):
        v = hearing.Voicing(0.012, 3.0)
        feed(v, level(QUIET), 10)
        _rms, floor, _thr, _n = feed(v, level(ROOM), 65)
        self.assertAlmostEqual(floor, ROOM, places=4)

    def test_a_steady_noise_lifts_the_room_within_three_seconds(self):
        v = hearing.Voicing(0.012, 3.0)
        feed(v, level(QUIET), 200)
        _rms, floor, thr, _n = feed(v, level(ROOM), 75)            # 75 frames of 40 ms: 3 s
        self.assertAlmostEqual(floor, ROOM, places=4)
        self.assertAlmostEqual(thr, ROOM * 3.0, places=4)

    def test_a_held_frame_leaves_the_room_alone(self):
        v = hearing.Voicing(0.012, 3.0)
        feed(v, level(QUIET), 75)
        _rms, floor, _thr, _n = feed(v, level(ROOM), 200, hold=True)
        self.assertAlmostEqual(floor, QUIET, places=4)

    def test_a_held_first_frame_still_sets_the_room(self):
        _rms, floor, _thr, _n = hearing.Voicing(0.012, 3.0).frame(level(ROOM), 1.0, hold=True)
        self.assertAlmostEqual(floor, ROOM, places=4)

    def test_the_count_climbs_to_four_over_the_threshold_and_falls_to_nought_under_it(self):
        v = hearing.Voicing(0.012, 3.0)
        feed(v, level(0.0), 10)
        up = [v.frame(level(LOUD), 1.0, hold=True)[3] for _ in range(6)]
        down = [v.frame(level(0.0), 1.0)[3] for _ in range(6)]
        self.assertEqual(up, [1, 2, 3, 4, 4, 4])
        self.assertEqual(down, [3, 2, 1, 0, 0, 0])

    def test_soft_decides_whether_a_frame_clears_the_threshold(self):
        v = hearing.Voicing(0.012, 3.0)
        feed(v, level(0.0), 10)
        self.assertEqual(v.frame(level(0.008), 1.0, hold=True)[3], 0)    # 0.008 is under 0.012
        self.assertEqual(v.frame(level(0.008), 2.0, hold=True)[3], 1)    # 0.016 is over it

    def test_two_detectors_keep_their_own_rooms(self):
        a, b = hearing.Voicing(0.012, 3.0), hearing.Voicing(0.012, 3.0)
        feed(a, level(ROOM), 75)
        _rms, floor, _thr, n = b.frame(level(0.0), 1.0)
        self.assertEqual((floor, n), (0.0, 0))


class Built(Exception):
    pass


class MicRead(Exception):
    pass


class DeafMic:
    def read(self, timeout):
        raise MicRead

    def close(self):
        pass


@unittest.skipIf(server is None, f"server.py doesn't import here: {SERVER_ERR}")
@unittest.skipIf(hearing is None, f"hearing.py doesn't import here: {IMPORT_ERR}")
class LoopsUseVoicingTest(unittest.TestCase):
    """Listen.run and Wake.session hear voice through hearing.Voicing, and server.py keeps no Floor."""

    def setUp(self):
        def spy(*a, **k):
            raise Built
        for target, name, value in ((hearing, "Voicing", spy),
                                    (server, "open_clean_mic", lambda: (DeafMic(), "deafmic", bytearray()))):
            p = mock.patch.object(target, name, value, create=True)
            p.start()
            self.addCleanup(p.stop)

    def test_server_keeps_no_floor_of_its_own(self):
        self.assertFalse(hasattr(server, "Floor"))

    def test_listen_builds_a_voicing_before_it_reads_the_mic(self):
        with self.assertRaises(Built):
            server.Listen("auto").run(lambda **k: None)

    def test_wake_session_builds_a_voicing_before_it_reads_the_mic(self):
        cut = server.Wake.cut
        self.addCleanup(setattr, server.Wake, "cut", cut)
        with mock.patch.object(server.Wake, "should_run", lambda *a: True):
            with self.assertRaises(Built):
                server.Wake.session()


if __name__ == "__main__":
    unittest.main()
