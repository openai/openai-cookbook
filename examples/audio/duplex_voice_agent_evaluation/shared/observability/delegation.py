"""Correlated delegated-work state shared by live observation and metric replay.

This is local accounting, not a new Live API contract. In particular, the client
controller's correlated error is normalized into a terminal event for replay.
Unknown IDs never finish another operation; incomplete evidence stays pending.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def lifecycle_event(event: dict[str, Any], timestamp_ms: int) -> dict[str, Any] | None:
    """Retain only fields needed to replay lifecycle state, not tool payloads."""
    kind = str(event.get("type", ""))
    if kind == "delegation.created":
        event = {**event, "delegation": event.get("item", {})}
        kind = "session.delegation.created"
    error = event.get("error") if isinstance(event.get("error"), dict) else {}
    if kind == "error" and error.get("code") == "client_delegation_failed" and event.get("delegation_id"):
        kind = "client_delegation.failed"
    if kind not in {
        "session.delegation.created",
        "client_delegation.completed",
        "client_delegation.failed",
        "response.created",
        "response.completed",
        "response.failed",
        "response.incomplete",
        "tool.called",
        "tool.completed",
        "tool.failed",
    }:
        return None
    item = event.get("delegation") if kind == "session.delegation.created" else event.get("item")
    item = item if isinstance(item, dict) else {}
    response = event.get("response") if isinstance(event.get("response"), dict) else {}
    return {
        "type": kind,
        "offset_ms": max(0, timestamp_ms),
        "delegation_id": str(
            event.get("delegation_id") or (item.get("id") if kind == "session.delegation.created" else "") or ""
        ),
        "response_id": str(event.get("response_id") or item.get("response_id") or response.get("id") or ""),
        "previous_response_id": str(event.get("previous_response_id") or response.get("previous_response_id") or ""),
        "call_id": str(event.get("call_id") or item.get("call_id") or ""),
        "target": str(item.get("target", event.get("target", "responses"))),
    }


@dataclass
class DelegationState:
    clients: set[str] = field(default_factory=set)
    responses: set[str] = field(default_factory=set)
    # Keys are call IDs, never tool names: parallel lookup calls are distinct.
    calls: dict[tuple[str, str], str] = field(default_factory=dict)
    followups: set[str] = field(default_factory=set)
    response_owners: dict[str, str] = field(default_factory=dict)
    started_responses: set[str] = field(default_factory=set)
    delegation_targets: dict[str, str] = field(default_factory=dict)
    unbound: set[str] = field(default_factory=set)
    finished_calls: set[tuple[str, str]] = field(default_factory=set)
    continued_responses: set[str] = field(default_factory=set)
    finished_clients: set[str] = field(default_factory=set)
    finished_responses: set[str] = field(default_factory=set)
    failed_responses: set[str] = field(default_factory=set)

    @property
    def active(self) -> bool:
        return bool(self.clients or self.responses or self.calls or self.followups or self.unbound)

    def apply(self, event: dict[str, Any]) -> None:
        kind = event["type"]
        if kind == "session.delegation.created":
            self._start_delegation(event)
        elif kind in {"client_delegation.completed", "client_delegation.failed"}:
            self._finish_client(event.get("delegation_id", ""))
        elif kind == "response.created":
            self._start_response(event)
        elif kind == "tool.called":
            self._start_tool(event)
        elif kind in {"tool.completed", "tool.failed"}:
            self._finish_tool(event)
        elif kind in {"response.completed", "response.failed", "response.incomplete"}:
            self._finish_response(event)

    def _start_delegation(self, event: dict[str, Any]) -> None:
        delegation_id = event.get("delegation_id", "")
        response_id = event.get("response_id", "")
        self.delegation_targets[delegation_id] = event.get("target", "responses")
        if event.get("target") == "client":
            if delegation_id not in self.finished_clients:
                self.clients.add(delegation_id or "unknown-client")
        elif response_id:
            if response_id not in self.finished_responses:
                self.responses.add(response_id)
        else:
            self.unbound.add(delegation_id or "unknown-responses")

    def _finish_client(self, delegation_id: str) -> None:
        self.clients.discard(delegation_id)
        if delegation_id:
            # IDs identify one operation. Retain a tombstone when a local
            # completion reaches us before the corresponding start receipt.
            self.finished_clients.add(delegation_id)
        owned = {key for key, owner in self.response_owners.items() if owner == delegation_id and owner}
        self.responses.difference_update(owned)
        self.finished_responses.update(owned)
        self.followups.difference_update(owned)
        self.calls = {key: owner for key, owner in self.calls.items() if owner != delegation_id or not owner}

    def _start_response(self, event: dict[str, Any]) -> None:
        delegation_id = event.get("delegation_id", "")
        response_id = event.get("response_id", "")
        previous = event.get("previous_response_id", "")
        if response_id in self.started_responses:
            return
        if response_id:
            self.started_responses.add(response_id)
        if delegation_id and self.delegation_targets.get(delegation_id) == "responses":
            for key in list(self.followups):
                if key != response_id and self.response_owners.get(key) == delegation_id:
                    self.followups.discard(key)
                    self.continued_responses.add(key)
        if previous:
            self.followups.discard(previous)
            self.continued_responses.add(previous)
        if response_id in self.finished_responses or delegation_id in self.finished_clients:
            # A late start still carries its parent's continuation proof.
            return
        if (
            not previous
            and not delegation_id
            and len(self.followups) == 1
            and not self.responses
            and not self.calls
            and not self.unbound
        ):
            # Legacy serial traces omit previous_response_id. Only infer the
            # continuation when exactly one completed chain can own it.
            self.followups.clear()
        if delegation_id in self.unbound:
            self.unbound.discard(delegation_id)
        elif not delegation_id and len(self.unbound) == 1 and not self.responses:
            # An explicit different owner is evidence against legacy inference.
            self.unbound.clear()
        if response_id:
            self.responses.add(response_id)
            if delegation_id:
                self.response_owners[response_id] = delegation_id
        else:
            self.unbound.add("unknown-responses")

    def _start_tool(self, event: dict[str, Any]) -> None:
        delegation_id = event.get("delegation_id", "")
        response_id = event.get("response_id", "")
        call_id = event.get("call_id", "")
        if (
            delegation_id in self.finished_clients
            or response_id in self.failed_responses
            or (response_id, call_id) in self.finished_calls
        ):
            return
        self.calls[(response_id, call_id)] = delegation_id

    def _finish_tool(self, event: dict[str, Any]) -> None:
        delegation_id = event.get("delegation_id", "")
        response_id = event.get("response_id", "")
        call_id = event.get("call_id", "")
        key = (response_id, call_id)
        if key in self.finished_calls or response_id in self.failed_responses or delegation_id in self.finished_clients:
            return
        if key in self.calls or call_id:
            owner = self.calls.pop(key, "") or delegation_id or self.response_owners.get(response_id, "")
            if call_id:
                # The terminal may arrive before its unique start receipt.
                self.finished_calls.add(key)
            # Client work ends at its explicit terminal event. Managed
            # Responses tools require the subsequent response, not merely
            # a successful function return, before the handoff is complete.
            if (
                not owner or self.delegation_targets.get(owner) == "responses"
            ) and response_id not in self.continued_responses:
                self.followups.add(response_id)

    def _finish_response(self, event: dict[str, Any]) -> None:
        response_id = event.get("response_id", "")
        self.responses.discard(response_id)
        if response_id:
            self.finished_responses.add(response_id)
        if event["type"] in {"response.failed", "response.incomplete"}:
            if response_id:
                self.failed_responses.add(response_id)
            # One failed backend response must not erase another response's
            # active call or awaiting-followup state.
            self.calls = {key: owner for key, owner in self.calls.items() if key[0] != response_id}
            self.followups.discard(response_id)


def active_intervals(events: list[dict[str, Any]], duration_ms: int) -> tuple[tuple[int, int], ...]:
    """Return the union of active work clipped to the actual observation window."""
    state = DelegationState()
    start: int | None = None
    intervals: list[tuple[int, int]] = []
    for event in sorted(events, key=lambda item: item["offset_ms"]):
        timestamp = int(event["offset_ms"])
        if timestamp > duration_ms:
            break
        was_active = state.active
        state.apply(event)
        if state.active and not was_active:
            start = timestamp
        elif was_active and not state.active and start is not None:
            if timestamp > start:
                intervals.append((start, timestamp))
            start = None
    if start is not None and duration_ms > start:
        intervals.append((start, duration_ms))
    # Same-timestamp terminal/start events create no acoustic silence boundary.
    merged: list[tuple[int, int]] = []
    for left, right in intervals:
        if merged and left <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], right))
        else:
            merged.append((left, right))
    return tuple(merged)
