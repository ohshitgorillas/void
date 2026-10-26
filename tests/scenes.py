"""Scene replay harness: Void's speakers and you sharing one simulated room and one mic, on a simulated clock.

A scene plays committed fixture clips (tests/fixtures/scenes/, listed in manifest.json there) through the real
Speaker player path into PlayRef and out of the room's speakers (at 24 kHz, Kokoro's rate, as his real voice is), mixes in your voice and any music bed, and lets the
real Wake.session listen through open_clean_mic. What it produced comes back as a Take.

How it runs. Everything that waits in the scene waits on one simulated clock: server's `time` is swapped for one
whose monotonic() is the scene's clock and whose sleep() waits on it, Speaker.cv for a condition that waits on it, and
the mic hands over 20 ms each time the clock reaches the end of it. The scene's threads (Wake.session, Speaker's maker
and player, and the one who hands Void his line) take turns: only one runs at a time, and the clock moves on to the
earliest moment any of them waits for (ties go in that order). So a scene gives the same samples however busy the
machine is. Only the OS player, the OS mic and the synth are faked (and, with hear=False, the speech detector and
Whisper): the speakers play what the fake player was handed, when it would play it, and the room is made from that.
The scene's settings are pinned (SETTINGS), not read from your config file.
"""
import collections
import io
import json
import math
import sys
import threading
import time as _time
import types
import wave
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

import numpy as np

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "scenes"   # clips listed in manifest.json there

SR = 16000                # the scene's rate: the mic's, PlayRef's, and the clips'
VOICE_SR = 24000          # the rate the faked synth hands his voice over at (Kokoro's), played at rate 1.0
RS_HALF = 32              # the harness's resampler: half its taps, in input samples
RS_BETA = 8.0             # and its Kaiser window's shape
CHUNK = 320               # the mic hands over 20 ms at a time
T0 = 1000.0               # server's monotonic clock when the mic opens (scene time 0)
LEAD_IN = 0.5             # Void is handed his line this long after the mic opens
AFTER = 2.0               # by default a scene runs this long after everything has played (Wake ends a turn after 1.2 s quiet)
WALL = 120.0              # real seconds a scene may take before it is called stuck
SPEAKER_TAPS = 65         # the laptop speaker's high-pass (no bass from a small driver), as an FIR this long
SPEAKER_CUT = 250.0       # Hz, roughly where that speaker stops making sound
VOICED = 300.0            # hear=False: a 30 ms frame this loud (int16 RMS, about -41 dBFS) counts as someone talking


SETTINGS = {              # every setting Wake.session, Wake.check and Speaker read from server.CFG, pinned for a scene
    "wake_word": True, "barge_in": True, "follow_up": 8,        # (Wake: always listening, his window after he talks)
    "mic_auto": False, "mic_device": "", "mic_cmd": "",         # (no mic levelling; the mic is faked)
    "echo_cancel": True, "voice_out": "auto",
    "language": "en", "whisper_beam": 5, "whisper_model": "base.en", "whisper_device": "cpu",   # (hear=True)
}                         # (plus stt_hint: server's default, set in play)


def clip(name: str) -> np.ndarray:
    """A fixture WAV from FIXTURES, read as 16 kHz int16 mono samples."""
    with wave.open(str(FIXTURES / name)) as w:
        if (w.getframerate(), w.getnchannels(), w.getsampwidth()) != (SR, 1, 2):
            raise ValueError(f"{name}: not 16 kHz 16-bit mono")
        return np.frombuffer(w.readframes(w.getnframes()), np.int16).copy()


