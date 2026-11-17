"""Required tool progress counts distinct invocations, not matching projections."""

from __future__ import annotations

import pytest

from shared.grading.scoring import build_result
from shared.observability.timeline import Timeline
from shared.scenarios import Scenario
from shared.single_turn.grading import grade_single_turn_example


def _scenario(required_count: int = 2, *, status: str = "completed") -> Scenario:
    return Scenario(
        id="repeated-actions",
        title="Repeated actions",
        interaction="single_turn",
        input={"text": "Record the requested actions."},
        expected={
            "answer": "The requested actions were recorded.",
            "criteria": ["Record every requested action."],
            "tools": {
                "required": [{"name": "record_action", "arguments": {"value": 2}, "status": status}] * required_count
            },
        },
    )


def _turns() -> list[dict]:
    return [
        {"start_ms": 0, "window_end_ms": 100, "action": "OPENING"},
        {"start_ms": 100, "window_end_ms": 200, "action": "SPEAK"},
        {"start_ms": 200, "window_end_ms": 300, "action": "STOP"},
    ]


def _timeline(invocation_count: int) -> Timeline:
    timeline = Timeline()
    for index in range(invocation_count):
        timeline.apply_event(
            {
                "type": "tool.completed",
                "offset_ms": 150 + index * 100,
                "call_id": f"action-{index}",
                "name": "record_action",
                "arguments": {"value": 2},
                "result": {"recorded": True},
            }
        )
    return timeline


@pytest.mark.parametrize("invocation_count", [0, 1, 2])
def test_required_tool_progress_counts_each_distinct_invocation_once(invocation_count: int) -> None:
    result = build_result(
        _scenario(),
        _timeline(invocation_count),
        caller_mode="offline_fixture",
        termination_reason="response_completed",
        turn_metrics=_turns(),
    )

    assert result.task_metrics["tool_call_coverage"] == invocation_count / 2
    assert result.task_metrics["matched_tool_call_count"] == invocation_count
    assert result.efficiency_metrics["matched_tool_call_count"] == invocation_count
    assert result.task_metrics["requirements_satisfied"] is (invocation_count == 2)
    assert result.task_metrics["task_completed"] is (invocation_count == 2)
    assert len(result.criteria[0]["evidence"]["missing_tool_calls"]) == 2 - invocation_count
    tasks = [turn["task"] for turn in result.turn_metrics]
    assert [task["tool_call_coverage"] for task in tasks] == [0.0, min(invocation_count, 1) / 2, invocation_count / 2]
    assert [task["requirements_satisfied"] for task in tasks] == [False, False, invocation_count == 2]
    assert [len(task["new_matched_tool_calls"]) for task in tasks] == [
        0,
        min(invocation_count, 1),
        invocation_count // 2,
    ]
    assert result.efficiency_metrics["seconds_to_requirements"] == (0.3 if invocation_count == 2 else None)


def test_duplicate_terminal_projections_do_not_satisfy_repeated_requirements() -> None:
    timeline = _timeline(1)
    timeline.apply_event(
        {
            "type": "tool.completed",
            "offset_ms": 250,
            "call_id": "action-0",
            "name": "record_action",
            "arguments": {"value": 2},
            "result": {"recorded": True},
        }
    )
    result = build_result(
        _scenario(),
        timeline,
        caller_mode="offline_fixture",
        termination_reason="response_completed",
        turn_metrics=_turns(),
    )

    assert result.task_metrics["tool_call_coverage"] == 0.5
    assert result.task_metrics["requirements_satisfied"] is False
    assert result.efficiency_metrics["unique_tool_invocation_count"] == 1
    assert result.efficiency_metrics["seconds_to_requirements"] is None
    tasks = [turn["task"] for turn in result.turn_metrics]
    assert [task["tool_call_coverage"] for task in tasks] == [0.0, 0.5, 0.5]
    assert [len(task["new_matched_tool_calls"]) for task in tasks] == [0, 1, 0]
    assert [len(task["tool_calls"]) for task in tasks] == [0, 1, 1]


