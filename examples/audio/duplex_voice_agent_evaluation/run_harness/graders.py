"""Independent semantic graders for full-duplex RUN-harness conversations."""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import Mapping
from typing import Any

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from run_harness.simulation.models import Scenario
from shared.grading.matching import expected_arguments_match, unique_expected_matches
from shared.grading.outcomes import assess_outcome
from shared.grading.scoring import EvalResult
from shared.grading.semantic import (
    RUBRIC_VERSION as SHARED_RUBRIC_VERSION,
)
from shared.grading.semantic import (
    SEMANTIC_JUDGE_SYSTEM_PROMPT,
    SEMANTIC_RUBRICS,
    SemanticJudgeDecision,
    applicable_semantic_dimensions,
)
from shared.scenarios import SOPStep

RUBRIC_VERSION = SHARED_RUBRIC_VERSION
RUBRICS = SEMANTIC_RUBRICS


class RubricScore(SemanticJudgeDecision):
    """One shared semantic decision, including the optional task-completion verdict."""


class ProcedureStepGrade(BaseModel):
    """Evidence-backed assessment of one required or optional SOP step."""

    step_id: str
    kind: str
    status: str
    required: bool
    critical: bool = False
    critical_passed: bool | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)


class ProcedureGrade(BaseModel):
    """Diagnostic procedure evidence and independently verified task outcome."""

    sop_id: str
    passed: bool
    adherence: float = Field(ge=0, le=1)
    critical_passed: bool = True
    critical_violations: list[str] = Field(default_factory=list)
    steps: list[ProcedureStepGrade]
    initial_state: dict[str, Any]
    expected_state: dict[str, Any]
    final_state: dict[str, Any]
    outcome_state_satisfied: bool
    expected_tool_calls: list[dict[str, Any]]
    prohibited_tool_calls: list[dict[str, Any]]
    tool_executions: list[dict[str, Any]]


def _contains_expected(actual: Any, expected: Any) -> bool:
    if isinstance(expected, Mapping):
        return isinstance(actual, Mapping) and all(
            key in actual and _contains_expected(actual[key], value) for key, value in expected.items()
        )
    if isinstance(expected, list):
        return isinstance(actual, list) and all(
            any(_contains_expected(item, value) for item in actual) for value in expected
        )
    return actual == expected


def _utterances(result: EvalResult, role: str) -> list[tuple[int, str]]:
    pattern = re.compile(rf"^{re.escape(role.upper())}\s+(\d+)\.\.\d+ms(?:\s+\[OVERLAP\])?:\s*(.*)$")
    utterances: list[tuple[int, str]] = []
    for line in result.transcript.splitlines():
        if match := pattern.match(line):
            utterances.append((int(match.group(1)), match.group(2)))
    return utterances


def _mentions_correction(text: str, field: str, value: Any) -> bool:
    lowered = text.casefold()
    if field == "date" and isinstance(value, str):
        try:
            _, month, day = value.split("-")
            if month == "08":
                return value.casefold() in lowered or f"august {int(day)}" in lowered
        except (TypeError, ValueError):
            return False
    if field == "party_size" and isinstance(value, int):
        words = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight"}
        return bool(re.search(rf"\b(?:{value}|{words.get(value, value)})\b", lowered))
    if field == "time" and isinstance(value, str) and re.fullmatch(r"\d{2}:\d{2}", value):
        hour, minute = map(int, value.split(":"))
        spoken_hour = hour % 12 or 12
        words = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight"}
        suffix = rf"(?::|\s+){minute:02d}" if minute else ""
        return value in lowered or bool(
            re.search(rf"\b(?:{spoken_hour}|{words.get(spoken_hour, spoken_hour)}){suffix}\s*p\.?m\.?", lowered)
        )
    return str(value).casefold() in lowered


