"""Recorded-audio replay, evaluator isolation, and shared WALK grading."""

from __future__ import annotations

import ast
import json
import wave
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from shared.audio.effects import AUDIO_CONDITIONS
from shared.audio.pcm import tone_for_text, write_mono_wav
from shared.scenarios import load_scenario_dataset
from shared.single_turn.grading import grade_single_turn_example
from walk_harness import evaluate as walk_runner
from walk_harness.evaluate import DEFAULT_DATA_JSON, load_dataset, parse_args, read_recorded_pcm, run_evals
from walk_harness.generate_audio import generate
from walk_harness.generate_audio import parse_args as parse_generator_args
from walk_harness.graders import grade_walk_example

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_walk_dataset_reuses_crawl_restaurant_examples_and_explicit_recordings() -> None:
    examples = load_dataset(DEFAULT_DATA_JSON)
    crawl = {
        scenario.id: scenario
        for scenario in load_scenario_dataset(PROJECT_ROOT / "crawl_harness/data/scenarios.json").scenarios
    }

    assert [scenario.id for scenario in examples[:5]] == [
        "restaurant_001",
        "restaurant_003",
        "restaurant_012",
        "restaurant_018",
        "restaurant_020",
    ]
    assert len(examples) == len(crawl) + 5
    assert len({scenario.id for scenario in examples}) == len(examples)
    for scenario in examples:
        generation = scenario.input.recordings[0].metadata.get("generation", {})
        original = crawl[generation.get("source_scenario_id", scenario.id)]
        assert scenario.input.recordings[0].path.is_file()
        assert scenario.input.text == original.input.text
        assert scenario.expected == original.expected
        assert scenario.application == original.application


def test_walk_uses_the_shared_single_turn_grader_and_metric_contract() -> None:
    assert grade_walk_example is grade_single_turn_example


def test_recorded_wav_reader_returns_exact_original_pcm() -> None:
    example = load_dataset(DEFAULT_DATA_JSON)[0]
    path = example.input.recordings[0].path
    with wave.open(str(path), "rb") as recording:
        expected = recording.readframes(recording.getnframes())

    assert read_recorded_pcm(path) == expected


@pytest.mark.parametrize(
    ("channels", "width", "sample_rate", "message"),
    [
        (2, 2, 24_000, "mono"),
        (1, 1, 24_000, "16-bit"),
        (1, 2, 16_000, "24000 Hz"),
    ],
)
def test_recorded_wav_rejects_unsupported_audio_instead_of_substituting_tts(
    tmp_path: Path,
    channels: int,
    width: int,
    sample_rate: int,
    message: str,
) -> None:
    path = tmp_path / "invalid.wav"
    with wave.open(str(path), "wb") as recording:
        recording.setnchannels(channels)
        recording.setsampwidth(width)
        recording.setframerate(sample_rate)
        recording.writeframes(bytes(channels * width * 100))

    with pytest.raises(ValueError, match=message):
        read_recorded_pcm(path)


def test_walk_runner_never_imports_crawl_or_a_tts_client() -> None:
    parsed = ast.parse((PROJECT_ROOT / "walk_harness/evaluate.py").read_text(encoding="utf-8"))
    imports = [node.module or "" for node in ast.walk(parsed) if isinstance(node, ast.ImportFrom)]

    assert not any(module.startswith("crawl_harness") for module in imports)
    assert not any(module.startswith("single_turn_eval") for module in imports)


