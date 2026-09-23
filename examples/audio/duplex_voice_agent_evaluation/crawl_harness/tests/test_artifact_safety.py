"""Imported datasets cannot redirect or alias writable artifacts."""

from __future__ import annotations

import importlib
import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from crawl_harness.audio_cache import CallerAudioCache
from shared.artifacts import artifact_path, create_run_directory, scenario_audio_directory, validate_artifact_id
from shared.audio.pcm import write_mono_wav
from shared.scenarios import ScenarioDataset, load_scenario_dataset
from walk_harness.generate_audio import generate, parse_args

ROOT = Path(__file__).resolve().parents[2]
BAD_IDS = [
    "/tmp/escape",
    "../escape",
    "a/b",
    "a\\b",
    "C:escape",
    "\\\\server\\share",
    ".",
    "..",
    "bad\nname",
    "bad\x00name",
    "name.",
    "name ",
    "CON",
    "nul.txt",
    "LPT9",
    "x" * 101,
]


def _scenario(identifier: str, recording: str | None = None) -> dict:
    item = {
        "id": identifier,
        "title": "Sample",
        "interaction": "single_turn",
        "input": {"text": "Hello"},
        "expected": {"answer": "Hello"},
    }
    if recording is not None:
        item["input"]["recordings"] = [{"id": "recording", "path": recording}]
    return item


def _dataset(path: Path, scenarios: list[dict]) -> Path:
    path.write_text(json.dumps({"schema_version": "1.0", "scenarios": scenarios}))
    return path


def _client() -> SimpleNamespace:
    return SimpleNamespace(
        audio=SimpleNamespace(
            speech=SimpleNamespace(
                create=AsyncMock(return_value=SimpleNamespace(content=b"\x01\x00" * 480)),
            )
        )
    )


@pytest.mark.parametrize("identifier", BAD_IDS)
def test_reject_unsafe_portable_identifiers(identifier: str) -> None:
    with pytest.raises(ValueError, match="artifact id"):
        ScenarioDataset.model_validate({"scenarios": [_scenario(identifier)]})


def test_safe_ids_are_not_silently_normalized() -> None:
    for identifier in ("a", "A.b_c-9", "x" * 100):
        assert validate_artifact_id(identifier) == identifier
    with pytest.raises(ValueError, match="case-insensitive"):
        ScenarioDataset.model_validate({"scenarios": [_scenario("Sample"), _scenario("sample")]})


@pytest.mark.parametrize("module", ["crawl_harness", "walk_harness", "run_harness"])
@pytest.mark.parametrize("invalid", ["absolute", "../escape", "a\\b", "x" * 101, "case_collision"])
@pytest.mark.asyncio
async def test_entire_import_is_rejected_before_run_creation(
    tmp_path: Path,
    module: str,
    invalid: str,
) -> None:
    evaluator = importlib.import_module(f"{module}.evaluate")
    first = load_scenario_dataset(ROOT / module / "data/scenarios.json").scenarios[0].model_dump(mode="json")
    second = deepcopy(first)
    escaped = tmp_path / "escaped"
    second["id"] = (
        str(escaped) if invalid == "absolute" else first["id"].upper() if invalid == "case_collision" else invalid
    )
    data = _dataset(tmp_path / "data.json", [first, second])
    results = tmp_path / "results"
    args = evaluator.parse_args(
        [
            "--data",
            str(data),
            "--results-dir",
            str(results),
            "--offline",
            "--example",
            first["id"],
            "--max-examples",
            "1",
        ]
    )
    with pytest.raises(ValueError):
        await evaluator.run_evals(args)
    assert not results.exists()
    assert not escaped.exists()
    assert not escaped.with_suffix(".jsonl").exists()


@pytest.mark.parametrize("kind", ["directory", "file", "internal", "dangling", "hardlink"])
def test_destinations_reject_existing_links(tmp_path: Path, kind: str) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    victim = outside / "victim.wav"
    victim.write_bytes(b"untouched")
    if kind == "directory":
        (root / "sample").symlink_to(outside, target_is_directory=True)
    else:
        (root / "sample").mkdir()
        target = root / "sample/input.wav"
        if kind == "hardlink":
            target.hardlink_to(victim)
        elif kind == "internal":
            inside = root / "other.wav"
            inside.write_bytes(b"untouched")
            target.symlink_to(inside)
        else:
            target.symlink_to(victim if kind == "file" else outside / "missing")
    with pytest.raises(ValueError, match="link"):
        scenario_audio_directory(root, "sample")
    assert victim.read_bytes() == b"untouched"


@pytest.mark.parametrize("part", ["../escape", "/tmp/escape", "C:\\escape", "a\\b"])
def test_destination_rejects_nonrelative_paths(tmp_path: Path, part: str) -> None:
    with pytest.raises(ValueError):
        artifact_path(tmp_path, part)


def test_run_directory_is_never_reused(tmp_path: Path) -> None:
    run = create_run_directory(tmp_path, "run_test")
    marker = run / "results.json"
    marker.write_text("untouched")
    with pytest.raises(FileExistsError):
        create_run_directory(tmp_path, "run_test")
    assert marker.read_text() == "untouched"


