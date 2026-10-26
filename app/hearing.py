"""What Void hears of himself: a record of what the speakers play, to tell his own voice from yours."""
import collections
import math
import sys
import threading

import numpy as np

try:                                                              # optional: without it the mic goes through as it is
    from livekit import rtc
except Exception as e:  # noqa: BLE001
    rtc, RTC_ERR = None, e
else:
    RTC_ERR = None

SR = 16000                                                        # the rate it keeps, which is what the mic runs at


class PlayRef:
    """What the speakers are playing, by monotonic time, at 16 kHz mono.

    A ring of the last KEEP seconds, by absolute sample number (time × 16000), so it never grows however long Void
    runs: the echo canceller only ever asks about the last moment or so, plus the ~0.8 s the player writes ahead.
    Samples in [lo, hi) are real; anything outside is silence. Other rates go through a windowed-sinc resampler
    (low-passed below both Nyquists, so a 22050/24000 voice doesn't alias into the reference); a chunk that follows
    straight on from the last one is resampled with the last one's tail in front, redoing the seam, so 20 ms chunks
    join without a click every 20 ms. One lock: `span` only copies under it, resampling happens outside it,
    so the mic threads never wait on maths."""
    KEEP = 10                                                     # seconds of the past kept
    H = 16                                                        # half the resampler's taps, in input samples
    lock = threading.Lock()
    moves = 0                                                     # how many times the speakers changed mid-play
    ring = np.zeros(KEEP * SR, np.int16)
    lo = hi = None                                                # the real samples' absolute numbers, [lo, hi)
    tail = None                                                   # (rate, end time, last 2H input samples)

    @classmethod
    def played(cls, pcm: bytes, rate: int, at: float) -> None:    # Speaker._write, each chunk, at its play time
        x = np.frombuffer(pcm, np.int16)
        if not len(x):
            return
        end = at + len(x) / rate
        t, start = cls.tail, at
        if t and t[0] == rate and abs(t[1] - at) < 1e-3:         # straight on from the last chunk: join the seam
            x, start = np.concatenate((t[2], x)), at - len(t[2]) / rate
            at -= cls.H / rate                                    # redo the last chunk's end, now we know what follows
        s = math.ceil(at * SR - 1e-3)
        e = math.ceil(end * SR - 1e-3)
        if rate == SR:
            y = x[round((s / SR - start) * SR):][:e - s]
        else:                                                     # (the sums happen outside the lock)
            y = cls._resample(x, rate, (np.arange(s, e) / SR - start) * rate)
        with cls.lock:
            if cls.tail is t:                                     # (cut meanwhile: it was stopped, so it never plays)
                cls._put(s, y)
                cls.tail = (rate, end, x[-2 * cls.H:].copy())

    @classmethod
    def cut(cls, at: float, moved: bool = False) -> None:         # Speaker.stop: nothing after `at` will play
        with cls.lock:                                            # (moved: other speakers carry on from there)
            cls.tail, cls.moves = None, cls.moves + moved
            if cls.hi is not None:
                cls.hi = min(cls.hi, max(cls.lo, math.ceil(at * SR - 1e-3)))

    @classmethod
    def span(cls, at: float, n: int) -> bytes:                    # n samples playing from `at`; silence where none
        out = np.zeros(n, np.int16)
        s = math.ceil(at * SR - 1e-3)
        with cls.lock:
            if cls.hi is not None:
                a, b = max(s, cls.lo), min(s + n, cls.hi)
                if a < b:
                    out[a - s:b - s] = cls.ring[np.arange(a, b) % len(cls.ring)]
        return out.tobytes()

    @classmethod
    def _put(cls, s, y):
        """Write y at absolute sample s (under the lock): silence over any gap since the last, drop what's too old."""
        N = len(cls.ring)
        if len(y) > N:
            s, y = s + len(y) - N, y[-N:]
        e = s + len(y)
        if cls.hi is None or s - cls.hi >= N:                     # first audio, or a gap longer than we keep
            cls.lo = cls.hi = s
        if s > cls.hi:
            cls.ring[np.arange(cls.hi, s) % N] = 0
        if s < cls.lo:                                            # older than anything we hold: only its newer part
            y, s = y[cls.lo - s:], cls.lo
        if s < e:
            cls.ring[np.arange(s, e) % N] = y
        cls.hi = max(cls.hi, e)
        cls.lo = max(cls.lo, cls.hi - N)

    @classmethod
    def _resample(cls, x, rate, pos):
        """x (at `rate`) at fractional input positions pos: Hann-windowed sinc, cut off at 0.45 × the lower rate,
        each row's weights summed to 1 (counting taps off the ends as silence) so a steady level stays put."""
        c = 0.45 * min(rate, SR) / rate                           # cutoff, in cycles per input sample
        i = np.floor(pos).astype(np.int64)[:, None] + np.arange(1 - cls.H, cls.H + 1)
        d = pos[:, None] - i
        w = np.sinc(2 * c * d) * (0.5 + 0.5 * np.cos(np.pi * np.clip(d / cls.H, -1, 1)))
        w /= w.sum(1, keepdims=True)
        ok = (i >= 0) & (i < len(x))
        y = (w * np.where(ok, x[np.clip(i, 0, len(x) - 1)], 0)).sum(1)
        return np.clip(np.rint(y), -32768, 32767).astype(np.int16)


