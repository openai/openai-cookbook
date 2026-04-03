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

from shared.result_types import (
    CrawlEvalRunConfig,
    CrawlEvalRunSummary,
    NumericMetricSummary,
    RunEvalRunConfig,
    RunEvalRunSummary,
    WalkEvalRunConfig,
    WalkEvalRunSummary,
)

DEFAULT_RESULTS_DIRS = {
    "crawl": ROOT_DIR / "crawl_harness" / "results",
    "walk": ROOT_DIR / "walk_harness" / "results",
    "run": ROOT_DIR / "run_harness" / "results",
}


def _load_summary(summary_path: Path) -> Mapping[str, object]:
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"`summary.json` must contain an object: {summary_path}")
    return payload


def _required_string(summary: Mapping[str, object], key: str, summary_path: Path) -> str:
    value = summary.get(key, "")
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"`{key}` is required in {summary_path}.")
    return value


def _string_value(
    summary: Mapping[str, object],
    key: str,
    summary_path: Path,
    *,
    allow_empty: bool = False,
) -> str:
    value = summary.get(key, "")
    if not isinstance(value, str):
        raise ValueError(f"`{key}` must be a string in {summary_path}.")
    if not allow_empty and not value.strip():
        raise ValueError(f"`{key}` is required in {summary_path}.")
    return value


def _required_intish(summary: Mapping[str, object], key: str, summary_path: Path) -> int:
    try:
        return int(summary.get(key, 0))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"`{key}` must be an integer in {summary_path}.") from exc


def _required_bool(summary: Mapping[str, object], key: str, summary_path: Path) -> bool:
    value = summary.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1"}:
            return True
        if normalized in {"false", "0"}:
            return False
    raise ValueError(f"`{key}` must be a boolean in {summary_path}.")


def _load_results(results_path: Path) -> pd.DataFrame:
    return pd.read_csv(results_path, keep_default_na=False)


def _path_from_value(path_value: object, *, field_name: str, row_number: int) -> Path:
    text = str(path_value).strip()
    if not text:
        raise ValueError(f"`{field_name}` is required in results row {row_number}.")
    return Path(text)


def _parse_json_list(cell_value: object, *, field_name: str, row_number: int) -> list[object]:
    text = str(cell_value).strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"`{field_name}` in results row {row_number} is not valid JSON."
        ) from exc
    if not isinstance(parsed, list):
        raise ValueError(f"`{field_name}` in results row {row_number} must be a JSON list.")
    return parsed


def _optional_existing_path(
    path_value: object,
    *,
    row_status: str,
    field_name: str,
    row_number: int,
) -> None:
    text = str(path_value).strip()
    if not text:
        return
    path = Path(text)
    if row_status != "failed" and not path.exists():
        raise ValueError(
            f"`{field_name}` in results row {row_number} points to a missing file: {path}"
        )


def _validate_numeric_summary(
    summary: Mapping[str, object],
    prefix: str,
    *,
    summary_path: Path,
) -> NumericMetricSummary | None:
    return NumericMetricSummary.from_flat_summary(summary, prefix)


def _validate_crawl_results(results: pd.DataFrame, results_path: Path) -> None:
    required_columns = {
        "example_id",
        "user_text",
        "assistant_text",
        "tool_calls",
        "input_audio_path",
        "event_log_path",
        "status",
    }
    missing = required_columns.difference(results.columns)
    if missing:
        raise ValueError(f"Missing required columns in {results_path}: {sorted(missing)}")

    for row_index, row in results.iterrows():
        row_number = row_index + 2
        row_status = str(row.get("status", "")).strip()
        _parse_json_list(row.get("tool_calls", "[]"), field_name="tool_calls", row_number=row_number)
        _optional_existing_path(
            row.get("input_audio_path", ""),
            row_status=row_status,
            field_name="input_audio_path",
            row_number=row_number,
        )
        _optional_existing_path(
            row.get("output_audio_path", ""),
            row_status=row_status,
            field_name="output_audio_path",
            row_number=row_number,
        )
        _optional_existing_path(
            row.get("event_log_path", ""),
            row_status=row_status,
            field_name="event_log_path",
            row_number=row_number,
        )


