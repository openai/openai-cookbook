"""Generate small, replayable restaurant WAV fixtures for the WALK harness."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections.abc import Sequence
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from shared.artifacts import artifact_path, validate_artifact_id
from shared.audio.effects import (
    AUDIO_CONDITIONS,
    SAMPLE_RATE,
    AudioRealism,
    AudioRealismProcessor,
    add_audio_realism_arguments,
    audio_realism_from_args,
)
from shared.audio.pcm import read_mono_wav, rms_pcm16, write_mono_wav
from shared.environment import load_environment
from shared.paths import is_installed_package_path, package_path, require_external_output
from shared.private_files import private_directory, private_write_text
from shared.scenarios import (
    AudioCondition,
    Recording,
    Scenario,
    ScenarioDataset,
    load_scenario_dataset,
    resolve_recording_path,
)

DEFAULT_DATA_JSON = package_path("walk_harness", "data", "scenarios.json")
DEFAULT_SAMPLE_RATE_HZ = SAMPLE_RATE
DEFAULT_FRAME_MS = 200
DEFAULT_SPEECH_RMS_THRESHOLD = 220.0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    load_environment()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA_JSON)
    parser.add_argument("--output-data", type=Path, help="Write a separate WALK scenario dataset and generated WAVs.")
    parser.add_argument("--example", default="all", help="Generate one scenario ID or every single-turn scenario.")
    parser.add_argument("--model", default=os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts"))
    parser.add_argument("--voice", default=os.getenv("OPENAI_WALK_TTS_VOICE", "marin"))
    add_audio_realism_arguments(parser)
    parser.add_argument(
        "--vary-conditions",
        action="store_true",
        help="Cycle through the seven built-in acoustic presets across scenarios.",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Preserve existing scenarios in --output-data and reuse their clean recordings when possible.",
    )
    parser.add_argument("--seed", type=int, default=7, help="Seed for reproducible acoustic effects.")
    parser.add_argument("--frame-ms", type=int, default=DEFAULT_FRAME_MS, help="Audio-effect frame duration.")
    parser.add_argument("--force", action="store_true", help="Replace existing example WAV files.")
    args = parser.parse_args(argv)
    if args.vary_conditions and args.condition is not None:
        parser.error("--vary-conditions cannot be combined with --condition")
    if args.vary_conditions and audio_realism_from_args(args).model_fields_set:
        parser.error("--vary-conditions uses predefined acoustic settings and cannot be combined with effect overrides")
    if args.append and args.output_data is None:
        parser.error("--append requires --output-data")
    return args


def _condition_audio(
    pcm: bytes,
    *,
    condition: AudioCondition,
    seed: int,
    frame_ms: int,
    realism: AudioRealism,
) -> tuple[bytes, dict[str, object]]:
    if frame_ms <= 0:
        raise ValueError("--frame-ms must be greater than zero")
    frame_bytes = DEFAULT_SAMPLE_RATE_HZ * frame_ms // 1_000 * 2
    if frame_bytes <= 0:
        raise ValueError("--frame-ms must produce at least one PCM16 audio frame")
    processor = AudioRealismProcessor(condition, seed, realism)
    transformed = bytearray()
    for offset in range(0, len(pcm), frame_bytes):
        frame = pcm[offset : offset + frame_bytes]
        transformed.extend(processor.process(frame, speech_active=rms_pcm16(frame) >= DEFAULT_SPEECH_RMS_THRESHOLD))
    return bytes(transformed), processor.metadata


def _derived_dataset_path(args: argparse.Namespace) -> Path:
    if args.output_data is not None:
        return args.output_data.expanduser().resolve()
    suffix = "varied" if args.vary_conditions else args.condition or "generated"
    source = args.data.expanduser().resolve()
    if is_installed_package_path(source):
        return Path.cwd() / "data" / "walk" / f"{source.stem}.{suffix}{source.suffix}"
    return source.with_name(f"{source.stem}.{suffix}{source.suffix}")


def _target_recording(
    scenario: Scenario,
    recording: Recording | None,
    *,
    condition: AudioCondition,
    derived: bool,
    profile_name: str | None = None,
) -> Recording:
    target_path = (
        Path("audio") / "conditioned" / f"{scenario.id}.wav"
        if profile_name is not None
        else Path("audio") / f"{scenario.id}_{condition}.wav"
    )
    if recording is None:
        return Recording(
            id="synthetic_recording",
            path=target_path,
            condition=condition,
        )
    if not derived:
        return recording.model_copy(deep=True)
    target = recording.model_copy(deep=True)
    target.id = f"{recording.id}_{profile_name or condition}"
    target.path = target_path
    target.condition = condition
    return target


@dataclass(frozen=True)
class PlannedRecording:
    index: int
    scenario: Scenario
    source_id: str
    varied_condition: AudioCondition | None
    original: Recording | None
    source_dataset: Path
    recording: Recording
    path: Path


def _recording_destination(output_data: Path, recording: Recording) -> Path:
    """Only the output dataset's audio/ subtree is an approved WAV write root."""
    root = output_data.parent
    location = recording.path.expanduser()
    if location.is_absolute():
        try:
            location = location.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"Generated recording must be below {root / 'audio'}: {location}") from exc
    if not location.parts or location.parts[0] != "audio" or location.suffix.lower() != ".wav":
        raise ValueError(f"Generated recording must be a WAV below {root / 'audio'}: {location}")
    return artifact_path(root, location)


