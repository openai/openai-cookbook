"""MVP regression coverage for assistant, transport, artifacts, and audio."""

from __future__ import annotations

import ast
import asyncio
import base64
import io
import json
import sys
import threading
import time
import wave
from array import array
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from assistants.config import LiveAgentSettings, build_assistant_session, build_initial_items
from assistants.frontend.transport import normalize_live_response_tools
from assistants.responses.delegation import bind_responses_delegation
from assistants.runtime import AsyncToolRuntime
from crawl_harness import evaluate as crawl_runner
from crawl_harness.evaluate import (
    DEFAULT_BACKEND_SYSTEM_PROMPT_PATH,
    DEFAULT_DATA_JSON,
    DEFAULT_SYSTEM_PROMPT_PATH,
    DEFAULT_TOOLS_PATH,
    load_dataset,
    load_system_prompt,
    load_tools,
    parse_args,
    run_evals,
)
from shared.audio import conversation as conversation_audio
from shared.audio.conversation import ConversationRecorder
from shared.audio.pacing import AudioPacer
from shared.audio.pcm import AudioQueue, chunk_pcm, read_mono_wav, speech_intervals_pcm16, write_mono_wav
from shared.grading.scoring import unique_tool_invocations
from shared.metrics.interaction import (
    build_ticks,
    compute_interaction_metrics,
    compute_turn_interaction_metrics,
    extract_interaction_events,
)
from shared.metrics.latency import first_speech_offset_ms
from shared.metrics.tokens import TokenUsage, aggregate_backend_usage
from shared.observability.timeline import AgentEvent, Timeline, Turn, project_agent_event
from shared.observability.trace import record_event
from shared.reporting.results import build_results_report, build_timestamped_run_name, write_json
from shared.scenarios import ConversationHistoryItem
from shared.single_turn import runtime as single_turn_runtime
from shared.single_turn.runtime import CallerAudioCompletion, collect_live_response, stream_audio_to_connection

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class SlowApplicationTools:
    """Blocking customer tool used to verify continuous event processing."""

    def __init__(self) -> None:
        self.executions: list[dict[str, object]] = []
        self.started = threading.Event()
        self.completed = threading.Event()

    def execute(self, name: str, arguments: dict[str, object], *, call_id: str) -> dict[str, object]:
        self.started.set()
        time.sleep(0.2)
        output = {"ok": True, "available": True}
        self.executions.append(
            {"name": name, "arguments": arguments, "call_id": call_id, "status": "completed", "output": output}
        )
        self.completed.set()
        return output

    def snapshot(self) -> dict[str, object]:
        return {}


class ToolStreamingConnection:
    """Keep projecting audio during a deliberately slow application callback."""

    def __init__(self, executor: SlowApplicationTools, *, unfinished_status: str | None = None) -> None:
        self.executor = executor
        self.events: asyncio.Queue[dict[str, object]] = asyncio.Queue()
        self.sent: list[dict[str, object]] = []
        self.audio_received_while_tool_pending = False
        self.tool_started_before_completed_item = False
        speech = (1_000).to_bytes(2, "little", signed=True) * 480
        events = [
            {"type": "response.created", "response": {"id": "response-1"}},
            {
                "type": "response.function_call_arguments.done",
                "item_id": "item-1",
                "response_id": "response-1",
                "arguments": '{"date":"2026-08-08","time":"19:00","party_size":2}',
            },
            {
                "type": "response.output_item.done",
                "response_id": "response-1",
                "item": {
                    "id": "item-1",
                    "type": "function_call",
                    "status": "completed",
                    "name": "check_availability",
                    "call_id": "call-1",
                    "arguments": '{"date":"2026-08-08","time":"19:00","party_size":2}',
                },
            },
            {
                "type": "session.output_audio.delta",
                "start_ms": 0,
                "end_ms": 20,
                "delta": base64.b64encode(speech).decode("ascii"),
            },
            {"type": "session.output_transcript.delta", "start_ms": 0, "end_ms": 20, "delta": "Checking. "},
        ]
        events.append({"type": "response.completed", "response": {"id": "response-1", "output": []}})
        unfinished_item = dict(events[2])
        unfinished_item["item"] = dict(events[2]["item"])
        if unfinished_status is None:
            unfinished_item["item"].pop("status")
        else:
            unfinished_item["item"]["status"] = unfinished_status
        events.insert(2, unfinished_item)
        for event in events:
            self.events.put_nowait(event)

    async def send_json(self, event: dict[str, object]) -> None:
        self.sent.append(event)
        if event.get("type") != "response.create":
            return
        for response in (
            {"type": "response.created", "response": {"id": "response-2", "previous_response_id": "response-1"}},
            {
                "type": "response.output_text.delta",
                "response_id": "response-2",
                "item_id": "message-2",
                "delta": "Available.",
            },
            {
                "type": "session.output_audio.delta",
                # Separate the returned answer from the spoken acknowledgment.
                "delta": base64.b64encode(bytes(28_800) + (1000).to_bytes(2, "little", signed=True) * 480).decode(),
            },
            {"type": "session.output_transcript.delta", "start_ms": 1000, "end_ms": 1020, "delta": "Available."},
            {"type": "response.completed", "response": {"id": "response-2", "output": []}},
        ):
            await self.events.put(response)

    async def receive_json(self, *, timeout: float) -> dict[str, object]:  # noqa: ASYNC109
        event = await asyncio.wait_for(self.events.get(), timeout)
        if event.get("type") == "response.output_item.done":
            item = event.get("item", {})
            if item.get("status") != "completed":
                await asyncio.sleep(0.02)
            self.tool_started_before_completed_item |= self.executor.started.is_set()
        if event.get("type") == "session.output_audio.delta":
            await asyncio.sleep(0.02)
            self.audio_received_while_tool_pending |= (
                self.executor.started.is_set() and not self.executor.completed.is_set()
            )
        return event


class DelayedAudioConnection:
    """Inject controlled transport delays while observing packet cadence."""

    def __init__(self, *, first_delay: float = 0.0, send_delay: float = 0.0, limit: int = 0) -> None:
        self.first_delay = first_delay
        self.send_delay = send_delay
        self.limit = limit
        self.sent_at: list[float] = []
        self.reached_limit = asyncio.Event()

    async def send_json(self, _payload: dict[str, object]) -> None:
        delay = self.first_delay if not self.sent_at and self.first_delay else self.send_delay
        if delay:
            await asyncio.sleep(delay)
        self.sent_at.append(asyncio.get_running_loop().time())
        if self.limit and len(self.sent_at) >= self.limit:
            self.reached_limit.set()


class TimestampedAudioConnection:
    """Replay untimed v3 output frames without a live connection."""

    def __init__(self, frames: list[tuple[int, bytes]]) -> None:
        self.events: asyncio.Queue[dict[str, object]] = asyncio.Queue()
        for _, pcm in frames:
            self.events.put_nowait(
                {
                    "type": "session.output_audio.delta",
                    "delta": base64.b64encode(pcm).decode("ascii"),
                }
            )
        self.events.put_nowait(
            {
                "type": "session.output_transcript.delta",
                "start_ms": 50_000,
                "end_ms": 50_200,
                "delta": "The restaurant closes at nine.",
            }
        )

    async def send_json(self, _payload: dict[str, object]) -> None:
        return None

    async def receive_json(self, *, timeout: float | None = None) -> dict[str, object]:  # noqa: ASYNC109
        return await asyncio.wait_for(self.events.get(), timeout=timeout)


@pytest.mark.asyncio
async def test_audio_pacer_rebases_instead_of_returning_a_compressed_positive_delay() -> None:
    now = [0.0]
    pacer = AudioPacer(20)
    pacer._loop = SimpleNamespace(time=lambda: now[0])
    pacer.deadline = 0.0

    assert pacer.next_delay() == (0.02, None)
    now[0] = 0.035

    assert pacer.next_delay() == (0.015, None)
    assert pacer.deadline == pytest.approx(0.05)


@pytest.mark.asyncio
async def test_shared_audio_sender_never_catches_up_with_a_short_packet_gap() -> None:
    class BrieflyDelayedConnection(DelayedAudioConnection):
        async def send_json(self, payload: dict[str, object]) -> None:
            if len(self.sent_at) == 3:
                await asyncio.sleep(0.011)
            await super().send_json(payload)

    connection = BrieflyDelayedConnection()
    await stream_audio_to_connection(
        connection,
        bytes(960 * 8),
        20,
        24_000,
        True,
        log_file=io.StringIO(),
        started_at=time.monotonic(),
        event_index_state={"value": 0},
    )

    gaps_ms = [
        (second - first) * 1_000 for first, second in zip(connection.sent_at, connection.sent_at[1:], strict=False)
    ]
    assert min(gaps_ms) >= 14