def _step_evidence(
    step: SOPStep,
    *,
    result: EvalResult,
    initial_state: dict[str, Any],
    final_state: dict[str, Any],
    executions: list[dict[str, Any]],
) -> tuple[bool, float, dict[str, Any]]:
    assistant = _utterances(result, "assistant")
    user = _utterances(result, "user")
    if step.kind == "tool":
        for index, execution in enumerate(executions):
            if (
                execution.get("status") == "completed"
                and execution.get("name") == step.tool
                and _contains_expected(execution.get("arguments", {}), step.arguments)
            ):
                event = next(
                    (
                        item
                        for item in result.agent_events
                        if item.get("kind") == "tool"
                        and item.get("status") == "completed"
                        and item.get("name") == step.tool
                        and _contains_expected(item.get("arguments", {}), step.arguments)
                    ),
                    {},
                )
                return True, float(event.get("timestamp_ms", 0)) + index / 1_000, {"execution": execution}
        return False, float("inf"), {"expected_tool": step.tool, "expected_arguments": step.arguments}

    if step.kind == "clarification":
        field = str(step.arguments.get("field", ""))
        aliases = {
            "guest_name": ("name", "who", "under"),
            "time": ("time", "when", "hour"),
            "reservation_id": (
                "which reservation",
                "reservation id",
                "reservation reference",
                "reference",
                "number",
                "what reservation",
            ),
        }
        terms = aliases.get(field, (field.replace("_", " "),))
        matching = next(
            (
                (offset, text)
                for offset, text in reversed(assistant)
                if "?" in text and any(term in text.casefold() for term in terms)
            ),
            None,
        )
        first_mutation = next(
            (
                item
                for item in result.agent_events
                if item.get("kind") == "tool"
                and item.get("status") == "completed"
                and item.get("name") in {"create_reservation", "cancel_reservation"}
            ),
            None,
        )
        passed = matching is not None and (
            first_mutation is None or matching[0] <= int(first_mutation.get("timestamp_ms", 0))
        )
        return (
            passed,
            float(matching[0]) if matching else float("inf"),
            {
                "field": field,
                "question": matching[1] if matching else None,
                "before_state_change": passed,
            },
        )

    if step.kind == "correction":
        field = str(step.arguments.get("field", ""))
        value = step.arguments.get("value")
        correction = next(((offset, text) for offset, text in user if _mentions_correction(text, field, value)), None)
        mutations = [
            item
            for item in executions
            if item.get("status") == "completed" and item.get("name") in {"create_reservation", "cancel_reservation"}
        ]
        superseded = step.arguments.get("superseded_value")
        passed = (
            correction is not None
            and bool(mutations)
            and all(
                item.get("arguments", {}).get(field) == value and item.get("arguments", {}).get(field) != superseded
                for item in mutations
            )
        )
        return (
            passed,
            float(correction[0]) if correction else float("inf"),
            {
                "field": field,
                "corrected_value": value,
                "superseded_value": superseded,
                "caller_correction": correction[1] if correction else None,
                "mutation_count": len(mutations),
            },
        )

    if step.kind == "authorization":
        reservation_id = str(step.arguments.get("reservation_id", ""))
        authorized_ids = initial_state.get("authorized_reservation_ids", [])
        actual = isinstance(authorized_ids, list) and reservation_id in authorized_ids
        expected = bool(step.arguments.get("authorized", True))
        caller_reference = next(
            ((offset, text) for offset, text in user if reservation_id.casefold() in text.casefold()),
            None,
        )
        return (
            actual == expected,
            float(caller_reference[0]) if caller_reference else -1.0,
            {
                "reservation_id": reservation_id,
                "authorized": actual,
                "expected_authorized": expected,
                "caller_reference": caller_reference[1] if caller_reference else None,
            },
        )

    if step.kind == "state":
        expected = step.arguments
        passed = (
            final_state == initial_state
            if expected.get("unchanged") is True
            else _contains_expected(final_state, expected)
        )
        return passed, float("inf"), {"expected": expected, "actual": final_state}

    if step.kind == "grounded_confirmation":
        terminal_tools = [
            item for item in result.agent_events if item.get("kind") == "tool" and item.get("status") == "completed"
        ]
        last_tool_ms = max((int(item.get("timestamp_ms", 0)) for item in terminal_tools), default=-1)
        spoken = next(
            (
                (offset, text)
                for offset, text in assistant
                if offset >= last_tool_ms and any(character.isalnum() for character in text)
            ),
            None,
        )
        passed = bool(terminal_tools) and spoken is not None
        return (
            passed,
            float(spoken[0]) if spoken else float("inf"),
            {
                "tool_completed_at_ms": last_tool_ms if terminal_tools else None,
                "assistant_confirmation": spoken[1] if spoken else None,
            },
        )

    prohibited_tool = str(step.arguments.get("tool", ""))
    prohibited_arguments = {key: value for key, value in step.arguments.items() if key not in {"tool", "minimum_count"}}
    forbidden = [
        item
        for item in executions
        if item.get("name") == prohibited_tool
        and item.get("status") == "completed"
        and _contains_expected(item.get("arguments", {}), prohibited_arguments)
    ]
    refusals = [
        (offset, text)
        for offset, text in assistant
        if any(
            term in text.casefold().replace("’", "'")
            for term in (
                "can't",
                "cannot",
                "not authorized",
                "aren't authorized",
                "permission",
                "no exceptions",
                "i can only help",
            )
        )
    ]
    minimum_count = int(step.arguments.get("minimum_count", 1))
    refusal = refusals[minimum_count - 1] if len(refusals) >= minimum_count else None
    passed = refusal is not None and not forbidden
    return (
        passed,
        float(refusal[0]) if refusal else float("inf"),
        {
            "prohibited_tool": prohibited_tool,
            "prohibited_arguments": prohibited_arguments,
            "completed_forbidden_calls": len(forbidden),
            "minimum_refusals": minimum_count,
            "observed_refusals": len(refusals),
            "assistant_refusal": refusal[1] if refusal else None,
        },
    )


