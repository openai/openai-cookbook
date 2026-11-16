"""Shared deterministic and semantic grading for single-turn voice evaluations."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from statistics import fmean
from typing import Any

from openai import AsyncOpenAI

from shared.grading.matching import expected_arguments_match, normalize_argument_text
from shared.grading.outcomes import assess_outcome
from shared.grading.scoring import EvalResult, build_result
from shared.grading.semantic import (
    RUBRIC_VERSION,
    SEMANTIC_JUDGE_SYSTEM_PROMPT,
    SEMANTIC_RUBRICS,
    SemanticJudgeDecision,
)
from shared.grading.semantic import applicable_semantic_dimensions as shared_applicable_semantic_dimensions
from shared.metrics.evidence import evidence_scores
from shared.metrics.tokens import TokenUsage
from shared.observability.timeline import Timeline
from shared.scenarios import ExpectedToolCall as ScenarioExpectedToolCall
from shared.scenarios import Scenario
from shared.single_turn.types import ToolCallGrade

DEFAULT_JUDGE_MODEL = "gpt-5.6-terra"
DEFAULT_JUDGE_REASONING_EFFORT = "medium"
JUDGE_RUBRIC_VERSION = RUBRIC_VERSION


@dataclass(frozen=True, slots=True)
class DimensionGrade:
    """An independently applicable behavioral dimension and its evidence."""

    status: str
    passed: bool | None = None
    score: float | None = None
    rationale: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "passed": self.passed,
            "score": self.score,
            "rationale": self.rationale,
            "evidence": self.evidence,
        }


class SemanticJudgeError(RuntimeError):
    """An independent grader failed; this is not target model misbehavior."""

    failure_stage = "semantic_judge"


@dataclass(frozen=True, slots=True)
class SingleTurnGradeResult:
    """Keep Cookbook CRAWL grades independent from shared source task evidence."""

    tool_call: ToolCallGrade
    source_result: EvalResult
    evidence_metrics: dict[str, float | None]
    dimension_grades: dict[str, DimensionGrade] = field(default_factory=dict)


def _semantic_score(grade: Mapping[str, Any]) -> float:
    """Retain backward-compatible boolean grades while honoring fractional decisions."""
    score = grade.get("score")
    if isinstance(score, int | float) and not isinstance(score, bool):
        return float(score)
    return float(grade.get("status") == "passed")


def apply_semantic_grades(
    result: EvalResult,
    grades: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any] | None:
    """Reconcile assessed answer grades with the deterministic task decision."""
    achievement = grades.get("task_understanding")
    if not isinstance(achievement, Mapping) or achievement.get("status") not in {"passed", "failed"}:
        return None

    task = result.task_metrics
    deterministic_completed = bool(task.get("task_completed"))
    deterministic_satisfied = bool(task.get("requirements_satisfied"))
    semantic_completed = achievement.get("status") == "passed"
    applicable = [
        grade for grade in grades.values() if isinstance(grade, Mapping) and grade.get("status") in {"passed", "failed"}
    ]
    achievement_score = _semantic_score(achievement)
    semantic_quality = round(fmean(_semantic_score(grade) for grade in applicable), 4)
    semantic_satisfied = all(grade.get("status") == "passed" for grade in applicable)
    passed = deterministic_completed and deterministic_satisfied and semantic_completed
    task.update(
        {
            "deterministic_task_completed": deterministic_completed,
            "deterministic_requirements_satisfied": deterministic_satisfied,
            "semantic_task_completed": semantic_completed,
            "semantic_requirements_satisfied": semantic_satisfied,
            "semantic_outcome_score": achievement_score,
            "semantic_quality": semantic_quality,
            "completion_source": "llm",
            "requirements_satisfied": passed,
            "task_completed": passed,
        }
    )
    result.task_status = "passed" if passed else "incomplete"
    if isinstance(result, EvalResult):
        assessment = assess_outcome(
            result,
            semantic_completed=semantic_completed,
            strict_tools=True,
        )
        result.task_metrics["outcome_assessment"] = assessment.model_dump()
        result.task_metrics["requirements_satisfied"] = assessment.passed
        result.task_metrics["task_completed"] = assessment.passed
        result.task_status = "passed" if assessment.passed else "incomplete"

    behavioral = [
        _semantic_score(grade)
        for name, grade in grades.items()
        if name != "task_understanding" and isinstance(grade, Mapping) and grade.get("status") in {"passed", "failed"}
    ]
    rubrics: dict[str, Any] = {
        "task_understanding": {"score": achievement_score},
        "task_completion": {"completed": semantic_completed},
    }
    if behavioral:
        rubrics["semantic_quality"] = {"score": round(fmean(behavioral), 4)}
    return rubrics


def parse_json_dict(value: str) -> dict[str, Any]:
    """Parse an expected JSON object without exposing it to the target model."""
    if not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def normalize_text(value: object) -> str:
    """Match the Realtime cookbook's case and punctuation normalization."""
    return normalize_argument_text(value)


