"""Keep JSON containers and nulls distinct from normalized argument text."""

from typing import Any

import pytest

from shared.grading.matching import expected_arguments_match
from shared.grading.scoring import build_result
from shared.observability.timeline import AgentEvent, Timeline
from shared.scenarios import Scenario


@pytest.mark.parametrize(
    ("wanted", "observed"),
    [(None, "None"), ("Maya", ["Maya"]), ("", []), ("", {}), ("{'name': 'Maya'}", {"name": "Maya"})],
)
@pytest.mark.parametrize("reverse", [False, True])
def test_mismatched_json_types_do_not_match(wanted: Any, observed: Any, reverse: bool) -> None:
    if reverse:
        wanted, observed = observed, wanted
    assert not expected_arguments_match({"value": wanted}, {"value": observed})
    assert not expected_arguments_match({"nested": {"value": wanted}}, {"nested": {"value": observed}})
    assert not expected_arguments_match({"items": [wanted]}, {"items": [observed]})


@pytest.mark.parametrize(
    ("wanted", "observed"),
    [
        (None, None),
        ("Maya Smith!", "maya smith"),
        ("window-seat", "Window seat"),
        (2, 2.0),
        (2, "2"),
        (True, True),
        ({}, {"extra": 1}),
        ([], ["extra"]),
        ({"name": "Maya"}, {"name": "maya", "extra": 1}),
        ([None, {"name": "Maya"}], [None, {"name": "maya", "extra": 1}, "suffix"]),
    ],
)
def test_existing_matching_rules_are_preserved(wanted: Any, observed: Any) -> None:
    assert expected_arguments_match({"value": wanted}, {"value": observed})


def test_missing_keys_and_boolean_number_mismatches_remain_rejected() -> None:
    assert not expected_arguments_match({"value": None}, {})
    assert not expected_arguments_match({"value": True}, {"value": 1})
    assert not expected_arguments_match({"value": 1}, {"value": True})


@pytest.mark.parametrize("observed", [None, "None"])
def test_result_does_not_credit_text_for_a_required_null_argument(observed: Any) -> None:
    scenario = Scenario.model_validate(
        {
            "id": "clear-preference",
            "title": "Clear a seating preference",
            "interaction": "single_turn",
            "input": {"text": "Clear my seating preference."},
            "expected": {
                "answer": "Your seating preference has been cleared.",
                "tools": {"required": [{"name": "set_preference", "arguments": {"preference": None}}]},
            },
        }
    )
    timeline = Timeline()
    timeline.agent_events = [
        AgentEvent(
            10,
            "tool.completed",
            "tool",
            name="set_preference",
            status="completed",
            arguments={"preference": observed},
            call_id="preference-1",
        )
    ]
    result = build_result(
        scenario,
        timeline,
        caller_mode="offline_fixture",
        termination_reason="user_stopped",
        turn_metrics=[{"start_ms": 0, "window_end_ms": 100, "action": "STOP"}],
    )
    satisfied = observed is None
    assert result.task_metrics["matched_tool_call_count"] == int(satisfied)
    assert result.turn_metrics[0]["task"]["requirements_satisfied"] is satisfied
    assert result.efficiency_metrics["seconds_to_requirements"] == (0.1 if satisfied else None)