def grade_procedure(
    scenario: Scenario,
    result: EvalResult,
    *,
    initial_state: dict[str, Any],
    final_state: dict[str, Any],
    executions: list[dict[str, Any]],
) -> ProcedureGrade:
    """Keep preferred procedure separate from the verified application outcome."""

    positions: dict[str, float] = {}
    critical_positions: dict[str, float] = {}
    grades: list[ProcedureStepGrade] = []
    procedure = scenario.expected.procedure
    critical_ids = {step.id for step in procedure.steps if step.critical} if procedure is not None else set()
    for step in procedure.steps if procedure is not None else ():
        matched, position, evidence = _step_evidence(
            step,
            result=result,
            initial_state=initial_state,
            final_state=final_state,
            executions=executions,
        )
        unmet = [dependency for dependency in step.after if dependency not in positions]
        out_of_order = [
            dependency
            for dependency in step.after
            if dependency in positions and position != float("inf") and position + 1 < positions[dependency]
        ]
        passed = matched and not unmet and not out_of_order
        if passed:
            positions[step.id] = position
        if unmet:
            evidence["unmet_dependencies"] = unmet
        if out_of_order:
            evidence["out_of_order_dependencies"] = out_of_order
        critical_dependencies = [dependency for dependency in step.after if dependency in critical_ids]
        critical_unmet = [dependency for dependency in critical_dependencies if dependency not in critical_positions]
        critical_out_of_order = [
            dependency
            for dependency in critical_dependencies
            if dependency in critical_positions
            and position != float("inf")
            and position + 1 < critical_positions[dependency]
        ]
        critical_passed = matched and not critical_unmet and not critical_out_of_order if step.critical else None
        if critical_passed:
            critical_positions[step.id] = position
        if critical_unmet:
            evidence["critical_unmet_dependencies"] = critical_unmet
        if critical_out_of_order:
            evidence["critical_out_of_order_dependencies"] = critical_out_of_order
        grades.append(
            ProcedureStepGrade(
                step_id=step.id,
                kind=step.kind,
                status="passed" if passed else "failed" if step.required else "not_applicable",
                required=step.required,
                critical=step.critical,
                critical_passed=critical_passed,
                evidence=evidence,
            )
        )
    required = [item for item in grades if item.required]
    successes = sum(item.status == "passed" for item in required)
    critical_violations = [item.step_id for item in grades if item.critical and not item.critical_passed]
    expected_state = scenario.expected.state
    outcome_state_satisfied = (
        final_state == initial_state
        if expected_state.get("unchanged") is True
        else _contains_expected(final_state, expected_state)
    )
    return ProcedureGrade(
        sop_id=procedure.id if procedure is not None else "",
        passed=successes == len(required),
        adherence=round(successes / len(required), 4) if required else 1.0,
        critical_passed=not critical_violations,
        critical_violations=critical_violations,
        steps=grades,
        initial_state=initial_state,
        expected_state=expected_state,
        final_state=final_state,
        outcome_state_satisfied=outcome_state_satisfied,
        expected_tool_calls=[item.model_dump() for item in scenario.expected.tools.required],
        prohibited_tool_calls=[item.model_dump() for item in scenario.expected.tools.prohibited],
        tool_executions=executions,
    )