def _tool_mapping(tool_call: object) -> Mapping[str, Any]:
    if isinstance(tool_call, Mapping):
        return tool_call
    to_dict = getattr(tool_call, "to_dict", None)
    if callable(to_dict):
        result = to_dict()
        if isinstance(result, Mapping):
            return result
    return {}


def expected_args_subset(expected: Mapping[str, Any], actual: Mapping[str, Any]) -> bool:
    """Retain the cookbook's normalized, recursively matched argument subset."""
    return expected_arguments_match(expected, actual)


def compute_tool_call_grade(
    expected_tool_name: str,
    expected_tool_args_text: str,
    tool_calls: Sequence[object],
    *,
    expected_tools: Sequence[ScenarioExpectedToolCall] | None = None,
) -> dict[str, Any]:
    """Grade one legacy tool expectation or an ordered single-turn tool sequence."""
    expected_name = expected_tool_name.strip()
    expected_arguments = parse_json_dict(expected_tool_args_text)
    calls = [_tool_mapping(item) for item in tool_calls]

    if expected_tools is not None:
        wanted = list(expected_tools)
        predicted = calls[0] if calls else {}
        names_match = len(calls) == len(wanted) and all(
            observed.get("name") == expected.name for expected, observed in zip(wanted, calls, strict=False)
        )
        arguments_match = names_match and all(
            isinstance(observed.get("arguments"), Mapping)
            and expected_args_subset(expected.arguments, observed["arguments"])
            for expected, observed in zip(wanted, calls, strict=False)
        )
        return {
            "tool_call_correctness": int(names_match),
            "tool_call_arg_correctness": int(arguments_match),
            "pred_tool_call": str(predicted.get("name", "")),
            "pred_tool_call_arg": json.dumps(predicted.get("arguments", {})) if predicted else "",
        }

    if not expected_name:
        first = calls[0] if calls else {}
        return {
            "tool_call_correctness": int(not calls),
            "tool_call_arg_correctness": int(not calls),
            "pred_tool_call": str(first.get("name", "")),
            "pred_tool_call_arg": json.dumps(first.get("arguments", {})) if calls else "",
        }

    names = {str(item.get("name", "")) for item in calls}
    matching = next((item for item in calls if str(item.get("name", "")) == expected_name), None)
    predicted = matching if matching is not None else (calls[0] if calls else {})
    arguments = predicted.get("arguments", {})
    if not isinstance(arguments, Mapping):
        arguments = {}

    return {
        "tool_call_correctness": int(names == {expected_name}),
        "tool_call_arg_correctness": int(matching is not None and expected_args_subset(expected_arguments, arguments)),
        "pred_tool_call": str(predicted.get("name", "")),
        "pred_tool_call_arg": json.dumps(dict(arguments)) if predicted else "",
    }


def expected_tool_fields(scenario: Scenario) -> tuple[str, str]:
    """Return one single-turn tool expectation in the grader's normalized form."""

    if not scenario.expected.tools.required:
        return "", "{}"
    tool = scenario.expected.tools.required[0]
    return tool.name, json.dumps(tool.arguments, ensure_ascii=False, sort_keys=True)


