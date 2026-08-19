from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import beds24_guest_journey_mcp as mcp  # noqa: E402


class Beds24GuestJourneyMcpTests(unittest.TestCase):
    def test_server_lists_only_two_read_only_tools(self) -> None:
        response = mcp.handle_request(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        )
        tools = response["result"]["tools"]
        self.assertEqual(
            [tool["name"] for tool in tools],
            ["get_guest_journey_scope", "get_guest_journey_shadow"],
        )
        for tool in tools:
            self.assertTrue(tool["annotations"]["readOnlyHint"])
            self.assertFalse(tool["annotations"]["destructiveHint"])

    def test_scope_call_returns_structured_pii_free_result(self) -> None:
        scope = {
            "mode": "shadow_read_only",
            "containsGuestPii": False,
            "properties": [{"key": "elcid", "roomIdFilter": None}],
        }
        with mock.patch.object(mcp.shadow, "configured_scope", return_value=scope):
            response = mcp.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "get_guest_journey_scope",
                        "arguments": {},
                    },
                }
            )
        self.assertEqual(response["result"]["structuredContent"], scope)
        self.assertFalse(response["result"]["isError"])

    def test_unexpected_errors_do_not_leak_credentials(self) -> None:
        with mock.patch.object(
            mcp.shadow,
            "build_live_shadow_summary",
            side_effect=RuntimeError("credential super-secret-value"),
        ):
            response = mcp.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "get_guest_journey_shadow",
                        "arguments": {},
                    },
                }
            )
        encoded = json.dumps(response)
        self.assertTrue(response["result"]["isError"])
        self.assertNotIn("super-secret-value", encoded)

    def test_stdio_handshake_and_tool_list(self) -> None:
        payload = "\n".join(
            [
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 10,
                        "method": "initialize",
                        "params": {"protocolVersion": "2025-06-18"},
                    }
                ),
                json.dumps(
                    {"jsonrpc": "2.0", "id": 11, "method": "tools/list"}
                ),
                "",
            ]
        )
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "beds24_guest_journey_mcp.py")],
            input=payload,
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        messages = [json.loads(line) for line in completed.stdout.splitlines()]
        self.assertEqual(messages[0]["result"]["protocolVersion"], "2025-06-18")
        self.assertEqual(len(messages[1]["result"]["tools"]), 2)

    def test_repository_config_uses_agent_secret_and_tool_allowlists(self) -> None:
        config = json.loads(
            (ROOT / "config" / "copilot-mcp.json").read_text(encoding="utf-8")
        )
        servers = config["mcpServers"]
        self.assertTrue(servers)
        self.assertTrue(
            all(server.get("type") == "stdio" for server in servers.values())
        )
        self.assertEqual(
            servers["beds24-shadow"]["env"]["BEDS24_REFRESH_TOKEN"],
            "$COPILOT_MCP_BEDS24_REFRESH_CREDENTIAL",
        )
        self.assertNotIn("${{ secrets.", json.dumps(config))
        self.assertEqual(
            servers["beds24-shadow"]["tools"],
            ["get_guest_journey_scope", "get_guest_journey_shadow"],
        )
        self.assertFalse(
            any(
                tool.startswith(("write", "edit", "move", "create"))
                for tool in servers["policy-tower"]["tools"]
            )
        )


if __name__ == "__main__":
    unittest.main()
