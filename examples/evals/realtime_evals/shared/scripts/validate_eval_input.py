from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Mapping

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from crawl_harness.run_realtime_evals import load_dataset as load_crawl_dataset
from run_harness.run_realtime_evals import (
    load_simulation,
    load_simulation_index,
    resolve_path,
)
from walk_harness.run_realtime_evals import (
    load_dataset as load_walk_dataset,
    read_ulaw_wav,
)

DEFAULT_INPUT_PATHS = {
    "crawl": ROOT_DIR / "crawl_harness" / "data" / "customer_service_synthetic.csv",
    "walk": ROOT_DIR / "walk_harness" / "data" / "customer_service_synthetic.csv",
    "run": ROOT_DIR / "run_harness" / "data" / "simulations.csv",
}
EXPECTED_WALK_SAMPLE_RATE_HZ = 8000


def _json_object_from_text(text: str, *, context: str) -> Mapping[str, object]:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{context} is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"{context} must be a JSON object.")
    return parsed


def _coerce_mapping(
    value: object,
    *,
    field_name: str,
    source_path: Path,
) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"`{field_name}` in {source_path} must be an object.")
    return value


def _require_non_empty_string(
    value: object,
    *,
    field_name: str,
    source_path: Path,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"`{field_name}` in {source_path} must be a non-empty string.")
    return value.strip()


def _grader_type(
    grader: Mapping[str, object],
    *,
    field_name: str,
    source_path: Path,
) -> str:
    value = grader.get("type", "")
    if not isinstance(value, str):
        raise ValueError(f"`{field_name}` in {source_path} must be a string.")
    normalized = value.strip()
    return normalized or "llm_as_judge"


def _validate_expected_tool_arg_json(dataset: pd.DataFrame, data_path: Path) -> None:
    for row_index, row in dataset.iterrows():
        argument_value = row.get("gt_tool_call_arg", "")
        if pd.isna(argument_value):
            continue
        argument_text = str(argument_value).strip()
        if not argument_text:
            continue
        _json_object_from_text(
            argument_text,
            context=f"`gt_tool_call_arg` in row {row_index + 2} of {data_path}",
        )


def validate_crawl_input(data_path: Path) -> None:
    dataset = load_crawl_dataset(data_path)
    _validate_expected_tool_arg_json(dataset, data_path)


def validate_walk_input(data_path: Path) -> None:
    dataset = load_walk_dataset(data_path)
    _validate_expected_tool_arg_json(dataset, data_path)
    for row_index, row in dataset.iterrows():
        audio_path_value = str(row.get("audio_path", "")).strip()
        if not audio_path_value:
            raise ValueError(
                f"`audio_path` in row {row_index + 2} of {data_path} must be non-empty."
            )
        audio_path = resolve_path(audio_path_value, data_path.parent)
        if not audio_path.exists():
            raise ValueError(f"Audio file does not exist: {audio_path}")
        read_ulaw_wav(audio_path, EXPECTED_WALK_SAMPLE_RATE_HZ)


