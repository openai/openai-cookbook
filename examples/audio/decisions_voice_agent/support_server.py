"""Local, read-only synthetic data. No outbound services or customer records."""

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

server = MCPServer("Synthetic support")


@server.tool(annotations=ToolAnnotations(read_only_hint=True))
def order_status(order_id: str) -> str:
    """Read the one synthetic order available in this example."""
    if order_id != "DEMO-1001":
        raise ValueError("Unknown synthetic order")
    return "Order DEMO-1001 has shipped. Its estimated delivery is Friday."


@server.tool(annotations=ToolAnnotations(read_only_hint=True))
def return_policy() -> str:
    """Read the synthetic store's return policy; do not initiate a return."""
    return "Unopened items may be returned within 30 days of delivery."


if __name__ == "__main__":
    server.run(transport="stdio")
