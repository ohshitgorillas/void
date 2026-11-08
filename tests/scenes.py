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

The follow-up gate is on, judging on Whisper's confidence, as it does in Void.
"""
import collections
import io
import json
import math
import re
import sys
import threading
import time as _time
import types
import wave
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

import numpy as np

import fakes

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
HEARD = 30.0              # hear=False: and someone talking comes through to the speech detector this loud (about -61 dBFS)
OPENING = 0.3             # hear=False: the first this-many seconds of your voice, in what Wake.session read,
OPENING_LOST_DB = 5.0     # turned down more than this under how you said them (opening_db), and Whisper loses
OPENING_WORDS = 2         # your first this-many words (heard as words of its own, or nothing). Real Whisper, warm canceller,
                          # each stop phrase alone 1, 2, 3 and 4 s into his voice: "Stop, stop", "Hold on" and "Shut up"
                          # came through 5.8-21 dB down and were lost at 2, 1 and 1 of the 4 moments (nothing at all,
                          # "Soft stuff"; "How old are you"; "Shings out"), every loss 5.8 dB down or more; "Hey Void"
                          # came through 3.2-4.1 dB down and was heard at all 4. (This loses every one Whisper lost, and
                          # more: Whisper heard the other 7, some as far as 20 dB down.)
OPENING_LAG = 0.04        # (the canceller hands your voice back up to this late)


SETTINGS = {              # every setting Wake.session, Wake.check and Speaker read from server.CFG, pinned for a scene
    "wake_word": True, "barge_in": True, "follow_up": 8,        # (Wake: always listening, his window after he talks)
    "mic_auto": False, "mic_device": "", "mic_cmd": "",         # (no mic levelling; the mic is faked)
    "echo_cancel": True, "voice_out": "auto",
    "language": "en", "whisper_beam": 5, "whisper_model": "base.en", "whisper_device": "cpu",   # (hear=True)
    "voice_gate": True,                                         # (follow-ups judged on Whisper's confidence)
}                         # (plus stt_hint and speak_max_chars: server's defaults, set in play)


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


def _clips() -> dict[str, dict]:
    """manifest.json's "clips": the one reader of them."""
    return json.loads((FIXTURES / "manifest.json").read_text("utf-8"))["clips"]


def _texts() -> dict[str, str]:
    """Each clip's "text"."""
    return {k: v.get("text", "") for k, v in _clips().items()}


def _words() -> dict[str, list[list[float]]]:
    """Each clip's "words" (one [start, end] per word of its text, in s from the clip's first sample), where it has them."""
    return {k: v["words"] for k, v in _clips().items() if "words" in v}


def _leads() -> dict[str, float]:
    """Each Void clip's "lead": the s that server.tidy_full trims off its front, so it is not played."""
    return {k: v["lead"] for k, v in _clips().items() if "lead" in v}


def _gate():
    _server()                                                     # (app/ on sys.path)
    import gate
    return gate


def void_stops(name: str) -> list[tuple[float, float]]:
    """Each stop phrase of Void's clip `name` as (start, end) in s after his voice starts coming out of the speakers:
    the clip's "words" less its "lead" (what the player drops), grouped by gate.stop_phrases. [] when the clip has no
    word times."""
    clip = _clips()[name]
    if "words" not in clip:
        return []
    gate, lead = _gate(), clip.get("lead", 0.0)
    timed = [gate.Word(w, s - lead, e - lead) for w, (s, e) in zip(clip["text"].split(), clip["words"])]
    return [(p.start, p.end) for p in gate.stop_phrases(timed)]


def _tokens(text):
    return re.findall(r"[\w']+", text.lower())


