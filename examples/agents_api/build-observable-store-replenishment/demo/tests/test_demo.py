from __future__ import annotations

import sys
from contextlib import nullcontext
from copy import deepcopy
from pathlib import Path

import httpx
import pytest
from openai import APIConnectionError

DEMO_DIR = Path(__file__).parents[1]
EXAMPLE_DIR = DEMO_DIR.parent
sys.path.insert(0, str(DEMO_DIR))
sys.path.insert(0, str(EXAMPLE_DIR))

from main import (
    Incident,
    guided_first_turn,
    guided_storm_turn,
    interpret_manager_command,
)
from replenishment_agent import ScenarioData

DATA_DIR = EXAMPLE_DIR / "data"


@pytest.mark.parametrize(
    "command",
    [
        "Do not approve this transfer",
        "Don't approve the shelf restock",
        "Do not proceed",
        "Should I approve this transfer?",
        "approve but wait",
    ],
)
@pytest.mark.parametrize("stage", ["initial_review", "storm_review"])
def test_ambiguous_or_negative_commands_never_approve(command, stage):
    assert interpret_manager_command(stage, command) is None


@pytest.mark.parametrize("delay", [13, 14, 15, 16])
def test_guided_storm_uses_inclusive_shipment_horizon(delay):
    _, revised = storm_decision(delay=delay, demand=50, nearby=40)
    assert revised.decision.decision == "wait_for_inbound"


def prepared_incident():
    import main

    result = main.start(main.StartRequest())
    incident_id = result["incident_id"]
    main.approve_restock(incident_id, main.ApprovalRequest(quantity=16))
    return main.get_incident(incident_id)


def test_initial_negative_command_leaves_stock_unchanged():
    import main

    initial = main.start(main.StartRequest())
    result = main.manager_command(
        initial["incident_id"],
        main.ManagerCommandRequest(command="Don't approve the shelf restock"),
    )
    assert result["accepted"] is False
    assert result["incident"]["snapshot"] == initial["snapshot"]


@pytest.mark.parametrize("delay,nearby", [(12, 40), (48, 10)])
def test_non_transfer_approval_rejected(delay, nearby):
    import main

    incident = prepared_incident()
    main.storm(
        incident.id,
        main.StormRequest(delay_hours=delay, demand_units=50, nearby_units=nearby),
    )
    before = deepcopy(incident.scenario.__dict__)
    with pytest.raises(main.HTTPException, match="No transfer was recommended"):
        main.resolve(incident.id, main.ResolutionRequest(resolution="approved"))
    assert incident.resolution is None
    assert incident.scenario.__dict__ == before


def test_adjusted_transfer_reply_matches_snapshot():
    import main

    incident = prepared_incident()
    main.storm(
        incident.id, main.StormRequest(delay_hours=48, demand_units=52, nearby_units=40)
    )
    result = main.manager_command(
        incident.id, main.ManagerCommandRequest(command="Approve this transfer")
    )
    assert "28 units" in result["reply"]
    assert "12 in reserve" in result["reply"]
    assert result["incident"]["snapshot"]["inventory"]["backroom_units"] == 12


def test_failed_live_storm_preserves_local_state_and_retry(monkeypatch):
    from types import SimpleNamespace

    import main

    incident = prepared_incident()
    incident.mode = "live"
    before = deepcopy(incident.__dict__)
    sessions = SimpleNamespace(stream=lambda *a, **k: nullcontext([]))
    monkeypatch.setattr(
        main,
        "OpenAI",
        lambda: nullcontext(
            SimpleNamespace(
                beta=SimpleNamespace(agents=SimpleNamespace(sessions=sessions))
            )
        ),
    )

    def fail(*args, **kwargs):
        raise APIConnectionError(request=httpx.Request("POST", "https://example.test"))

    monkeypatch.setattr(main, "collect_turn", fail)
    request = main.StormRequest(delay_hours=48, demand_units=50, nearby_units=40)
    with pytest.raises(main.HTTPException):
        main.storm(incident.id, request)
    assert incident.scenario.__dict__ == before["scenario"].__dict__
    assert incident.storm_sales == 0
    assert incident.revised is None
    incident.mode = "guided"
    result = main.storm(incident.id, request)
    assert result["storm_sales"] == 20


def storm_decision(*, delay: int, demand: int, nearby: int):
    scenario = ScenarioData(DATA_DIR)
    first = guided_first_turn(scenario)
    scenario.apply_approved_restock(first.decision.quantity)
    scenario.storm_delay_hours = delay
    scenario.storm_demand_units = demand
    scenario.nearby_inventory[0]["available_transfer_units"] = nearby
    scenario.activate_storm()
    incident = Incident("incident_test", "guided", scenario, first)
    return first, guided_storm_turn(incident)


def test_guided_first_turn_uses_same_story_as_the_notebook():
    scenario = ScenarioData(DATA_DIR)

    result = guided_first_turn(scenario)

    assert result.decision.decision == "restock_from_backroom"
    assert result.decision.quantity == 16
    assert [call.name for call in result.tool_calls] == [
        "get_inventory_position",
        "get_demand_forecast",
        "get_inbound_shipment",
        "get_replenishment_policy",
    ]


def test_guided_storm_requests_transfer_when_nearby_store_covers_gap():
    first, revised = storm_decision(delay=48, demand=50, nearby=40)

    assert revised.session_id == first.session_id
    assert revised.decision.decision == "request_store_transfer"
    assert revised.decision.quantity == 26
    assert revised.decision.approval_required is True


def test_guided_storm_waits_when_truck_is_inside_demand_horizon():
    _, revised = storm_decision(delay=12, demand=50, nearby=40)

    assert revised.decision.decision == "wait_for_inbound"
    assert revised.decision.quantity == 0


def test_guided_storm_escalates_when_nearby_store_cannot_cover_gap():
    _, revised = storm_decision(delay=48, demand=50, nearby=10)

    assert revised.decision.decision == "needs_human_review"
    assert revised.decision.quantity == 26


def test_manager_commands_follow_the_active_incident_stage():
    assert (
        interpret_manager_command("initial_review", "Approve the shelf restock")
        == "approve_restock"
    )
    assert (
        interpret_manager_command("restock_approved", "Report the storm delay")
        == "report_storm"
    )
    assert (
        interpret_manager_command("storm_review", "Approve this transfer")
        == "approve_transfer"
    )
    assert interpret_manager_command("storm_review", "Hold and escalate") == "escalate"
    assert interpret_manager_command("initial_review", "Show me the weather") is None
