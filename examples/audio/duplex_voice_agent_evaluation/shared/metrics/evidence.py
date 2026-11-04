"""Atomic assistant measurements derived from observable evaluation evidence."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any


def _score(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value) if math.isfinite(value) and 0 <= value <= 1 else None


def optional_count(value: Any) -> int | None:
    """Keep unavailable observations distinct from an explicitly observed zero."""
    return value if type(value) is int and value >= 0 else None


def expected_tool_count(golden: dict[str, Any]) -> int | None:
    """An explicit empty expectation is zero; no expectation is unknown."""
    tools = golden.get("tool_calls")
    if not isinstance(tools, list | tuple) or any(not isinstance(item, Mapping) for item in tools):
        return None
    counts = [optional_count(item.get("count", 1)) for item in tools]
    if any(count is None for count in counts):
        return None
    return sum(count for count in counts if count is not None)


def _tool_accuracy(
    task: dict[str, Any],
    efficiency: dict[str, Any],
    golden: dict[str, Any],
) -> float | None:
    """Measure expected tool selection, arguments, and prohibited calls."""
    prohibited = optional_count(task.get("prohibited_tool_call_count", 0))
    if prohibited:
        return 0.0
    expected = expected_tool_count(golden)
    actual = optional_count(efficiency.get("unique_tool_invocation_count"))
    if expected is None or actual is None:
        return None
    if actual == 0 or expected == 0:
        score = float(actual == expected)
        return None if score and prohibited is None else score
    matched = optional_count(efficiency.get("matched_tool_call_count", task.get("matched_tool_call_count")))
    if matched is None:
        coverage = _score(task.get("tool_call_coverage"))
        if coverage is None:
            return None
        matched = round(expected * coverage)
    matched = min(matched, expected, actual)
    score = round(matched / max(expected, actual), 4)
    return None if score and prohibited is None else score


def evidence_scores(
    task: dict[str, Any],
    efficiency: dict[str, Any],
    golden: dict[str, Any],
) -> dict[str, float | None]:
    """Return deterministic task evidence without transforming audio metrics."""
    actual = optional_count(efficiency.get("delegation_count"))
    policy = golden.get("delegation_policy")
    required = bool(task.get("delegation_required")) or policy == "required"
    forbidden = bool(task.get("delegation_prohibited")) or policy == "forbidden"
    policy_known = (
        (isinstance(policy, str) and policy in {"required", "forbidden", "optional"}) or required or forbidden
    )
    if policy is None and not required and not forbidden:
        expected = optional_count(golden.get("delegations"))
        if expected is not None:
            required = expected > 0
            policy_known = True
        elif task.get("delegation_required") is False and task.get("delegation_prohibited") is False:
            policy_known = True
    delegation_accuracy = None
    if actual is not None and policy_known:
        delegated = actual > 0
        delegation_accuracy = float((not required or delegated) and not (forbidden and delegated))
    return {
        "tool_accuracy": _tool_accuracy(task, efficiency, golden),
        "delegation_accuracy": delegation_accuracy,
    }
