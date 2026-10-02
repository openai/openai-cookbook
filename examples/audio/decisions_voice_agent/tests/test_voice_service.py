"""Synthetic events exercise real service/controller seams without provider calls."""

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agent import Choice

try:
    from aiohttp.test_utils import TestClient, TestServer
    from assistants.client.remote import RemoteClientDelegationController
    from assistants.errors import LiveResponseError
    from assistants.runtime import RemoteToolObserver

    from voice_service import (
        SUPPORT_LIMITS,
        SupersedingController,
        SyntheticSupportExecutor,
        create_support_app,
        support_backend,
    )
except ModuleNotFoundError as error:
    if error.name not in {"aiohttp", "assistants", "openai", "dotenv"}:
        raise
    pytest.skip(
        "Optional service dependencies require uv sync --extra live", allow_module_level=True
    )

TOKEN = "offline-support-test-token-0123456789abcdef"


def transcript(text="Where is my order?", identifier="utterance-1", event_id="input-1"):
    return {
        "type": "session.input_transcript.delta",
        "event_id": event_id,
        "item_id": identifier,
        "delta": text,
        "start_ms": 0,
        "end_ms": 1000,
    }


def delegation(identifier="request-1"):
    return {
        "type": "session.delegation.created",
        "delegation": {"id": identifier, "target": "client"},
    }


class Events(list):
    async def emit(self, event):
        self.append(event)


class Router:
    # This fixture has no external work or provider billing to reconcile.
    cancellation_safe = True

    def __init__(self, *, block=False, fail=False):
        self.block = block
        self.fail = fail
        self.requests = []
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()
        self.closed = False

    async def choose(self, request):
        self.requests.append(request)
        self.started.set()
        if self.fail:
            raise ConnectionError("Provider acceptance is unknown")
        if self.block:
            self.block = False
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled.set()
                raise
        return Choice.RETURN_POLICY if "policy" in request.transcript_srt else Choice.ORDER_STATUS

    async def close(self):
        self.closed = True


def controller_for(router, *, work_timeout=1):
    executor, sent, events = SyntheticSupportExecutor(), Events(), Events()

    async def execute(name, arguments, call_id):
        return executor.execute(name, arguments, call_id=call_id)

    controller = SupersedingController(
        backend=support_backend(router, execute),
        send_live=sent.emit,
        emit=events.emit,
        max_pending=1,
        max_delegations=2,
        work_timeout=work_timeout,
        cleanup_timeout=0.1,
    )
    return controller, executor, sent, events


async def test_real_service_dispatch_tool_and_correlated_commentary():
    routers = []

    def factory():
        router = Router()
        routers.append(router)
        return router

    app = create_support_app(factory, token=TOKEN)
    async with (
        TestClient(TestServer(app)) as client,
        client.ws_connect(
            "/ws/assistant",
            headers={"Authorization": f"Bearer {TOKEN}"},
        ) as socket,
    ):
        # Disallowed peer model/tool values cannot change the frozen factory.
        await socket.send_json({"type": "session.configure", "model": "ignored", "tools": []})
        assert await socket.receive_json(timeout=1) == {"type": "session.ready"}
        for event in [transcript(), delegation(), delegation()]:
            await socket.send_json({"type": "live.event", "event": event})
        events = []
        async with asyncio.timeout(2):
            while True:
                event = await socket.receive_json()
                events.append(event)
                if event.get("event", {}).get("type") == "client_delegation.completed":
                    break
        commentary = next(item["event"] for item in events if item["type"] == "live.send")
        assert commentary["delegation_id"] == "request-1"
        assert "Order DEMO-1001 has shipped" in commentary["content"]
        completed = next(
            item["event"]
            for item in events
            if item.get("event", {}).get("type") == "tool.completed"
        )
        assert completed["tool_execution"]["call_id"] == completed["call_id"]
        assert completed["application_state"]["completed_lookups"] == 1
    assert len(routers) == 1 and len(routers[0].requests) == 1
    assert routers[0].closed


async def test_new_transcript_cancels_old_work_and_preserves_history():
    router = Router(block=True)
    controller, executor, sent, events = controller_for(router)
    try:
        await controller.observe(transcript())
        await controller.observe(delegation())
        await router.started.wait()
        # Exact retransmission must neither cancel nor duplicate the old request.
        await controller.observe(transcript())
        await controller.observe(delegation())
        assert len(router.requests) == 1 and not router.cancelled.is_set()
        await controller.observe(transcript("Actually, what is the return policy?", "u2", "e2"))
        await controller.wait()
        assert router.cancelled.is_set() and not sent and not executor.executions
        await controller.observe(delegation("request-2"))
        await controller.wait()
        assert len(router.requests) == 2
        assert "Where is my order?" in router.requests[1].transcript_srt
        assert "Actually, what is the return policy?" in router.requests[1].transcript_srt
        assert sent[0]["delegation_id"] == "request-2"
        assert "30 days" in sent[0]["content"]
        assert any(item["type"] == "client_delegation.superseded" for item in events)
    finally:
        await controller.close()