def _path_key(path: Path) -> str:
    return str(path.resolve()).casefold()


def _check_recording_ownership(plans: list[PlannedRecording], catalogs: list[tuple[Path, list[Scenario]]]) -> None:
    """Do not let --force or filename normalization steal another scenario's WAV."""
    owners: dict[str, set[str]] = {}
    for dataset_path, scenarios in catalogs:
        for scenario in scenarios:
            for recording in scenario.input.recordings:
                key = _path_key(resolve_recording_path(dataset_path, recording))
                owners.setdefault(key, set()).add(scenario.id)
    planned: dict[str, str] = {}
    for plan in plans:
        key = _path_key(plan.path)
        owner = plan.scenario.id
        if key in planned or owners.get(key, set()) - {owner}:
            raise ValueError(f"Recording destination collision for scenario {owner!r}: {plan.path}")
        if plan.path.exists() and owner not in owners.get(key, set()):
            raise ValueError(f"Recording destination has no matching scenario owner: {plan.path}")
        planned[key] = owner


async def generate(args: argparse.Namespace, client: AsyncOpenAI | None = None) -> int:
    """Create reusable WALK WAVs; evaluation always replays the saved recording."""
    dataset = load_scenario_dataset(args.data)
    scenarios = [
        scenario.model_copy(deep=True) for scenario in dataset.scenarios if scenario.interaction == "single_turn"
    ]
    if args.example != "all":
        scenarios = [scenario for scenario in scenarios if scenario.id == args.example]
        if not scenarios:
            raise ValueError(f"Unknown single-turn scenario: {args.example}")
    if not scenarios:
        raise ValueError("The scenario dataset does not contain any single-turn examples")
    selected_source_ids = {scenario.id for scenario in scenarios}

    if args.frame_ms <= 0:
        raise ValueError("--frame-ms must be greater than zero")
    default_realism = audio_realism_from_args(args)
    derived = (
        args.output_data is not None
        or is_installed_package_path(args.data)
        or args.condition is not None
        or args.vary_conditions
        or args.append
        or any(not scenario.input.recordings for scenario in scenarios)
    )
    output_data = require_external_output(_derived_dataset_path(args) if derived else args.data)
    source_payloads = {
        item["id"]: item
        for item in json.loads(args.data.expanduser().resolve().read_text(encoding="utf-8"))["scenarios"]
    }
    existing_payloads = (
        {item["id"]: item for item in json.loads(output_data.read_text(encoding="utf-8"))["scenarios"]}
        if derived and output_data.is_file()
        else {}
    )
    existing_scenarios = load_scenario_dataset(output_data).scenarios if derived and output_data.is_file() else []
    previous_recordings = {
        scenario.id: scenario.input.recordings[0]
        for scenario in existing_scenarios
        if len(scenario.input.recordings) == 1
    }
    plans: list[PlannedRecording] = []
    for index, scenario in enumerate(scenarios):
        source_id = scenario.id
        varied_condition: AudioCondition | None = (
            AUDIO_CONDITIONS[index % len(AUDIO_CONDITIONS)] if args.vary_conditions else None
        )
        if varied_condition is not None:
            scenario.id = validate_artifact_id(f"{source_id}_{varied_condition}")
        reusable_baseline = previous_recordings.get(source_id) if args.append else None
        originals = scenario.input.recordings or ([reusable_baseline] if reusable_baseline is not None else [None])
        if len(originals) != 1:
            raise ValueError(f"WALK requires exactly one recording per scenario: {scenario.id}")
        original = originals[0]
        condition: AudioCondition = (
            varied_condition
            if varied_condition is not None
            else args.condition or (original.condition if original is not None else "clean")
        )
        recording = _target_recording(
            scenario,
            original,
            condition=condition,
            derived=derived,
            profile_name=varied_condition,
        )
        scenario.input.recordings = [recording]
        plans.append(
            PlannedRecording(
                index,
                scenario,
                source_id,
                varied_condition,
                original,
                output_data if original is reusable_baseline else args.data,
                recording,
                _recording_destination(output_data, recording),
            )
        )

    # Validate all generated IDs, paths and preserved IDs before writes or paid TTS.
    generated_ids = {scenario.id for scenario in scenarios}
    retained = []
    obsolete_paths = []
    if args.append:
        for previous in existing_scenarios:
            generation = (
                previous.input.recordings[0].metadata.get("generation", {}) if previous.input.recordings else {}
            )
            replaced = previous.id in generated_ids or (
                args.vary_conditions and generation.get("source_scenario_id") in selected_source_ids
            )
            if not replaced:
                retained.append(previous)
            elif previous.id not in generated_ids:
                for recording in previous.input.recordings:
                    # Only delete the exact generated filename belonging to the retired scenario.
                    expected = Path("audio/conditioned") / f"{previous.id}.wav"
                    if recording.path == expected:
                        obsolete_paths.append(_recording_destination(output_data, recording))
    ScenarioDataset.model_validate(
        {
            "scenarios": [item.model_dump(mode="json") for item in [*retained, *scenarios]],
        }
    )
    _check_recording_ownership(plans, [(args.data, dataset.scenarios), (output_data, existing_scenarios)])
    protected_paths = {
        _path_key(resolve_recording_path(output_data, recording))
        for item in [*retained, *scenarios]
        for recording in item.input.recordings
    }
    protected_paths.update(
        _path_key(resolve_recording_path(args.data, recording))
        for item in dataset.scenarios
        for recording in item.input.recordings
    )
    obsolete_paths = [path for path in obsolete_paths if _path_key(path) not in protected_paths]
    if derived:
        artifact_path(output_data.parent, output_data.name)

    owned_client = False
    generated = 0
    try:
        for plan in plans:
            index, scenario = plan.index, plan.scenario
            source_id, varied_condition = plan.source_id, plan.varied_condition
            original, source_dataset = plan.original, plan.source_dataset
            recording, path = plan.recording, plan.path
            condition, realism = recording.condition, default_realism
            if path.is_file() and not args.force:
                previous = previous_recordings.get(scenario.id)
                if previous is not None and resolve_recording_path(output_data, previous) == path:
                    recording.metadata = previous.model_copy(deep=True).metadata
                print(f"EXISTS {scenario.id:16} {path}", flush=True)
                continue

            source = resolve_recording_path(source_dataset, original) if original is not None else None
            reusable_source = (
                source is not None
                and source.is_file()
                and source != path
                and (
                    original.condition == "clean" or (original.condition == condition and not realism.model_fields_set)
                )
            )
            if reusable_source:
                pcm = read_mono_wav(source, sample_rate_hz=DEFAULT_SAMPLE_RATE_HZ)
                source_kind = "existing_recording"
            else:
                if client is None:
                    if not os.getenv("OPENAI_API_KEY", "").strip():
                        raise ValueError("OPENAI_API_KEY is required to synthesize missing caller recordings")
                    client = AsyncOpenAI(timeout=45, max_retries=2)
                    owned_client = True
                response = await client.audio.speech.create(
                    model=args.model,
                    voice=args.voice,
                    input=scenario.input.text,
                    instructions="Speak naturally and conversationally, like a restaurant customer.",
                    response_format="pcm",
                )
                pcm = response.content
                if not pcm or len(pcm) % 2:
                    raise RuntimeError(f"TTS returned invalid PCM16 audio for {scenario.id}")
                source_kind = "synthetic_speech"

            if reusable_source and original.condition == condition and condition != "clean":
                conditioned = pcm
                previous_generation = original.metadata.get("generation")
                realism_metadata = (
                    previous_generation.get("audio_realism", {}) if isinstance(previous_generation, dict) else {}
                )
            else:
                conditioned, realism_metadata = _condition_audio(
                    pcm,
                    condition=condition,
                    seed=args.seed + index if varied_condition is not None else args.seed,
                    frame_ms=args.frame_ms,
                    realism=realism,
                )

            if derived or condition != "clean" or realism.model_fields_set:
                generation: dict[str, Any] = {
                    "source": source_kind,
                    "audio_realism": realism_metadata,
                }
                if source_kind == "synthetic_speech":
                    generation["tts_model"] = args.model
                    generation["tts_voice"] = args.voice
                if varied_condition is not None:
                    generation["source_scenario_id"] = source_id
                recording.metadata["generation"] = generation

            write_mono_wav(_recording_destination(output_data, recording), conditioned, DEFAULT_SAMPLE_RATE_HZ)
            seconds = len(conditioned) / (DEFAULT_SAMPLE_RATE_HZ * 2)
            print(f"CREATED {scenario.id:16} {condition:17} {seconds:5.2f}s {path}", flush=True)
            generated += 1

        if derived:
            private_directory(output_data.parent)
            preserved = []
            for previous in retained:
                previous_payload = existing_payloads[previous.id]
                preserved_payload = deepcopy(source_payloads.get(previous.id, previous_payload))
                preserved_payload["input"]["recordings"] = previous_payload["input"]["recordings"]
                preserved.append(preserved_payload)

            generated_payloads = []
            for scenario in scenarios:
                recording = scenario.input.recordings[0]
                generation = recording.metadata.get("generation", {})
                source_id = generation.get("source_scenario_id", scenario.id)
                scenario_payload = deepcopy(source_payloads[source_id])
                scenario_payload["id"] = scenario.id
                scenario_payload["input"]["recordings"] = [recording.model_dump(mode="json", exclude_none=True)]
                generated_payloads.append(scenario_payload)

            payload = {"schema_version": dataset.schema_version, "scenarios": [*preserved, *generated_payloads]}
            private_write_text(
                artifact_path(output_data.parent, output_data.name),
                json.dumps(payload, indent=2) + "\n",
                encoding="utf-8",
            )
            for path in obsolete_paths:
                artifact_path(output_data.parent, path.relative_to(output_data.parent)).unlink(missing_ok=True)
            print(f"DATASET {output_data}", flush=True)
    finally:
        if owned_client and client is not None:
            await client.close()
    return generated


def main(argv: Sequence[str] | None = None) -> None:
    try:
        count = asyncio.run(generate(parse_args(argv)))
        print(f"Generated {count} recording{'s' if count != 1 else ''}.", flush=True)
    except (KeyboardInterrupt, asyncio.CancelledError):
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()