def test_tool_progress_does_not_use_arguments_from_a_later_projection() -> None:
    timeline = Timeline()
    for timestamp_ms, arguments in [(150, {}), (250, {"value": 2})]:
        timeline.apply_event(
            {
                "type": "tool.completed",
                "offset_ms": timestamp_ms,
                "call_id": "action-0",
                "name": "record_action",
                "arguments": arguments,
            }
        )
    result = build_result(
        _scenario(),
        timeline,
        caller_mode="offline_fixture",
        termination_reason="response_completed",
        turn_metrics=_turns(),
    )

    assert [turn["task"]["tool_call_coverage"] for turn in result.turn_metrics] == [0.0, 0.0, 0.5]
    assert result.task_metrics["tool_call_coverage"] == 0.5
    assert result.efficiency_metrics["seconds_to_requirements"] is None


def test_single_turn_grade_does_not_report_early_completion_for_a_missing_repeat() -> None:
    execution = {"name": "record_action", "arguments": {"value": 2}, "status": "completed"}
    grade = grade_single_turn_example(
        _scenario(),
        [execution],
        _timeline(1),
        interaction_metrics={},
        turn_metrics=_turns(),
        user_audio_ms=0,
        run_name="missing-repeat",
        tts_model="offline",
        offline=True,
        tool_executions=[execution],
    )

    result = grade.source_result
    assert result.task_metrics["matched_tool_call_count"] == 1
    assert result.task_metrics["task_completed"] is False
    assert result.turn_metrics[-1]["task"]["tool_call_coverage"] == 0.5
    assert result.turn_metrics[-1]["task"]["requirements_satisfied"] is False
    assert result.efficiency_metrics["seconds_to_requirements"] is None


def test_no_required_tools_preserves_full_coverage() -> None:
    result = build_result(
        _scenario(required_count=0),
        Timeline(),
        caller_mode="offline_fixture",
        termination_reason="response_completed",
        turn_metrics=_turns(),
    )

    assert result.task_metrics["tool_call_coverage"] == 1.0
    assert result.task_metrics["matched_tool_call_count"] == 0
    assert result.task_metrics["task_completed"] is True
    assert all(turn["task"]["tool_call_coverage"] == 1.0 for turn in result.turn_metrics)
    assert result.efficiency_metrics["seconds_to_requirements"] == 0.1


@pytest.mark.parametrize("status", ["any", "completed"])
def test_called_only_evidence_preserves_required_status_semantics(status: str) -> None:
    timeline = Timeline()
    timeline.apply_event(
        {
            "type": "tool.called",
            "offset_ms": 150,
            "call_id": "action-0",
            "name": "record_action",
            "arguments": {"value": 2},
        }
    )
    result = build_result(
        _scenario(required_count=1, status=status),
        timeline,
        caller_mode="offline_fixture",
        termination_reason="response_completed",
        turn_metrics=_turns(),
    )

    accepted = status == "any"
    assert result.task_metrics["tool_call_coverage"] == float(accepted)
    assert result.task_metrics["requirements_satisfied"] is accepted
    assert [turn["task"]["tool_call_coverage"] for turn in result.turn_metrics] == [
        0.0,
        float(accepted),
        float(accepted),
    ]
    assert result.efficiency_metrics["seconds_to_requirements"] == (0.2 if accepted else None)
    assert result.efficiency_metrics["unique_tool_invocation_count"] == 0


def test_called_and_completed_projections_match_only_one_required_any_call() -> None:
    timeline = Timeline()
    for event_type, timestamp_ms in [("tool.called", 150), ("tool.completed", 250)]:
        timeline.apply_event(
            {
                "type": event_type,
                "offset_ms": timestamp_ms,
                "call_id": "action-0",
                "name": "record_action",
                "arguments": {"value": 2},
            }
        )
    result = build_result(
        _scenario(status="any"),
        timeline,
        caller_mode="offline_fixture",
        termination_reason="response_completed",
        turn_metrics=_turns(),
    )

    assert result.task_metrics["tool_call_coverage"] == 0.5
    assert result.task_metrics["requirements_satisfied"] is False
    assert [turn["task"]["tool_call_coverage"] for turn in result.turn_metrics] == [0.0, 0.5, 0.5]
    assert result.efficiency_metrics["seconds_to_requirements"] is None
