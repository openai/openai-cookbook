"""Run one observable store-replenishment incident with the Agents API."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Callable, Iterable
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from openai import APIError, OpenAI

MODEL = "gpt-6-astra"
STORE_ID = "store_101"
SKU = "water_24pk"
INCIDENT_TIME = "2026-09-18T08:15:00Z"
SCENARIO_VERSION = "store-replenishment-derived-time-v3"
PLATFORM_LOGS_URL = "https://platform.openai.com/logs?api=agents"

DECISIONS = {
    "restock_from_backroom",
    "wait_for_inbound",
    "request_store_transfer",
    "needs_human_review",
}

AGENT_INSTRUCTIONS = """You are a retail replenishment planning agent.

Use the supplied function tools for every operational fact. Do not invent inventory,
demand, shipment, weather, policy, or transfer data. Recommend an action but never
change inventory or approve a transfer yourself.

The user's stated synthetic incident time is authoritative. Evaluate timestamps
relative to that incident time and never compare them with the current real-world
date.

Return only one JSON object with these keys:
- decision: restock_from_backroom, wait_for_inbound, request_store_transfer, or needs_human_review
- quantity: a non-negative integer
- summary: one short sentence
- evidence_used: a list of short factual strings
- approval_required: a boolean

Follow the replenishment policy returned by the policy tool. If the evidence cannot
support one action or quantity, choose needs_human_review.
"""

INITIAL_INPUT = f"""A low-shelf alert fired for store {STORE_ID}, SKU {SKU}.
This synthetic incident occurs at {INCIDENT_TIME}. Evaluate all timestamps relative
to this incident time, not the current real-world date. The inventory and forecast
records generated at 08:00Z are current for this alert.
Call get_inventory_position, get_demand_forecast, get_inbound_shipment, and
get_replenishment_policy. Recommend the next action for this store.
"""

FOLLOW_UP_INPUT = f"""A severe storm event now affects store {STORE_ID}, SKU {SKU}.
The synthetic storm begins at 2026-09-18T12:00:00Z. Continue to use the synthetic
incident clock, not the current real-world date. The 24-hour storm demand window
ends at 2026-09-19T12:00:00Z.
The previously recommended shelf refill was approved and completed. Re-evaluate the
same replenishment incident. Call get_weather_alert, get_inventory_position,
get_demand_forecast, get_inbound_shipment, get_nearby_inventory, and
get_replenishment_policy before recommending the next action.
"""


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "name": "get_inventory_position",
        "description": "Return current shelf and back-room inventory for a store SKU.",
        "parameters": {
            "type": "object",
            "properties": {
                "store_id": {"type": "string"},
                "sku": {"type": "string"},
            },
            "required": ["store_id", "sku"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_demand_forecast",
        "description": "Return forecast demand for a store SKU over the next 24 hours.",
        "parameters": {
            "type": "object",
            "properties": {
                "store_id": {"type": "string"},
                "sku": {"type": "string"},
            },
            "required": ["store_id", "sku"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_inbound_shipment",
        "description": "Return the next inbound shipment and its current arrival time.",
        "parameters": {
            "type": "object",
            "properties": {
                "store_id": {"type": "string"},
                "sku": {"type": "string"},
            },
            "required": ["store_id", "sku"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_weather_alert",
        "description": "Return the active weather disruption for a store, if any.",
        "parameters": {
            "type": "object",
            "properties": {"store_id": {"type": "string"}},
            "required": ["store_id"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_nearby_inventory",
        "description": "Return inventory available for transfer from nearby stores.",
        "parameters": {
            "type": "object",
            "properties": {
                "store_id": {"type": "string"},
                "sku": {"type": "string"},
            },
            "required": ["store_id", "sku"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_replenishment_policy",
        "description": "Return the retailer's replenishment decision policy.",
        "parameters": {
            "type": "object",
            "properties": {
                "store_id": {"type": "string"},
                "sku": {"type": "string"},
            },
            "required": ["store_id", "sku"],
            "additionalProperties": False,
        },
    },
]


@dataclass(frozen=True)
class Decision:
    """Validated recommendation returned by the agent."""

    decision: str
    quantity: int
    summary: str
    evidence_used: list[str]
    approval_required: bool


@dataclass(frozen=True)
class ToolCall:
    """One application function call observed during a turn."""

    name: str
    arguments: dict[str, Any]
    output: dict[str, Any]


@dataclass(frozen=True)
class TurnResult:
    """Result and observable activity from one Agents API turn."""

    session_id: str
    turn_id: str
    final_text: str
    decision: Decision
    event_types: tuple[str, ...]
    tool_calls: tuple[ToolCall, ...]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


class ScenarioData:
    """Application-owned data returned by the function tools."""

    def __init__(
        self,
        data_dir: Path,
        *,
        storm_delay_hours: int | None = None,
        storm_demand_units: int | None = None,
        nearby_transfer_units: int | None = None,
    ) -> None:
        self.inventory = deepcopy(read_json(data_dir / "inventory.json"))
        self.forecast = read_json(data_dir / "demand_forecast.json")
        self.shipments = read_json(data_dir / "inbound_shipments.json")
        self.weather_events = read_json(data_dir / "weather_events.json")
        self.nearby_inventory = read_json(data_dir / "nearby_store_inventory.json")
        self.policy = (data_dir / "replenishment_policy.md").read_text(encoding="utf-8")
        self.phase = "baseline"
        self.storm_delay_hours = (
            storm_delay_hours
            if storm_delay_hours is not None
            else self.weather_events[0]["shipment_delay_hours"]
        )
        self.storm_demand_units = (
            storm_demand_units
            if storm_demand_units is not None
            else self.weather_events[0]["revised_demand_units"]
        )
        if nearby_transfer_units is not None:
            self.nearby_inventory[0]["available_transfer_units"] = nearby_transfer_units
        self.approved_transfer: dict[str, Any] | None = None
        self.storm_sales_units = 0

    def _inventory_record(self, store_id: str, sku: str) -> dict[str, Any]:
        return next(
            row
            for row in self.inventory
            if row["store_id"] == store_id and row["sku"] == sku
        )

    def apply_approved_restock(self, quantity: int) -> None:
        """Apply the approved first recommendation before the storm event."""

        record = self._inventory_record(STORE_ID, SKU)
        if quantity < 0 or quantity > record["backroom_units"]:
            raise ValueError("Restock quantity exceeds the available back-room stock.")
        if record["shelf_units"] + quantity > record["shelf_capacity"]:
            raise ValueError("Restock quantity exceeds shelf capacity.")
        record["shelf_units"] += quantity
        record["backroom_units"] -= quantity

    def activate_storm(self) -> None:
        self.phase = "storm"

    def apply_storm_sales(self, quantity: int) -> None:
        """Record sales that occur while the storm incident is developing."""

        record = self._inventory_record(STORE_ID, SKU)
        if quantity < 0 or quantity > record["shelf_units"]:
            raise ValueError("Storm sales exceed the shelf inventory.")
        record["shelf_units"] -= quantity
        self.storm_sales_units += quantity

    def apply_approved_transfer(self, quantity: int) -> dict[str, Any]:
        """Reserve nearby inventory after a manager approves a transfer."""

        if self.approved_transfer is not None:
            if self.approved_transfer["quantity"] != quantity:
                raise ValueError("A different transfer was already approved.")
            return deepcopy(self.approved_transfer)

        record = self.nearby_inventory[0]
        available = record["available_transfer_units"]
        if quantity <= 0 or quantity > available:
            raise ValueError("Transfer quantity exceeds nearby available inventory.")
        record["available_transfer_units"] -= quantity
        self.approved_transfer = {
            "status": "approved_for_dispatch",
            "source_store_id": record["source_store_id"],
            "destination_store_id": record["destination_store_id"],
            "sku": record["sku"],
            "quantity": quantity,
            "remaining_source_availability": record["available_transfer_units"],
        }
        return deepcopy(self.approved_transfer)

    def receive_approved_transfer(self) -> int:
        """Receive an approved nearby-store transfer into the back room."""

        if self.approved_transfer is None:
            raise ValueError("No approved transfer is available to receive.")
        if self.approved_transfer["status"] == "received":
            return self.approved_transfer["quantity"]
        quantity = self.approved_transfer["quantity"]
        record = self._inventory_record(STORE_ID, SKU)
        record["backroom_units"] += quantity
        self.approved_transfer["status"] = "received"
        return quantity

    def get_inventory_position(self, store_id: str, sku: str) -> dict[str, Any]:
        result = deepcopy(self._inventory_record(store_id, sku))
        result.update(
            incident_time=INCIDENT_TIME,
            data_status="current_for_synthetic_incident",
        )
        return result

    def get_demand_forecast(self, store_id: str, sku: str) -> dict[str, Any]:
        if store_id != self.forecast["store_id"] or sku != self.forecast["sku"]:
            raise KeyError(f"No forecast for {store_id}/{sku}.")
        total_units = (
            self.forecast["baseline_units"]
            if self.phase == "baseline"
            else self.storm_demand_units
        )
        units = max(0, total_units - self.storm_sales_units)
        return {
            "store_id": store_id,
            "sku": sku,
            "horizon_hours": self.forecast["horizon_hours"],
            "forecast_units": units,
            "total_forecast_units": total_units,
            "units_already_sold": self.storm_sales_units,
            "scenario_phase": self.phase,
            "incident_time": INCIDENT_TIME,
            "data_status": "current_for_synthetic_incident",
        }

    def get_inbound_shipment(self, store_id: str, sku: str) -> dict[str, Any]:
        shipment = next(
            row
            for row in self.shipments
            if row["store_id"] == store_id and row["sku"] == sku
        )
        result = deepcopy(shipment)
        delay = self.storm_delay_hours if self.phase == "storm" else 0
        baseline = datetime.fromisoformat(
            shipment["baseline_arrival"].replace("Z", "+00:00")
        )
        revised = baseline + timedelta(hours=delay)
        decision_time_text = (
            INCIDENT_TIME
            if self.phase == "baseline"
            else self.weather_events[0]["starts_at"]
        )
        decision_time = datetime.fromisoformat(
            decision_time_text.replace("Z", "+00:00")
        )
        hours_until_arrival = (revised - decision_time).total_seconds() / 3600
        result.update(
            delay_hours=delay,
            expected_arrival=revised.astimezone(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            decision_time=decision_time_text,
            hours_until_arrival=hours_until_arrival,
            arrives_within_24h_demand_horizon=hours_until_arrival <= 24,
            data_status="current_for_synthetic_incident",
        )
        return result

    def get_weather_alert(self, store_id: str) -> dict[str, Any]:
        if self.phase == "baseline":
            return {"store_id": store_id, "active": False}
        event = deepcopy(
            next(row for row in self.weather_events if row["store_id"] == store_id)
        )
        event.update(
            active=True,
            shipment_delay_hours=self.storm_delay_hours,
            revised_demand_units=self.storm_demand_units,
        )
        return event

    def get_nearby_inventory(self, store_id: str, sku: str) -> dict[str, Any]:
        return deepcopy(
            next(
                row
                for row in self.nearby_inventory
                if row["destination_store_id"] == store_id and row["sku"] == sku
            )
        )

    def get_replenishment_policy(self, store_id: str, sku: str) -> dict[str, Any]:
        return {"store_id": store_id, "sku": sku, "policy": self.policy}

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Dispatch an agent-requested function to application code."""

        handlers: dict[str, Callable[..., dict[str, Any]]] = {
            "get_inventory_position": self.get_inventory_position,
            "get_demand_forecast": self.get_demand_forecast,
            "get_inbound_shipment": self.get_inbound_shipment,
            "get_weather_alert": self.get_weather_alert,
            "get_nearby_inventory": self.get_nearby_inventory,
            "get_replenishment_policy": self.get_replenishment_policy,
        }
        if name not in handlers:
            raise KeyError(f"Unknown function tool: {name}")
        return handlers[name](**arguments)


