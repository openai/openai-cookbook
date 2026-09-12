"""Deterministic, stateful microphone effects shared by voice-evaluation runners."""

from __future__ import annotations

import argparse
import math
import random
import wave
from array import array
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Final, get_args

from pydantic import BaseModel, ConfigDict, Field

from shared.paths import package_path
from shared.scenarios import AudioCondition

SAMPLE_RATE: Final = 24_000
TELEPHONE_SAMPLE_RATE: Final = 8_000
TELEPHONE_BAND_HZ: Final = (300, 3_400)
DEFAULT_NOISY_RMS: Final = 1_200.0

DEFAULT_BACKGROUND_SPEECH: Final = package_path("shared", "audio", "assets", "background_conversation.wav")
DEFAULT_BACKGROUND_GAIN: Final = 0.65
DEFAULT_REALISTIC_NOISE_RMS: Final = 500.0
DEFAULT_REALISTIC_BACKGROUND_GAIN: Final = 0.4
DEFAULT_REALISTIC_ECHO_DECAY: Final = 0.25
DEFAULT_REALISTIC_PACKET_LOSS_RATE: Final = 0.04
_PCM_MIN: Final = -32_768
_PCM_MAX: Final = 32_767
AUDIO_CONDITIONS: Final = get_args(AudioCondition)
AUDIO_REALISM_FIELDS: Final = (
    "noise_rms",
    "background_speech",
    "background_gain",
    "echo_delay_ms",
    "echo_decay",
    "packet_loss_rate",
    "packet_loss_burst",
    "cough_every_ms",
    "non_directed_every_ms",
)


