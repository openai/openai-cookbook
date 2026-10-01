"""Correlate recorded assistant handoffs without exporting raw protocol data."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from assistants.frontend.transport import unwrap_response_event

TRACE_TYPES = {
    "delegation.created",
    "session.delegation.created",
    "delegation.function_call_output.created",
    "response.created",
    "response.output_item.added",
    "response.output_item.done",
    "response.output_text.done",
    "response.completed",
    "response.failed",
    "response.incomplete",
    "client_delegation.completed",
    "tool.called",
    "tool.completed",
    "tool.failed",
}


def _identifier(value: object) -> str:
    return value if isinstance(value, str) else ""


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _timestamp(event: dict[str, Any]) -> int | None:
    for key in ("timestamp_ms", "offset_ms"):
        value = event.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
    raw = event.get("_raw_live_event", event)
    for value in (raw.get("_evaluation_offset_ms"), raw.get("_relay_receipt", {}).get("media_ms")):
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
    return None


def _read_events(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    events = []
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue  # An interrupted run can leave a partial final line.
            if not isinstance(record, dict) or record.get("source") != "assistant_gpt_live":
                continue
            event = unwrap_response_event(_mapping(record.get("event")))
            if event.get("type") in TRACE_TYPES:
                events.append(event)
    return events


@dataclass
class _Delegation:
    time_ms: int | None
    target: str
    response_ids: set[str] = field(default_factory=set)
    messages: dict[str, str] = field(default_factory=dict)
    tools: dict[str, dict[str, Any]] = field(default_factory=dict)
    final_text: str = ""
    status: str = "recorded"

    def public(self) -> dict[str, Any]:
        texts = [self.final_text] if self.final_text else list(dict.fromkeys(self.messages.values()))
        return {
            "timeMs": self.time_ms,
            "target": self.target,
            "status": self.status,
            "responseCount": len(self.response_ids),
            "responses": texts,
            "toolCount": len(self.tools),
            "tools": list(self.tools.values()),
            "provenance": "protocol_trace",
        }


def _public_tool(name: str, kind: str, call_id: str, call_indexes: dict[str, int] | None) -> dict[str, Any]:
    tool: dict[str, Any] = {"name": name, "status": kind.removeprefix("tool.")}
    if call_indexes is not None and call_id in call_indexes:
        tool["toolIndex"] = call_indexes[call_id]
    return tool


def _trace_delegations(
    events: list[dict[str, Any]], call_indexes: dict[str, int] | None = None
) -> list[dict[str, Any]]:
    delegations: dict[str, _Delegation] = {}
    response_owners: dict[str, str] = {}
    for event in events:
        if event.get("type") not in {"session.delegation.created", "delegation.created"}:
            continue
        item = _mapping(event.get("delegation", event.get("item")))
        identifier = _identifier(item.get("id"))
        if not identifier:
            continue
        delegations.setdefault(identifier, _Delegation(_timestamp(event), str(item.get("target") or "responses")))
        if response_id := _identifier(item.get("response_id")):
            response_owners[response_id] = identifier

    # Managed responses identify their first response in delegation.created;
    # client responses carry delegation_id. Continuations can name a predecessor.
    for event in events:
        if event.get("type") != "response.created":
            continue
        response = _mapping(event.get("response"))
        response_id = _identifier(response.get("id"))
        owner = _identifier(event.get("delegation_id") or event.get("delegation_item_id"))
        owner = owner or response_owners.get(response_id, "")
        owner = owner or response_owners.get(_identifier(response.get("previous_response_id")), "")
        if owner in delegations and response_id:
            response_owners[response_id] = owner

    active_responses: set[str] = set()
    message_owners: dict[str, str] = {}
    call_owners: dict[str, str] = {}
    awaiting_continuation: dict[str, str] = {}
    for event in events:
        kind = event.get("type")
        item = _mapping(event.get("item"))
        response = _mapping(event.get("response"))
        response_id = _identifier(event.get("response_id") or response.get("id"))
        item_id = _identifier(event.get("item_id") or item.get("id"))
        explicit_owner = _identifier(event.get("delegation_id") or event.get("delegation_item_id"))
        owner = explicit_owner or response_owners.get(response_id, "") or message_owners.get(item_id, "")
        if kind == "delegation.function_call_output.created":
            call_id = _identifier(item.get("call_id"))
            if call_id in call_owners:
                awaiting_continuation[call_id] = call_owners[call_id]
            continue
        if kind == "response.created" and response_id:
            owner = owner or response_owners.get(_identifier(response.get("previous_response_id")), "")
            waiting_owners = set(awaiting_continuation.values())
            if not owner and not explicit_owner and not active_responses and len(waiting_owners) == 1:
                owner = next(iter(waiting_owners))
            if owner in delegations:
                response_owners[response_id] = owner
                awaiting_continuation = {
                    call_id: waiting for call_id, waiting in awaiting_continuation.items() if waiting != owner
                }
            active_responses.add(response_id)
        if not owner and not explicit_owner and not response_id and len(active_responses) == 1:
            owner = response_owners.get(next(iter(active_responses)), "")
        if kind in {"response.completed", "response.failed", "response.incomplete"}:
            active_responses.discard(response_id)
        if owner not in delegations:
            continue  # Never guess between overlapping or unidentified handoffs.
        delegation = delegations[owner]
        if kind == "response.created" and response_id:
            delegation.response_ids.add(response_id)
            delegation.status = "in_progress"
        elif kind == "response.output_item.added" and item_id:
            message_owners[item_id] = owner
        elif kind == "response.output_text.done":
            if isinstance(text := event.get("text"), str) and text.strip():
                delegation.messages[item_id or text] = text.strip()
        elif kind == "response.output_item.done" and item.get("type") == "message":
            if item.get("role") != "assistant" or item.get("status") not in {None, "completed"}:
                continue
            content = item.get("content")
            parts = content if isinstance(content, list) else []
            text = "\n".join(
                part["text"]
                for part in parts
                if isinstance(part, dict) and part.get("type") == "output_text" and isinstance(part.get("text"), str)
            ).strip()
            if text:
                delegation.messages[item_id or text] = text
        elif kind == "client_delegation.completed":
            if isinstance(text := event.get("text"), str):
                delegation.final_text = text.strip()
            delegation.status = "completed"
        elif kind in {"response.completed", "response.failed", "response.incomplete"}:
            delegation.status = str(kind).removeprefix("response.")
        elif kind in {"tool.called", "tool.completed", "tool.failed"}:
            call_id = _identifier(event.get("call_id"))
            name = _identifier(event.get("name"))
            if call_id and name:
                call_owners[call_id] = owner
                delegation.tools[call_id] = _public_tool(name, str(kind), call_id, call_indexes)
    return [item.public() for item in delegations.values()]


def build_delegation_details(
    event_path: Path,
    fallback: list[dict[str, Any]],
    *,
    call_indexes: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    """Prefer exact protocol IDs; retain timing-only markers from older artifacts."""
    details = _trace_delegations(_read_events(event_path), call_indexes)
    represented = {(item["timeMs"], item["target"]) for item in details}
    for marker in fallback:
        if (marker["timeMs"], marker["target"]) not in represented:
            details.append(
                {
                    **marker,
                    "status": "unavailable",
                    "responseCount": None,
                    "responses": [],
                    "toolCount": None,
                    "tools": [],
                    "provenance": "timeline_only",
                }
            )
    return sorted(details, key=lambda item: (item["timeMs"] is None, item["timeMs"] or 0))
