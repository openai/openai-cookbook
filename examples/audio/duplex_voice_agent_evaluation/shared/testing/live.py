"""Explicit offline GPT Live protocol fixtures, never evidence of model quality."""

from __future__ import annotations

import asyncio
import base64
import json
from typing import Any

from assistants.frontend.transport import DEFAULT_SAMPLE_RATE_HZ
from assistants.runtime import OfflineApplicationBehavior
from shared.audio.pcm import tone_for_text


def offline_tone_for_text(text: str, sample_rate_hz: int = DEFAULT_SAMPLE_RATE_HZ) -> bytes:
    """Expose the directly copied source audio fixture under its existing API."""
    return tone_for_text(text, sample_rate_hz)


class OfflineLiveConnection:
    """Explicitly labeled protocol fixture; never evidence of live model quality."""

    def __init__(
        self,
        *,
        example_id: str,
        user_text: str,
        input_audio_length: int,
        sample_rate_hz: int,
        application_behavior: OfflineApplicationBehavior | None = None,
    ) -> None:
        self.example_id = example_id
        self.user_text = user_text
        self.input_audio_length = input_audio_length
        self.sample_rate_hz = sample_rate_hz
        self.application_behavior = application_behavior
        self.events: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.received_audio_bytes = 0
        self.started_response = False
        self.closed = False
        self.model = ""
        self.backend_model = ""
        self.response_id = f"resp_offline_{example_id}"
        self.followup_response_id = f"{self.response_id}_followup"
        self.call_id = f"call_offline_{example_id}"
        self.assistant_parts: list[str] = []
        self.output_audio_tokens = 0
        self._outputs: dict[str, str] = {}
        self._continued = False
        self._event_index = 0
        self.assistant_audio_start_ms: int | None = None
        self.assistant_audio_end_ms: int | None = None

    async def send_json(self, payload: dict[str, Any]) -> None:
        kind = payload.get("type")
        if kind == "session.start":
            session = payload.get("session", {})
            if not session.get("model") or "initial_items" in session:
                raise ValueError("Invalid v3 startup configuration")
            self.model = session["model"]
            self.backend_model = str(session.get("delegation", {}).get("responses", {}).get("model", ""))
            await self._emit_event({"type": "session.started", "session": {"id": f"sess_offline_{self.example_id}"}})
            return
        if kind == "session.input_audio.append":
            encoded = payload.get("audio", "")
            if not isinstance(encoded, str):
                raise ValueError("offline audio payload must be base64-encoded PCM")
            self.received_audio_bytes += len(base64.b64decode(encoded, validate=True))
            if not self.started_response and self.received_audio_bytes >= self.input_audio_length:
                self.started_response = True
                await self._begin_response()
            return
        if kind == "response.item.create":
            item = payload["item"]
            if item.get("call_id") != self.call_id or self.call_id in self._outputs:
                raise ValueError("Unknown or duplicate function output")
            self._outputs[self.call_id] = item["output"]
            return
        if kind == "response.create":
            if self.call_id not in self._outputs or self._continued:
                raise ValueError("A complete, uncontinued function batch is required")
            self._continued = True
            output = json.loads(self._outputs[self.call_id])
            if self.application_behavior is None:
                raise RuntimeError("Offline Live evaluation requires application-owned behavior")
            final_answer = self.application_behavior.final_answer(output)
            message_id = f"message_offline_{self.example_id}"
            await self._emit_event(
                {
                    "type": "response.created",
                    "response": {
                        "id": self.followup_response_id,
                        "status": "in_progress",
                        "model": self.backend_model,
                    },
                }
            )
            await self._emit_event(
                {
                    "type": "response.output_text.done",
                    "response_id": self.followup_response_id,
                    "item_id": message_id,
                    "output_index": 0,
                    "text": final_answer,
                }
            )
            await self._emit_event(
                {
                    "type": "response.output_item.done",
                    "response_id": self.followup_response_id,
                    "item": {
                        "id": message_id,
                        "type": "message",
                        "status": "completed",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": final_answer}],
                    },
                    "output_index": 0,
                }
            )
            await self._emit_event(
                {
                    "type": "response.completed",
                    "response": {
                        "id": self.followup_response_id,
                        "status": "completed",
                        "usage": {
                            "total_tokens": 52,
                            "input_tokens": 36,
                            "output_tokens": 16,
                            "input_tokens_details": {"cached_tokens": 0},
                        },
                    },
                }
            )
            await self._emit_assistant(final_answer, final=True)
            return
        if kind == "session.close":
            await self._emit_event(
                {
                    "type": "session.closed",
                    "reason": "client_request",
                    "session": {"id": f"sess_offline_{self.example_id}"},
                    "usage": {"seconds": self.received_audio_bytes / (self.sample_rate_hz * 2)},
                }
            )
            return
        raise ValueError(f"Unsupported offline Live event: {kind}")

    async def _emit_event(self, event: dict[str, Any]) -> None:
        self._event_index += 1
        if event["type"].startswith("response."):
            if isinstance(event.get("response"), dict):
                event["response"]["output"] = []
            event = {"type": "response.event", "delegation_id": f"delegation_offline_{self.example_id}", "event": event}
        if event["type"] == "session.delegation.created":
            event.pop("offset_ms", None)
        if event["type"] == "session.output_audio.delta":
            event.pop("start_ms", None)
            event.pop("end_ms", None)
        await self.events.put({"event_id": f"offline_{self.example_id}_{self._event_index}", **event})

    async def receive_json(self, *, timeout: float | None = None) -> dict[str, Any]:  # noqa: ASYNC109
        if timeout is None:
            return await self.events.get()
        return await asyncio.wait_for(self.events.get(), timeout)

    async def close(self) -> None:
        self.closed = True

    async def _begin_response(self) -> None:
        audio_ms = round(self.input_audio_length / (self.sample_rate_hz * 2) * 1_000)
        await self._emit_event(
            {
                "type": "session.input_transcript.delta",
                "start_ms": 0,
                "end_ms": audio_ms,
                "delta": self.user_text,
            }
        )
        if self.application_behavior is None:
            raise RuntimeError("Offline Live evaluation requires application-owned behavior")
        inferred = self.application_behavior.infer_tool_call(self.user_text)
        if inferred is None:
            answer = self.application_behavior.direct_answer(self.user_text)
            await self._emit_assistant(answer, final=True)
            return

        name, arguments = inferred
        await self._emit_event(
            {
                "type": "session.delegation.created",
                "offset_ms": audio_ms + 40,
                "delegation": {
                    "id": f"delegation_offline_{self.example_id}",
                    "type": "delegation",
                    "target": "responses",
                    "response_id": self.response_id,
                },
            }
        )
        await self._emit_event(
            {
                "type": "response.created",
                "response": {"id": self.response_id, "status": "in_progress", "model": self.backend_model},
            }
        )
        await self._emit_assistant("One moment while I take care of that.", final=False)
        item_id = f"function_offline_{self.example_id}"
        await self._emit_event(
            {
                "type": "response.output_item.added",
                "item": {
                    "id": item_id,
                    "type": "function_call",
                    "status": "in_progress",
                    "arguments": "",
                    "call_id": self.call_id,
                    "name": name,
                },
                "output_index": 1,
            }
        )
        await self._emit_event(
            {
                "type": "response.function_call_arguments.done",
                "item_id": item_id,
                "output_index": 1,
                "arguments": json.dumps(arguments, ensure_ascii=False),
            }
        )
        await self._emit_event(
            {
                "type": "response.output_item.done",
                "response_id": self.response_id,
                "item": {
                    "id": item_id,
                    "type": "function_call",
                    "status": "completed",
                    "arguments": json.dumps(arguments, ensure_ascii=False),
                    "call_id": self.call_id,
                    "name": name,
                },
                "output_index": 1,
            }
        )
        await self._emit_event(
            {
                "type": "response.completed",
                "response": {"id": self.response_id, "status": "completed"},
            }
        )

    async def _emit_assistant(self, text: str, *, final: bool) -> None:
        start_ms = round(self.input_audio_length / (self.sample_rate_hz * 2) * 1_000) + 100
        # The fixture's returned answer has a distinct speech/caption boundary.
        # Blended acknowledgment/answer groups intentionally cannot complete.
        gap_ms = 600 if self.assistant_audio_end_ms is not None else 0
        if self.assistant_audio_end_ms is not None:
            start_ms = self.assistant_audio_end_ms + gap_ms
        pcm = offline_tone_for_text(text, self.sample_rate_hz)
        duration_ms = round(len(pcm) / (self.sample_rate_hz * 2) * 1_000)
        if self.assistant_audio_start_ms is None:
            self.assistant_audio_start_ms = start_ms
        self.assistant_audio_end_ms = start_ms + duration_ms
        self.assistant_parts.append(text)
        self.output_audio_tokens += max(1, len(pcm) // 1_920)
        await self._emit_event(
            {
                "type": "session.output_transcript.delta",
                "start_ms": start_ms,
                "end_ms": start_ms + duration_ms,
                "delta": (" " if len(self.assistant_parts) > 1 else "") + text,
            }
        )
        await self._emit_event(
            {
                "type": "session.output_audio.delta",
                "start_ms": start_ms,
                "end_ms": start_ms + duration_ms,
                "delta": base64.b64encode(bytes(gap_ms * self.sample_rate_hz * 2 // 1_000) + pcm).decode("ascii"),
            }
        )
