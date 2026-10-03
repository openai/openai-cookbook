"""One fake Live socket and real local MCP; no model or external network calls."""

import asyncio
import base64
import hashlib
import io
import json
import math
import struct
import wave
from types import SimpleNamespace

import pytest

import wav_demo

try:
    import aiohttp
    from assistants.frontend import assistant as frontend
    from shared.observability import redaction
except ModuleNotFoundError as error:
    if error.name not in {"aiohttp", "assistants", "openai", "dotenv"}:
        raise
    pytest.skip(
        "Optional frontend dependencies require uv sync --extra live", allow_module_level=True
    )

from agent import Choice
from mcp_tools import (
    MCPExecutor,  # Import before a per-test capture stream can become an SDK default.
)


@pytest.fixture(autouse=True)
def no_environment_secrets(monkeypatch):
    # Tests do not enumerate/read the operator's credential environment.
    monkeypatch.setattr(redaction, "_environment_secrets", lambda: ())


def wav(path, *, channels=1, rate=24_000, width=2, frames=480):
    with wave.open(str(path), "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(width)
        output.setframerate(rate)
        output.writeframes(bytes(frames * channels * width))
    return path


@pytest.mark.parametrize(
    "kwargs",
    [
        {"channels": 2},
        {"rate": 16_000},
        {"width": 1},
        {"frames": 0},
        {"frames": 480_001},
    ],
)
def test_invalid_wav_rejected(tmp_path, kwargs):
    with pytest.raises(ValueError):
        wav_demo.read_input(wav(tmp_path / "input.wav", **kwargs))


def test_truncated_wav_rejected(tmp_path):
    path = wav(tmp_path / "input.wav")
    path.write_bytes(path.read_bytes()[:-2])
    with pytest.raises(ValueError, match="truncated"):
        wav_demo.read_input(path)


def test_check_does_not_read_credentials_construct_clients_or_create_output(
    tmp_path, monkeypatch, capfd
):
    from assistants import config

    def forbidden(*args, **kwargs):
        pytest.fail("Offline check touched a credential/client/dotenv boundary")

    monkeypatch.setattr(config, "load_environment", forbidden)
    monkeypatch.setattr(wav_demo, "owned_router", forbidden)
    monkeypatch.setattr(wav_demo.os, "environ", {})
    output = tmp_path / "new"
    assert (
        wav_demo.main(["--input", str(wav(tmp_path / "input.wav")), "--output-dir", str(output)])
        == 0
    )
    assert json.loads(capfd.readouterr().out)["status"] == "checked"
    assert not output.exists()


def test_existing_output_rejected_before_provider_setup(tmp_path, monkeypatch):
    monkeypatch.setattr(wav_demo, "owned_router", lambda *args: pytest.fail("Provider constructed"))
    with pytest.raises(ValueError, match="already exist"):
        wav_demo.plan(wav(tmp_path / "input.wav"), tmp_path)


def test_audio_and_trace_byte_limits(monkeypatch):
    capture = wav_demo.Capture(io.StringIO())
    monkeypatch.setattr(wav_demo, "MAX_OUTPUT_BYTES", 4)
    with pytest.raises(ValueError, match="oversized"):
        capture.observe(
            {"type": "session.output_audio.delta", "delta": base64.b64encode(b"123456").decode()},
            "server_to_client",
        )
    assert capture.audio == b""
    monkeypatch.setattr(wav_demo, "MAX_TRACE_BYTES", 3)
    with pytest.raises(ValueError, match="Trace byte"):
        capture.write("four")


class Socket:
    def __init__(self):
        self.messages = asyncio.Queue()
        self.sent = []
        self.closed = False
        self.delegated = False
        self.reply_task = None

    def __aiter__(self):
        return self

    async def __anext__(self):
        event = await self.messages.get()
        if event is None:
            raise StopAsyncIteration
        return SimpleNamespace(type=aiohttp.WSMsgType.TEXT, data=json.dumps(event))

    async def send_json(self, event):
        self.sent.append(event)
        if event["type"] == "session.start":
            await self.messages.put(
                {"type": "session.started", "session": {"id": "offline", "model": "gpt-live-1"}}
            )
        elif event["type"] == "session.input_audio.append" and not self.delegated:
            self.delegated = True
            await self.messages.put(
                {
                    "type": "session.input_transcript.delta",
                    "item_id": "input-1",
                    "event_id": "transcript-1",
                    "delta": "Where is my order?",
                    "start_ms": 0,
                    "end_ms": 20,
                }
            )
            delegation = {
                "type": "session.delegation.created",
                "delegation": {"id": "one", "target": "client"},
            }
            await self.messages.put(delegation)
            await self.messages.put(
                delegation
            )  # Duplicate transport event must not repeat paid work.
        elif event["type"] == "session.commentary.append":

            async def reply():
                await asyncio.sleep(0.05)  # Publication precedes the spoken continuation.
                await self.messages.put(
                    {
                        "type": "session.commentary.appended",
                        "event_id": "ack-1",
                        "client_event_id": event["event_id"],
                        "delegation_id": "one",
                    }
                )
                await self.messages.put(
                    {
                        "type": "session.output_transcript.delta",
                        "item_id": "answer",
                        "delta": event["content"],
                        "start_ms": 100,
                        "end_ms": 200,
                    }
                )
                pcm = b"".join(
                    struct.pack("<h", round(2000 * math.sin(i * 0.1))) for i in range(2400)
                )
                await self.messages.put(
                    {"type": "session.output_audio.delta", "delta": base64.b64encode(pcm).decode()}
                )

            self.reply_task = asyncio.create_task(reply())
        elif event["type"] == "session.close":
            await self.messages.put(
                {
                    "type": "session.closed",
                    "session": {"id": "offline", "model": "gpt-live-1"},
                    "usage": {"seconds": 1.25},
                    "reason": "close_requested",
                }
            )

    async def close(self):
        if self.reply_task is not None:
            await self.reply_task
        self.closed = True
        await self.messages.put(None)

    def exception(self):
        return None


class Session:
    def __init__(self, socket):
        self.socket = socket
        self.closed = False
        self.connector = SimpleNamespace(closed=False)
        self._retry_connection = True
        self.connects = 0

    async def ws_connect(self, *args, **kwargs):
        assert self._retry_connection is False
        self.connects += 1
        return self.socket

    async def close(self):
        self.closed = True
        self.connector.closed = True


class Router:
    cancellation_safe = True

    def __init__(self, receipt):
        self.receipt = receipt
        self.requests = []
        self.closed = False

    async def choose(self, request):
        self.requests.append(request)
        self.receipt.dispatch()
        self.receipt.response(
            SimpleNamespace(
                id="fixture-response",
                model="gpt-6-luna",
                status="completed",
                usage=SimpleNamespace(input_tokens=100, output_tokens=5),
            )
        )
        return Choice.ORDER_STATUS

    async def close(self):
        self.closed = True


class CaptionMismatchSocket(Socket):
    """Caption coordinates differ from the locally observed PCM episode count."""

    def __init__(self, *, final_usage=1.25, malformed_audio=False):
        super().__init__()
        self.final_usage = final_usage
        self.malformed_audio = malformed_audio
        speech = (1000).to_bytes(2, "little", signed=True) * (24 * 400)
        self.pcm = speech + bytes(24 * 600 * 2) + speech

    async def send_json(self, event):
        if event["type"] == "session.commentary.append":
            self.sent.append(event)

            async def reply():
                await asyncio.sleep(0.05)
                for index, text in enumerate(
                    ["Order DEMO-1001 ", "has shipped. ", "Its estimated delivery is Friday."]
                ):
                    await self.messages.put(
                        {
                            "type": "session.output_transcript.delta",
                            "event_id": f"caption-{index}",
                            "start_ms": 50_000 + index * 2000,
                            "end_ms": 50_100 + index * 2000,
                            "delta": text,
                        }
                    )
                await self.messages.put(
                    {
                        "type": "session.output_audio.delta",
                        "delta": (
                            "invalid!"
                            if self.malformed_audio
                            else base64.b64encode(self.pcm).decode()
                        ),
                    }
                )

            self.reply_task = asyncio.create_task(reply())
        elif event["type"] == "session.close":
            self.sent.append(event)
            await self.messages.put(
                {
                    "type": "session.closed",
                    "session": {"id": "offline", "model": "gpt-live-1"},
                    "usage": {"seconds": self.final_usage},
                    "reason": "close_requested",
                }
            )
        else:
            await super().send_json(event)


@pytest.mark.parametrize("final_usage", [1.25, None])
async def test_wav_retains_nonzero_audio_received_during_finalization(
    tmp_path, monkeypatch, final_usage
):
    from shared.single_turn import runtime

    class LateAudioSocket(CaptionMismatchSocket):
        tail = (1000).to_bytes(2, "little", signed=True) * 2400

        async def send_json(self, event):
            if event["type"] == "session.close":
                # These bytes arrive strictly after the real collector returns.
                assert collected_audio
                for index in range(2):
                    await asyncio.sleep(0.02)
                    await self.messages.put(
                        {
                            "type": "session.output_audio.delta",
                            "event_id": f"late-audio-{index}",
                            "delta": base64.b64encode(self.tail).decode(),
                        }
                    )
            await super().send_json(event)

    socket = LateAudioSocket(final_usage=final_usage)
    session = Session(socket)
    collected_audio = []
    collect = runtime.collect_live_response

    async def record_collector_result(*args, **kwargs):
        result = await collect(*args, **kwargs)
        collected_audio.append(result["output_audio_bytes"])
        return result

    monkeypatch.setattr(frontend.aiohttp, "ClientSession", lambda **kwargs: session)
    monkeypatch.setattr(frontend, "configured_proxy", lambda url: None)
    monkeypatch.setattr(runtime, "collect_live_response", record_collector_result)
    monkeypatch.setattr(wav_demo, "WORK_SECONDS", 5)
    output = tmp_path / "result"
    result = await wav_demo.run_once(
        bytes(960), output, "offline-not-a-key", router_factory=lambda key, receipt: Router(receipt)
    )

    assert collected_audio == [socket.pcm]
    expected = socket.pcm + socket.tail * 2
    with wave.open(str(output / "output.wav")) as saved:
        assert saved.readframes(saved.getnframes()) == expected
    assert result["output_audio_bytes"] == len(expected)
    assert result["output_pcm_sha256"] == hashlib.sha256(expected).hexdigest()
    assert json.loads((output / "result.json").read_text()) == result
    assert result["cleanup"]["transport_closed"] and session.closed
    assert result["status"] == ("completed" if final_usage is not None else "unknown")
    assert result["live"]["usage_known"] is (final_usage is not None)


@pytest.mark.parametrize("final_usage", [1.25, None, True])
async def test_unaligned_captions_drain_real_collector_without_fabricating_finalization(
    tmp_path, monkeypatch, final_usage
):
    socket = CaptionMismatchSocket(final_usage=final_usage)
    session = Session(socket)
    monkeypatch.setattr(frontend.aiohttp, "ClientSession", lambda **kwargs: session)
    monkeypatch.setattr(frontend, "configured_proxy", lambda url: None)
    monkeypatch.setattr(wav_demo, "WORK_SECONDS", 5)
    routers = []

    def router_factory(key, receipt):
        router = Router(receipt)
        routers.append(router)
        return router

    output = tmp_path / "result"
    result = await wav_demo.run_once(
        bytes(960), output, "offline-not-a-key", router_factory=router_factory
    )
    assert result["response_completion"] == {
        "basis": "returned_audio_with_unaligned_captions",
        "projection_complete": False,
        "projected_turns": [],
    }
    assert result["assistant_text"] == (
        "Order DEMO-1001 has shipped. Its estimated delivery is Friday."
    )
    assert result["raw_assistant_text"] == result["assistant_text"]
    assert len(routers[0].requests) == len(result["tool_executions"]) == session.connects == 1
    assert result["tool_executions"][0]["mcp"]["transport_closed"]
    assert session.closed and routers[0].closed
    assert len([event for event in socket.sent if event["type"] == "session.close"]) == 1
    assert (
        len([event for event in socket.sent if event["type"] == "session.commentary.append"]) == 1
    )
    with wave.open(str(output / "output.wav")) as saved:
        assert saved.readframes(saved.getnframes()) == socket.pcm
    assert result["output_audio_bytes"] == len(socket.pcm)
    assert result["route"]["usage_known"]
    if type(final_usage) is float:
        assert result["status"] == "completed" and result["live"]["usage_known"]
        assert result["errors"] == []
    else:
        assert result["status"] == "unknown" and not result["live"]["usage_known"]
        assert any(error["stage"] == "finalization" for error in result["cleanup"]["errors"])
    persisted = json.loads((output / "result.json").read_text())
    assert persisted["response_completion"] == result["response_completion"]


async def test_malformed_reply_audio_cannot_use_operational_completion(tmp_path, monkeypatch):
    socket = CaptionMismatchSocket(malformed_audio=True)
    session = Session(socket)
    monkeypatch.setattr(frontend.aiohttp, "ClientSession", lambda **kwargs: session)
    monkeypatch.setattr(frontend, "configured_proxy", lambda url: None)
    monkeypatch.setattr(wav_demo, "WORK_SECONDS", 5)
    result = await wav_demo.run_once(
        bytes(960),
        tmp_path / "result",
        "offline-not-a-key",
        router_factory=lambda key, receipt: Router(receipt),
    )
    assert result["status"] == "failed"
    assert result["response_completion"]["basis"] is None
    assert result["live"]["usage_known"] and result["cleanup"]["transport_closed"]
    assert "NoCompletedResponse" in result["errors"]
    assert len(result["tool_executions"]) == 1


async def test_supplied_audio_delegates_once_through_real_mcp_and_returns_wav(
    tmp_path, monkeypatch
):
    socket = Socket()
    session = Session(socket)
    monkeypatch.setattr(frontend.aiohttp, "ClientSession", lambda **kwargs: session)
    monkeypatch.setattr(frontend, "configured_proxy", lambda url: None)
    routers = []

    def router_factory(key, receipt):
        router = Router(receipt)
        routers.append(router)
        return router

    output = tmp_path / "result"
    result = await wav_demo.run_once(
        bytes(960),
        output,
        "offline-not-a-key",
        router_factory=router_factory,
        executor_factory=MCPExecutor,
    )
    assert result["status"] == "completed", result
    assert session.connects == 1 and session.closed and routers[0].closed
    assert len(routers[0].requests) == 1
    calls = result["tool_executions"]
    assert len(calls) == 1 and calls[0]["arguments"] == {"order_id": "DEMO-1001"}
    assert calls[0]["mcp"]["transport"] == "stdio" and calls[0]["mcp"]["transport_closed"]
    assert (
        len([event for event in socket.sent if event["type"] == "session.commentary.append"]) == 1
    )
    assert result["live"]["usage_known"] and result["route"]["usage_known"]
    with wave.open(str(output / "output.wav")) as audio:
        assert audio.getframerate() == 24_000 and audio.getnframes() > 0
    events = (output / "events.jsonl").read_text()
    assert '"routing.completed"' in events and '"tool.completed"' in events
    assert "offline-not-a-key" not in events
    assert json.loads((output / "result.json").read_text())["device_playback_verified"] is False


def test_route_usage_retained_independently_of_decode_status():
    receipt = wav_demo.RouteReceipt()
    receipt.dispatch()
    receipt.response(
        SimpleNamespace(
            id="refused",
            model="gpt-6-luna",
            status="failed",
            usage=SimpleNamespace(input_tokens=50, output_tokens=2),
        )
    )
    assert receipt.data["usage_known"] and receipt.data["status"] == "failed"
    with pytest.raises(RuntimeError, match="already attempted"):
        receipt.dispatch()


async def test_known_frontend_audio_without_backend_request_is_failed(tmp_path, monkeypatch):
    from shared.single_turn import runtime

    socket = Socket()
    socket.delegated = True  # This model never asks its backend.
    session = Session(socket)
    monkeypatch.setattr(frontend.aiohttp, "ClientSession", lambda **kwargs: session)
    monkeypatch.setattr(frontend, "configured_proxy", lambda url: None)

    async def frontend_only(connection, capture, **kwargs):
        capture.observe(
            {"type": "session.output_audio.delta", "delta": "AAAAAA=="}, "server_to_client"
        )
        return {"assistant_text": "An unverified frontend-only answer"}

    monkeypatch.setattr(runtime, "collect_live_response", frontend_only)
    result = await wav_demo.run_once(
        bytes(960),
        tmp_path / "result",
        "offline-not-a-key",
        router_factory=lambda key, receipt: Router(receipt),
    )
    assert result["status"] == "failed"
    assert result["live"]["usage_known"] and result["output_audio_bytes"] > 0
    assert "MissingDelegation" in result["errors"] and not result["route"]["attempted"]


async def test_assistant_construction_failure_closes_prior_owners_and_redacts(tmp_path):
    router = Router(wav_demo.RouteReceipt())

    def broken_assistant(**kwargs):
        raise ValueError("proxy https://sensitive-user:private-password@example.test")

    output = tmp_path / "result"
    result = await wav_demo.run_once(
        bytes(960),
        output,
        "offline-not-a-key",
        router_factory=lambda key, receipt: router,
        assistant_factory=broken_assistant,
    )
    assert router.closed and result["status"] == "failed"
    assert "private-password" not in (output / "result.json").read_text()
    assert result["errors"][0] == "ValueError"


def test_cli_setup_error_never_prints_proxy_credentials(tmp_path, monkeypatch, capfd):
    monkeypatch.setattr(wav_demo, "plan", lambda *args: (bytes(960), {}))
    monkeypatch.setattr(wav_demo.os, "environ", {"OPENAI_API_KEY": "offline-not-a-key"})

    async def failed(*args):
        raise ValueError("proxy https://sensitive-user:private-password@example.test")

    monkeypatch.setattr(wav_demo, "run_once", failed)
    assert (
        wav_demo.main(["--input", "unused.wav", "--output-dir", str(tmp_path / "new"), "--run"])
        == 2
    )
    output = capfd.readouterr()
    assert (
        "ValueError" in output.err
        and "private-password" not in output.err
        and "sensitive-user" not in output.err
    )


async def test_close_invalidates_router_that_returns_after_cancellation():
    from voice_service import SupersedingController, SupportBackend

    started = asyncio.Event()
    calls, sent, emitted = [], [], []

    class LateRouter:
        async def choose(self, request):
            started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                return Choice.ORDER_STATUS

    async def execute(*args):
        calls.append(args)
        return {"ok": True, "answer": "Must not execute"}

    async def send(event):
        sent.append(event)

    async def emit(event):
        emitted.append(event)

    controller = SupersedingController(
        backend=SupportBackend(LateRouter(), execute),
        send_live=send,
        emit=emit,
        max_pending=1,
        max_delegations=1,
        work_timeout=1,
    )
    await controller.observe(
        {
            "type": "session.input_transcript.delta",
            "delta": "Where is my order?",
            "item_id": "user",
            "start_ms": 0,
            "end_ms": 20,
        }
    )
    await controller.observe(
        {"type": "session.delegation.created", "delegation": {"id": "one", "target": "client"}}
    )
    await started.wait()
    await controller.close()
    assert not calls and not sent
    assert not any(
        event["type"] in {"routing.completed", "tool.called", "client_delegation.completed"}
        for event in emitted
    )
