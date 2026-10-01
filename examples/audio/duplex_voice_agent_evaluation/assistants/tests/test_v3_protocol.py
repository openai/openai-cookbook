"""V3 wire boundaries, atomic tool batches, and real finalization."""

from __future__ import annotations

import asyncio
import io
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from assistants.client.memory import TranscriptLedger
from assistants.config import LiveAgentSettings, build_assistant_session
from assistants.errors import LiveResponseError
from assistants.frontend.transport import (
    build_context_append,
    build_live_headers,
    build_live_websocket_url,
    unwrap_response_event,
)
from assistants.responses.delegation import ResponsesDelegationController
from shared.metrics.tokens import TokenUsage
from shared.observability.trace import record_event
from shared.single_turn.runtime import close_live_session, wait_for_session_started


@pytest.mark.parametrize("mode", ["responses", "client"])
@pytest.mark.parametrize("model", ["gpt-live-1", "custom-live-model"])
def test_startup_uses_native_fields_and_preserves_overrides(mode, model):
    config = LiveAgentSettings(assistant_mode=mode, model=model, voice="voice_custom", backend_model="backend-custom")
    event = build_assistant_session(config, instructions="Exact prompt", backend_instructions="Exact backend", tools=[])
    assert event["type"] == "session.start"
    assert event["session"]["model"] == model
    assert event["session"]["audio"] == {
        "format": {"type": "audio/pcm", "rate": 24000},
        "output": {"voice": {"id": "voice_custom"}},
    }
    assert event["session"]["instructions"] == "Exact prompt"
    assert "initial_items" not in event["session"]
    assert build_live_headers("test") == {"Authorization": "Bearer test"}
    assert (
        build_live_websocket_url("https://api.openai.com/v1/live/sessions", model)
        == "wss://api.openai.com/v1/live/sessions"
    )
    with pytest.raises(ValueError, match="/v1/live/sessions"):
        build_live_websocket_url("https://api.openai.com/v1/live", model)


@pytest.mark.parametrize("intent", ["commentary", "thinking", "instructions"])
@pytest.mark.parametrize("owner", [None, "delegation-1"])
def test_context_commands_and_acknowledgments_retain_distinct_ids(intent, owner):
    command = build_context_append("  Exact text ✓\n", kind=intent, delegation_id=owner)
    assert command["type"] == f"session.{intent}.append"
    assert command["content"] == "  Exact text ✓\n"
    assert command["delegation_id"] == owner
    ack = {
        "type": f"session.{intent}.appended",
        "event_id": "server-1",
        "client_event_id": command["event_id"],
        "start_ms": 0,
        "end_ms": 200,
    }
    error = {"type": "error", "error": {"client_event_id": command["event_id"], "message": "rejected"}}
    log = io.StringIO()
    for event in [command, ack, error]:
        record_event(
            log, event, started_at=time.monotonic(), event_index_state={"value": 0}, source="test", direction="test"
        )
    records = [json.loads(line)["event"] for line in log.getvalue().splitlines()]
    assert records[0]["event_id"] == records[1]["client_event_id"] == records[2]["error"]["client_event_id"]
    assert "Exact text" not in log.getvalue()
    assert records[1]["event_id"] != records[1]["client_event_id"]


def test_wrapped_events_preserve_wire_evidence_and_nullable_ownership():
    inner = {"type": "response.completed", "response": {"id": "r", "output": [], "usage": {"input_tokens": 2}}}
    for owner in [None, "d"]:
        raw = {"type": "response.event", "event_id": "outer", "delegation_id": owner, "event": inner}
        observed = unwrap_response_event(raw)
        assert observed["response"]["output"] == []
        assert observed["delegation_id"] == owner
        assert observed["_raw_live_event"] is raw
    assert unwrap_response_event({"type": "response.event", "event": inner})["delegation_id"] is None
    application = {"type": "response.created", "_client_managed": True}
    assert unwrap_response_event(application) is application