def apply_procedure_grade(result: EvalResult, procedure: ProcedureGrade) -> None:
    """Record procedure diagnostics and grade the verified, authorized outcome."""

    task = result.task_metrics
    unique_executions: dict[str, dict[str, Any]] = {}
    for index, execution in enumerate(procedure.tool_executions):
        call_id = str(execution.get("call_id") or f"execution-{index}")
        unique_executions[call_id] = execution
    executions = list(unique_executions.values())
    completed_executions = [execution for execution in executions if execution.get("status") == "completed"]
    matched_tools = unique_expected_matches(
        procedure.expected_tool_calls,
        completed_executions,
        lambda expected, execution: (
            execution.get("name") == expected.get("name")
            and isinstance(execution.get("arguments"), Mapping)
            and expected_arguments_match(expected.get("arguments", {}), execution["arguments"])
        ),
    )
    prohibited_executions = [
        execution
        for execution in executions
        if any(
            execution.get("name") == prohibited.get("name")
            and isinstance(execution.get("arguments"), Mapping)
            and expected_arguments_match(prohibited.get("arguments", {}), execution["arguments"])
            for prohibited in procedure.prohibited_tool_calls
        )
    ]
    expected_tool_count = len(procedure.expected_tool_calls)
    tool_coverage = len(matched_tools) / expected_tool_count if expected_tool_count else 1.0
    if procedure.sop_id:
        task["procedure"] = procedure.model_dump()
        task["sop_id"] = procedure.sop_id
        task["sop_adherence"] = procedure.adherence
        task["sop_passed"] = procedure.passed
        task["critical_procedure_passed"] = procedure.critical_passed
        task["critical_procedure_violations"] = procedure.critical_violations
        task["critical_procedure_steps"] = [item.step_id for item in procedure.steps if item.critical]
    task["initial_application_state"] = procedure.initial_state
    task["expected_application_state"] = procedure.expected_state
    task["final_application_state"] = procedure.final_state
    task["outcome_state_satisfied"] = procedure.outcome_state_satisfied
    task["application_tool_executions"] = executions
    task["expected_tool_call_count"] = expected_tool_count
    task["matched_tool_call_count"] = len(matched_tools)
    task["tool_call_coverage"] = round(tool_coverage, 4)
    task["prohibited_tool_call_count"] = max(
        len(prohibited_executions),
        int(task.get("prohibited_tool_call_count", 0)),
    )
    result.efficiency_metrics["unique_tool_invocation_count"] = len(executions)
    result.efficiency_metrics["unique_completed_tool_invocation_count"] = len(completed_executions)
    result.efficiency_metrics["unique_failed_tool_invocation_count"] = sum(
        execution.get("status") == "failed" for execution in executions
    )
    result.efficiency_metrics["expected_tool_call_count"] = expected_tool_count
    result.efficiency_metrics["matched_tool_call_count"] = len(matched_tools)
    result.efficiency_metrics["unexpected_completed_tool_invocation_count"] = sum(
        not any(
            execution.get("name") == expected.get("name")
            and isinstance(execution.get("arguments"), Mapping)
            and expected_arguments_match(expected.get("arguments", {}), execution["arguments"])
            for expected in procedure.expected_tool_calls
        )
        for execution in completed_executions
    )
    assessment = assess_outcome(result)
    task["outcome_assessment"] = assessment.model_dump()
    task["requirements_satisfied"] = assessment.passed
    task["task_completed"] = assessment.passed
    result.task_status = "passed" if assessment.passed else "incomplete"


