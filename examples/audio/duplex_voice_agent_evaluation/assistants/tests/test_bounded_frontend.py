"""Provider-free checks for the opt-in finite frontend lifecycle."""

import asyncio
import json
from contextlib import suppress
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

import assistants.frontend.assistant as frontend_module
import assistants.frontend.bounded as policy
from assistants.frontend.assistant import LiveFrontend

MODEL = "gpt-live-1"
START = {"type": "session.started", "session": {"id": "live_test", "model": MODEL}}
FINAL = {"type": "session.closed", "session": START["session"], "usage": {"seconds": 2.5}}


class Socket:
    def __init__(self, *, acknowledge=True, final=None, close_error=None):
        self.events = asyncio.Queue()
        self.sent = []
        self.closed = False
        self.acknowledge = acknowledge
        self.final = FINAL if final is None else final
        self.close_error = close_error
        self.internal_error = None
        self.on_send = None

    def __aiter__(self):
        return self

    async def __anext__(self):
        event = await self.events.get()
        if event is None:
            raise StopAsyncIteration
        return SimpleNamespace(type=aiohttp.WSMsgType.TEXT, data=json.dumps(event))

    async def send_json(self, event):
        if self.on_send:
            self.on_send(event)
        self.sent.append(event)
        if event["type"] == "session.start" and self.acknowledge:
            await self.events.put(START)
        if event["type"] == "session.close":
            await self.events.put(self.final)

    async def close(self):
        if self.close_error:
            raise self.close_error
        self.closed = True

    def exception(self):
        return self.internal_error


class Session:
    def __init__(self, socket):
        self.socket = socket
        self.closed = False
        self.connector = SimpleNamespace(closed=False)
        self._retry_connection = True
        self.calls = []

    async def ws_connect(self, url, **kwargs):
        assert self._retry_connection is False
        self.calls.append((url, kwargs))
        return self.socket

    async def close(self):
        self.closed = True
        self.connector.closed = True


def frontend(monkeypatch, socket=None, observer=None):
    socket = socket or Socket()
    session = Session(socket)

    monkeypatch.setattr(frontend_module.aiohttp, "ClientSession", lambda **kwargs: session)
    monkeypatch.setattr(frontend_module, "configured_proxy", lambda url: "http://configured.invalid:8080")
    agent = LiveFrontend(
        scenario=object(),
        settings=SimpleNamespace(agent_instructions="Synthetic support", backend_instructions="", delegation_tools=[]),
        api_key="unused-test-value",
        config=SimpleNamespace(
            endpoint="https://api.openai.com/v1/live/sessions", model=MODEL, voice="marin", assistant_mode="client"
        ),
        bounded=True,
        raw_observer=observer,
    )
    return agent, session, socket


async def test_start_registers_reader_before_dispatch_and_exposes_collector_facade(monkeypatch):
    observed = []
    agent, session, socket = frontend(
        monkeypatch, observer=lambda event, direction: observed.append((event, direction))
    )

    def on_send(event):
        if event["type"] == "session.start":
            assert agent.receiver is not None and not agent.receiver.done()

    socket.on_send = on_send
    await agent.start()
    assert agent.start_sent and agent.start_event == START
    assert (await agent.receive_json(timeout=0.1))["type"] == "session.started"
    await agent.send_json({"type": "session.input_audio.append", "audio": "AAAA"})
    assert session.calls[0][1]["proxy"] == "http://configured.invalid:8080"
    assert session.calls[0][1]["timeout"].ws_close == 0.25
    await agent.close()
    assert agent.final_event == FINAL and agent.finalization_confirmed
    assert agent.transport_closed and session.closed
    assert (FINAL, "server_to_client") in observed
    assert not agent.cleanup_errors
    with pytest.raises(RuntimeError, match="cannot reconnect"):
        await agent.start()
    assert len(session.calls) == 1


async def test_application_error_does_not_hide_raw_close_and_seals_dispatch(monkeypatch):
    agent, session, socket = frontend(monkeypatch)
    agent._close_delegation = AsyncMock()
    await agent.start()
    await agent.receive_json()
    await socket.events.put({"type": "error", "error": {"code": "provider_failure"}})
    assert (await agent.receive_json(timeout=0.1))["type"] == "error"
    with pytest.raises(RuntimeError, match="sealed"):
        await agent.send_json({"type": "session.commentary.append", "content": "late"})
    await agent.close()
    assert agent.final_event == FINAL and agent.finalization_confirmed and session.closed
    agent._close_delegation.assert_awaited_once()
    with pytest.raises(EOFError):
        await agent.receive_json()


