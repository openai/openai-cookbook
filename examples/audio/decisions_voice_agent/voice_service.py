"""Bounded synthetic support service using the existing Live evaluator.

Install the sibling duplex_voice_agent_evaluation package to use this module.
create_support_app accepts a per-connection router factory; constructing it does
not open a provider session. Provider clients and admission belong to the caller.
The default executor calls fixture functions directly. An injected MCPExecutor
uses real stdio transport and contributes protocol evidence to tool events.
This is a single-user example; executor configuration is application-owned.
"""

from __future__ import annotations

import asyncio
import copy
import inspect
import json
from collections.abc import Callable
from contextvars import ContextVar
from typing import Any
from uuid import uuid4

from assistants.client.backend import DelegationHandoff, EventCallback, ToolCallback
from assistants.client.delegation import ClientDelegationController
from assistants.client.memory import TranscriptLedger
from assistants.client.security import ServiceLimits
from assistants.client.service import create_app

from agent import ExampleBackend, RoutingBackend, ScriptedRouter, SupportAgent
from support_server import order_status, return_policy

SUPPORT_LIMITS = ServiceLimits(
    max_connections=1,
    max_pending_delegations=1,
    max_delegations=2,
    max_message_bytes=32 * 1024,
    max_session_bytes=256 * 1024,
    max_events=1000,
    configure_timeout=5,
    session_timeout=35,
    delegation_timeout=15,
    cleanup_timeout=5,
)


class SyntheticSupportExecutor:
    """Fresh authorized fixture per connection; user text cannot select identity."""

    def __init__(self) -> None:
        self.executions: list[dict[str, Any]] = []

    def execute(self, name: str, arguments: dict[str, Any], *, call_id: str) -> dict:
        if name == "order_status" and arguments == {"order_id": "DEMO-1001"}:
            answer = order_status("DEMO-1001")
        elif name == "return_policy" and arguments == {}:
            answer = return_policy()
        else:
            raise ValueError("Unsupported or unauthorized support lookup")
        output = {"ok": True, "answer": answer}
        self.executions.append(
            {
                "call_id": call_id,
                "name": name,
                "arguments": copy.deepcopy(arguments),
                "status": "completed",
                "output": output.copy(),
            }
        )
        return output

    def snapshot(self) -> dict[str, Any]:
        return {"authorized_order_id": "DEMO-1001", "completed_lookups": len(self.executions)}


class CallbackTools:
    """Adapt the sample Tools protocol to the service's observed executor."""

    def __init__(self, execute: ToolCallback) -> None:
        self.execute = execute
        self.call_id = ""
        self.calls = 0
        self.expected_failure: dict | None = None

    async def call(self, name: str, arguments: dict[str, str]) -> str:
        if self.calls >= SUPPORT_LIMITS.max_delegations:
            raise RuntimeError("Support tool allowance exhausted")
        self.calls += 1
        self.expected_failure = None
        async with asyncio.timeout(6):
            output = await self.execute(name, arguments, self.call_id)
        if len(json.dumps(output).encode("utf-8")) > 16 * 1024:
            raise ValueError("Support tool output exceeds the bound")
        answer = output.get("answer")
        if output.get("ok") is False and output.get("error") == {
            "code": "lookup_unavailable",
            "expected": True,
        }:
            self.expected_failure = output["error"]
            raise ExpectedToolError("The configured lookup is unavailable")
        if output.get("ok") is not True or not isinstance(answer, str) or not answer.strip():
            raise ValueError("Support lookup returned no verified answer")
        return answer


class ExpectedToolError(RuntimeError):
    """A trusted, explicitly configured business error, not a transport failure."""


