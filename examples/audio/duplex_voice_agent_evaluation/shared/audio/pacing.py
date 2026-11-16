"""Absolute-deadline packet pacing shared by single- and multi-turn audio."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field


@dataclass(slots=True)
class AudioPacer:
    """Maintain absolute packet deadlines without replaying stalled audio in bursts."""

    chunk_ms: int
    deadline: float = field(init=False)
    late_chunk_count: int = field(default=0, init=False)
    max_lag_ms: float = field(default=0.0, init=False)
    _loop: asyncio.AbstractEventLoop = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if self.chunk_ms <= 0:
            raise ValueError("Audio pacing requires a positive chunk duration")
        self._loop = asyncio.get_running_loop()
        self.deadline = self._loop.time()

    def next_delay(self) -> tuple[float, float | None]:
        """Deduct send time, or reset cadence instead of flushing overdue packets."""
        interval = self.chunk_ms / 1_000
        self.deadline += interval
        now = self._loop.time()
        delay = self.deadline - now
        minimum_delay = interval * 0.75
        if delay >= minimum_delay:
            return delay, None
        if delay > 0:
            self.deadline = now + minimum_delay
            return minimum_delay, None
        lag_ms = round(-delay * 1_000, 3)
        self.late_chunk_count += 1
        self.max_lag_ms = max(self.max_lag_ms, lag_ms)
        self.deadline = now + interval
        return interval, lag_ms