class AudioRealism(BaseModel):
    """Optional validated overrides for a named, deterministic audio preset."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    noise_rms: float | None = Field(default=None, ge=0, le=_PCM_MAX)
    background_speech: Path | None = None
    background_gain: float | None = Field(default=None, ge=0, le=1)
    echo_delay_ms: int | None = Field(default=None, ge=0, le=60_000)
    echo_decay: float | None = Field(default=None, ge=0, le=1)
    packet_loss_rate: float | None = Field(default=None, ge=0, le=1)
    packet_loss_burst: int | None = Field(default=None, ge=1, le=1_000)
    cough_every_ms: int | None = Field(default=None, ge=1, le=3_600_000)
    non_directed_every_ms: int | None = Field(default=None, ge=1, le=3_600_000)


def add_audio_realism_arguments(
    parser: argparse.ArgumentParser,
    *,
    condition_default: AudioCondition | None = None,
) -> None:
    """Expose the same acoustic presets and effect overrides in every relevant CLI."""
    parser.add_argument(
        "--condition",
        choices=AUDIO_CONDITIONS,
        default=condition_default,
        help="Deterministic caller-audio realism preset.",
    )
    parser.add_argument("--noise-rms", type=float, help="Background-noise RMS in PCM16 sample units.")
    parser.add_argument("--background-speech", type=Path, help="Optional approved mono or stereo PCM16 WAV.")
    parser.add_argument("--background-gain", type=float, help="Gain applied to background speech.")
    parser.add_argument("--echo-delay-ms", type=int, help="Caller echo delay in milliseconds.")
    parser.add_argument("--echo-decay", type=float, help="Caller echo decay as a fraction of its source.")
    parser.add_argument("--packet-loss-rate", type=float, help="Probability of dropping each audio frame.")
    parser.add_argument("--packet-loss-burst", type=int, help="Number of consecutive frames dropped together.")
    parser.add_argument("--cough-every-ms", type=int, help="Interval between labeled synthetic coughs.")
    parser.add_argument(
        "--non-directed-every-ms",
        type=int,
        help="Interval between labeled non-directed acoustic distractions.",
    )


def audio_realism_from_args(args: argparse.Namespace) -> AudioRealism:
    """Validate optional deterministic acoustic overrides from a parsed CLI."""
    return AudioRealism(
        **{field: value for field in AUDIO_REALISM_FIELDS if (value := getattr(args, field, None)) is not None}
    )


@dataclass(frozen=True, slots=True)
class AcousticEvent:
    """One delivered, labeled distractor on the absolute caller-audio clock."""

    kind: str
    start_ms: int
    end_ms: int
    provenance: str
    origin_start_ms: int | None = None


def _clip(value: float | int) -> int:
    return max(_PCM_MIN, min(_PCM_MAX, round(value)))


def _g711_mulaw_round_trip(sample: int) -> int:
    """Apply an 8-bit G.711 mu-law encode/decode cycle without extra dependencies."""

    mask = 0x7F if sample < 0 else 0xFF
    biased = min(abs(sample), 32_635) + 0x84
    segment = min(7, max(0, biased.bit_length() - 8))
    encoded = ((segment << 4) | ((biased >> (segment + 3)) & 0x0F)) ^ mask
    decoded = (~encoded) & 0xFF
    expanded = ((decoded & 0x0F) << 3) + 0x84
    expanded <<= (decoded & 0x70) >> 4
    return 0x84 - expanded if decoded & 0x80 else expanded - 0x84


def _background_samples(path: Path) -> array[int]:
    """Read and linearly resample a local 16-bit mono or stereo WAV."""

    try:
        with wave.open(str(path), "rb") as source:
            channels = source.getnchannels()
            if channels not in {1, 2}:
                raise ValueError(f"background recording must have one or two channels: {path}")
            if source.getsampwidth() != 2:
                raise ValueError(f"background recording must be 16-bit PCM WAV: {path}")
            source_rate = source.getframerate()
            frames = source.readframes(source.getnframes())
    except (EOFError, OSError, wave.Error) as exc:
        raise ValueError(f"could not read background recording {path}: {exc}") from exc

    if source_rate <= 0:
        raise ValueError(f"background recording has an invalid sample rate: {path}")
    if not frames or len(frames) % (channels * 2):
        raise ValueError(f"background recording contains no complete audio frames: {path}")

    samples: array[int] = array("h")
    samples.frombytes(frames)
    if channels == 2:
        samples = array("h", ((samples[index] + samples[index + 1]) // 2 for index in range(0, len(samples), 2)))
    if source_rate != SAMPLE_RATE:
        count = max(1, round(len(samples) * SAMPLE_RATE / source_rate))
        resampled: array[int] = array("h")
        for index in range(count):
            position = index * source_rate / SAMPLE_RATE
            left = min(int(position), len(samples) - 1)
            right = min(left + 1, len(samples) - 1)
            fraction = position - left
            resampled.append(_clip(samples[left] + (samples[right] - samples[left]) * fraction))
        samples = resampled

    # Keep competing speech clearly audible without making it louder than the caller.
    peak = max((abs(value) for value in samples), default=0)
    if peak:
        samples = array("h", (_clip(value * 6_000 / peak) for value in samples))
    return samples


class AudioRealismProcessor:
    """Continuously condition PCM16 while keeping primary speech independently visible."""

    def __init__(self, condition: str, seed: int = 0, realism: AudioRealism | None = None) -> None:
        if condition not in AUDIO_CONDITIONS:
            raise ValueError(f"unknown audio condition: {condition}")
        self.condition = condition
        self.seed = seed
        self.realism = AudioRealism() if realism is None else AudioRealism.model_validate(realism)

        self._telephony = condition in {"telephony", "realistic"}
        self._noise_enabled = condition in {"noisy", "realistic"} or self.realism.noise_rms is not None
        self._noise_rms = (
            self.realism.noise_rms
            if self.realism.noise_rms is not None
            else DEFAULT_NOISY_RMS
            if condition == "noisy"
            else DEFAULT_REALISTIC_NOISE_RMS
            if condition == "realistic"
            else 0.0
        )

        self._background_enabled = (
            condition in {"background_speech", "realistic"}
            or self.realism.background_speech is not None
            or self.realism.background_gain is not None
        )
        self._background_gain = (
            self.realism.background_gain
            if self.realism.background_gain is not None
            else DEFAULT_BACKGROUND_GAIN
            if condition == "background_speech"
            else DEFAULT_REALISTIC_BACKGROUND_GAIN
            if condition == "realistic"
            else 0.1
        )
        self._background: array[int] | None = None
        self._background_reference: str | None = None
        if self._background_enabled:
            if self.realism.background_speech is not None:
                self._background = _background_samples(self.realism.background_speech)
                self._background_reference = str(self.realism.background_speech)
                self._background_provenance = self._background_reference
            elif DEFAULT_BACKGROUND_SPEECH.is_file():
                self._background = _background_samples(DEFAULT_BACKGROUND_SPEECH)
                self._background_reference = "shared/audio/assets/background_conversation.wav"
                self._background_provenance = "bundled_synthetic_speech"
            else:
                self._background_provenance = "synthetic_surrogate"
        else:
            self._background_provenance = None

        echo_enabled = (
            condition in {"echo", "realistic"}
            or self.realism.echo_delay_ms is not None
            or self.realism.echo_decay is not None
        )
        self._echo_delay_ms = (
            self.realism.echo_delay_ms if self.realism.echo_delay_ms is not None else 120 if echo_enabled else 0
        )
        self._echo_decay = (
            self.realism.echo_decay
            if self.realism.echo_decay is not None
            else DEFAULT_REALISTIC_ECHO_DECAY
            if condition == "realistic"
            else 0.35
        )
        delay_samples = self._echo_delay_ms * SAMPLE_RATE // 1_000 if echo_enabled else 0
        self._echo_buffer: deque[int] = deque([0] * delay_samples)

        packet_loss_enabled = (
            condition in {"packet_loss", "realistic"}
            or self.realism.packet_loss_rate is not None
            or self.realism.packet_loss_burst is not None
        )
        self._packet_loss_rate = (
            self.realism.packet_loss_rate
            if self.realism.packet_loss_rate is not None
            else DEFAULT_REALISTIC_PACKET_LOSS_RATE
            if condition == "realistic"
            else 0.08
            if packet_loss_enabled
            else 0.0
        )
        self._packet_loss_burst = self.realism.packet_loss_burst or (
            1 if condition == "realistic" else 2 if packet_loss_enabled else 1
        )
        self._loss_rng = random.Random(seed ^ 0xA0D10)
        self._remaining_lost_frames = 0

        self._cough_every_ms = (
            self.realism.cough_every_ms
            if self.realism.cough_every_ms is not None
            else 3_200
            if condition == "realistic"
            else 0
        )
        self._non_directed_every_ms = (
            self.realism.non_directed_every_ms
            if self.realism.non_directed_every_ms is not None
            else 4_600
            if condition == "realistic"
            else 0
        )
        self._next_event_samples = {"vocal_tic": 0, "non_directed": 0}
        self._active_event_samples: dict[str, deque[int]] = {
            "vocal_tic": deque(),
            "non_directed": deque(),
        }
        self._last_counted_event_samples = {"vocal_tic": -1, "non_directed": -1}

        self._sample_cursor = 0
        self._processed_frames = 0
        self._lost_frames = 0
        self._event_counts = {"vocal_tic": 0, "non_directed": 0}
        self._high_pass_inputs = [0.0, 0.0]
        self._high_pass_outputs = [0.0, 0.0]
        self._low_pass_outputs = [0.0, 0.0]
        self._telephone_phase = 0
        self._telephone_sample = 0
        self.last_source_pcm = b""
        self.last_packet_lost = False
        self.last_acoustic_events: tuple[AcousticEvent, ...] = ()

    @property
    def metadata(self) -> dict[str, object]:
        """Return effective settings and observations using JSON-safe values."""

        return {
            "preset": self.condition,
            "condition": self.condition,
            "seed": self.seed,
            "sample_rate": SAMPLE_RATE,
            "effects": {
                "telephony": self._telephony,
                "telephony_sample_rate_hz": TELEPHONE_SAMPLE_RATE if self._telephony else None,
                "telephony_band_hz": list(TELEPHONE_BAND_HZ) if self._telephony else None,
                "telephony_codec": "g711_mulaw" if self._telephony else None,
                "noise_rms": self._noise_rms if self._noise_enabled else None,
                "background_speech": self._background_reference,
                "background_gain": self._background_gain if self._background_enabled else None,
                "echo_delay_ms": self._echo_delay_ms if self._echo_buffer else None,
                "echo_decay": self._echo_decay if self._echo_buffer else None,
                "packet_loss_rate": self._packet_loss_rate,
                "packet_loss_burst": self._packet_loss_burst,
                "cough_every_ms": self._cough_every_ms or None,
                "non_directed_every_ms": self._non_directed_every_ms or None,
            },
            "background_provenance": self._background_provenance,
            "observations": {
                "processed_ticks": self._processed_frames,
                "processed_frames": self._processed_frames,
                "lost_ticks": self._lost_frames,
                "lost_frames": self._lost_frames,
                "vocal_tic_events": self._event_counts["vocal_tic"],
                "non_directed_events": self._event_counts["non_directed"],
            },
        }

    def _filter_telephony(self, samples: array[int]) -> array[int]:
        if not self._telephony:
            return array("h", samples)
        high_alpha = SAMPLE_RATE / (SAMPLE_RATE + 2 * math.pi * TELEPHONE_BAND_HZ[0])
        low_alpha = 2 * math.pi * TELEPHONE_BAND_HZ[1] / (SAMPLE_RATE + 2 * math.pi * TELEPHONE_BAND_HZ[1])
        downsample_factor = SAMPLE_RATE // TELEPHONE_SAMPLE_RATE
        filtered: array[int] = array("h")
        for sample in samples:
            value = float(sample)
            for stage in range(len(self._high_pass_outputs)):
                high = high_alpha * (self._high_pass_outputs[stage] + value - self._high_pass_inputs[stage])
                self._high_pass_inputs[stage] = value
                self._high_pass_outputs[stage] = high
                value = high
            for stage in range(len(self._low_pass_outputs)):
                self._low_pass_outputs[stage] += low_alpha * (value - self._low_pass_outputs[stage])
                value = self._low_pass_outputs[stage]
            if self._telephone_phase == 0:
                self._telephone_sample = _g711_mulaw_round_trip(_clip(value * 1.8))
            filtered.append(self._telephone_sample)
            self._telephone_phase = (self._telephone_phase + 1) % downsample_factor
        return filtered

    def _is_lost(self) -> bool:
        if self._remaining_lost_frames:
            self._remaining_lost_frames -= 1
            return True
        if self._packet_loss_rate and self._loss_rng.random() < self._packet_loss_rate:
            self._remaining_lost_frames = self._packet_loss_burst - 1
            return True
        return False

    def _events(
        self, count: int, *, speech_active: bool
    ) -> tuple[list[tuple[str, int, int, int, int, int]], tuple[AcousticEvent, ...]]:
        start_sample = self._sample_cursor
        end_sample = start_sample + count
        generated: list[tuple[str, int, int, int, int, int]] = []
        observed: list[AcousticEvent] = []
        specifications = (
            ("vocal_tic", self._cough_every_ms, 80, "synthetic_cough"),
            ("non_directed", self._non_directed_every_ms, 160, "synthetic_non_directed_speech"),
        )
        for kind, interval_ms, duration_ms, provenance in specifications:
            if not interval_ms:
                continue
            interval = max(1, interval_ms * SAMPLE_RATE // 1_000)
            duration = duration_ms * SAMPLE_RATE // 1_000
            active = self._active_event_samples[kind]
            while active and active[0] + duration <= start_sample:
                active.popleft()
            next_sample = self._next_event_samples[kind]
            if next_sample < start_sample:
                next_sample += ((start_sample - next_sample + interval - 1) // interval) * interval
            while next_sample < end_sample:
                if not speech_active:
                    active.append(next_sample)
                next_sample += interval
            self._next_event_samples[kind] = next_sample
            if speech_active:
                continue
            for event_start in active:
                segment_start = max(start_sample, event_start)
                segment_end = min(end_sample, event_start + duration)
                if segment_end <= segment_start:
                    continue
                generated.append(
                    (
                        kind,
                        segment_start - start_sample,
                        segment_end - start_sample,
                        segment_start - event_start,
                        duration,
                        event_start,
                    )
                )
                observed.append(
                    AcousticEvent(
                        kind=kind,
                        start_ms=segment_start * 1_000 // SAMPLE_RATE,
                        end_ms=(segment_end * 1_000 + SAMPLE_RATE - 1) // SAMPLE_RATE,
                        provenance=provenance,
                        origin_start_ms=event_start * 1_000 // SAMPLE_RATE,
                    )
                )
        observed.sort(key=lambda event: (event.start_ms, event.kind))
        return generated, tuple(observed)

    def process(self, pcm: bytes, *, speech_active: bool = True) -> bytes:
        """Return one conditioned frame without exposing ambience as caller speech."""

        if len(pcm) % 2:
            raise ValueError("PCM16 audio must contain complete samples")
        if not pcm:
            self.last_source_pcm = b""
            self.last_packet_lost = False
            self.last_acoustic_events = ()
            return b""

        samples: array[int] = array("h")
        samples.frombytes(pcm)
        primary = self._filter_telephony(samples)
        mixed = list(primary)

        if self._echo_buffer and self._echo_decay:
            for index, sample in enumerate(primary):
                delayed = self._echo_buffer.popleft()
                self._echo_buffer.append(sample)
                mixed[index] += delayed * self._echo_decay
        elif self._echo_buffer:
            for sample in primary:
                self._echo_buffer.popleft()
                self._echo_buffer.append(sample)

        if self._background_enabled and self._background_gain:
            for index in range(len(mixed)):
                position = self._sample_cursor + index
                if self._background is not None:
                    background = self._background[position % len(self._background)]
                else:
                    phase = 2 * math.pi * position / SAMPLE_RATE
                    background = 900 * math.sin(173 * phase) + 500 * math.sin(293 * phase)
                mixed[index] += background * self._background_gain

        if self._noise_enabled and self._noise_rms:
            rng = random.Random(self.seed + self._processed_frames)
            amplitude = round(self._noise_rms * math.sqrt(3))
            if amplitude <= _PCM_MAX:
                for index in range(len(mixed)):
                    mixed[index] += rng.randint(-amplitude, amplitude)
            else:
                uniform_mean_square = _PCM_MAX * (_PCM_MAX + 1) / 3
                endpoint_probability = max(
                    0.0,
                    min(
                        1.0,
                        (self._noise_rms**2 - uniform_mean_square) / (_PCM_MAX**2 - uniform_mean_square),
                    ),
                )
                for index in range(len(mixed)):
                    if rng.random() < endpoint_probability:
                        noise = _PCM_MAX if rng.getrandbits(1) else -_PCM_MAX
                    else:
                        noise = rng.randint(-_PCM_MAX, _PCM_MAX)
                    mixed[index] += noise

        generated, events = self._events(len(samples), speech_active=speech_active)
        for kind, start, end, initial_offset, duration, _ in generated:
            for index in range(start, end):
                offset = initial_offset + index - start
                if kind == "vocal_tic":
                    decay = 1 - offset / duration
                    distractor = 1_400 * decay * math.sin(2 * math.pi * 530 * offset / SAMPLE_RATE)
                else:
                    frequency = 230 if (offset // 960) % 2 == 0 else 360
                    distractor = 700 * math.sin(2 * math.pi * frequency * offset / SAMPLE_RATE)
                mixed[index] += distractor

        lost = self._is_lost()
        self.last_packet_lost = lost
        if lost:
            self._lost_frames += 1
            self.last_source_pcm = bytes(len(pcm))
            self.last_acoustic_events = ()
            result = bytes(len(pcm))
        else:
            self.last_source_pcm = primary.tobytes() if speech_active else bytes(len(pcm))
            self.last_acoustic_events = events
            for kind, _, _, _, _, event_start in generated:
                if event_start > self._last_counted_event_samples[kind]:
                    self._event_counts[kind] += 1
                    self._last_counted_event_samples[kind] = event_start
            result = array("h", (_clip(value) for value in mixed)).tobytes()

        self._sample_cursor += len(samples)
        self._processed_frames += 1
        return result


__all__ = [
    "AUDIO_CONDITIONS",
    "AUDIO_REALISM_FIELDS",
    "SAMPLE_RATE",
    "AcousticEvent",
    "AudioRealism",
    "AudioRealismProcessor",
    "add_audio_realism_arguments",
    "audio_realism_from_args",
]
