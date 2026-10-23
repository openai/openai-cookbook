"""Evaluator-owned single-turn audio streaming and observed GPT Live response collection."""

from __future__ import annotations

import asyncio
import base64
import time
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from typing import Any, TextIO

from assistants.errors import LiveResponseError
from assistants.frontend.transport import open_live_websocket
from assistants.runtime import OfflineApplicationBehavior, ToolExecutor
from shared.audio.conversation import ConversationRecorder, LiveMonitor
from shared.audio.pacing import AudioPacer
from shared.audio.pcm import AudioQueue, speech_intervals_pcm16
from shared.metrics.latency import elapsed_ms
from shared.observability.timeline import Timeline, project_agent_event
from shared.observability.trace import record_event
from shared.single_turn.response import ResponseCollector
from shared.testing.live import OfflineLiveConnection


@dataclass(slots=True)
class CallerAudioCompletion:
    """Coordinate one caller recording with its concurrently running receiver."""

    completed: asyncio.Event = field(default_factory=asyncio.Event)
    completed_at: float | None = None
    timeline_ms: int = 0

    def mark_completed(self) -> None:
        self.completed_at = time.monotonic()
        self.completed.set()


@asynccontextmanager
async def open_live_connection(
    *,
    endpoint: str,
    model: str,
    api_key: str,
    timeout_seconds: float,
    offline: bool,
    example_id: str,
    user_text: str,
    input_audio_length: int,
    sample_rate_hz: int,
    offline_behavior: OfflineApplicationBehavior | None = None,
) -> AsyncIterator[Any]:
    """Select the evaluator-owned offline fixture or real assistant transport."""
    if offline:
        connection = OfflineLiveConnection(
            example_id=example_id,
            user_text=user_text,
            input_audio_length=input_audio_length,
            sample_rate_hz=sample_rate_hz,
            application_behavior=offline_behavior,
        )
        try:
            yield connection
        finally:
            await connection.close()
        return

    async with open_live_websocket(
        endpoint=endpoint,
        model=model,
        api_key=api_key,
        timeout_seconds=timeout_seconds,
    ) as connection:
        yield connection


async def wait_for_session_started(
    connection: Any,
    log_file: TextIO,
    *,
    timeout_seconds: float,
    started_at: float,
    event_index_state: dict[str, int],
) -> dict[str, Any]:
    try:
        event = await connection.receive_json(timeout=timeout_seconds)
    except TimeoutError as exc:
        raise LiveResponseError(
            "GPT Live session did not start before the timeout", failure_stage="session_start"
        ) from exc
    if not isinstance(event, dict):
        raise LiveResponseError("GPT Live returned a non-object startup event", failure_stage="session_start")
    record_event(
        log_file,
        event,
        started_at=started_at,
        event_index_state=event_index_state,
        source="live_frontend",
        direction="server_to_client",
    )
    if event.get("type") == "error":
        error = event.get("error", {})
        raise LiveResponseError(
            f"GPT Live session rejected: {error.get('message', 'unknown error')}",
            failure_stage="session_start",
        )
    if event.get("type") != "session.started":
        raise LiveResponseError(
            f"Expected session.started, received {event.get('type', 'unknown')}",
            failure_stage="session_start",
        )
    return event