async def test_observer_failure_disables_observer_stops_backend_and_retains_close(monkeypatch):
    seen = []

    def observer(event, direction):
        seen.append(event["type"])
        if event["type"] == "session.output_audio.delta":
            raise ValueError("observation limit")

    agent, _, socket = frontend(monkeypatch, observer=observer)
    stopped = asyncio.Event()
    agent._close_delegation = AsyncMock(side_effect=stopped.set)
    await agent.start()
    await agent.receive_json()
    await socket.events.put({"type": "session.output_audio.delta", "delta": "AAAA"})
    assert (await agent.receive_json(timeout=0.1))["type"] == "error"
    await asyncio.wait_for(stopped.wait(), 0.1)
    await agent.close()
    assert agent.raw_observer is None and agent.finalization_confirmed
    assert {"stage": "raw_observer", "error_class": "ValueError"} in agent.cleanup_errors
    assert "session.closed" not in seen


async def test_controller_observe_error_preserves_reader(monkeypatch):
    agent, _, socket = frontend(monkeypatch)
    await agent.start()
    await agent.receive_json()
    agent._observe_event = AsyncMock(side_effect=RuntimeError("local backend failed"))
    await socket.events.put({"type": "session.input_transcript.delta", "delta": "test"})
    await agent.receive_json()
    assert (await agent.receive_json(timeout=0.1))["type"] == "error"
    await agent.close()
    assert agent.finalization_confirmed


async def test_malformed_response_envelope_preserves_finalization_reader(monkeypatch):
    agent, _, socket = frontend(monkeypatch)
    await agent.start()
    await agent.receive_json()
    await socket.events.put({"type": "response.event", "event": []})
    assert (await agent.receive_json(timeout=0.1))["type"] == "error"
    await agent.close()
    assert agent.finalization_confirmed


async def test_observer_rejecting_start_prevents_dispatch(monkeypatch):
    def observer(event, direction):
        if event["type"] == "session.start":
            raise ValueError("Capture unavailable")

    agent, session, socket = frontend(monkeypatch, observer=observer)
    with pytest.raises(ValueError, match="Capture unavailable"):
        await agent.start()
    assert not agent.start_sent and socket.sent == []
    assert session.closed and agent.transport_closed
    assert agent.cleanup_errors == [{"stage": "raw_observer", "error_class": "ValueError"}]


async def test_observer_failure_during_close_does_not_prevent_finalization(monkeypatch):
    def observer(event, direction):
        if event["type"] == "session.close":
            raise ValueError("Capture limit")

    agent, session, socket = frontend(monkeypatch, observer=observer)
    await agent.start()
    await agent.close()
    assert agent.finalization_confirmed and session.closed
    assert any(event["type"] == "session.close" for event in socket.sent)
    assert agent.cleanup_errors == [{"stage": "raw_observer", "error_class": "ValueError"}]


async def test_blocked_close_send_is_bounded_and_http_still_closes(monkeypatch):
    agent, session, socket = frontend(monkeypatch)
    await agent.start()
    original_send = socket.send_json
    send_cancelled = asyncio.Event()

    async def blocked_send(event):
        if event["type"] == "session.close":
            try:
                await asyncio.Event().wait()
            finally:
                send_cancelled.set()
        await original_send(event)

    socket.send_json = blocked_send
    original_step = agent._cleanup_step

    async def short_step(work, seconds, deadline):
        return await original_step(work, min(seconds, 0.02), deadline)

    agent._cleanup_step = short_step
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(agent.close(), 0.3)
    assert send_cancelled.is_set()
    assert session.closed and agent.transport_closed
    assert not agent.finalization_confirmed
    assert {"stage": "finalization", "error_class": "TimeoutError"} in agent.cleanup_errors


async def test_missing_start_ack_still_requests_close_and_keeps_raw_receipt(monkeypatch):
    agent, session, socket = frontend(monkeypatch, Socket(acknowledge=False))
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(agent.start(), 0.02)
    assert agent.start_sent and agent.start_event is None
    assert any(event["type"] == "session.close" for event in socket.sent)
    assert agent.final_event == FINAL and not agent.finalization_confirmed
    assert session.closed and agent.cleanup_errors