async def test_cancellation_after_tool_observation_does_not_publish_stale_answer():
    router = Router()
    controller, executor, sent, events = controller_for(router)
    observed = asyncio.Event()
    original_emit = controller.emit

    async def pause_after_tool(event):
        await original_emit(event)
        if event["type"] == "tool.completed":
            observed.set()
            await asyncio.Event().wait()

    controller.emit = pause_after_tool
    try:
        await controller.observe(transcript())
        await controller.observe(delegation())
        await observed.wait()
        assert len(executor.executions) == 1
        await controller.observe(transcript("Actually, return policy", "u2", "e2"))
        await controller.wait()
        assert not sent
    finally:
        await controller.close()


async def test_unknown_provider_cancellation_stops_replacement_admission():
    router = Router(block=True)
    router.cancellation_safe = False
    controller, executor, sent, events = controller_for(router)
    try:
        await controller.observe(transcript())
        await controller.observe(delegation())
        await router.started.wait()
        with pytest.raises(RuntimeError, match="usage may be unknown"):
            await controller.observe(transcript("Actually, return policy", "u2", "e2"))
        with pytest.raises(LiveResponseError, match="usage may be unknown"):
            await controller.wait()
        with pytest.raises(RuntimeError, match="closed"):
            await controller.observe(delegation("request-2"))
        assert len(router.requests) == 1 and not executor.executions and not sent
        assert not any(event["type"] == "client_delegation.superseded" for event in events)
    finally:
        await controller.close()


async def test_interrupt_during_failure_publication_cannot_clear_admission_failure():
    router = Router(fail=True)
    router.cancellation_safe = False
    controller, _, sent, events = controller_for(router)
    failure_publishing = asyncio.Event()
    original_emit = controller.emit

    async def pause_on_failure(event):
        await original_emit(event)
        if event["type"] == "routing.failed":
            failure_publishing.set()
            await asyncio.Event().wait()

    controller.emit = pause_on_failure
    try:
        await controller.observe(transcript())
        await controller.observe(delegation())
        await failure_publishing.wait()
        with pytest.raises(RuntimeError, match="backend work failed"):
            await controller.observe(transcript("Actually, return policy", "u2", "e2"))
        with pytest.raises(LiveResponseError, match="backend work failed"):
            await controller.wait()
        with pytest.raises(RuntimeError, match="closed"):
            await controller.observe(delegation("request-2"))
        assert len(router.requests) == 1 and not sent
        assert not any(event["type"] == "client_delegation.superseded" for event in events)
    finally:
        await controller.close()


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_connections", 2),
        ("max_pending_delegations", 2),
        ("max_delegations", 3),
    ],
)
def test_service_rejects_relaxing_single_user_bounds(field, value):
    with pytest.raises(ValueError, match="one connection"):
        create_support_app(token=TOKEN, limits=replace(SUPPORT_LIMITS, **{field: value}))


async def test_backend_error_stops_admission_instead_of_returning_success():
    controller, executor, sent, events = controller_for(Router(fail=True))
    try:
        await controller.observe(transcript())
        await controller.observe(delegation())
        with pytest.raises(LiveResponseError):
            await controller.wait()
        with pytest.raises(LiveResponseError):
            await controller.observe(delegation("request-2"))
        assert not sent and not executor.executions
        assert any(event["type"] == "error" for event in events)
    finally:
        await controller.close()


async def test_deadline_and_close_wake_waiters():
    controller, _, sent, _ = controller_for(Router(block=True), work_timeout=0.01)
    await controller.observe(transcript())
    await controller.observe(delegation())
    with pytest.raises(LiveResponseError):
        await asyncio.wait_for(controller.wait(), 0.3)
    assert not sent
    await controller.close()

    router = Router(block=True)
    controller, _, sent, _ = controller_for(router)
    await controller.observe(transcript())
    await controller.observe(delegation())
    await router.started.wait()
    waiter = asyncio.create_task(controller.wait())
    await controller.close()
    with pytest.raises(LiveResponseError):
        await asyncio.wait_for(waiter, 0.3)
    assert router.closed and not sent


