"""F10 regression coverage for destinations, traces, private artifacts, and overload."""

from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import stat
import time
from pathlib import Path

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from assistants.client.security import validate_endpoint
from assistants.config import LiveAgentSettings
from assistants.frontend.assistant import LiveFrontend
from assistants.frontend.events import MAX_TERMINAL_BYTES, EventQueue, LimitedQueue
from assistants.frontend.security import MAX_LIVE_MESSAGE_BYTES, validate_live_endpoint
from assistants.frontend.transport import build_live_websocket_url, open_live_websocket
from run_harness.simulation.gpt_live_runner import DualGptLiveRunner
from shared.artifacts import create_run_directory
from shared.audio.conversation import ConversationRecorder
from shared.audio.pcm import write_mono_wav
from shared.metrics.interaction import write_ticks
from shared.observability.redaction import REDACTED, TraceRedactor
from shared.observability.trace import append_trace_events, record_event, sanitize_trace_value
from shared.private_files import private_directory, private_open, private_write_text
from shared.reporting.results import write_json


@pytest.mark.parametrize("validate", [validate_live_endpoint, validate_endpoint])
@pytest.mark.parametrize(
    "endpoint",
    [
        "http://example.com/live",
        "ws://example.com/live",
        "wss://u:p@example.com/live",
        "https://example.com/live?token=secret",
        "wss://example.com/live#secret",
        "file:///tmp/live",
        "http://localhost.example.com/live",
        "ws://127.0.0.1.example.com/live",
    ],
)
def test_unsafe_endpoints_are_rejected_even_with_local_opt_in(validate, endpoint: str) -> None:
    with pytest.raises(ValueError) as error:
        validate(endpoint, allow_insecure_loopback=True)
    assert "u:p" not in str(error.value)
    assert "token=secret" not in str(error.value)


@pytest.mark.parametrize("validate", [validate_live_endpoint, validate_endpoint])
@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "[::1]"])
def test_loopback_requires_explicit_opt_in(validate, host: str) -> None:
    endpoint = f"ws://{host}/live"
    with pytest.raises(ValueError):
        validate(endpoint, allow_insecure_loopback=False)
    validate(endpoint, allow_insecure_loopback=True)
    validate("wss://example.com/live", allow_insecure_loopback=False)


def test_live_url_omits_model_query() -> None:
    assert build_live_websocket_url("https://example.com/live", "a&b") == "wss://example.com/live"


@pytest.mark.parametrize("field", ["X-API-Key", "OPENAI_API_KEY", "OPENAI_RESPONSES_API_KEY", "session_token"])
def test_common_credential_header_and_setting_names_are_redacted(field: str) -> None:
    assert sanitize_trace_value({field: "opaque-value"}) == {field: REDACTED}


@pytest.mark.parametrize("frontend", [False, True])
async def test_both_live_paths_reject_redirects(monkeypatch: pytest.MonkeyPatch, frontend: bool) -> None:
    monkeypatch.setenv("OPENAI_LIVE_ALLOW_INSECURE_LOOPBACK", "true")
    reached = []

    async def redirect(_: web.Request) -> web.Response:
        raise web.HTTPFound("/target")

    async def target(_: web.Request) -> web.Response:
        reached.append(True)
        return web.Response()

    app = web.Application()
    app.router.add_get("/redirect", redirect)
    app.router.add_get("/target", target)
    async with TestClient(TestServer(app)) as client:
        endpoint = str(client.make_url("/redirect"))
        with pytest.raises(RuntimeError, match="redirects are not permitted"):
            if frontend:
                agent = LiveFrontend(
                    scenario=object(), settings=None, api_key="test-only", config=LiveAgentSettings(endpoint=endpoint)
                )
                await agent.start()
            else:
                async with open_live_websocket(endpoint=endpoint, model="test", api_key="test-only", timeout_seconds=1):
                    pytest.fail("Redirect reached a WebSocket")
    assert reached == []