@pytest.mark.asyncio
async def test_shared_audio_sender_resumes_real_time_without_bursting_after_a_stall() -> None:
    connection = DelayedAudioConnection(first_delay=0.08)
    event_log = io.StringIO()

    await stream_audio_to_connection(
        connection,
        bytes(960 * 8),
        20,
        24_000,
        True,
        log_file=event_log,
        started_at=time.monotonic(),
        event_index_state={"value": 0},
    )

    gaps_ms = [
        (second - first) * 1_000 for first, second in zip(connection.sent_at, connection.sent_at[1:], strict=False)
    ]
    assert len(connection.sent_at) == 8
    assert min(gaps_ms) >= 14
    events = [json.loads(line) for line in event_log.getvalue().splitlines()]
    lag_events = [event for event in events if event["type"] == "audio.pacing_lag"]
    assert len(lag_events) == 1
    assert lag_events[0]["event"]["lag_ms"] >= 40


@pytest.mark.asyncio
async def test_continuous_silence_resumes_real_time_without_bursting_after_a_stall() -> None:
    connection = DelayedAudioConnection(first_delay=0.08, limit=5)
    event_log = io.StringIO()
    completion = CallerAudioCompletion()
    completion.mark_completed()

    sender = asyncio.create_task(
        single_turn_runtime._continue_audio_clock(
            connection,
            chunk_ms=20,
            sample_rate_hz=24_000,
            log_file=event_log,
            started_at=time.monotonic(),
            event_index_state={"value": 0},
            caller_audio_completion=completion,
        )
    )
    await asyncio.wait_for(connection.reached_limit.wait(), timeout=1)
    sender.cancel()
    await asyncio.gather(sender, return_exceptions=True)

    gaps_ms = [
        (second - first) * 1_000 for first, second in zip(connection.sent_at, connection.sent_at[1:], strict=False)
    ]
    assert min(gaps_ms) >= 14
    assert completion.timeline_ms == len(connection.sent_at) * 20
    assert any(json.loads(line)["type"] == "audio.pacing_lag" for line in event_log.getvalue().splitlines())


@pytest.mark.asyncio
async def test_shared_audio_sender_preserves_absolute_deadlines_across_64_streams() -> None:
    connections = [DelayedAudioConnection(send_delay=0.004) for _ in range(64)]

    async def send(connection: DelayedAudioConnection) -> None:
        await stream_audio_to_connection(
            connection,
            bytes(960 * 8),
            20,
            24_000,
            True,
            log_file=io.StringIO(),
            started_at=time.monotonic(),
            event_index_state={"value": 0},
        )

    await asyncio.gather(*(send(connection) for connection in connections))

    drifts_ms = [(connection.sent_at[-1] - connection.sent_at[0]) * 1_000 - 140 for connection in connections]
    assert max(drifts_ms) < 35
    assert min(drifts_ms) > -20


@pytest.mark.asyncio
async def test_shared_tool_runtime_keeps_the_event_loop_available_during_blocking_customer_tools() -> None:
    executor = SlowApplicationTools()
    runtime = AsyncToolRuntime(executor)
    received: list[dict[str, object]] = []

    async def on_result(result) -> None:
        received.append(result.output)

    runtime.submit("check_availability", {}, call_id="call-1", on_result=on_result)
    await asyncio.wait_for(asyncio.to_thread(executor.started.wait, 1), timeout=1)
    await asyncio.wait_for(asyncio.sleep(0.02), timeout=0.1)

    assert runtime.pending
    assert not executor.completed.is_set()

    await runtime.wait()

    assert received == [{"ok": True, "available": True}]
    assert len(executor.executions) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("unfinished_status", [None, "in_progress", "incomplete", "cancelled", "failed"])
async def test_shared_single_turn_receiver_processes_audio_while_customer_tool_is_running(
    unfinished_status: str | None,
) -> None:
    executor = SlowApplicationTools()
    connection = ToolStreamingConnection(executor, unfinished_status=unfinished_status)
    timeline = Timeline()
    event_log = io.StringIO()

    assistant_connection = await bind_responses_delegation(connection, executor=executor)
    try:
        response = await collect_live_response(
            assistant_connection,
            event_log,
            chunk_ms=20,
            sample_rate_hz=24_000,
            timeout_seconds=2,
            trace_started_at=time.monotonic(),
            event_index_state={"value": 0},
            tool_observer=executor,
            timeline=timeline,
        )
    finally:
        await assistant_connection.close()

    assert not connection.tool_started_before_completed_item
    assert connection.audio_received_while_tool_pending
    assert response["assistant_text"] == "Checking. Available."
    assert len(response["tool_executions"]) == 1
    assert any(event["type"] == "session.input_audio.append" for event in connection.sent)
    assert any(event["type"] == "response.item.create" for event in connection.sent)
    tool_events = [event for event in timeline.agent_events if event.event_type in {"tool.called", "tool.completed"}]
    assert [event.event_type for event in tool_events] == ["tool.called", "tool.completed"]
    assert tool_events[0].timestamp_ms < tool_events[1].timestamp_ms
    traces = [json.loads(line) for line in event_log.getvalue().splitlines()]
    tool_traces = [event for event in traces if event["type"] in {"tool.called", "tool.completed"}]
    assert tool_traces[0]["event_index"] < tool_traces[1]["event_index"]
    assert tool_traces[0]["event"]["offset_ms"] < tool_traces[1]["event"]["offset_ms"]


@pytest.mark.parametrize(
    "kind", ["session.delegation.created", "response.created", "response.output_item.done", "tool.called"]
)
def test_agent_event_projection_uses_audio_clock_without_overwriting_provider_timestamps(kind: str) -> None:
    event = {"type": kind}

    projected = project_agent_event(event, 1_400)

    assert projected == {"type": kind, "offset_ms": 1_400}
    assert event == {"type": kind}
    provider_event = {"type": kind, "start_ms": 1_250}
    assert project_agent_event(provider_event, 1_400) is provider_event


def test_tool_projections_are_deduplicated_by_call_id_not_timestamp() -> None:
    generated = AgentEvent(
        timestamp_ms=1_400,
        event_type="response.output_item.done",
        kind="tool",
        name="check_availability",
        status="completed",
        arguments={"date": "2026-08-07"},
        call_id="call-1",
    )
    executed = AgentEvent(
        timestamp_ms=1_620,
        event_type="tool.completed",
        kind="tool",
        name="check_availability",
        status="completed",
        arguments={"date": "2026-08-07"},
        result={"available": True},
        call_id="call-1",
    )

    assert unique_tool_invocations([generated, executed]) == [executed]


def test_all_harnesses_share_restaurant_prompts_and_tools() -> None:
    assert DEFAULT_DATA_JSON.name == "scenarios.json"
    assert DEFAULT_SYSTEM_PROMPT_PATH.name == "voice.txt"
    assert DEFAULT_BACKEND_SYSTEM_PROMPT_PATH.name == "backend.txt"
    assert DEFAULT_TOOLS_PATH.name == "definitions.json"
    assert load_system_prompt(DEFAULT_SYSTEM_PROMPT_PATH)
    assert load_system_prompt(DEFAULT_BACKEND_SYSTEM_PROMPT_PATH)


def test_phase_runners_do_not_import_each_other() -> None:
    for phase in ("crawl_harness", "walk_harness", "run_harness"):
        source = PROJECT_ROOT / phase / "evaluate.py"
        modules = [
            node.module or ""
            for node in ast.walk(ast.parse(source.read_text(encoding="utf-8")))
            if isinstance(node, ast.ImportFrom)
        ]
        other_phases = {"crawl_harness", "walk_harness", "run_harness"} - {phase}
        assert not any(module.split(".", maxsplit=1)[0] in other_phases for module in modules)


def test_shared_audio_queue_preserves_continuous_silence() -> None:
    pcm = b"\x01\x00" * 7
    assert chunk_pcm(pcm, 8) == [b"\x01\x00" * 4, b"\x01\x00" * 3 + bytes(2)]
    queue = AudioQueue(24_000, 20, "clean", 0)

    assert queue.enqueue(pcm) == 1
    speech, speaking = queue.next_chunk()
    silence, silence_speaking = queue.next_chunk()

    assert speaking
    assert speech == pcm + bytes(960 - len(pcm))
    assert not silence_speaking
    assert silence == bytes(960)


def test_audio_writer_preserves_valid_mono_pcm(tmp_path: Path) -> None:
    silence = bytes(960)
    speech = (2_500).to_bytes(2, "little", signed=True) * 480
    output = write_mono_wav(tmp_path / "reference.wav", silence + speech, 24_000)

    assert speech_intervals_pcm16(silence + speech, 100, 24_000, 220.0) == [(120, 140)]
    with wave.open(str(output), "rb") as recording:
        assert (recording.getnchannels(), recording.getsampwidth(), recording.getframerate()) == (1, 2, 24_000)
        assert recording.readframes(recording.getnframes()) == silence + speech
    assert read_mono_wav(output, sample_rate_hz=24_000) == silence + speech


