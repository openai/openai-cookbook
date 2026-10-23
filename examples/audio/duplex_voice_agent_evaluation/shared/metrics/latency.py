"""Shared wall-clock and actual-speech latency measurements."""

from __future__ import annotations

import time

from shared.audio.pcm import speech_intervals_pcm16


def elapsed_ms(started_at: float) -> float:
    """Measure elapsed milliseconds from the monotonic evaluation clock."""
    return round((time.monotonic() - started_at) * 1_000, 3)


def first_speech_offset_ms(
    pcm: bytes,
    *,
    start_ms: int,
    sample_rate_hz: int,
    frame_ms: int = 20,
    threshold: float = 220.0,
) -> float | None:
    """Locate actual audible speech rather than treating silent PCM as a response."""
    intervals = speech_intervals_pcm16(
        pcm,
        start_ms,
        sample_rate_hz,
        threshold,
        frame_ms=frame_ms,
    )
    return float(intervals[0][0]) if intervals else None