def _reconcile_single_turn_task_evidence(
    source_result: EvalResult,
    *,
    expected_tools: Sequence[ScenarioExpectedToolCall],
    tool_grade: ToolCallGrade,
    tool_executions: Sequence[Mapping[str, Any]],
    dimensions: Mapping[str, DimensionGrade],
    initial_state: Mapping[str, Any],
    expected_state: Mapping[str, Any],
    final_state: Mapping[str, Any],
    post_tool_assistant_text: str,
) -> None:
    """Match every required application tool and argument in scenario order."""
    completed = [execution for execution in tool_executions if execution.get("status") == "completed"]
    failed = [execution for execution in tool_executions if execution.get("status") == "failed"]
    matched_count = sum(
        observed.get("name") == expected.name
        and isinstance(observed.get("arguments"), Mapping)
        and expected_args_subset(expected.arguments, observed["arguments"])
        for expected, observed in zip(expected_tools, completed, strict=False)
    )
    expected_count = len(expected_tools)
    execution_correct = matched_count == expected_count and len(completed) == expected_count and not failed
    task = source_result.task_metrics
    efficiency = source_result.efficiency_metrics
    delegation_ok = (not task.get("delegation_required") or task.get("delegation_observed")) and not (
        task.get("delegation_prohibited") and task.get("delegation_observed")
    )
    deterministic_ok = all(grade.status != "failed" for grade in dimensions.values())
    requirements_satisfied = bool(
        delegation_ok
        and tool_grade.grade
        and execution_correct
        and not task.get("prohibited_tool_call_count", 0)
        and deterministic_ok
    )

    task.update(
        {
            "task_completed": bool(task.get("conversation_completed") and requirements_satisfied),
            "requirements_satisfied": requirements_satisfied,
            "tool_call_coverage": matched_count / expected_count if expected_count else float(not completed),
            "matched_tool_call_count": matched_count,
            "expected_tool_call_count": expected_count,
            "initial_application_state": dict(initial_state),
            "expected_application_state": dict(expected_state),
            "final_application_state": dict(final_state),
            "outcome_state_satisfied": verify_final_state(expected_state, initial_state, final_state),
            "application_tool_executions": [dict(execution) for execution in tool_executions],
            "post_tool_assistant_text": post_tool_assistant_text,
        }
    )
    efficiency.update(
        {
            "matched_tool_call_count": matched_count,
            "expected_tool_call_count": expected_count,
            "unexpected_completed_tool_invocation_count": len(completed) - matched_count,
            "unique_failed_tool_invocation_count": len(failed),
        }
    )
    source_result.task_status = "passed" if task["task_completed"] else "incomplete"


