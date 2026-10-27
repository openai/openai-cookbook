"""Required tool progress counts distinct invocations, not matching projections."""

from __future__ import annotations

import pytest

from shared.grading.scoring import build_result
from shared.observability.timeline import AgentEvent, Timeline
from shared.scenarios import Scenario
from shared.single_turn.grading import grade_single_turn_example


def _scenario() -> Scenario:
    return Scenario.model_validate(
        {
            "id": "two-reservations",
            "title": "Make two separate reservations",
            "interaction": "single_turn",
            "input": {"text": "Make two separate reservations for two at 7 PM."},
            "expected": {
                "answer": "Two reservations created.",
                "tools": {
                    "required": [
                        {"name": "create_reservation", "arguments": {"party_size": 2}},
                        {"name": "create_reservation", "arguments": {"party_size": 2}},
                    ]
                },
            },
        }
    )


def _grade(count: int):
    scenario = _scenario()
    timeline = Timeline()
    timeline.add_transcript("assistant", 110, 200, "Done.", "fixture")
    timeline.agent_events = [
        AgentEvent(
            i,
            "tool.completed",
            "tool",
            name="create_reservation",
            status="completed",
            arguments={"party_size": 2},
            call_id=f"call-{i}",
        )
        for i in range(count)
    ]
    executions = [event.model_dump() for event in timeline.agent_events]
    return grade_single_turn_example(
        scenario,
        executions,
        timeline,
        interaction_metrics={},
        turn_metrics=[{"start_ms": 0, "window_end_ms": 200, "action": "OPENING"}],
        user_audio_ms=0,
        run_name="offline-repro",
        tts_model="",
        offline=True,
        tool_executions=executions,
    )


@pytest.mark.parametrize(
    ("count", "coverage", "satisfied", "seconds"),
    [
        (0, 0.0, False, None),
        (1, 0.5, False, None),
        (2, 1.0, True, 0.2),
    ],
)
def test_issue_3220_progress_needs_each_required_call(
    count: int, coverage: float, satisfied: bool, seconds: float | None
) -> None:
    result = _grade(count).source_result
    turn_task = result.turn_metrics[0]["task"]
    assert result.task_metrics["matched_tool_call_count"] == count
    assert turn_task["tool_call_coverage"] == coverage
    assert turn_task["requirements_satisfied"] is satisfied
    assert result.efficiency_metrics["seconds_to_requirements"] == seconds


def test_duplicate_call_id_projections_count_once() -> None:
    scenario = _scenario()
    timeline = Timeline()
    for offset, call_id in ((150, "call-0"), (160, "call-0"), (250, "call-1")):
        timeline.apply_event(
            {
                "type": "tool.completed",
                "offset_ms": offset,
                "call_id": call_id,
                "name": "create_reservation",
                "arguments": {"party_size": 2},
                "result": {"ok": True},
            }
        )
    result = build_result(
        scenario,
        timeline,
        caller_mode="offline_fixture",
        termination_reason="response_completed",
        turn_metrics=[
            {"start_ms": 0, "window_end_ms": 100, "action": "OPENING"},
            {"start_ms": 100, "window_end_ms": 200, "action": "SPEAK"},
            {"start_ms": 200, "window_end_ms": 300, "action": "STOP"},
        ],
    )
    assert result.task_metrics["matched_tool_call_count"] == 2
    assert result.task_metrics["tool_call_coverage"] == 1.0
    assert [turn["task"]["tool_call_coverage"] for turn in result.turn_metrics] == [0.0, 0.5, 1.0]


def test_one_invocation_cannot_satisfy_two_identical_requirements() -> None:
    scenario = _scenario()
    timeline = Timeline()
    timeline.apply_event(
        {
            "type": "tool.completed",
            "offset_ms": 150,
            "call_id": "call-0",
            "name": "create_reservation",
            "arguments": {"party_size": 2},
            "result": {"ok": True},
        }
    )
    result = build_result(
        scenario,
        timeline,
        caller_mode="offline_fixture",
        termination_reason="response_completed",
        turn_metrics=[{"start_ms": 0, "window_end_ms": 200, "action": "OPENING"}],
    )
    assert result.task_metrics["matched_tool_call_count"] == 1
    assert result.task_metrics["tool_call_coverage"] == 0.5
    assert result.task_metrics["requirements_satisfied"] is False
    assert result.turn_metrics[0]["task"]["requirements_satisfied"] is False
    assert result.efficiency_metrics["seconds_to_requirements"] is None