def test_conversation_artifact_retains_timeline_aligned_stereo(tmp_path: Path) -> None:
    recorder = ConversationRecorder(24_000)
    caller = array("h", [1_000, -1_000, 2_000, -2_000])
    assistant = array("h", [3_000, -3_000])
    recorder.add("user", 0, caller.tobytes())
    recorder.add("assistant", 1, assistant.tobytes())

    path, transcript = recorder.save(tmp_path / "conversation.wav", "USER: Hi\nASSISTANT: Hello")

    with wave.open(str(path), "rb") as recording:
        samples = array("h")
        samples.frombytes(recording.readframes(recording.getnframes()))
        assert recording.getnchannels() == 2
    assert samples[::2] == array("h", [*caller, *([0] * 22)])
    assert samples[1::2] == array("h", [*([0] * 24), *assistant])
    assert transcript.read_text(encoding="utf-8") == "USER: Hi\nASSISTANT: Hello\n"


def test_timestamped_pcm_normalizes_first_offset_and_preserves_real_provider_gap() -> None:
    first = array("h", [1_100] * 2_400).tobytes()
    second = array("h", [2_200] * 2_400).tobytes()
    aligned = conversation_audio.TimestampedAudioBuffer(24_000)

    first_output = aligned.append(first, start_ms=5_660)
    second_output = aligned.append(second, start_ms=5_960)

    assert first_output == first
    assert second_output == bytes(9_600) + second
    assert len(first_output + second_output) == 19_200


def test_timestamped_pcm_omits_duplicate_and_overlapping_provider_samples() -> None:
    first = array("h", range(2_400)).tobytes()
    overlapping = array("h", range(2_400, 4_800)).tobytes()
    duplicate = array("h", range(4_800, 7_200)).tobytes()
    aligned = conversation_audio.TimestampedAudioBuffer(24_000)

    assert aligned.append(first, start_ms=1_000) == first
    assert aligned.append(overlapping, start_ms=1_080) == overlapping[960:]
    assert aligned.append(duplicate, start_ms=1_040) == b""
    assert aligned.sample_count == 4_320


@pytest.mark.asyncio
async def test_single_turn_untimed_burst_preserves_order_without_network_arrival_gaps() -> None:
    first = array("h", [1_200] * 2_400).tobytes()
    second = array("h", [2_300] * 2_400).tobytes()
    recorder = ConversationRecorder(24_000)
    connection = TimestampedAudioConnection([(5_660, first), (5_960, second)])

    response = await collect_live_response(
        connection,
        io.StringIO(),
        chunk_ms=20,
        sample_rate_hz=24_000,
        timeout_seconds=1,
        trace_started_at=time.monotonic(),
        event_index_state={"value": 0},
        tool_observer=SlowApplicationTools(),
        recorder=recorder,
    )

    assert response["output_audio_bytes"] == first + second
    assert len(response["output_audio_bytes"]) * 1_000 // (24_000 * 2) == 200
    start = round(response["first_assistant_speech_offset_ms"] * 24)
    assert recorder.assistant[start : start + 2400] == array("h", [1_200] * 2_400)
    assert recorder.assistant[start + 2400 : start + 4800] == array("h", [2_300] * 2_400)


@pytest.mark.parametrize(("available_channels", "expected_channels"), [(1, 1), (2, 2), (8, 2)])
def test_live_monitor_selects_supported_output_channels(
    monkeypatch: pytest.MonkeyPatch,
    available_channels: int,
    expected_channels: int,
) -> None:
    streams: list[SimpleNamespace] = []

    def create_stream(**kwargs: object) -> SimpleNamespace:
        stream = SimpleNamespace(
            channels=kwargs["channels"],
            started=False,
            stopped=False,
            closed=False,
        )
        stream.start = lambda: setattr(stream, "started", True)
        stream.stop = lambda: setattr(stream, "stopped", True)
        stream.close = lambda: setattr(stream, "closed", True)
        streams.append(stream)
        return stream

    monkeypatch.setitem(
        sys.modules,
        "sounddevice",
        SimpleNamespace(
            query_devices=lambda *, kind: {"max_output_channels": available_channels},
            RawOutputStream=create_stream,
        ),
    )
    monitor = conversation_audio.LiveMonitor(24_000)

    monitor.start()

    assert monitor.output_channels == expected_channels
    assert streams[0].channels == expected_channels
    assert streams[0].started

    monitor.close()

    assert streams[0].stopped
    assert streams[0].closed


def test_live_monitor_mixes_both_conversation_roles_for_mono_output() -> None:
    monitor = conversation_audio.LiveMonitor(24_000)
    monitor.output_channels = 1
    monitor.push("user", array("h", [1_100, 30_000, -30_000, 1_100]).tobytes())
    monitor.push("assistant", array("h", [2_200, 10_000, -10_000]).tobytes())
    output = bytearray(4 * 2)

    monitor._callback(output, 4, None, None)

    mono = array("h")
    mono.frombytes(output)
    assert mono == array("h", [3_300, 32_767, -32_768, 1_100])


def test_live_monitor_preserves_timestamped_gap_and_stereo_channel_alignment() -> None:
    monitor = conversation_audio.LiveMonitor(24_000)
    caller = array("h", [1_100] * 2_400).tobytes()
    first = array("h", [2_200] * 480).tobytes()
    second = array("h", [3_300] * 480).tobytes()

    monitor.push("user", caller, start_ms=1_000)
    monitor.push("assistant", first, start_ms=1_040)
    monitor.push("assistant", second, start_ms=1_120)
    output = bytearray(3_360 * 4)
    monitor._callback(output, 3_360, None, None)
    stereo = array("h")
    stereo.frombytes(output)

    assert stereo[::2] == array("h", [*([1_100] * 2_400), *([0] * 960)])
    assert stereo[1::2] == array("h", [*([0] * 960), *([2_200] * 480), *([0] * 1_440), *([3_300] * 480)])


def test_live_monitor_preserves_late_assistant_audio_in_full() -> None:
    monitor = conversation_audio.LiveMonitor(24_000)
    caller = array("h", [1_100] * 2_400).tobytes()
    late_assistant = array("h", [*([2_200] * 1_200), *([3_300] * 1_200)]).tobytes()
    monitor.push("user", caller, start_ms=1_000)
    monitor._callback(bytearray(2_400 * 4), 2_400, None, None)

    monitor.push("assistant", late_assistant, start_ms=1_050)

    assert len(monitor._assistant) == 4_800
    samples = array("h")
    samples.frombytes(monitor._assistant)
    assert samples == array("h", [*([2_200] * 1_200), *([3_300] * 1_200)])


def test_live_monitor_preserves_gaps_between_late_assistant_packets() -> None:
    monitor = conversation_audio.LiveMonitor(24_000)
    caller = array("h", [1_100] * 4_800).tobytes()
    first = array("h", [2_200] * 480).tobytes()
    second = array("h", [3_300] * 480).tobytes()
    monitor.push("user", caller, start_ms=1_000)
    monitor._callback(bytearray(4_800 * 4), 4_800, None, None)

    monitor.push("assistant", first, start_ms=1_040)
    monitor.push("assistant", second, start_ms=1_120)

    samples = array("h")
    samples.frombytes(monitor._assistant)
    assert samples == array("h", [*([2_200] * 480), *([0] * 1_440), *([3_300] * 480)])


def test_live_monitor_discards_duplicate_source_audio_without_discarding_late_audio() -> None:
    monitor = conversation_audio.LiveMonitor(24_000)
    caller = array("h", [1_100] * 2_400).tobytes()
    first = array("h", [2_200] * 480).tobytes()
    overlapping = array("h", [3_300] * 480).tobytes()
    monitor.push("user", caller, start_ms=1_000)
    monitor._callback(bytearray(2_400 * 4), 2_400, None, None)

    monitor.push("assistant", first, start_ms=1_040)
    monitor.push("assistant", first, start_ms=1_040)
    monitor.push("assistant", overlapping, start_ms=1_050)

    samples = array("h")
    samples.frombytes(monitor._assistant)
    assert samples == array("h", [*([2_200] * 480), *([3_300] * 240)])


def test_live_monitor_anchors_first_source_timestamp_to_current_playback_cursor() -> None:
    monitor = conversation_audio.LiveMonitor(24_000)
    first = array("h", [1_100] * 480).tobytes()
    monitor._callback(bytearray(480 * 4), 480, None, None)

    monitor.push("user", first, start_ms=2_000)

    assert monitor._user == first


def test_shared_traces_redact_audio_and_preserve_direction() -> None:
    stream = io.StringIO()
    record_event(
        stream,
        {"type": "session.input_audio.append", "audio": "sensitive-base64-audio"},
        started_at=time.monotonic(),
        event_index_state={"value": 0},
        source="caller_audio",
        direction="client_to_server",
    )

    event = json.loads(stream.getvalue())
    assert event["source"] == "caller_audio"
    assert event["direction"] == "client_to_server"
    assert "sensitive-base64-audio" not in stream.getvalue()