def parse_decision(text: str) -> Decision:
    """Parse and validate the JSON recommendation returned by the agent."""

    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = candidate.split("\n", 1)[1].rsplit("```", 1)[0]

    decoder = json.JSONDecoder()
    payloads: list[dict[str, Any]] = []
    cursor = 0
    while (start := candidate.find("{", cursor)) != -1:
        try:
            payload, length = decoder.raw_decode(candidate[start:])
        except json.JSONDecodeError:
            cursor = start + 1
            continue
        if isinstance(payload, dict):
            payloads.append(payload)
        cursor = start + length

    if not payloads:
        raise ValueError("The agent did not return a JSON decision.")
    # A resumed session stream can replay an earlier turn before emitting the
    # current turn. The last complete object is therefore the current decision.
    payload = payloads[-1]

    required = {
        "decision",
        "quantity",
        "summary",
        "evidence_used",
        "approval_required",
    }
    if set(payload) != required:
        raise ValueError(
            f"Decision must contain exactly these keys: {sorted(required)}"
        )
    if payload["decision"] not in DECISIONS:
        raise ValueError(f"Unsupported decision: {payload['decision']}")
    if type(payload["quantity"]) is not int:
        raise TypeError("Decision quantity must be an integer.")
    if payload["quantity"] < 0:
        raise ValueError("Decision quantity must be a non-negative integer.")
    if not isinstance(payload["summary"], str):
        raise TypeError("Decision summary must be a string.")
    if not isinstance(payload["evidence_used"], list) or not all(
        isinstance(item, str) for item in payload["evidence_used"]
    ):
        raise TypeError("Decision evidence_used must be a list of strings.")
    if not isinstance(payload["approval_required"], bool):
        raise TypeError("Decision approval_required must be a boolean.")
    return Decision(**payload)


