"""Readable, evidence-backed RUN diagnostics and append-only evaluation traces."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from run_harness.simulation.models import Scenario
from shared.grading.scoring import EvalResult
from shared.observability.trace import append_trace_events


def build_observability(scenario: Scenario, result: EvalResult) -> dict[str, Any]:
    """Summarize caller progress, inferred actions, tool evidence, and completion."""

    metadata = result.run_metadata or {}
    completed = set(metadata.get("caller_agenda_completed", []))
    skipped = set(metadata.get("caller_agenda_skipped", []))
    bypassed = set(metadata.get("caller_agenda_bypassed", []))
    agenda = scenario.simulation_parameters.agenda if scenario.simulation_parameters is not None else []
    executions = result.task_metrics.get("application_tool_executions", [])
    assessment = result.task_metrics.get("outcome_assessment", {})
    failed_steps = [
        step["step_id"]
        for step in result.task_metrics.get("procedure", {}).get("steps", [])
        if step.get("required") and step.get("status") == "failed"
    ]
    return {
        "agenda": {
            "total": len(agenda),
            "completed": sorted(completed),
            "skipped": sorted(skipped),
            "bypassed": sorted(bypassed),
            "pending_required": sorted(
                item.id for item in agenda if item.required and item.id not in completed and item.id not in skipped
            ),
        },
        "interaction": {
            "mode": result.interaction_mode,
            "audio_source": result.audio_source,
            "caller_mode": result.caller_mode,
            "caller_actions": dict(result.caller_actions),
            "attribution": "post_hoc_audio_and_transcript",
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
        "completion": {
            "termination_reason": result.termination_reason,
            "policy": metadata.get("caller_completion_policy", "unknown"),
            "passed": assessment.get("passed", bool(result.task_metrics.get("task_completed"))),
            "source": assessment.get("source", "deterministic"),
            "rationale": assessment.get("rationale", ""),
            "failed_checks": [
                check["id"]
                for check in assessment.get("checks", [])
                if check.get("required") and check.get("status") == "failed"
            ],
            "failed_procedure_steps": failed_steps,
            "procedure_is_diagnostic": True,
        },
    }


def append_grading_trace(result: EvalResult) -> None:
    """Append evaluator decisions after the conversation's streaming trace closes."""

    artifacts = result.artifacts or {}
    if not artifacts.get("events"):
        return
    path = Path(artifacts["events"])
    if not path.exists():
        return
    started = (result.run_metadata or {}).get("started_at")
    try:
        elapsed_ms = (datetime.now(UTC) - datetime.fromisoformat(str(started))).total_seconds() * 1_000
    except (TypeError, ValueError):
        started_at = None
    else:
        started_at = time.monotonic() - elapsed_ms / 1_000
    procedure = result.task_metrics.get("procedure", {})
    events: list[dict[str, Any]] = []
    if procedure:
        events.append(
            {
                "type": "evaluation.procedure.assessed",
                "scenario_id": result.scenario_id,
                "sop_id": procedure.get("sop_id"),
                "passed": procedure.get("passed"),
                "adherence": procedure.get("adherence"),
                "failed_required_steps": [
                    step["step_id"]
                    for step in procedure.get("steps", [])
                    if step.get("required") and step.get("status") == "failed"
                ],
                "diagnostic_only": True,
            }
        )
    events.append(
        {
            "type": "evaluation.outcome.assessed",
            "scenario_id": result.scenario_id,
            **result.task_metrics.get("outcome_assessment", {}),
        }
    )
    if result.rubric_metrics is not None:
        events.append(
            {
                "type": "evaluation.semantic_judge.completed",
                "scenario_id": result.scenario_id,
                "model": result.rubric_metrics.get("judge_model"),
                "completion": result.rubric_metrics.get("task_completion"),
                "scores": {
                    name: grade["score"]
                    for name, grade in result.rubric_metrics.items()
                    if isinstance(grade, dict) and isinstance(grade.get("score"), int | float)
                },
            }
        )
    append_trace_events(path, events, started_at=started_at)