def test_shared_artifact_writer_saves_reproducible_json(tmp_path: Path) -> None:
    path = write_json(tmp_path / "nested" / "artifact.json", {"example": "restaurant_001"})

    assert json.loads(path.read_text(encoding="utf-8")) == {"example": "restaurant_001"}
    assert path.read_text(encoding="utf-8").endswith("\n")


def test_restaurant_tools_are_normalized_for_the_live_alpha() -> None:
    original = load_tools(DEFAULT_TOOLS_PATH)
    normalized = normalize_live_response_tools(original)

    assert {tool["name"] for tool in original} == {
        "check_availability",
        "create_reservation",
        "cancel_reservation",
    }
    assert all(tool["parameters"]["additionalProperties"] is False for tool in normalized)
    assert all("strict" not in tool for tool in normalized)


def test_shared_assistant_builds_one_safe_delegated_session() -> None:
    event = build_assistant_session(
        LiveAgentSettings(backend_model="shared-backend", backend_reasoning_effort="low"),
        instructions="Frontend instructions.",
        backend_instructions="Backend instructions.",
        tools=load_tools(DEFAULT_TOOLS_PATH),
    )

    serialized = json.dumps(event)
    assert event["type"] == "session.start"
    assert event["session"]["delegation"]["responses"]["model"] == "shared-backend"
    assert "response.create" not in serialized
    assert "input_audio_buffer.commit" not in serialized


def test_shared_assistant_hydrates_text_only_history_without_mutating_it() -> None:
    history = [
        ConversationHistoryItem(role="user", text="Please book a table under Maya."),
        ConversationHistoryItem(role="assistant", text="What time works best?"),
    ]
    initial_items = build_initial_items(history)

    event = build_assistant_session(
        LiveAgentSettings(),
        instructions="Frontend instructions.",
        backend_instructions="Backend instructions.",
        tools=load_tools(DEFAULT_TOOLS_PATH),
        initial_items=initial_items,
    )

    assert event["session"]["input"] == [
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "Please book a table under Maya."}],
        },
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "What time works best?"}],
        },
    ]
    event["session"]["input"][0]["content"][0]["text"] = "Changed after construction."
    assert initial_items[0]["content"][0]["text"] == "Please book a table under Maya."


def test_delegation_is_active_only_until_its_final_followup_response_completes() -> None:
    timeline = Timeline()

    assert not timeline.delegation_active

    lifecycle = [
        (
            {
                "type": "session.delegation.created",
                "offset_ms": 200,
                "delegation": {"target": "responses", "response_id": "response-original"},
            },
            True,
        ),
        (
            {"type": "response.created", "offset_ms": 300, "response": {"id": "response-original"}},
            True,
        ),
        (
            {
                "type": "tool.called",
                "offset_ms": 400,
                "response_id": "response-original",
                "call_id": "call-1",
                "name": "check_availability",
            },
            True,
        ),
        (
            {
                "type": "tool.completed",
                "offset_ms": 500,
                "response_id": "response-original",
                "call_id": "call-1",
                "name": "check_availability",
                "result": {"available": True},
            },
            True,
        ),
        (
            {"type": "response.completed", "offset_ms": 600, "response": {"id": "response-original"}},
            True,
        ),
        (
            {"type": "response.created", "offset_ms": 700, "response": {"id": "response-followup"}},
            True,
        ),
        (
            {"type": "response.completed", "offset_ms": 800, "response": {"id": "response-followup"}},
            False,
        ),
    ]
    for event, expected_active in lifecycle:
        timeline.apply_event(event)
        assert timeline.delegation_active is expected_active, event["type"]

    ticks = build_ticks(timeline, 100, 24_000, duration_ms=1_000)
    assert [tick["interaction"]["delegation_active"] for tick in ticks] == [
        False,
        False,
        True,
        True,
        True,
        True,
        True,
        True,
        False,
        False,
    ]
    timeline.add_audio("assistant", 320, 380, True)
    timeline.add_audio("user", 520, 570, True)
    ticks = build_ticks(timeline, 100, 24_000, duration_ms=1_000)
    metrics = compute_interaction_metrics(ticks, tick_ms=100, timeline=timeline)

    assert metrics["floor_hold_silence_ms"] == {"cumulative": 490, "maximum": 230}
    assert metrics["floor_hold_intervals_ms"] == [[200, 320], [380, 520], [570, 800]]
    assert sum(right - left for left, right in metrics["floor_hold_intervals_ms"]) == 490


def test_interaction_metrics_use_the_audio_timeline() -> None:
    timeline = Timeline()
    timeline.add_audio("user", 0, 200, True)
    timeline.add_user_utterance(0, 200, "Hello", action="OPENING")
    timeline.add_audio("assistant", 400, 600, True)
    metrics = compute_interaction_metrics(
        build_ticks(timeline, 20, 24_000, duration_ms=600), tick_ms=20, timeline=timeline
    )

    assert metrics["response_latencies_ms"] == [200]
    assert metrics["response_latency_ms"] == 200
    assert metrics["response_latency_mean"] == 0.2
    assert metrics["response_rate"] == 1.0
    assert metrics["speaking_duration_ms"] == {"cumulative": 200, "maximum": 200}
    assert metrics["floor_hold_silence_ms"] == {"cumulative": 0, "maximum": 0}


@pytest.mark.parametrize("tick_ms", [20, 200])
@pytest.mark.parametrize("offset_ms", [0, 100])
def test_silent_gap_does_not_become_a_yield_opportunity(tick_ms: int, offset_ms: int) -> None:
    timeline = Timeline()
    timeline.add_audio("assistant", 200 + offset_ms, 220 + offset_ms, True)
    timeline.add_audio("assistant", 580 + offset_ms, 600 + offset_ms, True)
    timeline.add_audio("user", 350 + offset_ms, 370 + offset_ms, True)
    timeline.add_user_utterance(350 + offset_ms, 370 + offset_ms, "A new question", action="SPEAK")
    ticks = build_ticks(timeline, tick_ms, 24_000, duration_ms=1_000 + offset_ms)

    metrics = compute_interaction_metrics(ticks, tick_ms=tick_ms, timeline=timeline)
    turn = compute_turn_interaction_metrics(ticks, timeline)[0]

    assert metrics["counts"]["yield_total"] == 0
    assert metrics["response_latencies_ms"] == [210]
    assert turn["audio"]["overlap_ms"] == 0
    assert turn["audio"]["yield_outcome"] == "not_applicable"
    assert turn["audio"]["response_latency_ms"] == 210


def test_disjoint_speech_inside_one_tick_does_not_fill_the_gap() -> None:
    timeline = Timeline()
    timeline.add_audio("assistant", 100, 110, True)
    timeline.add_audio("assistant", 160, 170, True)
    timeline.add_audio("user", 130, 140, True)
    timeline.add_user_utterance(130, 140, "Question", action="SPEAK")
    ticks = build_ticks(timeline, 200, 24_000, duration_ms=400)

    metrics = compute_interaction_metrics(ticks, tick_ms=200, timeline=timeline)

    assert metrics["counts"]["yield_total"] == 0
    assert metrics["response_latencies_ms"] == [20]


@pytest.mark.parametrize("tick_ms", [20, 200])
def test_overlapping_audio_intervals_are_counted_once(tick_ms: int) -> None:
    timeline = Timeline()
    timeline.add_audio("assistant", 100, 140, True)
    timeline.add_audio("assistant", 120, 160, True)
    timeline.add_audio("assistant", 160, 180, True)
    timeline.add_audio("user", 130, 170, True)
    timeline.add_user_utterance(130, 170, "Correction", action="INTERRUPT")
    ticks = build_ticks(timeline, tick_ms, 24_000, duration_ms=400)

    turn = compute_turn_interaction_metrics(ticks, timeline)[0]

    assert sum(tick["interaction"]["overlap_ms"] for tick in ticks) == 40
    assert turn["audio"]["overlap_ms"] == 40
    assert turn["audio"]["assistant_speech_ms"] == 50


@pytest.mark.parametrize("tick_ms", [20, 200])
def test_speech_during_a_caller_pause_is_not_an_acoustic_interruption(tick_ms: int) -> None:
    timeline = Timeline()
    timeline.add_audio("user", 100, 110, True)
    timeline.add_audio("user", 160, 170, True)
    timeline.add_user_utterance(100, 170, "One question with a pause", action="SPEAK")
    timeline.add_audio("assistant", 130, 140, True)
    ticks = build_ticks(timeline, tick_ms, 24_000, duration_ms=6_000)

    metrics = compute_interaction_metrics(ticks, tick_ms=tick_ms, timeline=timeline)
    turn = compute_turn_interaction_metrics(ticks, timeline)[0]

    assert metrics["counts"]["agent_interrupts_count"] == 0
    assert turn["audio"]["agent_interruption_count"] == 0
    assert turn["audio"]["overlap_ms"] == 0
    assert turn["audio"]["user_speech_ms"] == 20


