"""Persistent, content-addressed caller audio for repeatable CRAWL evaluations."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
import wave
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from shared.artifacts import artifact_path, validate_artifact_id
from shared.audio.pcm import write_mono_wav
from shared.paths import require_external_output
from shared.private_files import private_directory


@dataclass(frozen=True, slots=True)
class CachedCallerAudio:
    """A validated PCM recording and its reusable WAV cache location."""

    pcm: bytes
    path: Path
    reused: bool


class CallerAudioCache:
    """Reuse identical caller speech without confusing it with human WALK audio."""

    def __init__(self, directory: Path, *, refresh: bool = False) -> None:
        self.directory = require_external_output(directory)
        self.refresh = refresh

    def path_for(self, scenario_id: str, *, text: str, model: str, voice: str, sample_rate_hz: int) -> Path:
        validate_artifact_id(scenario_id)
        parameters = {
            "scenario_id": scenario_id,
            "text": text,
            "model": model,
            "voice": voice,
            "sample_rate_hz": sample_rate_hz,
            "format": "pcm16-mono-v1",
        }
        serialized = json.dumps(parameters, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]
        label = re.sub(r"[^a-zA-Z0-9_-]", "_", scenario_id).strip("_") or "scenario"
        return artifact_path(self.directory, f"{label}-{digest}.wav")

    def load_or_create(
        self,
        scenario_id: str,
        *,
        text: str,
        model: str,
        voice: str,
        sample_rate_hz: int,
        synthesize: Callable[[], bytes],
    ) -> CachedCallerAudio:
        path = self.path_for(scenario_id, text=text, model=model, voice=voice, sample_rate_hz=sample_rate_hz)
        if path.is_file() and not self.refresh:
            try:
                return CachedCallerAudio(self._read_pcm(path, sample_rate_hz), path, reused=True)
            except (EOFError, ValueError, wave.Error):
                pass

        pcm = synthesize()
        if not pcm or len(pcm) % 2:
            raise ValueError("Cached caller audio requires nonempty PCM16 samples")
        private_directory(self.directory)
        temporary = artifact_path(self.directory, f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            write_mono_wav(temporary, pcm, sample_rate_hz)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
        return CachedCallerAudio(pcm, path, reused=False)

    @staticmethod
    def _read_pcm(path: Path, sample_rate_hz: int) -> bytes:
        with wave.open(str(path), "rb") as recording:
            if recording.getnchannels() != 1:
                raise ValueError("Cached caller audio must be mono")
            if recording.getsampwidth() != 2:
                raise ValueError("Cached caller audio must use 16-bit PCM")
            if recording.getframerate() != sample_rate_hz:
                raise ValueError("Cached caller audio has the wrong sample rate")
            if recording.getcomptype() != "NONE":
                raise ValueError("Cached caller audio must be uncompressed")
            pcm = recording.readframes(recording.getnframes())
        if not pcm or len(pcm) % 2:
            raise ValueError("Cached caller audio must contain complete PCM16 samples")
        return pcm