async def stream_audio_to_connection(
    connection: Any,
    input_audio: bytes,
    chunk_ms: int,
    sample_rate_hz: int,
    real_time: bool,
    *,
    log_file: TextIO,
    started_at: float,
    event_index_state: dict[str, int],
    timeline: Timeline | None = None,
    recorder: ConversationRecorder | None = None,
    audio_monitor: LiveMonitor | None = None,
    caller_audio_completion: CallerAudioCompletion | None = None,
) -> None:
    if not input_audio or len(input_audio) % 2:
        raise LiveResponseError("Caller audio must contain nonempty PCM16 samples", failure_stage="audio_input")
    chunk_bytes = sample_rate_hz * chunk_ms // 1_000 * 2
    if chunk_bytes <= 0 or chunk_bytes % 2:
        raise ValueError("Audio chunk duration must produce a positive, even PCM16 byte count")
    queue = AudioQueue(sample_rate_hz, chunk_ms, "clean", 0)
    queue.enqueue(input_audio)
    pacer = AudioPacer(chunk_ms)
    offset_ms = 0
    while queue.queued_chunks:
        chunk, speaking = queue.next_chunk()
        payload = {"type": "session.input_audio.append", "audio": base64.b64encode(chunk).decode("ascii")}
        await connection.send_json(payload)
        record_event(
            log_file,
            payload,
            started_at=started_at,
            event_index_state=event_index_state,
            source="caller_audio",
            direction="client_to_server",
        )
        if recorder is not None:
            recorder.add("user", offset_ms, chunk)
        if audio_monitor is not None:
            audio_monitor.push("user", chunk, start_ms=offset_ms)
        if timeline is not None:
            intervals = speech_intervals_pcm16(chunk, offset_ms, sample_rate_hz, 220.0) if speaking else []
            timeline.add_audio(
                "user",
                offset_ms,
                offset_ms + chunk_ms,
                speaking,
                speech_intervals=intervals,
            )
        offset_ms += chunk_ms
        if caller_audio_completion is not None:
            caller_audio_completion.timeline_ms = offset_ms
        if real_time:
            delay, lag_ms = pacer.next_delay()
            if lag_ms is not None:
                record_event(
                    log_file,
                    {"type": "audio.pacing_lag", "lag_ms": lag_ms, "chunk_ms": chunk_ms, "stream": "speech"},
                    started_at=started_at,
                    event_index_state=event_index_state,
                    source="caller_audio",
                    direction="internal",
                )
            await asyncio.sleep(delay)
        else:
            await asyncio.sleep(0)
    if caller_audio_completion is not None:
        caller_audio_completion.mark_completed()


async def _continue_audio_clock(
    connection: Any,
    *,
    chunk_ms: int,
    sample_rate_hz: int,
    log_file: TextIO,
    started_at: float,
    event_index_state: dict[str, int],
    caller_audio_completion: CallerAudioCompletion | None = None,
) -> None:
    if caller_audio_completion is not None:
        await caller_audio_completion.completed.wait()
    queue = AudioQueue(sample_rate_hz, chunk_ms, "clean", 0)
    pacer = AudioPacer(chunk_ms)
    while True:
        silence, _ = queue.next_chunk()
        payload = {"type": "session.input_audio.append", "audio": base64.b64encode(silence).decode("ascii")}
        await connection.send_json(payload)
        if caller_audio_completion is not None:
            caller_audio_completion.timeline_ms += chunk_ms
        record_event(
            log_file,
            {"type": "session.input_audio.append", "audio_bytes": len(silence), "audio_kind": "silence"},
            started_at=started_at,
            event_index_state=event_index_state,
            source="caller_audio",
            direction="client_to_server",
        )
        delay, lag_ms = pacer.next_delay()
        if lag_ms is not None:
            record_event(
                log_file,
                {"type": "audio.pacing_lag", "lag_ms": lag_ms, "chunk_ms": chunk_ms, "stream": "silence"},
                started_at=started_at,
                event_index_state=event_index_state,
                source="caller_audio",
                direction="internal",
            )
        await asyncio.sleep(delay)


def _response_source(event: Mapping[str, Any]) -> str:
    kind = str(event.get("type", ""))
    if kind.startswith("response."):
        return "delegated_responses"
    if kind.startswith("client_delegation."):
        return "client_assistant"
    return "live_frontend"