def grade_single_turn_example(
    scenario: Scenario,
    tool_calls: Sequence[object],
    timeline: Timeline,
    *,
    interaction_metrics: dict[str, Any],
    turn_metrics: list[dict[str, Any]],
    user_audio_ms: int,
    run_name: str,
    tts_model: str,
    offline: bool,
    audio_source: str = "synthetic",
    tool_executions: Sequence[Mapping[str, Any]] = (),
    final_state: Mapping[str, Any] | None = None,
    initial_state: Mapping[str, Any] | None = None,
    delegations: Sequence[Mapping[str, Any]] = (),
    post_tool_assistant_text: str = "",
) -> SingleTurnGradeResult:
    """Compose typed, shared-scenario grades with the common task scorer."""
    source_result = build_result(
        scenario,
        timeline,
        caller_mode="offline_fixture" if offline else "recorded_audio" if audio_source == "recorded" else "tts",
        caller_model="" if offline or audio_source == "recorded" else tts_model,
        caller_actions={"OPENING": 1},
        caller_audio_ms=user_audio_ms,
        termination_reason="response_completed",
        interaction_metrics=interaction_metrics,
        turn_metrics=turn_metrics,
        interaction_mode="single_turn",
        audio_source=audio_source,
        run_id=run_name,
    )
    expected_name, expected_arguments = expected_tool_fields(scenario)
    expected_tools = scenario.expected.tools.required
    tool_grade = ToolCallGrade.from_mapping(
        compute_tool_call_grade(expected_name, expected_arguments, tool_calls, expected_tools=expected_tools)
    )
    dimensions = grade_deterministic_dimensions(
        scenario,
        tool_grade,
        tool_executions=tool_executions,
        final_state=dict(final_state or {}),
        initial_state=dict(initial_state or {}),
        delegations=delegations,
        post_tool_assistant_text=post_tool_assistant_text,
    )
    _reconcile_single_turn_task_evidence(
        source_result,
        expected_tools=expected_tools,
        tool_grade=tool_grade,
        tool_executions=tool_executions,
        dimensions=dimensions,
        initial_state=dict(initial_state or {}),
        expected_state=scenario.expected.state,
        final_state=dict(final_state or {}),
        post_tool_assistant_text=post_tool_assistant_text,
    )
    assessment = assess_outcome(source_result, strict_tools=True)
    source_result.task_metrics["outcome_assessment"] = assessment.model_dump()
    source_result.task_metrics["requirements_satisfied"] = assessment.passed
    source_result.task_metrics["task_completed"] = assessment.passed
    source_result.task_status = "passed" if assessment.passed else "incomplete"
    expected_tools = [{"count": 1} for _ in scenario.expected.tools.required]
    evidence = evidence_scores(
        source_result.task_metrics,
        source_result.efficiency_metrics,
        {"tool_calls": expected_tools, "total_turns": 2},
    )
    return SingleTurnGradeResult(
        tool_call=tool_grade,
        source_result=source_result,
        evidence_metrics=evidence,
        dimension_grades=dimensions,
    )


def _boolean_dimension(passed: bool, rationale: str, **evidence: Any) -> DimensionGrade:
    return DimensionGrade(
        status="passed" if passed else "failed",
        passed=passed,
        rationale=rationale,
        evidence=evidence,
    )


def verify_final_state(
    expected: Mapping[str, Any],
    initial_state: Mapping[str, Any],
    final_state: Mapping[str, Any],
) -> bool:
    """Require exact unchanged state or a recursively normalized state subset."""
    if expected.get("unchanged") is True:
        return dict(final_state) == dict(initial_state)
    return expected_args_subset(expected, final_state)


