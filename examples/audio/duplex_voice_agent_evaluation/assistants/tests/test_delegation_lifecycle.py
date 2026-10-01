"""The managed, local-client, and remote-client controllers share one lifecycle contract."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import aiohttp
import pytest

from assistants.client.delegation import ClientDelegationController
from assistants.client.remote import RemoteClientDelegationController
from assistants.errors import LiveResponseError
from assistants.frontend.assistant import LiveFrontend
from assistants.frontend.connection import AssistantConnection, DelegationController
from assistants.responses.delegation import ResponsesDelegationController
from assistants.runtime import RemoteToolObserver

MODES = ("responses", "client", "remote")


def request(identifier: str) -> dict[str, Any]:
    return {
        "type": "session.delegation.created",
        "delegation": {"id": identifier, "target": "client", "content": [{"type": "input_text", "text": identifier}]},
    }


def function_call(identifier: str) -> dict[str, Any]:
    return {
        "type": "response.output_item.done",
        "response_id": identifier,
        "item": {
            "id": identifier,
            "call_id": identifier,
            "type": "function_call",
            "status": "completed",
            "name": "lookup",
            "arguments": {},
        },
    }


class ControlledBackend:
    def __init__(self) -> None:
        self.executions: list[dict[str, Any]] = []
        self.gates = {name: asyncio.Event() for name in ("one", "two")}
        self.started = {name: asyncio.Event() for name in self.gates}
        self.cancelled = asyncio.Event()
        self.failure: Exception | None = None
        self.close_calls = 0

    async def work(self, identifier: str) -> str:
        self.started[identifier].set()
        try:
            await self.gates[identifier].wait()
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        if self.failure is not None:
            raise self.failure
        return "Result " + identifier

    async def run(self, handoff: Any, emit: Any) -> str:
        return await self.work("two" if handoff.follow_up else "one")

    async def execute(self, name: str, arguments: dict[str, Any], *, call_id: str) -> dict[str, Any]:
        return {"answer": await self.work(call_id)}

    def snapshot(self) -> dict[str, Any]:
        return {}

    async def close(self) -> None:
        self.close_calls += 1


class Socket:
    def __init__(self) -> None:
        self.messages: asyncio.Queue[Any] = asyncio.Queue()
        self.sent: list[dict[str, Any]] = []
        self.closed = False
        self.close_calls = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        value = await self.messages.get()
        if value is None:
            raise StopAsyncIteration
        return SimpleNamespace(type=aiohttp.WSMsgType.TEXT, json=lambda: value)

    async def send_json(self, event: dict[str, Any]) -> None:
        self.sent.append(event)

    async def close(self) -> None:
        self.closed = True
        self.close_calls += 1


@dataclass
class Case:
    mode: str
    backend: ControlledBackend = field(default_factory=ControlledBackend)
    socket: Socket = field(default_factory=Socket)
    emitted: list[dict[str, Any]] = field(default_factory=list)
    sent: list[dict[str, Any]] = field(default_factory=list)
    controller: DelegationController = field(init=False)
    publish_gate: asyncio.Event = field(default_factory=asyncio.Event)
    publishing: asyncio.Event = field(default_factory=asyncio.Event)

    def __post_init__(self) -> None:
        self.publish_gate.set()
        if self.mode == "responses":
            self.controller = ResponsesDelegationController(executor=self.backend, send_live=self.send, emit=self.emit)
        elif self.mode == "client":
            self.controller = ClientDelegationController(backend=self.backend, send_live=self.send, emit=self.emit)
        else:
            remote = RemoteClientDelegationController(
                endpoint="wss://example.test/ws",
                configuration={},
                send_live=self.send,
                emit=self.emit,
                tool_observer=RemoteToolObserver(initial_state={}, facts={}),
            )
            remote.connection = self.socket
            remote.receiver = asyncio.create_task(remote._receive())
            remote.receiver.add_done_callback(remote._receiver_finished)
            self.controller = remote

    async def send(self, event: dict[str, Any]) -> None:
        self.publishing.set()
        await self.publish_gate.wait()
        self.sent.append(event)
        if self.mode == "responses" and event["type"] == "response.create":
            identifier = event["event_id"].removeprefix("continue_")

            async def followup():
                await asyncio.sleep(0)
                await self.controller.observe(
                    {
                        "type": "response.created",
                        "response": {"id": identifier + "_followup", "previous_response_id": identifier},
                    }
                )
                await self.controller.observe(
                    {"type": "response.completed", "response": {"id": identifier + "_followup", "output": []}}
                )

            asyncio.create_task(followup())

    async def emit(self, event: dict[str, Any]) -> None:
        self.emitted.append(event)

    async def accept(self, identifier: str) -> None:
        event = function_call(identifier) if self.mode == "responses" else request(identifier)
        if self.mode == "responses" and identifier not in self.controller.responses:
            await self.controller.observe({"type": "response.created", "response": {"id": identifier}})
        await self.controller.observe(event)
        if self.mode == "responses":
            await self.controller.observe({"type": "response.completed", "response": {"id": identifier, "output": []}})

    async def release(self, identifier: str) -> None:
        if self.mode != "remote":
            self.backend.gates[identifier].set()
            return
        await self.socket.messages.put(
            {
                "type": "live.send",
                "event": {
                    "type": "session.commentary.append",
                    "delegation_id": identifier,
                    "content": "Result " + identifier,
                },
            }
        )
        await self.socket.messages.put(
            {
                "type": "assistant.event",
                "event": {
                    "type": "client_delegation.completed",
                    "delegation_id": identifier,
                    "text": "Result " + identifier,
                },
            }
        )


@pytest.fixture(params=MODES)
async def case(request: pytest.FixtureRequest):
    item = Case(request.param)
    try:
        yield item
    finally:
        await item.controller.close()


async def test_pending_is_visible_immediately_and_covers_result_publication(case: Case) -> None:
    case.publish_gate.clear()
    await case.accept("one")
    wrapper = AssistantConnection(case.socket, case.controller)
    assert case.controller.pending and wrapper.pending_tools
    waiter = asyncio.create_task(case.controller.wait())
    await case.release("one")
    await asyncio.wait_for(case.publishing.wait(), 1)
    assert case.controller.pending and not waiter.done()
    case.publish_gate.set()
    await asyncio.wait_for(waiter, 1)
    assert not wrapper.pending_tools
    assert len(case.sent) == (2 if case.mode == "responses" else 1)


async def test_frontend_and_connection_expose_the_same_controller_contract(case: Case) -> None:
    frontend = object.__new__(LiveFrontend)
    frontend.controller = case.controller
    wrapper = AssistantConnection(case.socket, case.controller)
    await case.accept("one")
    assert frontend.pending_tools and wrapper.pending_tools
    await case.release("one")
    await asyncio.wait_for(asyncio.gather(frontend.wait_for_tools(), wrapper.wait_for_tools()), 1)
    assert not frontend.pending_tools and not wrapper.pending_tools


async def test_frontend_only_caller_has_no_delegation_capability() -> None:
    frontend = object.__new__(LiveFrontend)
    assert not hasattr(frontend, "controller")
    assert not frontend.pending_tools
    await frontend.wait_for_tools()
    await frontend._close_delegation()
    assert not hasattr(frontend, "controller")


async def test_canceling_a_waiter_does_not_cancel_owned_work(case: Case) -> None:
    await case.accept("one")
    waiter = asyncio.create_task(case.controller.wait())
    await asyncio.sleep(0)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    assert case.controller.pending
    assert not case.backend.cancelled.is_set()
    await case.release("one")
    await asyncio.wait_for(case.controller.wait(), 1)
    assert len(case.sent) == (2 if case.mode == "responses" else 1)


async def test_overlapping_and_duplicate_work_reaches_real_quiescence(case: Case) -> None:
    await case.accept("one")
    waiter = asyncio.create_task(case.controller.wait())
    await asyncio.sleep(0)
    await case.accept("two")
    await case.accept("one")
    await case.release("one")
    await asyncio.wait_for(case.publishing.wait(), 1)
    assert case.controller.pending and not waiter.done()
    await case.release("two")
    await asyncio.wait_for(waiter, 1)
    assert not case.controller.pending
    assert len(case.sent) == (4 if case.mode == "responses" else 2)


async def test_failure_is_retained_for_current_and_later_waiters(case: Case) -> None:
    await case.accept("one")
    waiter = asyncio.create_task(case.controller.wait())
    if case.mode == "remote":
        await case.socket.messages.put({"type": "error", "error": {"message": "private failure"}})
    else:
        case.backend.failure = RuntimeError("private failure")
        await case.release("one")
    for waiting in (waiter, case.controller.wait()):
        with pytest.raises(LiveResponseError) as error:
            await asyncio.wait_for(waiting, 1)
        assert "private failure" not in str(error.value)
        assert (
            error.value.failure_stage
            == {"responses": "tool_execution", "client": "client_delegation", "remote": "client_assistant_connection"}[
                case.mode
            ]
        )
    assert not case.controller.pending
    assert any(event["type"] == "error" for event in case.emitted)


async def test_close_abandons_pending_work_and_rejects_late_acceptance(case: Case) -> None:
    await case.accept("one")
    waiter = asyncio.create_task(case.controller.wait())
    await asyncio.wait_for(asyncio.gather(case.controller.close(), case.controller.close()), 1)
    with pytest.raises(LiveResponseError):
        await asyncio.wait_for(waiter, 1)
    assert not case.controller.pending
    assert case.sent == []
    with pytest.raises(RuntimeError, match="closed"):
        await case.accept("two")
    assert case.backend.close_calls == (1 if case.mode == "client" else 0)
    assert case.socket.close_calls == (1 if case.mode == "remote" else 0)


@pytest.mark.parametrize("mode", ["responses", "client"])
async def test_unexpected_owned_task_cancellation_is_not_success(mode: str) -> None:
    item = Case(mode)
    try:
        await item.accept("one")
        tasks = item.controller.runtime._tasks if mode == "responses" else item.controller._tasks.values()
        for task in tuple(tasks):
            task.cancel()
        with pytest.raises(LiveResponseError, match="cancelled"):
            await asyncio.wait_for(item.controller.wait(), 1)
        assert not item.controller.pending
    finally:
        await item.controller.close()


@pytest.mark.parametrize(
    "message",
    [
        {"type": "assistant.event", "event": {"type": "client_delegation.completed", "delegation_id": "unknown"}},
        {"type": "assistant.event", "event": {"type": "client_delegation.completed", "delegation_id": "one"}},
        {"type": "live.send", "event": {"type": "session.commentary.append", "delegation_id": "unknown"}},
        None,
    ],
)
async def test_remote_missing_or_uncorrelated_completion_fails_wait(message: dict | None) -> None:
    item = Case("remote")
    try:
        await item.accept("one")
        await item.socket.messages.put(message)
        with pytest.raises(LiveResponseError):
            await asyncio.wait_for(item.controller.wait(), 1)
        assert len([event for event in item.emitted if event["type"] == "error"]) == 1
        assert not item.controller.pending
    finally:
        await item.controller.close()


async def test_expected_remote_shutdown_with_pending_work_is_not_success() -> None:
    item = Case("remote")
    try:
        await item.accept("one")
        await item.controller.observe({"type": "session.closed"})
        await item.socket.messages.put({"type": "session.closed"})
        with pytest.raises(LiveResponseError, match="unfinished"):
            await asyncio.wait_for(item.controller.wait(), 1)
        assert item.emitted[-1]["error"]["code"] == "client_assistant_incomplete"
    finally:
        await item.controller.close()


async def test_remote_receiver_canceled_before_start_wakes_waiters() -> None:
    item = Case("remote")
    try:
        await item.accept("one")
        item.controller.receiver.cancel()
        with pytest.raises(LiveResponseError, match="cancelled"):
            await asyncio.wait_for(item.controller.wait(), 1)
    finally:
        await item.controller.close()


async def test_managed_call_is_pending_before_its_started_event_can_block() -> None:
    backend = ControlledBackend()
    publishing = asyncio.Event()
    release = asyncio.Event()

    async def emit(event: dict[str, Any]) -> None:
        if event["type"] == "tool.called":
            publishing.set()
            await release.wait()

    async def send(event: dict[str, Any]) -> None:
        if event["type"] == "response.create":
            await controller.observe(
                {"type": "response.created", "response": {"id": "followup", "previous_response_id": "one"}}
            )
            await controller.observe({"type": "response.completed", "response": {"id": "followup", "output": []}})

    controller = ResponsesDelegationController(executor=backend, send_live=send, emit=emit)
    try:
        await controller.observe({"type": "response.created", "response": {"id": "one"}})
        await controller.observe(function_call("one"))
        await controller.observe({"type": "response.completed", "response": {"id": "one", "output": []}})
        assert controller.pending
        await asyncio.wait_for(publishing.wait(), 1)
        assert not backend.started["one"].is_set()
        release.set()
        backend.gates["one"].set()
        await asyncio.wait_for(controller.wait(), 1)
    finally:
        release.set()
        await controller.close()


async def test_remote_forward_failure_releases_accepted_work() -> None:
    item = Case("remote")

    async def fail(event: dict[str, Any]) -> None:
        raise ConnectionError("private send detail")

    item.socket.send_json = fail
    try:
        with pytest.raises(LiveResponseError):
            await item.accept("one")
        with pytest.raises(LiveResponseError) as error:
            await asyncio.wait_for(item.controller.wait(), 1)
        assert "private send detail" not in str(error.value)
        assert not item.controller.pending
    finally:
        await item.controller.close()
