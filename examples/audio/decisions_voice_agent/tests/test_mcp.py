import asyncio

import pytest
from cookbook_evaluation_backend import DelegationHandoff

from agent import ExampleBackend, ScriptedRouter, SupportAgent
from mcp_tools import LocalMCPTools


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
