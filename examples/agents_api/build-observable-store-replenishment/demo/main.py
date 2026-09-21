# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "fastapi>=0.116.0",
#     "openai>=3.13.0",
#     "python-dotenv>=1.0.0",
#     "uvicorn>=0.35.0",
# ]
# ///

"""Serve an interactive store-manager replenishment demo."""

from __future__ import annotations

import argparse
import itertools
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any, Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from openai import APIError, OpenAI
from pydantic import BaseModel, Field

DEMO_DIR = Path(__file__).resolve().parent
EXAMPLE_DIR = DEMO_DIR.parent
DATA_DIR = EXAMPLE_DIR / "data"
REPO_ROOT = DEMO_DIR.parents[3]

sys.path.insert(0, str(EXAMPLE_DIR))

from replenishment_agent import (
    FOLLOW_UP_INPUT,
    MODEL,
    PLATFORM_LOGS_URL,
    Decision,
    ScenarioData,
    ToolCall,
    TurnResult,
    collect_turn,
    start_incident,
)

load_dotenv(REPO_ROOT / ".env.local")

PRESENTATION_TARGET = 20
STORM_SALES_UNITS = 20
BASELINE_TOOL_NAMES = (
    "get_inventory_position",
    "get_demand_forecast",
    "get_inbound_shipment",
    "get_replenishment_policy",
)
STORM_TOOL_NAMES = (
    "get_weather_alert",
    "get_inventory_position",
    "get_demand_forecast",
    "get_inbound_shipment",
    "get_nearby_inventory",
    "get_replenishment_policy",
)


class StartRequest(BaseModel):
    mode: Literal["guided", "live"] = "guided"


class ApprovalRequest(BaseModel):
    quantity: int = Field(ge=0)


class StormRequest(BaseModel):
    delay_hours: int = Field(ge=0, le=72)
    demand_units: int = Field(ge=10, le=80)
    nearby_units: int = Field(ge=0, le=100)


class ResolutionRequest(BaseModel):
    resolution: Literal["approved", "escalated"]


class ManagerCommandRequest(BaseModel):
    command: str = Field(min_length=2, max_length=240)
    delay_hours: int = Field(default=48, ge=0, le=72)
    demand_units: int = Field(default=50, ge=10, le=80)
    nearby_units: int = Field(default=40, ge=0, le=100)


@dataclass
class Incident:
    id: str
    mode: Literal["guided", "live"]
    scenario: ScenarioData
    first: TurnResult
    approved_restock: int | None = None
    revised: TurnResult | None = None
    resolution: str | None = None
    storm_sales: int = 0
    transfer_received: int = 0
    follow_up_restock: int = 0
    manager_log: list[dict[str, Any]] = field(default_factory=list)


INCIDENTS: dict[str, Incident] = {}
INCIDENT_LOCK = Lock()
INCIDENT_SEQUENCE = itertools.count(1)
SESSION_SEQUENCE = itertools.count(1)


def tool_call(scenario: ScenarioData, name: str) -> ToolCall:
    arguments: dict[str, Any] = {"store_id": "store_101"}
    if name != "get_weather_alert":
        arguments["sku"] = "water_24pk"
    return ToolCall(name, arguments, scenario.call(name, arguments))


def guided_first_turn(scenario: ScenarioData) -> TurnResult:
    inventory = scenario.get_inventory_position("store_101", "water_24pk")
    quantity = min(
        PRESENTATION_TARGET - inventory["shelf_units"],
        inventory["backroom_units"],
    )
    decision = Decision(
        decision="restock_from_backroom",
        quantity=quantity,
        summary=f"Move {quantity} units from the back room to reach the shelf target.",
        evidence_used=[
            f"Shelf has {inventory['shelf_units']} units.",
            f"Back room has {inventory['backroom_units']} units.",
            f"Shelf presentation target is {PRESENTATION_TARGET} units.",
        ],
        approval_required=False,
    )
    sequence = next(SESSION_SEQUENCE)
    return TurnResult(
        session_id=f"demo_session_{sequence:03d}",
        turn_id=f"demo_turn_{sequence:03d}_1",
        final_text="",
        decision=decision,
        event_types=(
            "agent.session.created",
            "agent.session.turn.in_progress",
            "agent.session.requires_action",
            "agent.session.turn.completed",
        ),
        tool_calls=tuple(tool_call(scenario, name) for name in BASELINE_TOOL_NAMES),
    )


