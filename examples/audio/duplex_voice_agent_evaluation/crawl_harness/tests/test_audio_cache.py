"""Synthetic caller recordings remain repeatable without entering shipped artifacts."""

from __future__ import annotations

import json
import tomllib
import wave
from pathlib import Path

import pytest

from crawl_harness.audio_cache import CallerAudioCache
from crawl_harness.evaluate import parse_args, run_evals


def _parameters() -> dict[str, str | int]:
    return {
        "text": "Please book a table for two.",
        "model": "gpt-4o-mini-tts",
        "voice": "marin",
        "sample_rate_hz": 24_000,
    }


def test_caller_audio_cache_reuses_a_valid_wav(tmp_path: Path) -> None:
    generated: list[bytes] = []

    def synthesize() -> bytes:
        generated.append(b"\x01\x00" * 480)
        return generated[-1]

    cache = CallerAudioCache(tmp_path / "recordings")
    first = cache.load_or_create("restaurant_003", **_parameters(), synthesize=synthesize)
    second = cache.load_or_create("restaurant_003", **_parameters(), synthesize=synthesize)

    assert first.reused is False
    assert second.reused is True
    assert first.path == second.path
    assert first.pcm == second.pcm == generated[0]
    assert len(generated) == 1
    with wave.open(str(first.path), "rb") as recording:
        assert recording.getnchannels() == 1
        assert recording.getsampwidth() == 2
        assert recording.getframerate() == 24_000
        assert recording.readframes(recording.getnframes()) == generated[0]


@pytest.mark.parametrize(
    ("setting", "value"),
    [
        ("text", "Please book a table for three."),
        ("model", "another-tts-model"),
        ("voice", "cedar"),
        ("sample_rate_hz", 16_000),
    ],
)
def test_synthesis_input_changes_create_separate_recordings(
    tmp_path: Path,
    setting: str,
    value: str | int,
) -> None:
    generated: list[bytes] = []

    def synthesize() -> bytes:
        generated.append(b"\x01\x00" * 480)
        return generated[-1]

    cache = CallerAudioCache(tmp_path / "recordings")
    original = cache.load_or_create("restaurant_003", **_parameters(), synthesize=synthesize)
    changed_parameters = {**_parameters(), setting: value}
    changed = cache.load_or_create("restaurant_003", **changed_parameters, synthesize=synthesize)

    assert original.path != changed.path
    assert original.reused is False
    assert changed.reused is False
    assert len(generated) == 2


def test_refresh_replaces_an_existing_recording(tmp_path: Path) -> None:
    generated: list[bytes] = []

    def synthesize() -> bytes:
        pcm = bytes((len(generated) + 1, 0)) * 480
        generated.append(pcm)
        return pcm

    directory = tmp_path / "recordings"
    original = CallerAudioCache(directory).load_or_create(
        "restaurant_003",
        **_parameters(),
        synthesize=synthesize,
    )
    refreshed = CallerAudioCache(directory, refresh=True).load_or_create(
        "restaurant_003",
        **_parameters(),
        synthesize=synthesize,
    )
    reused = CallerAudioCache(directory).load_or_create(
        "restaurant_003",
        **_parameters(),
        synthesize=synthesize,
    )

    assert original.path == refreshed.path == reused.path
    assert refreshed.reused is False
    assert reused.reused is True
    assert original.pcm != refreshed.pcm == reused.pcm
    assert len(generated) == 2


def test_corrupted_recording_is_regenerated(tmp_path: Path) -> None:
    generated: list[bytes] = []

    def synthesize() -> bytes:
        generated.append(b"\x01\x00" * 480)
        return generated[-1]

    cache = CallerAudioCache(tmp_path / "recordings")
    original = cache.load_or_create("restaurant_003", **_parameters(), synthesize=synthesize)
    original.path.write_bytes(b"not a WAV recording")
    repaired = cache.load_or_create("restaurant_003", **_parameters(), synthesize=synthesize)

    assert repaired.path == original.path
    assert repaired.reused is False
    assert len(generated) == 2
    with wave.open(str(repaired.path), "rb") as recording:
        assert recording.getframerate() == 24_000


def test_cache_rejects_empty_or_incomplete_pcm(tmp_path: Path) -> None:
    cache = CallerAudioCache(tmp_path / "recordings")

    for invalid in (b"", b"\x01"):
        with pytest.raises(ValueError, match="nonempty PCM16"):
            cache.load_or_create("restaurant_003", **_parameters(), synthesize=lambda pcm=invalid: pcm)

    assert not cache.directory.exists()


def test_scenario_identifier_cannot_escape_the_cache_directory(tmp_path: Path) -> None:
    cache = CallerAudioCache(tmp_path / "recordings")

    with pytest.raises(ValueError, match="artifact id"):
        cache.path_for("../../customer sample", **_parameters())


def test_cache_path_is_configured_relative_to_the_crawl_module_configuration(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text('[audio]\ncache_dir = "recordings/synthetic"\n', encoding="utf-8")

    args = parse_args(["--config", str(config), "--refresh-audio"])

    assert args.audio_cache_dir == tmp_path / "recordings" / "synthetic"
    assert args.refresh_audio is True


@pytest.mark.asyncio
async def test_offline_evaluations_do_not_create_or_reuse_synthetic_recordings(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text('[audio]\ncache_dir = "recordings"\n', encoding="utf-8")
    args = parse_args(
        [
            "--config",
            str(config),
            "--offline",
            "--no-real-time",
            "--example",
            "restaurant_003",
            "--results-dir",
            str(tmp_path / "results"),
        ]
    )

    run_directory = await run_evals(args)
    report = json.loads((run_directory / "results.json").read_text(encoding="utf-8"))

    assert report["summary"]["passed"] == 1
    assert report["run"]["configuration"]["audio_cache_dir"] == str(tmp_path / "recordings")
    assert not (tmp_path / "recordings").exists()


def test_cached_caller_recordings_are_ignored_and_excluded_from_distributions() -> None:
    project_root = Path(__file__).resolve().parents[2]
    with (project_root / "pyproject.toml").open("rb") as stream:
        excluded = tomllib.load(stream)["tool"]["hatch"]["build"]["exclude"]

    assert {"**/.audio_cache", "**/.audio_cache/**"}.issubset(excluded)
    assert "/crawl_harness/.audio_cache/" in (project_root / ".gitignore").read_text(encoding="utf-8")