def _failure_message(event: Any) -> str:
    error = getattr(event, "error", None)
    return getattr(error, "message", None) or f"Agent failed: {event.type}"


def _submit_function_results(
    client: OpenAI,
    session_id: str,
    required_actions: Iterable[Any],
    scenario: ScenarioData,
    tool_calls: list[ToolCall],
    handled_call_ids: set[str],
    progress: Callable[[str], None],
) -> int:
    """Run and submit function calls that have not already been handled."""

    submitted = 0
    for pending in required_actions:
        action = pending.to_dict()
        if action["type"] != "function_call" or action["call_id"] in handled_call_ids:
            continue
        handled_call_ids.add(action["call_id"])
        progress(f"Tool requested: {action['name']}")
        try:
            output = scenario.call(action["name"], action["arguments"])
            tool_result = {
                "type": "agent.session.input.tool_result",
                "turn_id": action["turn_id"],
                "call_id": action["call_id"],
                "success": True,
                "output": json.dumps(output),
            }
            tool_calls.append(ToolCall(action["name"], action["arguments"], output))
        except (KeyError, TypeError, ValueError, StopIteration) as error:
            tool_result = {
                "type": "agent.session.input.tool_result",
                "turn_id": action["turn_id"],
                "call_id": action["call_id"],
                "success": False,
                "error": str(error)
                or "No matching record for the supplied tool arguments.",
            }
        client.beta.agents.sessions.events.create(
            session_id,
            events=[tool_result],
        )
        submitted += 1
    return submitted


