"""Small helpers shared across the realtime eval harnesses."""

from typing import Any, Dict, List

from shared.graders import parse_json_dict


class ToolCallAccumulator:
    """Accumulates tool calls from the Realtime event stream.

    For these eval harnesses we only track tool calls from `response.done`, which
    includes a fully materialized `response` payload with `response["output"]`.

    This helper normalizes `response.output[]` items of type `function_call` into
    a stable list of tool calls: `{name, arguments, raw_arguments, call_id}`
    ordered by first appearance across the stream.
    """

    def __init__(self) -> None:
        self._tool_calls_by_id: Dict[str, Dict[str, Any]] = {}
        self._tool_call_order: List[str] = []

    def _ensure_entry(self, call_id: str, tool_name: str) -> Dict[str, Any]:
        entry = self._tool_calls_by_id.get(call_id)
        if entry is None:
            entry = {"name": tool_name, "raw_arguments": "", "call_id": call_id}
            self._tool_calls_by_id[call_id] = entry
            self._tool_call_order.append(call_id)
        elif tool_name:
            entry["name"] = tool_name
        return entry

    def handle_event_payload(self, payload: Dict[str, Any]) -> None:
        """Update state from a single event payload (`event.model_dump()`)."""
        event_type = payload.get("type", "")
        if event_type != "response.done":
            return

        response_payload = payload.get("response") or {}
        for output_item in response_payload.get("output") or []:
            if output_item.get("type") != "function_call":
                continue
            call_id = output_item.get("call_id") or output_item.get("id") or ""
            if not call_id:
                continue
            tool_name = output_item.get("name", "")
            entry = self._ensure_entry(call_id, tool_name)
            arguments_text = output_item.get("arguments", "") or ""
            if arguments_text:
                entry["raw_arguments"] = arguments_text

    def get_call(self, call_id: str) -> Dict[str, Any]:
        """Return the partially-built entry for a call id (or `{}` if missing)."""
        return self._tool_calls_by_id.get(call_id, {})

    def build_tool_calls(self) -> List[Dict[str, Any]]:
        """Return the final ordered list of tool calls with parsed JSON args."""
        tool_calls: List[Dict[str, Any]] = []
        for call_id in self._tool_call_order:
            entry = self._tool_calls_by_id.get(call_id, {})
            raw_arguments = entry.get("raw_arguments", "")
            parsed_arguments = parse_json_dict(raw_arguments)
            tool_calls.append(
                {
                    "name": entry.get("name", ""),
                    "arguments": parsed_arguments,
                    "raw_arguments": raw_arguments,
                    "call_id": call_id,
                }
            )
        return tool_calls
