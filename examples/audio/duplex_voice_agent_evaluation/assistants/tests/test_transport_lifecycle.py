"""Every assistant receiver must wake its consumer when the transport ends."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import aiohttp
import pytest

from assistants.client.remote import RemoteClientDelegationController
from assistants.config import LiveAgentSettings
from assistants.frontend.assistant import LiveFrontend
from assistants.frontend.connection import AssistantConnection
from assistants.frontend.events import EventQueue
from assistants.runtime import RemoteToolObserver


class Socket:
    def __init__(self, messages: list[Any] = ()) -> None:
        self.messages: asyncio.Queue[Any] = asyncio.Queue()
        for item in messages:
            self.messages.put_nowait(item)
        self.closed = False
        self.close_calls = 0
        self.sent: list[dict[str, Any]] = []

    def __aiter__(self) -> Socket:
        return self

    async def __anext__(self) -> Any:
        item = await self.messages.get()
        if item is None:
            raise StopAsyncIteration
        if isinstance(item, Exception):
            raise item
        if isinstance(item, SimpleNamespace):
            return item
        raw = item if isinstance(item, str) else json.dumps(item)
        return SimpleNamespace(type=aiohttp.WSMsgType.TEXT, data=raw, json=lambda: json.loads(raw))

    async def receive_json(self, **_: Any) -> Any:
        try:
            return (await self.__anext__()).json()
        except StopAsyncIteration as error:
            raise EOFError("socket ended") from error

    async def send_json(self, event: dict[str, Any]) -> None:
        self.sent.append(event)
        if event.get("type") == "session.close":
            await self.messages.put(None)

    async def close(self) -> None:
        self.closed = True
        self.close_calls += 1


def frontend(socket: Socket) -> LiveFrontend:
    agent = LiveFrontend(scenario=object(), settings=None, api_key="test-key", config=LiveAgentSettings())
    agent.ws = socket
    agent.session = SimpleNamespace(close=AsyncMock())
    return agent


async def collect(agent: LiveFrontend) -> list[dict[str, Any]]:
    return [event async for event in agent.incoming()]


@pytest.mark.parametrize(
    ("messages", "code"),
    [
        ([None], "live_unexpected_eof"),
        (["not JSON"], "live_protocol_error"),
        ([[]], "live_protocol_error"),
        ([{}], "live_protocol_error"),
        ([ConnectionError("socket broke")], "live_transport_error"),
        ([SimpleNamespace(type=aiohttp.WSMsgType.ERROR)], "live_transport_error"),
    ],
)
async def test_frontend_failures_wake_waiting_consumer(messages: list[Any], code: str) -> None:
    agent = frontend(Socket(messages))
    consumer = asyncio.create_task(collect(agent))
    agent.receiver = asyncio.create_task(agent._receive())
    events = await asyncio.wait_for(consumer, 0.5)
    await agent.receiver
    assert len(events) == 1
    assert events[0]["error"]["code"] == code
    await agent.close()
    assert agent.events.empty()
    assert await asyncio.wait_for(collect(agent), 0.5) == []


@pytest.mark.parametrize("terminal", [{"type": "session.closed"}, {"type": "error", "error": {"code": "provider"}}])
async def test_frontend_preserves_terminal_event_exactly_once(terminal: dict[str, Any]) -> None:
    agent = frontend(Socket([{"type": "session.started"}, terminal, None]))
    agent.receiver = asyncio.create_task(agent._receive())
    assert await asyncio.wait_for(collect(agent), 0.5) == [{"type": "session.started"}, terminal]
    await agent.close()
    assert agent.events.empty()


async def test_frontend_close_cancels_receiver_and_is_idempotent() -> None:
    socket = Socket()
    agent = frontend(socket)
    session = agent.session
    agent._close_delegation = AsyncMock()
    agent.receiver = asyncio.create_task(agent._receive())
    consumer = asyncio.create_task(collect(agent))
    await asyncio.wait_for(asyncio.gather(agent.close(), agent.close()), 0.5)
    assert await consumer == [{"type": "session.closed", "_synthetic": True}]
    agent._close_delegation.assert_awaited_once()
    session.close.assert_awaited_once()
    assert socket.close_calls == 1
    assert agent.receiver is None


async def test_frontend_cleanup_continues_if_delegation_cleanup_fails() -> None:
    socket = Socket()
    agent = frontend(socket)
    session = agent.session
    agent._close_delegation = AsyncMock(side_effect=RuntimeError("cleanup failed"))
    agent.receiver = asyncio.create_task(agent._receive())
    with pytest.raises(RuntimeError, match="cleanup failed"):
        await asyncio.wait_for(agent.close(), 0.5)
    assert await collect(agent) == [{"type": "session.closed", "_synthetic": True}]
    assert socket.closed
    session.close.assert_awaited_once()
    await agent.close()


async def test_direct_receiver_cancellation_is_not_an_infrastructure_error() -> None:
    agent = frontend(Socket())
    agent.receiver = asyncio.create_task(agent._receive())
    await asyncio.sleep(0)
    agent.receiver.cancel()
    await asyncio.gather(agent.receiver, return_exceptions=True)
    assert await asyncio.wait_for(collect(agent), 0.5) == [{"type": "session.closed", "_synthetic": True}]
    await agent.close()


def controller_stub() -> SimpleNamespace:
    return SimpleNamespace(pending=False, observe=AsyncMock(), close=AsyncMock(), wait=AsyncMock())


@pytest.mark.parametrize(
    ("messages", "terminal"),
    [
        ([None], "error"),
        (["bad JSON"], "error"),
        ([[]], "error"),
        ([ConnectionError("broken")], "error"),
        ([{"type": "session.closed"}], "session.closed"),
        ([{"type": "error", "error": {"code": "provider"}}], "error"),
    ],
)
async def test_single_turn_wrapper_has_explicit_terminal_state(messages: list[Any], terminal: str) -> None:
    controller = controller_stub()
    connection = AssistantConnection(Socket(messages), controller)
    await connection.start()
    event = await asyncio.wait_for(connection.receive_json(), 0.5)
    assert event["type"] == terminal
    await connection.receiver
    await connection.close()
    await connection.close()
    controller.close.assert_awaited_once()
    with pytest.raises(EOFError):
        await connection.receive_json()


async def test_wrapper_close_wakes_a_waiting_consumer() -> None:
    controller = controller_stub()
    connection = AssistantConnection(Socket(), controller)
    await connection.start()
    waiting = asyncio.create_task(connection.receive_json())
    await asyncio.wait_for(connection.close(), 0.5)
    assert await waiting == {"type": "session.closed", "_synthetic": True}


async def test_wrapper_receiver_cancelled_before_start_still_wakes_consumer() -> None:
    connection = AssistantConnection(Socket(), controller_stub())
    await connection.start()
    connection.receiver.cancel()
    await asyncio.gather(connection.receiver, return_exceptions=True)
    assert await asyncio.wait_for(connection.receive_json(), 0.5) == {"type": "session.closed", "_synthetic": True}
    await connection.close()


async def test_terminal_queue_drops_late_delegation_events() -> None:
    events = EventQueue()
    await events.put({"type": "error", "error": {"code": "original"}})
    await events.put({"type": "tool.completed"})
    events.finish(closing=True, code="", message="")
    assert events.qsize() == 1
    assert (await events.receive())["error"]["code"] == "original"
    with pytest.raises(EOFError):
        await events.receive()


def remote(socket: Socket, emitted: list[dict[str, Any]]) -> RemoteClientDelegationController:
    async def emit(event: dict[str, Any]) -> None:
        emitted.append(event)

    controller = RemoteClientDelegationController(
        endpoint="ws://127.0.0.1/ws",
        configuration={},
        send_live=AsyncMock(),
        emit=emit,
        tool_observer=RemoteToolObserver(initial_state={}, facts={}),
    )
    controller.connection = socket
    controller.session = SimpleNamespace(close=AsyncMock())
    return controller


@pytest.mark.parametrize(
    ("messages", "code"),
    [
        ([None], "client_assistant_unexpected_eof"),
        (["bad JSON"], "client_assistant_protocol_error"),
        ([[]], "client_assistant_protocol_error"),
        ([{"type": "unknown"}], "client_assistant_protocol_error"),
        ([ConnectionError("broken")], "client_assistant_connection"),
        ([SimpleNamespace(type=aiohttp.WSMsgType.ERROR)], "client_assistant_connection"),
        ([{"type": "error", "error": {"message": "private"}}], "client_assistant_error"),
    ],
)
async def test_remote_receiver_reports_failures_once(messages: list[Any], code: str) -> None:
    emitted = []
    controller = remote(Socket(messages), emitted)
    await asyncio.wait_for(controller._receive(), 0.5)
    await controller.close()
    await controller.close()
    assert len(emitted) == 1
    assert emitted[0]["error"]["code"] == code
    assert "private" not in json.dumps(emitted)


async def test_remote_expected_shutdown_is_silent_and_filters_audio() -> None:
    emitted = []
    socket = Socket([{"type": "session.closed"}])
    controller = remote(socket, emitted)
    await controller.observe({"type": "session.output_audio.delta", "delta": "AAAA"})
    assert socket.sent == []
    await controller.observe({"type": "session.closed"})
    await asyncio.wait_for(controller._receive(), 0.5)
    await controller.close()
    assert emitted == []


async def test_remote_close_cancels_receiver_without_emitting_error() -> None:
    emitted = []
    controller = remote(Socket(), emitted)
    session = controller.session
    controller.receiver = asyncio.create_task(controller._receive())
    await asyncio.sleep(0)
    await asyncio.wait_for(asyncio.gather(controller.close(), controller.close()), 0.5)
    assert emitted == []
    session.close.assert_awaited_once()


async def test_started_frontend_waits_for_real_usage_even_when_close_reply_is_immediate() -> None:
    socket = Socket()
    agent = frontend(socket)
    agent._started = True
    real_close = {"type": "session.closed", "reason": "client_request", "usage": {"seconds": 1.5}}

    async def send(event):
        socket.sent.append(event)
        if event["type"] == "session.close":
            await socket.messages.put(real_close)

    socket.send_json = send
    agent.receiver = asyncio.create_task(agent._receive())
    await agent.close()
    assert agent._finalized.is_set()
    assert await collect(agent) == [real_close]
    assert socket.closed


async def test_started_frontend_socket_eof_cannot_satisfy_finalization() -> None:
    socket = Socket()
    agent = frontend(socket)
    agent._started = True
    agent.receiver = asyncio.create_task(agent._receive())
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(agent.close(), 0.05)
    assert not agent._finalized.is_set()
    assert socket.closed