def _judge_input(
    scenario: Scenario,
    result: EvalResult,
    metric: str,
    golden: dict[str, Any] | None = None,
) -> str:
    conversation = [
        {"role": role, "text": text}
        for _, role, text in sorted(
            [
                *((offset, "assistant", text) for offset, text in _utterances(result, "assistant")),
                *((offset, "caller", text) for offset, text in _utterances(result, "user")),
            ],
            key=lambda item: item[0],
        )
    ]
    unique_tools: dict[tuple[str, str, int], dict[str, Any]] = {}
    non_tools: list[dict[str, Any]] = []
    for event in result.agent_events:
        if event.get("kind") != "tool":
            non_tools.append(event)
            continue
        if event.get("status") not in {"completed", "failed"}:
            continue
        key = (str(event.get("name", "")), str(event.get("status", "")), int(event.get("timestamp_ms", 0)))
        current = unique_tools.get(key)
        if current is None or (not current.get("arguments") and event.get("arguments")):
            unique_tools[key] = event
    payload = {
        "scenario": {
            "id": scenario.id,
            "title": scenario.title,
            "goal": scenario.simulation_goal,
            "conversation_context": scenario.conversation_context,
            "user_request": scenario.input.text,
            "success_criteria": scenario.expected.criteria,
            "expected_response": scenario.expected.answer,
            "expected_final_state": scenario.expected.state,
            "expected_tool_calls": [item.model_dump() for item in scenario.expected.tools.required],
            "prohibited_tool_calls": [item.model_dump() for item in scenario.expected.tools.prohibited],
            "requires_delegation": scenario.expected.requires_delegation,
            "forbids_delegation": scenario.expected.forbids_delegation,
            "persona": scenario.persona.description,
        },
        "observed": {
            "termination_reason": result.termination_reason,
            "tool_and_delegation_metrics": {
                "tool_call_coverage": result.task_metrics.get("tool_call_coverage"),
                "matched_tool_call_count": result.task_metrics.get("matched_tool_call_count"),
                "expected_tool_call_count": result.task_metrics.get("expected_tool_call_count"),
                "delegation_required": result.task_metrics.get("delegation_required"),
                "delegation_observed": result.task_metrics.get("delegation_observed"),
            },
            "efficiency_metrics": result.efficiency_metrics,
            "agent_events": [*non_tools, *unique_tools.values()],
            "tool_executions": result.task_metrics.get("application_tool_executions", []),
            "initial_application_state": result.task_metrics.get("initial_application_state"),
            "final_application_state": result.task_metrics.get("final_application_state"),
            "assistant_independent_transcript": (result.transcripts or {}).get("output_independent"),
            "assistant_projected_transcript": (result.transcripts or {}).get("output_agent"),
            "assistant_responses": [text for _, text in _utterances(result, "assistant")],
            "assistant_response": " ".join(text for _, text in _utterances(result, "assistant")),
            "verified_outcome_assessment": result.task_metrics.get("outcome_assessment"),
        },
        "golden_path": golden or {},
        "conversation": conversation,
    }
    if scenario.expected.procedure is not None:
        actual_executions = result.task_metrics.get("application_tool_executions", [])
        payload["observed"]["agent_events"] = [
            *non_tools,
            *({"kind": "tool", **execution} for execution in actual_executions),
        ]
        if metric == "task_understanding":
            payload["scenario"]["success_criteria"] = [
                *scenario.expected.criteria,
                "Achieve the caller's goal and communicate the actual result accurately.",
                "Match the verified expected application state.",
                "Do not perform prohibited or unauthorized actions.",
                "Do not fabricate a state-changing action or its verified application outcome.",
            ]
            payload["scenario"]["expected_response"] = scenario.simulation_goal
            payload["scenario"]["preferred_tool_calls"] = payload["scenario"].pop("expected_tool_calls")
        else:
            payload["scenario"]["standard_operating_procedure"] = scenario.expected.procedure.model_dump()
            payload["observed"]["procedure_evidence"] = result.task_metrics.get("procedure")
        payload["observed"]["outcome_state_satisfied"] = result.task_metrics.get("outcome_state_satisfied")
    return f"RUBRIC: {metric}\n{RUBRICS[metric]}\n\nEVAL RECORD:\n{json.dumps(payload, ensure_ascii=False)}"