def _validate_run_simulation_file(
    simulation_path: Path,
    *,
    expected_simulation_id: str,
) -> None:
    simulation = load_simulation(simulation_path)
    if not isinstance(simulation, dict):
        raise ValueError(f"Simulation file must contain an object: {simulation_path}")

    simulation_id = str(simulation.get("simulation_id", "")).strip()
    if simulation_id and simulation_id != expected_simulation_id:
        raise ValueError(
            f"`simulation_id` mismatch in {simulation_path}: "
            f"expected `{expected_simulation_id}`, found `{simulation_id}`."
        )

    _require_non_empty_string(
        simulation.get("scenario", ""),
        field_name="scenario",
        source_path=simulation_path,
    )

    assistant_config = _coerce_mapping(
        simulation.get("assistant", {}),
        field_name="assistant",
        source_path=simulation_path,
    )
    prompt_path = resolve_path(
        _require_non_empty_string(
            assistant_config.get("system_prompt_file", ""),
            field_name="assistant.system_prompt_file",
            source_path=simulation_path,
        ),
        ROOT_DIR,
    )
    if not prompt_path.exists():
        raise ValueError(f"Assistant system prompt file does not exist: {prompt_path}")

    tools_path = resolve_path(
        _require_non_empty_string(
            assistant_config.get("tools_file", ""),
            field_name="assistant.tools_file",
            source_path=simulation_path,
        ),
        ROOT_DIR,
    )
    if not tools_path.exists():
        raise ValueError(f"Assistant tools file does not exist: {tools_path}")

    simulator_config = _coerce_mapping(
        simulation.get("simulator", {}),
        field_name="simulator",
        source_path=simulation_path,
    )
    _require_non_empty_string(
        simulator_config.get("system_prompt", ""),
        field_name="simulator.system_prompt",
        source_path=simulation_path,
    )

    _coerce_mapping(
        simulation.get("audio", {}),
        field_name="audio",
        source_path=simulation_path,
    )
    turns_config = _coerce_mapping(
        simulation.get("turns", {}),
        field_name="turns",
        source_path=simulation_path,
    )
    _require_non_empty_string(
        turns_config.get("fixed_first_user_turn", ""),
        field_name="turns.fixed_first_user_turn",
        source_path=simulation_path,
    )

    tool_mocks = simulation.get("tool_mocks", [])
    if not isinstance(tool_mocks, list):
        raise ValueError(f"`tool_mocks` in {simulation_path} must be a list.")
    for entry_index, tool_mock in enumerate(tool_mocks, start=1):
        tool_mock_mapping = _coerce_mapping(
            tool_mock,
            field_name=f"tool_mocks[{entry_index}]",
            source_path=simulation_path,
        )
        _require_non_empty_string(
            tool_mock_mapping.get("name", ""),
            field_name=f"tool_mocks[{entry_index}].name",
            source_path=simulation_path,
        )
        _coerce_mapping(
            tool_mock_mapping.get("output", {}),
            field_name=f"tool_mocks[{entry_index}].output",
            source_path=simulation_path,
        )

    expected_tool_call = _coerce_mapping(
        simulation.get("expected_tool_call", {}),
        field_name="expected_tool_call",
        source_path=simulation_path,
    )
    arguments = expected_tool_call.get("arguments", {})
    if arguments not in ({}, None) and not isinstance(arguments, dict):
        raise ValueError(
            f"`expected_tool_call.arguments` in {simulation_path} must be an object."
        )

    graders = _coerce_mapping(
        simulation.get("graders", {}),
        field_name="graders",
        source_path=simulation_path,
    )
    for level_name in ("turn_level", "trace_level"):
        level_value = graders.get(level_name, [])
        if not isinstance(level_value, list):
            raise ValueError(f"`graders.{level_name}` in {simulation_path} must be a list.")
        for grader_index, grader in enumerate(level_value, start=1):
            grader_mapping = _coerce_mapping(
                grader,
                field_name=f"graders.{level_name}[{grader_index}]",
                source_path=simulation_path,
            )
            _require_non_empty_string(
                grader_mapping.get("id", ""),
                field_name=f"graders.{level_name}[{grader_index}].id",
                source_path=simulation_path,
            )
            grader_type = _grader_type(
                grader_mapping,
                field_name=f"graders.{level_name}[{grader_index}].type",
                source_path=simulation_path,
            )
            if grader_type == "llm_as_judge":
                _require_non_empty_string(
                    grader_mapping.get("criteria", ""),
                    field_name=f"graders.{level_name}[{grader_index}].criteria",
                    source_path=simulation_path,
                )


def validate_run_input(data_path: Path) -> None:
    simulation_index = load_simulation_index(data_path)
    if simulation_index["simulation_id"].duplicated().any():
        raise ValueError(f"`simulation_id` values must be unique in {data_path}.")

    for row_index, row in simulation_index.iterrows():
        simulation_id = str(row["simulation_id"]).strip()
        simulation_path = resolve_path(str(row["simulation_path"]), data_path.parent)
        if not simulation_path.exists():
            raise ValueError(
                f"`simulation_path` in row {row_index + 2} of {data_path} does not exist: "
                f"{simulation_path}"
            )
        _validate_run_simulation_file(
            simulation_path,
            expected_simulation_id=simulation_id,
        )


def validate_input(harness: str, data_path: Path) -> None:
    if harness == "crawl":
        validate_crawl_input(data_path)
    elif harness == "walk":
        validate_walk_input(data_path)
    elif harness == "run":
        validate_run_input(data_path)
    else:
        raise ValueError(f"Unsupported harness: {harness}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate the input contract for a realtime eval harness."
    )
    parser.add_argument(
        "--harness",
        choices=sorted(DEFAULT_INPUT_PATHS),
        required=True,
        help="Harness whose input contract should be validated.",
    )
    parser.add_argument(
        "--data-path",
        type=Path,
        default=None,
        help="Override the default dataset/simulation index path for the harness.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data_path = (args.data_path or DEFAULT_INPUT_PATHS[args.harness]).resolve()
    validate_input(args.harness, data_path)
    print(f"Validated {args.harness} input: {data_path}")


if __name__ == "__main__":
    main()
