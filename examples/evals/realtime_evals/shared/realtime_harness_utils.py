"""Shared realtime harness helpers for audio streaming and response collection."""

import asyncio
import base64
import json
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional, TextIO

from shared.realtime_utils import ToolCallAccumulator
from shared.trace_utils import build_event_record


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def bytes_per_sample_for_format(audio_format: str) -> int:
    if audio_format == "pcm16":
        return 2
    if audio_format in {"g711_ulaw", "g711_alaw"}:
        # G.711 variants are 8-bit companded audio.
        return 1
    raise ValueError(f"Unsupported audio format: {audio_format}")


def audio_format_config(audio_format: str, sample_rate_hz: int) -> Dict[str, Any]:
    if audio_format == "pcm16":
        return {"type": "audio/pcm", "rate": sample_rate_hz}
    if audio_format == "g711_ulaw":
        return {"type": "audio/pcmu"}
    if audio_format == "g711_alaw":
        return {"type": "audio/pcma"}
    raise ValueError(f"Unsupported audio format: {audio_format}")


def compute_bytes_per_chunk(
    sample_rate_hz: int, chunk_ms: int, bytes_per_sample: int
) -> int:
    # Ensure we always send at least one byte even for tiny chunk sizes.
    computed = int(sample_rate_hz * (chunk_ms / 1000.0) * bytes_per_sample)
    return max(1, computed)


def chunk_audio_bytes(audio_bytes: bytes, bytes_per_chunk: int) -> List[bytes]:
    audio_chunks: List[bytes] = []
    for offset in range(0, len(audio_bytes), bytes_per_chunk):
        audio_chunks.append(audio_bytes[offset : offset + bytes_per_chunk])
    return audio_chunks