class SupportBackend(ExampleBackend):
    """Use the same SupportAgent while surfacing failed/uncertain work as failure."""

    def __init__(
        self,
        router: RoutingBackend,
        execute_tool: ToolCallback,
        *,
        owned_executor: Any | None = None,
    ) -> None:
        self.tools = CallbackTools(execute_tool)
        self.owned_executor = owned_executor
        self.admission_error: str | None = None
        self._routing_pending = False
        super().__init__(SupportAgent(router, self.tools), timeout=14, shutdown_timeout=4)

    async def run(self, handoff: DelegationHandoff, emit: EventCallback) -> str:
        if self.admission_error:
            raise RuntimeError(self.admission_error)
        if self._active is not None and not self._active.done():
            raise RuntimeError("Support backend already has pending work")
        failed = False
        self.tools.call_id = f"support_{uuid4().hex}"
        self._routing_pending = True

        async def observed(event: dict[str, Any]) -> None:
            nonlocal failed
            expected_failure = (
                event.get("type") == "tool.failed"
                and event.get("error") == "ExpectedToolError"
                and self.tools.expected_failure is not None
            )
            if expected_failure:
                event = {
                    **event,
                    "expected": True,
                    "error_code": self.tools.expected_failure["code"],
                }
            if event.get("type") in {"routing.failed", "tool.failed"} and not expected_failure:
                failed = True
                # Latch before any await: interruption during failure publication
                # must not turn unknown/failed work into settled supersession.
                self.admission_error = "Support backend work failed; do not retry automatically"
            if str(event.get("type", "")).startswith("routing."):
                self._routing_pending = False
            if str(event.get("type", "")).startswith("tool."):
                event = {**event, "call_id": self.tools.call_id}
            await emit(event)

        handoff = DelegationHandoff(
            task=(
                handoff.task + " The transcript is the full current session snapshot. "
                "The latest user correction takes precedence over earlier requests."
            ),
            transcript_srt=handoff.transcript_srt,
            follow_up=handoff.follow_up,
        )
        answer = await super().run(handoff, observed)
        if failed:
            # A model/tool exception may mean accepted work has unknown usage.
            # Stop this session; do not convert it into successful commentary.
            raise RuntimeError("Support backend work failed; do not retry automatically")
        return answer

    async def interrupt(self) -> None:
        routing_pending = self._routing_pending
        try:
            await super().interrupt()
        finally:
            if routing_pending and not (
                type(self.agent.router) is ScriptedRouter
                or getattr(self.agent.router, "cancellation_safe", False) is True
            ):
                self.admission_error = (
                    "Provider route interrupted; acceptance and usage may be unknown"
                )
            self._routing_pending = False

    async def close(self) -> None:
        errors = []
        try:
            await super().close()
        except BaseException as error:
            errors.append(error)

        async def close_owner(owner):
            close = getattr(owner, "close", None)
            if close is not None:
                result = close()
                if inspect.isawaitable(result):
                    await result

        # Independent attempts: one owner's failure must not skip the other.
        # Keep cleanup in the owning task rather than detach new cleanup tasks.
        for owner in (self.owned_executor, self.agent.router):
            try:
                async with asyncio.timeout(2):
                    await close_owner(owner)
            except BaseException as error:
                errors.append(error)
        if len(errors) == 1:
            raise errors[0]
        if errors:
            raise BaseExceptionGroup("Support backend cleanup failed", errors)


class ConversationSnapshot:
    """Rebuild with the shared ledger so corrections aren't lost as suffixes."""

    def __init__(self, initial_items: list[dict[str, Any]] | None) -> None:
        self.initial_items = copy.deepcopy(initial_items or [])
        self.events: list[dict[str, Any]] = []

    def record_event(self, event: dict[str, Any]) -> None:
        self.events.append(copy.deepcopy(event))

    def consume_srt(self) -> str:
        ledger = TranscriptLedger()
        ledger.add_history(self.initial_items)
        for event in self.events:
            ledger.record_event(event)
        return ledger.consume_srt()


