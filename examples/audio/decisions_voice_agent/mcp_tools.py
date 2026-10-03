"""Official MCP stdio transport, synthetic fixture execution and observed evidence."""

import asyncio
import copy
import json
import sys
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mcp import Client, StdioServerParameters
from mcp.types import CallToolResult

from support_server import MCPFixtureConfig


async def _exchange(name: str, arguments: dict, config: MCPFixtureConfig, evidence: dict):
    """One cold stdio session and one tools/call; no continuation or retry loop."""
    parameters = StdioServerParameters(
        command=sys.executable,
        args=[
            str(Path(__file__).with_name("support_server.py")),
            "--fixture-json",
            json.dumps(asdict(config)),
        ],
    )
    evidence.update(
        transport="stdio",
        transport_closed=False,
        started_at=datetime.now(UTC).isoformat(),
        started_monotonic=time.monotonic(),
    )
    try:
        async with asyncio.timeout(5):
            pending_error = None
            async with Client(parameters) as client:
                evidence.update(
                    protocol_version=client.protocol_version,
                    server_info=(
                        client.server_info.model_dump(mode="json", by_alias=True)
                        if client.server_info
                        else None
                    ),
                )
                try:
                    listed = await client.list_tools()
                    evidence["listed_tools"] = [tool.name for tool in listed.tools]
                    if name not in evidence["listed_tools"]:
                        raise RuntimeError("Required support tool is unavailable")
                    evidence["request"] = {
                        "method": "tools/call",
                        "params": {"name": name, "arguments": arguments},
                    }
                    # Timestamp the SDK invocation, not an inferred socket write.
                    evidence["call_started_monotonic"] = time.monotonic()
                    # The high-level client can continue input_required results.
                    # This example requires exactly one bounded tool request.
                    result = await client.session.call_tool(
                        name,
                        arguments,
                        read_timeout_seconds=3,
                        allow_input_required=False,
                        allow_claimed=False,
                    )
                    evidence["result_received_monotonic"] = time.monotonic()
                    if not isinstance(result, CallToolResult):
                        raise RuntimeError("Unexpected MCP tool response")
                    evidence["raw_result"] = result.model_dump(mode="json", by_alias=True)
                except BaseException as error:
                    pending_error = error
            # Only record closure after the SDK's context exit completes.
            evidence["transport_closed"] = True
            if pending_error is not None:
                raise pending_error
            return result
    except BaseException as error:
        evidence["transport_error"] = type(error).__name__
        raise
    finally:
        evidence["finished_monotonic"] = time.monotonic()
        evidence["finished_at"] = datetime.now(UTC).isoformat()


class LocalMCPTools:
    """The standalone demo's string-returning adapter; each lookup includes startup."""

    async def call(self, name: str, arguments: dict[str, str]) -> str:
        result = await _exchange(name, arguments, MCPFixtureConfig(), {})
        output = result.structured_content
        if result.is_error:
            raise RuntimeError("Support tool returned an error")
        if not isinstance(output, dict) or not isinstance(output.get("answer"), str):
            raise RuntimeError("Support tool returned no text")
        return output["answer"]


class MCPExecutor:
    """Session-owned asynchronous executor; actual MCP records feed service traces."""

    def __init__(self, config: MCPFixtureConfig | None = None):
        self.config = config or MCPFixtureConfig()
        self.executions: list[dict[str, Any]] = []
        self._active: asyncio.Task | None = None
        self._closed = False
        self._observed_state: dict | None = None

    async def execute(self, name: str, arguments: dict, *, call_id: str) -> dict:
        if self._closed or (self._active and not self._active.done()):
            raise RuntimeError("MCP executor is closed or busy")
        if not (
            (name == "order_status" and arguments == {"order_id": "DEMO-1001"})
            or (name == "return_policy" and arguments == {})
        ):
            raise ValueError("Unsupported or unauthorized support lookup")
        self._active = asyncio.current_task()
        record = {
            "call_id": call_id,
            "name": name,
            "arguments": copy.deepcopy(arguments),
            "status": "pending",
            "output": None,
            "mcp": {},
        }
        self.executions.append(record)
        try:
            result = await _exchange(name, arguments, self.config, record["mcp"])
            output = result.structured_content
            if not isinstance(output, dict) or output.get("state") != self.config.state():
                raise RuntimeError("MCP returned invalid synthetic state")
            expected_error = (
                result.is_error
                and self.config.error_tool == name
                and output.get("ok") is False
                and output.get("error") == {"code": "lookup_unavailable", "expected": True}
                and output.get("answer") is None
            )
            if not expected_error and (
                result.is_error
                or output.get("ok") is not True
                or not isinstance(output.get("answer"), str)
                or not output["answer"].strip()
            ):
                raise RuntimeError("Unexpected MCP tool failure or malformed output")
            record.update(status="failed" if expected_error else "completed", output=output)
            self._observed_state = copy.deepcopy(output["state"])
            return copy.deepcopy(output)
        except BaseException as error:
            record.update(
                status="cancelled" if isinstance(error, asyncio.CancelledError) else "failed",
                output={"ok": False, "error": {"code": type(error).__name__, "expected": False}},
            )
            raise
        finally:
            self._active = None

    def snapshot(self) -> dict:
        return {
            "authorized_order_id": self.config.authorized_order_id,
            "completed_lookups": sum(x["status"] == "completed" for x in self.executions),
            "failed_lookups": sum(x["status"] == "failed" for x in self.executions),
            "observed_backend_state": copy.deepcopy(self._observed_state),
        }

    async def close(self) -> None:
        self._closed = True
        work = self._active
        if work is not None and work is not asyncio.current_task() and not work.done():
            work.cancel()
            _, pending = await asyncio.wait({work}, timeout=5)
            if pending:
                raise RuntimeError("MCP executor cleanup deadline exceeded")
