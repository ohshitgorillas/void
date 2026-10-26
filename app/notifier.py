"""Ping batching: pings in, at most one turn out per quiet spell. No model call."""
import time


class PingBatch:                                  # pure: clock injected, no threads
    def __init__(self, quiet_s: float, hold_s: float, clock=time.monotonic):
        self._quiet_s = quiet_s
        self._hold_s = hold_s
        self._clock = clock
        self._lines: list[str] = []
        self._first = 0.0
        self._last = 0.0

    def add(self, line: str) -> None:
        now = self._clock()
        if not self._lines:
            self._first = now
        self._last = now
        self._lines.append(line)

    def due(self) -> list[str] | None:            # the batch once quiet_s passed since the last line, or hold_s since the first
        if not self._lines:
            return None
        now = self._clock()
        if now - self._last >= self._quiet_s or now - self._first >= self._hold_s:
            lines, self._lines = self._lines, []
            return lines
        return None


def digest(lines: list[str]) -> str:              # the batch as one message, one line per ping, in arrival order
    return "\n".join(" ".join(line.split()) for line in lines)