def collect_turn(
    client: OpenAI,
    events: Iterable[Any],
    scenario: ScenarioData,
    *,
    session_id: str | None = None,
    progress: Callable[[str], None] = print,
    _text_parts: list[str] | None = None,
    _event_types: list[str] | None = None,
    _tool_calls: list[ToolCall] | None = None,
    _handled_call_ids: set[str] | None = None,
    _reported_progress: set[str] | None = None,
) -> TurnResult:
    """Run application function calls while collecting one Agents API turn."""

    turn_id: str | None = None
    text_parts = _text_parts if _text_parts is not None else []
    event_types = _event_types if _event_types is not None else []
    tool_calls = _tool_calls if _tool_calls is not None else []
    handled_call_ids = _handled_call_ids if _handled_call_ids is not None else set()
    reported_progress = _reported_progress if _reported_progress is not None else set()

    for event in events:
        event_types.append(event.type)
        if event.type == "agent.session.created":
            session_id = event.session.id
            marker = f"session:{session_id}"
            if marker not in reported_progress:
                progress(f"Session created: {session_id}")
                reported_progress.add(marker)
        elif event.type == "agent.session.turn.in_progress":
            if "turn_started" not in reported_progress:
                progress("Turn started")
                reported_progress.add("turn_started")
        elif event.type == "agent.session.requires_action":
            session_id = session_id or event.session.id
            _submit_function_results(
                client,
                session_id,
                event.session.required_actions,
                scenario,
                tool_calls,
                handled_call_ids,
                progress,
            )
        elif event.type == "agent.session.turn.output_text.delta":
            text_parts.append(event.delta)
        elif event.type == "agent.session.turn.output_text.done" and not text_parts:
            text_parts.append(event.text)
        elif event.type in {
            "error",
            "agent.session.failed",
            "agent.session.environment.failed",
            "agent.session.turn.failed",
            "agent.session.turn.cancelled",
        }:
            if getattr(getattr(event, "turn", None), "subagent_id", None) is None:
                raise RuntimeError(_failure_message(event))
        elif event.type == "agent.session.turn.completed":
            if event.turn.subagent_id is None:
                turn_id = event.turn.id
                progress(f"Turn completed: {turn_id}")
                break

    if session_id is None:
        raise RuntimeError("The event stream ended before a session was created.")
    if turn_id is None:
        session = client.beta.agents.sessions.retrieve(session_id)
        if session.status == "failed":
            raise RuntimeError(session.error or "The Agents API session failed.")
        if session.status != "requires_action":
            raise RuntimeError(
                "The event stream ended before the root turn completed "
                f"(session status: {session.status})."
            )

        # Subscribe before submitting results so no continuation events are missed.
        with client.beta.agents.sessions.events.stream(session_id) as continuation:
            submitted = _submit_function_results(
                client,
                session_id,
                session.required_actions,
                scenario,
                tool_calls,
                handled_call_ids,
                progress,
            )
            if submitted == 0:
                raise RuntimeError(
                    "The session requires action, but it has no unhandled function calls."
                )
            return collect_turn(
                client,
                continuation,
                scenario,
                session_id=session_id,
                progress=progress,
                _text_parts=text_parts,
                _event_types=event_types,
                _tool_calls=tool_calls,
                _handled_call_ids=handled_call_ids,
                _reported_progress=reported_progress,
            )
    final_text = "".join(text_parts)
    return TurnResult(
        session_id=session_id,
        turn_id=turn_id,
        final_text=final_text,
        decision=parse_decision(final_text),
        event_types=tuple(dict.fromkeys(event_types)),
        tool_calls=tuple(tool_calls),
    )


