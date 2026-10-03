"""Finite routing, trusted execution and a duck-typed ApplicationBackend adapter.

This module makes no provider calls. ScriptedRouter is an exact-match test fixture,
not a language model, Decisions implementation, or general intent classifier.
"""

import asyncio
import math
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

EventCallback = Callable[[dict[str, Any]], Awaitable[None]]
AUTHORIZED_ORDER_ID = "DEMO-1001"


class Choice(StrEnum):
    ORDER_STATUS = "order_status"
    RETURN_POLICY = "return_policy"
    CLARIFY = "clarify"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class RoutingRequest:
    instructions: str
    transcript_srt: str
    follow_up: bool = False


class RoutingBackend(Protocol):
    """A future provider adapter returns one choice, never executable arguments."""

    async def choose(self, request: RoutingRequest) -> Choice: ...


class Tools(Protocol):
    async def call(self, name: str, arguments: dict[str, str]) -> str: ...


class Handoff(Protocol):
    """Structural view of the existing evaluator's DelegationHandoff."""

    task: str
    transcript_srt: str
    follow_up: bool


class ScriptedRouter:
    """Known offline inputs only; all unknown or incremental inputs abstain."""

    async def choose(self, request: RoutingRequest) -> Choice:
        if request.follow_up:
            return Choice.CLARIFY
        # The public ledger emits ROLE-prefixed SRT blocks. Restrict this fixture
        # to one user segment; multiple turns require conversation state.
        users = []
        for block in re.split(r"\n\s*\n", request.transcript_srt.strip()):
            lines = block.splitlines()
            if len(lines) >= 3 and " --> " in lines[1] and lines[2].startswith("USER: "):
                users.append(" ".join([lines[2][6:], *lines[3:]]).strip())
        if len(users) != 1:
            return Choice.CLARIFY
        return {
            "Where is my order?": Choice.ORDER_STATUS,
            "What is the return policy?": Choice.RETURN_POLICY,
            "Cancel my order.": Choice.UNSUPPORTED,
        }.get(users[0], Choice.CLARIFY)


class SupportAgent:
    """The router selects; application code owns authorization and arguments."""

    def __init__(self, router: RoutingBackend, tools: Tools):
        self.router = router
        self.tools = tools

    async def answer(self, request: RoutingRequest, emit: EventCallback) -> str:
        # Runtime validation still matters when a remote implementation replaces
        # the typed fixture. An arbitrary tool name or argument object is invalid.
        choice = Choice(await self.router.choose(request))
        await emit({"type": "routing.completed", "choice": choice.value})
        if choice == Choice.CLARIFY:
            return "Please restate one request: order status or the return policy."
        if choice == Choice.UNSUPPORTED:
            return "I can look up order status or the return policy. I cannot change orders."

        # This demo is pre-authorized for one fictional order. A real application
        # must bind verified identity and resource permissions before this point.
        if choice == Choice.ORDER_STATUS:
            name, arguments = "order_status", {"order_id": AUTHORIZED_ORDER_ID}
        else:
            name, arguments = "return_policy", {}
        await emit({"type": "tool.called", "name": name, "arguments": arguments.copy()})
        try:
            answer = await self.tools.call(name, arguments)
            if not isinstance(answer, str) or not answer.strip():
                raise RuntimeError("Tool returned no answer")
        except Exception as error:
            await emit({"type": "tool.failed", "name": name, "error": type(error).__name__})
            return "The lookup is unavailable. I have no verified answer; please try again later."
        await emit({"type": "tool.completed", "name": name, "result": answer})
        return answer


class ExampleBackend:
    """Single-session adapter for ApplicationBackend.run(handoff, emit) -> str.

    One request is admitted at a time; overlapping calls receive an explicit busy
    answer. interrupt() is an application hook, not automatic voice wiring. This
    example deliberately clarifies follow-ups instead of inventing lost context.
    Routers/tools must cooperate with cancellation; close reports failed cleanup.
    """

    def __init__(self, agent: SupportAgent, timeout: float = 5, shutdown_timeout: float = 5):
        if any(not math.isfinite(value) or value <= 0 for value in (timeout, shutdown_timeout)):
            raise ValueError("Timeouts must be finite and positive")
        self.agent = agent
        self.timeout = timeout
        self.shutdown_timeout = shutdown_timeout
        self._active: asyncio.Task[str] | None = None
        self._generation = 0
        self._closed = False

    async def run(self, handoff: Handoff, emit: EventCallback) -> str:
        if self._closed:
            raise RuntimeError("Backend is closed")
        if self._active is not None and not self._active.done():
            return "A lookup is still running. Please wait or interrupt it before trying again."
        self._generation += 1
        generation = self._generation

        async def current_emit(event: dict[str, Any]) -> None:
            if generation != self._generation or self._closed:
                raise asyncio.CancelledError
            await emit(event)
            if generation != self._generation or self._closed:
                raise asyncio.CancelledError

        request = RoutingRequest(handoff.task, handoff.transcript_srt, handoff.follow_up)
        work = asyncio.create_task(self.agent.answer(request, current_emit))
        self._active = work
        try:
            done, _ = await asyncio.wait({work}, timeout=self.timeout)
            if not done:
                await self.interrupt()
                if generation + 1 != self._generation or self._closed:
                    raise asyncio.CancelledError
                await emit({"type": "routing.failed", "error": "timeout"})
                if generation + 1 != self._generation or self._closed:
                    raise asyncio.CancelledError
                return "The lookup timed out. I have no verified answer."
            if generation != self._generation or self._closed:
                raise asyncio.CancelledError
            return work.result()
        except asyncio.CancelledError:
            # Also catches caller cancellation; stale results cannot escape even
            # if a poorly behaved dependency swallows its own cancellation.
            if generation == self._generation:
                await self.interrupt()
            raise
        except Exception as error:
            if generation != self._generation:
                raise  # Preserve a cancellation-cleanup failure, rather than hide it.
            await current_emit({"type": "routing.failed", "error": type(error).__name__})
            return "Routing failed. No verified answer is available."

    async def interrupt(self) -> None:
        self._generation += 1
        work = self._active
        if work is not None and not work.done():
            work.cancel()
            done, _ = await asyncio.wait({work}, timeout=self.shutdown_timeout)
            if not done:
                raise RuntimeError("Backend cancellation did not finish before shutdown deadline")
        if work is not None and not work.cancelled():
            work.exception()  # Retrieve exceptions from the specific interrupted work.

    async def close(self) -> None:
        self._closed = True
        await self.interrupt()