def _validate_walk_results(results: pd.DataFrame, results_path: Path) -> None:
    required_columns = {
        "example_id",
        "user_text",
        "assistant_text",
        "tool_calls",
        "audio_path",
        "event_log_path",
        "status",
    }
    missing = required_columns.difference(results.columns)
    if missing:
        raise ValueError(f"Missing required columns in {results_path}: {sorted(missing)}")

    for row_index, row in results.iterrows():
        row_number = row_index + 2
        row_status = str(row.get("status", "")).strip()
        _parse_json_list(row.get("tool_calls", "[]"), field_name="tool_calls", row_number=row_number)
        _optional_existing_path(
            row.get("audio_path", ""),
            row_status="ok",
            field_name="audio_path",
            row_number=row_number,
        )
        _optional_existing_path(
            row.get("output_audio_path", ""),
            row_status=row_status,
            field_name="output_audio_path",
            row_number=row_number,
        )
        _optional_existing_path(
            row.get("event_log_path", ""),
            row_status=row_status,
            field_name="event_log_path",
            row_number=row_number,
        )


def _validate_run_results(results: pd.DataFrame, results_path: Path) -> None:
    required_columns = {
        "simulation_id",
        "assistant_model",
        "simulator_model",
        "turn_index",
        "user_text",
        "assistant_text",
        "tool_calls",
        "tool_outputs",
        "user_audio_path",
        "assistant_audio_path",
        "event_log_path",
        "status",
    }
    missing = required_columns.difference(results.columns)
    if missing:
        raise ValueError(f"Missing required columns in {results_path}: {sorted(missing)}")

    for row_index, row in results.iterrows():
        row_number = row_index + 2
        row_status = str(row.get("status", "")).strip()
        try:
            int(row.get("turn_index", ""))
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"`turn_index` in results row {row_number} must be an integer."
            ) from exc
        _parse_json_list(row.get("tool_calls", "[]"), field_name="tool_calls", row_number=row_number)
        _parse_json_list(
            row.get("tool_outputs", "[]"),
            field_name="tool_outputs",
            row_number=row_number,
        )
        _optional_existing_path(
            row.get("user_audio_path", ""),
            row_status=row_status,
            field_name="user_audio_path",
            row_number=row_number,
        )
        _optional_existing_path(
            row.get("assistant_audio_path", ""),
            row_status=row_status,
            field_name="assistant_audio_path",
            row_number=row_number,
        )
        _optional_existing_path(
            row.get("event_log_path", ""),
            row_status=row_status,
            field_name="event_log_path",
            row_number=row_number,
        )


def _validate_dynamic_grade_means(
    results: pd.DataFrame,
    summary: Mapping[str, object],
    *,
    summary_path: Path,
) -> None:
    for grade_column in sorted(
        column for column in results.columns if column.endswith("_grade")
    ):
        mean_key = f"{grade_column}_mean"
        if mean_key not in summary:
            raise ValueError(
                f"Missing `{mean_key}` in {summary_path} for results column `{grade_column}`."
            )


def _build_crawl_config(
    summary: Mapping[str, object], summary_path: Path
) -> CrawlEvalRunConfig:
    return CrawlEvalRunConfig(
        run_name=_required_string(summary, "run_name", summary_path),
        model=_required_string(summary, "model", summary_path),
        tts_model=_required_string(summary, "tts_model", summary_path),
        voice=_required_string(summary, "voice", summary_path),
        chunk_ms=_required_intish(summary, "chunk_ms", summary_path),
        sample_rate_hz=_required_intish(summary, "sample_rate_hz", summary_path),
        input_audio_format=_required_string(summary, "input_audio_format", summary_path),
        output_audio_format=_required_string(
            summary, "output_audio_format", summary_path
        ),
        real_time=_required_bool(summary, "real_time", summary_path),
        data_csv=_path_from_value(summary.get("data_csv", ""), field_name="data_csv", row_number=1),
        system_prompt_file=_path_from_value(
            summary.get("system_prompt_file", ""),
            field_name="system_prompt_file",
            row_number=1,
        ),
        tools_file=_path_from_value(summary.get("tools_file", ""), field_name="tools_file", row_number=1),
    )


def _build_walk_config(summary: Mapping[str, object], summary_path: Path) -> WalkEvalRunConfig:
    return WalkEvalRunConfig(
        run_name=_required_string(summary, "run_name", summary_path),
        model=_required_string(summary, "model", summary_path),
        voice=_required_string(summary, "voice", summary_path),
        chunk_ms=_required_intish(summary, "chunk_ms", summary_path),
        sample_rate_hz=_required_intish(summary, "sample_rate_hz", summary_path),
        input_audio_format=_required_string(summary, "input_audio_format", summary_path),
        output_audio_format=_required_string(
            summary, "output_audio_format", summary_path
        ),
        output_sample_rate_hz=_required_intish(
            summary, "output_sample_rate_hz", summary_path
        ),
        real_time=_required_bool(summary, "real_time", summary_path),
        data_csv=_path_from_value(summary.get("data_csv", ""), field_name="data_csv", row_number=1),
        system_prompt_file=_path_from_value(
            summary.get("system_prompt_file", ""),
            field_name="system_prompt_file",
            row_number=1,
        ),
        tools_file=_path_from_value(summary.get("tools_file", ""), field_name="tools_file", row_number=1),
    )