def write_pcm16_wav(output_path: Path, pcm_bytes: bytes, sample_rate_hz: int) -> None:
    ensure_dir(output_path.parent)
    with wave.open(str(output_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate_hz)
        wav_file.writeframes(pcm_bytes)


async def stream_audio_to_connection(
    connection: Any,
    audio_bytes: bytes,
    chunk_ms: int,
    sample_rate_hz: int,
    input_audio_format: str,
    real_time: bool,
    minimum_duration_seconds: float = 0.0,
) -> None:
    bytes_per_sample = bytes_per_sample_for_format(input_audio_format)
    minimum_audio_bytes = int(
        sample_rate_hz * minimum_duration_seconds * bytes_per_sample
    )
    if minimum_audio_bytes > 0 and len(audio_bytes) < minimum_audio_bytes:
        # Very short turns can be ignored by the model; pad with silence when requested.
        padding_bytes = minimum_audio_bytes - len(audio_bytes)
        audio_bytes = audio_bytes + (b"\x00" * padding_bytes)

    bytes_per_chunk = compute_bytes_per_chunk(
        sample_rate_hz, chunk_ms, bytes_per_sample
    )
    audio_chunks = chunk_audio_bytes(audio_bytes, bytes_per_chunk)

    await connection.input_audio_buffer.clear()
    for audio_chunk in audio_chunks:
        # Realtime expects base64-encoded audio bytes per append event.
        await connection.input_audio_buffer.append(
            audio=base64.b64encode(audio_chunk).decode("ascii")
        )
        if real_time:
            # Optional: emulate wall-clock streaming instead of sending as fast as possible.
            await asyncio.sleep(chunk_ms / 1000.0)
    # Mark end-of-user-turn (required when `turn_detection` is disabled).
    await connection.input_audio_buffer.commit()


def _next_event_index(event_index_state: Optional[Dict[str, int]]) -> int:
    if event_index_state is None:
        return -1
    # Keep a single monotonically increasing index across interleaved streams.
    event_index_state["value"] = event_index_state["value"] + 1
    return event_index_state["value"]


async def collect_realtime_response(
    connection: Any,
    response_payload: Dict[str, Any],
    log_file: Optional[TextIO] = None,
    event_index_state: Optional[Dict[str, int]] = None,
    source: Optional[str] = None,
    turn_index: Optional[int] = None,
    tool_mocks: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Collect a realtime response and optionally log each event as JSONL."""
    assistant_text_parts: List[str] = []
    output_audio_bytes = bytearray()
    tool_call_accumulator = ToolCallAccumulator()
    # Track tool calls we've already responded to so follow-up responses are clean.
    responded_call_ids: set[str] = set()

    first_audio_time_ms: Optional[float] = None
    first_text_time_ms: Optional[float] = None
    response_done_time_ms: Optional[float] = None
    usage_data: Dict[str, Any] = {}
    awaiting_followup = False

    loop = asyncio.get_running_loop()
    response_start_time = loop.time()
    await connection.response.create(response=response_payload)

    local_event_index = 0
    async for event in connection:
        event_time_ms = (loop.time() - response_start_time) * 1000
        if event_index_state is None:
            # Use a local counter when the caller does not need cross-stream ordering.
            local_event_index += 1
            event_index = local_event_index
        else:
            event_index = _next_event_index(event_index_state)

        if log_file is not None:
            log_entry = build_event_record(
                event,
                event_time_ms=event_time_ms,
                event_index=event_index,
                source=source,
                turn_index=turn_index,
            )
            log_file.write(json.dumps(log_entry))
            log_file.write("\n")

        payload = event.model_dump()
        event_type = payload.get("type", "")

        if event_type == "response.output_audio.delta":
            if first_audio_time_ms is None:
                first_audio_time_ms = event_time_ms
            output_audio_bytes.extend(base64.b64decode(payload.get("delta", "")))

        if event_type == "response.output_audio_transcript.delta":
            if first_text_time_ms is None:
                first_text_time_ms = event_time_ms
            assistant_text_parts.append(payload.get("delta", ""))

        if event_type == "response.output_text.delta":
            if first_text_time_ms is None:
                first_text_time_ms = event_time_ms
            assistant_text_parts.append(payload.get("delta", ""))

        if event_type == "response.done":
            response_done_time_ms = event_time_ms
            tool_call_accumulator.handle_event_payload(payload)
            response = payload.get("response") or {}
            usage_data = response.get("usage") or {}

            tool_calls = tool_call_accumulator.build_tool_calls()
            # Only respond to newly observed tool calls; some calls may repeat in follow-ups.
            pending_tool_calls = [
                call
                for call in tool_calls
                if call.get("call_id") and call.get("call_id") not in responded_call_ids
            ]
            if tool_mocks is not None and pending_tool_calls:
                for call in pending_tool_calls:
                    call_id = call.get("call_id", "")
                    if not call_id:
                        continue
                    tool_name = call.get("name", "")
                    # Provide deterministic mock outputs so multi-turn runs stay comparable.
                    tool_output = tool_mocks.get(
                        tool_name, {"status": "Unsupported tool"}
                    )
                    await connection.conversation.item.create(
                        item={
                            "type": "function_call_output",
                            "call_id": call_id,
                            "output": json.dumps(tool_output),
                        }
                    )
                    responded_call_ids.add(call_id)
                # After providing tool output(s), explicitly request the assistant to continue.
                await connection.response.create()
                awaiting_followup = True
                continue

            if awaiting_followup:
                # This `response.done` corresponds to the post-tool-call follow-up response.
                awaiting_followup = False
            break

    tool_calls = tool_call_accumulator.build_tool_calls()
    return {
        "assistant_text": "".join(assistant_text_parts).strip(),
        "output_audio_bytes": bytes(output_audio_bytes),
        "tool_calls": tool_calls,
        "first_audio_time_ms": first_audio_time_ms,
        "first_text_time_ms": first_text_time_ms,
        "response_done_time_ms": response_done_time_ms,
        "usage": usage_data,
    }