def guided_storm_turn(incident: Incident) -> TurnResult:
    scenario = incident.scenario
    inventory = scenario.get_inventory_position("store_101", "water_24pk")
    forecast = scenario.get_demand_forecast("store_101", "water_24pk")
    shipment = scenario.get_inbound_shipment("store_101", "water_24pk")
    nearby = scenario.get_nearby_inventory("store_101", "water_24pk")
    local_units = inventory["shelf_units"] + inventory["backroom_units"]
    shortfall = max(0, forecast["forecast_units"] - local_units)
    arrival_within_horizon = 12 + shipment["delay_hours"] <= 24

    if shortfall == 0:
        decision = Decision(
            decision="wait_for_inbound",
            quantity=0,
            summary="Local inventory covers forecast demand; no transfer is needed.",
            evidence_used=[
                f"Local inventory totals {local_units} units.",
                f"Forecast demand is {forecast['forecast_units']} units.",
            ],
            approval_required=False,
        )
    elif arrival_within_horizon:
        decision = Decision(
            decision="wait_for_inbound",
            quantity=0,
            summary="The inbound truck is expected inside the demand horizon.",
            evidence_used=[
                f"Projected local shortfall is {shortfall} units.",
                f"Inbound shipment is delayed {shipment['delay_hours']} hours.",
            ],
            approval_required=False,
        )
    elif nearby["available_transfer_units"] >= shortfall:
        decision = Decision(
            decision="request_store_transfer",
            quantity=shortfall,
            summary=(
                f"Request {shortfall} units from the nearby store to cover "
                "the remaining storm demand."
            ),
            evidence_used=[
                (
                    f"{forecast['units_already_sold']} units have sold; "
                    f"{forecast['forecast_units']} units of demand remain."
                ),
                (
                    f"Local inventory is {inventory['shelf_units']} shelf units plus "
                    f"{inventory['backroom_units']} back-room units."
                ),
                f"Projected local shortfall is {shortfall} units.",
                f"Nearby store can transfer {nearby['available_transfer_units']} units.",
                f"Inbound shipment is delayed {shipment['delay_hours']} hours.",
            ],
            approval_required=True,
        )
    else:
        decision = Decision(
            decision="needs_human_review",
            quantity=shortfall,
            summary="Nearby inventory cannot cover the projected shortfall.",
            evidence_used=[
                f"Projected local shortfall is {shortfall} units.",
                f"Nearby store can transfer only {nearby['available_transfer_units']} units.",
            ],
            approval_required=True,
        )

    return TurnResult(
        session_id=incident.first.session_id,
        turn_id=f"{incident.first.session_id.replace('session', 'turn')}_2",
        final_text="",
        decision=decision,
        event_types=(
            "agent.session.turn.in_progress",
            "agent.session.requires_action",
            "agent.session.turn.completed",
        ),
        tool_calls=tuple(tool_call(scenario, name) for name in STORM_TOOL_NAMES),
    )


def serialize_turn(result: TurnResult) -> dict[str, Any]:
    return {
        "session_id": result.session_id,
        "turn_id": result.turn_id,
        "decision": asdict(result.decision),
        "events": list(dict.fromkeys(result.event_types)),
        "tool_calls": [asdict(call) for call in result.tool_calls],
        "trace_url": PLATFORM_LOGS_URL if result.session_id.startswith("sess_") else None,
    }


def scenario_snapshot(scenario: ScenarioData) -> dict[str, Any]:
    return {
        "inventory": scenario.get_inventory_position("store_101", "water_24pk"),
        "forecast": scenario.get_demand_forecast("store_101", "water_24pk"),
        "shipment": scenario.get_inbound_shipment("store_101", "water_24pk"),
        "weather": scenario.get_weather_alert("store_101"),
        "nearby": scenario.get_nearby_inventory("store_101", "water_24pk"),
    }


def serialize_incident(incident: Incident) -> dict[str, Any]:
    return {
        "incident_id": incident.id,
        "mode": incident.mode,
        "stage": (
            "resolved"
            if incident.resolution
            else "storm_review"
            if incident.revised
            else "restock_approved"
            if incident.approved_restock is not None
            else "initial_review"
        ),
        "snapshot": scenario_snapshot(incident.scenario),
        "initial_turn": serialize_turn(incident.first),
        "storm_turn": serialize_turn(incident.revised) if incident.revised else None,
        "approved_restock": incident.approved_restock,
        "resolution": incident.resolution,
        "storm_sales": incident.storm_sales,
        "transfer_received": incident.transfer_received,
        "follow_up_restock": incident.follow_up_restock,
        "manager_log": incident.manager_log,
    }


