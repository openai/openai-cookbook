"""Investigate warehouse questions with persistent Agents API sessions."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping
from typing import Any
from uuid import uuid4

from openai import AsyncOpenAI
from openai.lib.streaming.agents import AsyncToolHandler
from openai.types.beta import AgentToolParam
from openai.types.beta.agent_tool_param import AgentToolConfigParamFunction
from openai.types.beta.agents.session_create_params import Agent

from .warehouse import Warehouse

INSTRUCTIONS = """\
You are a careful business data analyst.
Find relevant warehouse tables and inspect their schemas.
Check business definitions, trusted prior queries, and saved analyst corrections.
Execute only read-only queries.
Explain your verified findings, sources, assumptions, and SQL.
Save a memory only when the user explicitly asks you to remember a correction.
"""


def define_tool(
    name: str,
    description: str,
    properties: Mapping[str, dict[str, Any]],
    *,
    defer_loading: bool = False,
) -> AgentToolConfigParamFunction:
    tool: AgentToolConfigParamFunction = {
        "type": "function",
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": dict(properties),
            "required": list(properties),
            "additionalProperties": False,
        },
    }
    if defer_loading:
        tool["defer_loading"] = True
    return tool


TOOLS: list[AgentToolParam] = [
    define_tool(
        "search_tables",
        "Find relevant warehouse tables and inspect their actual columns and business context.",
        {"query": {"type": "string"}},
    ),
    define_tool(
        "search_context",
        "Find business definitions, reviewed queries, company documents, and analyst memories.",
        {"query": {"type": "string"}},
    ),
    define_tool(
        "query_warehouse",
        "Execute one read-only SQL query and return at most 100 rows.",
        {"sql": {"type": "string"}},
    ),
    define_tool(
        "save_memory",
        "Save a useful correction only when the user explicitly asks you to remember it.",
        {
            "note": {"type": "string"},
            "scope": {"type": "string", "enum": ["personal", "team"]},
        },
        defer_loading=True,
    ),
    {"type": "tool_search"},
    {"type": "programmatic_tool_calling", "enabled": True},
]


class DataAnalyst:
    """Keep one Agents API session for each warehouse investigation."""

    def __init__(self, client: AsyncOpenAI, warehouse: Warehouse) -> None:
        self.client = client
        self.warehouse = warehouse
        self.model = os.environ.get("OPENAI_MODEL", "gpt-5.6-luna")
        self.sessions: dict[str, str] = {}
        self.owners: dict[str, str] = {}

    async def answer(
        self,
        question: str,
        conversation_id: str | None = None,
        *,
        user_id: str = "analyst",
    ) -> dict[str, Any]:
        conversation_id = conversation_id or uuid4().hex
        owner = self.owners.get(conversation_id)
        if owner is not None and owner != user_id:
            raise PermissionError(
                "Start a new conversation to use your own analyst context."
            )

        queries: list[str] = []

        def execute(arguments: dict[str, Any]) -> dict[str, Any]:
            result = self.warehouse.query(arguments)
            queries.append(str(result["sql"]))
            return result

        handlers: dict[str, AsyncToolHandler] = {
            "search_tables": self.warehouse.search_tables,
            "search_context": lambda arguments: self.warehouse.search_context(
                arguments, user_id=user_id
            ),
            "query_warehouse": execute,
            "save_memory": lambda arguments: self.warehouse.memory.save(
                arguments, user_id=user_id
            ),
        }

        if conversation_id in self.sessions:
            session = await self.client.beta.agents.sessions.retrieve(
                self.sessions[conversation_id]
            )
        else:
            agent: Agent = {
                "model": self.model,
                "instructions": INSTRUCTIONS,
                "reasoning": {"effort": "high"},
                "tools": TOOLS,
            }
            session = await self.client.beta.agents.sessions.create(
                agent=agent,
                environment={"type": "none"},
            )
            self.sessions[conversation_id] = session.id
            self.owners[conversation_id] = user_id

        session_id = session.id
        parts: list[str] = []
        async with self.client.beta.agents.sessions.stream(
            session_id, input=question, tool_handlers=handlers
        ) as events:
            async for event in events:
                if event.type == "agent.session.turn.output_text.delta":
                    parts.append(event.delta)
                elif event.type == "agent.session.turn.output_text.done" and not parts:
                    parts.append(event.text)
                elif event.type in {
                    "agent.session.failed",
                    "agent.session.turn.failed",
                    "error",
                }:
                    raise RuntimeError(f"Data investigation failed: {event.to_dict()}")
                elif event.type == "agent.session.turn.cancelled":
                    raise RuntimeError("Data investigation was cancelled.")
        answer = "".join(parts)

        return {
            "answer": answer,
            "conversation_id": conversation_id,
            "session_id": session_id,
            "sql": queries[-1] if queries else None,
            "queries": queries,
            "memories": self.warehouse.memory.list(user_id=user_id),
        }

    async def close(self) -> None:
        try:
            results = await asyncio.gather(
                *(
                    self.client.beta.agents.sessions.delete(sid)
                    for sid in set(self.sessions.values())
                ),
                return_exceptions=True,
            )
            for result in results:
                if isinstance(result, BaseException):
                    raise result
        finally:
            self.sessions.clear()
            self.owners.clear()
            self.warehouse.close()