@pytest.mark.asyncio
async def test_offline_walk_replays_original_recordings_and_isolates_reference_text(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    original_stream = walk_runner.stream_audio_to_connection
    streamed: list[bytes] = []

    async def observe_stream(connection: Any, pcm: bytes, *args: Any, **kwargs: Any) -> None:
        streamed.append(pcm)
        await original_stream(connection, pcm, *args, **kwargs)

    monkeypatch.setattr(walk_runner, "stream_audio_to_connection", observe_stream)
    args = parse_args(["--offline", "--no-real-time", "--results-dir", str(tmp_path)])

    run_dir = await run_evals(args)

    examples = load_dataset(DEFAULT_DATA_JSON)
    assert streamed == [read_recorded_pcm(example.input.recordings[0].path) for example in examples]
    report = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    rows = report["results"]
    assert len(rows) == 26
    assert all(row["status"] == "passed" for row in rows)
    assert all(row["metrics"]["task"]["task_completed"] for row in rows)
    assert all(row["metrics"]["task"]["semantic_quality"] == {"score": None, "dimensions": {}} for row in rows)
    assert all(row["assessment"]["passed"] for row in rows)
    assert all(row["observability"]["interaction"]["audio_source"] == "recorded" for row in rows)
    baseline_rows = [row for row in rows if "generation" not in row["recording"]["metadata"]]
    assert len(baseline_rows) == 5
    assert all(row["recording"]["metadata"] == {"language": "en"} for row in baseline_rows)
    generated_rows = [row for row in rows if "generation" in row["recording"]["metadata"]]
    assert len(generated_rows) == 21
    assert all("source_scenario_id" in row["recording"]["metadata"]["generation"] for row in generated_rows)
    assert {row["recording"]["condition"] for row in generated_rows} == set(AUDIO_CONDITIONS)
    assert all("agenda" not in row["observability"] and "floor" not in row["observability"] for row in rows)
    assert all("response_latency_ms" in row["metrics"]["audio"] for row in rows)
    assert all("floor_hold_silence_ms" in row["metrics"]["audio"] for row in rows)
    assert next(row for row in rows if row["scenario_id"] == "restaurant_001")["metrics"]["task"]["tool_calls"] == {
        "actual": 1,
        "expected": 1,
    }
    assert next(row for row in rows if row["scenario_id"] == "restaurant_020")["metrics"]["task"]["tool_calls"] == {
        "actual": 0,
        "expected": 0,
    }

    for scenario in examples:
        source_pcm = read_recorded_pcm(scenario.input.recordings[0].path)
        replayed = read_recorded_pcm(run_dir / "audio" / scenario.id / "input.wav")
        assert replayed == source_pcm
        trace_path = run_dir / "events" / f"{scenario.id}.jsonl"
        trace = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
        sent = [event for event in trace if event["direction"] == "client_to_server"]
        assert any(event["type"] == "session.input_audio.append" for event in sent)
        assert all(event["type"] != "input_text" for event in sent)
        assert any(event["type"] == "evaluation.checks.assessed" for event in trace)
        assert any(event["type"] == "evaluation.outcome.assessed" for event in trace)
        assert [event["event_index"] for event in trace] == list(range(1, len(trace) + 1))
        serialized = json.dumps(sent, ensure_ascii=False)
        assert scenario.input.text not in serialized
        assert scenario.expected.answer not in serialized

    assert report["run"]["module"] == "walk"
    assert report["run"]["configuration"]["audio_source"] == "recorded"
    assert report["summary"]["passed"] == 26
    assert report["summary"]["infrastructure_errors"] == 0
    assert "semantic_quality" not in report["summary"]


@pytest.mark.asyncio
async def test_walk_selects_one_recording_and_preserves_result_artifacts(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    args = parse_args(
        [
            "--offline",
            "--no-real-time",
            "--example",
            "restaurant_003",
            "--results-dir",
            str(tmp_path),
        ]
    )

    run_dir = await run_evals(args)
    output = capsys.readouterr().out

    assert "Completed 1/1 valid recordings; 1 passed; 0 failed; 0 infrastructure failures." in output
    assert f"Results: {run_dir}" in output
    assert "restaurant_003" not in output
    assert "session.input_audio.append" not in output
    assert (run_dir / "audio/restaurant_003/conversation.wav").is_file()
    assert (run_dir / "audio/restaurant_003/conversation.transcript.txt").is_file()
    assert (run_dir / "events/restaurant_003.jsonl").is_file()
    result = json.loads((run_dir / "transcripts/restaurant_003.json").read_text(encoding="utf-8"))
    assert result["audio_source"] == "recorded"
    assert result["recording"] == {
        "id": "caller_recording",
        "path": str(load_dataset(DEFAULT_DATA_JSON)[1].input.recordings[0].path),
        "condition": "clean",
        "metadata": {"language": "en"},
    }
    assert result["input_reference"] == "Book a table for Maya on August 7—sorry, August 6—at 7 p.m. for two."
    assert result["task_metrics"]["task_completed"]
    assert result["assessment"]["passed"] is True
    assert result["observability"]["interaction"]["audio_source"] == "recorded"
    assert result["tool_executions"][0]["arguments"]["date"] == "2026-08-06"


@pytest.mark.asyncio
async def test_walk_preserves_recording_conditions_and_nested_acoustic_metadata(tmp_path: Path) -> None:
    scenario = load_dataset(DEFAULT_DATA_JSON)[0].model_copy(deep=True)
    recording = scenario.input.recordings[0]
    recording.condition = "noisy"
    recording.metadata = {
        "language": "en-GB",
        "accent": "Scottish",
        "microphone": {"device": "headset", "distance_cm": 15},
        "environment": "busy restaurant",
    }
    dataset = tmp_path / "recorded-scenarios.json"
    dataset.write_text(
        json.dumps({"schema_version": "1.0", "scenarios": [scenario.model_dump(mode="json")]}),
        encoding="utf-8",
    )
    args = parse_args(["--offline", "--no-real-time", "--data", str(dataset), "--results-dir", str(tmp_path)])

    run_dir = await run_evals(args)

    expected = recording.model_dump(mode="json")
    report = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    transcript = json.loads((run_dir / "transcripts" / f"{scenario.id}.json").read_text(encoding="utf-8"))
    assert report["results"][0]["recording"] == expected
    assert transcript["recording"] == expected


@pytest.mark.parametrize("concurrency", [0, -1, 9])
@pytest.mark.asyncio
async def test_walk_rejects_invalid_concurrency(tmp_path: Path, concurrency: int) -> None:
    args = parse_args(["--offline", "--concurrency", str(concurrency), "--results-dir", str(tmp_path)])

    with pytest.raises(ValueError, match="between 1 and 8"):
        await run_evals(args)


@pytest.mark.asyncio
async def test_live_walk_requires_an_api_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")
    args = parse_args(["--results-dir", str(tmp_path)])

    with pytest.raises(ValueError, match="OPENAI_API_KEY is required"):
        await run_evals(args)


@pytest.mark.asyncio
async def test_sample_generator_saves_wav_files_from_the_reference_transcript(tmp_path: Path) -> None:
    dataset = tmp_path / "recordings.json"
    dataset.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "scenarios": [
                    {
                        "id": "sample",
                        "title": "Recorded sample",
                        "interaction": "single_turn",
                        "input": {
                            "text": "Do you have a table for two?",
                            "recordings": [{"id": "sample_recording", "path": "audio/sample.wav"}],
                        },
                        "expected": {"answer": "Confirm availability."},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    class FakeSpeech:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        async def create(self, **kwargs: Any) -> SimpleNamespace:
            self.calls.append(kwargs)
            return SimpleNamespace(content=b"\x01\x00" * 480)

    speech = FakeSpeech()
    client = SimpleNamespace(audio=SimpleNamespace(speech=speech))
    args = parse_generator_args(["--data", str(dataset)])

    generated = await generate(args, client=client)

    assert generated == 1
    assert speech.calls[0]["input"] == "Do you have a table for two?"
    assert speech.calls[0]["response_format"] == "pcm"
    assert read_recorded_pcm(tmp_path / "audio/sample.wav") == b"\x01\x00" * 480


@pytest.mark.asyncio
async def test_sample_generator_creates_reproducible_noisy_walk_data_from_text_only_scenarios(
    tmp_path: Path,
) -> None:
    source = load_scenario_dataset(PROJECT_ROOT / "crawl_harness/data/scenarios.json").scenarios[2]
    dataset = tmp_path / "text-scenarios.json"
    dataset.write_text(
        json.dumps({"schema_version": "1.0", "scenarios": [source.model_dump(mode="json")]}),
        encoding="utf-8",
    )
    source_pcm = tone_for_text(source.input.text)

    class FakeSpeech:
        def __init__(self) -> None:
            self.calls = 0

        async def create(self, **_: Any) -> SimpleNamespace:
            self.calls += 1
            return SimpleNamespace(content=source_pcm)

    speech = FakeSpeech()
    client = SimpleNamespace(audio=SimpleNamespace(speech=speech))
    output_data = tmp_path / "conditioned" / "scenarios.json"
    arguments = [
        "--data",
        str(dataset),
        "--output-data",
        str(output_data),
        "--condition",
        "noisy",
        "--noise-rms",
        "120",
        "--seed",
        "41",
    ]

    assert await generate(parse_generator_args(arguments), client=client) == 1
    scenario = load_dataset(output_data)[0]
    recording = scenario.input.recordings[0]
    conditioned = read_recorded_pcm(recording.path)

    assert recording.condition == "noisy"
    assert recording.metadata["generation"]["source"] == "synthetic_speech"
    assert recording.metadata["generation"]["audio_realism"]["seed"] == 41
    assert recording.metadata["generation"]["audio_realism"]["effects"]["noise_rms"] == 120
    assert len(conditioned) == len(source_pcm)
    assert conditioned != source_pcm
    assert speech.calls == 1

    assert await generate(parse_generator_args([*arguments, "--force"]), client=client) == 1
    assert read_recorded_pcm(recording.path) == conditioned
    assert speech.calls == 2

    assert await generate(parse_generator_args(arguments), client=client) == 0
    reused = load_dataset(output_data)[0].input.recordings[0]
    assert reused.metadata["generation"]["source"] == "synthetic_speech"
    assert reused.metadata["generation"]["audio_realism"]["effects"]["noise_rms"] == 120
    assert speech.calls == 2


def test_varied_conditions_use_only_the_seven_existing_acoustic_presets() -> None:
    assert AUDIO_CONDITIONS == (
        "clean",
        "noisy",
        "telephony",
        "background_speech",
        "echo",
        "packet_loss",
        "realistic",
    )


@pytest.mark.asyncio
async def test_sample_generator_varies_conditions_and_preserves_reusable_clean_baselines(tmp_path: Path) -> None:
    source_scenarios = load_scenario_dataset(PROJECT_ROOT / "crawl_harness/data/scenarios.json").scenarios[:3]
    source_data = tmp_path / "source.json"
    source_data.write_text(
        json.dumps({"schema_version": "1.0", "scenarios": [item.model_dump(mode="json") for item in source_scenarios]}),
        encoding="utf-8",
    )
    baseline = load_dataset(DEFAULT_DATA_JSON)[0].model_copy(deep=True)
    output_data = tmp_path / "scenarios.json"
    output_data.write_text(
        json.dumps({"schema_version": "1.0", "scenarios": [baseline.model_dump(mode="json")]}),
        encoding="utf-8",
    )

    class FakeSpeech:
        def __init__(self) -> None:
            self.calls = 0

        async def create(self, **kwargs: Any) -> SimpleNamespace:
            self.calls += 1
            return SimpleNamespace(content=tone_for_text(kwargs["input"]))

    speech = FakeSpeech()
    client = SimpleNamespace(audio=SimpleNamespace(speech=speech))
    arguments = [
        "--data",
        str(source_data),
        "--output-data",
        str(output_data),
        "--vary-conditions",
        "--append",
        "--seed",
        "41",
    ]

    assert await generate(parse_generator_args(arguments), client=client) == 3
    scenarios = load_dataset(output_data)

    assert [scenario.id for scenario in scenarios] == [
        "restaurant_001",
        "restaurant_001_clean",
        "restaurant_002_noisy",
        "restaurant_003_telephony",
    ]
    assert speech.calls == 2
    assert scenarios[1].input.recordings[0].metadata["generation"]["source"] == "existing_recording"
    for index, scenario in enumerate(scenarios[1:]):
        recording = scenario.input.recordings[0]
        generation = recording.metadata["generation"]
        assert recording.condition == AUDIO_CONDITIONS[index]
        assert "profile" not in generation
        assert generation["source_scenario_id"] == source_scenarios[index].id
        assert generation["audio_realism"]["seed"] == 41 + index
        assert recording.path.parent.name == "conditioned"

    assert await generate(parse_generator_args(arguments), client=client) == 0
    assert len(load_dataset(output_data)) == 4
    assert speech.calls == 2


@pytest.mark.asyncio
async def test_varying_conditions_replaces_stale_generated_names_without_removing_clean_baselines(
    tmp_path: Path,
) -> None:
    source = load_scenario_dataset(PROJECT_ROOT / "crawl_harness/data/scenarios.json").scenarios[0]
    source_data = tmp_path / "source.json"
    source_data.write_text(
        json.dumps({"schema_version": "1.0", "scenarios": [source.model_dump(mode="json")]}),
        encoding="utf-8",
    )
    baseline = load_dataset(DEFAULT_DATA_JSON)[0].model_copy(deep=True)
    obsolete = baseline.model_copy(deep=True)
    obsolete.id = "restaurant_001_small_room_echo"
    obsolete.input.recordings[0].path = Path("audio/conditioned/restaurant_001_small_room_echo.wav")
    obsolete.input.recordings[0].metadata["generation"] = {"source_scenario_id": source.id}
    obsolete_path = tmp_path / obsolete.input.recordings[0].path
    write_mono_wav(obsolete_path, tone_for_text(source.input.text), 24_000)
    output_data = tmp_path / "scenarios.json"
    output_data.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "scenarios": [baseline.model_dump(mode="json"), obsolete.model_dump(mode="json")],
            }
        ),
        encoding="utf-8",
    )

    assert (
        await generate(
            parse_generator_args(
                ["--data", str(source_data), "--output-data", str(output_data), "--vary-conditions", "--append"]
            )
        )
        == 1
    )
    assert [scenario.id for scenario in load_dataset(output_data)] == ["restaurant_001", "restaurant_001_clean"]
    assert not obsolete_path.exists()


@pytest.mark.parametrize(
    "arguments",
    [
        ["--vary-conditions", "--condition", "noisy"],
        ["--vary-conditions", "--noise-rms", "90"],
        ["--append"],
    ],
)
def test_sample_generator_rejects_ambiguous_varied_condition_options(arguments: list[str]) -> None:
    with pytest.raises(SystemExit):
        parse_generator_args(arguments)


@pytest.mark.asyncio
async def test_sample_generator_reuses_clean_recording_without_tts_and_walk_replays_conditioned_wav(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")
    original = next(item for item in load_dataset(DEFAULT_DATA_JSON) if item.id == "restaurant_003")
    source_pcm = read_recorded_pcm(original.input.recordings[0].path)
    output_data = tmp_path / "telephony" / "scenarios.json"
    args = parse_generator_args(
        [
            "--data",
            str(DEFAULT_DATA_JSON),
            "--example",
            original.id,
            "--output-data",
            str(output_data),
            "--condition",
            "telephony",
            "--seed",
            "41",
        ]
    )

    assert await generate(args) == 1
    scenario = load_dataset(output_data)[0]
    recording = scenario.input.recordings[0]
    conditioned = read_recorded_pcm(recording.path)

    assert recording.condition == "telephony"
    assert recording.metadata["generation"]["source"] == "existing_recording"
    assert len(conditioned) == len(source_pcm)
    assert conditioned != source_pcm

    run_dir = await run_evals(
        parse_args(["--offline", "--no-real-time", "--data", str(output_data), "--results-dir", str(tmp_path)])
    )
    assert read_recorded_pcm(run_dir / "audio" / scenario.id / "input.wav") == conditioned
    result = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))["results"][0]
    assert result["recording"]["condition"] == "telephony"
    assert result["recording"]["metadata"]["generation"]["audio_realism"]["effects"]["telephony"] is True