async def test_live_message_limit_is_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_LIVE_ALLOW_INSECURE_LOOPBACK", "true")

    async def oversized(request: web.Request) -> web.WebSocketResponse:
        socket = web.WebSocketResponse()
        await socket.prepare(request)
        await socket.send_str("x" * (MAX_LIVE_MESSAGE_BYTES + 1))
        await socket.close()
        return socket

    app = web.Application()
    app.router.add_get("/live", oversized)
    async with (
        TestClient(TestServer(app)) as client,
        open_live_websocket(
            endpoint=str(client.make_url("/live")), model="test", api_key="test-only", timeout_seconds=1
        ) as connection,
    ):
        message = await connection.receive(timeout=2)
        assert message.type == aiohttp.WSMsgType.ERROR
        assert connection.close_code == aiohttp.WSCloseCode.MESSAGE_TOO_BIG


async def test_queue_count_overflow_preserves_order_and_one_terminal() -> None:
    queue = EventQueue(maxsize=2)
    first = {"type": "session.output_audio.delta", "delta": "one"}
    second = {"type": "turn.done"}
    await queue.put(first)
    await queue.put(second)
    await asyncio.wait_for(queue.put({"type": "late"}), 0.2)
    queue.finish(closing=True, code="", message="")
    await queue.put({"type": "later"})
    assert queue.qsize() == 3
    assert await queue.receive() == first
    assert await queue.receive() == second
    assert (await queue.receive())["error"]["code"] == "event_queue_overflow"
    assert queue.queued_bytes == 0
    with pytest.raises(EOFError):
        await queue.receive()


async def test_full_queue_can_finish_without_a_consumer() -> None:
    queue = EventQueue(maxsize=1)
    await queue.put({"type": "data"})
    queue.finish(closing=True, code="", message="")
    assert (await queue.receive())["type"] == "data"
    assert await queue.receive() == {"type": "session.closed", "_synthetic": True}


async def test_terminal_reserved_slot_is_also_size_limited() -> None:
    queue = EventQueue()
    await queue.put({"type": "error", "error": {"message": "x" * MAX_TERMINAL_BYTES}})
    assert (await queue.receive())["error"]["code"] == "event_queue_overflow"


async def test_queue_byte_limit_and_reclaimed_capacity() -> None:
    queue = LimitedQueue(maxsize=10, max_bytes=30)
    await queue.put({"x": "a" * 15})
    with pytest.raises(asyncio.QueueFull):
        await queue.put({"x": "b" * 15})
    await queue.get()
    assert queue.queued_bytes == 0
    await queue.put({"x": "b" * 15})
    events = EventQueue(max_bytes=30)
    await events.put({"type": "data", "payload": "x" * 31})
    assert (await events.receive())["error"]["code"] == "event_queue_overflow"


async def test_run_relay_overflow_is_attributed_to_the_participant() -> None:
    class Participant:
        async def incoming(self):
            yield {"type": "one"}
            yield {"type": "two"}

    runner = object.__new__(DualGptLiveRunner)
    runner.events = LimitedQueue(maxsize=1)
    runner.failure = None
    runner.started = time.monotonic()
    runner.input_ms = 0
    await runner._pump("assistant", Participant())
    assert runner.failure is not None
    assert runner.failure.failure_stage == "assistant_connection"
    assert "event_queue_overflow" in str(runner.failure)
    assert runner.events.qsize() == 1


async def test_normal_audio_burst_does_not_overflow() -> None:
    # Ten times the observed peak one-second event count, using its largest audio chunk.
    queue = EventQueue()
    event = {"type": "session.output_audio.delta", "delta": base64.b64encode(bytes(4800)).decode()}
    for _ in range(650):
        await queue.put(event)
    assert queue.terminal is None
    assert queue.qsize() == 650
    for _ in range(650):
        assert await queue.receive() == event
    assert queue.queued_bytes == 0