def grade_deterministic_dimensions(
    scenario: Scenario,
    tool_grade: ToolCallGrade,
    *,
    tool_executions: Sequence[Mapping[str, Any]],
    final_state: Mapping[str, Any],
    initial_state: Mapping[str, Any],
    delegations: Sequence[Mapping[str, Any]],
    post_tool_assistant_text: str,
) -> dict[str, DimensionGrade]:
    """Grade observable portable outcomes without reading semantic judge results."""
    expected_tools = scenario.expected.tools.required
    observed_delegation = bool(delegations)
    delegation_allowed = (
        scenario.expected.delegation == "optional"
        or scenario.expected.delegation == "required"
        and observed_delegation
        or scenario.expected.delegation == "forbidden"
        and not observed_delegation
    )
    completed = [item for item in tool_executions if item.get("status") == "completed"]
    failed = [item for item in tool_executions if item.get("status") == "failed"]
    execution_correct = (
        len(completed) == len(expected_tools)
        and not failed
        and all(
            observed.get("name") == expected.name
            and isinstance(observed.get("arguments"), Mapping)
            and expected_args_subset(expected.arguments, observed["arguments"])
            for expected, observed in zip(expected_tools, completed, strict=False)
        )
    )
    state_correct = verify_final_state(
        scenario.expected.state,
        initial_state,
        final_state,
    )
    dimensions = {
        "run_validity": _boolean_dimension(True, "The audio and GPT Live session completed successfully."),
        "delegation_decision": _boolean_dimension(
            delegation_allowed,
            "Compare required, optional, or forbidden delegation with the observed GPT Live delegation.",
            expected=scenario.expected.delegation,
            observed=observed_delegation,
            count=len(delegations),
        ),
        "tool_selection": _boolean_dimension(
            bool(tool_grade.tool_call_correctness),
            "Compare the observed ordered function calls with the expected functions.",
            expected=[tool.name for tool in expected_tools],
            observed=[str(item.get("name", "")) for item in completed],
        ),
        "parameter_accuracy": _boolean_dimension(
            bool(tool_grade.tool_call_arg_correctness),
            "Compare normalized observed arguments for every expected function.",
            expected=[tool.arguments for tool in expected_tools],
            observed=[item.get("arguments", {}) for item in completed],
        ),
        "tool_execution": _boolean_dimension(
            execution_correct,
            "Verify every ordered application-owned tool and reject failed, missing, or extra executions.",
            expected=[tool.name for tool in expected_tools],
            completed=len(completed),
            failed=len(failed),
        ),
        "final_state": _boolean_dimension(
            state_correct,
            "Verify the resulting application state against the expected state.",
            expected=scenario.expected.state,
            initial=dict(initial_state),
            observed=dict(final_state),
        ),
    }
    if scenario.scenario_type == "clarification":
        dimensions["clarification_behavior"] = _boolean_dimension(
            not delegations and not tool_executions and state_correct,
            "Clarification must not delegate, execute tools, or change application state.",
            delegation_count=len(delegations),
            execution_count=len(tool_executions),
            state_unchanged=state_correct,
        )
    else:
        dimensions["clarification_behavior"] = DimensionGrade(status="not_applicable")
    if expected_tools:
        dimensions["grounded_relay_order"] = _boolean_dimension(
            execution_correct and bool(post_tool_assistant_text.strip()),
            "Verify that a final audible answer followed the completed application tools.",
            completed_tools=[item.get("name") for item in completed],
            post_tool_assistant_text=post_tool_assistant_text,
        )
    else:
        dimensions["grounded_relay_order"] = DimensionGrade(status="not_applicable")
    return dimensions


def applicable_semantic_dimensions(scenario: Scenario) -> tuple[str, ...]:
    """Apply the shared semantic rubric to a single-turn scenario."""
    return shared_applicable_semantic_dimensions(scenario)


def unassessed_semantic_dimensions(scenario: Scenario) -> dict[str, DimensionGrade]:
    """Represent real offline limitations without generating mock judge grades."""
    applicable = set(applicable_semantic_dimensions(scenario))
    return {
        dimension: DimensionGrade(
            status="not_assessed" if dimension in applicable else "not_applicable",
            rationale=("Semantic judging requires a completed live evaluation." if dimension in applicable else ""),
        )
        for dimension in SEMANTIC_RUBRICS
    }


def build_semantic_judge_input(
    scenario: Scenario,
    *,
    dimension: str,
    assistant_text: str,
    delegations: Sequence[Mapping[str, Any]],
    backend_messages: Sequence[Mapping[str, Any]],
    tool_executions: Sequence[Mapping[str, Any]],
    final_state: Mapping[str, Any],
    facts: Mapping[str, Any],
) -> str:
    """Build evaluator-only evidence; never include this in target instructions."""
    if dimension not in SEMANTIC_RUBRICS:
        raise ValueError(f"Unknown semantic grading dimension: {dimension}")
    expected_name, expected_arguments = expected_tool_fields(scenario)
    payload = {
        "scenario": {
            "example_id": scenario.id,
            "scenario_type": scenario.scenario_type,
            "conversation_context": scenario.conversation_context,
            "user_request": scenario.input.text,
            "expected_response": scenario.expected.answer,
            "success_criteria": list(scenario.expected.criteria),
            "expected_delegation": scenario.expected.delegation,
            "expected_tool_call": expected_name,
            "expected_tool_args": parse_json_dict(expected_arguments),
            "expected_tool_calls": [tool.model_dump() for tool in scenario.expected.tools.required],
            "expected_final_state": scenario.expected.state,
        },
        "observed": {
            "assistant_response": assistant_text,
            "delegations": list(delegations),
            "backend_messages": list(backend_messages),
            "tool_executions": list(tool_executions),
            "initial_application_state": scenario.application.initial_state,
            "final_application_state": dict(final_state),
            "public_business_facts": {
                key: value for key, value in facts.items() if key not in {"availability_overrides"}
            },
        },
    }
    return (
        f"RUBRIC: {dimension}\n"
        f"{SEMANTIC_RUBRICS[dimension]}\n\n"
        f"EVALUATION EVIDENCE:\n{json.dumps(payload, ensure_ascii=False, sort_keys=True)}"
    )