def resample(x, rate, pos):
    """The harness's own resampler (not PlayRef's): x (float samples at `rate`) read at fractional input positions
    `pos`, by a Kaiser-windowed sinc cut off just under half the lower of `rate` and SR; samples off either end of
    x are silence."""
    pos = np.asarray(pos, np.float64)
    if not len(pos) or not len(x):
        return np.zeros(len(pos))
    c = 0.475 * min(rate, SR) / rate                              # cutoff, in cycles per input sample
    i = np.floor(pos).astype(np.int64)[:, None] + np.arange(1 - RS_HALF, RS_HALF + 1)
    d = pos[:, None] - i
    w = 2 * c * np.sinc(2 * c * d) * np.i0(RS_BETA * np.sqrt(np.clip(1 - (d / RS_HALF) ** 2, 0, 1))) / np.i0(RS_BETA)
    ok = (i >= 0) & (i < len(x))
    return (w * np.where(ok, x[np.clip(i, 0, len(x) - 1)], 0.0)).sum(1)


def _wav(x, rate=SR):
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(np.clip(np.rint(x), -32768, 32767).astype(np.int16).tobytes())
    return b.getvalue()


def _texts():
    return {k: v.get("text", "") for k, v in json.loads((FIXTURES / "manifest.json").read_text("utf-8"))["clips"].items()}