class Linear:
    """A linear echo canceller beside the APM: a partitioned-block frequency-domain NLMS filter (overlap-save, 10 ms
    blocks, K of them: 100 ms of room) that learns the path from what PlayRef says played to the mic. Its residual
    (the mic less its estimate of his echo) is a subtraction, so it has your voice in it at full level even while he
    talks: what Canceller hands on while you talk over him, where the APM's suppressor turns your opening down.
    Two filters, as in Speex's MDF: the one in front (`w`, whose estimate is used) and one behind (`b`) that always
    learns. The front one takes the one behind's path when that has done clearly better for a while, and the one
    behind is put back to the front one's when it has done clearly worse (your voice dragged it off the room), so
    talking over him never spoils the path. Both are kept with the APM, warm across sessions; the reference they
    filter (`X`, the last K blocks' spectra) is each session's own, filled from PlayRef when the session opens.
    `erle`: how far under the mic its residual has lately been while he talked alone (dB), which says whether it
    knows the room; Canceller._pick keeps it."""
    K = 10                                                        # 10 ms blocks of room it models (100 ms: Speaker.LAT's
                                                                  # error, the room's reflections; fewer learn faster)
    moves = 0                                                     # PlayRef.moves when it last started re-learning
    RELEARN = 250                                                 # 10 ms frames of him it hears on new speakers
                                                                  # before it's trusted (a part-learnt path looks like you)
    MU = 0.5                                                      # the step behind, normalised by the reference's power

    def __init__(self, L: int):
        self.L, self.w, self.b = L, np.zeros((self.K, L + 1), complex), np.zeros((self.K, L + 1), complex)
        self.erle, self.sw, self.sb, self.wait = 0.0, 0.0, 0.0, 0

    def start(self, past: np.ndarray) -> None:
        """A session opens: `past`, the (K + 1) × L samples of reference that played up to its first frame."""
        L = self.L
        self.X = np.array([np.fft.rfft(past[len(past) - (k + 2) * L:len(past) - k * L]) for k in range(self.K)])
        self.last = past[-L:].astype(np.float64)
        self.P = None

    def step(self, ref: np.ndarray, mic: np.ndarray) -> tuple:
        """One block: `ref` (what played) and `mic` (what the mic caught then), L samples each; the filter behind
        learns from it. → (the mic less the front filter's estimate of his echo, that estimate)."""
        L, ref, d = self.L, ref.astype(np.float64), mic.astype(np.float64)
        self.X = np.roll(self.X, 1, 0)
        self.X[0] = np.fft.rfft(np.concatenate((self.last, ref)))
        self.last = ref
        y = np.fft.irfft((self.w * self.X).sum(0), 2 * L)[L:]
        yb = np.fft.irfft((self.b * self.X).sum(0), 2 * L)[L:]
        e, eb = d - y, d - yb
        self.sw, self.sb = 0.9 * self.sw + 0.1 * float(e @ e), 0.9 * self.sb + 0.1 * float(eb @ eb)
        if self.sb < 0.5 * self.sw:                               # behind is clearly better: it leads now
            self.w, self.sw = self.b.copy(), self.sb
        elif self.sb > 4 * self.sw:                               # behind went off the room: back to the front's
            self.b, self.sb, eb = self.w.copy(), self.sw, e
        p = (np.abs(self.X) ** 2).sum(0)
        self.P = p if self.P is None else 0.7 * self.P + 0.3 * p
        E = np.fft.rfft(np.concatenate((np.zeros(L), eb)))
        g = self.MU * np.conj(self.X) * E / (self.P + 1e4 * L)
        self.b += np.fft.rfft(np.fft.irfft(g, 2 * L, axis=1)[:, :L], 2 * L, axis=1)   # (kept causal: L taps a block)
        return e, y


