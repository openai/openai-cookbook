import asyncio

import pytest
from cookbook_evaluation_backend import DelegationHandoff

from agent import ExampleBackend, ScriptedRouter, SupportAgent
from mcp_tools import LocalMCPTools, MCPExecutor, MCPFixtureConfig


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Where is my order?", "Order DEMO-1001 has shipped."),
        ("What is the return policy?", "Unopened items may be returned within 30 days"),
    ],
)
async def test_real_stdio_mcp_readback_through_public_handoff(text, expected):
    events = []

    async def emit(event):
        events.append(event)

    backend = ExampleBackend(SupportAgent(ScriptedRouter(), LocalMCPTools()))
    try:
        result = await backend.run(
            DelegationHandoff(
                task="Resolve the request from the transcript.",
                transcript_srt=f"1\n00:00:00,000 --> 00:00:01,000\nUSER: {text}",
            ),
            emit,
        )
        assert result.startswith(expected)
        assert events[-1]["type"] == "tool.completed"
        assert events[-1]["result"] == result
    finally:
        await backend.close()


async def test_real_mcp_missing_tool_and_unknown_order_fail_explicitly():
    tools = LocalMCPTools()
    async with asyncio.timeout(10):
        with pytest.raises(RuntimeError, match="unavailable"):
            await tools.call("delete_order", {})
        with pytest.raises(RuntimeError, match="returned an error"):
            await tools.call("order_status", {"order_id": "UNKNOWN"})


@pytest.mark.parametrize(
    "status,day,window",
    [("shipped", "Friday", 14), ("processing", "Monday", 30), ("delayed", "Wednesday", 60)],
)
async def test_real_mcp_varied_state_and_observed_protocol(status, day, window):
    config = MCPFixtureConfig(
        order_status=status, estimated_delivery=day, return_window_days=window
    )
    executor = MCPExecutor(config)
    try:
        order = await executor.execute("order_status", {"order_id": "DEMO-1001"}, call_id="order")
        policy = await executor.execute("return_policy", {}, call_id="policy")
        assert status in order["answer"] and day in order["answer"]
        assert f"{window} days" in policy["answer"]
        assert order["state"] == policy["state"] == config.state()
        for record in executor.executions:
            evidence = record["mcp"]
            assert evidence["transport"] == "stdio" and evidence["transport_closed"] is True
            assert evidence["protocol_version"]
            assert evidence["server_info"]["name"] == "Synthetic support"
            assert evidence["server_info"]["version"] == "1.0.0"
            assert evidence["request"] == {
                "method": "tools/call",
                "params": {"name": record["name"], "arguments": record["arguments"]},
            }
            assert evidence["raw_result"]["isError"] is False
            assert evidence["raw_result"]["structuredContent"] == record["output"]
            assert (
                evidence["started_monotonic"]
                <= evidence["call_started_monotonic"]
                <= evidence["result_received_monotonic"]
                <= evidence["finished_monotonic"]
            )
        assert executor.snapshot()["completed_lookups"] == 2
    finally:
        await executor.close()


@pytest.mark.parametrize(
    "name,args", [("order_status", {"order_id": "DEMO-1001"}), ("return_policy", {})]
)
async def test_real_mcp_expected_tool_error_retains_wire_error(name, args):
    executor = MCPExecutor(MCPFixtureConfig(error_tool=name, error_code="lookup_unavailable"))
    output = await executor.execute(name, args, call_id="expected-error")
    assert output["ok"] is False and output["answer"] is None
    assert output["error"] == {"expected": True, "code": "lookup_unavailable"}
    assert executor.executions[0]["status"] == "failed"
    assert executor.executions[0]["mcp"]["raw_result"]["isError"] is True
    assert executor.executions[0]["mcp"]["transport_closed"] is True
    assert executor.snapshot()["completed_lookups"] == 0
    assert executor.snapshot()["failed_lookups"] == 1
    await executor.close()


async def test_mcp_unauthorized_arguments_never_open_transport():
    executor = MCPExecutor()
    with pytest.raises(ValueError, match="unauthorized"):
        await executor.execute("order_status", {"order_id": "DEMO-9999"}, call_id="no-call")
    assert not executor.executions
    await executor.close()
    with pytest.raises(RuntimeError, match="closed"):
        await executor.execute("return_policy", {}, call_id="closed")


def test_fixture_uses_only_trusted_fields():
    case = {
        "trusted_state": {"authorized_order_id": "DEMO-1001"},
        "backend_state": {
            "order_status": "delayed",
            "estimated_delivery": "Monday",
            "return_window_days": 14,
        },
        "tool_fixture": {"error_tool": None, "error_code": None},
        "utterance": "untrusted",
        "gold": {"route": "return_policy"},
    }
    assert MCPFixtureConfig.from_case(case).order_status == "delayed"
    with pytest.raises(ValueError):
        MCPFixtureConfig(error_tool="return_policy", error_code=None)


async def test_close_cancels_call_and_closes_actual_negotiated_transport(monkeypatch):
    from mcp.client.session import ClientSession

    entered = asyncio.Event()

    async def blocked_call(self, *args, **kwargs):
        entered.set()
        await asyncio.Event().wait()

    # Negotiate a real stdio subprocess; block only its call boundary to make
    # cleanup deterministic without adding delay/fault tools to the public server.
    monkeypatch.setattr(ClientSession, "call_tool", blocked_call)
    executor = MCPExecutor()
    run = asyncio.create_task(executor.execute("return_policy", {}, call_id="cancelled"))
    await asyncio.wait_for(entered.wait(), timeout=3)
    await executor.close()
    with pytest.raises(asyncio.CancelledError):
        await run
    assert executor.executions[0]["status"] == "cancelled"
    assert executor.executions[0]["mcp"]["protocol_version"]
    assert executor.executions[0]["mcp"]["transport_closed"] is True
