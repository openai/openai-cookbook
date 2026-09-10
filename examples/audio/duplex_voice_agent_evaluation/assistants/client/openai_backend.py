"""Optional OpenAI Responses adapter for an application-owned backend."""

from __future__ import annotations

import asyncio
import copy
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from openai import AsyncOpenAI

from assistants.client.backend import DelegationHandoff, EventCallback, ToolCallback

ResponseItem = dict[str, Any]
MAX_TOOL_ROUNDS = 8


@dataclass(slots=True)
class ResponsesConversation:
    """Maintain and replay application-owned Responses conversation history."""

    items: list[ResponseItem] = field(default_factory=list)

    def begin(self, handoff: DelegationHandoff) -> list[ResponseItem]:
        self.items.append(
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": handoff.as_prompt()}],
            }
        )
        return copy.deepcopy(self.items)

    def request_payload(
        self,
        *,
        model: str,
        instructions: str,
        tools: list[ResponseItem],
        inputs: Sequence[ResponseItem],
        reasoning_effort: str,
        max_output_tokens: int,
    ) -> dict[str, Any]:
        return {
            "model": model,
            "instructions": instructions,
            "input": list(inputs),
            "tools": tools,
            "parallel_tool_calls": False,
            "reasoning": {"effort": reasoning_effort},
            "max_output_tokens": max_output_tokens,
            "stream": True,
            "store": False,
            "include": ["reasoning.encrypted_content"],
        }

    def record_response(self, response: ResponseItem) -> list[ResponseItem]:
        output = response.get("output", [])
        if not isinstance(output, list) or not all(isinstance(item, dict) for item in output):
            raise RuntimeError("Responses backend returned invalid output items")
        for item in output:
            if item.get("type") == "reasoning" and not item.get("encrypted_content"):
                raise RuntimeError("OpenAI Responses replay requires encrypted reasoning")
            self.items.append(copy.deepcopy(item))
        return [item for item in output if item.get("type") == "function_call"]

    def continue_tools(self, outputs: Sequence[ResponseItem]) -> list[ResponseItem]:
        self.items.extend(copy.deepcopy(list(outputs)))
        return copy.deepcopy(self.items)


