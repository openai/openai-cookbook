"""Project application calls into safe, ID-correlated transcript activity."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from run_harness.visualization.delegations import _read_events, _timestamp, build_delegation_details

_SECRET_KEY = re.compile(r"secret|password|passwd|token|authorization|credential|apikey|privatekey|cookie", re.I)
_SECRET_VALUE = re.compile(r"\bBearer\s+\S+|\bsk-[A-Za-z0-9_-]{12,}", re.I)
_KINDS = {"tool.called", "tool.completed", "tool.failed"}


def safe_arguments(value: Any) -> Any:
    """Keep application arguments, but never copy opaque text or credential fields."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            return None
    if not isinstance(value, dict | list):
        return None

    def clean(item: Any) -> Any:
        if isinstance(item, dict):
            return {
                str(key): "[redacted]" if _SECRET_KEY.search(re.sub(r"[^a-zA-Z]", "", str(key))) else clean(child)
                for key, child in item.items()
            }
        if isinstance(item, list):
            return [clean(child) for child in item]
        if isinstance(item, str):
            return _SECRET_VALUE.sub("[redacted]", item)
        return item

    return clean(value)


@dataclass
class _CallIndex:
    calls: list[dict[str, Any]] = field(default_factory=list)
    by_id: dict[str, int] = field(default_factory=dict)
    seen: set[tuple[Any, ...]] = field(default_factory=set)

    def _legacy_index(self, name: str, status: str, *, trace: bool) -> int | None:
        # Older turn traces have no IDs. Pair only unfinished same-name calls;
        # never collapse distinct identified executions.
        candidates = [i for i, call in enumerate(self.calls) if call["name"] == name and i not in self.by_id.values()]
        if status != "called" and (pending := [i for i in candidates if self.calls[i]["status"] == "called"]):
            return pending[0]
        return next(iter(candidates), None) if trace else None

    @staticmethod
    def _merge(call: dict[str, Any], event: dict[str, Any], time: int | None, status: str) -> None:
        if time is not None and (call["timeMs"] is None or time < call["timeMs"]):
            call["timeMs"] = time
        if call["status"] not in {"completed", "failed"} or status in {"completed", "failed"}:
            call["status"] = status
        if arguments := event.get("arguments"):
            sanitized = safe_arguments(arguments)
            if sanitized is not None:
                call["arguments"] = sanitized
        elif event.get("arguments") == {} and call["arguments"] is None:
            call["arguments"] = {}

    def add(self, event: dict[str, Any], *, trace: bool = False, execution: bool = False) -> None:
        kind = event.get("type") or event.get("event_type")
        if not execution and kind not in _KINDS:
            return
        name = event.get("name")
        if not isinstance(name, str) or not name or name == "unknown":
            return
        status = str(kind).removeprefix("tool.") if not execution else str(event.get("status") or "recorded")
        raw_id = event.get("call_id")
        call_id = raw_id if isinstance(raw_id, str) else ""
        time = _timestamp(event)
        signature = (call_id, name, status, time)
        if not execution and not call_id and signature in self.seen:
            return
        self.seen.add(signature)
        index = self.by_id.get(call_id) if call_id else None
        if index is None and not call_id and not execution:
            index = self._legacy_index(name, status, trace=trace)
        if index is None:
            index = len(self.calls)
            self.calls.append({"timeMs": time, "name": name, "status": status, "arguments": None})
        if call_id:
            self.by_id[call_id] = index
        self._merge(self.calls[index], event, time, status)

    def add_turns(self, turns: list[dict[str, Any]]) -> None:
        for turn in turns:
            for event in turn.get("task", {}).get("tool_calls", []):
                if isinstance(event, dict):
                    self.add(event)

    def add_missing_executions(self, executions: list[dict[str, Any]]) -> None:
        # Preserve older executions even without a lifecycle timestamp.
        recorded_names = [call["name"] for call in self.calls]
        for execution in executions:
            if not isinstance(execution, dict):
                continue
            name = execution.get("name")
            if name in recorded_names:
                recorded_names.remove(name)
            else:
                self.add(execution, execution=True)

    def associate_delegations(self, delegations: list[dict[str, Any]]) -> None:
        for delegation_index, delegation in enumerate(delegations):
            for tool in delegation["tools"]:
                if (index := tool.get("toolIndex")) is not None:
                    self.calls[index]["delegationIndex"] = delegation_index


def build_backend_activity(
    event_path: Path,
    fallback: list[dict[str, Any]],
    turns: list[dict[str, Any]],
    executions: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Merge lifecycle records without exposing protocol identifiers or tool results."""
    index = _CallIndex()
    index.add_turns(turns)
    for event in _read_events(event_path):
        index.add(event, trace=True)
    index.add_missing_executions(executions)
    delegations = build_delegation_details(event_path, fallback, call_indexes=index.by_id)
    index.associate_delegations(delegations)
    return delegations, index.calls
