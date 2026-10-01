"""Small, portable run report shared by CRAWL, WALK, and RUN."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from math import isfinite
from pathlib import Path
from statistics import fmean
from typing import Any

from shared.private_files import private_directory, private_write_text
from shared.reporting.schema import SCHEMA_VERSION

TASK_METRICS = (
    "task_completed",
    "semantic_quality",
    "tool_accuracy",
    "tool_calls",
    "delegation_accuracy",
    "delegations",
    "turns",
)
AUDIO_METRICS = (
    "response_rate",
    "response_latency_ms",
    "interruption_rate",
    "speaking_duration_ms",
    "floor_hold_silence_ms",
)

ARTIFACT_FIELDS = {
    "input_audio_path": "input_audio",
    "output_audio_path": "output_audio",
    "conversation_audio_path": "conversation_audio",
    "conversation_transcript_path": "conversation_transcript",
    "event_log_path": "events",
    "transcript_path": "details",
    "result_path": "details",
}


def _count_pair(value: Any) -> dict[str, int] | None:
    if isinstance(value, Mapping):
        actual = value.get("actual")
        expected = value.get("expected")
        if isinstance(actual, int) and isinstance(expected, int):
            return {"actual": actual, "expected": expected}
    if isinstance(value, str) and "/" in value:
        actual, expected = value.split("/", maxsplit=1)
        try:
            return {"actual": int(actual), "expected": int(expected)}
        except ValueError:
            return None
    return None


def _optional_int(row: Mapping[str, Any], key: str) -> int | None:
    value = row.get(key)
    if isinstance(value, bool) or value is None or value == "":
        return None
    return int(value)


def _usage_source(row: Mapping[str, Any], prefix: str) -> dict[str, Any]:
    total_tokens = _optional_int(row, f"{prefix}_total_tokens")
    input_tokens = {
        "total_tokens": _optional_int(row, f"{prefix}_input_tokens"),
        "cached_tokens": _optional_int(row, f"{prefix}_cached_input_tokens"),
        "cache_write_tokens": _optional_int(row, f"{prefix}_cache_write_input_tokens"),
        "text_tokens": _optional_int(row, f"{prefix}_input_text_tokens"),
        "audio_tokens": _optional_int(row, f"{prefix}_input_audio_tokens"),
        "image_tokens": _optional_int(row, f"{prefix}_input_image_tokens"),
    }
    output_tokens = {
        "total_tokens": _optional_int(row, f"{prefix}_output_tokens"),
        "cached_tokens": _optional_int(row, f"{prefix}_cached_output_tokens"),
        "text_tokens": _optional_int(row, f"{prefix}_output_text_tokens"),
        "audio_tokens": _optional_int(row, f"{prefix}_output_audio_tokens"),
        "image_tokens": _optional_int(row, f"{prefix}_output_image_tokens"),
        "reasoning_tokens": _optional_int(row, f"{prefix}_output_reasoning_tokens"),
    }
    usage: dict[str, Any] = {}
    if total_tokens is not None:
        usage["total_tokens"] = total_tokens
    if observed_input := {key: value for key, value in input_tokens.items() if value is not None}:
        usage["input"] = observed_input
    if observed_output := {key: value for key, value in output_tokens.items() if value is not None}:
        usage["output"] = observed_output
    if prefix == "frontend":
        if (duration := _optional_int(row, "frontend_audio_duration_ms")) is not None:
            usage["audio_duration_ms"] = duration
    elif prefix == "backend":
        models = row.get("backend_model_usage")
        observed_models = (
            [dict(model) for model in models if isinstance(model, Mapping)] if isinstance(models, list) else []
        )
        if len(observed_models) > 1:
            usage["models"] = observed_models
    return usage


def _artifact_path(value: Any, run_dir: Path) -> str | None:
    if not value:
        return None
    path = Path(str(value))
    try:
        return str(path.resolve().relative_to(run_dir.resolve()))
    except ValueError:
        return str(path)


def _status(row: Mapping[str, Any]) -> str:
    raw_status = str(row.get("status", ""))
    if raw_status in {"infrastructure_error", "failed"} and row.get("failure_stage"):
        return "infrastructure_error"
    return "passed" if bool(row.get("task_completed")) else "failed"


def _semantic_quality(row: Mapping[str, Any]) -> dict[str, Any]:
    """Attach assessed semantic dimensions to task metrics without inventing offline grades."""
    raw = row.get("semantic_dimension_scores")
    dimensions: dict[str, float] = {}
    if isinstance(raw, Mapping):
        for name, score in raw.items():
            if not isinstance(score, int | float) or isinstance(score, bool):
                continue
            numeric = float(score)
            if not isfinite(numeric) or not 0.0 <= numeric <= 1.0:
                raise ValueError(f"Semantic quality score for {name!r} must be between 0 and 1")
            dimensions[str(name)] = round(numeric, 4)
    return {
        "score": round(fmean(dimensions.values()), 4) if dimensions else None,
        "dimensions": dimensions,
    }


def build_result_item(
    row: Mapping[str, Any],
    *,
    run_dir: Path,
    scenario_id_key: str,
    title_key: str | None = None,
) -> dict[str, Any]:
    """Project one internal result row into the stable customer-facing schema."""
    task = {key: row.get(key) for key in TASK_METRICS}
    task["task_completed"] = bool(task["task_completed"])
    task["semantic_quality"] = _semantic_quality(row)
    task["tool_calls"] = _count_pair(task["tool_calls"])
    task["delegations"] = _count_pair(task["delegations"])
    task["turns"] = _count_pair(task["turns"])

    artifacts: dict[str, str] = {}
    for source, target in ARTIFACT_FIELDS.items():
        if path := _artifact_path(row.get(source), run_dir):
            artifacts[target] = path

    failure_stage = str(row.get("failure_stage", ""))
    error_message = str(row.get("error_message", ""))
    error = {"stage": failure_stage or "unknown", "message": error_message} if failure_stage or error_message else None
    item: dict[str, Any] = {
        "scenario_id": str(row.get(scenario_id_key, "")),
        "status": _status(row),
        "metrics": {
            "task": task,
            "audio": {key: row.get(key) for key in AUDIO_METRICS},
            "consumption": {
                "frontend": _usage_source(row, "frontend"),
                "backend": _usage_source(row, "backend"),
            },
        },
        "artifacts": artifacts,
        "error": error,
    }
    if title_key and row.get(title_key):
        item["title"] = str(row[title_key])
    if isinstance(row.get("recording"), Mapping):
        item["recording"] = dict(row["recording"])
    if isinstance(row.get("assessment"), Mapping):
        item["assessment"] = dict(row["assessment"])
    if isinstance(row.get("observability"), Mapping):
        item["observability"] = dict(row["observability"])
    if isinstance(row.get("validity"), Mapping) and row["validity"]:
        item["validity"] = dict(row["validity"])
    if row.get("metrics_version"):
        # Keep the denominator/policy beside the rate in the portable report;
        # users should not need a debug-only artifact to interpret a percentage.
        item["metrics"]["audio"].update(
            {
                "metrics_version": row["metrics_version"],
                "response_deadline_ms": row.get("response_deadline_ms"),
                "response_opportunities": dict(row.get("response_opportunities", {})),
                "response_exclusion_reasons": dict(row.get("response_exclusion_reasons", {})),
            }
        )
    return item


def build_results_report(
    *,
    module: str,
    run_name: str,
    execution_mode: str,
    interaction: str,
    dataset: Path,
    configuration: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    run_dir: Path,
    scenario_id_key: str,
    title_key: str | None = None,
) -> dict[str, Any]:
    """Build one run-level JSON document without derived percentiles."""
    results = [
        build_result_item(
            row,
            run_dir=run_dir,
            scenario_id_key=scenario_id_key,
            title_key=title_key,
        )
        for row in rows
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "run": {
            "id": run_name,
            "module": module,
            "execution_mode": execution_mode,
            "interaction": interaction,
            "dataset": str(dataset.resolve()),
            "configuration": dict(configuration),
        },
        "summary": {
            "total": len(results),
            "passed": sum(item["status"] == "passed" for item in results),
            "failed": sum(item["status"] == "failed" for item in results),
            "infrastructure_errors": sum(item["status"] == "infrastructure_error" for item in results),
        },
        "results": results,
    }


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    """Persist one human-readable, UTF-8 encoded evaluation result."""
    private_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def build_timestamped_run_name(
    *,
    phase: str,
    offline: bool,
    label: str = "",
    timestamp: datetime | None = None,
) -> str:
    """Build a readable, UTC-stamped run name without unsafe path components."""
    prefix = label.strip() or f"{phase}_{'offline' if offline else 'live'}"
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", prefix) is None:
        raise ValueError("Run names must use only letters, digits, periods, hyphens, and underscores")

    instant = datetime.now(UTC) if timestamp is None else timestamp
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("Run timestamps must include a timezone")
    instant = instant.astimezone(UTC)
    return f"{prefix}_{instant:%Y%m%d_%H%M%S}_{instant.microsecond // 1_000:03d}Z"


def ensure_dir(path: Path) -> Path:
    private_directory(path)
    return path
