"""Connect workplace MCP tools through vault credentials."""

from __future__ import annotations

import asyncio
import os

from openai import AsyncOpenAI
from openai.types.beta import AgentToolParam
from openai.types.beta.agent_tool_param import AgentToolConfigParamMcp
from openai.types.beta.agents.vaults.credential_auth_create_param import (
    CredentialAuthCreateParam,
)

from .tools import SLACK_TOOLS

NOTION_MCP_URL = "https://mcp.notion.com/mcp"
GOOGLE_DRIVE_MCP_URL = "https://drivemcp.googleapis.com/mcp/v1"
GITHUB_MCP_URL = "https://api.githubcopilot.com/mcp/"


def mcp_server(label: str, url: str) -> AgentToolConfigParamMcp:
    return {
        "type": "mcp",
        "server_label": label,
        "transport": {"type": "http", "server_url": url},
        "connection_origin": "service",
    }


class Connections:
    """Configure workplace tools once per Slack workspace."""

    def __init__(self, client: AsyncOpenAI) -> None:
        self.client = client
        self.vaults: dict[str, str] = {}
        self.lock = asyncio.Lock()

    async def get(self, team_id: str) -> tuple[str | None, list[AgentToolParam]]:
        async with self.lock:
            return await self._configure_tools(team_id)

    async def _configure_tools(
        self, team_id: str
    ) -> tuple[str | None, list[AgentToolParam]]:
        notion_token = os.environ.get("NOTION_TOKEN")
        google_drive_token = os.environ.get("GOOGLE_DRIVE_TOKEN")
        github_token = os.environ.get("GITHUB_TOKEN")
        google_refresh_token = os.environ.get("GOOGLE_DRIVE_REFRESH_TOKEN")
        if google_refresh_token:
            for name in (
                "GOOGLE_DRIVE_TOKEN",
                "GOOGLE_DRIVE_CLIENT_ID",
                "GOOGLE_DRIVE_CLIENT_SECRET",
            ):
                if not os.environ.get(name):
                    raise ValueError(
                        f"Set {name} when enabling Google Drive OAuth refresh."
                    )
        tools: list[AgentToolParam] = [*SLACK_TOOLS, {"type": "web_search"}]
        if notion_token:
            tools.append(mcp_server("notion", NOTION_MCP_URL))
        if google_drive_token:
            tools.append(mcp_server("google_drive", GOOGLE_DRIVE_MCP_URL))
        if github_token:
            tools.append(mcp_server("github", GITHUB_MCP_URL))
        if not (notion_token or google_drive_token or github_token):
            return None, tools

        vault_id = self.vaults.get(team_id)
        if vault_id is not None:
            return vault_id, tools

        existing = [
            candidate
            async for candidate in self.client.beta.agents.vaults.list(limit=100)
        ]
        vault = next(
            (
                candidate
                for candidate in existing
                if candidate.metadata.get("slack_team_id") == team_id
                and candidate.metadata.get("owner") == "slack_bot"
            ),
            None,
        )
        if vault is None:
            vault = await self.client.beta.agents.vaults.create(
                name="Slack teammate integrations",
                metadata={"slack_team_id": team_id, "owner": "slack_bot"},
            )
        credentials = [
            item
            async for item in self.client.beta.agents.vaults.credentials.list(vault.id)
        ]

        async def save_credential(label: str, auth: CredentialAuthCreateParam) -> None:
            credential = next(
                (
                    item
                    for item in credentials
                    if item.auth.mcp_server_url == auth["mcp_server_url"]
                ),
                None,
            )
            if credential is not None and credential.auth.type != auth["type"]:
                raise ValueError(
                    f"Archive the existing {label} vault credential before changing auth type."
                )
            if credential is None:
                await self.client.beta.agents.vaults.credentials.create(
                    vault.id,
                    name=label.replace("_", " ").title(),
                    auth=auth,
                )
            elif auth["type"] == "static_bearer":
                await self.client.beta.agents.vaults.credentials.update(
                    credential.id,
                    vault_id=vault.id,
                    auth={"type": "static_bearer", "token": auth["token"]},
                )
            # Keep refreshed OAuth grants in the vault; .env only seeds a new credential.

        if notion_token:
            await save_credential(
                "notion",
                {
                    "type": "static_bearer",
                    "mcp_server_url": NOTION_MCP_URL,
                    "token": notion_token,
                },
            )

        if google_drive_token:
            google_auth: CredentialAuthCreateParam = {
                "type": "static_bearer",
                "mcp_server_url": GOOGLE_DRIVE_MCP_URL,
                "token": google_drive_token,
            }
            if google_refresh_token:
                google_auth = {
                    "type": "mcp_oauth",
                    "mcp_server_url": GOOGLE_DRIVE_MCP_URL,
                    "access_token": google_drive_token,
                    "expires_at": os.environ.get("GOOGLE_DRIVE_TOKEN_EXPIRES_AT")
                    or None,
                    "refresh": {
                        "token_endpoint": "https://oauth2.googleapis.com/token",
                        "client_id": os.environ["GOOGLE_DRIVE_CLIENT_ID"],
                        "refresh_token": google_refresh_token,
                        "token_endpoint_auth": {
                            "type": "client_secret_post",
                            "client_secret": os.environ["GOOGLE_DRIVE_CLIENT_SECRET"],
                        },
                    },
                }
            await save_credential("google_drive", google_auth)

        if github_token:
            await save_credential(
                "github",
                {
                    "type": "static_bearer",
                    "mcp_server_url": GITHUB_MCP_URL,
                    "token": github_token,
                },
            )

        self.vaults[team_id] = vault.id
        return vault.id, tools
