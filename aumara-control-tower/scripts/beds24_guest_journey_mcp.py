#!/usr/bin/env python3
"""Expose the Beds24 guest-journey shadow as two read-only MCP tools."""

from __future__ import annotations

import json
import sys
from typing import Any

import beds24_guest_journey_shadow as shadow


SERVER_NAME = "aumara-beds24-guest-journey-shadow"
SERVER_VERSION = "1.0.0"
DEFAULT_PROTOCOL_VERSION = "2025-06-18"

TOOLS = [
    {
        "name": "get_guest_journey_scope",
        "title": "Get AUMARA and El Cid shadow scope",
        "description": (
            "Return the PII-free Beds24 property and room coverage used by the "
            "AUMARA/El Cid guest-journey shadow. Performs no network request."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "get_guest_journey_shadow",
        "title": "Read the live Beds24 guest-journey shadow",
        "description": (
            "Run the guarded Beds24 GET-only reader for AUMARA and all rooms "
            "under the El Cid property, returning aggregate PII-free counters. "
            "Never sends a guest message or mutates a booking."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    },
]


def _result(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(value, ensure_ascii=False, sort_keys=True),
            }
        ],
        "structuredContent": value,
        "isError": False,
    }


def _tool_error(message: str) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": message}],
        "isError": True,
    }


def _call_tool(name: str, arguments: Any) -> dict[str, Any]:
    if arguments not in (None, {}):
        return _tool_error("This read-only tool does not accept arguments.")
    try:
        if name == "get_guest_journey_scope":
            return _result(shadow.configured_scope())
        if name == "get_guest_journey_shadow":
            return _result(shadow.build_live_shadow_summary())
    except shadow.ShadowFeedError as exc:
        return _tool_error(f"Beds24 shadow unavailable: {exc}")
    except Exception:
        return _tool_error("Beds24 shadow unavailable: internal read failure")
    return _tool_error("Unknown tool.")


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def handle_request(message: dict[str, Any]) -> dict[str, Any] | None:
    """Handle one MCP JSON-RPC request without writing outside stdout."""
    request_id = message.get("id")
    method = message.get("method")
    params = message.get("params") or {}

    if method in {"notifications/initialized", "notifications/cancelled"}:
        return None
    if request_id is None:
        return None
    if method == "initialize":
        requested = params.get("protocolVersion")
        protocol_version = (
            requested if isinstance(requested, str) and requested else DEFAULT_PROTOCOL_VERSION
        )
        result = {
            "protocolVersion": protocol_version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            "instructions": (
                "Read-only AUMARA/El Cid guest-journey shadow. No guest sends "
                "and no Beds24 booking mutations are available."
            ),
        }
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        if not isinstance(params, dict) or not isinstance(params.get("name"), str):
            return _error(request_id, -32602, "Invalid tools/call parameters")
        result = _call_tool(params["name"], params.get("arguments"))
    else:
        return _error(request_id, -32601, "Method not found")
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def main() -> int:
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            response = _error(None, -32700, "Parse error")
        else:
            if not isinstance(message, dict):
                response = _error(None, -32600, "Invalid Request")
            else:
                response = handle_request(message)
        if response is not None:
            sys.stdout.write(
                json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n"
            )
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
