"""Local read-only synthetic MCP server with application-owned fixture settings."""

import argparse
import json
from dataclasses import asdict, dataclass
from typing import Any

from mcp.server import MCPServer
from mcp.types import CallToolResult, TextContent, ToolAnnotations


@dataclass(frozen=True)
class MCPFixtureConfig:
    authorized_order_id: str = "DEMO-1001"
    order_status: str = "shipped"
    estimated_delivery: str = "Friday"
    return_window_days: int = 30
    error_tool: str | None = None
    error_code: str | None = None

    def __post_init__(self):
        if (
            self.authorized_order_id != "DEMO-1001"
            or self.order_status not in {"shipped", "processing", "delayed"}
            or self.estimated_delivery not in {"Friday", "Monday", "Wednesday"}
            or type(self.return_window_days) is not int
            or self.return_window_days not in {14, 30, 60}
            or (self.error_tool, self.error_code)
            not in {
                (None, None),
                ("order_status", "lookup_unavailable"),
                ("return_policy", "lookup_unavailable"),
            }
        ):
            raise ValueError("Unsupported synthetic MCP fixture configuration")

    @classmethod
    def from_case(cls, case: dict[str, Any]) -> "MCPFixtureConfig":
        """Consume trusted setup only; never send utterances or evaluator gold."""
        return cls(**case["trusted_state"], **case["backend_state"], **case["tool_fixture"])

    def state(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if not key.startswith("error_")}


DEFAULT_FIXTURE = MCPFixtureConfig()


def order_status(order_id: str, config: MCPFixtureConfig = DEFAULT_FIXTURE) -> str:
    """Pure fixture used by both the direct example and MCP server."""
    if order_id != config.authorized_order_id:
        raise ValueError("Unknown synthetic order")
    status = "has shipped" if config.order_status == "shipped" else f"is {config.order_status}"
    return f"Order {order_id} {status}. Its estimated delivery is {config.estimated_delivery}."


def return_policy(config: MCPFixtureConfig = DEFAULT_FIXTURE) -> str:
    return f"Unopened items may be returned within {config.return_window_days} days of delivery."


def create_server(config: MCPFixtureConfig) -> MCPServer:
    server = MCPServer("Synthetic support", version="1.0.0")

    def result(name: str, answer: str) -> CallToolResult:
        failed = config.error_tool == name
        output = {
            "ok": not failed,
            "answer": None if failed else answer,
            "error": {"code": "lookup_unavailable", "expected": True} if failed else None,
            "state": config.state(),
        }
        return CallToolResult(
            is_error=failed,
            content=[TextContent(text="Lookup unavailable." if failed else answer)],
            structured_content=output,
        )

    @server.tool(name="order_status", annotations=ToolAnnotations(read_only_hint=True))
    def lookup_order_status(order_id: str) -> CallToolResult:
        """Read the authorized synthetic order's status."""
        return result("order_status", order_status(order_id, config))

    @server.tool(name="return_policy", annotations=ToolAnnotations(read_only_hint=True))
    def lookup_return_policy() -> CallToolResult:
        """Read the synthetic return policy; never initiate a return."""
        return result("return_policy", return_policy(config))

    return server


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture-json", default="{}")
    args = parser.parse_args()
    create_server(MCPFixtureConfig(**json.loads(args.fixture_json))).run(transport="stdio")