async def test_close_seals_and_stops_delegation_before_provider_close(monkeypatch):
    agent, _, socket = frontend(monkeypatch)
    stopped = False

    async def close_delegation():
        nonlocal stopped
        with pytest.raises(RuntimeError, match="sealed"):
            await agent.send_json({"type": "session.commentary.append", "content": "late"})
        stopped = True

    def on_send(event):
        if event["type"] == "session.close":
            assert stopped

    socket.on_send = on_send
    agent._close_delegation = close_delegation
    await agent.start()
    await agent.close()
    assert agent.finalization_confirmed


@pytest.mark.parametrize("seconds", [True, False, None, -1, float("nan"), float("inf"), "2", 10**400])
def test_finalization_requires_real_finite_nonboolean_usage(seconds):
    final = {**FINAL, "usage": {"seconds": seconds}}
    assert not policy.confirmed_close(START, final, MODEL)


@pytest.mark.parametrize("field,value", [("id", "different"), ("model", "different")])
def test_finalization_requires_matching_session_and_model(field, value):
    final = {**FINAL, "session": {**FINAL["session"], field: value}}
    assert not policy.confirmed_close(START, final, MODEL)
    assert not policy.confirmed_close(START, {**FINAL, "_synthetic": True}, MODEL)


@pytest.mark.parametrize("internal", [False, True])
@pytest.mark.parametrize("valid", [False, True])
async def test_ws_timeout_only_warns_after_verified_provider_and_transport_close(monkeypatch, internal, valid):
    final = FINAL if valid else {**FINAL, "usage": {"seconds": True}}
    socket = Socket(final=final, close_error=None if internal else TimeoutError())
    socket.internal_error = TimeoutError() if internal else None
    agent, session, _ = frontend(monkeypatch, socket)
    await agent.start()
    if valid:
        await agent.close()
        assert agent.cleanup_warnings == [{"stage": "websocket", "error_class": "TimeoutError"}]
    else:
        with pytest.raises(BaseExceptionGroup):
            await agent.close()
        assert not agent.cleanup_warnings
    assert session.closed and agent.transport_closed


async def test_http_closes_even_if_websocket_close_fails(monkeypatch):
    agent, session, _ = frontend(monkeypatch, Socket(close_error=ConnectionError()))
    await agent.start()
    with pytest.raises(ConnectionError):
        await agent.close()
    assert session.closed and agent.transport_closed and not agent.cleanup_warnings


async def test_unverified_http_close_remains_failure(monkeypatch):
    agent, session, _ = frontend(monkeypatch, Socket(close_error=TimeoutError()))
    session.close = AsyncMock()
    await agent.start()
    with pytest.raises(BaseExceptionGroup):
        await agent.close()
    assert not agent.transport_closed and not agent.cleanup_warnings


async def test_uncooperative_cleanup_closes_transport_but_reports_pending_owned_work(monkeypatch):
    agent, session, _ = frontend(monkeypatch)
    release = asyncio.Event()

    async def stubborn_close():
        while not release.is_set():
            with suppress(asyncio.CancelledError):
                await release.wait()

    original = agent._cleanup_step

    async def short_step(work, seconds, deadline):
        return await original(work, min(seconds, 0.02), deadline)

    agent._cleanup_step = short_step
    agent._close_delegation = stubborn_close
    await agent.start()
    try:
        with pytest.raises(BaseExceptionGroup):
            await asyncio.wait_for(agent.close(), 1)
        assert session.closed and agent.transport_closed
        assert {"stage": "delegation", "error_class": "TimeoutError"} in agent.cleanup_errors
        assert {"stage": "owned_tasks", "error_class": "IncompleteCleanup"} in agent.cleanup_errors
        assert any(not task.done() for task in agent._cleanup_tasks)
    finally:
        # This artificial backend refuses every cancellation. A real asyncio.run
        # could wait indefinitely without cooperation or a process supervisor;
        # the frontend promises bounded waits and explicit failure, not forced exit.
        release.set()
        await asyncio.gather(*agent._cleanup_tasks, return_exceptions=True)


