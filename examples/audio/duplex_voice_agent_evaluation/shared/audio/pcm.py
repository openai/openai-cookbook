"""Deterministic PCM16 audio utilities and a continuously drained speech queue."""

from __future__ import annotations

import base64
import math
import wave
from array import array
from collections import deque
from pathlib import Path
from typing import Any

from shared.audio.effects import AcousticEvent, AudioRealism, AudioRealismProcessor
from shared.private_files import private_open
from shared.scenarios import AudioCondition


def decode_audio(event: dict[str, Any]) -> bytes:
    """Decode one provider-neutral output_audio.delta payload."""
    encoded = event.get("delta")
    if event.get("type") != "session.output_audio.delta" or not isinstance(encoded, str):
        return b""
    try:
        return base64.b64decode(encoded, validate=True)
    except ValueError:
        return b""


def rms_pcm16(pcm: bytes) -> float:
    if not pcm:
        return 0.0
    samples = array("h")
    samples.frombytes(pcm[: len(pcm) - len(pcm) % 2])
    if not samples:
        return 0.0
    return math.sqrt(sum(value * value for value in samples) / len(samples))


def speech_intervals_pcm16(
    pcm: bytes,
    start_ms: int,
    sample_rate: int,
    threshold: float,
    *,
    frame_ms: int = 20,
) -> list[tuple[int, int]]:
    """Locate speech on the actual PCM clock instead of treating a whole tick as speech."""
    if sample_rate <= 0 or frame_ms <= 0:
        raise ValueError("sample_rate and frame_ms must be positive")
    frame_bytes = max(2, sample_rate * frame_ms // 1_000 * 2)
    frame_bytes -= frame_bytes % 2
    valid_bytes = len(pcm) - len(pcm) % 2
    intervals: list[tuple[int, int]] = []
    for offset in range(0, valid_bytes, frame_bytes):
        frame = pcm[offset : min(offset + frame_bytes, valid_bytes)]
        if rms_pcm16(frame) < threshold:
            continue
        frame_start_ms = start_ms + offset * 1_000 // (sample_rate * 2)
        frame_end_ms = start_ms + (offset + len(frame)) * 1_000 // (sample_rate * 2)
        if frame_end_ms <= frame_start_ms:
            continue
        if intervals and intervals[-1][1] == frame_start_ms:
            intervals[-1] = (intervals[-1][0], frame_end_ms)
        else:
            intervals.append((frame_start_ms, frame_end_ms))
    return intervals


def chunk_pcm(pcm: bytes, chunk_bytes: int) -> list[bytes]:
    if chunk_bytes <= 0 or chunk_bytes % 2:
        raise ValueError("chunk_bytes must be a positive, even integer")
    chunks = [pcm[i : i + chunk_bytes] for i in range(0, len(pcm), chunk_bytes)]
    if chunks and len(chunks[-1]) < chunk_bytes:
        chunks[-1] += bytes(chunk_bytes - len(chunks[-1]))
    return chunks


def condition_pcm(
    pcm: bytes,
    condition: str,
    seed: int,
    *,
    realism: AudioRealism | None = None,
) -> bytes:
    """Mix a reproducible ambience bed into one PCM tick."""
    if not pcm:
        return pcm
    if realism is None and condition == "clean":
        return pcm
    return AudioRealismProcessor(condition, seed, realism).process(pcm)


def tone_for_text(text: str, sample_rate: int = 24_000) -> bytes:
    """Offline speech surrogate with speech-like duration and measurable energy."""
    duration_s = min(4.0, max(0.28, len(text.split()) * 0.19))
    count = int(duration_s * sample_rate)
    values = array("h")
    for i in range(count):
        # Brief periodic gaps make energy-based activity tests more realistic.
        envelope = 0.18 if (i // (sample_rate // 12)) % 8 == 7 else 1.0
        values.append(int(2_300 * envelope * math.sin(2 * math.pi * 180 * i / sample_rate)))
    return values.tobytes()


class AudioQueue:
    def __init__(
        self,
        sample_rate: int,
        tick_ms: int,
        condition: AudioCondition,
        seed: int,
        *,
        realism: AudioRealism | None = None,
    ) -> None:
        self.chunk_bytes = sample_rate * tick_ms // 1_000 * 2
        self.condition = condition
        self.seed = seed
        self._realism_processor = AudioRealismProcessor(condition, seed, realism)
        self._chunks: deque[bytes] = deque()
        self._pending = bytearray()
        self._ticks = 0
        self.last_source_pcm = bytes(self.chunk_bytes)
        self.last_packet_lost = False
        self.last_acoustic_events: list[AcousticEvent] = []

    @property
    def queued_chunks(self) -> int:
        return len(self._chunks)

    @property
    def realism_metadata(self) -> dict[str, Any]:
        """Report configured effects and observed events with explicit provenance."""
        return self._realism_processor.metadata

    def enqueue(self, pcm: bytes) -> int:
        return self.append(pcm) + self.finish()

    def append(self, pcm: bytes) -> int:
        """Queue complete audio ticks while retaining an incomplete streamed tail."""
        self._pending.extend(pcm)
        count = 0
        while len(self._pending) >= self.chunk_bytes:
            chunk = bytes(self._pending[: self.chunk_bytes])
            del self._pending[: self.chunk_bytes]
            self._chunks.append(chunk)
            count += 1
        return count

    def finish(self) -> int:
        """Pad only the final tick, never an intermediate streaming fragment."""
        if not self._pending:
            return 0
        if len(self._pending) % 2:
            raise ValueError("PCM16 stream ended with an incomplete sample")
        chunk = bytes(self._pending)
        self._chunks.append(chunk + bytes(self.chunk_bytes - len(chunk)))
        self._pending.clear()
        return 1

    def discard_pending(self) -> None:
        self._pending.clear()

    def next_chunk(self) -> tuple[bytes, bool]:
        speaking = bool(self._chunks)
        speech = self._chunks.popleft() if speaking else bytes(self.chunk_bytes)
        # Mix ambience at send time, including pauses and final-tick padding, so a
        # noisy microphone remains continuously open while speech state stays explicit.
        pcm = self._realism_processor.process(speech, speech_active=speaking)
        self.last_source_pcm = self._realism_processor.last_source_pcm
        self.last_packet_lost = self._realism_processor.last_packet_lost
        self.last_acoustic_events = list(self._realism_processor.last_acoustic_events)
        self._ticks += 1
        return pcm, speaking and not self.last_packet_lost


def write_mono_wav(path: Path, pcm: bytes, sample_rate: int) -> Path:
    """Persist exact normalized PCM so a result remains independently auditable."""
    with private_open(path, "wb") as raw, wave.open(raw, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(pcm)
    return path


def read_mono_wav(path: Path, *, sample_rate_hz: int) -> bytes:
    """Return exact PCM16 from a validated, uncompressed single-channel WAV."""
    try:
        with wave.open(str(path), "rb") as recording:
            if recording.getnchannels() != 1:
                raise ValueError(f"Recorded WAV must be mono: {path}")
            if recording.getsampwidth() != 2:
                raise ValueError(f"Recorded WAV must use 16-bit PCM: {path}")
            if recording.getframerate() != sample_rate_hz:
                raise ValueError(f"Recorded WAV must use {sample_rate_hz} Hz PCM: {path}")
            if recording.getcomptype() != "NONE":
                raise ValueError(f"Recorded WAV must not be compressed: {path}")
            pcm = recording.readframes(recording.getnframes())
    except (OSError, wave.Error, EOFError) as exc:
        raise ValueError(f"Invalid recorded WAV: {path}") from exc
    if not pcm or len(pcm) % 2:
        raise ValueError(f"Recorded WAV must contain nonempty, complete PCM16 samples: {path}")
    return pcm