def _build_run_config(summary: Mapping[str, object], summary_path: Path) -> RunEvalRunConfig:
    return RunEvalRunConfig(
        run_name=_required_string(summary, "run_name", summary_path),
        assistant_model_default=_string_value(
            summary,
            "assistant_model_default",
            summary_path,
            allow_empty=True,
        ),
        simulator_model_default=_string_value(
            summary,
            "simulator_model_default",
            summary_path,
            allow_empty=True,
        ),
        input_audio_format=_required_string(summary, "input_audio_format", summary_path),
        output_audio_format=_required_string(
            summary, "output_audio_format", summary_path
        ),
        chunk_ms=_required_intish(summary, "chunk_ms", summary_path),
        sample_rate_hz=_required_intish(summary, "sample_rate_hz", summary_path),
        real_time=_required_bool(summary, "real_time", summary_path),
        data_csv=_path_from_value(summary.get("data_csv", ""), field_name="data_csv", row_number=1),
    )


def _validate_crawl_summary(summary: Mapping[str, object], summary_path: Path) -> None:
    parsed_summary = CrawlEvalRunSummary.from_flat_summary(
        summary,
        _build_crawl_config(summary, summary_path),
    )
    if parsed_summary.total_examples < parsed_summary.failed_examples:
        raise ValueError(f"`failed_examples` cannot exceed `total_examples` in {summary_path}.")
    _validate_numeric_summary(summary, "latency_first_audio_ms", summary_path=summary_path)


def _validate_walk_summary(summary: Mapping[str, object], summary_path: Path) -> None:
    parsed_summary = WalkEvalRunSummary.from_flat_summary(
        summary,
        _build_walk_config(summary, summary_path),
    )
    if parsed_summary.total_examples < parsed_summary.failed_examples:
        raise ValueError(f"`failed_examples` cannot exceed `total_examples` in {summary_path}.")
    _validate_numeric_summary(summary, "latency_first_audio_ms", summary_path=summary_path)


def _validate_run_summary(summary: Mapping[str, object], summary_path: Path) -> None:
    parsed_summary = RunEvalRunSummary.from_flat_summary(
        summary,
        _build_run_config(summary, summary_path),
    )
    if parsed_summary.total_rows < parsed_summary.failed_simulations:
        raise ValueError(f"`failed_simulations` cannot exceed `total_rows` in {summary_path}.")
    _validate_numeric_summary(summary, "latency_response_done_ms", summary_path=summary_path)


def latest_run_dir(harness: str) -> Path:
    results_root = DEFAULT_RESULTS_DIRS[harness]
    candidates = [path for path in results_root.iterdir() if path.is_dir()]
    if not candidates:
        raise ValueError(f"No runs found under {results_root}")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def validate_output(harness: str, run_dir: Path) -> None:
    results_path = run_dir / "results.csv"
    summary_path = run_dir / "summary.json"
    if not results_path.exists():
        raise ValueError(f"Missing results file: {results_path}")
    if not summary_path.exists():
        raise ValueError(f"Missing summary file: {summary_path}")

    results = _load_results(results_path)
    summary = _load_summary(summary_path)

    if harness == "crawl":
        _validate_crawl_results(results, results_path)
        _validate_crawl_summary(summary, summary_path)
    elif harness == "walk":
        _validate_walk_results(results, results_path)
        _validate_walk_summary(summary, summary_path)
    elif harness == "run":
        _validate_run_results(results, results_path)
        _validate_dynamic_grade_means(results, summary, summary_path=summary_path)
        _validate_run_summary(summary, summary_path)
    else:
        raise ValueError(f"Unsupported harness: {harness}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the on-disk output data contract consumed by the realtime "
            "eval results viewer."
        )
    )
    parser.add_argument(
        "--harness",
        choices=sorted(DEFAULT_RESULTS_DIRS),
        required=True,
        help="Harness whose results-app output contract should be validated.",
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=None,
        help="Override the run directory to validate. Defaults to the latest run for the harness.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_dir = (args.run_dir or latest_run_dir(args.harness)).resolve()
    validate_output(args.harness, run_dir)
    print(f"Validated {args.harness} output: {run_dir}")


if __name__ == "__main__":
    main()