async def test_cleanup_joins_owned_tasks_that_finish_after_initial_timeout(monkeypatch):
    agent, session, _ = frontend(monkeypatch)

    async def slow_cancel():
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            await asyncio.sleep(0)

    original = agent._cleanup_step

    async def short_step(work, seconds, deadline):
        return await original(work, min(seconds, 0.02), deadline)

    agent._cleanup_step = short_step
    agent._close_delegation = slow_cancel
    await agent.start()
    with pytest.raises(TimeoutError):
        await agent.close()
    assert session.closed and agent.transport_closed
    assert not any(not task.done() for task in agent._cleanup_tasks)
    assert not any(error["error_class"] == "IncompleteCleanup" for error in agent.cleanup_errors)


def test_configured_proxy_preserves_https_and_no_proxy(monkeypatch):
    monkeypatch.setattr(policy, "getproxies", lambda: {"https": "http://configured.invalid:8080"})
    monkeypatch.setattr(policy, "proxy_bypass", lambda host: host == "local.invalid")
    assert policy.configured_proxy("wss://api.openai.com/v1/live/sessions") == "http://configured.invalid:8080"
    assert policy.configured_proxy("wss://local.invalid/live") is None


async def test_retry_switch_is_checked_on_installed_aiohttp_without_network():
    policy.check_transport_support()
    async with aiohttp.ClientSession(trust_env=False) as session:
        policy.disable_connection_retry(session)
        assert session._retry_connection is False
    with pytest.raises(RuntimeError, match="one handshake"):
        policy.disable_connection_retry(SimpleNamespace())


async def test_untested_aiohttp_version_fails_before_transport_creation(monkeypatch):
    agent, session, socket = frontend(monkeypatch)
    monkeypatch.setattr(aiohttp, "__version__", "3.99.0")
    with pytest.raises(RuntimeError, match="cannot support"):
        policy.check_transport_support()
    with pytest.raises(RuntimeError, match="cannot support"):
        await agent.start()
    assert agent.session is None and session.calls == [] and socket.sent == []


@pytest.mark.parametrize("bounded,attempts", [(False, 2), (True, 1)])
async def test_installed_aiohttp_request_loop_does_not_retry_disconnect(monkeypatch, bounded, attempts):
    # Exercise the installed request loop. Both the connector and request send
    # are mocks, so no DNS lookup, socket, credential, or provider is involved.
    response = MagicMock(start=AsyncMock(side_effect=aiohttp.ServerDisconnectedError()))
    send = AsyncMock(return_value=response)
    monkeypatch.setattr(aiohttp.ClientRequest, "send", send)
    async with aiohttp.ClientSession(trust_env=False) as session:
        connection = MagicMock()
        connect = AsyncMock(return_value=connection)
        monkeypatch.setattr(session.connector, "connect", connect)
        if bounded:
            policy.disable_connection_retry(session)
        with pytest.raises(aiohttp.ServerDisconnectedError):
            await session.ws_connect("wss://offline.invalid/live")
        assert connect.await_count == attempts
        assert send.await_count == attempts
        assert response.start.await_count == attempts
        assert connection.close.call_count == attempts


async def test_installed_aiohttp_connect_timeout_makes_one_attempt_and_no_send(monkeypatch):
    send = AsyncMock()
    monkeypatch.setattr(aiohttp.ClientRequest, "send", send)
    async with aiohttp.ClientSession(trust_env=False) as session:
        connect = AsyncMock(side_effect=TimeoutError("private endpoint omitted"))
        monkeypatch.setattr(session.connector, "connect", connect)
        policy.disable_connection_retry(session)
        with pytest.raises(aiohttp.ConnectionTimeoutError) as caught:
            await session.ws_connect("wss://offline.invalid/live")
        assert connect.await_count == 1 and send.await_count == 0
        assert policy.exception_classes(caught.value) == ["ConnectionTimeoutError", "TimeoutError"]


async def test_transport_observations_retain_only_counts_and_exception_classes():
    observations = {"connection_attempts": 0, "request_headers_sent": 0, "error_classes": []}
    trace = policy.bounded_trace_config(observations)
    trace.freeze()
    await trace.on_connection_create_start.send(None, None, None)
    await trace.on_request_headers_sent.send(None, None, None)
    error = ConnectionError("sensitive proxy or endpoint information")
    error.__cause__ = TimeoutError("sensitive details")
    await trace.on_request_exception.send(None, None, SimpleNamespace(exception=error))
    assert observations == {
        "connection_attempts": 1,
        "request_headers_sent": 1,
        "error_classes": ["ConnectionError", "TimeoutError"],
    }