@pytest.mark.parametrize("assistant_end_ms, expected_yields", [(400, 1), (399, 0)])
@pytest.mark.parametrize("tick_ms", [20, 200])
def test_explicit_interruption_cue_preserves_immediate_yield_without_inventing_gap_exposure(
    assistant_end_ms: int, expected_yields: int, tick_ms: int
) -> None:
    timeline = Timeline()
    timeline.add_audio("assistant", 200, assistant_end_ms, True)
    timeline.add_audio("user", 400, 600, True)
    timeline.add_user_utterance(400, 600, "Wait, change the date", action="INTERRUPT")
    timeline.add_audio("assistant", 700, 800, True)
    ticks = build_ticks(timeline, tick_ms, 24_000, duration_ms=800)

    metrics = compute_interaction_metrics(ticks, tick_ms=tick_ms, timeline=timeline)
    turn = compute_turn_interaction_metrics(ticks, timeline)[0]

    assert metrics["counts"]["yield_total"] == expected_yields
    assert metrics["yield_latencies_ms"] == ([0] if expected_yields else [])
    assert turn["audio"]["overlap_ms"] == 0
    assert turn["audio"]["yield_outcome"] == ("yielded" if expected_yields else "not_applicable")


def test_simultaneous_speech_onset_is_not_preexisting_interruption_exposure() -> None:
    timeline = Timeline()
    timeline.add_audio("assistant", 200, 400, True)
    timeline.add_audio("user", 200, 500, True)
    timeline.add_user_utterance(200, 500, "Question", action="INTERRUPT")
    ticks = build_ticks(timeline, 200, 24_000, duration_ms=600)

    metrics = compute_interaction_metrics(ticks, tick_ms=200, timeline=timeline)

    assert metrics["counts"]["yield_total"] == 0


@pytest.mark.parametrize("tick_ms", [20, 200])
def test_backchannel_silence_is_not_bridged_by_reporting_tick_width(tick_ms: int) -> None:
    timeline = Timeline()
    timeline.add_audio("assistant", 100, 240, True)
    timeline.add_audio("assistant", 300, 500, True)
    timeline.add_audio("user", 200, 280, True)
    timeline.add_user_utterance(200, 280, "Mm-hmm", action="BACKCHANNEL")
    ticks = build_ticks(timeline, tick_ms, 24_000, duration_ms=600)

    metrics = compute_interaction_metrics(ticks, tick_ms=tick_ms, timeline=timeline)
    turn = compute_turn_interaction_metrics(ticks, timeline)[0]

    assert metrics["selectivity_backchannel"] == 0.0
    assert turn["audio"]["backchannel_outcome"] == "false_yield"


def test_speaking_duration_excludes_silence_and_uses_agent_turns() -> None:
    timeline = Timeline()
    timeline.add_audio("assistant", 200, 300, True)
    timeline.add_audio("assistant", 400, 550, True)
    timeline.add_turn(Turn("assistant", 200, 600, "First response"))
    timeline.add_audio("assistant", 720, 820, True)
    timeline.add_turn(Turn("assistant", 700, 900, "Second response"))

    metrics = compute_interaction_metrics(
        build_ticks(timeline, 20, 24_000, duration_ms=900), tick_ms=20, timeline=timeline
    )

    assert metrics["speaking_duration_ms"] == {"cumulative": 350, "maximum": 250}


def test_transcript_only_caller_cannot_fabricate_audio_metrics() -> None:
    timeline = Timeline()
    timeline.add_user_utterance(0, 200, "A caller transcript without speech", action="OPENING")
    timeline.add_audio("assistant", 400, 600, True)

    metrics = compute_interaction_metrics(
        build_ticks(timeline, 20, 24_000, duration_ms=600), tick_ms=20, timeline=timeline
    )

    assert timeline.speech_intervals("user") == ()
    assert metrics["response_latencies_ms"] == []
    assert metrics["response_latency_ms"] is None
    assert metrics["response_latency_mean"] is None
    assert metrics["response_rate"] is None
    assert metrics["yield_latency_mean"] is None
    assert metrics["selectivity_backchannel"] is None


def test_transcript_and_turn_events_do_not_replace_missing_audio() -> None:
    timeline = Timeline()
    timeline.add_user_utterance(0, 200, "Hello", action="OPENING")
    for event in (
        {"type": "session.input_transcript.delta", "start_ms": 0, "end_ms": 200, "delta": "Hello"},
        {"type": "turn.done", "turn": {"role": "user", "start_ms": 0, "end_ms": 200, "transcript": "Hello"}},
        {"type": "session.output_transcript.delta", "start_ms": 300, "end_ms": 500, "delta": "Hi"},
        {"type": "turn.done", "turn": {"role": "assistant", "start_ms": 300, "end_ms": 500, "transcript": "Hi"}},
    ):
        timeline.apply_event(event)

    metrics = compute_interaction_metrics(
        build_ticks(timeline, 20, 24_000, duration_ms=500), tick_ms=20, timeline=timeline
    )

    assert timeline.speech_intervals("user") == ()
    assert timeline.speech_intervals("assistant") == ()
    assert metrics["response_latency_mean"] is None
    assert metrics["response_rate"] is None
    assert metrics["interruption_rate"] is None


def test_audio_metrics_use_observed_boundaries_not_utterance_or_transcript_timestamps() -> None:
    timeline = Timeline()
    timeline.add_user_utterance(0, 200, "A caller with a natural pause", action="OPENING")
    timeline.add_audio("user", 40, 80, True)
    timeline.add_audio("user", 120, 160, True)
    timeline.add_audio("assistant", 220, 300, True)
    timeline.add_transcript("assistant", 1_000, 1_200, "A delayed transcript", "session.output_transcript.delta")

    metrics = compute_interaction_metrics(
        build_ticks(timeline, 20, 24_000, duration_ms=1_200), tick_ms=20, timeline=timeline
    )

    assert metrics["response_latencies_ms"] == [60]
    assert metrics["response_latency_mean"] == 0.06
    assert metrics["response_rate"] == 1.0


def test_caller_closing_is_excluded_from_response_metrics_even_when_the_assistant_replies() -> None:
    timeline = Timeline()
    timeline.add_user_utterance(0, 200, "Book a table", action="OPENING")
    timeline.add_audio("user", 0, 200, True)
    timeline.add_audio("assistant", 300, 500, True)
    timeline.add_user_utterance(600, 800, "Thanks, that's everything.", action="STOP")
    timeline.add_audio("user", 600, 800, True)
    timeline.add_audio("assistant", 900, 1_100, True)
    ticks = build_ticks(timeline, 20, 24_000, duration_ms=1_100)

    metrics = compute_interaction_metrics(ticks, tick_ms=20, timeline=timeline)
    turns = compute_turn_interaction_metrics(ticks, timeline)

    assert metrics["response_latencies_ms"] == [100]
    assert metrics["response_rate"] == 1.0
    assert metrics["counts"]["response_total"] == 1
    assert turns[-1]["action"] == "STOP"
    assert turns[-1]["audio"]["response_expected"] is False
    assert turns[-1]["audio"]["response_outcome"] == "not_applicable"


def test_caller_closing_overlap_does_not_count_as_interruption_or_yield_opportunity() -> None:
    timeline = Timeline()
    timeline.add_user_utterance(0, 200, "Book a table", action="OPENING")
    timeline.add_audio("user", 0, 200, True)
    timeline.add_audio("assistant", 300, 500, True)
    timeline.add_user_utterance(600, 800, "Thanks, goodbye.", action="STOP")
    timeline.add_audio("user", 600, 800, True)
    timeline.add_audio("assistant", 650, 900, True)
    ticks = build_ticks(timeline, 20, 24_000, duration_ms=900)

    metrics = compute_interaction_metrics(ticks, tick_ms=20, timeline=timeline)
    turns = compute_turn_interaction_metrics(ticks, timeline)

    assert metrics["response_rate"] == 1.0
    assert metrics["interruption_rate"] == 0.0
    assert metrics["yield_rate"] is None
    assert turns[-1]["audio"]["agent_interruption_count"] == 0
    assert turns[-1]["audio"]["yield_outcome"] == "not_applicable"
    assert not any(event["type"] == "agent_interruption" for event in extract_interaction_events(turns))


def test_final_unanswered_caller_request_remains_unobserved_instead_of_a_failure() -> None:
    timeline = Timeline()
    timeline.add_user_utterance(0, 200, "Book a table", action="OPENING")
    timeline.add_audio("user", 0, 200, True)
    ticks = build_ticks(timeline, 20, 24_000, duration_ms=400)

    metrics = compute_interaction_metrics(ticks, tick_ms=20, timeline=timeline)
    turns = compute_turn_interaction_metrics(ticks, timeline)

    assert metrics["response_rate"] is None
    assert metrics["counts"]["no_response_count"] == 0
    assert turns[-1]["audio"]["response_outcome"] == "unobserved"


