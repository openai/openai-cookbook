"""Shared tool contracts, observation, and nonblocking protocol execution."""

from __future__ import annotations

import asyncio
import copy
import inspect
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from assistants.lifecycle import PendingWork


class ToolExecutor(Protocol):
    """Application-owned tool and state contract for one GPT Live session."""

    executions: list[dict[str, Any]]

    def execute(self, name: str, arguments: dict[str, Any], *, call_id: str) -> dict[str, Any]:
        """Validate and perform an authorized application operation."""
        ...

    def snapshot(self) -> dict[str, Any]:
        """Return observable application state after completed operations."""
        ...


@dataclass(slots=True)
class RemoteToolObserver:
    """Read-only projection of tools and state owned by a remote assistant."""

    initial_state: dict[str, Any]
    facts: dict[str, Any]
    executions: list[dict[str, Any]] = field(init=False, default_factory=list)
    _state: dict[str, Any] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.initial_state = copy.deepcopy(self.initial_state)
        self.facts = copy.deepcopy(self.facts)
        self._state = copy.deepcopy(self.initial_state)

    def execute(self, name: str, arguments: dict[str, Any], *, call_id: str) -> dict[str, Any]:
        raise RuntimeError("Application tools must execute inside the remote assistant")

    def observe(self, event: dict[str, Any]) -> None:
        """Mirror assistant-emitted evidence without running application code."""
        state = event.get("application_state")
        if isinstance(state, dict):
            self._state = copy.deepcopy(state)
        execution = event.get("tool_execution")
        if isinstance(execution, dict):
            call_id = str(execution.get("call_id", ""))
            if call_id and any(item.get("call_id") == call_id for item in self.executions):
                return
            self.executions.append(copy.deepcopy(execution))

    def snapshot(self) -> dict[str, Any]:
        return copy.deepcopy(self._state)


@dataclass(frozen=True, slots=True)
class ToolExecutionResult:
    """One completed application-owned tool invocation."""

    name: str
    arguments: dict[str, Any]
    call_id: str
    output: dict[str, Any]
    error: str | None = None


def build_tool_output_event(call_id: str, output: dict[str, Any]) -> dict[str, Any]:
    """Return the same GPT Live function-output event for every harness."""
    return {
        "type": "response.item.create",
        "event_id": f"event_tool_output_{call_id}",
        "item": {
            "type": "function_call_output",
            "call_id": call_id,
            "output": json.dumps(output, ensure_ascii=False, separators=(",", ":")),
        },
    }


class AsyncToolRuntime:
    """Execute application tools without blocking a live audio receive loop."""

    def __init__(self, executor: ToolExecutor) -> None:
        self.executor = executor
        self.error: Exception | None = None
        self._lock = asyncio.Lock()
        self._tasks: set[asyncio.Task[None]] = set()
        self._work = PendingWork(failure_stage="tool_execution")
        self._close_lock = asyncio.Lock()
        self._closed = False

    @property
    def pending(self) -> bool:
        return self._work.pending

    def ensure_open(self) -> None:
        self._work.ensure_open()

    def submit(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        call_id: str,
        on_result: Callable[[ToolExecutionResult], Awaitable[None]],
        on_error: Callable[[Exception], Awaitable[None]] | None = None,
        on_start: Callable[[], Awaitable[None]] | None = None,
    ) -> asyncio.Task[None]:
        self._work.begin(call_id)
        task = asyncio.create_task(
            self._execute(name, arguments, call_id=call_id, on_result=on_result, on_error=on_error, on_start=on_start),
            name=f"application-tool-{call_id}",
        )
        self._tasks.add(task)
        task.add_done_callback(lambda completed: self._finished(call_id, completed))
        return task

    def _finished(self, call_id: str, task: asyncio.Task[None]) -> None:
        self._tasks.discard(task)
        if task.cancelled():
            self._work.fail("Application tool work was cancelled")
        elif error := task.exception():
            self.error = error
            self._work.fail(f"Application tool publication failed ({type(error).__name__})")
        self._work.finish(call_id)

    async def _execute(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        call_id: str,
        on_result: Callable[[ToolExecutionResult], Awaitable[None]],
        on_error: Callable[[Exception], Awaitable[None]] | None,
        on_start: Callable[[], Awaitable[None]] | None,
    ) -> None:
        try:
            if on_start is not None:
                await on_start()
            async with self._lock:
                try:
                    execute = self.executor.execute
                    if inspect.iscoroutinefunction(execute):
                        output = await execute(name, arguments, call_id=call_id)
                    else:
                        output = await asyncio.to_thread(execute, name, arguments, call_id=call_id)
                    result = ToolExecutionResult(name, arguments, call_id, output)
                except ValueError as exc:
                    output = {"ok": False, "error": str(exc)}
                    self.executor.executions.append(
                        {
                            "call_id": call_id,
                            "name": name,
                            "arguments": arguments,
                            "status": "failed",
                            "output": output,
                        }
                    )
                    result = ToolExecutionResult(name, arguments, call_id, output, str(exc))
            await on_result(result)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.error = exc
            self._work.fail(f"Application tool execution failed ({type(exc).__name__})")
            if on_error is not None:
                await on_error(exc)

    def raise_if_failed(self) -> None:
        self._work.raise_if_failed()

    async def wait(self) -> None:
        await self._work.wait()

    async def close(self) -> None:
        async with self._close_lock:
            if self._closed:
                return
            self._work.seal()
            try:
                tasks = tuple(self._tasks)
                for task in tasks:
                    task.cancel()
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
            finally:
                self._work.abort("Application tool work was cancelled during close")
                self._closed = True


class OfflineApplicationBehavior(Protocol):
    """Visible-input behavior for a domain-owned offline protocol fixture."""

    def infer_tool_call(self, user_text: str) -> tuple[str, dict[str, Any]] | None:
        """Select an operation from user-visible, authorized context."""
        ...

    def direct_answer(self, user_text: str) -> str:
        """Produce a tool-free answer using only configured public facts."""
        ...

    def final_answer(self, output: dict[str, Any]) -> str:
        """Relay the completed, actual application-owned tool result."""
        ...