class SupersedingController(ClientDelegationController):
    """A new user transcript invalidates pending work before awaiting cleanup.

    Only a fresh delegation admits replacement work. A cancellation does not
    retract commentary already sent or establish cancellation/billing at a
    provider. Full snapshots are bounded by the surrounding service limits.
    """

    def __init__(self, *, cleanup_timeout: float = 4, **kwargs: Any) -> None:
        send_live, emit = kwargs["send_live"], kwargs["emit"]
        self._revision = 0
        self._run_revision: ContextVar[int | None] = ContextVar("support_revision", default=None)
        self._superseded: set[str] = set()
        self._input_events: set[str] = set()
        self.cleanup_timeout = cleanup_timeout

        def ensure_current() -> None:
            revision = self._run_revision.get()
            if revision is not None and (revision != self._revision or self._closed):
                raise asyncio.CancelledError

        async def guarded_send(event: dict[str, Any]) -> None:
            ensure_current()
            await send_live(event)
            ensure_current()

        async def guarded_emit(event: dict[str, Any]) -> None:
            ensure_current()
            await emit(event)
            ensure_current()

        super().__init__(**{**kwargs, "send_live": guarded_send, "emit": guarded_emit})
        self.transcript = ConversationSnapshot(kwargs.get("initial_items"))

    async def observe(self, event: dict[str, Any]) -> None:
        self._work.ensure_open()
        event_id = event.get("event_id")
        user_text = event.get("type") == "session.input_transcript.delta" and event.get("delta")
        if user_text and (not event_id or event_id not in self._input_events):
            if event_id:
                self._input_events.add(event_id)
            self._revision += 1
            tasks = dict(self._tasks)
            self._superseded.update(tasks)
            for task in tasks.values():
                task.cancel()
            if tasks:
                _, pending = await asyncio.wait(tasks.values(), timeout=self.cleanup_timeout)
                if pending:
                    self._work.fail("Superseded work did not stop; external usage may be unknown")
                    self._work.seal()
                    raise RuntimeError("Superseded work did not stop before cleanup deadline")
                if error := getattr(self.backend, "admission_error", None):
                    self._work.fail(error)
                    self._work.seal()
                    raise RuntimeError(error)
                for identifier in tasks:
                    await self.emit(
                        {
                            "type": "client_delegation.superseded",
                            "delegation_id": identifier,
                            "revision": self._revision,
                            "reason": "new_user_transcript",
                        }
                    )
        await super().observe(event)

    async def _run(self, identifier: str, handoff: DelegationHandoff) -> None:
        token = self._run_revision.set(self._revision)
        try:
            await super()._run(identifier, handoff)
        finally:
            self._run_revision.reset(token)

    def _finished(self, identifier: str, task: asyncio.Task[None]) -> None:
        if identifier in self._superseded:
            self._tasks.pop(identifier, None)
            self._superseded.discard(identifier)
            if not task.cancelled() and task.exception() is not None:
                self._work.fail("Superseded work failed during cleanup")
            if error := getattr(self.backend, "admission_error", None):
                self._work.fail(error)
            self._work.finish(identifier)
        else:
            super()._finished(identifier, task)


def support_backend(router: RoutingBackend, execute_tool: ToolCallback) -> SupportBackend:
    """Consume a session-owned router; close it when this backend closes."""
    return SupportBackend(router, execute_tool)


def create_support_app(
    router_factory: Callable[[], RoutingBackend] = ScriptedRouter,
    *,
    token: str,
    limits: ServiceLimits = SUPPORT_LIMITS,
    executor_factory: Callable[[], Any] | None = None,
):
    """Serve one independently owned router/session and optional async executor.

    For real stdio MCP pass ``executor_factory=MCPExecutor``. Trusted per-case
    state can use ``lambda: MCPExecutor(MCPFixtureConfig.from_case(case))``.
    Without a factory, lookups use direct fixture functions, not MCP transport.
    """
    if (
        limits.max_connections != 1
        or limits.max_pending_delegations != 1
        or limits.max_delegations > 2
    ):
        raise ValueError(
            "Support example permits one connection, one pending request, two delegations"
        )
    # The shared service's execute callback uses to_thread for synchronous tools.
    # Pair its observer with an async executor here so cancellation reaches MCP.
    pending_executor: ContextVar[Any] = ContextVar("support_executor", default=None)

    def tools(_configuration):
        executor = executor_factory() if executor_factory else SyntheticSupportExecutor()
        pending_executor.set(executor)
        return executor

    def backend(_configuration, synchronous_execute):
        executor = pending_executor.get()
        pending_executor.set(None)
        if executor_factory is None:
            return support_backend(router_factory(), synchronous_execute)
        if not inspect.iscoroutinefunction(executor.execute):
            raise TypeError("Injected executor must expose asynchronous execute")

        async def execute(name, arguments, call_id):
            return await executor.execute(name, arguments, call_id=call_id)

        return SupportBackend(router_factory(), execute, owned_executor=executor)

    return create_app(
        token=token,
        limits=limits,
        tool_factory=tools,
        backend_factory=backend,
        controller_factory=SupersedingController,
    )