class ResponsesBackend:
    """Run one isolated delegated assistant, without access to evaluator-only data."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        instructions: str,
        tools: list[ResponseItem],
        reasoning_effort: str,
        max_output_tokens: int,
        execute_tool: ToolCallback,
        client: AsyncOpenAI | None = None,
    ) -> None:
        self.model = model
        self.instructions = instructions
        self.tools = copy.deepcopy(tools)
        self.reasoning_effort = reasoning_effort
        self.max_output_tokens = max_output_tokens
        self.execute_tool = execute_tool
        self.conversation = ResponsesConversation()
        self.client = client or AsyncOpenAI(api_key=api_key, timeout=60, max_retries=2)
        self._owns_client = client is None
        self._lock = asyncio.Lock()
        self._completed_call_ids: set[str] = set()

    async def run(self, handoff: DelegationHandoff, emit: EventCallback) -> str:
        async with self._lock:
            inputs = self.conversation.begin(handoff)
            for round_number in range(1, MAX_TOOL_ROUNDS + 1):
                request = self.conversation.request_payload(
                    model=self.model,
                    instructions=self.instructions,
                    tools=self.tools,
                    inputs=inputs,
                    reasoning_effort=self.reasoning_effort,
                    max_output_tokens=self.max_output_tokens,
                )
                await emit(
                    {
                        "type": "client_delegation.context.assembled",
                        "round": round_number,
                        "input_item_count": len(inputs),
                    }
                )
                response = await self._stream_response(request, emit)
                calls = self.conversation.record_response(response)
                if not calls:
                    answer = _output_text(response)
                    if not answer:
                        raise RuntimeError("Delegated Responses backend completed without spoken text")
                    return answer
                outputs: list[ResponseItem] = []
                for call in calls:
                    output = await self._execute_call(call, str(response.get("id", "")), emit)
                    outputs.append(output)
                inputs = self.conversation.continue_tools(outputs)
        raise RuntimeError(f"Delegated Responses backend exceeded {MAX_TOOL_ROUNDS} tool rounds")

    async def _stream_response(self, request: dict[str, Any], emit: EventCallback) -> ResponseItem:
        stream = await self.client.responses.create(**request)
        completed: ResponseItem | None = None
        async for item in stream:
            raw_event = item.model_dump(mode="json", exclude_none=True)
            event = _safe_stream_event(raw_event)
            event["_client_managed"] = True
            await emit(event)
            if raw_event.get("type") == "response.completed":
                candidate = raw_event.get("response")
                if isinstance(candidate, dict):
                    completed = candidate
            elif raw_event.get("type") in {"response.failed", "response.incomplete", "error"}:
                error = raw_event.get("error") or raw_event.get("response", {}).get("error") or {}
                message = error.get("message") if isinstance(error, dict) else str(error)
                raise RuntimeError(message or "Delegated Responses request failed")
        if completed is None:
            raise RuntimeError("Delegated Responses stream ended without a completed response")
        return completed

    async def _execute_call(self, call: ResponseItem, response_id: str, emit: EventCallback) -> ResponseItem:
        call_id = call.get("call_id")
        name = call.get("name")
        if not isinstance(call_id, str) or not call_id or not isinstance(name, str) or not name:
            raise RuntimeError("Delegated Responses function call is missing its name or call_id")
        if call_id in self._completed_call_ids:
            raise RuntimeError(f"Delegated Responses repeated completed tool call {call_id}")
        raw_arguments = call.get("arguments", "{}")
        try:
            arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
        except json.JSONDecodeError as error:
            raise RuntimeError(f"Invalid arguments for tool {name}") from error
        if not isinstance(arguments, dict):
            raise RuntimeError(f"Arguments for tool {name} must be an object")
        schema = next((tool for tool in self.tools if tool.get("name") == name), {})
        parameters = schema.get("parameters", {}) if isinstance(schema, dict) else {}
        required = set(parameters.get("required", [])) if isinstance(parameters, dict) else set()
        arguments = {
            key: value
            for key, value in arguments.items()
            if value is not None and not (isinstance(value, str) and not value.strip() and key not in required)
        }
        correlation = {
            "name": name,
            "arguments": arguments,
            "call_id": call_id,
            "response_id": response_id,
            "_client_managed": True,
        }
        await emit({"type": "tool.called", **correlation})
        try:
            result = await self.execute_tool(name, arguments, call_id)
            self._completed_call_ids.add(call_id)
            await emit({"type": "tool.completed", **correlation, "result": result})
        except asyncio.CancelledError:
            raise
        except Exception as error:
            result = {"ok": False, "error": str(error)}
            await emit({"type": "tool.failed", **correlation, "error": str(error)})
        return {
            "type": "function_call_output",
            "call_id": call_id,
            "output": json.dumps(result, ensure_ascii=False, separators=(",", ":")),
        }

    async def close(self) -> None:
        if self._owns_client:
            await self.client.close()


def _output_text(response: ResponseItem) -> str:
    messages = response.get("output", [])
    if not isinstance(messages, list):
        return ""
    return " ".join(
        str(part.get("text", "")).strip()
        for item in messages
        if isinstance(item, dict) and item.get("type") == "message"
        for part in item.get("content", [])
        if isinstance(part, dict) and part.get("type") == "output_text" and part.get("text")
    ).strip()


def _safe_stream_event(event: ResponseItem) -> ResponseItem:
    """Expose useful response evidence without leaking encrypted reasoning or prompts."""
    visible = dict(event)
    response = visible.get("response")
    if isinstance(response, dict):
        visible["response"] = {
            key: value for key, value in response.items() if key in {"id", "status", "model", "usage", "error"}
        }
    item = visible.get("item")
    if isinstance(item, dict):
        visible["item"] = {key: value for key, value in item.items() if key != "encrypted_content"}
    return visible
