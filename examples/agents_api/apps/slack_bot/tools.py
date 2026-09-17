"""Read Slack messages, teammates, and shared files."""

from __future__ import annotations

from typing import Any

from openai.lib.streaming.agents import AsyncToolHandler
from openai.types.beta.agent_tool_param import AgentToolConfigParamFunction
from slack_sdk.web.async_client import AsyncWebClient


def define_tool(
    name: str, description: str, *fields: str
) -> AgentToolConfigParamFunction:
    return {
        "type": "function",
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": {field: {"type": "string"} for field in fields},
            "required": list(fields),
            "additionalProperties": False,
        },
    }


SLACK_TOOLS: list[AgentToolConfigParamFunction] = [
    define_tool(
        "search_slack_messages",
        "Search recent messages in this Slack channel.",
        "query",
    ),
    define_tool("read_slack_channel", "Read recent messages in this Slack channel."),
    define_tool("find_teammate", "Find a Slack teammate by name.", "query"),
    define_tool("list_slack_files", "List files shared in this Slack channel."),
]


def slack_handlers(
    slack: AsyncWebClient, channel_id: str
) -> dict[str, AsyncToolHandler]:
    async def search_slack_messages(arguments: dict[str, Any]) -> dict[str, Any]:
        query = str(arguments["query"]).casefold()
        response = await slack.conversations_history(channel=channel_id, limit=100)
        messages: list[dict[str, Any]] = response.get("messages", [])
        return {
            "messages": [
                {
                    "user": str(message.get("user", "")),
                    "text": str(message.get("text", "")),
                }
                for message in messages
                if query in str(message.get("text", "")).casefold()
            ][:20]
        }

    async def read_slack_channel(_arguments: dict[str, Any]) -> dict[str, Any]:
        response = await slack.conversations_history(channel=channel_id, limit=20)
        messages: list[dict[str, Any]] = response.get("messages", [])
        return {
            "messages": [
                {
                    "user": str(message.get("user", "")),
                    "text": str(message.get("text", "")),
                }
                for message in messages
            ]
        }

    async def find_teammate(arguments: dict[str, Any]) -> dict[str, Any]:
        query = str(arguments["query"]).casefold()
        response = await slack.users_list(limit=200)
        members: list[dict[str, Any]] = response.get("members", [])
        matches: list[dict[str, Any]] = []
        for member in members:
            if member.get("deleted") or member.get("is_bot"):
                continue
            profile = member.get("profile", {})
            name = str(profile.get("display_name") or member.get("real_name") or "")
            if (
                query in name.casefold()
                or query in str(member.get("name", "")).casefold()
            ):
                matches.append({"id": str(member.get("id", "")), "name": name})
        return {"users": matches[:20]}

    async def list_slack_files(_arguments: dict[str, Any]) -> dict[str, Any]:
        response = await slack.files_list(channel=channel_id, count=20)
        files: list[dict[str, Any]] = response.get("files", [])
        return {
            "files": [
                {
                    "name": str(file.get("name", "")),
                    "title": str(file.get("title", "")),
                    "url": str(file.get("permalink", "")),
                }
                for file in files
            ]
        }

    return {
        "search_slack_messages": search_slack_messages,
        "read_slack_channel": read_slack_channel,
        "find_teammate": find_teammate,
        "list_slack_files": list_slack_files,
    }