def api_error(error: APIError) -> HTTPException:
    body = error.body if isinstance(error.body, dict) else {}
    code = body.get("code")
    if code == "rate_limit_exceeded" or "rate limit" in str(error).lower():
        return HTTPException(
            status_code=429,
            detail="The live agent reached its project rate limit. Wait for the limit window to reset or use Guided mode.",
        )
    return HTTPException(status_code=502, detail=f"Agents API request failed: {error}")


def interpret_manager_command(stage: str, command: str) -> str | None:
    """Map plain-language manager input to the actions allowed at this stage."""

    words = set(command.lower().replace("-", " ").split())
    approval = bool(words & {"approve", "approved", "accept", "yes", "proceed"})
    if stage == "initial_review" and approval:
        return "approve_restock"
    if stage == "restock_approved" and words & {
        "storm",
        "weather",
        "delay",
        "delayed",
        "reassess",
        "alert",
    }:
        return "report_storm"
    if stage == "storm_review" and approval:
        return "approve_transfer"
    if stage == "storm_review" and words & {
        "escalate",
        "escalated",
        "reject",
        "hold",
        "regional",
    }:
        return "escalate"
    return None


app = FastAPI(title="Store replenishment manager demo")
app.mount("/assets", StaticFiles(directory=DEMO_DIR / "assets"), name="assets")


@app.middleware("http")
async def disable_demo_caching(request: Any, call_next: Any) -> Any:
    """Keep the local HTML, CSS, and JavaScript on the same demo revision."""

    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/")
def home() -> FileResponse:
    return FileResponse(DEMO_DIR / "index.html")


@app.get("/api/config")
def config() -> dict[str, Any]:
    scenario = ScenarioData(DATA_DIR)
    return {
        "store": "Lakeside Market",
        "store_id": "store_101",
        "sku": "water_24pk",
        "product": "Bottled water, 24 pack",
        "model": MODEL,
        "live_available": bool(os.getenv("OPENAI_API_KEY")),
        "snapshot": scenario_snapshot(scenario),
    }


@app.post("/api/incidents")
def start(request: StartRequest) -> dict[str, Any]:
    scenario = ScenarioData(DATA_DIR)
    try:
        if request.mode == "live":
            with OpenAI() as client:
                first = start_incident(client, scenario)
        else:
            first = guided_first_turn(scenario)
    except APIError as error:
        raise api_error(error) from error

    incident_id = f"incident_{next(INCIDENT_SEQUENCE):03d}"
    incident = Incident(incident_id, request.mode, scenario, first)
    incident.manager_log.append(
        {"actor": "agent", "action": "Initial shelf review completed"}
    )
    with INCIDENT_LOCK:
        INCIDENTS[incident_id] = incident
    return serialize_incident(incident)