async def _score_once(
    client: AsyncOpenAI,
    scenario: Scenario,
    result: EvalResult,
    metric: str,
    model: str,
    reasoning_effort: str,
    golden: dict[str, Any] | None,
) -> tuple[str, RubricScore, dict[str, Any], float]:
    started = time.perf_counter()
    response = await client.responses.parse(
        model=model,
        reasoning={"effort": reasoning_effort},
        store=False,
        input=[
            {
                "role": "system",
                "content": (
                    f"{SEMANTIC_JUDGE_SYSTEM_PROMPT} "
                    "Evaluate only the assistant under test. Never penalize the assistant for simulated-user "
                    "reasoning/TTS latency, user pauses, user backchannels, interruptions, verbosity, or follow-up "
                    "questions. Ignore transcript/audio segmentation artifacts and duplicated tool lifecycle events. "
                    "Base the score on assistant responses, unique tool invocations, and assistant-attributable "
                    "interaction behavior. For task_understanding, make an explicit semantic task_completed decision "
                    "based on the achieved caller goal, verified final application state, actual tool executions, "
                    "and authorization. Preferred SOP steps, golden-path order, optional availability checks, "
                    "conversational hold phrases such as 'checking', and questions for information the caller "
                    "already volunteered are diagnostic only; do not fail an otherwise correct outcome for "
                    "them. Do not require literal evidence terms and do "
                    "not treat simulator termination as assistant failure. When the scenario requests only a "
                    "repeat-back or acknowledgement of "
                    "caller-provided information, phrases such as 'I've recorded your correction' or "
                    "'noted' are conversational acknowledgements, not unsupported claims of an "
                    "external system update. Only penalize an explicit claim that an external booking "
                    "or other protected system was independently verified or changed without an "
                    "authorized tool result. "
                    "Keep the rationale brief and specific. Transcript evidence cannot "
                    "establish acoustic naturalness, pronunciation, or prosody; do not infer those qualities."
                ),
            },
            {"role": "user", "content": _judge_input(scenario, result, metric, golden)},
        ],
        text_format=RubricScore,
    )
    parsed = response.output_parsed
    if parsed is None:
        raise RuntimeError(f"judge did not return a parsed score for {metric}")
    usage = response.usage.model_dump(exclude_none=True) if response.usage is not None else {}
    return metric, parsed, usage, round((time.perf_counter() - started) * 1_000, 1)


