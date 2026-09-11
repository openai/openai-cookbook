"""Phase-neutral single-turn task observability and evaluator trace events."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from shared.grading.outcomes import compact_assessment
from shared.grading.scoring import EvalResult
from shared.observability.trace import append_trace_events
from shared.scenarios import Scenario


def build_single_turn_observability(
    scenario: Scenario,
    result: EvalResult,
    *,
    audio_source: str,
    deterministic_grades: Mapping[str, Mapping[str, Any]],
    semantic_grades: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Explain a one-request result without inventing caller-agenda data."""

    assessment = result.task_metrics.get("outcome_assessment", {})
    executions = result.task_metrics.get("application_tool_executions", [])
    return {
        "provenance": {
            "api_version": "v3",
            "turn_derivation": "local_audio_and_transcript",
            "audio_timing": "local_playout_clock",
            "transcript_timing": "provider_session_clock",
        },
        "interaction": {
            "mode": "single_turn",
            "audio_source": audio_source,
            "assistant_turns": result.assistant_turns,
            "caller_turns": result.user_turns,
            "delegations": result.delegation_count,
        },
        "tools": {
            "executed": [
                {
                    "name": execution.get("name"),
                    "status": execution.get("status"),
                    "arguments": execution.get("arguments", {}),
                    "call_id": execution.get("call_id"),
                }
                for execution in executions
            ],
            "expected_count": int(result.task_metrics.get("expected_tool_call_count", 0)),
            "matched_count": int(result.task_metrics.get("matched_tool_call_count", 0)),
            "unexpected_completed_count": int(
                result.efficiency_metrics.get("unexpected_completed_tool_invocation_count", 0)
            ),
            "failed_count": int(result.efficiency_metrics.get("unique_failed_tool_invocation_count", 0)),
        },
        "grading": {
            "deterministic": {name: grade.get("status") for name, grade in deterministic_grades.items()},
            "semantic": {name: grade.get("status") for name, grade in semantic_grades.items()},
            "semantic_scores": {
                name: grade["score"]
                for name, grade in semantic_grades.items()
                if grade.get("status") in {"passed", "failed"} and grade.get("score") is not None
            },
        },
        "completion": {
            "termination_reason": result.termination_reason,
            "passed": assessment.get("passed", bool(result.task_metrics.get("task_completed"))),
            "source": assessment.get("source", "deterministic"),
            "rationale": assessment.get("rationale", ""),
            "failed_checks": [
                check["id"]
                for check in assessment.get("checks", [])
                if check.get("required") and check.get("status") == "failed"
            ],
        },
        "scenario": {"id": scenario.id, "type": scenario.scenario_type},
    }


def append_single_turn_grading_trace(
    path: Path,
    *,
    scenario: Scenario,
    result: EvalResult,
    deterministic_grades: Mapping[str, Mapping[str, Any]],
    semantic_grades: Mapping[str, Mapping[str, Any]],
    started_at: float,
) -> None:
    """Add consistent grading verdicts after CRAWL or WALK audio transport ends."""

    assessed_semantic = {
        name: grade for name, grade in semantic_grades.items() if grade.get("status") in {"passed", "failed"}
    }
    events: list[dict[str, Any]] = [
        {
            "type": "evaluation.checks.assessed",
            "scenario_id": scenario.id,
            "dimensions": {
                name: {"status": grade.get("status"), "evidence": grade.get("evidence", {})}
                for name, grade in deterministic_grades.items()
            },
        },
        {
            "type": "evaluation.outcome.assessed",
            "scenario_id": scenario.id,
            **result.task_metrics.get("outcome_assessment", {}),
        },
    ]
    if assessed_semantic:
        events.append(
            {
                "type": "evaluation.semantic_judge.completed",
                "scenario_id": scenario.id,
                "dimensions": {
                    name: {
                        "status": grade.get("status"),
                        "score": grade.get("score"),
                        "rationale": grade.get("rationale", ""),
                    }
                    for name, grade in assessed_semantic.items()
                },
            }
        )
    append_trace_events(path, events, started_at=started_at)


def result_assessment(result: EvalResult) -> dict[str, Any]:
    """Expose the same concise assessment shape as the RUN harness."""

    return compact_assessment(result.task_metrics.get("outcome_assessment", {}))
