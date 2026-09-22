"""Investigate warehouse questions with persistent Agents API sessions."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from collections.abc import Callable, Mapping
from typing import Any
from uuid import uuid4

from openai import AsyncOpenAI
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

        handlers: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
            "search_tables": self.warehouse.search_tables,
            "search_context": lambda arguments: self.warehouse.search_context(
                arguments, user_id=user_id
            ),
            "query_warehouse": execute,
            "save_memory": lambda arguments: self.warehouse.memory.save(
                arguments, user_id=user_id
            ),
        }

        first_turn = conversation_id not in self.sessions
        session_id = self.sessions.get(conversation_id)
        if session_id is not None:
            session = await self.client.beta.agents.sessions.retrieve(session_id)
            events = self.client.beta.agents.sessions.stream(
                session.id, input=question, tool_handlers=handlers
            )
        else:
            agent: Agent = {
                "model": self.model,
                "instructions": INSTRUCTIONS,
                "reasoning": {"effort": "high"},
                "tools": TOOLS,
            }
            # Conversation-only sessions need input at creation, not in a later call.
            events = await self.client.beta.agents.sessions.create(
                agent=agent,
                environment={"type": "none"},
                input=question,
                stream=True,
            )

        parts: list[str] = []
        completed = False
        handled_calls: set[tuple[str, str]] = set()
        async with events:
            async for event in events:
                if event.type == "agent.session.created":
                    session_id = event.session.id
                    self.sessions[conversation_id] = session_id
                    self.owners[conversation_id] = user_id
                elif first_turn and event.type == "agent.session.requires_action":
                    # Creation streams expose pending calls; follow-ups use SDK handlers.
                    for action in event.session.required_actions:
                        if action.type != "function_call":
                            continue
                        call = (action.turn_id, action.call_id)
                        if call in handled_calls:
                            continue
                        try:
                            arguments = action.arguments
                            if isinstance(arguments, str):
                                arguments = json.loads(arguments)
                            if not isinstance(arguments, dict):
                                raise ValueError("Function arguments must be an object")
                            output = json.dumps(handlers[action.name](arguments))
                            success, error = True, None
                        except Exception:
                            output, success, error = None, False, "Tool handler failed."
                        await self.client.beta.agents.sessions.events.create(
                            event.session.id,
                            events=[
                                {
                                    "type": "agent.session.input.tool_result",
                                    "turn_id": action.turn_id,
                                    "call_id": action.call_id,
                                    "success": success,
                                    "output": output,
                                    "error": error,
                                }
                            ],
                            idempotency_key=str(uuid4()),
                        )
                        handled_calls.add(call)
                elif event.type == "agent.session.turn.output_text.delta":
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
                elif (
                    event.type == "agent.session.turn.completed"
                    and event.turn.subagent_id is None
                ):
                    completed = True
        if not completed or session_id is None:
            raise RuntimeError("Stream ended without a completed investigation.")
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
        original_error = sys.exception()
        session_ids = list(set(self.sessions.values()))
        try:
            results = await asyncio.gather(
                *(self.client.beta.agents.sessions.delete(sid) for sid in session_ids),
                return_exceptions=True,
            )
            for session_id, result in zip(session_ids, results):
                if isinstance(result, BaseException):
                    if original_error is not None:
                        original_error.add_note(
                            f"Could not delete session {session_id}: {result}"
                        )
                        continue
                    raise result
        finally:
            self.sessions.clear()
            self.owners.clear()
            self.warehouse.close()