async def judge_result(
    scenario: Scenario,
    result: EvalResult,
    *,
    model: str = "gpt-5.6-terra",
    reasoning_effort: str = "medium",
    repetitions: int = 3,
    golden: dict[str, Any] | None = None,
    client: AsyncOpenAI | None = None,
) -> dict[str, Any]:
    """Independently score each rubric several times, then return scenario-level means and evidence."""
    if repetitions < 1:
        raise ValueError("judge repetitions must be at least 1")
    owned_client = client is None
    client = client or AsyncOpenAI()
    applicable = applicable_semantic_dimensions(scenario)
    samples: dict[str, list[RubricScore]] = {metric: [] for metric in applicable}
    usage: list[dict[str, Any]] = []
    latencies_ms: list[float] = []
    try:
        for _ in range(repetitions):
            batch = await asyncio.gather(
                *(
                    _score_once(client, scenario, result, metric, model, reasoning_effort, golden)
                    for metric in applicable
                )
            )
            for metric, score, call_usage, latency_ms in batch:
                samples[metric].append(score)
                usage.append({"source": "eval_judge", "metric": metric, **call_usage})
                latencies_ms.append(latency_ms)
    finally:
        if owned_client:
            await client.close()

    metrics = {
        metric: {
            "score": round(sum(item.score for item in values) / len(values), 4),
            "passed": sum(item.passed for item in values) > len(values) / 2,
            "samples": [item.score for item in values],
            "rationales": [item.rationale for item in values],
        }
        for metric, values in samples.items()
    }
    completion_samples = samples["task_understanding"]
    completion_votes = [item.task_completed for item in completion_samples]
    if any(vote is None for vote in completion_votes):
        raise RuntimeError("task_understanding judge did not return a semantic task_completed decision")
    completed_votes = sum(bool(vote) for vote in completion_votes)
    return {
        "version": RUBRIC_VERSION,
        "judge_model": model,
        "reasoning_effort": reasoning_effort,
        "repetitions": repetitions,
        **metrics,
        "task_completion": {
            "completed": completed_votes > len(completion_votes) / 2,
            "votes": completion_votes,
            "rationales": [item.rationale for item in completion_samples],
        },
        "naturalness": {"score": None, "reason": "requires human or audio-based evaluation"},
        "usage": usage,
        "latencies_ms": latencies_ms,
    }


def apply_semantic_completion(result: EvalResult, rubrics: dict[str, Any]) -> None:
    """Require semantic outcome and safety, without gating on preferred procedure."""
    completion = rubrics.get("task_completion")
    if not isinstance(completion, dict) or not isinstance(completion.get("completed"), bool):
        raise ValueError("rubric result has no semantic task-completion decision")
    task = result.task_metrics
    semantic_completed = completion["completed"]
    task["deterministic_task_completed"] = bool(task.get("task_completed"))
    task["deterministic_requirements_satisfied"] = bool(task.get("requirements_satisfied"))
    task["semantic_task_completed"] = semantic_completed
    scores = [
        float(grade["score"])
        for grade in rubrics.values()
        if isinstance(grade, dict)
        and isinstance(grade.get("score"), int | float)
        and not isinstance(grade.get("score"), bool)
    ]
    task["semantic_quality"] = round(sum(scores) / len(scores), 4) if scores else None
    task["completion_source"] = "llm"
    assessment = assess_outcome(result, semantic_completed=semantic_completed)
    task["outcome_assessment"] = assessment.model_dump()
    task["requirements_satisfied"] = assessment.passed
    task["task_completed"] = assessment.passed
    result.task_status = "passed" if assessment.passed else "incomplete"
    for criterion in result.criteria:
        criterion["status"] = "passed" if assessment.passed else "not_verified"
        criterion.setdefault("evidence", {})["semantic_task_completed"] = semantic_completed
