"""Shared, customer-facing CRAWL and RUN evaluation metric contracts."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from crawl_harness.graders import apply_semantic_grades
from shared.grading.matching import expected_arguments_match, unique_expected_matches
from shared.metrics.reporting import METRIC_COLUMNS, build_metric_row
from shared.observability.timeline import Timeline
from shared.reporting.results import build_result_item, build_results_report
from shared.scenarios import Scenario
from shared.single_turn.grading import grade_single_turn_example
from shared.single_turn.types import (
    ExpectedToolCall,
    ResultArtifactPaths,
    ResultLatencies,
    SingleTurnEvalResult,
    ToolCallGrade,
)


def test_portable_metric_report_keeps_the_response_denominator_and_scoring_policy(tmp_path: Path) -> None:
    metrics = build_metric_row(
        task={"task_completed": True},
        efficiency={},
        golden={},
        interaction={
            "metrics_version": "2.0",
            "response_rate": 0.5,
            "config": {"response_deadline_ms": 5_000},
            "counts": {"response_count": 1, "no_response_count": 1, "response_censored_count": 1, "response_total": 2},
            "response_exclusion_reasons": {"caller_closing": 1},
        },
    )
    item = build_result_item({"example_id": "requests", **metrics}, run_dir=tmp_path, scenario_id_key="example_id")
    audio = item["metrics"]["audio"]
    assert audio["response_rate"] == 0.5
    assert audio["response_deadline_ms"] == 5_000
    assert audio["response_opportunities"] == {
        "response_count": 1,
        "no_response_count": 1,
        "response_censored_count": 1,
        "response_total": 2,
    }
    assert audio["response_exclusion_reasons"] == {"caller_closing": 1}


def test_all_harnesses_use_the_same_customer_facing_metric_contract(tmp_path: Path) -> None:
    assert METRIC_COLUMNS == (
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
    item = build_result_item(
        {
            "example_id": "sample",
            "task_completed": True,
            "tool_accuracy": 1.0,
            "tool_calls": "1/1",
            "delegation_accuracy": 1.0,
            "delegations": "1/1",
            "turns": "2/2",
            "frontend_total_tokens": 18,
            "frontend_input_tokens": 10,
            "frontend_input_audio_tokens": 6,
            "frontend_input_text_tokens": 4,
            "frontend_cached_input_tokens": 4,
            "frontend_cache_write_input_tokens": 2,
            "frontend_output_tokens": 8,
            "frontend_output_audio_tokens": 5,
            "frontend_output_text_tokens": 3,
            "backend_total_tokens": 15,
            "backend_input_tokens": 10,
            "backend_input_text_tokens": 10,
            "backend_cached_input_tokens": 4,
            "backend_cache_write_input_tokens": 3,
            "backend_output_tokens": 5,
            "backend_output_text_tokens": 5,
            "backend_output_reasoning_tokens": 2,
        },
        run_dir=tmp_path,
        scenario_id_key="example_id",
    )

    assert set(item["metrics"]) == {"task", "audio", "consumption"}
    assert item["metrics"]["task"]["semantic_quality"] == {"score": None, "dimensions": {}}
    assert item["metrics"]["task"]["tool_calls"] == {"actual": 1, "expected": 1}
    assert item["metrics"]["task"]["delegations"] == {"actual": 1, "expected": 1}
    assert item["metrics"]["task"]["turns"] == {"actual": 2, "expected": 2}
    frontend = item["metrics"]["consumption"]["frontend"]
    backend = item["metrics"]["consumption"]["backend"]
    assert frontend["total_tokens"] == 18
    assert frontend["input"]["audio_tokens"] == 6
    assert frontend["input"]["text_tokens"] == 4
    assert frontend["input"]["cached_tokens"] == 4
    assert frontend["input"]["cache_write_tokens"] == 2
    assert frontend["output"]["audio_tokens"] == 5
    assert frontend["output"]["text_tokens"] == 3
    assert backend["total_tokens"] == 15
    assert backend["input"]["text_tokens"] == 10
    assert backend["input"]["cached_tokens"] == 4
    assert backend["input"]["cache_write_tokens"] == 3
    assert backend["output"]["text_tokens"] == 5
    assert backend["output"]["reasoning_tokens"] == 2


def test_shared_metrics_show_actual_and_golden_counts_without_extra_efficiency_columns() -> None:
    metrics = build_metric_row(
        task={"task_completed": True, "matched_tool_call_count": 1},
        efficiency={
            "total_turns": 5,
            "unique_tool_invocation_count": 2,
            "matched_tool_call_count": 1,
            "delegation_count": 2,
        },
        interaction={
            "response_rate": 1.0,
            "response_latency_ms": 400,
            "interruption_rate": 0.25,
            "speaking_duration_ms": {"cumulative": 900, "maximum": 500},
            "floor_hold_silence_ms": {"cumulative": 180, "maximum": 120},
        },
        golden={"total_turns": 3, "delegations": 1, "tool_calls": [{"name": "check_availability", "count": 1}]},
        usage={
            "frontend_input_tokens": 8,
            "frontend_input_audio_tokens": 5,
            "frontend_input_text_tokens": 3,
            "frontend_cached_input_tokens": 2,
            "frontend_cache_write_input_tokens": 1,
            "backend_input_text_tokens": 11,
            "backend_cached_input_tokens": 4,
            "backend_cache_write_input_tokens": 3,
            "backend_output_tokens": 7,
            "backend_output_text_tokens": 7,
        },
    )

    assert tuple(metrics) == METRIC_COLUMNS
    assert metrics["task_completed"] is True
    assert metrics["semantic_quality"] is None
    assert metrics["tool_accuracy"] == 0.5
    assert metrics["tool_calls"] == "2/1"
    assert metrics["delegation_accuracy"] == 1.0
    assert metrics["delegations"] == "2/1"
    assert metrics["turns"] == "5/3"
    assert metrics["response_latency_ms"] == 400
    assert metrics["interruption_rate"] == 0.25
    assert metrics["speaking_duration_ms"] == {"cumulative": 900, "maximum": 500}
    assert metrics["floor_hold_silence_ms"] == {"cumulative": 180, "maximum": 120}
    assert metrics["frontend_input_tokens"] == 8
    assert metrics["frontend_input_audio_tokens"] == 5
    assert metrics["frontend_input_text_tokens"] == 3
    assert metrics["frontend_cached_input_tokens"] == 2
    assert metrics["frontend_cache_write_input_tokens"] == 1
    assert metrics["backend_input_text_tokens"] == 11
    assert metrics["backend_cached_input_tokens"] == 4
    assert metrics["backend_cache_write_input_tokens"] == 3
    assert metrics["backend_output_tokens"] == 7
    assert metrics["backend_output_text_tokens"] == 7


@pytest.mark.parametrize(
    ("expected", "actual", "matched", "prohibited", "accuracy"),
    [
        (1, 1, 1, 0, 1.0),
        (2, 1, 1, 0, 0.5),
        (1, 2, 1, 0, 0.5),
        (0, 0, 0, 0, 1.0),
        (0, 1, 0, 0, 0.0),
        (1, 1, 1, 1, 0.0),
    ],
)
def test_tool_accuracy_penalizes_missing_extra_and_prohibited_calls(
    expected: int,
    actual: int,
    matched: int,
    prohibited: int,
    accuracy: float,
) -> None:
    metrics = build_metric_row(
        task={"task_completed": True, "prohibited_tool_call_count": prohibited},
        efficiency={"unique_tool_invocation_count": actual, "matched_tool_call_count": matched},
        interaction={},
        golden={"tool_calls": [{"count": expected}] if expected else []},
    )

    assert metrics["tool_accuracy"] == accuracy


def test_tool_argument_matching_is_recursive_normalized_and_boolean_safe() -> None:
    assert expected_arguments_match(
        {"guest": {"name": "Maya Smith", "preferences": [{"location": "Window-seat"}]}},
        {
            "guest": {
                "name": "maya smith",
                "preferences": [{"location": "window seat", "priority": 1}],
                "source": "caller",
            },
            "optional": True,
        },
    )
    assert not expected_arguments_match({"confirmed": True}, {"confirmed": 1})
    assert not expected_arguments_match({"guest": {"name": "Maya"}}, {"guest": {"name": "Amaya"}})


def test_tool_accuracy_matches_each_execution_to_at_most_one_expectation() -> None:
    expected = [
        {"name": "lookup", "arguments": {"reservation_id": "R-100"}},
        {"name": "lookup", "arguments": {"reservation_id": "R-100"}},
    ]
    observed = [
        {"name": "lookup", "arguments": {"reservation_id": "R-100"}},
        {"name": "lookup", "arguments": {"reservation_id": "R-200"}},
    ]

    matched = unique_expected_matches(
        expected,
        observed,
        lambda wanted, actual: (
            wanted["name"] == actual["name"] and expected_arguments_match(wanted["arguments"], actual["arguments"])
        ),
    )
    metrics = build_metric_row(
        task={},
        efficiency={"unique_tool_invocation_count": 2, "matched_tool_call_count": len(matched)},
        interaction={},
        golden={"tool_calls": [{"count": 2}]},
    )

    assert len(matched) == 1
    assert metrics["tool_accuracy"] == 0.5


@pytest.mark.parametrize(
    ("expected", "actual", "policy", "accuracy"),
    [
        (1, 1, "required", 1.0),
        (1, 0, "required", 0.0),
        (1, 2, "required", 1.0),
        (2, 1, "required", 1.0),
        (0, 0, "forbidden", 1.0),
        (0, 1, "forbidden", 0.0),
        (0, 0, "optional", 1.0),
        (0, 1, "optional", 1.0),
    ],
)
def test_delegation_accuracy_measures_the_binary_delegation_decision(
    expected: int,
    actual: int,
    policy: str,
    accuracy: float,
) -> None:
    metrics = build_metric_row(
        task={"delegation_required": policy == "required", "delegation_prohibited": policy == "forbidden"},
        efficiency={"delegation_count": actual},
        interaction={},
        golden={"delegations": expected, "delegation_policy": policy},
    )

    assert metrics["delegation_accuracy"] == accuracy
    assert metrics["delegations"] == f"{actual}/{expected}"


def test_single_turn_results_report_every_expected_tool_and_optional_delegation(tmp_path: Path) -> None:
    expected = [
        ExpectedToolCall("check_availability", '{"date":"2026-08-07"}'),
        ExpectedToolCall("create_reservation", '{"guest_name":"Maya"}'),
    ]
    executions = [{"name": tool.name, "arguments": {}, "status": "completed"} for tool in expected]
    result = SingleTurnEvalResult(
        example_id="multi-tool",
        user_text="Check availability and book the table.",
        expected_tool_call=expected[0],
        expected_tool_calls=expected,
        assistant_text="Your reservation is confirmed.",
        tool_calls=[],
        tool_call_grade=ToolCallGrade(tool_call_correctness=1, tool_call_arg_correctness=1),
        artifact_paths=ResultArtifactPaths(tmp_path / "input.wav", tmp_path / "events.jsonl"),
        latencies=ResultLatencies(),
        delegation_count=1,
        delegation_policy="optional",
        expected_delegation=False,
        tool_executions=executions,
        task_metrics={"task_completed": True, "expected_tool_call_count": 2, "matched_tool_call_count": 2},
        efficiency_metrics={"total_turns": 2, "unique_tool_invocation_count": 2},
    )

    row = result.to_result_row()

    assert row["tool_calls"] == "2/2"
    assert row["delegation_policy"] == "optional"
    assert row["delegation_accuracy"] == 1.0
    assert row["delegations"] == "1/0"
    assert row["delegation_correctness"] == 1
    assert row["tool_execution_correctness"] == 1


def test_shared_results_preserve_optional_recording_provenance(tmp_path: Path) -> None:
    recording = {
        "id": "caller-1",
        "path": "/recordings/caller.wav",
        "condition": "noisy",
        "metadata": {"accent": "Scottish", "microphone": {"device": "headset"}},
    }

    item = build_result_item(
        {"example_id": "recorded-sample", "task_completed": True, "recording": recording},
        run_dir=tmp_path,
        scenario_id_key="example_id",
    )

    assert item["recording"] == recording


def test_fractional_semantic_quality_is_reported_without_changing_task_pass_fail(tmp_path: Path) -> None:
    item = build_result_item(
        {
            "example_id": "partially-correct",
            "task_completed": False,
            "semantic_dimension_scores": {"task_understanding": 0.4, "grounded_communication": 0.8},
        },
        run_dir=tmp_path,
        scenario_id_key="example_id",
    )

    assert item["status"] == "failed"
    assert item["metrics"]["task"]["task_completed"] is False
    assert item["metrics"]["task"]["semantic_quality"] == {
        "score": 0.6,
        "dimensions": {"task_understanding": 0.4, "grounded_communication": 0.8},
    }


def test_summary_contains_only_execution_counts_while_scenarios_retain_semantic_quality(tmp_path: Path) -> None:
    report = build_results_report(
        module="crawl",
        run_name="quality-contract",
        execution_mode="live",
        interaction="single_turn",
        dataset=tmp_path / "scenarios.json",
        configuration={},
        rows=[
            {"example_id": "partial", "task_completed": False, "semantic_dimension_scores": {"outcome": 0.4}},
            {"example_id": "complete", "task_completed": True, "semantic_dimension_scores": {"outcome": 1.0}},
            {"example_id": "offline", "task_completed": True},
            {
                "example_id": "error",
                "status": "infrastructure_error",
                "task_completed": False,
                "failure_stage": "semantic_judge",
                "semantic_dimension_scores": {"outcome": 0.0},
            },
        ],
        run_dir=tmp_path,
        scenario_id_key="example_id",
    )

    assert "semantic_quality" not in report["summary"]
    assert report["results"][0]["metrics"]["task"]["semantic_quality"]["score"] == 0.4
    assert report["results"][1]["metrics"]["task"]["semantic_quality"]["score"] == 1.0
    assert report["summary"]["failed"] == 1
    assert report["summary"]["infrastructure_errors"] == 1
    assert report["results"][2]["metrics"]["task"]["semantic_quality"]["score"] is None


def test_duration_only_frontend_omits_unavailable_token_fields(tmp_path: Path) -> None:
    item = build_result_item(
        {
            "example_id": "duration-only",
            "task_completed": True,
            "frontend_audio_duration_ms": 42_800,
            "backend_total_tokens": 3991,
            "backend_input_tokens": 3812,
            "backend_input_text_tokens": 3812,
            "backend_cached_input_tokens": 1222,
            "backend_cache_write_input_tokens": 1426,
            "backend_output_tokens": 179,
            "backend_output_text_tokens": 179,
            "backend_output_reasoning_tokens": 84,
            "backend_model_usage": [
                {"model": "gpt-5.6-terra", "total_tokens": 3991, "input_tokens": 3812, "output_tokens": 179}
            ],
        },
        run_dir=tmp_path,
        scenario_id_key="example_id",
    )

    assert item["metrics"]["consumption"]["frontend"] == {"audio_duration_ms": 42_800}
    assert item["metrics"]["consumption"]["backend"] == {
        "total_tokens": 3991,
        "input": {
            "total_tokens": 3812,
            "cached_tokens": 1222,
            "cache_write_tokens": 1426,
            "text_tokens": 3812,
        },
        "output": {"total_tokens": 179, "text_tokens": 179, "reasoning_tokens": 84},
    }


def test_backend_model_breakdown_is_retained_only_for_multiple_models(tmp_path: Path) -> None:
    models = [
        {"model": "gpt-5.6-terra", "total_tokens": 120},
        {"model": "specialist", "total_tokens": 80},
    ]
    item = build_result_item(
        {
            "example_id": "multi-model",
            "task_completed": True,
            "backend_total_tokens": 200,
            "backend_model_usage": models,
        },
        run_dir=tmp_path,
        scenario_id_key="example_id",
    )

    assert item["metrics"]["consumption"]["backend"] == {"total_tokens": 200, "models": models}


@pytest.mark.parametrize("score", [-0.1, 1.1, float("inf"), float("nan")])
def test_semantic_quality_scores_must_be_finite_and_normalized(tmp_path: Path, score: float) -> None:
    with pytest.raises(ValueError, match="between 0 and 1"):
        build_result_item(
            {"example_id": "invalid-score", "task_completed": False, "semantic_dimension_scores": {"outcome": score}},
            run_dir=tmp_path,
            scenario_id_key="example_id",
        )


def test_metrics_without_an_observed_opportunity_remain_null() -> None:
    metrics = build_metric_row(
        task={"task_completed": True},
        efficiency={"total_turns": 2, "unique_tool_invocation_count": 0},
        interaction={"response_rate": 1.0, "response_latency_ms": 400},
        golden={"total_turns": 2, "tool_calls": []},
    )

    assert metrics["interruption_rate"] is None
    assert metrics["speaking_duration_ms"] is None
    assert metrics["floor_hold_silence_ms"] is None
    assert metrics["frontend_input_tokens"] is None
    assert metrics["tool_calls"] == "0/0"


@pytest.mark.parametrize(
    ("failed_dimension", "task_passed"),
    [("task_understanding", False), ("grounded_communication", True)],
)
def test_only_semantic_task_understanding_updates_the_exported_task_decision(
    failed_dimension: str, task_passed: bool
) -> None:
    result = SimpleNamespace(
        task_metrics={"task_completed": True, "requirements_satisfied": True},
        task_status="passed",
    )
    grades = {
        "task_understanding": {"status": "passed", "passed": True},
        "grounded_communication": {"status": "passed", "passed": True},
    }
    grades[failed_dimension] = {"status": "failed", "passed": False}

    rubrics = apply_semantic_grades(result, grades)

    assert rubrics is not None
    assert result.task_metrics["deterministic_task_completed"] is True
    assert result.task_metrics["completion_source"] == "llm"
    assert result.task_metrics["task_completed"] is task_passed
    assert result.task_metrics["requirements_satisfied"] is task_passed
    assert result.task_status == ("passed" if task_passed else "incomplete")


def test_partial_semantic_credit_preserves_strict_binary_task_completion() -> None:
    result = SimpleNamespace(
        task_metrics={"task_completed": True, "requirements_satisfied": True},
        task_status="passed",
    )

    rubrics = apply_semantic_grades(
        result,
        {
            "task_understanding": {"status": "failed", "passed": False, "score": 0.45},
            "grounded_communication": {"status": "passed", "passed": True, "score": 0.8},
        },
    )

    assert rubrics == {
        "task_understanding": {"score": 0.45},
        "task_completion": {"completed": False},
        "semantic_quality": {"score": 0.8},
    }
    assert result.task_metrics["semantic_outcome_score"] == 0.45
    assert result.task_metrics["semantic_quality"] == 0.625
    assert result.task_metrics["semantic_task_completed"] is False
    assert result.task_metrics["task_completed"] is False
    assert result.task_status == "incomplete"


def test_partial_semantic_quality_cannot_override_failed_deterministic_requirements() -> None:
    result = SimpleNamespace(
        task_metrics={"task_completed": False, "requirements_satisfied": False},
        task_status="incomplete",
    )

    apply_semantic_grades(
        result,
        {"task_understanding": {"status": "passed", "passed": True, "score": 0.9}},
    )

    assert result.task_metrics["semantic_outcome_score"] == 0.9
    assert result.task_metrics["semantic_task_completed"] is True
    assert result.task_metrics["task_completed"] is False
    assert result.task_status == "incomplete"


def test_unassessed_crawl_semantic_grade_does_not_invent_an_answer_score() -> None:
    result = SimpleNamespace(
        task_metrics={"task_completed": True, "requirements_satisfied": True},
        task_status="passed",
    )

    rubrics = apply_semantic_grades(
        result,
        {"task_understanding": {"status": "not_assessed", "passed": None}},
    )

    assert rubrics is None
    assert result.task_metrics == {"task_completed": True, "requirements_satisfied": True}
    assert result.task_status == "passed"


def test_equivalent_single_turn_answer_is_not_failed_for_missing_diagnostic_phrases() -> None:
    scenario = Scenario(
        id="hours",
        title="Opening hours",
        interaction="single_turn",
        input={"text": "When are you open?"},
        expected={
            "answer": "We are open nine to five.",
            "criteria": ["Explain the opening hours."],
            "diagnostic_terms": ["nine to five"],
        },
    )
    timeline = Timeline()
    timeline.add_user_utterance(0, 200, scenario.input.text, action="OPENING")
    timeline.add_transcript(
        "assistant",
        300,
        900,
        "We open at nine in the morning and close at five in the afternoon.",
        "turn.done",
    )

    grade = grade_single_turn_example(
        scenario,
        [],
        timeline,
        interaction_metrics={"response_latencies_ms": [], "yield_latencies_ms": []},
        turn_metrics=[],
        user_audio_ms=200,
        run_name="equivalent-answer",
        tts_model="offline",
        offline=True,
    )

    assert grade.source_result.task_metrics["evidence_coverage"] == 0.0
    assert grade.source_result.task_metrics["outcome_assessment"]["passed"] is True
    assert grade.source_result.task_metrics["task_completed"] is True
