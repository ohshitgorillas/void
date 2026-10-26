"""What Void hears of himself: a record of what the speakers play, to tell his own voice from yours."""
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
    def cut(cls, at: float) -> None:                              # Speaker.stop: nothing after `at` will play
        with cls.lock:
            cls.tail = None
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


class Canceller:
    """Takes Void's own voice out of the mic: livekit's WebRTC echo canceller, against what PlayRef says played.

    One per mic session (it keeps the canceller's adaptive state). The APM takes exact 10 ms frames, so mic audio
    is gathered into them: whatever's left over (< 10 ms) waits for the next chunk, and the first time a chunk can't
    be answered in full the shortfall is made up once with silence in front, so the output runs at most 159 samples
    behind from then on (20 ms chunks never add any). Each frame's reference is PlayRef's span for the same moment,
    fed just before the frame, so the stream delay is 0 and the canceller's own estimator only finds the room's.
    Echo cancelling and the high-pass filter (which AEC3 expects) are on; noise suppression and gain control
    are off, so your voice reaches whisper and the mic levelling as it was. Off, or without livekit, it hands the
    mic back untouched; `available` says which, `on` whether echo_cancel asked for it, and `why` why not (said
    once per process)."""
    F = SR // 100                                                 # the APM's 10 ms frame, in samples
    said = set()

    def __init__(self, on: bool = True):
        self.apm, why = None, "echo_cancel is off" if not on else f"livekit doesn't load ({RTC_ERR})" if rtc is None else ""
        if not why:
            try:
                self.apm = rtc.AudioProcessingModule(echo_cancellation=True, high_pass_filter=True)
            except Exception as e:  # noqa: BLE001
                why = f"livekit's echo canceller doesn't start ({e})"
        self.on, self.available, self.why = on, self.apm is not None, why
        if why and why not in Canceller.said:
            Canceller.said.add(why)
            print(f"[void] not cancelling his echo: {why}; the mic goes through as it is", file=sys.stderr)
        self.buf, self.out = b"", b""                             # mic not yet framed; cleaned audio not yet handed back

    def process(self, mic: bytes, at: float) -> bytes:            # 16 kHz s16le mono captured from `at`; same length back
        if self.apm is None:
            return mic
        t = at - len(self.buf) / 2 / SR                           # when the waiting leftover was captured
        self.buf += mic
        B, done = 2 * self.F, []
        for i in range(0, len(self.buf) - B + 1, B):
            ref = rtc.AudioFrame(bytearray(PlayRef.span(t + i / 2 / SR, self.F)), SR, 1, self.F)
            frame = rtc.AudioFrame(bytearray(self.buf[i:i + B]), SR, 1, self.F)
            self.apm.process_reverse_stream(ref)
            self.apm.set_stream_delay_ms(0)
            self.apm.process_stream(frame)
            done.append(frame.data.tobytes())
        k = len(self.buf) // B * B
        self.buf, self.out = self.buf[k:], self.out + b"".join(done)
        if len(self.out) < len(mic):                              # (only ever once, and < 10 ms)
            self.out = bytes(len(mic) - len(self.out)) + self.out
        got, self.out = self.out[:len(mic)], self.out[len(mic):]
        return got