@pytest.mark.parametrize("tick_ms", [20, 200])
@pytest.mark.parametrize("offset_ms", [0, 100])
@pytest.mark.parametrize(
    "duration_ms, expected_rate, expected_missed, expected_censored, expected_status",
    [
        (1_020, 1.0, 0, 1, "censored"),
        (5_999, 1.0, 0, 1, "censored"),
        (6_000, 0.5, 1, 0, "missed"),
        (90_000, 0.5, 1, 0, "missed"),
    ],
)
def test_final_response_opportunity_matures_independently_of_tick_phase(
    tick_ms: int,
    offset_ms: int,
    duration_ms: int,
    expected_rate: float,
    expected_missed: int,
    expected_censored: int,
    expected_status: str,
) -> None:
    timeline = Timeline()
    timeline.add_audio("user", offset_ms, 200 + offset_ms, True)
    timeline.add_user_utterance(offset_ms, 200 + offset_ms, "First question", action="OPENING")
    timeline.add_audio("assistant", 300 + offset_ms, 500 + offset_ms, True)
    timeline.add_audio("user", 800 + offset_ms, 1_000 + offset_ms, True)
    timeline.add_user_utterance(800 + offset_ms, 1_000 + offset_ms, "Another question", action="SPEAK")
    ticks = build_ticks(timeline, tick_ms, 24_000, duration_ms=duration_ms + offset_ms)

    metrics = compute_interaction_metrics(ticks, tick_ms=tick_ms, timeline=timeline)
    turns = compute_turn_interaction_metrics(ticks, timeline)

    assert metrics["response_rate"] == expected_rate
    assert metrics["counts"]["response_count"] == 1
    assert metrics["counts"]["no_response_count"] == expected_missed
    assert metrics["counts"]["response_total"] == 1 + expected_missed
    assert metrics["counts"].get("caller_turn_count") == 2
    assert metrics["counts"].get("response_eligible_count") == 2
    assert metrics["counts"].get("response_censored_count") == expected_censored
    assert metrics["counts"].get("response_excluded_count") == 0
    assert turns[-1]["audio"].get("response_status") == expected_status
    assert turns[-1]["audio"]["response_outcome"] == ("no_response" if expected_missed else "unobserved")
    assert turns[-1]["audio"].get("response_deadline_at_ms") == 6_000 + offset_ms
    assert metrics.get("metrics_version") == "2.0"
    assert metrics["config"].get("response_deadline_ms") == 5_000


@pytest.mark.parametrize(
    "response_start_ms, expected_rate, expected_timely, expected_late",
    [(5_199, 1.0, [4_999], []), (5_200, 1.0, [5_000], []), (5_201, 0.0, [], [5_001])],
)
def test_response_deadline_boundary_preserves_late_audio_without_erasing_the_miss(
    response_start_ms: int, expected_rate: float, expected_timely: list[int], expected_late: list[int]
) -> None:
    timeline = Timeline()
    timeline.add_audio("user", 0, 200, True)
    timeline.add_user_utterance(0, 200, "Question", action="OPENING")
    timeline.add_audio("assistant", response_start_ms, response_start_ms + 100, True)
    ticks = build_ticks(timeline, 200, 24_000, duration_ms=5_400)

    metrics = compute_interaction_metrics(ticks, tick_ms=200, timeline=timeline)
    turn = compute_turn_interaction_metrics(ticks, timeline)[0]

    assert metrics["response_rate"] == expected_rate
    assert metrics["response_latencies_ms"] == expected_timely
    assert metrics.get("late_response_latencies_ms") == expected_late
    assert metrics["counts"].get("response_late_count") == len(expected_late)
    assert metrics["counts"]["no_response_count"] == len(expected_late)
    assert turn["audio"].get("response_observed_latency_ms") == response_start_ms - 200
    assert turn["audio"].get("response_status") == ("missed" if expected_late else "answered")
    if expected_late:
        events = extract_interaction_events([turn])
        assert {"type": "no_response", "caller_end_ms": 200} in events
        assert {
            "type": "late_response",
            "caller_end_ms": 200,
            "assistant_start_ms": 5_201,
            "latency_ms": 5_001,
            "deadline_at_ms": 5_200,
        } in events


@pytest.mark.parametrize("deadline_ms, expected_rate, expected_status", [(199, 0.0, "missed"), (200, 1.0, "answered")])
def test_custom_response_deadline_changes_the_measured_outcome_in_both_views(
    deadline_ms: int, expected_rate: float, expected_status: str
) -> None:
    timeline = Timeline()
    timeline.add_audio("user", 0, 200, True)
    timeline.add_user_utterance(0, 200, "Question", action="OPENING")
    timeline.add_audio("assistant", 400, 600, True)
    ticks = build_ticks(timeline, 200, 24_000, duration_ms=600)

    metrics = compute_interaction_metrics(ticks, tick_ms=200, timeline=timeline, response_deadline_ms=deadline_ms)
    turn = compute_turn_interaction_metrics(ticks, timeline, response_deadline_ms=deadline_ms)[0]

    assert metrics["response_rate"] == expected_rate
    assert turn["audio"]["response_status"] == expected_status
    assert turn["audio"]["response_deadline_at_ms"] == 200 + deadline_ms
    assert metrics["config"]["response_deadline_ms"] == deadline_ms


@pytest.mark.parametrize("deadline_ms", [0, -1, True, 1.5, None])
def test_invalid_response_deadline_is_rejected_even_without_audio(deadline_ms: object) -> None:
    timeline = Timeline()

    with pytest.raises(ValueError, match="response_deadline_ms must be a positive integer"):
        compute_interaction_metrics([], tick_ms=20, timeline=timeline, response_deadline_ms=deadline_ms)
    with pytest.raises(ValueError, match="response_deadline_ms must be a positive integer"):
        compute_turn_interaction_metrics([], timeline, response_deadline_ms=deadline_ms)


def test_response_opportunity_exclusions_have_explicit_reasons() -> None:
    timeline = Timeline()
    timeline.add_audio("user", 0, 200, True)
    timeline.add_user_utterance(0, 200, "Question", action="OPENING")
    timeline.add_audio("assistant", 300, 500, True)
    timeline.add_audio("user", 600, 650, True)
    timeline.add_user_utterance(600, 650, "Mm-hmm", action="BACKCHANNEL")
    timeline.add_audio("user", 800, 1_000, True)
    timeline.add_user_utterance(800, 1_000, "Thanks, goodbye", action="STOP")
    ticks = build_ticks(timeline, 200, 24_000, duration_ms=1_200)

    metrics = compute_interaction_metrics(ticks, tick_ms=200, timeline=timeline)
    turns = compute_turn_interaction_metrics(ticks, timeline)

    assert metrics["counts"].get("caller_turn_count") == 3
    assert metrics["counts"].get("response_eligible_count") == 1
    assert metrics["counts"].get("response_excluded_count") == 2
    assert metrics.get("response_exclusion_reasons") == {"backchannel": 1, "caller_closing": 1}
    assert [turn["audio"].get("response_status") for turn in turns] == ["answered", "excluded", "excluded"]


def test_a_new_eligible_request_closes_an_unanswered_opportunity() -> None:
    timeline = Timeline()
    timeline.add_audio("user", 0, 200, True)
    timeline.add_user_utterance(0, 200, "First question", action="OPENING")
    timeline.add_audio("user", 600, 800, True)
    timeline.add_user_utterance(600, 800, "Different question", action="SPEAK")
    timeline.add_audio("assistant", 900, 1_100, True)
    ticks = build_ticks(timeline, 200, 24_000, duration_ms=1_200)

    metrics = compute_interaction_metrics(ticks, tick_ms=200, timeline=timeline)
    turns = compute_turn_interaction_metrics(ticks, timeline)

    assert metrics["response_rate"] == 0.5
    assert metrics["counts"]["no_response_count"] == 1
    assert turns[0]["audio"].get("response_status") == "missed"
    assert turns[0]["audio"].get("response_reason") == "next_eligible_request"
    assert turns[1]["audio"]["response_latency_ms"] == 100


@pytest.mark.parametrize("tick_ms", [20, 200])
def test_contiguous_caller_utterances_remain_distinct_response_opportunities(tick_ms: int) -> None:
    timeline = Timeline()
    timeline.add_audio("user", 0, 400, True)
    timeline.add_user_utterance(0, 200, "First question", action="OPENING")
    timeline.add_user_utterance(200, 400, "Different question", action="SPEAK")
    timeline.add_audio("assistant", 500, 600, True)
    ticks = build_ticks(timeline, tick_ms, 24_000, duration_ms=800)

    metrics = compute_interaction_metrics(ticks, tick_ms=tick_ms, timeline=timeline)
    turns = compute_turn_interaction_metrics(ticks, timeline)

    assert [(turn["start_ms"], turn["end_ms"]) for turn in turns] == [(0, 200), (200, 400)]
    assert metrics["response_rate"] == 0.5
    assert metrics["counts"]["response_total"] == 2
    assert [turn["audio"]["response_status"] for turn in turns] == ["missed", "answered"]