class Room:
    """Void's speakers and you sharing one mic: acoustic delay, reflections, loudness, an optional music bed.

    delay: seconds from the speakers to the mic. It also stands in for any error in Speaker.LAT (how long the
    speakers really take to get his voice out, against the latency Void assumes): either way his echo reaches the
    mic that much later than PlayRef says it played. With 10 ms or more, the canceller takes out only about 6 to
    10 dB of his echo for roughly the first 2 s of his speech, while it finds the extra delay. reflections: (extra delay in seconds, gain) for each echo of the
    speakers off the walls. echo_db: Void's loudness at the mic, in dB relative to the clip as played. you_db: your
    loudness at the mic, the same way. music: a clip name played in the room that Void did not play (so no echo
    reference has it), at music_db.

    The defaults are a laptop on a desk: its own small speakers some 17 cm from its mic (0.5 ms; loud at the mic, and
    with no bass: they roll off below about SPEAKER_CUT Hz), you about half a metre away, the desk and the walls
    sending back fainter, later copies of him, and the mic's own hiss at noise_db (dB below full scale, RMS)."""

    def __init__(self, delay=0.0005, reflections=((0.007, 0.4), (0.019, 0.25), (0.041, 0.12)),
                 echo_db=-6.0, you_db=-12.0, music=None, music_db=-20.0, noise_db=-70.0):
        self.delay = delay
        self.reflections = reflections
        self.echo_db = echo_db
        self.you_db = you_db
        self.music = music
        self.music_db = music_db
        self.noise_db = noise_db

    def impulse(self):
        """The path from the speakers' output to the mic, as an FIR: the speaker's high-pass, put down once for the
        direct sound and once for each reflection, delayed and scaled."""
        n = np.arange(SPEAKER_TAPS) - SPEAKER_TAPS // 2
        lp = np.sinc(2 * SPEAKER_CUT / SR * n) * np.hanning(SPEAKER_TAPS)
        hp = -lp / lp.sum()
        hp[SPEAKER_TAPS // 2] += 1.0                              # (spectral inversion: what's left above the cut)
        taps = [(self.delay, 1.0)] + [(self.delay + d, g) for d, g in self.reflections]
        h = np.zeros(round(max(d for d, _ in taps) * SR) + SPEAKER_TAPS)
        for d, g in taps:
            a = round(d * SR) - SPEAKER_TAPS // 2                 # (the FIR's centre lands on the delay)
            lo = max(0, -a)
            h[a + lo:a + SPEAKER_TAPS] += g * hp[lo:]
        return h * 10 ** (self.echo_db / 20)


class Take:
    """What one scene produced, all 16 kHz int16 arrays on the scene's clock (0 = mic opened), same length:
    raw (what the mic picked up), clean (what Wake.session read from open_clean_mic), and the room's parts of raw:
    echo (Void through the room), you, music. Plus void_start/void_end and you_start/you_end in seconds (None when
    absent) and events: the BUS events published during the scene."""

    def __init__(self):
        empty = np.zeros(0, np.int16)
        self.raw = self.clean = self.echo = self.you = self.music = empty
        self.void_start = self.void_end = self.you_start = self.you_end = None
        self.events = []


# ---------------------------------------------------------------- the simulated clock and its turn-taking

class _Over(BaseException):
    """Raised in a scene thread that waits on the clock once the scene is over (BaseException: nothing catches it)."""


class Sim:
    """One clock and the threads that wait on it. A thread runs only when given the turn; when it waits (park) the
    turn goes back, and the next is the thread waiting for the earliest moment, the clock moving on to it."""

    def __init__(self, start):
        self.now = start
        self.c = threading.Condition()
        self.actors, self.mine, self.errors = [], {}, []
        self.turn, self.over = None, False

    def current(self):
        return self.mine.get(threading.get_ident())

    def spawn(self, name, fn, at):
        a = types.SimpleNamespace(name=name, order=len(self.actors), due=at, parked=False, done=False, notified=False)
        a.thread = threading.Thread(target=self._run, args=(a, fn), name=f"scene-{name}", daemon=True)
        self.actors.append(a)
        a.thread.start()
        with self.c:
            while not a.parked and not a.done:
                self.c.wait()
        return a

    def _run(self, a, fn):
        self.mine[threading.get_ident()] = a
        try:
            self.park(a, a.due)
            fn()
        except _Over:
            pass
        except BaseException as e:  # noqa: BLE001
            self.errors.append(e)
        finally:
            with self.c:
                a.done, a.parked = True, False
                if self.turn is a:
                    self.turn = None
                self.c.notify_all()

    def park(self, a, due):
        """Wait (as actor a) until the clock reaches `due` or something wakes a sooner."""
        with self.c:
            if self.over and self.turn is a:
                raise _Over
            a.due, a.parked = due, True
            if self.turn is a:
                self.turn = None
            self.c.notify_all()
            while self.turn is not a:
                self.c.wait()
            a.parked = False
            if self.over:
                raise _Over

    def wake(self, a):
        with self.c:
            a.due, a.notified = min(a.due, self.now), True

    def sleep(self, s):
        a = self.current()
        if a is None:                                             # (a thread that isn't part of the scene)
            return _time.sleep(s)
        self.park(a, self.now + max(0.0, s))

    def _settle(self, deadline):
        """Wait (holding c) until the thread that has the turn has given it back and every thread is parked."""
        while self.turn is not None or any(not a.parked and not a.done for a in self.actors):
            if not self.c.wait(timeout=1.0) and _time.monotonic() > deadline:
                raise RuntimeError(f"scene stuck at {self.now - T0:.3f} s: "
                                   + ", ".join(a.name for a in self.actors if not a.parked and not a.done)
                                   + " neither waiting on the clock nor done")

    def run(self, end):
        """Hand out turns until the next wait is past `end`; then wake every thread once more into _Over."""
        deadline = _time.monotonic() + WALL
        with self.c:
            try:
                while True:
                    self._settle(deadline)
                    live = [a for a in self.actors if not a.done]
                    if not live:
                        break
                    a = min(live, key=lambda a: (a.due, a.order))
                    if a.due > end:
                        break
                    self.now = max(self.now, a.due)
                    self.turn = a
                    self.c.notify_all()
            finally:
                self.over = True
                while any(not a.done for a in self.actors):
                    self._settle(deadline)
                    a = next((a for a in self.actors if not a.done), None)
                    if a is not None:
                        self.turn = a
                        self.c.notify_all()


class SimTime:
    """server's `time` during a scene: monotonic() is the scene's clock, sleep() waits on it, the rest is real."""

    def __init__(self, sim):
        self._sim = sim

    def monotonic(self):
        return self._sim.now

    def sleep(self, s):
        self._sim.sleep(s)

    def __getattr__(self, k):
        return getattr(_time, k)


class SimCondition:
    """Speaker.cv during a scene: waits on the scene's clock. (Only one scene thread runs at a time, so the lock part
    has nothing to guard.)"""

    def __init__(self, sim):
        self.sim, self.waiting = sim, []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def wait(self, timeout=None):
        a = self.sim.current()
        if a is None:
            raise RuntimeError("Speaker.cv waited on outside the scene")
        a.notified = False
        self.waiting.append(a)
        try:
            self.sim.park(a, math.inf if timeout is None else self.sim.now + max(0.0, timeout))
        finally:
            self.waiting.remove(a)
        return a.notified

    def notify_all(self):
        for a in self.waiting:
            self.sim.wake(a)

    notify = notify_all


# ---------------------------------------------------------------- the room, the OS player and the OS mic

class Scene:
    """The room as it sounds at the mic: what the speakers really played (from the fake players), through the room,
    plus you, the music and the mic's hiss, captured 20 ms at a time as the clock reaches each chunk's end."""

    def __init__(self, sim, room, n, lat, you, you_at, has_void):
        self.sim, self.room, self.lat = sim, room, lat
        pad = n + 4 * SR                                          # (the player writes up to ~1 s ahead of the clock)
        self.out = np.zeros(pad)                                  # what the speakers played, by scene sample
        self.h = room.impulse()
        self.played = []                                          # where any player put sound: scene sample numbers
        self.you_clip = None if you is None else clip(you).astype(np.float64) * 10 ** (room.you_db / 20)
        self.you_at, self.has_void, self.you_from = you_at, has_void, None
        self.music_part = np.zeros(pad)
        if room.music:
            m = clip(room.music).astype(np.float64)[:pad] * 10 ** (room.music_db / 20)
            self.music_part[:len(m)] = m
        self.noise = np.random.default_rng(0).normal(0.0, 32768 * 10 ** (room.noise_db / 20), pad)
        self.raw, self.echo, self.you, self.music = (np.zeros(pad, np.int16) for _ in range(4))
        self.you_part = np.zeros(pad)
        self.n = 0                                                # samples captured so far

    def index(self, t):
        return round((t - T0) * SR)

    def put(self, k, y, old=()):
        """The speakers' output from scene sample k on becomes y, where it was `old` (what a player put there)."""
        y = np.asarray(y, np.float64)
        d = y.copy()
        d[:len(old)] -= old[:len(d)]
        lo, hi = max(0, -k), max(0, min(len(d), len(self.out) - k))
        if lo >= hi:
            return
        self.out[k + lo:k + hi] += d[lo:hi]
        loud = np.flatnonzero(np.abs(y[lo:hi]) >= 0.5)            # (loud enough to come out of the mic as a sample)
        if len(loud):
            self.played.append(k + lo + int(loud[0]))

    def void_start(self):
        return min(self.played) / SR if self.played else None

    def _place_you(self):
        if self.you_from is not None or self.you_clip is None:
            return
        ref = self.void_start() if self.has_void else LEAD_IN
        if ref is None:
            return
        a = round((ref + self.you_at) * SR)
        y = self.you_clip[:max(0, len(self.you_part) - a)]
        self.you_part[a:a + len(y)] = y
        self.you_from = a

    def capture(self, a, b):
        """The mic's samples [a, b): only ever asked once the clock has reached b, so all of it has happened."""
        self._place_you()
        L = len(self.h)
        src = self.out[max(0, a - L + 1):b]
        if a - L + 1 < 0:
            src = np.concatenate((np.zeros(L - 1 - a), src))
        echo = np.convolve(src, self.h, "valid")
        you, music = self.you_part[a:b], self.music_part[a:b]

        def i16(x):
            return np.clip(np.rint(x), -32768, 32767).astype(np.int16)
        self.raw[a:b] = i16(echo + you + music + self.noise[a:b])
        self.echo[a:b], self.you[a:b], self.music[a:b] = i16(echo), i16(you), i16(music)
        self.n = b
        return self.raw[a:b]


class FakePlayer:
    """The OS player, at whatever rate it is opened at: plays what it's handed in order, each sample `lat` after it
    was written or straight after the one before, whichever is later; killed, whatever it still had queued past `lat`
    from now never plays. What it plays reaches the room at the scene's 16 kHz, through the harness's own resampler:
    each unbroken run of sound is resampled as one, the newest stretch redone as more of it arrives."""

    def __init__(self, scene, rate):
        self.scene, self.rate, self.stdin, self.end, self.killed, self.got = scene, rate, self, None, False, bytearray()
        self.runs = []                     # unbroken runs: [start (scene seconds), samples at rate, first out index, out]

    def write(self, b):
        if self.killed:
            raise BrokenPipeError("the player was killed")
        x = np.frombuffer(bytes(b), np.int16).astype(np.float64)
        now = self.scene.sim.now
        start = now + self.scene.lat if self.end is None else max(self.end, now + self.scene.lat)
        r, ts = self.rate, start - T0
        if self.runs and start == self.end:
            run = self.runs[-1]
            redo = math.ceil((self.end - T0 - (RS_HALF + 1) / r) * SR)   # (out samples whose taps reach the new ones)
            run[1] = np.concatenate((run[1], x))
        else:
            run = [ts, x, math.ceil((ts - RS_HALF / r) * SR), np.zeros(0)]
            self.runs.append(run)
            redo = run[2]
        self.end = start + len(x) / r
        k0, k1 = max(run[2], redo), math.ceil((self.end - T0 + RS_HALF / r) * SR)
        y = resample(run[1], r, (np.arange(k0, k1) / SR - run[0]) * r)
        old = run[3][k0 - run[2]:]
        run[3] = np.concatenate((run[3][:k0 - run[2]], y))
        self.scene.put(k0, y, old)
        self.got += b

    def flush(self):
        pass

    def poll(self):
        return 0 if self.killed else None

    def kill(self):
        if self.killed:
            return
        self.killed = True
        cut = self.scene.index(self.scene.sim.now + self.scene.lat)
        for run in self.runs:
            k = max(cut, run[2])
            gone = run[3][k - run[2]:]
            if len(gone):
                self.scene.put(k, np.zeros(len(gone)), gone)
                run[3] = run[3][:k - run[2]]


class FakeMic:
    """The OS mic: read() waits on the scene's clock for the next 20 ms and hands it over; once the scene is over it
    ends (EOFError), as a recorder that stopped does."""

    def __init__(self, scene):
        self.scene, self.k, self.closed, self.name = scene, 0, False, "scene mic"

    def read(self, timeout):
        sim = self.scene.sim
        due = T0 + (self.k + 1) * CHUNK / SR
        try:
            if sim.now < due:
                sim.park(sim.current(), due)
            elif sim.over:
                raise _Over
        except _Over:
            raise EOFError from None
        a = self.k * CHUNK
        self.k += 1
        return self.scene.capture(a, a + CHUNK).tobytes()

    def close(self):
        self.closed = True

    def err(self):
        return ""


class RecordedMic:
    """What open_clean_mic handed back, wrapped so every read is kept: the Take's `clean`."""

    def __init__(self, mic, got):
        self.mic, self.got = mic, got

    def read(self, timeout):
        b = self.mic.read(timeout)
        self.got.append(b)
        return b

    def close(self):
        self.mic.close()

    def err(self):
        return self.mic.err()


class Events:
    """BUS during a scene: keeps every event published."""

    def __init__(self):
        self.got = []

    def pub(self, **ev):
        self.got.append(ev)

    def sub(self):
        import queue
        return queue.Queue()

    def unsub(self, q):
        pass


# ---------------------------------------------------------------- hear=False: stand-ins for the speech detector and Whisper

def _voiced(pcm):
    x = np.frombuffer(pcm, np.int16)[:len(pcm) // 2 // 480 * 480].astype(np.float64).reshape(-1, 480)
    return np.sqrt((x ** 2).mean(1)) > VOICED if len(x) else np.zeros(0, bool)


def speech_seconds(pcm):
    """Stand-in for server.speech_seconds: 30 ms frames loud enough to be someone talking."""
    return float(_voiced(pcm).sum()) * 0.03


def last_speech_end(pcm):
    """Stand-in for server.last_speech_end: the end of the last loud 30 ms frame, in seconds (None: nobody)."""
    v = np.flatnonzero(_voiced(pcm))
    return (v[-1] + 1) * 0.03 if len(v) else None


def _spectra(x):
    """Root-magnitude spectra of x, 32 ms Hann frames every 16 ms (one row per frame)."""
    n = (len(x) - 512) // 256 + 1
    if n <= 0:
        return np.zeros((0, 257))
    idx = np.arange(512)[None, :] + 256 * np.arange(n)[:, None]
    return np.sqrt(np.abs(np.fft.rfft(x[idx] * np.hanning(512), axis=1)))


def _whisper(scene, clean, texts, void, you):
    """Stand-in for server.transcribe_pcm: it makes out the words of whoever's voice the burst mostly sounds like.
    Finds where the burst sits on the scene's clock (it is a stretch of what Wake.session read), then, frame by frame,
    asks whose spectrum the burst's is most like there: your voice, Void's echo, or the music, as they reached the
    mic (spectra, not samples: the canceller's suppressor reshapes what it lets through, and hands it back a little
    late). Each frame votes by its loudness. Your words if you win, his if he does, else nothing."""
    def hear(pcm, **_kw):
        if len(pcm) < SR * 2 * 0.3:
            return ""
        got = b"".join(clean)
        e = len(got)
        for back in range(0, 4 * CHUNK * 2 + 1, 2):
            if len(got) - back >= len(pcm) and got[len(got) - back - len(pcm):len(got) - back] == pcm:
                e = len(got) - back
                break
        b, a = e // 2, max(0, e // 2 - len(pcm) // 2)
        c = _spectra(np.frombuffer(got[2 * a:2 * b], np.int16).astype(np.float64))
        votes = {}
        for who, part, text in (("you", scene.you, texts.get(you, "") if you else ""),
                                ("void", scene.echo, texts.get(void, "") if void else ""),
                                ("music", scene.music, "")):
            m = _spectra(part[a:b].astype(np.float64))
            sim = (c * m).sum(1) / np.maximum(1e-9, np.linalg.norm(c, axis=1) * np.linalg.norm(m, axis=1))
            votes[who] = (sim, text)
        sims = np.array([v[0] for v in votes.values()])
        loud = (c ** 4).sum(1)                                    # (each frame's power, near enough)
        won = [float(loud[(sims.argmax(0) == i) & (sims.max(0) > 0)].sum()) for i in range(len(votes))]
        texts_ = [v[1] for v in votes.values()]
        return texts_[int(np.argmax(won))] if max(won) > 0 else ""
    return hear


# ---------------------------------------------------------------- a scene

def play(room, void=None, you=None, you_at=0.0, hear=False, seconds=None) -> Take:
    """Play a scene on a simulated clock: `void` (a clip name) goes through the real Speaker player path into PlayRef
    and out of the room's speakers; `you` (a clip name) speaks into the room at `you_at` seconds after Void's voice
    starts coming out of the speakers; the real Wake.session listens through open_clean_mic. hear=False stands in
    for speech detection and Whisper; hear=True runs the real ones. `seconds`: how long the scene runs (default:
    until everything has played, plus a little)."""
    app = str(Path(__file__).resolve().parent.parent / "app")
    if app not in sys.path:
        sys.path.insert(0, app)
    import server
    S, W, P = server.Speaker, server.Wake, server.hearing.PlayRef
    lat, texts = S.LAT, _texts()
    void_pcm = clip(void) if void else None
    if seconds is None:
        ref = LEAD_IN + lat if void else LEAD_IN
        ends = [LEAD_IN]
        if void:
            ends.append(ref + len(void_pcm) / SR)
        if you:
            ends.append(ref + you_at + len(clip(you)) / SR)
        if room.music:
            ends.append(len(clip(room.music)) / SR)
        seconds = max(ends) + AFTER
    n = math.ceil(seconds * SR)

    sim = Sim(T0)
    scene = Scene(sim, room, n, lat, you, you_at, bool(void))
    events, clean = Events(), []
    real_open_clean_mic = server.open_clean_mic

    def open_mic():
        m = FakeMic(scene)
        return m, m.name, m.read(2.5)

    def open_clean_mic():
        m, name, first = real_open_clean_mic()
        clean.append(first)
        return RecordedMic(m, clean), name, first

    cfg = dict(SETTINGS, stt_hint=server.DEFAULTS["stt_hint"])
    with ExitStack() as st:
        def patch(obj, name, value):
            st.enter_context(mock.patch.object(obj, name, value))
        patch(server, "time", SimTime(sim))
        patch(server, "CFG", cfg)
        patch(server, "BUS", events)
        patch(server, "SPOKEN", collections.deque(maxlen=200))
        patch(server, "make_player", lambda rate: FakePlayer(scene, rate))
        patch(server, "open_mic", open_mic)
        patch(server, "open_clean_mic", open_clean_mic)
        if void:                                                  # (his voice at Kokoro's rate, same duration)
            m = round(len(void_pcm) * VOICE_SR / SR)
            wav = _wav(resample(void_pcm.astype(np.float64), SR, np.arange(m) * SR / VOICE_SR), VOICE_SR)
            patch(server, "synth", lambda text: (wav, 1.0))
        if not hear:
            patch(server, "speech_seconds", speech_seconds)
            patch(server, "last_speech_end", last_speech_end)
            patch(server, "transcribe_pcm", _whisper(scene, clean, texts, void, you))
        for k, v in (("cv", SimCondition(sim)), ("todo", []), ("ready", []), ("making", False), ("gen", 0),
                     ("epoch", 0), ("proc", None), ("prate", None), ("t0", 0.0), ("written", 0), ("threads", []),
                     ("filled", False), ("stats", {})):
            patch(S, k, v)
        for k, v in (("speaking_until", 0.0), ("follow_from", 0.0), ("follow_until", 0.0), ("follow_on", False),
                     ("cut", None), ("asleep", False), ("thread", None), ("poke", threading.Event())):
            patch(W, k, v)
        for k, v in (("ring", np.zeros(len(P.ring), np.int16)), ("lo", None), ("hi", None), ("tail", None)):
            patch(P, k, v)

        try:
            sim.spawn("wake", W.session, T0)
            if void:
                maker = sim.spawn("maker", S._maker, T0)
                player = sim.spawn("player", S._player_loop, T0)
                S.threads = [maker.thread, player.thread]          # (so say() finds them running and starts none)
                sim.spawn("void", lambda: S.say(texts.get(void, ""), 1), T0 + LEAD_IN)
            sim.run(T0 + seconds)
        finally:
            sim.over = True
            for a in sim.actors:
                a.thread.join(timeout=10)
            alive = [a.name for a in sim.actors if a.thread.is_alive()]
        if alive:
            raise RuntimeError(f"scene threads still running: {', '.join(alive)}")
        if sim.errors:
            raise sim.errors[0]

    t = Take()
    k = scene.n
    t.raw, t.echo, t.you, t.music = (x[:k].copy() for x in (scene.raw, scene.echo, scene.you, scene.music))
    t.clean = np.frombuffer(b"".join(clean), np.int16).copy()
    t.events = events.got
    if void:
        t.void_start = scene.void_start()
        loud = np.flatnonzero(np.abs(scene.out) >= 0.5)
        t.void_end = (loud[-1] + 1) / SR if len(loud) else None
    if scene.you_from is not None and scene.you_from < k:
        t.you_start = scene.you_from / SR
        t.you_end = min(k, scene.you_from + len(scene.you_clip)) / SR
    return t