async def test_remote_bridge_settles_superseded_without_injecting_commentary():
    emitted = Events()
    remote = RemoteClientDelegationController(
        endpoint="ws://127.0.0.1/unused",
        configuration={},
        send_live=AsyncMock(),
        emit=emitted.emit,
        tool_observer=RemoteToolObserver({}, {}),
        token=TOKEN,
    )
    remote._seen.add("request-1")
    remote._work.begin("request-1")
    event = {"type": "client_delegation.superseded", "delegation_id": "request-1"}
    await remote._observe_assistant_event(event)
    await asyncio.wait_for(remote.wait(), 0.1)
    assert not remote.pending and emitted == [event]
    await remote._observe_assistant_event(event)
    assert len(emitted) == 1
    remote.send_live.assert_not_awaited()
    await remote.close()


async def test_session_is_finite_and_each_connection_gets_fresh_state():
    limits = replace(SUPPORT_LIMITS, session_timeout=0.03)
    app = create_support_app(token=TOKEN, limits=limits)
    async with (
        TestClient(TestServer(app)) as client,
        client.ws_connect(
            "/ws/assistant",
            headers={"Authorization": f"Bearer {TOKEN}"},
        ) as socket,
    ):
        await socket.send_json({"type": "session.configure"})
        assert (await socket.receive_json(timeout=1))["type"] == "session.ready"
        assert (await socket.receive_json(timeout=1))["error"]["code"] == "client_session_timeout"
    first, second = SyntheticSupportExecutor(), SyntheticSupportExecutor()
    first.execute("order_status", {"order_id": "DEMO-1001"}, call_id="one")
    assert first.snapshot()["completed_lookups"] == 1
    assert second.snapshot()["completed_lookups"] == 0


def test_executor_rejects_arbitrary_arguments_and_mutations():
    executor = SyntheticSupportExecutor()
    for name, arguments in [
        ("order_status", {"order_id": "OTHER"}),
        ("cancel_order", {}),
        ("return_policy", {"order_id": "DEMO-1001"}),
    ]:
        with pytest.raises(ValueError):
            executor.execute(name, arguments, call_id="forbidden")
    assert not executor.executions


def test_service_entry_point_defaults_and_loopback_binding(monkeypatch):
    from aiohttp import web

    import serve

    assert serve.parse_args([]).router == "scripted"
    with pytest.raises(SystemExit):
        serve.parse_args(["--port", "65536"])
    with pytest.raises(SystemExit):
        serve.parse_args(["--host", "0.0.0.0"])
    calls = []
    app = object()
    monkeypatch.setattr(serve, "create_local_app", lambda router: app)
    monkeypatch.setattr(web, "run_app", lambda value, **kwargs: calls.append((value, kwargs)))
    serve.main(["--port", "0"])
    assert calls == [(app, {"host": "127.0.0.1", "port": 0, "access_log": None})]


def test_service_entry_point_requires_separate_token_and_luna_key(monkeypatch):
    import serve

    monkeypatch.delenv("OPENAI_CLIENT_ASSISTANT_TOKEN", raising=False)
    with pytest.raises(ValueError, match="OPENAI_CLIENT_ASSISTANT_TOKEN"):
        serve.create_local_app()
    monkeypatch.setenv("OPENAI_CLIENT_ASSISTANT_TOKEN", TOKEN)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert serve.create_local_app() is not None  # Default offline mode needs no key.
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        serve.create_local_app("luna")


async def test_luna_service_factory_is_lazy_and_owns_client(monkeypatch):
    import openai
    from assistants.client.service import BACKEND_FACTORY

    import serve

    clients = []

    class Client:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.responses = SimpleNamespace(create=AsyncMock())
            self.close = AsyncMock()
            clients.append(self)

        def with_options(self, **kwargs):
            self.options = kwargs
            return self

    monkeypatch.setenv("OPENAI_CLIENT_ASSISTANT_TOKEN", TOKEN)
    monkeypatch.setenv("OPENAI_API_KEY", "fake-offline-test-key")
    monkeypatch.setattr(openai, "AsyncOpenAI", Client)
    app = serve.create_local_app("luna")
    assert not clients
    backend = app[BACKEND_FACTORY]({}, AsyncMock())
    assert len(clients) == 1
    assert clients[0].kwargs == {"max_retries": 0, "timeout": 5}
    assert clients[0].options == {"max_retries": 0, "timeout": 5.0}
    assert backend.agent.router.complete_history is True
    clients[0].responses.create.assert_not_awaited()
    await backend.close()
    clients[0].close.assert_awaited_once()
