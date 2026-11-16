"""Atomic assistant measurements derived from observable evaluation evidence."""

from __future__ import annotations

from typing import Any


def _score(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    return max(0.0, min(1.0, float(value)))


def _tool_accuracy(
    task: dict[str, Any],
    efficiency: dict[str, Any],
    golden: dict[str, Any],
) -> float:
    """Measure expected tool selection, arguments, and prohibited calls."""
    expected = sum(max(0, int(item.get("count", 1))) for item in golden.get("tool_calls", []))
    actual = max(0, int(efficiency.get("unique_tool_invocation_count", 0)))
    matched_value = efficiency.get("matched_tool_call_count", task.get("matched_tool_call_count"))
    if matched_value is None:
        coverage = _score(task.get("tool_call_coverage"))
        matched = round(expected * coverage) if coverage is not None else 0
    else:
        matched = max(0, int(matched_value))
    matched = min(matched, expected, actual)

    if int(task.get("prohibited_tool_call_count", 0)):
        return 0.0
    if expected == 0:
        return float(actual == 0)
    return round(matched / max(expected, actual), 4)


def evidence_scores(
    task: dict[str, Any],
    efficiency: dict[str, Any],
    golden: dict[str, Any],
) -> dict[str, float | None]:
    """Return deterministic task evidence without transforming audio metrics."""
    actual = max(0, int(efficiency.get("delegation_count", int(bool(task.get("delegation_observed"))))))
    delegated = actual > 0
    policy = golden.get("delegation_policy")
    required = bool(task.get("delegation_required")) or policy == "required"
    forbidden = bool(task.get("delegation_prohibited")) or policy == "forbidden"
    if policy is None and not required and not forbidden:
        required = int(golden.get("delegations", 0)) > 0
    delegation_accuracy = float((not required or delegated) and not (forbidden and delegated))
    return {
        "tool_accuracy": _tool_accuracy(task, efficiency, golden),
        "delegation_accuracy": delegation_accuracy,
    }