class Executor:
    def __init__(self):
        self.gates = {key: asyncio.Event() for key in ["a", "b", "c"]}
        self.calls = []
        self.executions = []

    async def execute(self, name, arguments, *, call_id):
        self.calls.append(call_id)
        await self.gates[call_id].wait()
        return {"call_id": call_id}

    def snapshot(self):
        return {}


def call(response_id, call_id, owner=None):
    return {
        "type": "response.output_item.done",
        "response_id": response_id,
        "delegation_id": owner,
        "item": {
            "id": "item-" + call_id,
            "type": "function_call",
            "status": "completed",
            "call_id": call_id,
            "name": "lookup",
            "arguments": "{}",
        },
    }


def created(response_id, owner=None, previous=None):
    return {
        "type": "response.created",
        "delegation_id": owner,
        "response": {"id": response_id, "previous_response_id": previous},
    }


def completed(response_id):
    return {"type": "response.completed", "response": {"id": response_id, "output": []}}


async def test_complete_tool_inventory_and_all_results_precede_one_continuation():
    executor = Executor()
    sent = []

    async def send(event):
        sent.append(event)

    controller = ResponsesDelegationController(executor=executor, send_live=send, emit=AsyncMock())
    try:
        await controller.observe(created("r", "d"))
        await controller.observe(call("r", "a", "d"))
        await controller.observe(call("r", "b", "d"))
        executor.gates["b"].set()
        await asyncio.sleep(0)
        assert sent == []
        await controller.observe(completed("r"))
        assert sent == [] and controller.pending
        executor.gates["a"].set()
        await controller.runtime.wait()
        assert [event["type"] for event in sent] == ["response.item.create", "response.item.create", "response.create"]
        assert [event["item"]["call_id"] for event in sent[:-1]] == ["a", "b"]
        assert set(sent[-1]) == {"type", "event_id"}
        await controller.observe(call("r", "a", "d"))
        await controller.observe(completed("r"))
        assert len(sent) == 3 and controller.pending
        await controller.observe(created("r", "d"))
        assert controller.pending
        await controller.observe(created("followup", "d"))
        await controller.observe(completed("followup"))
        await controller.wait()
        assert not controller.pending and executor.calls == ["a", "b"]
    finally:
        await controller.close()


async def test_overlapping_batches_are_serialized_and_ambiguous_items_are_unresolved():
    executor = Executor()
    sent = []
    publishing = asyncio.Event()
    release = asyncio.Event()

    async def send(event):
        sent.append(event)
        if len(sent) == 1:
            publishing.set()
            await release.wait()

    controller = ResponsesDelegationController(executor=executor, send_live=send, emit=AsyncMock())
    try:
        for rid, cid in [("one", "a"), ("two", "b")]:
            await controller.observe(created(rid, rid))
            await controller.observe(call(rid, cid, rid))
        with pytest.raises(ValueError, match="correlate"):
            await controller.observe(
                {"type": "response.output_item.added", "item": {"id": "unknown", "type": "function_call"}}
            )
        executor.gates["a"].set()
        executor.gates["b"].set()
        await controller.runtime.wait()
        first = asyncio.create_task(controller.observe(completed("one")))
        await publishing.wait()
        second = asyncio.create_task(controller.observe(completed("two")))
        await asyncio.sleep(0)
        assert len(sent) == 1
        release.set()
        await asyncio.gather(first, second)
        assert [e["type"] for e in sent] == ["response.item.create", "response.create"] * 2
        await controller.observe(created("ambiguous"))
        assert controller._work.contains("one") and controller._work.contains("two")
        for rid in ["one", "two"]:
            await controller.observe(created(rid + "-next", previous=rid))
            await controller.observe(completed(rid + "-next"))
        await controller.observe(completed("ambiguous"))
        await controller.wait()
    finally:
        release.set()
        await controller.close()