def test_pending_delegated_work_does_not_erase_a_matured_response_opportunity() -> None:
    timeline = Timeline()
    timeline.add_audio("user", 0, 200, True)
    timeline.add_user_utterance(0, 200, "Book a table", action="OPENING")
    timeline.apply_event(
        {
            "type": "session.delegation.created",
            "offset_ms": 300,
            "delegation": {"target": "responses", "response_id": "pending"},
        }
    )
    ticks = build_ticks(timeline, 200, 24_000, duration_ms=6_000)

    metrics = compute_interaction_metrics(ticks, tick_ms=200, timeline=timeline)
    turn = compute_turn_interaction_metrics(ticks, timeline)[0]

    assert metrics["response_rate"] == 0.0
    assert metrics["counts"]["no_response_count"] == 1
    assert turn["audio"].get("response_reason") == "deadline_expired"


@pytest.mark.parametrize("tick_ms", [20, 200])
@pytest.mark.parametrize("offset_ms", [0, 100])
@pytest.mark.parametrize("start_ms, end_ms, expected_silence_ms", [(150, 450, 300), (250, 550, 300), (150, 190, 40)])
def test_delegation_silence_uses_exact_intervals_instead_of_tick_final_state(
    tick_ms: int, offset_ms: int, start_ms: int, end_ms: int, expected_silence_ms: int
) -> None:
    timeline = Timeline()
    timeline.apply_event(
        {
            "type": "session.delegation.created",
            "offset_ms": start_ms + offset_ms,
            "delegation": {"target": "responses", "response_id": "work"},
        }
    )
    timeline.apply_event({"type": "response.completed", "offset_ms": end_ms + offset_ms, "response": {"id": "work"}})
    ticks = build_ticks(timeline, tick_ms, 24_000, duration_ms=1_000 + offset_ms)

    for observed_timeline in (timeline, None):
        metrics = compute_interaction_metrics(ticks, tick_ms=tick_ms, timeline=observed_timeline)

        assert metrics["floor_hold_silence_ms"] == {"cumulative": expected_silence_ms, "maximum": expected_silence_ms}
        assert metrics["floor_hold_intervals_ms"] == [[start_ms + offset_ms, end_ms + offset_ms]]
        assert metrics.get("delegation_timing_source") == (
            "lifecycle_events" if observed_timeline is not None else "exact_tick_intervals"
        )
    assert sum(tick["interaction"].get("delegation_active_ms", 0) for tick in ticks) == expected_silence_ms


@pytest.mark.parametrize("tick_ms", [20, 200])
@pytest.mark.parametrize("offset_ms", [0, 100])
def test_delegation_silence_subtracts_the_union_of_both_voiced_tracks(tick_ms: int, offset_ms: int) -> None:
    timeline = Timeline()
    timeline.apply_event(
        {
            "type": "session.delegation.created",
            "offset_ms": 150 + offset_ms,
            "delegation": {"target": "responses", "response_id": "work"},
        }
    )
    timeline.apply_event({"type": "response.completed", "offset_ms": 550 + offset_ms, "response": {"id": "work"}})
    timeline.add_audio("assistant", 100 + offset_ms, 200 + offset_ms, True)
    timeline.add_audio("assistant", 350 + offset_ms, 400 + offset_ms, True)
    timeline.add_audio("user", 300 + offset_ms, 370 + offset_ms, True)
    ticks = build_ticks(timeline, tick_ms, 24_000, duration_ms=800 + offset_ms)

    metrics = compute_interaction_metrics(ticks, tick_ms=tick_ms, timeline=timeline)

    assert metrics["floor_hold_silence_ms"] == {"cumulative": 250, "maximum": 150}
    assert metrics["floor_hold_intervals_ms"] == [
        [200 + offset_ms, 300 + offset_ms],
        [400 + offset_ms, 550 + offset_ms],
    ]


@pytest.mark.parametrize("with_empty_timeline", [False, True])
def test_legacy_tick_only_delegation_reconstruction_is_explicitly_labeled(with_empty_timeline: bool) -> None:
    timeline = Timeline()
    timeline.add_audio("user", 250, 270, True)
    timeline.add_audio("assistant", 280, 290, True)
    ticks = build_ticks(timeline, 200, 24_000, duration_ms=600)
    for tick in ticks:
        tick["interaction"].pop("delegation_intervals_ms", None)
        tick["interaction"].pop("delegation_active_ms", None)
        tick["interaction"]["delegation_active"] = tick["tick"] == 1

    metrics = compute_interaction_metrics(ticks, tick_ms=200, timeline=Timeline() if with_empty_timeline else None)

    assert metrics["floor_hold_silence_ms"] == {"cumulative": 170, "maximum": 110}
    assert metrics.get("delegation_timing_source") == "legacy_tick_projection"


def test_transcript_only_backchannel_cannot_fabricate_yield_or_overlap() -> None:
    timeline = Timeline()
    timeline.add_user_utterance(200, 300, "Mm-hmm", action="BACKCHANNEL")
    timeline.add_audio("assistant", 100, 500, True)

    metrics = compute_interaction_metrics(
        build_ticks(timeline, 20, 24_000, duration_ms=500), tick_ms=20, timeline=timeline
    )

    assert timeline.overlap_ms == 0
    assert metrics["yield_latency_mean"] is None
    assert metrics["yield_rate"] is None
    assert metrics["selectivity_backchannel"] is None
    assert metrics["counts"]["backchannel_total"] == 0


def test_backchannel_does_not_penalize_natural_assistant_sentence_completion() -> None:
    timeline = Timeline()
    timeline.add_user_utterance(0, 200, "Book a table", action="OPENING")
    timeline.add_audio("user", 0, 200, True)
    timeline.add_audio("assistant", 400, 900, True)
    timeline.add_user_utterance(700, 850, "Right", action="BACKCHANNEL")
    timeline.add_audio("user", 700, 850, True)
    ticks = build_ticks(timeline, 20, 24_000, duration_ms=900)

    metrics = compute_interaction_metrics(ticks, tick_ms=20, timeline=timeline)
    turns = compute_turn_interaction_metrics(ticks, timeline)

    assert metrics["selectivity_backchannel"] == 1.0
    assert metrics["counts"]["backchannel_correct_count"] == 1
    assert metrics["counts"]["backchannel_error_count"] == 0
    assert turns[-1]["audio"]["backchannel_outcome"] == "continued"
    assert any(event["type"] == "backchannel_correct" for event in extract_interaction_events(turns))


def test_backchannel_penalizes_assistant_that_stops_before_acknowledgement_ends() -> None:
    timeline = Timeline()
    timeline.add_user_utterance(0, 200, "Book a table", action="OPENING")
    timeline.add_audio("user", 0, 200, True)
    timeline.add_audio("assistant", 400, 740, True)
    timeline.add_user_utterance(700, 900, "Right", action="BACKCHANNEL")
    timeline.add_audio("user", 700, 900, True)
    ticks = build_ticks(timeline, 20, 24_000, duration_ms=900)

    metrics = compute_interaction_metrics(ticks, tick_ms=20, timeline=timeline)
    turns = compute_turn_interaction_metrics(ticks, timeline)

    assert metrics["selectivity_backchannel"] == 0.0
    assert metrics["counts"]["backchannel_correct_count"] == 0
    assert metrics["counts"]["backchannel_error_count"] == 1
    assert turns[-1]["audio"]["backchannel_outcome"] == "false_yield"
    assert any(event["type"] == "backchannel_error" for event in extract_interaction_events(turns))


def test_interaction_event_evidence_uses_observed_response_and_yield_boundaries() -> None:
    timeline = Timeline()
    timeline.add_user_utterance(0, 200, "Book a table", action="OPENING")
    timeline.add_audio("user", 0, 200, True)
    timeline.add_audio("assistant", 400, 1_000, True)
    timeline.add_user_utterance(600, 1_100, "Actually, tomorrow", action="INTERRUPT")
    timeline.add_audio("user", 600, 1_100, True)
    timeline.add_audio("assistant", 1_400, 1_600, True)
    ticks = build_ticks(timeline, 20, 24_000, duration_ms=1_600)

    events = extract_interaction_events(compute_turn_interaction_metrics(ticks, timeline))

    assert {"type": "response", "caller_end_ms": 200, "assistant_start_ms": 400, "latency_ms": 200} in events
    assert {
        "type": "yield",
        "caller_interruption_ms": 600,
        "assistant_stop_ms": 1_000,
        "latency_ms": 400,
    } in events
    assert {"type": "response", "caller_end_ms": 1_100, "assistant_start_ms": 1_400, "latency_ms": 300} in events


