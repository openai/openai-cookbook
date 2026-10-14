"""Evidence-backed task-outcome assessments shared by every evaluation phase."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from shared.grading.scoring import EvalResult


class OutcomeCheck(BaseModel):
    """One independently explainable condition behind the task verdict."""

    id: str
    status: Literal["passed", "failed", "not_applicable", "not_assessed"]
    required: bool = True
    reason: str
    evidence: dict[str, Any] = Field(default_factory=dict)


class OutcomeAssessment(BaseModel):
    """Small outcome verdict; conversation policy and SOPs remain diagnostics."""

    passed: bool
    source: Literal["deterministic", "semantic_judge"]
    rationale: str
    checks: list[OutcomeCheck]


def _assistant_utterances(result: EvalResult) -> list[tuple[int, str]]:
    pattern = re.compile(r"^ASSISTANT\s+(\d+)\.\.\d+ms(?:\s+\[OVERLAP\])?:\s*(.*)$")
    observed: list[tuple[int, str]] = []
    for line in result.transcript.splitlines():
        if match := pattern.match(line):
            observed.append((int(match.group(1)), match.group(2)))
    return observed


def assess_outcome(
    result: EvalResult,
    *,
    semantic_completed: bool | None = None,
    strict_tools: bool = False,
    semantic_requirements_satisfied: bool | None = None,
) -> OutcomeAssessment:
    """Explain task success using verified assistant, state, tool, and judge evidence."""

    task = result.task_metrics
    assistant = _assistant_utterances(result)
    completed_tools = [
        execution for execution in task.get("application_tool_executions", []) if execution.get("status") == "completed"
    ]
    initial_state = task.get("initial_application_state")
    final_state = task.get("final_application_state")
    state_changes = initial_state is not None and final_state is not None and initial_state != final_state
    completed_events = [
        event for event in result.agent_events if event.get("kind") == "tool" and event.get("status") == "completed"
    ]
    latest_tool_ms = max((int(event.get("timestamp_ms", 0)) for event in completed_events), default=None)
    grounded_reply = next(
        (
            {"start_ms": start_ms, "text": text}
            for start_ms, text in assistant
            if latest_tool_ms is None or start_ms >= latest_tool_ms
        ),
        None,
    )
    post_tool_text = str(task.get("post_tool_assistant_text", "")).strip()
    if post_tool_text and latest_tool_ms is not None:
        grounded_reply = {"start_ms": latest_tool_ms, "text": post_tool_text, "source": "post_tool_audio"}
    state_expected = task.get("expected_application_state")
    state_required = isinstance(state_expected, dict) and bool(state_expected)
    delegation_required = bool(task.get("delegation_required"))
    delegation_prohibited = bool(task.get("delegation_prohibited"))
    delegation_observed = bool(task.get("delegation_observed"))
    prohibited_count = int(task.get("prohibited_tool_call_count", 0))
    expected_tools = int(task.get("expected_tool_call_count", 0))
    matched_tools = int(task.get("matched_tool_call_count", 0))
    unexpected_tools = int(result.efficiency_metrics.get("unexpected_completed_tool_invocation_count", 0))
    failed_tools = int(result.efficiency_metrics.get("unique_failed_tool_invocation_count", 0))
    critical_steps = task.get("critical_procedure_steps", [])
    critical_violations = task.get("critical_procedure_violations", [])

    checks = [
        OutcomeCheck(
            id="conversation_completed",
            status="passed" if task.get("conversation_completed") else "failed",
            reason=(
                "The conversation reached an explicit completion."
                if task.get("conversation_completed")
                else f"The conversation ended with {result.termination_reason!r} before completion."
            ),
            evidence={"termination_reason": result.termination_reason},
        ),
        OutcomeCheck(
            id="assistant_responded",
            status="passed" if assistant else "failed",
            reason=(
                "The assistant produced a substantive response."
                if assistant
                else "No substantive assistant response was observed."
            ),
            evidence={"assistant_response_count": len(assistant)},
        ),
        OutcomeCheck(
            id="application_state",
            status=(
                "not_applicable"
                if not state_required
                else "passed"
                if task.get("outcome_state_satisfied")
                else "failed"
            ),
            required=state_required,
            reason=(
                "No application-state outcome was specified."
                if not state_required
                else "Verified application state matches the expected outcome."
                if task.get("outcome_state_satisfied")
                else "Verified application state does not match the expected outcome."
            ),
            evidence={"expected": state_expected, "actual": final_state},
        ),
        OutcomeCheck(
            id="delegation_policy",
            status=(
                "not_applicable"
                if not delegation_required and not delegation_prohibited
                else "passed"
                if (not delegation_required or delegation_observed)
                and not (delegation_prohibited and delegation_observed)
                else "failed"
            ),
            required=delegation_required or delegation_prohibited,
            reason=(
                "The observed delegation behavior matches the scenario policy."
                if (not delegation_required or delegation_observed)
                and not (delegation_prohibited and delegation_observed)
                else "The assistant violated the required or prohibited delegation policy."
            ),
            evidence={
                "required": delegation_required,
                "prohibited": delegation_prohibited,
                "observed": delegation_observed,
            },
        ),
        OutcomeCheck(
            id="authorized_actions",
            status="passed" if not prohibited_count else "failed",
            reason=(
                "No prohibited or unauthorized tool actions were observed."
                if not prohibited_count
                else f"Observed {prohibited_count} prohibited or unauthorized tool action(s)."
            ),
            evidence={"prohibited_tool_call_count": prohibited_count},
        ),
        OutcomeCheck(
            id="critical_procedure",
            status=(
                "not_applicable"
                if not critical_steps
                else "passed"
                if task.get("critical_procedure_passed", True)
                else "failed"
            ),
            required=bool(critical_steps),
            reason=(
                "No outcome-critical procedure steps were specified."
                if not critical_steps
                else "Every outcome-critical procedure step and critical ordering requirement passed."
                if task.get("critical_procedure_passed", True)
                else "One or more outcome-critical procedure steps or ordering requirements failed."
            ),
            evidence={"required_steps": critical_steps, "failed_steps": critical_violations},
        ),
        OutcomeCheck(
            id="tool_contract",
            status=(
                "not_applicable"
                if not strict_tools
                else "passed"
                if expected_tools == matched_tools and unexpected_tools == 0 and failed_tools == 0
                else "failed"
            ),
            required=strict_tools,
            reason=(
                "Preferred RUN tool choices are graded separately from the outcome."
                if not strict_tools
                else "Observed tool names, arguments, and execution match the single-turn scenario."
                if expected_tools == matched_tools and unexpected_tools == 0 and failed_tools == 0
                else "Observed tool execution does not match the expected single-turn contract."
            ),
            evidence={
                "expected_count": expected_tools,
                "matched_count": matched_tools,
                "unexpected_completed_count": unexpected_tools,
                "failed_count": failed_tools,
            },
        ),
        OutcomeCheck(
            id="verified_state_change",
            status="not_applicable" if not state_changes else "passed" if completed_tools else "failed",
            required=state_changes,
            reason=(
                "The scenario did not change application state."
                if not state_changes
                else "The application change is backed by a completed tool execution."
                if completed_tools
                else "Application state changed without a completed, observable tool execution."
            ),
            evidence={"completed_tool_count": len(completed_tools)},
        ),
        OutcomeCheck(
            id="grounded_assistant_response",
            status=("not_applicable" if not completed_tools else "passed" if grounded_reply is not None else "failed"),
            required=bool(completed_tools),
            reason=(
                "No completed tool requires a grounded response."
                if not completed_tools
                else "The assistant communicated after the completed tool result."
                if grounded_reply is not None
                else "The assistant did not communicate the result after the completed tool."
            ),
            evidence={"last_completed_tool_ms": latest_tool_ms, "assistant_response": grounded_reply},
        ),
        OutcomeCheck(
            id="semantic_outcome",
            status="not_assessed" if semantic_completed is None else "passed" if semantic_completed else "failed",
            required=semantic_completed is not None,
            reason=(
                "Independent semantic grading was not requested."
                if semantic_completed is None
                else "The independent judge confirmed the assistant achieved the caller's goal."
                if semantic_completed
                else "The independent judge found the caller's goal was not achieved."
            ),
            evidence={"task_completed": semantic_completed},
        ),
        OutcomeCheck(
            id="semantic_requirements",
            status=(
                "not_assessed"
                if semantic_requirements_satisfied is None
                else "passed"
                if semantic_requirements_satisfied
                else "failed"
            ),
            required=semantic_requirements_satisfied is not None,
            reason=(
                "No additional semantic scenario requirements were assessed."
                if semantic_requirements_satisfied is None
                else "All applicable semantic scenario requirements passed."
                if semantic_requirements_satisfied
                else "At least one applicable semantic scenario requirement failed."
            ),
            evidence={"requirements_satisfied": semantic_requirements_satisfied},
        ),
    ]
    failures = [check for check in checks if check.required and check.status == "failed"]
    return OutcomeAssessment(
        passed=not failures,
        source="semantic_judge" if semantic_completed is not None else "deterministic",
        rationale=(
            "The assistant achieved the verified outcome without violating safety or authorization constraints."
            if not failures
            else "; ".join(check.reason for check in failures)
        ),
        checks=checks,
    )


def compact_assessment(assessment: dict[str, Any]) -> dict[str, Any]:
    """Keep the common results report readable while retaining detailed artifact evidence."""

    return {
        "passed": bool(assessment.get("passed", False)),
        "source": assessment.get("source", "deterministic"),
        "rationale": assessment.get("rationale", ""),
        "checks": [
            {"id": check["id"], "status": check["status"], "required": check["required"]}
            for check in assessment.get("checks", [])
        ],
    }
