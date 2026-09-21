from __future__ import annotations

import json
import sys
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

EXAMPLE_DIR = Path(__file__).parents[1]
sys.path.insert(0, str(EXAMPLE_DIR))

from generate_dataset import write_dataset
from replenishment_agent import (
    INCIDENT_TIME,
    INITIAL_INPUT,
    SCENARIO_VERSION,
    Decision,
    ScenarioData,
    ToolCall,
    TurnResult,
    build_trace_summary,
    collect_turn,
    continue_after_storm,
    parse_decision,
    start_incident,
    write_github_step_summary,
    write_outputs,
)

DATA_DIR = EXAMPLE_DIR / "data"


def test_initial_input_anchors_the_synthetic_incident_clock():
    assert SCENARIO_VERSION == "store-replenishment-derived-time-v3"
    assert INCIDENT_TIME in INITIAL_INPUT
    assert "not the current real-world date" in INITIAL_INPUT


def event(event_type: str, **values):
    return SimpleNamespace(type=event_type, **values)


def decision_text(decision: str, quantity: int, approval: bool) -> str:
    return json.dumps(
        {
            "decision": decision,
            "quantity": quantity,
            "summary": "Synthetic recommendation.",
            "evidence_used": ["Synthetic evidence."],
            "approval_required": approval,
        }
    )


def completed_stream(
    *,
    session_id: str = "sess_123",
    turn_id: str = "turn_123",
    text: str,
    include_created: bool = True,
    required_actions=(),
):
    events = []
    if include_created:
        events.append(
            event("agent.session.created", session=SimpleNamespace(id=session_id))
        )
    events.append(event("agent.session.turn.in_progress"))
    if required_actions:
        events.append(
            event(
                "agent.session.requires_action",
                session=SimpleNamespace(
                    id=session_id,
                    required_actions=required_actions,
                ),
            )
        )
    events.extend(
        [
            event("agent.session.turn.output_text.delta", delta=text),
            event(
                "agent.session.turn.completed",
                turn=SimpleNamespace(id=turn_id, subagent_id=None),
            ),
        ]
    )
    return events


class PendingAction:
    def __init__(self, name: str, arguments: dict):
        self.name = name
        self.arguments = arguments

    def to_dict(self):
        return {
            "type": "function_call",
            "turn_id": "turn_123",
            "call_id": f"call_{self.name}",
            "name": self.name,
            "arguments": self.arguments,
        }


class FakeEventAPI:
    def __init__(self, continuation=()):
        self.submissions = []
        self.continuation = continuation

    def create(self, session_id, *, events):
        self.submissions.append((session_id, events))

    def stream(self, session_id):
        return nullcontext(self.continuation)


class FakeSessions:
    def __init__(self, *, continuation=(), retrieved_session=None):
        self.create_kwargs = None
        self.stream_args = None
        self.events = FakeEventAPI(continuation)
        self.retrieved_session = retrieved_session

    def create(self, **kwargs):
        self.create_kwargs = kwargs
        return nullcontext(
            completed_stream(text=decision_text("restock_from_backroom", 16, False))
        )

    def stream(self, session_id, **kwargs):
        self.stream_args = (session_id, kwargs)
        return nullcontext(
            completed_stream(
                session_id=session_id,
                turn_id="turn_456",
                text=decision_text("request_store_transfer", 26, True),
                include_created=False,
            )
        )

    def retrieve(self, session_id):
        return self.retrieved_session


def fake_client(sessions=None):
    sessions = sessions or FakeSessions()
    return SimpleNamespace(
        beta=SimpleNamespace(agents=SimpleNamespace(sessions=sessions))
    )


def make_turn(
    decision: str,
    quantity: int,
    *,
    turn_id: str,
    approval: bool,
) -> TurnResult:
    parsed = Decision(
        decision=decision,
        quantity=quantity,
        summary="Synthetic recommendation.",
        evidence_used=["Synthetic evidence."],
        approval_required=approval,
    )
    return TurnResult(
        session_id="sess_123",
        turn_id=turn_id,
        final_text=json.dumps(parsed.__dict__),
        decision=parsed,
        event_types=("agent.session.turn.in_progress", "agent.session.turn.completed"),
        tool_calls=(
            ToolCall(
                "get_inventory_position",
                {"store_id": "store_101", "sku": "water_24pk"},
                {"shelf_units": 4, "backroom_units": 20},
            ),
        ),
    )


