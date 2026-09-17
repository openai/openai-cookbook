"""The standalone reference service authenticates before accepting bounded work."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from typing import Any

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from assistants.client.remote import RemoteClientDelegationController
from assistants.client.security import TOKEN_ENV, ServiceLimits, service_token, validate_endpoint
from assistants.client.service import SERVICE_STATE, create_app, parse_args
from assistants.runtime import RemoteToolObserver

TOKEN = "test-service-secret-0123456789abcdef"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def delegation(identifier: str = "one") -> dict[str, Any]:
    return {
        "type": "live.event",
        "event": {
            "type": "session.delegation.created",
            "delegation": {
                "id": identifier,
                "target": "client",
                "content": [{"type": "input_text", "text": "Check availability"}],
            },
        },
    }


class Backend:
    def __init__(self, *, wait: bool = False, fail: bool = False) -> None:
        self.calls = 0
        self.closed = asyncio.Event()
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()
        self.wait = wait
        self.fail = fail

    async def run(self, _handoff: Any, _emit: Any) -> str:
        self.calls += 1
        self.started.set()
        try:
            if self.wait:
                await asyncio.Event().wait()
            if self.fail:
                raise RuntimeError(f"private backend detail {TOKEN}")
            return "Available"
        except asyncio.CancelledError:
            self.cancelled.set()
            raise

    async def close(self) -> None:
        self.closed.set()


def app_for(backend: Backend, **kwargs: Any) -> web.Application:
    return create_app(token=TOKEN, backend_factory=lambda *_: backend, **kwargs)


async def configure(socket: Any) -> None:
    await socket.send_json({"type": "session.configure"})
    assert await socket.receive_json(timeout=1) == {"type": "session.ready"}


async def error_from(socket: Any) -> dict[str, Any]:
    for _ in range(10):
        event = await socket.receive_json(timeout=1)
        if event["type"] == "error":
            return event["error"]
        if event["type"] == "assistant.event" and event["event"]["type"] == "error":
            return event["event"]["error"]
    pytest.fail("No terminal error received")


@pytest.mark.parametrize("token", ["", "short", "x" * 31, "x" * 513, "x" * 32 + "\n", "é" * 32])
def test_service_rejects_missing_or_invalid_secret(monkeypatch: pytest.MonkeyPatch, token: str) -> None:
    monkeypatch.setenv(TOKEN_ENV, token)
    with pytest.raises(ValueError, match=TOKEN_ENV):
        create_app()


@pytest.mark.parametrize("key", ["OPENAI_API_KEY", "OPENAI_RESPONSES_API_KEY"])
def test_service_token_cannot_reuse_provider_key(monkeypatch: pytest.MonkeyPatch, key: str) -> None:
    monkeypatch.setenv(key, TOKEN)
    with pytest.raises(ValueError, match="must not reuse"):
        service_token(TOKEN)


@pytest.mark.parametrize(
    ("headers", "status"),
    [
        ({}, 401),
        ({"Authorization": "Bearer wrong"}, 401),
        ({"Origin": "https://untrusted.example"}, 401),
        ({**AUTH, "Origin": "https://untrusted.example"}, 403),
        ({**AUTH, "Origin": "null"}, 403),
    ],
)
async def test_rejected_handshake_never_constructs_backend(headers: dict[str, str], status: int) -> None:
    calls = []
    app = create_app(
        token=TOKEN, backend_factory=lambda *_: calls.append("backend"), tool_factory=lambda *_: calls.append("tools")
    )
    async with TestClient(TestServer(app)) as client:
        with pytest.raises(aiohttp.WSServerHandshakeError) as failure:
            await client.ws_connect("/ws/assistant", headers=headers)
        assert failure.value.status == status
        assert (await client.get("/health")).status == 200
    assert calls == []


@pytest.mark.parametrize("origin", [None, "https://trusted.example"])
async def test_authenticated_allowed_client_can_delegate(origin: str | None) -> None:
    backend = Backend()
    headers = AUTH if origin is None else {**AUTH, "Origin": origin}
    async with (
        TestClient(TestServer(app_for(backend, allowed_origins=("https://trusted.example",)))) as client,
        client.ws_connect("/ws/assistant", headers=headers) as socket,
    ):
        await configure(socket)
        await socket.send_json(delegation())
        while (event := await socket.receive_json(timeout=1))["type"] != "live.send":
            pass
        assert event["event"]["type"] == "session.commentary.append"
    assert backend.calls == 1
    assert backend.closed.is_set()


@pytest.mark.parametrize(
    "event",
    [
        [],
        {"type": "unknown"},
        {"type": "live.event", "event": {}},
        {"type": "session.configure", "initial_items": ["bad"]},
        {"type": "session.configure", "initial_items": [{"role": "system", "content": []}]},
    ],
)
async def test_invalid_configuration_or_early_event_never_starts_work(event: Any) -> None:
    backend = Backend()
    async with (
        TestClient(TestServer(app_for(backend))) as client,
        client.ws_connect("/ws/assistant", headers=AUTH) as socket,
    ):
        await socket.send_json(event)
        assert (await error_from(socket))["code"] == "client_protocol_error"
    assert backend.calls == 0


@pytest.mark.parametrize(
    "event",
    [
        {"type": "session.configure"},
        {"type": "live.event", "event": {"type": "session.input_audio.append", "audio": "AAAA"}},
        {"type": "live.event", "event": {"type": "session.delegation.created", "delegation": {"target": "client"}}},
        {"type": "live.event", "event": {"type": "turn.done", "turn": {"role": "user", "start_ms": "bad"}}},
        {"type": "live.event", "event": {"type": "session.input_transcript.delta", "item": []}},
    ],
)
async def test_configured_service_rejects_malformed_control_events(event: dict[str, Any]) -> None:
    backend = Backend()
    async with (
        TestClient(TestServer(app_for(backend))) as client,
        client.ws_connect("/ws/assistant", headers=AUTH) as socket,
    ):
        await configure(socket)
        await socket.send_json(event)
        assert (await error_from(socket))["code"] == "client_protocol_error"
    assert backend.calls == 0


async def test_service_rejects_oversized_messages() -> None:
    backend = Backend()
    async with (
        TestClient(TestServer(app_for(backend, limits=replace(ServiceLimits(), max_message_bytes=256)))) as client,
        client.ws_connect("/ws/assistant", headers=AUTH) as socket,
    ):
        await socket.send_str("x" * 1024)
        message = await socket.receive(timeout=1)
        assert message.type in {aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.TEXT}
    assert backend.calls == 0


async def test_connection_limit_is_released_after_disconnect() -> None:
    backend = Backend()
    app = app_for(backend, limits=replace(ServiceLimits(), max_connections=1))
    async with TestClient(TestServer(app)) as client:
        first = await client.ws_connect("/ws/assistant", headers=AUTH)
        with pytest.raises(aiohttp.WSServerHandshakeError) as failure:
            await client.ws_connect("/ws/assistant", headers=AUTH)
        assert failure.value.status == 503
        await first.close()
        async with asyncio.timeout(1):
            while app[SERVICE_STATE].active_connections:  # noqa: ASYNC110 - wait for server handler finalization.
                await asyncio.sleep(0)
        second = await client.ws_connect("/ws/assistant", headers=AUTH)
        await second.close()


async def test_pending_delegation_limit_cancels_outstanding_work() -> None:
    backend = Backend(wait=True)
    limits = replace(ServiceLimits(), max_pending_delegations=1)
    async with (
        TestClient(TestServer(app_for(backend, limits=limits))) as client,
        client.ws_connect("/ws/assistant", headers=AUTH) as socket,
    ):
        await configure(socket)
        await socket.send_json(delegation("one"))
        await asyncio.wait_for(backend.started.wait(), 1)
        await socket.send_json(delegation("two"))
        assert (await error_from(socket))["code"] == "client_limit_reached"
    assert backend.calls == 1
    assert backend.cancelled.is_set()
    assert backend.closed.is_set()


async def test_total_delegation_limit_applies_after_completed_work() -> None:
    backend = Backend()
    limits = replace(ServiceLimits(), max_delegations=1)
    async with (
        TestClient(TestServer(app_for(backend, limits=limits))) as client,
        client.ws_connect("/ws/assistant", headers=AUTH) as socket,
    ):
        await configure(socket)
        await socket.send_json(delegation("one"))
        while True:
            event = await socket.receive_json(timeout=1)
            if event.get("event", {}).get("type") == "client_delegation.completed":
                break
        await socket.send_json(delegation("two"))
        assert (await error_from(socket))["code"] == "client_limit_reached"
    assert backend.calls == 1


@pytest.mark.parametrize("configured", [False, True])
async def test_idle_service_session_has_a_deadline(configured: bool) -> None:
    backend = Backend()
    limits = replace(ServiceLimits(), configure_timeout=0.05, session_timeout=0.1)
    async with (
        TestClient(TestServer(app_for(backend, limits=limits))) as client,
        client.ws_connect("/ws/assistant", headers=AUTH) as socket,
    ):
        if configured:
            await configure(socket)
        assert (await error_from(socket))["code"] == "client_session_timeout"


@pytest.mark.parametrize(
    "limits", [replace(ServiceLimits(), max_events=1), replace(ServiceLimits(), max_session_bytes=40)]
)
async def test_total_session_input_is_bounded(limits: ServiceLimits) -> None:
    backend = Backend()
    async with (
        TestClient(TestServer(app_for(backend, limits=limits))) as client,
        client.ws_connect("/ws/assistant", headers=AUTH) as socket,
    ):
        await configure(socket)
        await socket.send_json(delegation())
        assert (await error_from(socket))["code"] == "client_limit_reached"
    assert backend.calls == 0


@pytest.mark.parametrize("fail", [False, True])
async def test_backend_timeout_and_errors_are_sanitized(fail: bool, caplog: pytest.LogCaptureFixture) -> None:
    backend = Backend(wait=not fail, fail=fail)
    limits = replace(ServiceLimits(), delegation_timeout=0.05)
    async with (
        TestClient(TestServer(app_for(backend, limits=limits))) as client,
        client.ws_connect("/ws/assistant", headers=AUTH) as socket,
    ):
        await configure(socket)
        await socket.send_json(delegation())
        error = await error_from(socket)
        assert error["code"] == "client_assistant_error"
        assert TOKEN not in json.dumps(error)
    assert TOKEN not in caplog.text
    assert backend.closed.is_set()
    if not fail:
        assert backend.cancelled.is_set()


@pytest.mark.parametrize(
    "endpoint",
    [
        "ws://example.com/ws",
        "http://example.com/ws",
        "wss://user:pass@example.com/ws",
        "wss://example.com/ws?token=secret",
        "file:///tmp/socket",
    ],
)
def test_connector_refuses_unsafe_credential_destinations(endpoint: str) -> None:
    with pytest.raises(ValueError):
        validate_endpoint(endpoint)


def test_reference_service_remains_loopback_only() -> None:
    with pytest.raises(SystemExit):
        parse_args(["--host", "0.0.0.0"])
    with pytest.raises(SystemExit):
        parse_args(["--allow-origin", "https://example.com/path"])
    assert parse_args(["--allow-origin", "https://example.com"]).allow_origin == ["https://example.com"]


async def test_connector_does_not_follow_redirects(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_CLIENT_ASSISTANT_ALLOW_INSECURE_LOOPBACK", "true")
    monkeypatch.setenv(TOKEN_ENV, TOKEN)
    reached = []

    async def redirect(_: web.Request) -> web.Response:
        raise web.HTTPFound("/target")

    async def target(_: web.Request) -> web.Response:
        reached.append(True)
        return web.Response()

    async def ignore(_: Any) -> None:
        pass

    app = web.Application()
    app.router.add_get("/redirect", redirect)
    app.router.add_get("/target", target)
    async with TestClient(TestServer(app)) as client:
        controller = RemoteClientDelegationController(
            endpoint=str(client.make_url("/redirect")),
            configuration={},
            send_live=ignore,
            emit=ignore,
            tool_observer=RemoteToolObserver(initial_state={}, facts={}),
        )
        with pytest.raises(RuntimeError, match="connection failed") as failure:
            await controller.start()
        assert TOKEN not in str(failure.value)
        assert controller.session is None
    assert reached == []