class Canceller:
    """Takes Void's own voice out of the mic: livekit's WebRTC echo canceller, against what PlayRef says played.

    One Canceller per mic session, but one APM per process: the canceller's adaptive state (what it has learnt of the
    room) is kept in `Canceller.kept` (by the rtc module that built it) and shared by every session after the first, so a session opened while Void is
    already talking cancels him from its first frame instead of learning the room again. A mic or speaker device
    change means it re-learns as it goes. `Canceller.forget()` drops it, as a fresh process would start.
    `process` holds `Canceller.lock` throughout, so two sessions open at once never drive the shared APM together.
    A session's first audio is preceded by the PRIME × 10 ms of what played just before it, against a silent mic:
    without that the APM has none of the echo already in flight when the session opens (the room's delay and
    tail), and a session opened partway into his voice let most of its first 100 ms through.
    The APM takes exact 10 ms frames, so mic audio is gathered into them: whatever's left over (< 10 ms) waits for
    the next chunk, and the first time a chunk can't be answered in full the shortfall is made up once with silence
    in front, so the framing puts the output at most 159 samples behind (20 ms chunks never add any); the APM adds
    128 of its own, so measured end to end the output runs at most 287 samples (18 ms) behind the mic, with a first
    chunk of 159 samples, and 128 when the first chunk is whole frames. Each frame's reference is PlayRef's span
    for the same moment, fed just before the frame, so the stream delay is 0 and the canceller's own estimator only finds the room's.
    Echo cancelling and the high-pass filter (which AEC3 expects) are on; noise suppression and gain control
    are off, so your voice reaches whisper and the mic levelling as it was. Beside the APM runs a linear canceller
    of its own (Linear, kept with the APM): AEC3's suppressor turns your voice down for the first second or so of you
    talking over him (by 6 to 20 dB: "stop" lost its "stop"), so while you do, what goes out is the linear stage's
    residual instead, which has your voice whole and his echo some 20 dB down (_pick); the rest of the time it is the
    APM's. Off, or without livekit, it hands the
    mic back untouched; `available` says which, `on` whether echo_cancel asked for it, and `why` why not (said
    once per process)."""
    F = SR // 100                                                 # the APM's 10 ms frame, in samples
    said = set()
    PRIME = 10                                                    # 10 ms frames of what played fed in before a session
    kept = {}                                                     # the process's one APM, warm across sessions, by
                                                                  # the livekit rtc module that built it
    lock = threading.Lock()                                       # one session at a time drives the shared APM

    @classmethod
    def forget(cls) -> None:
        """Drop the kept APM, as a fresh process would start: the next Canceller learns the room from nothing."""
        cls.kept.clear()

    def __init__(self, on: bool = True):
        self.apm, why = None, "echo_cancel is off" if not on else f"livekit doesn't load ({RTC_ERR})" if rtc is None else ""
        if not why:
            try:
                if rtc not in Canceller.kept:
                    Canceller.kept[rtc] = (rtc.AudioProcessingModule(echo_cancellation=True, high_pass_filter=True),
                                           Linear(self.F))
                self.apm, self.linear = Canceller.kept[rtc]
            except Exception as e:  # noqa: BLE001
                why = f"livekit's echo canceller doesn't start ({e})"
        self.on, self.available, self.why = on, self.apm is not None, why
        if why and why not in Canceller.said:
            Canceller.said.add(why)
            print(f"[void] not cancelling his echo: {why}; the mic goes through as it is", file=sys.stderr)
        self.buf, self.out = b"", b""                             # mic not yet framed; cleaned audio not yet handed back
        self.fresh = True                                         # nothing of this session processed yet
        self.lin = np.zeros(self.LAG)                             # the linear stage's last LAG samples, not yet due
        self.near = self.run = 0                                  # frames you're still taken to be on for; how long
                                                                  # you have been

    LAG = 128                                                     # the APM's own delay, in samples
    TRUST = 12.0                                                  # dB the linear stage must have been taking out of him
    SPEECH = 3e4                                                  # mean square (int16) of a frame loud enough to be you
    ONSET = 6.0                                                   # dB of sudden drop that's you, not the room changing
    LOUD = 1e5                                                    # mean square of what played, when he's talking
    NEAR, MOST = 0.1, 0.25                                        # its residual over its echo estimate, and over the mic
    HOLD = 20                                                     # 10 ms frames you're still taken to be on for after
    LONGEST = 300                                                 # 10 ms frames of "you" before it stops trusting itself

    def _pick(self, o: np.ndarray, e: np.ndarray, y: np.ndarray, m: np.ndarray, r: np.ndarray) -> bytes:
        """One 10 ms frame out: the APM's `o`, or while you talk over him the linear stage's residual `e` (LAG later,
        to line up with the APM's). `y`: the linear stage's estimate of his echo; `m`: the mic; `r`: what played. You are taken to be
        talking when the linear stage knows the room (erle over TRUST) and its residual is loud enough to be speech, not
        far under its estimate of his echo (as it is when it's only his echo left) and most of what the mic caught.
        The switch is a crossfade across the frame. While he talks alone, `erle` follows how far under the mic the
        residual is, within a fifth of a second or so; a stretch of "you" longer than LONGEST is taken to be the room changed
        instead, and the linear stage isn't trusted again until it has learnt it."""
        P = lambda x: float(np.asarray(x, np.float64) @ np.asarray(x, np.float64)) / len(x) + 1.0   # noqa: E731
        pm, pe, py = P(m), P(e), P(y)
        lin = np.concatenate((self.lin, e))
        self.lin, late = lin[-self.LAG:], lin[:self.F]
        L, was = self.linear, self.near > 0
        if L.erle > self.TRUST and not L.wait and pe > self.SPEECH and pe > py * self.NEAR and pe > pm * self.MOST:
            self.near, self.run = self.HOLD, self.run + 1
            if self.run > self.LONGEST:
                L.erle, self.near = 0.0, 0
        elif self.near:
            self.near -= 1
        else:
            self.run = 0
        now = 10 * math.log10(pm / pe)                            # how far under the mic its residual is, this frame
        if not self.near and P(r) > self.LOUD and now > L.erle - self.ONSET:   # (he's talking: how well it takes him
            L.erle += 0.05 * (now - L.erle)                       # out; not a sudden drop, which is you starting)
            L.wait = max(0, L.wait - 1)
        w = np.full(self.F, float(self.near > 0)) if was == (self.near > 0) else np.linspace(was, self.near > 0, self.F)
        return np.clip(np.rint(w * late + (1 - w) * o), -32768, 32767).astype(np.int16).tobytes()

    def process(self, mic: bytes, at: float) -> bytes:            # 16 kHz s16le mono captured from `at`; same length back
        if self.apm is None:
            return mic
        with Canceller.lock:
            t = at - len(self.buf) / 2 / SR                           # when the waiting leftover was captured
            B, done = 2 * self.F, []
            if PlayRef.moves != Linear.moves:                         # other speakers: a new path, so it's trusted
                Linear.moves, self.near = PlayRef.moves, 0           # again only once it has learnt it
                self.linear.erle, self.linear.wait = 0.0, Linear.RELEARN
            if self.fresh:                                            # a session's first audio: what's already in flight
                self.fresh = False
                for j in range(self.PRIME, 0, -1):
                    self.apm.process_reverse_stream(rtc.AudioFrame(bytearray(PlayRef.span(t - j * self.F / SR, self.F)), SR, 1, self.F))
                    self.apm.set_stream_delay_ms(0)
                    self.apm.process_stream(rtc.AudioFrame(bytearray(2 * self.F), SR, 1, self.F))
                K = Linear.K + 1
                self.linear.start(np.frombuffer(PlayRef.span(t - K * self.F / SR, K * self.F), np.int16))
            self.buf += mic
            for i in range(0, len(self.buf) - B + 1, B):
                played = PlayRef.span(t + i / 2 / SR, self.F)
                ref = rtc.AudioFrame(bytearray(played), SR, 1, self.F)
                less, echo = self.linear.step(np.frombuffer(played, np.int16), np.frombuffer(self.buf[i:i + B], np.int16))
                frame = rtc.AudioFrame(bytearray(self.buf[i:i + B]), SR, 1, self.F)
                self.apm.process_reverse_stream(ref)
                self.apm.set_stream_delay_ms(0)
                self.apm.process_stream(frame)
                done.append(self._pick(np.frombuffer(frame.data.tobytes(), np.int16), less, echo,
                                       np.frombuffer(self.buf[i:i + B], np.int16), np.frombuffer(played, np.int16)))
            k = len(self.buf) // B * B
            self.buf, self.out = self.buf[k:], self.out + b"".join(done)
            if len(self.out) < len(mic):                              # (only ever once, and < 10 ms)
                self.out = bytes(len(mic) - len(self.out)) + self.out
            got, self.out = self.out[:len(mic)], self.out[len(mic):]
            return got