def test_generator_reproduces_committed_dataset(tmp_path: Path):
    write_dataset(tmp_path)

    expected = sorted(path.name for path in DATA_DIR.iterdir())
    generated = sorted(path.name for path in tmp_path.iterdir())
    assert generated == expected
    for filename in expected:
        assert (tmp_path / filename).read_text() == (DATA_DIR / filename).read_text()


def test_scenario_starts_with_one_clear_inventory_position():
    scenario = ScenarioData(DATA_DIR)

    inventory = scenario.get_inventory_position("store_101", "water_24pk")
    forecast = scenario.get_demand_forecast("store_101", "water_24pk")
    shipment = scenario.get_inbound_shipment("store_101", "water_24pk")

    assert inventory["shelf_units"] == 4
    assert inventory["backroom_units"] == 20
    assert forecast["forecast_units"] == 18
    assert shipment["delay_hours"] == 0


def test_storm_changes_the_same_incident_data():
    scenario = ScenarioData(DATA_DIR)
    scenario.apply_approved_restock(16)
    scenario.activate_storm()

    inventory = scenario.get_inventory_position("store_101", "water_24pk")
    forecast = scenario.get_demand_forecast("store_101", "water_24pk")
    shipment = scenario.get_inbound_shipment("store_101", "water_24pk")
    weather = scenario.get_weather_alert("store_101")

    assert inventory["shelf_units"] == 20
    assert inventory["backroom_units"] == 4
    assert forecast["forecast_units"] == 50
    assert shipment["delay_hours"] == 48
    assert shipment["hours_until_arrival"] == 56
    assert shipment["arrives_within_24h_demand_horizon"] is False
    assert weather["active"] is True


def test_manager_approval_reserves_transfer_without_instant_delivery():
    scenario = ScenarioData(DATA_DIR)
    scenario.apply_approved_restock(16)
    scenario.activate_storm()

    before = scenario.get_inventory_position("store_101", "water_24pk")
    transfer = scenario.apply_approved_transfer(26)
    after = scenario.get_inventory_position("store_101", "water_24pk")
    nearby = scenario.get_nearby_inventory("store_101", "water_24pk")

    assert transfer["status"] == "approved_for_dispatch"
    assert transfer["quantity"] == 26
    assert nearby["available_transfer_units"] == 14
    assert after == before


def test_received_transfer_restores_back_room_and_storm_depleted_shelf():
    scenario = ScenarioData(DATA_DIR)
    scenario.apply_approved_restock(16)
    scenario.activate_storm()
    scenario.apply_storm_sales(20)

    forecast = scenario.get_demand_forecast("store_101", "water_24pk")
    assert forecast["forecast_units"] == 30
    assert forecast["units_already_sold"] == 20

    scenario.apply_approved_transfer(26)
    assert scenario.receive_approved_transfer() == 26
    scenario.apply_approved_restock(20)
    inventory = scenario.get_inventory_position("store_101", "water_24pk")

    assert inventory["shelf_units"] == 20
    assert inventory["backroom_units"] == 10
    assert scenario.get_nearby_inventory("store_101", "water_24pk")[
        "available_transfer_units"
    ] == 14


def test_playground_overrides_storm_values():
    scenario = ScenarioData(
        DATA_DIR,
        storm_delay_hours=24,
        storm_demand_units=42,
        nearby_transfer_units=12,
    )
    scenario.activate_storm()

    assert scenario.get_inbound_shipment("store_101", "water_24pk")["delay_hours"] == 24
    assert (
        scenario.get_demand_forecast("store_101", "water_24pk")["forecast_units"] == 42
    )
    assert (
        scenario.get_nearby_inventory("store_101", "water_24pk")[
            "available_transfer_units"
        ]
        == 12
    )


def test_parse_decision_validates_the_agent_contract():
    decision = parse_decision(decision_text("restock_from_backroom", 16, False))

    assert decision.decision == "restock_from_backroom"
    assert decision.quantity == 16
    assert decision.approval_required is False

    with pytest.raises(ValueError, match="Unsupported decision"):
        parse_decision(decision_text("ship_from_moon", 16, False))


def test_parse_decision_tolerates_identical_replayed_output():
    text = decision_text("restock_from_backroom", 16, False)

    decision = parse_decision(text + text)

    assert decision.decision == "restock_from_backroom"
    assert decision.quantity == 16


def test_parse_decision_uses_latest_decision_from_resumed_stream():
    decision = parse_decision(
        decision_text("restock_from_backroom", 16, False)
        + decision_text("request_store_transfer", 26, True)
    )

    assert decision.decision == "request_store_transfer"
    assert decision.quantity == 26
    assert decision.approval_required is True