async def collect_live_response(
    connection: Any,
    log_file: TextIO,
    *,
    chunk_ms: int,
    sample_rate_hz: int,
    timeout_seconds: float,
    trace_started_at: float,
    event_index_state: dict[str, int],
    tool_observer: ToolExecutor,
    timeline: Timeline | None = None,
    recorder: ConversationRecorder | None = None,
    audio_monitor: LiveMonitor | None = None,
    tool_source: str = "application",
    caller_audio_completion: CallerAudioCompletion | None = None,
) -> dict[str, Any]:
    """Receive one response; protocol state stays independent of transport ownership."""
    collector = ResponseCollector(
        chunk_ms=chunk_ms,
        sample_rate_hz=sample_rate_hz,
        tool_observer=tool_observer,
        timeline=timeline,
        recorder=recorder,
        audio_monitor=audio_monitor,
        caller_audio_completion=caller_audio_completion,
    )
    deadline = collector.response_started_at + timeout_seconds
    caller_deadline_set = caller_audio_completion is None
    silence_sender = asyncio.create_task(
        _continue_audio_clock(
            connection,
            chunk_ms=chunk_ms,
            sample_rate_hz=sample_rate_hz,
            log_file=log_file,
            started_at=trace_started_at,
            event_index_state=event_index_state,
            caller_audio_completion=caller_audio_completion,
        ),
        name="live-audio-clock",
    )
    try:
        while time.monotonic() < deadline:
            if (
                not caller_deadline_set
                and caller_audio_completion is not None
                and caller_audio_completion.completed_at is not None
            ):
                deadline = caller_audio_completion.completed_at + timeout_seconds
                caller_deadline_set = True
            if silence_sender.done():
                await silence_sender
            wait_seconds = min(0.05, max(0.001, deadline - time.monotonic()))
            try:
                event = await connection.receive_json(timeout=wait_seconds)
            except TimeoutError:
                event = None
            else:
                if not isinstance(event, dict):
                    raise LiveResponseError("GPT Live returned a non-object event", failure_stage="response_collection")
                event = project_agent_event(event, collector.timeline_clock_ms())
                application_event = event.get("type") in {"tool.called", "tool.completed", "tool.failed"}
                record_event(
                    log_file,
                    event,
                    started_at=trace_started_at,
                    event_index_state=event_index_state,
                    source=tool_source if application_event else _response_source(event),
                    direction="application_internal" if application_event else "server_to_client",
                )
                if collector.observe(event, elapsed_ms(collector.response_started_at)):
                    continue
            if collector.is_complete(pending_tools=bool(getattr(connection, "pending_tools", False))):
                return collector.result(elapsed_ms(collector.response_started_at))
        raise LiveResponseError(
            "GPT Live did not complete one assistant turn before the timeout", failure_stage="response_timeout"
        )
    finally:
        silence_sender.cancel()
        with suppress(asyncio.CancelledError):
            await silence_sender


async def close_live_session(
    connection: Any,
    log_file: TextIO,
    *,
    trace_started_at: float,
    event_index_state: dict[str, int],
    timeout_seconds: float = 10.0,
    timeline: Timeline | None = None,
) -> dict[str, Any]:
    payload = {"type": "session.close", "event_id": "event_client_close"}
    await connection.send_json(payload)
    record_event(
        log_file,
        payload,
        started_at=trace_started_at,
        event_index_state=event_index_state,
        source="live_frontend",
        direction="client_to_server",
    )
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            event = await connection.receive_json(timeout=max(0.001, deadline - time.monotonic()))
        except TimeoutError as exc:
            raise LiveResponseError("GPT Live did not emit session.closed", failure_stage="session_close") from exc
        if not isinstance(event, dict):
            continue
        record_event(
            log_file,
            event,
            started_at=trace_started_at,
            event_index_state=event_index_state,
            source=_response_source(event),
            direction="server_to_client",
        )
        if timeline is not None:
            timeline.apply_event(event)
        if event.get("type") == "session.closed":
            usage = event.get("usage")
            if (
                event.get("_synthetic")
                or not isinstance(usage, dict)
                or not isinstance(usage.get("seconds"), (int, float))
            ):
                raise LiveResponseError("session.closed omitted final frontend usage", failure_stage="frontend_usage")
            return usage
        if event.get("type") == "error":
            error = event.get("error", {})
            message = (
                error.get("message", "GPT Live failed during session close") if isinstance(error, dict) else str(error)
            )
            raise LiveResponseError(message, failure_stage="session_close")
    raise LiveResponseError("GPT Live did not close within the shutdown timeout", failure_stage="session_close")
