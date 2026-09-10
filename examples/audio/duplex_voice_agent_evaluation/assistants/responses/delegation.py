"""Assistant-owned function execution for OpenAI-managed Responses delegation."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

from assistants.errors import LiveResponseError
from assistants.frontend.connection import AssistantConnection
from assistants.frontend.events import EventQueue
from assistants.lifecycle import PendingWork
from assistants.runtime import AsyncToolRuntime, ToolExecutionResult, ToolExecutor, build_tool_output_event

EventCallback = Callable[[dict[str, Any]], Awaitable[None]]


class ResponsesDelegationController:
    """Execute completed application tools within the evaluated assistant."""

    def __init__(self, *, executor: ToolExecutor, send_live: EventCallback, emit: EventCallback) -> None:
        self.executor = executor
        self.send_live = send_live
        self.emit = emit
        self.runtime = AsyncToolRuntime(executor)
        self.function_items: dict[str, dict[str, Any]] = {}
        self.handled_call_ids: set[str] = set()
        self.current_response_id = ""
        self.responses: dict[str, dict[str, Any]] = {}
        self._publication_lock = asyncio.Lock()
        self._work = PendingWork(failure_stage="delegated_response")

    @property
    def pending(self) -> bool:
        try:
            self.runtime.ensure_open()
            self._work.raise_if_failed()
        except (RuntimeError, LiveResponseError):
            return False
        return self.runtime.pending or self._work.pending

    async def observe(self, event: dict[str, Any]) -> None:
        self.runtime.ensure_open()
        kind = str(event.get("type", ""))
        if kind == "response.created":
            response = event.get("response", {})
            identifier = str(response.get("id") or "")
            if not identifier:
                raise ValueError("Responses lifecycle is missing response_id")
            if identifier in self.responses:
                return
            owner = event.get("delegation_id") or ""
            previous = response.get("previous_response_id") or event.get("previous_response_id")
            waiting = [
                key
                for key, batch in self.responses.items()
                if batch["continued"]
                and self._work.contains(key)
                and (key == previous or (owner and batch["delegation_id"] == owner))
            ]
            if not owner and not previous:
                candidates = [
                    key for key, batch in self.responses.items() if batch["continued"] and self._work.contains(key)
                ]
                active = [key for key in self.responses if self._work.contains(key) and key not in candidates]
                waiting = candidates if len(candidates) == 1 and not active else []
            if len(waiting) > 1:
                waiting = []
            for key in waiting:
                self._work.finish(key)
            if identifier not in self.responses:
                self.responses[identifier] = {
                    "delegation_id": owner,
                    "calls": {},
                    "complete": False,
                    "continued": False,
                }
                self._work.begin(identifier)
            self.current_response_id = identifier
            return
        if kind in {"response.failed", "response.incomplete", "error"}:
            self._work.fail("GPT Live rejected or failed delegated Responses work")
            self._work.abort("GPT Live rejected or failed delegated Responses work")
            if kind == "response.incomplete":
                await self.emit(
                    {
                        "type": "error",
                        "error": {"code": "response_incomplete", "message": "Delegated response was incomplete"},
                    }
                )
            return
        if kind == "response.completed":
            response_id = str(event.get("response", {}).get("id") or "")
            batch = self.responses.get(response_id)
            if batch is None:
                raise ValueError("Completed an unknown Responses invocation")
            batch["complete"] = True
            if batch["calls"]:
                await self._continue(response_id)
            else:
                self._work.finish(response_id)
            return
        if kind == "response.output_item.added":
            item = event.get("item", {})
            if isinstance(item, dict) and item.get("type") == "function_call" and item.get("id"):
                self.function_items[str(item["id"])] = {
                    "response_id": self._response_id(event),
                }
            return
        if kind != "response.output_item.done":
            return
        item = event.get("item", {})
        if not isinstance(item, dict) or item.get("type") != "function_call" or item.get("status") != "completed":
            return
        if event.get("_client_managed"):
            return
        await self._submit_call(event, item)

    def _response_id(self, event: dict[str, Any]) -> str:
        item = event.get("item", {})
        metadata = self.function_items.get(str(item.get("id", "")), {})
        identifier = event.get("response_id") or metadata.get("response_id")
        if identifier in self.responses:
            return str(identifier)
        if identifier:
            raise ValueError("Function item names an unknown Responses invocation")
        owner = event.get("delegation_id")
        candidates = [
            key
            for key, batch in self.responses.items()
            if not batch["complete"] and (not owner or batch["delegation_id"] == owner)
        ]
        if len(candidates) != 1:
            raise ValueError("Cannot correlate function item to one Responses invocation")
        return candidates[0]

    async def _continue(self, response_id: str) -> None:
        async with self._publication_lock:
            self._work.ensure_open()
            batch = self.responses[response_id]
            if not batch["complete"] or batch["continued"] or any(result is None for result in batch["calls"].values()):
                return
            try:
                for call_id, output in batch["calls"].items():
                    await self.send_live(build_tool_output_event(call_id, output))
                batch["continued"] = True
                await self.send_live({"type": "response.create", "event_id": f"continue_{response_id}"})
            except Exception as error:
                self._work.abort(f"Responses continuation failed ({type(error).__name__})")
                await self.emit(
                    {"type": "error", "error": {"code": "response_continuation_failed", "message": str(error)}}
                )
                raise

    async def _submit_call(self, event: dict[str, Any], item: dict[str, Any]) -> None:
        call_id = str(item.get("call_id", ""))
        if not call_id:
            await self.emit({"type": "error", "error": {"message": "Delegated function is missing call_id"}})
            return
        if call_id in self.handled_call_ids:
            return
        self.handled_call_ids.add(call_id)
        raw_arguments = item.get("arguments")
        try:
            arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
        except json.JSONDecodeError:
            arguments = None
        arguments = arguments if isinstance(arguments, dict) else {}
        arguments = {key: value for key, value in arguments.items() if value is not None}
        response_id = self._response_id(event)
        self.responses[response_id]["calls"][call_id] = None
        correlation = {
            "name": str(item.get("name", "")),
            "call_id": call_id,
            "response_id": response_id,
            "delegation_id": self.responses[response_id]["delegation_id"],
            "arguments": arguments,
            "_assistant_managed": True,
        }

        async def publish_start() -> None:
            await self.emit({"type": "tool.called", **correlation})

        async def publish_result(result: ToolExecutionResult) -> None:
            observed = {"type": "tool.failed" if result.error is not None else "tool.completed", **correlation}
            if result.error is not None:
                observed["error"] = result.error
            else:
                observed["result"] = result.output
            observed["application_state"] = self.executor.snapshot()
            await self.emit(observed)
            self.responses[response_id]["calls"][result.call_id] = result.output
            await self._continue(response_id)

        async def publish_error(error: Exception) -> None:
            self._work.fail(f"Tool result publication failed ({type(error).__name__})")
            await self.emit({"type": "error", "error": {"code": "tool_execution_error", "message": str(error)}})

        self.runtime.submit(
            correlation["name"],
            arguments,
            call_id=call_id,
            on_result=publish_result,
            on_error=publish_error,
            on_start=publish_start,
        )

    async def wait(self) -> None:
        await self.runtime.wait()
        self._work.raise_if_failed()
        await self._work.wait()

    async def close(self) -> None:
        self._work.seal()
        try:
            await self.runtime.close()
        finally:
            self._work.abort("Responses work abandoned during close")


async def bind_responses_delegation(connection: Any, *, executor: ToolExecutor) -> AssistantConnection:
    """Attach assistant-owned Responses tools to an existing voice connection."""
    events = EventQueue()
    controller = ResponsesDelegationController(executor=executor, send_live=connection.send_json, emit=events.put)
    wrapped = AssistantConnection(connection, controller, events=events)
    controller.send_live = wrapped.send_json
    await wrapped.start()
    return wrapped