def get_incident(incident_id: str) -> Incident:
    with INCIDENT_LOCK:
        incident = INCIDENTS.get(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found.")
    return incident


@app.post("/api/incidents/{incident_id}/approve-restock")
def approve_restock(incident_id: str, request: ApprovalRequest) -> dict[str, Any]:
    incident = get_incident(incident_id)
    expected = incident.first.decision.quantity
    if incident.approved_restock is not None:
        raise HTTPException(status_code=409, detail="The shelf move is already recorded.")
    if request.quantity != expected:
        raise HTTPException(
            status_code=400,
            detail=f"This demo expects the recommended {expected}-unit shelf move.",
        )
    incident.scenario.apply_approved_restock(request.quantity)
    incident.approved_restock = request.quantity
    incident.manager_log.append(
        {"actor": "manager", "action": f"Approved {request.quantity}-unit shelf move"}
    )
    return serialize_incident(incident)


@app.post("/api/incidents/{incident_id}/storm")
def storm(incident_id: str, request: StormRequest) -> dict[str, Any]:
    incident = get_incident(incident_id)
    if incident.approved_restock is None:
        raise HTTPException(status_code=409, detail="Approve the shelf move first.")
    if incident.revised is not None:
        raise HTTPException(status_code=409, detail="The storm was already reviewed.")

    incident.scenario.storm_delay_hours = request.delay_hours
    incident.scenario.storm_demand_units = request.demand_units
    incident.scenario.nearby_inventory[0]["available_transfer_units"] = (
        request.nearby_units
    )
    incident.scenario.activate_storm()
    inventory = incident.scenario.get_inventory_position("store_101", "water_24pk")
    incident.storm_sales = min(
        STORM_SALES_UNITS,
        request.demand_units,
        inventory["shelf_units"],
    )
    incident.scenario.apply_storm_sales(incident.storm_sales)

    try:
        if incident.mode == "live":
            with OpenAI() as client, client.beta.agents.sessions.stream(
                incident.first.session_id,
                input=FOLLOW_UP_INPUT,
            ) as events:
                revised = collect_turn(
                    client,
                    events,
                    incident.scenario,
                    session_id=incident.first.session_id,
                )
        else:
            revised = guided_storm_turn(incident)
    except APIError as error:
        raise api_error(error) from error

    incident.revised = revised
    incident.manager_log.extend(
        [
            {"actor": "system", "action": "Storm disruption received"},
            {"actor": "agent", "action": "Replenishment plan reassessed"},
        ]
    )
    return serialize_incident(incident)


@app.post("/api/incidents/{incident_id}/resolve")
def resolve(incident_id: str, request: ResolutionRequest) -> dict[str, Any]:
    incident = get_incident(incident_id)
    if incident.revised is None:
        raise HTTPException(status_code=409, detail="Review the storm event first.")
    if (
        request.resolution == "approved"
        and incident.revised.decision.decision == "request_store_transfer"
    ):
        incident.scenario.apply_approved_transfer(incident.revised.decision.quantity)
        incident.transfer_received = incident.scenario.receive_approved_transfer()
        inventory = incident.scenario.get_inventory_position("store_101", "water_24pk")
        incident.follow_up_restock = min(
            PRESENTATION_TARGET - inventory["shelf_units"],
            inventory["backroom_units"],
        )
        incident.scenario.apply_approved_restock(incident.follow_up_restock)
    incident.resolution = request.resolution
    label = (
        "Approved agent recommendation"
        if request.resolution == "approved"
        else "Escalated to regional operations"
    )
    incident.manager_log.append({"actor": "manager", "action": label})
    if incident.transfer_received:
        incident.manager_log.extend(
            [
                {
                    "actor": "store 205",
                    "action": f"Delivered {incident.transfer_received} units to receiving",
                },
                {
                    "actor": "associate",
                    "action": f"Moved {incident.follow_up_restock} units from back room to shelf",
                },
            ]
        )
    return serialize_incident(incident)


@app.post("/api/incidents/{incident_id}/manager-command")
def manager_command(
    incident_id: str, request: ManagerCommandRequest
) -> dict[str, Any]:
    """Apply a manager's typed instruction to the active store incident."""

    incident = get_incident(incident_id)
    stage = serialize_incident(incident)["stage"]
    intent = interpret_manager_command(stage, request.command)
    if intent is None:
        hints = {
            "initial_review": "Try: approve the shelf restock.",
            "restock_approved": "Try: report the storm delay.",
            "storm_review": "Try: approve the transfer, or escalate it.",
            "resolved": "This incident is resolved. Start a new shift to play again.",
        }
        return {
            "accepted": False,
            "intent": None,
            "reply": hints[stage],
            "incident": serialize_incident(incident),
        }

    if intent == "approve_restock":
        updated = approve_restock(
            incident_id,
            ApprovalRequest(quantity=incident.first.decision.quantity),
        )
        reply = (
            "Shelf recovered at 20 units. A severe storm alert just arrived; "
            "ask me to check the weather event."
        )
    elif intent == "report_storm":
        updated = storm(
            incident_id,
            StormRequest(
                delay_hours=request.delay_hours,
                demand_units=request.demand_units,
                nearby_units=request.nearby_units,
            ),
        )
        reply = "Storm recorded. The agent reassessed the same incident."
    elif intent == "approve_transfer":
        updated = resolve(incident_id, ResolutionRequest(resolution="approved"))
        reply = (
            "Approved. The Store 205 truck will unload into the back room, "
            "then Maya will place 20 on the shelf and leave 10 in reserve."
        )
    else:
        updated = resolve(incident_id, ResolutionRequest(resolution="escalated"))
        reply = "Escalated. Regional operations now owns the decision."

    return {
        "accepted": True,
        "intent": intent,
        "reply": reply,
        "incident": updated,
    }


@app.delete("/api/incidents/{incident_id}")
def reset(incident_id: str) -> dict[str, bool]:
    incident = get_incident(incident_id)
    if incident.mode == "live":
        try:
            with OpenAI() as client:
                client.beta.agents.sessions.delete(incident.first.session_id)
        except APIError:
            pass
    with INCIDENT_LOCK:
        INCIDENTS.pop(incident_id, None)
    return {"deleted": True}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8010)
    args = parser.parse_args()
    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