@pytest.mark.asyncio
async def test_sample_generator_writes_automatic_condition_dataset_without_modifying_the_source(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")
    scenario = load_dataset(DEFAULT_DATA_JSON)[0].model_copy(deep=True)
    dataset = tmp_path / "scenarios.json"
    dataset.write_text(
        json.dumps({"schema_version": "1.0", "scenarios": [scenario.model_dump(mode="json")]}),
        encoding="utf-8",
    )
    before = dataset.read_bytes()

    assert await generate(parse_generator_args(["--data", str(dataset), "--condition", "echo"])) == 1

    generated_data = tmp_path / "scenarios.echo.json"
    generated = load_dataset(generated_data)[0]
    assert generated.input.recordings[0].condition == "echo"
    assert generated.input.recordings[0].path.name == f"{scenario.id}_echo.wav"
    assert dataset.read_bytes() == before


@pytest.mark.asyncio
async def test_sample_generator_requires_api_access_only_when_source_speech_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")
    scenario = load_scenario_dataset(PROJECT_ROOT / "crawl_harness/data/scenarios.json").scenarios[0]
    dataset = tmp_path / "text-scenarios.json"
    dataset.write_text(
        json.dumps({"schema_version": "1.0", "scenarios": [scenario.model_dump(mode="json")]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="synthesize missing caller recordings"):
        await generate(parse_generator_args(["--data", str(dataset), "--condition", "noisy"]))


@pytest.mark.asyncio
async def test_sample_generator_rejects_invalid_effect_frames_before_synthesizing_audio(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")
    scenario = load_scenario_dataset(PROJECT_ROOT / "crawl_harness/data/scenarios.json").scenarios[0]
    dataset = tmp_path / "text-scenarios.json"
    dataset.write_text(
        json.dumps({"schema_version": "1.0", "scenarios": [scenario.model_dump(mode="json")]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="--frame-ms must be greater than zero"):
        await generate(parse_generator_args(["--data", str(dataset), "--condition", "noisy", "--frame-ms", "0"]))


def test_recorded_audio_is_not_generated_during_dataset_loading(tmp_path: Path) -> None:
    dataset = tmp_path / "missing.json"
    source = load_dataset(DEFAULT_DATA_JSON)[0].model_copy(deep=True)
    source.input.recordings[0].path = Path("audio/missing.wav")
    dataset.write_text(
        json.dumps({"schema_version": "1.0", "scenarios": [source.model_dump(mode="json")]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="existing .wav file"):
        load_dataset(dataset)

    assert not (tmp_path / "audio/missing.wav").exists()


def test_source_audio_writer_creates_a_valid_wav_without_text_metadata(tmp_path: Path) -> None:
    pcm = b"\x03\x00" * 480
    path = write_mono_wav(tmp_path / "source.wav", pcm, 24_000)

    assert read_recorded_pcm(path) == pcm