class Voicing:
    """Per-frame voice detection for a mic loop: the frame's level, the room's noise level (the quiet end, 20th
    percentile, of the last ~3 s), the threshold a voice must clear (`max(low, floor * over)`), and how many recent
    frames cleared it, counted up to 4 and back down to 0. Steady background (music, a fan) lifts the room within
    seconds, and the pauses between words still count as quiet. `hold` keeps a frame out of the room (you're talking),
    except the very first. Each caller keeps its own `low` and `over`."""

    def __init__(self, low: float, over: float):
        self.low, self.over = low, over
        self.h = collections.deque(maxlen=75)                     # 75 frames of 40 ms: 3 s
        self.floor = 0.0
        self.voiced = 0

    def frame(self, fr: bytes, soft: float, hold: bool = False) -> tuple[float, float, float, int]:
        """-> (rms, floor, threshold, voiced count 0-4)"""
        s = memoryview(fr).cast("h")
        rms = (sum(x * x for x in s) / len(s)) ** 0.5 / 32768.0 * soft if len(s) else 0.0
        if not hold or not self.h:
            self.h.append(rms)
            self.floor = sorted(self.h)[len(self.h) // 5]
        thr = max(self.low, self.floor * self.over)
        self.voiced = min(4, self.voiced + 1) if rms > thr else max(0, self.voiced - 1)
        return rms, self.floor, thr, self.voiced
