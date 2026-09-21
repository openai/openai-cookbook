from __future__ import annotations

import sys
from pathlib import Path

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