def test_interaction_event_evidence_cannot_be_created_from_transcript_only() -> None:
    timeline = Timeline()
    timeline.add_user_utterance(0, 200, "Book a table", action="OPENING")
    timeline.add_transcript("assistant", 300, 500, "Certainly", "session.output_transcript.delta")

    events = extract_interaction_events(
        compute_turn_interaction_metrics(build_ticks(timeline, 20, 24_000, duration_ms=500), timeline)
    )

    assert events == []


def test_assistant_usage_is_source_separated() -> None:
    frontend = TokenUsage.from_mapping(
        {
            "input_tokens": 70,
            "output_tokens": 30,
            "input_token_details": {"audio_tokens": 45, "cached_tokens": 12},
        }
    )
    backend = TokenUsage.from_mapping(
        aggregate_backend_usage(
            [
                {
                    "input_tokens": 50,
                    "output_tokens": 20,
                    "input_tokens_details": {"cache_write_tokens": 40, "cached_tokens": 0},
                    "output_tokens_details": {"reasoning_tokens": 8},
                },
                {
                    "input_tokens": 75,
                    "output_tokens": 25,
                    "input_tokens_details": {"cache_write_tokens": 0, "cached_tokens": 40},
                    "output_tokens_details": {"reasoning_tokens": 5},
                },
            ]
        ),
        text_only=True,
    )

    assert frontend.input_audio_tokens == 45
    assert frontend.cached_input_tokens == 12
    assert backend.input_tokens == 125
    assert backend.input_text_tokens == 125
    assert backend.output_tokens == 45
    assert backend.output_text_tokens == 45
    assert backend.cache_write_input_tokens == 40
    assert backend.cached_input_tokens == 40
    assert backend.output_reasoning_tokens == 13


def test_response_latency_ignores_silent_audio() -> None:
    silence = bytes(960)
    speech = (2_500).to_bytes(2, "little", signed=True) * 480

    assert first_speech_offset_ms(silence, start_ms=0, sample_rate_hz=24_000) is None
    assert first_speech_offset_ms(silence + speech, start_ms=100, sample_rate_hz=24_000) == 120


def test_result_names_use_normalized_utc() -> None:
    pacific = timezone(timedelta(hours=-7))
    timestamp = datetime(2026, 7, 28, 10, 26, 49, 123_456, tzinfo=pacific)

    assert build_timestamped_run_name(phase="crawl", offline=False, timestamp=timestamp) == (
        "crawl_live_20260728_172649_123Z"
    )
    assert timestamp.astimezone(UTC).hour == 17


@pytest.mark.parametrize("label", ["../outside", "nested/run", "invalid label"])
def test_result_names_cannot_escape_their_phase_directory(label: str) -> None:
    with pytest.raises(ValueError, match="Run names must use"):
        build_timestamped_run_name(phase="crawl", offline=False, label=label)


@pytest.mark.asyncio
async def test_parallel_restaurant_crawl_preserves_order_and_isolation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    original = crawl_runner.run_single_eval
    active = 0
    peak = 0

    async def track_concurrency(**kwargs: object) -> object:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        try:
            await asyncio.sleep(0.01)
            return await original(**kwargs)
        finally:
            active -= 1

    monkeypatch.setattr(crawl_runner, "run_single_eval", track_concurrency)
    args = parse_args(
        ["--offline", "--no-real-time", "--max-examples", "5", "--concurrency", "3", "--results-dir", str(tmp_path)]
    )
    run_dir = await run_evals(args)
    report = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    rows = report["results"]
    output = capsys.readouterr().out

    assert 1 < peak <= 3
    assert "Completed 5/5 valid examples; 5 passed; 0 failed; 0 infrastructure failures." in output
    assert f"Results: {run_dir}" in output
    assert "restaurant_001" not in output
    assert "session.input_audio.append" not in output
    assert [row["scenario_id"] for row in rows] == [f"restaurant_{index:03}" for index in range(1, 6)]
    assert len({row["artifacts"]["events"] for row in rows}) == 5
    assert all(row["status"] == "passed" for row in rows)


def test_summary_excludes_infrastructure_failures_from_model_grades(tmp_path: Path) -> None:
    dataset = tmp_path / "data.json"
    dataset.write_text("", encoding="utf-8")
    rows = [
        {"example_id": "passed", "status": "ok", "task_completed": True},
        {
            "example_id": "error",
            "status": "failed",
            "task_completed": False,
            "failure_stage": "transport",
            "error_message": "unavailable",
        },
    ]

    summary = build_results_report(
        module="crawl",
        run_name="summary",
        execution_mode="offline_fixture",
        interaction="single_turn",
        dataset=dataset,
        configuration={},
        rows=rows,
        run_dir=tmp_path,
        scenario_id_key="example_id",
    )["summary"]

    assert summary["total"] == 2
    assert summary["passed"] == 1
    assert summary["infrastructure_errors"] == 1


def test_default_restaurant_dataset_contains_twenty_one_scenarios() -> None:
    examples = load_dataset(DEFAULT_DATA_JSON)

    assert len(examples) == 21
    assert examples[0].id == "restaurant_001"
    assert sum(bool(example.expected.tools.required) for example in examples) == 15


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["crawl", "walk"])
async def test_shutdown_failure_preserves_captured_conversation_audio(phase, monkeypatch, tmp_path):
    import importlib

    from assistants.errors import LiveResponseError

    module = importlib.import_module(f"{phase}_harness.evaluate")
    pcm = (1000).to_bytes(2, "little", signed=True) * 480

    async def collect(_connection, _log, **kwargs):
        kwargs["recorder"].add("assistant", 0, pcm)
        return {"output_audio_bytes": pcm}

    async def fail_close(*args, **kwargs):
        raise LiveResponseError("Missing final provider usage", failure_stage="session_close")

    monkeypatch.setattr(module, "collect_live_response", collect)
    monkeypatch.setattr(module, "close_live_session", fail_close)
    args = module.parse_args(["--offline", "--example", "restaurant_003", "--results-dir", str(tmp_path)])
    run_dir = await module.run_evals(args)
    report = json.loads((run_dir / "results.json").read_text())
    row = report["results"][0]
    assert row["status"] == "infrastructure_error"
    assert row["error"]["stage"] == "session_close"
    with wave.open(str(run_dir / row["artifacts"]["conversation_audio"]), "rb") as recording:
        assert recording.getnchannels() == 2 and recording.getnframes() > 0


@pytest.mark.asyncio
async def test_acknowledgment_guard_keeps_caller_relative_timeout_and_retained_evidence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from assistants.errors import LiveResponseError
    from shared.single_turn import response as response_module

    clock = [0.0]
    fake_time = SimpleNamespace(monotonic=lambda: clock[0])
    monkeypatch.setattr(single_turn_runtime, "time", fake_time)
    monkeypatch.setattr(response_module, "time", fake_time)
    progress = CallerAudioCompletion()
    recorder = ConversationRecorder(24_000)
    timeline = Timeline()
    log = io.StringIO()
    events = iter(
        [
            (2.0, {"type": "session.usage.updated"}),
            (3.0, {"type": "response.created", "response": {"id": "r1"}}),
            (
                4.0,
                {
                    "type": "session.output_audio.delta",
                    "delta": base64.b64encode(array("h", [1000] * (24 * 960)).tobytes()).decode(),
                },
            ),
            (4.24, {"type": "response.output_text.delta", "response_id": "r1", "item_id": "m1", "delta": "What time?"}),
            (4.38, {"type": "response.completed", "response": {"id": "r1"}}),
            (
                4.7,
                {
                    "type": "session.output_transcript.delta",
                    "start_ms": 50_000,
                    "end_ms": 50_960,
                    "delta": "I'll check that for you.",
                },
            ),
            (6.0, None),
            (31.0, {"type": "response.output_text.done", "item_id": "m1", "text": "What time?"}),
            (32.01, None),
        ]
    )

    class Connection:
        async def receive_json(self, *, timeout):  # noqa: ASYNC109
            clock[0], event = next(events)
            progress.timeline_ms = round(clock[0] * 1000)
            if clock[0] == 2.0:
                progress.mark_completed()
            if event is None:
                raise TimeoutError
            return event

        async def send_json(self, event):
            pass

    with pytest.raises(LiveResponseError) as error:
        await collect_live_response(
            Connection(),
            log,
            chunk_ms=20,
            sample_rate_hz=24_000,
            timeout_seconds=30,
            trace_started_at=0,
            event_index_state={"value": 0},
            tool_observer=SlowApplicationTools(),
            caller_audio_completion=progress,
            recorder=recorder,
            timeline=timeline,
        )
    assert error.value.failure_stage == "response_timeout"
    assert clock[0] == 32.01
    assert progress.completed_at == 2.0
    assert timeline.latest_turn("assistant").transcript == "I'll check that for you."
    audio, transcript = recorder.save(tmp_path / "conversation.wav", timeline.evaluation_transcript())
    assert audio.stat().st_size > 44
    assert "I'll check that for you." in transcript.read_text()
    assert "response.output_text.done" in log.getvalue()