def start_incident(
    client: OpenAI,
    scenario: ScenarioData,
    *,
    model: str = MODEL,
    progress: Callable[[str], None] = print,
) -> TurnResult:
    """Start the incident and make the first replenishment recommendation."""

    with client.beta.agents.sessions.create(
        agent={
            "model": model,
            "instructions": AGENT_INSTRUCTIONS,
            "tools": TOOL_DEFINITIONS,
        },
        environment={"type": "none"},
        input=INITIAL_INPUT,
        stream=True,
    ) as events:
        created_session_id = None

        def track_session():
            nonlocal created_session_id
            for event in events:
                if event.type == "agent.session.created":
                    created_session_id = event.session.id
                yield event

        try:
            return collect_turn(client, track_session(), scenario, progress=progress)
        except Exception:
            if created_session_id:
                try:
                    client.beta.agents.sessions.delete(created_session_id)
                except APIError:
                    progress(
                        f"Cleanup failed; delete session {created_session_id} manually."
                    )
            raise


def continue_after_storm(
    client: OpenAI,
    scenario: ScenarioData,
    first: TurnResult,
    *,
    progress: Callable[[str], None] = print,
) -> TurnResult:
    """Apply the approved refill, activate the storm, and continue the session."""

    if first.decision.decision != "restock_from_backroom":
        raise ValueError("The first decision must restock from the back room.")
    scenario.apply_approved_restock(first.decision.quantity)
    scenario.activate_storm()
    with client.beta.agents.sessions.stream(
        first.session_id,
        input=FOLLOW_UP_INPUT,
    ) as events:
        return collect_turn(
            client,
            events,
            scenario,
            session_id=first.session_id,
            progress=progress,
        )