@pytest.mark.parametrize("kind", ["response.failed", "response.incomplete", "error"])
async def test_backend_failure_and_command_rejection_cannot_become_completion(kind):
    controller = ResponsesDelegationController(executor=Executor(), send_live=AsyncMock(), emit=AsyncMock())
    await controller.observe(created("r"))
    await controller.observe({"type": kind, "response": {"id": "r"}, "error": {"client_event_id": "continue_r"}})
    with pytest.raises(LiveResponseError):
        await controller.wait()
    assert not controller.pending
    await controller.close()


def test_metadata_only_client_handoff_preserves_partial_words_corrections_and_identity():
    ledger = TranscriptLedger()
    ledger.add_history([{"role": "user", "content": [{"text": "Under Maya."}]}])
    for identifier, text, start in [
        ("1", "Fri", 0),
        ("2", "day", 200),
        ("3", " no", 400),
        ("4", " no", 400),
        ("5", ", Saturday.", 600),
    ]:
        event = {
            "type": "session.input_transcript.delta",
            "event_id": identifier,
            "start_ms": start,
            "end_ms": start + 200,
            "delta": text,
        }
        ledger.record_event(event)
        ledger.record_event(event)
    handoff = ledger.consume_srt()
    assert "Under Maya." in handoff and "Friday no no, Saturday." in handoff
    assert ledger.consume_srt() == ""


@pytest.mark.parametrize("event", [{"type": "session.updated"}, {"type": "error", "error": {"message": "bad"}}, None])
async def test_startup_rejects_nonready_events(event):
    connection = SimpleNamespace(receive_json=AsyncMock(return_value=event))
    with pytest.raises(LiveResponseError):
        await wait_for_session_started(
            connection, io.StringIO(), timeout_seconds=0.1, started_at=time.monotonic(), event_index_state={"value": 0}
        )


@pytest.mark.parametrize(
    "event",
    [
        {"type": "session.closed", "_synthetic": True, "usage": {"seconds": 1}},
        {"type": "session.closed"},
        {"type": "session.closed", "usage": {"audio_duration_ms": 1000}},
    ],
)
async def test_synthetic_or_missing_final_usage_is_a_shutdown_failure(event):
    connection = SimpleNamespace(send_json=AsyncMock(), receive_json=AsyncMock(return_value=event))
    with pytest.raises(LiveResponseError, match="usage"):
        await close_live_session(
            connection, io.StringIO(), trace_started_at=time.monotonic(), event_index_state={"value": 0}
        )


async def test_real_finalization_reports_cumulative_duration_without_frontend_tokens():
    connection = SimpleNamespace(
        send_json=AsyncMock(),
        receive_json=AsyncMock(return_value={"type": "session.closed", "usage": {"seconds": 2.25}}),
    )
    usage = await close_live_session(
        connection, io.StringIO(), trace_started_at=time.monotonic(), event_index_state={"value": 0}
    )
    parsed = TokenUsage.from_mapping(usage)
    assert parsed.audio_duration_ms == 2250
    assert parsed.total_tokens is None and parsed.input_tokens is None


async def test_rejected_continuation_is_retained_without_republishing_outputs():
    executor = Executor()
    sent = []

    async def reject(event):
        sent.append(event)
        if event["type"] == "response.create":
            raise ConnectionError("continuation rejected")

    controller = ResponsesDelegationController(executor=executor, send_live=reject, emit=AsyncMock())
    try:
        await controller.observe(created("r"))
        await controller.observe(call("r", "a"))
        executor.gates["a"].set()
        await controller.runtime.wait()
        with pytest.raises(ConnectionError):
            await controller.observe(completed("r"))
        with pytest.raises(LiveResponseError):
            await controller.wait()
        with pytest.raises(RuntimeError):
            await controller.observe(completed("r"))
        assert [event["type"] for event in sent] == ["response.item.create", "response.create"]
        assert not controller.pending
    finally:
        await controller.close()