def test_nested_trace_redaction_preserves_metrics_and_delegation_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GPT_LIVE_EVALS_REDACT_FIELDS", "customer_email,phone_number")
    monkeypatch.setenv("OPENAI_API_KEY", "configured-key-value")
    payload = {
        "type": "response.done",
        "response": {
            "text": "Your table is booked.",
            "input_tokens": 42,
            "nested": [
                {
                    "Authorization": "Bearer hidden",
                    "api-key": "hidden-key",
                    "refresh_token": "refresh",
                    "password": "password-value",
                    "customerEmail": "private@example.com",
                }
            ],
            "arguments": json.dumps({"phone_number": "123456", "count": 2}),
            "error": "request failed with configured-key-value; token=opaque-value; Bearer another-value",
            "audio": "AAAA",
        },
    }
    result = sanitize_trace_value(payload)
    encoded = json.dumps(result)
    for secret in (
        "hidden",
        'refresh"',
        "password-value",
        "private@example.com",
        "123456",
        "configured-key-value",
        "opaque-value",
        "another-value",
    ):
        assert secret not in encoded
    assert result["response"]["input_tokens"] == 42
    assert result["response"]["text"] == "Your table is booked."
    assert json.loads(result["response"]["arguments"]) == {"phone_number": REDACTED, "count": 2}
    assert result["response"]["audio"] == "[base64 PCM; 4 characters]"
    assert payload["response"]["nested"][0]["password"] == "password-value"


def test_redacts_errors_before_truncating_and_keeps_session_context_private() -> None:
    redactor = TraceRedactor(fields=["account_id"], secrets=["opaque-secret"])
    value = sanitize_trace_value(
        {"error": "https://user:pass@example.com/?api_key=opaque-secret " + "x" * 900, "account_id": "customer-42"},
        redactor=redactor,
    )
    assert "opaque-secret" not in str(value)
    assert "user:pass" not in str(value)
    assert value["account_id"] == REDACTED
    stream = io.StringIO()
    record_event(
        stream,
        {"type": "session.commentary.append", "content": "private context"},
        started_at=time.monotonic(),
        event_index_state={"value": 0},
        source="test",
        direction="send",
    )
    assert "private context" not in stream.getvalue()


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission contract")
def test_artifact_writers_create_private_files_and_directories(tmp_path: Path) -> None:
    tmp_path.chmod(0o755)
    run = create_run_directory(tmp_path / "results", "run")
    write_json(run / "results.json", {"result": True})
    write_mono_wav(run / "audio" / "input.wav", bytes(480), 24000)
    ConversationRecorder(24000).save(run / "audio" / "conversation.wav", "private transcript")
    write_ticks(run / "debug" / "ticks.jsonl", [])
    private_write_text(run / "events" / "trace.jsonl", "")
    append_trace_events(run / "events" / "trace.jsonl", [{"type": "test"}])
    for path in (tmp_path / "results").rglob("*"):
        assert stat.S_IMODE(path.stat().st_mode) == (0o700 if path.is_dir() else 0o600), path
    assert stat.S_IMODE(tmp_path.stat().st_mode) == 0o755


@pytest.mark.skipif(os.name != "posix", reason="POSIX link/permission contract")
def test_private_writes_tighten_existing_file_and_refuse_links(tmp_path: Path) -> None:
    original = tmp_path / "existing"
    original.write_text("original")
    original.chmod(0o644)
    private_write_text(original, "new")
    assert stat.S_IMODE(original.stat().st_mode) == 0o600
    for name, make in (("symlink", lambda p: p.symlink_to(original)), ("hardlink", lambda p: os.link(original, p))):
        link = tmp_path / name
        make(link)
        with pytest.raises((OSError, ValueError)), private_open(link):
            pytest.fail("Opened linked output")
        assert original.read_text() == "new"
        link.unlink()
    private_directory(tmp_path / "nested" / "private")
    assert stat.S_IMODE((tmp_path / "nested").stat().st_mode) == 0o700