def build_trace_summary(first: TurnResult, revised: TurnResult) -> dict[str, Any]:
    """Build the application-readable trace saved by the demo and CI/CD job."""

    def turn(stage: str, result: TurnResult) -> dict[str, Any]:
        return {
            "stage": stage,
            "turn_id": result.turn_id,
            "decision": asdict(result.decision),
            "tools": [asdict(call) for call in result.tool_calls],
            "event_types": list(dict.fromkeys(result.event_types)),
        }

    return {
        "schema_version": 1,
        "scenario": "storm_delayed_store_replenishment",
        "model": MODEL,
        "platform_logs": PLATFORM_LOGS_URL,
        "session": {
            "id": first.session_id,
            "reused_for_storm_event": revised.session_id == first.session_id,
        },
        "turns": [
            turn("low shelf alert", first),
            turn("storm delayed shipment", revised),
        ],
    }


def write_outputs(
    output_dir: Path,
    first: TurnResult,
    revised: TurnResult,
) -> dict[str, Any]:
    """Write both recommendations and the application trace."""

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "initial_recommendation.json").write_text(
        json.dumps(asdict(first.decision), indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "storm_recommendation.json").write_text(
        json.dumps(asdict(revised.decision), indent=2) + "\n",
        encoding="utf-8",
    )
    summary = build_trace_summary(first, revised)
    (output_dir / "trace_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def write_github_step_summary(summary: dict[str, Any]) -> None:
    destination = os.getenv("GITHUB_STEP_SUMMARY")
    if not destination:
        return
    first, revised = summary["turns"]
    lines = [
        "## Store replenishment canary",
        "",
        f"Session: `{summary['session']['id']}`",
        "",
        "| Event | Tools | Recommendation | Quantity |",
        "| --- | --- | --- | ---: |",
        (
            f"| Low shelf alert | {', '.join(call['name'] for call in first['tools'])} "
            f"| `{first['decision']['decision']}` | {first['decision']['quantity']} |"
        ),
        (
            f"| Storm delays shipment | "
            f"{', '.join(call['name'] for call in revised['tools'])} "
            f"| `{revised['decision']['decision']}` | "
            f"{revised['decision']['quantity']} |"
        ),
        "",
        f"Inspect the full session in [OpenAI Platform Logs]({PLATFORM_LOGS_URL}).",
        "",
    ]
    with Path(destination).open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(__file__).with_name("data"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("replenishment-output"))
    parser.add_argument(
        "--check-expected-decisions",
        action="store_true",
        help="Fail unless the scenario changes from back-room restock to transfer.",
    )
    args = parser.parse_args()

    scenario = ScenarioData(args.data_dir)
    with OpenAI() as client:
        first = start_incident(client, scenario)
        try:
            revised = continue_after_storm(client, scenario, first)
            summary = write_outputs(args.output_dir, first, revised)
            write_github_step_summary(summary)
            observed = [
                first.decision.decision,
                revised.decision.decision,
            ]
            expected = ["restock_from_backroom", "request_store_transfer"]
            if args.check_expected_decisions and observed != expected:
                raise RuntimeError(f"Expected {expected}, but observed {observed}.")
            print(f"Recommendations and trace saved in {args.output_dir.resolve()}")
        finally:
            client.beta.agents.sessions.delete(first.session_id)


if __name__ == "__main__":
    main()
