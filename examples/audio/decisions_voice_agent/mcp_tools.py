"""A real local MCP SDK client; the subprocess never needs API credentials."""

import sys
from pathlib import Path

from mcp import Client, StdioServerParameters
from mcp.types import TextContent


class LocalMCPTools:
    """Open one bounded-lifetime stdio session per read-only lookup.

    Startup is intentionally included in this offline example. Do not treat its
    runtime as a warm production MCP latency measurement.
    """

    async def call(self, name: str, arguments: dict[str, str]) -> str:
        parameters = StdioServerParameters(
            command=sys.executable,
            args=[str(Path(__file__).with_name("support_server.py"))],
        )
        async with Client(parameters) as client:
            tools = await client.list_tools()
            if name not in {tool.name for tool in tools.tools}:
                error, text = "Required support tool is unavailable", ""
            else:
                result = await client.call_tool(name, arguments)
                text = "\n".join(
                    part.text for part in result.content if isinstance(part, TextContent)
                )
                error = "Support tool returned an error" if result.is_error else ""
        # Raise application-level failures after the SDK has closed its task groups.
        if error:
            raise RuntimeError(error)
        if not text.strip():
            raise RuntimeError("Support tool returned no text")
        return text