class Room:
    """Void's speakers and you sharing one mic: acoustic delay, reflections, loudness, an optional music bed.

    delay: seconds from the speakers to the mic. It also stands in for any error in Speaker.LAT (how long the
    speakers really take to get his voice out, against the latency Void assumes): either way his echo reaches the
    mic that much later than PlayRef says it played. On real hardware that comes to some 10 to 40 ms; the default,
    20 ms, sits inside it. reflections: (extra delay in seconds, gain) for each echo of the
    speakers off the walls. echo_db: Void's loudness at the mic, in dB relative to the clip as played. you_db: your
    loudness at the mic, the same way. music: a clip name played in the room that Void did not play (so no echo
    reference has it), at music_db.

    The defaults are a laptop on a desk: its own small speakers near its mic, their sound reaching it 20 ms later
    than Speaker.LAT says (loud at the mic, and with no bass: they roll off below about SPEAKER_CUT Hz), you about half a metre away, the desk and the walls
    sending back fainter, later copies of him, and the mic's own hiss at noise_db (dB below full scale, RMS)."""

    def __init__(self, delay=0.020, reflections=((0.007, 0.4), (0.019, 0.25), (0.041, 0.12)),
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
    echo (Void through the room), you, music; all of them silence before mic_from (seconds), when the mic session
    opened (0 unless play's mic_at put it later). Plus void_start/void_end and you_start/you_end in seconds (None when
    absent) and events: the BUS events published during the scene. switched: when the speakers changed mid-sentence
    (play's switch_at), in seconds on the scene's clock: the moment the old speakers fell silent and the new ones took
    over (None: no switch happened). opening_db: how far under how you said them the first OPENING seconds of your
    voice came through in clean (opening_db; None when you didn't speak). void_from: the scene second the first sample
    Void's player wrote comes out of the speakers (None when he didn't play): the clip's first sample after the trim."""

    def __init__(self):
        empty = np.zeros(0, np.int16)
        self.raw = self.clean = self.echo = self.you = self.music = empty
        self.void_start = self.void_end = self.you_start = self.you_end = self.opening_db = self.void_from = None
        self.events = []
        self.switched = None
        self.mic_from = 0.0


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
    plus you, the music and the mic's hiss, captured 20 ms at a time as the clock reaches each chunk's end. `lat` is
    the true output latency of the speakers a new player opens on (play's switch changes it); `players`, every fake
    player opened, in order; `first`, called once with the scene time (seconds) his voice first comes out. `void_from`:
    the scene sample at which the first sample his player wrote comes out of the speakers (set once; None until he
    plays), where the clip's own first sample, after the trim, sits; `switched`: the speakers changed mid-sentence."""

    def __init__(self, sim, room, n, lat, you, you_at, has_void, first=None):
        self.sim, self.room, self.lat, self.players, self.first = sim, room, lat, [], first
        pad = n + 4 * SR                                          # (the player writes up to ~1 s ahead of the clock)
        self.out = np.zeros(pad)                                  # what the speakers played, by scene sample
        self.h = room.impulse()
        self.played = []                                          # where any player put sound: scene sample numbers
        self.you_clip = None if you is None else you.astype(np.float64) * 10 ** (room.you_db / 20)
        self.you_at, self.has_void, self.you_from = you_at, has_void, None
        self.void_from, self.switched = None, False
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
            if not self.played and self.first:
                self.first((k + lo + int(loud[0])) / SR)
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
    """The OS player, at whatever rate it is opened at, on the speakers the scene has when it opens (their true
    latency, scene.lat, is its `lat`): plays what it's handed in order, each sample `lat` after it was written or
    straight after the one before, whichever is later; killed, whatever it still had queued past `lat` from now never
    plays; its speakers gone (gone()), whatever it had not yet played never plays and its next write is a broken pipe.
    What it plays reaches the room at the scene's 16 kHz, through the harness's own resampler: each unbroken run of
    sound is resampled as one, the newest stretch redone as more of it arrives."""

    def __init__(self, scene, rate):
        self.scene, self.rate, self.stdin, self.end, self.killed, self.got = scene, rate, self, None, False, bytearray()
        self.lat = scene.lat
        scene.players.append(self)
        self.runs = []                     # unbroken runs: [start (scene seconds), samples at rate, first out index, out]

    def write(self, b):
        if self.killed:
            raise BrokenPipeError("the player was killed")
        x = np.frombuffer(bytes(b), np.int16).astype(np.float64)
        now = self.scene.sim.now
        start = now + self.lat if self.end is None else max(self.end, now + self.lat)
        r, ts = self.rate, start - T0
        if self.runs and start == self.end:
            run = self.runs[-1]
            redo = math.ceil((self.end - T0 - (RS_HALF + 1) / r) * SR)   # (out samples whose taps reach the new ones)
            run[1] = np.concatenate((run[1], x))
        else:
            run = [ts, x, math.ceil((ts - RS_HALF / r) * SR), np.zeros(0)]
            self.runs.append(run)
            if self.scene.void_from is None:                  # (the start of the scene's first run: his clip's first sample)
                self.scene.void_from = round(ts * SR)
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
        self._silence(self.scene.sim.now + self.lat)

    def gone(self):
        """Its speakers went away (unplugged, power-cycled, another device picked): silent from now."""
        self._silence(self.scene.sim.now)

    def _silence(self, t):
        if self.killed:
            return
        self.killed = True
        cut = self.scene.index(t)
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
        self.scene, self.closed, self.name = scene, False, "scene mic"
        self.k = math.ceil(round((scene.sim.now - T0) * SR, 6) / CHUNK)   # (opened late: from the next 20 ms on)

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
    """BUS during a scene: keeps every event published, each with `scene_at`, the scene time it was published at (seconds
    from the scene's start)."""

    def __init__(self, sim):
        self.sim = sim
        self.got = []

    def pub(self, **ev):
        self.got.append(dict(ev, scene_at=self.sim.now - T0))

    def sub(self):
        import queue
        return queue.Queue()

    def unsub(self, q):
        pass


# ---------------------------------------------------------------- hear=False: stand-ins for the speech detector and Whisper

def _voiced(pcm):
    x = np.frombuffer(pcm, np.int16)[:len(pcm) // 2 // 480 * 480].astype(np.float64).reshape(-1, 480)
    return np.sqrt((x ** 2).mean(1)) > VOICED if len(x) else np.zeros(0, bool)


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


def opening_db(read, you, start):
    """How far under how you said them (dB, negative: turned down) the first OPENING seconds of your voice, from the
    first 30 ms frame of it loud enough to be talking, came through in `read` (int16 samples on the scene's clock, as
    Wake.session read them; `you`, your voice as it reached the mic, the same way; `start`, the sample you start
    at): the least-squares gain of your voice in what was read, at the lag up to OPENING_LAG that gives the most of it.
    None: no voice of yours, or not all of its opening read yet."""
    v = np.flatnonzero(_voiced(you[start:].tobytes()))
    if not len(v):
        return None
    s = start + int(v[0]) * 480
    n, lags = round(OPENING * SR), round(OPENING_LAG * SR)
    if len(read) < s + n + lags:
        return None
    u = you[s:s + n].astype(np.float64)
    g = max(float(read[s + k:s + k + n].astype(np.float64) @ u) for k in range(lags + 1)) / float(u @ u)
    return 20 * math.log10(g) if g > 0 else -math.inf


def _whisper(scene, clean, void_text, you_text, you_words=None, void_words=None, void_lead=0.0):
    """Stand-ins for Whisper and its speech detector, for fakes.ears: → (hear, speech, words). hear(pcm) makes out the words of whoever's voice the burst mostly sounds like.
    Finds where the burst sits on the scene's clock (it is a stretch of what Wake.session read), then, frame by frame,
    asks whose spectrum the burst's is most like there: your voice, Void's echo, or the music, as they reached the
    mic (spectra, not samples: the canceller's suppressor reshapes what it lets through, and hands it back a little
    late). Each frame votes by its loudness. His words if he wins, nothing if the music does. If you win, your words,
    less your first OPENING_WORDS when your opening came through more than OPENING_LOST_DB under how you said it
    (opening_db): real Whisper mishears a turned-down opening under his voice as words of its own, or as nothing.
    When he wins and his clip has word times (`void_words`, one [start, end] per word of `void_text`, from the clip's
    first sample; `void_lead`, what the player drops off its front), he is heard only as far as the burst holds him: his
    words that lie wholly inside it, as real Whisper hears only what the burst holds; a clip with none is heard whole.
    words(pcm, at) times what hear makes out, for transcribe_pcm_heard's `at` (the burst's first sample, on server's
    clock): the words of yours it keeps (`you_words`: your clip's word times for the words you say), or the words of his
    it hears, each wholly inside the burst, as a gate.Word at where it sits on the scene's clock. None when the music or
    no one wins, when the winner's clip has no word times, and for him after the speakers changed."""
    def yours(got):
        if scene.you_from is None:
            return you_text
        d = opening_db(np.frombuffer(got, np.int16), scene.you, scene.you_from)
        if d is not None and d < -OPENING_LOST_DB:
            return " ".join(you_text.split()[OPENING_WORDS:])
        return you_text

    def where(pcm):
        """→ what Wake.session has read so far, and where the burst `pcm` sits in it: [a, b) on the scene's clock."""
        got = b"".join(clean)
        e = len(got)
        for back in range(0, 4 * CHUNK * 2 + 1, 2):
            if len(got) - back >= len(pcm) and got[len(got) - back - len(pcm):len(got) - back] == pcm:
                e = len(got) - back
                break
        return got, max(0, e // 2 - len(pcm) // 2), e // 2

    def his(a, b):
        """His words wholly inside [a, b), each (word, start, end) in scene seconds as they reach the mic; None when
        his words are not timed here (no word times, he has not played, or the speakers changed)."""
        if not void_words or scene.void_from is None or scene.switched:
            return None
        t = scene.void_from / SR - void_lead + scene.room.delay
        return [(w, t + s, t + e) for w, (s, e) in zip(void_text.split(), void_words) if a / SR <= t + s and t + e <= b / SR]

    def speech(pcm):
        """Stand-in for server.speech_seconds on a burst Wake.session read: its 30 ms frames that are someone
        talking (you, his echo or the music loud enough to be, as they reached the mic) and that came through above
        HEARD. (Whisper's speech detector hears a voice turned down under his, as an absolute level does not.)"""
        got, a, b = where(pcm)
        n = (b - a) // 480 * 480
        if n <= 0:
            return 0.0
        rms = lambda x: np.sqrt((x[:n].astype(np.float64).reshape(-1, 480) ** 2).mean(1))   # noqa: E731
        talking = (rms(scene.you[a:b]) > VOICED) | (rms(scene.echo[a:b]) > VOICED) | (rms(scene.music[a:b]) > VOICED)
        return float((talking & (rms(np.frombuffer(got[2 * a:2 * b], np.int16)) > HEARD)).sum()) * 0.03

    def vote(pcm):
        """→ (who won the burst: "you", "void", "music" or None, the words heard, a, b: the burst on the scene's clock)."""
        if len(pcm) < SR * 2 * 0.3:
            return None, "", 0, 0
        got, a, b = where(pcm)
        c = _spectra(np.frombuffer(got[2 * a:2 * b], np.int16).astype(np.float64))
        votes = {}
        for who, part, text in (("you", scene.you, yours(got) if you_text else ""),
                                ("void", scene.echo, void_text),
                                ("music", scene.music, "")):
            m = _spectra(part[a:b].astype(np.float64))
            sim = (c * m).sum(1) / np.maximum(1e-9, np.linalg.norm(c, axis=1) * np.linalg.norm(m, axis=1))
            votes[who] = (sim, text)
        sims = np.array([v[0] for v in votes.values()])
        loud = (c ** 4).sum(1)                                    # (each frame's power, near enough)
        won = [float(loud[(sims.argmax(0) == i) & (sims.max(0) > 0)].sum()) for i in range(len(votes))]
        if max(won) <= 0:
            return None, "", a, b
        who = list(votes)[int(np.argmax(won))]
        text = votes[who][1]
        if who == "void" and his(a, b) is not None:
            text = " ".join(w for w, _, _ in his(a, b))
        return who, text, a, b

    def hear(pcm, **_kw):
        return vote(pcm)[1]

    def words(pcm, at):
        who, text, a, b = vote(pcm)
        if who == "you" and you_words and scene.you_from is not None:
            said = list(zip(you_text.split(), you_words))
            kept = said[len(said) - len(text.split()):] if text else []     # (the lost opening dropped, as yours drops it)
            timed = [(w, scene.you_from / SR + s, scene.you_from / SR + e) for w, (s, e) in kept]
            timed = [x for x in timed if a / SR <= x[1] and x[2] <= b / SR]
        elif who == "void" and his(a, b) is not None:
            timed = his(a, b)
        else:
            return None
        return tuple(_gate().Word(w, at + (s - a / SR), at + (e - a / SR)) for w, s, e in timed)

    return hear, speech, words


# ---------------------------------------------------------------- a scene

THEN = "And here is the rest of what I found."     # the second sentence of a line played with play(then=...)
PAGE_LEAD = 0.05          # page voice: the page schedules a sentence this long after it is handed over (its `when`)


def _page_player(sim, scene, server, text):
    """The page's player, for a scene (room harness beside FakePlayer, not a hearing double): what pump/enqueue in
    index.html do to the server for one sentence, through the server's own code for `/api/tts` (tts_reply) and
    `/api/speaking` (speaking_post). Handed the line it posts the owe and has the server make the audio; PAGE_LEAD
    later it posts the sentence's start (`left`: to its end plus the speakers' latency, with its text, played length
    and word times) and the trimmed audio comes out of the speakers `scene.lat` after that; when it has played it posts
    that he is quiet. The page's voice gives the echo canceller no reference, so nothing goes to PlayRef."""
    server.speaking_post({"owe": 1})
    reply = server.tts_reply(text)
    if reply is None:                                             # (nothing to say: it is no longer owed)
        server.speaking_post({"paid": 1})
        return
    audio, rate, _pause, words = reply
    with wave.open(io.BytesIO(audio)) as w:
        sr, pcm = w.getframerate(), w.readframes(w.getnframes())
    x = np.frombuffer(pcm, np.int16).astype(np.float64)
    r = sr * rate                                                 # (the player's rate: the clip's, sped by the voice's pitch)
    dur = len(x) / r
    sim.sleep(PAGE_LEAD)
    left = dur + scene.lat
    server.speaking_post({"on": True, "left": left, "paid": 1, "text": text, "dur": dur,
                          "words": [[a / rate, b / rate] for a, b in words] if words else None})
    ts = sim.now + scene.lat - T0                                 # (the sound reaches the room then)
    if scene.void_from is None:
        scene.void_from = round(ts * SR)                          # (the trimmed audio's first sample)
    k0, k1 = math.ceil((ts - RS_HALF / r) * SR), math.ceil((ts + (len(x) + RS_HALF) / r) * SR)
    scene.put(k0, resample(x, r, (np.arange(k0, k1) / SR - ts) * r))
    sim.sleep(left)
    server.speaking_post({"on": False})


def play(room, void=None, you=None, you_at=0.0, hear=False, seconds=None, switch_at=None, switch_lat=None,
         mic_at=None, you_only=None, then=None, page=False) -> Take:
    """Play a scene on a simulated clock: `void` (a clip name) goes through the real Speaker player path into PlayRef
    and out of the room's speakers; `you` (a clip name) speaks into the room at `you_at` seconds after Void's voice
    starts coming out of the speakers; `you_only`: (words, seconds) to say only the opening of your clip, its first
    `seconds`, whose words are `words` (None: all of it); the real Wake.session listens through open_clean_mic. hear=False stands in
    for speech detection and Whisper; hear=True runs the real ones. `seconds`: how long the scene runs (default:
    until everything has played, plus a little). `switch_at`: seconds after Void's voice starts coming out of the
    speakers at which the speakers change mid-sentence (the player he is writing to dies and a new one takes over, as
    Speaker._write handles it, e.g. a USB DAC power-cycled or headphones plugged in): from that moment whatever the
    old player had not yet played never plays, his next write to it fails as a broken pipe, and the real
    Speaker._write opens a new player through make_player, which the room then hears. None means no switch. The
    Take's `switched` says when it happened. `switch_lat`: the new speakers' true output latency, in seconds (default
    Speaker.LAT, the latency Void assumes; more stands in for speakers slower than he thinks). `mic_at`: seconds
    after his voice starts coming out of the speakers at which the mic session (Wake.session, through a fresh
    open_clean_mic session, with whatever canceller this run has kept) opens, as the always-on mic opens a new one
    when he starts talking; `then`: Void is handed a second sentence (the same voice again, as `void` says it) right
    after his first, and making it takes this many seconds from when he is handed his line (the pause between his
    sentences while the next is still being made; None: a one-sentence line);
    0 opens it as his voice starts, more while he is already talking. None (the default) opens it at scene time 0,
    before he is handed his line. The Take's `mic_from` says when it opened.

    `page`: Void speaks through the page's player instead of the native Speaker: a scene actor (_page_player) does to
    the server what the page does, through the server's own tts_reply and speaking_post, and no fake player is
    opened. It takes `void`, `you`, `you_at`, `you_only`, `hear` and `seconds`; any other argument raises ValueError.

    Scenes played one after another are one run of Void: whatever the app keeps across mic sessions in the process
    (a canceller kept warm) carries from one scene to the next. new_run() starts a fresh run."""
    if page:
        given = [k for k, v in (("switch_at", switch_at), ("switch_lat", switch_lat), ("mic_at", mic_at),
                                ("then", then)) if v is not None]
        if given or not void:
            raise ValueError("page voice takes void, you, you_at, you_only, hear and seconds"
                             + (f", not {', '.join(given)}" if given else ", and needs void"))
    server = _server()
    S, W, P = server.Speaker, server.Wake, server.hearing.PlayRef
    lat, texts = S.LAT, _texts()
    switch_lat = lat if switch_lat is None else switch_lat
    void_pcm = clip(void) if void else None
    you_pcm = clip(you) if you else None
    you_text = texts.get(you, "") if you else ""
    you_words = _words().get(you) if you else None
    if you_only is not None:
        you_text, n = you_only
        you_pcm = you_pcm[:round(n * SR)]
        k = len(you_text.split())                     # (its word times, when what you say is the clip's own opening)
        you_words = you_words[:k] if you_words and _tokens(you_text) == _tokens(texts[you])[:k] else None
    if seconds is None:
        ref = LEAD_IN + (PAGE_LEAD if page else 0.0) + lat if void else LEAD_IN
        ends = [LEAD_IN]
        if void:
            ends.append(ref + len(void_pcm) / SR)
            if then is not None:
                ends.append(max(ref + len(void_pcm) / SR, LEAD_IN + lat + then) + len(void_pcm) / SR + 0.5)
        if you:
            ends.append(ref + you_at + len(you_pcm) / SR)
        if room.music:
            ends.append(len(clip(room.music)) / SR)
        seconds = max(ends) + AFTER + (max(0.0, switch_lat - lat) if switch_at is not None else 0.0)
    n = math.ceil(seconds * SR)

    if mic_at is not None:
        if not void or mic_at < 0:
            raise ValueError("mic_at needs Void's voice, and opens the mic at or after its start")
    sim = Sim(T0)
    switch = types.SimpleNamespace(actor=None, at=None)
    wake = types.SimpleNamespace(actor=None, at=0.0)

    def first(t):                       # (his voice is out: the switch is due switch_at on, the mic session mic_at on)
        with sim.c:
            if switch.actor is not None:
                switch.actor.due = min(switch.actor.due, T0 + t + switch_at)
            if wake.actor is not None and mic_at is not None:
                wake.at = t + mic_at
                wake.actor.due = min(wake.actor.due, T0 + wake.at)

    def change():                                                 # (the speakers change: the old ones fall silent)
        sim.park(sim.current(), math.inf)
        switch.at = sim.now - T0
        scene.switched = True
        if scene.players:
            scene.players[-1].gone()
        scene.lat = switch_lat

    scene = Scene(sim, room, n, lat, you_pcm, you_at, bool(void),
                  first if switch_at is not None or mic_at is not None else None)
    events, clean = Events(sim), []
    real_open_clean_mic = server.open_clean_mic

    def open_mic():
        m = FakeMic(scene)
        return m, m.name, m.read(2.5)

    def open_clean_mic():
        m, name, first = real_open_clean_mic()
        clean.append(first)
        return RecordedMic(m, clean), name, first

    cfg = dict(SETTINGS, stt_hint=server.DEFAULTS["stt_hint"], speak_max_chars=server.DEFAULTS["speak_max_chars"])
    with ExitStack() as st:
        def patch(obj, name, value):
            st.enter_context(mock.patch.object(obj, name, value))
        patch(server, "time", SimTime(sim))
        patch(server, "CFG", cfg)
        patch(server, "BUS", events)
        patch(server, "SPOKEN", collections.deque(maxlen=200))
        patch(server, "PLAYED", collections.deque())            # (every scene's clock starts at T0: none hears another's stop phrases)
        patch(server, "make_player", lambda rate: FakePlayer(scene, rate))
        if page:
            patch(server, "tts_engine", lambda: "scene")             # (/api/tts has a voice: synth is the faked one)
        patch(server, "open_mic", open_mic)
        patch(server, "open_clean_mic", open_clean_mic)
        if void:                                                  # (his voice at Kokoro's rate, same duration)
            m = round(len(void_pcm) * VOICE_SR / SR)
            wav = _wav(resample(void_pcm.astype(np.float64), SR, np.arange(m) * SR / VOICE_SR), VOICE_SR)
            def synth(text):
                if then is not None and text == THEN:
                    server.time.sleep(then)                   # (the maker takes this long over the second sentence)
                return wav, 1.0
            patch(server, "synth", synth)
        if not hear:
            hear_text, hear_speech, hear_words = _whisper(scene, clean, texts.get(void, "") if void else "", you_text,
                                                          you_words, None if then is not None else _words().get(void),
                                                          _leads().get(void, 0.0))
            st.enter_context(fakes.ears(server, hear_text, hear_speech, hear_words))
            patch(server, "last_speech_end", last_speech_end)
        for k, v in (("cv", SimCondition(sim)), ("todo", []), ("ready", []), ("making", False), ("gen", 0),
                     ("epoch", 0), ("proc", None), ("prate", None), ("t0", 0.0), ("written", 0), ("threads", []),
                     ("filled", False), ("stats", {})):
            patch(S, k, v)
        for k, v in (("talked", []), ("owed", 0), ("seq", 0), ("told", 0.0), ("unsent", False), ("follow_on", False),
                     ("cut", None), ("asleep", False), ("thread", None), ("poke", threading.Event())):
            patch(W, k, v)
        for k, v in (("ring", np.zeros(len(P.ring), np.int16)), ("lo", None), ("hi", None), ("tail", None)):
            patch(P, k, v)

        try:
            wake.actor = sim.spawn("wake", W.session, T0 if mic_at is None else math.inf)
            if void and page:
                sim.spawn("void", lambda: _page_player(sim, scene, server, texts.get(void, "")), T0 + LEAD_IN)
            elif void:
                maker = sim.spawn("maker", S._maker, T0)
                player = sim.spawn("player", S._player_loop, T0)
                S.threads = [maker.thread, player.thread]          # (so say() finds them running and starts none)
                def hand_over():
                    S.say(texts.get(void, ""), 1)
                    if then is not None:
                        S.say(THEN, 2)
                sim.spawn("void", hand_over, T0 + LEAD_IN)
                if switch_at is not None:
                    switch.actor = sim.spawn("switch", change, T0)
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
    t.mic_from = scene.index(T0 + wake.at) / SR if mic_at is not None else 0.0
    a = math.ceil(round(t.mic_from * SR, 6) / CHUNK) * CHUNK      # (the first 20 ms the session read)
    t.mic_from = a / SR
    t.clean = np.concatenate((np.zeros(min(a, k), np.int16), np.frombuffer(b"".join(clean), np.int16)))[:k]
    t.events = events.got
    t.switched = switch.at
    if void:
        t.void_start = scene.void_start()
        t.void_from = None if scene.void_from is None else scene.void_from / SR
        loud = np.flatnonzero(np.abs(scene.out) >= 0.5)
        t.void_end = (loud[-1] + 1) / SR if len(loud) else None
    if scene.you_from is not None and scene.you_from < k:
        t.you_start = scene.you_from / SR
        t.you_end = min(k, scene.you_from + len(scene.you_clip)) / SR
        t.opening_db = opening_db(t.clean, t.you, scene.you_from)
    return t


# ---------------------------------------------------------------- a run of Void (what carries from scene to scene)

def _server():
    app = str(Path(__file__).resolve().parent.parent / "app")
    if app not in sys.path:
        sys.path.insert(0, app)
    import server
    return server


def new_run():
    """Start a fresh run of Void, as a fresh process would: `Canceller.forget()` drops the echo canceller the app
    keeps across mic sessions. Scenes and tests call this so that none depends on which ran before it."""
    _server().hearing.Canceller.forget()


def warm_up(room, void="void_question.wav"):
    """Let Void speak through the clean mic in `room` for the whole of `void` (7.7 s for the default), in this run,
    with the mic open from before he starts: what a later session in the same run inherits. Returns its Take."""
    return play(room, void=void)
