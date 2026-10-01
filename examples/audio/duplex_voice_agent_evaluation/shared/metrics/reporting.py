"""Customer-facing evaluation metrics shared by single- and multi-turn harnesses."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from shared.metrics.evidence import evidence_scores

METRIC_COLUMNS = (
    "task_completed",
    "semantic_quality",
    "tool_accuracy",
    "tool_calls",
    "delegation_accuracy",
    "delegations",
    "turns",
    "response_rate",
    "response_latency_ms",
    "interruption_rate",
    "speaking_duration_ms",
    "floor_hold_silence_ms",
    "frontend_audio_duration_ms",
    "frontend_total_tokens",
    "frontend_input_tokens",
    "frontend_input_audio_tokens",
    "frontend_input_text_tokens",
    "frontend_cached_input_tokens",
    "frontend_cache_write_input_tokens",
    "frontend_output_tokens",
    "frontend_output_audio_tokens",
    "frontend_output_text_tokens",
    "backend_total_tokens",
    "backend_input_tokens",
    "backend_input_text_tokens",
    "backend_cached_input_tokens",
    "backend_cache_write_input_tokens",
    "backend_output_tokens",
    "backend_output_text_tokens",
    "backend_output_reasoning_tokens",
)


def _response_policy_fields(interaction: dict[str, Any]) -> dict[str, Any]:
    if not interaction.get("metrics_version"):
        return {}
    return {
        "metrics_version": interaction["metrics_version"],
        "response_deadline_ms": interaction.get("config", {}).get("response_deadline_ms"),
        "response_opportunities": {
            key: value
            for key, value in interaction.get("counts", {}).items()
            if key.startswith("response_") or key in {"no_response_count", "caller_turn_count"}
        },
        "response_exclusion_reasons": interaction.get("response_exclusion_reasons", {}),
    }


def build_metric_row(
    *,
    task: dict[str, Any],
    efficiency: dict[str, Any],
    interaction: dict[str, Any],
    golden: dict[str, Any],
    evidence: Mapping[str, float | None] | None = None,
    usage: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Project measured evidence into one small, phase-independent result row."""
    scores = evidence_scores(task, efficiency, golden)
    if evidence is not None:
        scores.update(evidence)
    actual_turns = max(0, int(efficiency.get("total_turns", 0)))
    golden_turns = max(0, int(golden.get("total_turns", 0)))
    actual_tools = max(0, int(efficiency.get("unique_tool_invocation_count", 0)))
    golden_tools = sum(max(0, int(item.get("count", 1))) for item in golden.get("tool_calls", []))
    actual_delegations = max(0, int(efficiency.get("delegation_count", int(bool(task.get("delegation_observed"))))))
    golden_delegations = max(0, int(golden.get("delegations", int(bool(task.get("delegation_required"))))))
    tokens = usage or {}
    return {
        **_response_policy_fields(interaction),
        "task_completed": bool(task.get("task_completed", False)),
        "semantic_quality": task.get("semantic_quality"),
        "tool_accuracy": scores.get("tool_accuracy"),
        "tool_calls": f"{actual_tools}/{golden_tools}",
        "delegation_accuracy": scores.get("delegation_accuracy"),
        "delegations": f"{actual_delegations}/{golden_delegations}",
        "turns": f"{actual_turns}/{golden_turns}",
        "response_rate": interaction.get("response_rate"),
        "response_latency_ms": interaction.get("response_latency_ms"),
        "interruption_rate": interaction.get("interruption_rate", interaction.get("agent_interruption_rate")),
        "speaking_duration_ms": interaction.get("speaking_duration_ms"),
        "floor_hold_silence_ms": interaction.get("floor_hold_silence_ms"),
        "frontend_audio_duration_ms": tokens.get("frontend_audio_duration_ms"),
        "frontend_total_tokens": tokens.get("frontend_total_tokens"),
        "frontend_input_tokens": tokens.get("frontend_input_tokens"),
        "frontend_input_audio_tokens": tokens.get("frontend_input_audio_tokens"),
        "frontend_input_text_tokens": tokens.get("frontend_input_text_tokens"),
        "frontend_cached_input_tokens": tokens.get("frontend_cached_input_tokens"),
        "frontend_cache_write_input_tokens": tokens.get("frontend_cache_write_input_tokens"),
        "frontend_output_tokens": tokens.get("frontend_output_tokens"),
        "frontend_output_audio_tokens": tokens.get("frontend_output_audio_tokens"),
        "frontend_output_text_tokens": tokens.get("frontend_output_text_tokens"),
        "backend_total_tokens": tokens.get("backend_total_tokens"),
        "backend_input_tokens": tokens.get("backend_input_tokens"),
        "backend_input_text_tokens": tokens.get("backend_input_text_tokens"),
        "backend_cached_input_tokens": tokens.get("backend_cached_input_tokens"),
        "backend_cache_write_input_tokens": tokens.get("backend_cache_write_input_tokens"),
        "backend_output_tokens": tokens.get("backend_output_tokens"),
        "backend_output_text_tokens": tokens.get("backend_output_text_tokens"),
        "backend_output_reasoning_tokens": tokens.get("backend_output_reasoning_tokens"),
    }
