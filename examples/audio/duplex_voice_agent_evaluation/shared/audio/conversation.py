"""Optional live stereo monitoring and timeline-aligned conversation WAV artifacts."""

from __future__ import annotations

import threading
import time
import wave
from array import array
from pathlib import Path
from typing import Any

from shared.private_files import private_open, private_write_text


class TimestampedAudioBuffer:
    """Append provider PCM on its first-frame-relative sample clock."""

    def __init__(self, sample_rate: int) -> None:
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        self.sample_rate = sample_rate
        self.sample_count = 0
        self.gap_samples = 0
        self._origin_ms: int | None = None
        self._origin_sample = 0

    def append(self, pcm: bytes, *, start_ms: int | None = None) -> bytes:
        self.gap_samples = 0
        if len(pcm) % 2:
            raise ValueError("timestamped audio must contain complete PCM16 samples")
        if not pcm:
            return b""
        if start_ms is None:
            target_sample = self.sample_count
        else:
            if self._origin_ms is None:
                self._origin_ms = start_ms
                self._origin_sample = self.sample_count
            target_sample = max(
                0,
                self._origin_sample + (start_ms - self._origin_ms) * self.sample_rate // 1_000,
            )
        gap_samples = max(0, target_sample - self.sample_count)
        self.gap_samples = gap_samples
        overlapping_samples = min(len(pcm) // 2, max(0, self.sample_count - target_sample))
        novel_pcm = pcm[overlapping_samples * 2 :]
        self.sample_count += gap_samples + len(novel_pcm) // 2
        return bytes(gap_samples * 2) + novel_pcm


def _mix_into(track: array[int], start_sample: int, pcm: bytes) -> None:
    samples = array("h")
    samples.frombytes(pcm[: len(pcm) - len(pcm) % 2])
    if not samples:
        return
    required = start_sample + len(samples)
    if required > len(track):
        track.extend([0] * (required - len(track)))
    for index, sample in enumerate(samples, start_sample):
        track[index] = max(-32768, min(32767, track[index] + sample))


def _write_wav(path: Path, channels: int, sample_rate: int, frames: bytes) -> None:
    with private_open(path, "wb") as raw, wave.open(raw, "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(frames)


class ConversationRecorder:
    """Collect user and assistant PCM on the shared millisecond timeline."""

    def __init__(self, sample_rate: int) -> None:
        self.sample_rate = sample_rate
        self.user = array("h")
        self.assistant = array("h")

    def add(self, role: str, start_ms: int, pcm: bytes, *, start_sample: int | None = None) -> None:
        if role not in {"user", "assistant"}:
            raise ValueError(f"unknown audio role: {role}")
        start_sample = max(0, start_ms * self.sample_rate // 1_000 if start_sample is None else start_sample)
        _mix_into(self.user if role == "user" else self.assistant, start_sample, pcm)

    def save(self, path: Path, transcript: str) -> tuple[Path, Path]:
        frames = max(len(self.user), len(self.assistant))
        user = array("h", self.user)
        assistant = array("h", self.assistant)
        user.extend([0] * (frames - len(user)))
        assistant.extend([0] * (frames - len(assistant)))
        stereo = array("h")
        for left, right in zip(user, assistant, strict=True):
            stereo.extend((left, right))
        _write_wav(path, 2, self.sample_rate, stereo.tobytes())
        transcript_path = path.with_suffix(".transcript.txt")
        private_write_text(transcript_path, transcript.rstrip() + "\n", encoding="utf-8")
        return path, transcript_path


class LiveMonitor:
    """Play both conversation roles in stereo or mix them for mono-only devices."""

    def __init__(self, sample_rate: int, block_ms: int = 40) -> None:
        self.sample_rate = sample_rate
        self.block_ms = block_ms
        self.output_channels = 2
        self._user = bytearray()
        self._assistant = bytearray()
        self._lock = threading.Lock()
        self._stream: Any = None
        self._origin_ms: int | None = None
        self._origin_sample = 0
        self._played_samples = 0
        self._source_end_samples: dict[str, int] = {}
        self._playback_offsets: dict[str, int] = {}

    def start(self) -> None:
        try:
            import sounddevice as sd
        except ImportError as exc:
            raise RuntimeError(
                "Live playback requires the playback extra: run `uv sync --extra playback` "
                "in a source checkout or install `gpt-live-evals[playback]`."
            ) from exc

        blocksize = max(1, self.sample_rate * self.block_ms // 1_000)
        try:
            output_device = sd.query_devices(kind="output")
            self.output_channels = min(2, int(output_device["max_output_channels"]))
            if self.output_channels < 1:
                raise ValueError("the default audio device has no output channels")
            self._stream = sd.RawOutputStream(
                samplerate=self.sample_rate,
                channels=self.output_channels,
                dtype="int16",
                blocksize=blocksize,
                callback=self._callback,
            )
            self._stream.start()
        except Exception as exc:
            raise RuntimeError(f"could not start live audio playback: {exc}") from exc

    def push(self, role: str, pcm: bytes, *, start_ms: int | None = None) -> None:
        if role not in {"user", "assistant"}:
            raise ValueError(f"unknown audio role: {role}")
        if len(pcm) % 2:
            raise ValueError("live monitoring requires complete PCM16 samples")
        with self._lock:
            channel = self._user if role == "user" else self._assistant
            if start_ms is not None:
                if self._origin_ms is None:
                    self._origin_ms = start_ms
                    self._origin_sample = self._played_samples
                source_sample = max(
                    0,
                    self._origin_sample + (start_ms - self._origin_ms) * self.sample_rate // 1_000,
                )
                previous_source_end = self._source_end_samples.get(role)
                if previous_source_end is not None and source_sample < previous_source_end:
                    overlapping_samples = min(len(pcm) // 2, previous_source_end - source_sample)
                    pcm = pcm[overlapping_samples * 2 :]
                    source_sample += overlapping_samples
                if not pcm:
                    return

                playback_offset = self._playback_offsets.get(role, 0)
                target_sample = source_sample + playback_offset
                if target_sample < self._played_samples:
                    playback_offset += self._played_samples - target_sample
                    target_sample = self._played_samples
                queued_end_sample = self._played_samples + len(channel) // 2
                if target_sample < queued_end_sample:
                    playback_offset += queued_end_sample - target_sample
                    target_sample = queued_end_sample
                if target_sample > queued_end_sample:
                    channel.extend(bytes((target_sample - queued_end_sample) * 2))
                self._playback_offsets[role] = playback_offset
                self._source_end_samples[role] = source_sample + len(pcm) // 2
            channel.extend(pcm)

    @property
    def pending_ms(self) -> float:
        with self._lock:
            pending_bytes = max(len(self._user), len(self._assistant))
        return pending_bytes * 1_000 / (self.sample_rate * 2)

    def wait_until_drained(self, timeout_s: float) -> bool:
        deadline = time.monotonic() + timeout_s
        while self.pending_ms > 0 and time.monotonic() < deadline:
            time.sleep(min(self.block_ms / 1_000, 0.05))
        return self.pending_ms == 0

    def _callback(self, outdata: Any, frames: int, _time: Any, _status: Any) -> None:
        required = frames * 2
        with self._lock:
            user = bytes(self._user[:required])
            assistant = bytes(self._assistant[:required])
            del self._user[:required]
            del self._assistant[:required]
            self._played_samples += frames
        user += bytes(required - len(user))
        assistant += bytes(required - len(assistant))
        left = array("h")
        right = array("h")
        left.frombytes(user)
        right.frombytes(assistant)
        if self.output_channels == 1:
            mono = array("h")
            for user_sample, assistant_sample in zip(left, right, strict=True):
                mono.append(max(-32768, min(32767, user_sample + assistant_sample)))
            outdata[:] = mono.tobytes()
            return
        stereo = array("h")
        for user_sample, assistant_sample in zip(left, right, strict=True):
            stereo.extend((user_sample, assistant_sample))
        outdata[:] = stereo.tobytes()

    def close(self) -> None:
        if self._stream is None:
            return
        self._stream.stop()
        self._stream.close()
        self._stream = None