async def judge_semantic_dimensions(
    scenario: Scenario,
    *,
    assistant_text: str,
    delegations: Sequence[Mapping[str, Any]],
    backend_messages: Sequence[Mapping[str, Any]],
    tool_executions: Sequence[Mapping[str, Any]],
    final_state: Mapping[str, Any],
    facts: Mapping[str, Any],
    client: AsyncOpenAI,
    model: str = DEFAULT_JUDGE_MODEL,
    reasoning_effort: str = DEFAULT_JUDGE_REASONING_EFFORT,
) -> tuple[dict[str, DimensionGrade], list[dict[str, Any]]]:
    """Call an independent Responses judge once for each applicable dimension."""
    applicable = applicable_semantic_dimensions(scenario)
    grades = {dimension: DimensionGrade(status="not_applicable") for dimension in SEMANTIC_RUBRICS}
    usage_events: list[dict[str, Any]] = []

    async def grade_one(dimension: str) -> tuple[str, DimensionGrade, dict[str, Any]]:
        started = time.monotonic()
        judge_input = build_semantic_judge_input(
            scenario,
            dimension=dimension,
            assistant_text=assistant_text,
            delegations=delegations,
            backend_messages=backend_messages,
            tool_executions=tool_executions,
            final_state=final_state,
            facts=facts,
        )
        try:
            response = await client.responses.parse(
                model=model,
                reasoning={"effort": reasoning_effort},
                store=False,
                input=[
                    {
                        "role": "system",
                        "content": SEMANTIC_JUDGE_SYSTEM_PROMPT,
                    },
                    {"role": "user", "content": judge_input},
                ],
                text_format=SemanticJudgeDecision,
            )
        except Exception as exc:
            raise SemanticJudgeError(f"Semantic judge failed for {dimension}: {exc}") from exc
        parsed = response.output_parsed
        if parsed is None:
            raise SemanticJudgeError(f"Semantic judge did not return a parsed decision for {dimension}")
        raw_usage = response.usage.model_dump(exclude_none=True) if response.usage is not None else {}
        usage = TokenUsage.from_mapping(raw_usage)
        latency_ms = round((time.monotonic() - started) * 1_000, 3)
        grade = DimensionGrade(
            status="passed" if parsed.passed else "failed",
            passed=parsed.passed,
            score=parsed.score,
            rationale=parsed.rationale,
            evidence={
                "support": list(parsed.evidence),
                "judge_model": model,
                "rubric_version": JUDGE_RUBRIC_VERSION,
                "latency_ms": latency_ms,
            },
        )
        usage_event = {
            "source": "evaluation_judge",
            "dimension": dimension,
            "model": model,
            "latency_ms": latency_ms,
            "total_tokens": usage.total_tokens,
            "input_tokens": usage.input_tokens,
            "cached_input_tokens": usage.cached_input_tokens,
            "output_tokens": usage.output_tokens,
        }
        return dimension, grade, usage_event

    if applicable:
        for dimension, grade, usage in await asyncio.gather(*(grade_one(name) for name in applicable)):
            grades[dimension] = grade
            # Each entry is one real, separately attributable judge call.
            usage_events.append(usage)
    return grades, usage_events