@pytest.mark.parametrize("module", ["crawl_harness", "walk_harness", "run_harness"])
@pytest.mark.asyncio
async def test_harness_refuses_preexisting_run_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    module: str,
) -> None:
    evaluator = importlib.import_module(f"{module}.evaluate")
    results = tmp_path / "results"
    results.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (results / "fixed_run").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(evaluator, "build_timestamped_run_name", lambda **_: "fixed_run")
    args = evaluator.parse_args(["--offline", "--max-examples", "1", "--results-dir", str(results)])
    with pytest.raises(ValueError, match="symlink"):
        await evaluator.run_evals(args)
    assert list(outside.iterdir()) == []


def test_cache_checks_destination_before_synthesis(tmp_path: Path) -> None:
    cache = CallerAudioCache(tmp_path / "cache", refresh=True)
    params = dict(text="hi", model="model", voice="voice", sample_rate_hz=24000)
    target = cache.path_for("sample", **params)
    target.parent.mkdir()
    victim = tmp_path / "victim"
    victim.write_bytes(b"untouched")
    target.symlink_to(victim)
    with pytest.raises(ValueError, match="symlink"):
        cache.load_or_create("sample", **params, synthesize=lambda: pytest.fail("TTS must not run"))
    assert victim.read_bytes() == b"untouched"


@pytest.mark.parametrize(
    "bad_path",
    [
        "../victim.wav",
        "/tmp/victim.wav",
        "audio/../victim.wav",
        "audio\\victim.wav",
        "audio/NUL.wav",
        "audio/dir./victim.wav",
        "audio/victim:stream.wav",
    ],
)
@pytest.mark.asyncio
async def test_generator_preflights_every_recording(tmp_path: Path, bad_path: str) -> None:
    source = _dataset(tmp_path / "data.json", [_scenario("first", "audio/first.wav"), _scenario("second", bad_path)])
    client = _client()
    with pytest.raises(ValueError):
        await generate(parse_args(["--data", str(source), "--force"]), client=client)
    client.audio.speech.create.assert_not_called()
    assert not (tmp_path / "audio").exists()


@pytest.mark.parametrize("kind", ["directory", "file", "internal", "hardlink"])
@pytest.mark.asyncio
async def test_generator_refuses_linked_destinations(tmp_path: Path, kind: str) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    victim = outside / "victim.wav"
    victim.write_bytes(b"untouched")
    audio = tmp_path / "audio"
    if kind == "directory":
        audio.symlink_to(outside, target_is_directory=True)
    else:
        audio.mkdir()
        target = audio / "sample.wav"
        if kind == "hardlink":
            target.hardlink_to(victim)
        elif kind == "internal":
            other = audio / "other.wav"
            other.write_bytes(b"untouched")
            target.symlink_to(other)
        else:
            target.symlink_to(victim)
    data = _dataset(tmp_path / "data.json", [_scenario("sample", "audio/sample.wav")])
    client = _client()
    with pytest.raises(ValueError, match="link"):
        await generate(parse_args(["--data", str(data), "--force"]), client=client)
    client.audio.speech.create.assert_not_called()
    assert victim.read_bytes() == b"untouched"


@pytest.mark.parametrize("second_path", ["audio/shared.wav", "audio/SHARED.wav"])
@pytest.mark.asyncio
async def test_force_cannot_overwrite_an_unselected_scenarios_recording(tmp_path: Path, second_path: str) -> None:
    data = _dataset(tmp_path / "data.json", [_scenario("first", "audio/shared.wav"), _scenario("second", second_path)])
    client = _client()
    with pytest.raises(ValueError, match="collision"):
        await generate(parse_args(["--data", str(data), "--example", "first", "--force"]), client=client)
    client.audio.speech.create.assert_not_called()
    assert not (tmp_path / "audio").exists()


@pytest.mark.asyncio
async def test_derived_names_cannot_collide_with_existing_scenario_owners(tmp_path: Path) -> None:
    source = _dataset(tmp_path / "source.json", [_scenario("first")])
    output = _dataset(tmp_path / "output.json", [_scenario("other", "audio/first_clean.wav")])
    client = _client()
    with pytest.raises(ValueError, match="collision"):
        await generate(parse_args(["--data", str(source), "--output-data", str(output), "--force"]), client=client)
    client.audio.speech.create.assert_not_called()


@pytest.mark.asyncio
async def test_derived_ids_are_validated_before_tts(tmp_path: Path) -> None:
    source = _dataset(tmp_path / "source.json", [_scenario("x" * 100)])
    client = _client()
    with pytest.raises(ValueError, match="artifact id"):
        await generate(parse_args(["--data", str(source), "--vary-conditions"]), client=client)
    client.audio.speech.create.assert_not_called()


@pytest.mark.asyncio
async def test_external_wav_can_be_read_but_not_overwritten(tmp_path: Path) -> None:
    external = tmp_path / "external.wav"
    write_mono_wav(external, b"\x01\x00" * 480, 24000)
    original = external.read_bytes()
    data = _dataset(tmp_path / "source.json", [_scenario("sample", str(external))])
    client = _client()
    with pytest.raises(ValueError):
        await generate(parse_args(["--data", str(data), "--force"]), client=client)
    output = tmp_path / "derived/data.json"
    assert await generate(parse_args(["--data", str(data), "--output-data", str(output)]), client=client) == 1
    client.audio.speech.create.assert_not_called()
    assert external.read_bytes() == original
    assert (output.parent / "audio/sample_clean.wav").is_file()