def test_collect_turn_runs_required_application_function():
    sessions = FakeSessions()
    client = fake_client(sessions)
    scenario = ScenarioData(DATA_DIR)
    action = PendingAction(
        "get_inventory_position",
        {"store_id": "store_101", "sku": "water_24pk"},
    )
    stream = completed_stream(
        text=decision_text("restock_from_backroom", 16, False),
        required_actions=(action,),
    )

    result = collect_turn(client, stream, scenario, progress=lambda _: None)

    assert result.session_id == "sess_123"
    assert result.decision.quantity == 16
    assert [call.name for call in result.tool_calls] == ["get_inventory_position"]
    session_id, submitted = sessions.events.submissions[0]
    assert session_id == "sess_123"
    assert submitted[0]["type"] == "agent.session.input.tool_result"
    assert submitted[0]["success"] is True


def test_collect_turn_recovers_required_action_when_stream_closes_early():
    action = PendingAction(
        "get_inventory_position",
        {"store_id": "store_101", "sku": "water_24pk"},
    )
    continuation = completed_stream(
        text=decision_text("restock_from_backroom", 16, False),
        include_created=False,
    )
    sessions = FakeSessions(
        continuation=continuation,
        retrieved_session=SimpleNamespace(
            status="requires_action",
            required_actions=(action,),
            error=None,
        ),
    )
    interrupted_stream = [
        event("agent.session.created", session=SimpleNamespace(id="sess_123")),
        event("agent.session.turn.in_progress"),
    ]

    result = collect_turn(
        fake_client(sessions),
        interrupted_stream,
        ScenarioData(DATA_DIR),
        progress=lambda _: None,
    )

    assert result.turn_id == "turn_123"
    assert result.decision.quantity == 16
    assert [call.name for call in result.tool_calls] == ["get_inventory_position"]
    assert len(sessions.events.submissions) == 1


def test_start_incident_configures_function_tools_without_a_sandbox():
    sessions = FakeSessions()

    result = start_incident(
        fake_client(sessions),
        ScenarioData(DATA_DIR),
        progress=lambda _: None,
    )

    assert result.decision.decision == "restock_from_backroom"
    assert sessions.create_kwargs["environment"] == {"type": "none"}
    assert sessions.create_kwargs["stream"] is True
    assert len(sessions.create_kwargs["agent"]["tools"]) == 6


def test_continue_after_storm_reuses_session_and_updates_data():
    sessions = FakeSessions()
    scenario = ScenarioData(DATA_DIR)
    first = make_turn(
        "restock_from_backroom",
        16,
        turn_id="turn_123",
        approval=False,
    )

    revised = continue_after_storm(
        fake_client(sessions),
        scenario,
        first,
        progress=lambda _: None,
    )

    assert revised.session_id == first.session_id
    assert revised.decision.decision == "request_store_transfer"
    assert sessions.stream_args[0] == "sess_123"
    assert scenario.phase == "storm"
    assert (
        scenario.get_inventory_position("store_101", "water_24pk")["backroom_units"]
        == 4
    )


def test_trace_and_output_files_make_the_story_visible(tmp_path: Path):
    first = make_turn(
        "restock_from_backroom",
        16,
        turn_id="turn_123",
        approval=False,
    )
    revised = make_turn(
        "request_store_transfer",
        26,
        turn_id="turn_456",
        approval=True,
    )

    summary = write_outputs(tmp_path, first, revised)

    assert summary == build_trace_summary(first, revised)
    assert summary["session"]["reused_for_storm_event"] is True
    assert [turn["decision"]["decision"] for turn in summary["turns"]] == [
        "restock_from_backroom",
        "request_store_transfer",
    ]
    assert (tmp_path / "initial_recommendation.json").exists()
    assert (tmp_path / "storm_recommendation.json").exists()
    assert (tmp_path / "trace_summary.json").exists()


def test_github_summary_contains_decisions_and_trace_link(tmp_path: Path, monkeypatch):
    destination = tmp_path / "github-summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(destination))
    first = make_turn(
        "restock_from_backroom",
        16,
        turn_id="turn_123",
        approval=False,
    )
    revised = make_turn(
        "request_store_transfer",
        26,
        turn_id="turn_456",
        approval=True,
    )

    write_github_step_summary(build_trace_summary(first, revised))

    rendered = destination.read_text(encoding="utf-8")
    assert "restock_from_backroom" in rendered
    assert "request_store_transfer" in rendered
    assert "OpenAI Platform Logs" in rendered
