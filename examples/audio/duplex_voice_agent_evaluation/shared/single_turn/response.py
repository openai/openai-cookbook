"""Observe a single Live response without owning a harness or transport lifecycle."""

from __future__ import annotations

import base64
import copy
import json
import time
from typing import TYPE_CHECKING, Any

from assistants.errors import LiveResponseError
from assistants.runtime import ToolExecutor
from shared.audio.conversation import ConversationRecorder, LiveMonitor
from shared.audio.pcm import speech_intervals_pcm16
from shared.metrics.latency import first_speech_offset_ms
from shared.metrics.tokens import aggregate_backend_usage
from shared.observability.timeline import Timeline, Turn

if TYPE_CHECKING:
    from shared.single_turn.runtime import CallerAudioCompletion


def _decode_arguments(value: Any) -> tuple[dict[str, Any], str]:
    if isinstance(value, dict):
        return value, json.dumps(value, ensure_ascii=False)
    if not isinstance(value, str):
        return {}, ""
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}, value
    return (parsed if isinstance(parsed, dict) else {}), value


class ResponseCollector:
    """Keep protocol evidence and completion state in one per-response object."""

    def __init__(
        self,
        *,
        chunk_ms: int,
        sample_rate_hz: int,
        tool_observer: ToolExecutor,
        timeline: Timeline | None = None,
        recorder: ConversationRecorder | None = None,
        audio_monitor: LiveMonitor | None = None,
        caller_audio_completion: CallerAudioCompletion | None = None,
    ) -> None:
        self.sample_rate_hz = sample_rate_hz
        self.tool_observer = tool_observer
        self.recorder = recorder
        self.audio_monitor = audio_monitor
        self.caller_audio_completion = caller_audio_completion
        self.event_timeline = timeline if timeline is not None else Timeline()
        self._project_user_utterances = not self.event_timeline.user_utterances
        self.response_started_at = time.monotonic()
        self.assistant_fragments: list[dict[str, Any]] = []
        self.post_tool_assistant_fragments: list[dict[str, Any]] = []
        self.input_fragments: list[dict[str, Any]] = []
        self.backend_messages: list[dict[str, Any]] = []
        self.backend_message_ids: set[str] = set()
        self.backend_usages: list[dict[str, Any]] = []
        self.first_speech_offset: float | None = None
        self.first_text_offset: float | None = None
        self.turns: list[dict[str, Any]] = []
        self.delegations: list[dict[str, Any]] = []
        self.tool_calls: list[dict[str, Any]] = []
        self.output_audio = bytearray()
        self.handled_call_ids: set[str] = set()
        self.active_response_ids: set[str] = set()
        self.active_client_delegations: set[str] = set()
        self.current_response_id = ""
        self.first_audio_ms: float | None = None
        self.first_text_ms: float | None = None
        self.first_delegation_ms: float | None = None
        self.first_tool_call_ms: float | None = None
        self.first_tool_completed_ms: float | None = None
        self.backend_completed_ms: float | None = None
        self._output_end_sample = 0
        self._backend_usage_ids: set[str] = set()
        self._completed_response_ids: set[str] = set()
        self._response_owners: dict[str, str] = {}
        self._message_response_ids: dict[str, str] = {}
        self._tool_response_ids: set[str] = set()
        self._reply_markers: dict[tuple[str, str], tuple[int, set[str]] | None] = {}
        self.last_meaningful_event_at = self.response_started_at
        self.settle_seconds = max(0.6, chunk_ms / 1000 * 2)

    def timeline_clock_ms(self) -> int:
        if self.caller_audio_completion is not None:
            return self.caller_audio_completion.timeline_ms
        return max(0, round((time.monotonic() - self.response_started_at) * 1_000))

    def is_complete(self, *, pending_tools: bool) -> bool:
        now_ms = self.timeline_clock_ms()
        for role in ("user", "assistant"):
            for turn in self.event_timeline.transcript_projection.project(
                role,
                self.event_timeline.speech_intervals(role),
                now_ms=now_ms,
                quiet_ms=round(self.settle_seconds * 1_000),
            ):
                self.event_timeline.add_turn(turn)
                if role == "user" and self._project_user_utterances:
                    self.event_timeline.add_user_utterance(
                        turn.start_ms,
                        turn.end_ms,
                        turn.transcript,
                        source="local_transcript_projection",
                        turn_id=turn.turn_id,
                    )
        self.turns = [
            {
                "id": turn.turn_id,
                "role": turn.role,
                "start_ms": turn.start_ms,
                "end_ms": turn.end_ms,
                "transcript": turn.transcript,
            }
            for turn in self.event_timeline.turns
        ]
        assistant = self.event_timeline.latest_turn("assistant")
        has_spoken_turn = bool(assistant and not self.event_timeline.transcript_projection.pending("assistant"))
        return (
            (self.caller_audio_completion is None or self.caller_audio_completion.completed.is_set())
            and has_spoken_turn
            and not self.active_response_ids
            and not self.active_client_delegations
            and not pending_tools
            and not self.event_timeline.delegation_active
            and self._has_returned_reply(assistant)
            and assistant.end_ms >= self.event_timeline.last_assistant_speech_ms
            # Output can contain an unending silent tail. Queued speech already
            # contributes its future playout endpoint to last_assistant_speech_ms.
            and now_ms >= self.event_timeline.last_assistant_speech_ms + round(self.settle_seconds * 1_000)
            and (not self.tool_calls or bool(self.post_tool_assistant_fragments))
            and time.monotonic() - self.last_meaningful_event_at >= self.settle_seconds
        )

    def _has_returned_reply(self, assistant: Turn | None) -> bool:
        if not self._reply_markers:
            return not (self.delegations or self.tool_calls or self._completed_response_ids)
        # A tool-only final response still needs a continuation with returned
        # text. Earlier answers cannot satisfy that new work.
        latest = next(reversed(self._reply_markers))
        if latest[0] == "response" and latest[1] in self._tool_response_ids:
            return False
        for (kind, identifier), marker in self._reply_markers.items():
            if kind == "response" and identifier in self._tool_response_ids:
                continue
            if marker is None or assistant is None:
                return False
            available_ms, excluded_ids = marker
            if assistant.turn_id in excluded_ids or assistant.start_ms <= available_ms:
                return False
        return True

    def _mark_returned_content(self, key: tuple[str, str]) -> None:
        if self._reply_markers.get(key) is not None:
            return
        # Include unprojected captions: later audio or text revisions must not
        # turn an acknowledgment already underway into the returned answer.
        excluded = {group["id"] for group in self.event_timeline.transcript_projection.groups["assistant"]}
        excluded.update(turn.turn_id for turn in self.event_timeline.turns if turn.role == "assistant")
        self._reply_markers[key] = (self.timeline_clock_ms(), excluded)

    def _response_id(self, event: dict[str, Any], item_id: str = "") -> str:
        response = event.get("response", {})
        explicit = event.get("response_id") or (response.get("id") if isinstance(response, dict) else None)
        owner = self._message_response_ids.get(item_id)
        if explicit and owner and explicit != owner:
            return ""
        identifier = explicit or owner
        delegation = event.get("delegation_id")
        if not identifier:
            candidates = [
                key
                for key in self.active_response_ids
                if not delegation or self._response_owners.get(key) == delegation
            ]
            identifier = candidates[0] if len(candidates) == 1 else ""
        if not isinstance(identifier, str) or not identifier:
            return ""
        known_owner = self._response_owners.get(identifier)
        if delegation and known_owner and known_owner != delegation:
            return ""
        if item_id:
            self._message_response_ids[item_id] = identifier
        return identifier

    def _record_returned_text(self, event: dict[str, Any], item_id: str, text: Any) -> None:
        # Client backend text is not available to Live until its correlated
        # commentary command is sent (or the client completion fallback).
        if event.get("_client_managed") or not isinstance(text, str) or not text.strip():
            return
        if response_id := self._response_id(event, item_id):
            self._mark_returned_content(("response", response_id))

    def _record_tool_response(self, event: dict[str, Any], item_id: str = "") -> None:
        if not event.get("_client_managed") and (response_id := self._response_id(event, item_id)):
            self._reply_markers.setdefault(("response", response_id), None)
            self._tool_response_ids.add(response_id)

    def observe(self, event: dict[str, Any], elapsed: float) -> bool:
        """Apply evidence; return true when an intermediate item must not trigger settling."""
        kind = str(event.get("type", "unknown"))
        if kind != "session.output_audio.delta":
            if kind not in {"session.usage.updated", "evaluation.command.sent"} and not kind.endswith(".appended"):
                self.last_meaningful_event_at = time.monotonic()
            self.event_timeline.apply_event(event)
        handler = self._HANDLERS.get(kind)
        return bool(handler(self, event, elapsed)) if handler is not None else False

    def _on_error(self, event: dict[str, Any], elapsed: float) -> bool | None:
        error = event.get("error", {})
        raise LiveResponseError(
            f"GPT Live returned an error: {error.get('message', 'unknown error')}", failure_stage="response_collection"
        )

    def _on_input_transcript_added(self, event: dict[str, Any], elapsed: float) -> bool | None:
        if self.event_timeline.transcript_projection.record("user", event, received_ms=self.timeline_clock_ms()):
            self.input_fragments.append(event)

    def _on_output_transcript_added(self, event: dict[str, Any], elapsed: float) -> bool | None:
        if not self.event_timeline.transcript_projection.record(
            "assistant", event, received_ms=self.timeline_clock_ms()
        ):
            return None
        self.assistant_fragments.append(event)
        if self.first_tool_completed_ms is not None:
            self.post_tool_assistant_fragments.append(event)
        if self.first_text_offset is None:
            self.first_text_offset = float(self.timeline_clock_ms())
        if self.first_text_ms is None:
            self.first_text_ms = elapsed

    def _on_output_audio_delta(self, event: dict[str, Any], elapsed: float) -> bool | None:
        encoded = event.get("delta", "")
        if not isinstance(encoded, str):
            raise LiveResponseError("GPT Live returned invalid assistant PCM", failure_stage="output_audio")
        try:
            pcm = base64.b64decode(encoded, validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise LiveResponseError("GPT Live returned invalid base64 audio", failure_stage="output_audio") from exc
        if len(pcm) % 2:
            raise LiveResponseError("GPT Live returned incomplete PCM16 samples", failure_stage="output_audio")
        start_sample = max(self._output_end_sample, self.timeline_clock_ms() * self.sample_rate_hz // 1_000)
        gap_samples = start_sample - self._output_end_sample if self.output_audio else 0
        audio_start_ms = start_sample * 1_000 // self.sample_rate_hz
        contiguous = bool(self.output_audio) and gap_samples == 0
        self._output_end_sample = start_sample + len(pcm) // 2
        local_event = {
            **event,
            "start_ms": audio_start_ms,
            "end_ms": self._output_end_sample * 1_000 // self.sample_rate_hz,
        }
        self.output_audio.extend(bytes(gap_samples * 2))
        self.output_audio.extend(pcm)
        if self.recorder is not None:
            self.recorder.add("assistant", audio_start_ms, pcm, start_sample=start_sample)
        if self.audio_monitor is not None:
            self.audio_monitor.push("assistant", pcm, start_ms=None if contiguous else audio_start_ms)
        speech_intervals = speech_intervals_pcm16(pcm, audio_start_ms, self.sample_rate_hz, 220.0)
        if speech_intervals:
            self.last_meaningful_event_at = time.monotonic()
        self.event_timeline.apply_event(
            local_event, assistant_speaking=bool(speech_intervals), speech_intervals=speech_intervals
        )
        if self.first_speech_offset is None:
            self.first_speech_offset = first_speech_offset_ms(
                pcm, start_ms=audio_start_ms, sample_rate_hz=self.sample_rate_hz
            )
        if self.first_audio_ms is None and self.first_speech_offset is not None:
            self.first_audio_ms = elapsed

    def _on_delegation_created(self, event: dict[str, Any], elapsed: float) -> bool | None:
        item = event.get("delegation", {})
        if isinstance(item, dict):
            self.delegations.append(item)
            identifier = item.get("id")
            if item.get("target") == "client" and isinstance(identifier, str) and identifier:
                key = ("client", identifier)
                if key not in self._reply_markers:
                    self._reply_markers[key] = None
                    self.active_client_delegations.add(identifier)
            response_id = item.get("response_id")
            if isinstance(response_id, str) and response_id and response_id not in self._completed_response_ids:
                self.active_response_ids.add(response_id)
        if self.first_delegation_ms is None:
            self.first_delegation_ms = elapsed

    def _on_response_created(self, event: dict[str, Any], elapsed: float) -> bool | None:
        response = event.get("response", {})
        response_id = response.get("id") if isinstance(response, dict) else None
        if isinstance(response_id, str) and response_id:
            if response_id not in self._completed_response_ids:
                self.active_response_ids.add(response_id)
            self.current_response_id = response_id
            self._response_owners.setdefault(response_id, str(event.get("delegation_id") or ""))
            if not event.get("_client_managed"):
                self._reply_markers.setdefault(("response", response_id), None)

    def _on_response_output_item_added(self, event: dict[str, Any], elapsed: float) -> bool | None:
        item = event.get("item", {})
        if isinstance(item, dict):
            item_id = str(item.get("id", ""))
            if item.get("type") == "function_call":
                if not item_id:
                    raise LiveResponseError(
                        "Delegated function item is missing item_id", failure_stage="tool_correlation"
                    )
                self._record_tool_response(event, item_id)
            elif item.get("type") == "message":
                self._response_id(event, item_id)

    def _on_response_output_text_delta(self, event: dict[str, Any], elapsed: float) -> bool | None:
        self._record_returned_text(event, str(event.get("item_id", "")), event.get("delta"))

    def _on_response_output_text_done(self, event: dict[str, Any], elapsed: float) -> bool | None:
        item_id = str(event.get("item_id", ""))
        text = str(event.get("text", "")).strip()
        self._remember_backend_message(event, item_id, text)
        self._record_returned_text(event, item_id, event.get("text"))

    def _remember_backend_message(self, event: dict[str, Any], item_id: str, text: str) -> None:
        if item_id and text and (item_id not in self.backend_message_ids):
            self.backend_message_ids.add(item_id)
            self.backend_messages.append(
                {"item_id": item_id, "response_id": event.get("response_id") or self.current_response_id, "text": text}
            )

    def _on_response_output_item_done(self, event: dict[str, Any], elapsed: float) -> bool | None:
        item = event.get("item", {})
        if not isinstance(item, dict):
            return True
        if item.get("type") == "message":
            item_id = str(item.get("id", ""))
            content = item.get("content", [])
            if isinstance(content, list):
                text = " ".join(
                    str(part.get("text", "")).strip()
                    for part in content
                    if isinstance(part, dict) and part.get("type") == "output_text"
                ).strip()
                self._remember_backend_message(event, item_id, text)
                self._record_returned_text(event, item_id, text)
            return True
        if item.get("type") == "function_call":
            self._record_tool_response(event, str(item.get("id", "")))
        if item.get("type") != "function_call" or item.get("status") != "completed":
            return True
        # The selected assistant executes calls and emits the authoritative tool.* events.

    def _on_tool_called(self, event: dict[str, Any], elapsed: float) -> bool | None:
        call_id = str(event.get("call_id", ""))
        if not call_id:
            raise LiveResponseError("Delegated tool is missing call_id", failure_stage="tool_correlation")
        if call_id not in self.handled_call_ids:
            self._record_tool_response(event)
            self.handled_call_ids.add(call_id)
            arguments, raw_arguments = _decode_arguments(event.get("arguments"))
            self.tool_calls.append(
                {
                    "name": str(event.get("name", "")),
                    "arguments": arguments,
                    "raw_arguments": raw_arguments,
                    "call_id": call_id,
                    "response_id": str(event.get("response_id", "")),
                }
            )
            if self.first_tool_call_ms is None:
                self.first_tool_call_ms = elapsed

    def _on_tool_completed(self, event: dict[str, Any], elapsed: float) -> bool | None:
        self.post_tool_assistant_fragments.clear()
        if self.first_tool_completed_ms is None:
            self.first_tool_completed_ms = elapsed

    def _on_client_delegation_completed(self, event: dict[str, Any], elapsed: float) -> bool | None:
        identifier = event.get("delegation_id")
        if isinstance(identifier, str):
            text = event.get("text")
            if ("client", identifier) in self._reply_markers and isinstance(text, str) and text.strip():
                self._mark_returned_content(("client", identifier))
            self.active_client_delegations.discard(identifier)

    def _on_command_sent(self, event: dict[str, Any], elapsed: float) -> bool | None:
        identifier = event.get("delegation_id")
        if (
            event.get("command_type") == "session.commentary.append"
            and isinstance(identifier, str)
            and ("client", identifier) in self._reply_markers
        ):
            self._mark_returned_content(("client", identifier))

    def _on_response_completed(self, event: dict[str, Any], elapsed: float) -> bool | None:
        response = event.get("response", {})
        if isinstance(response, dict):
            response_id = response.get("id")
            if not event.get("_client_managed"):
                if isinstance(response_id, str) and response_id:
                    self._reply_markers.setdefault(("response", response_id), None)
                for item in response.get("output", []):
                    if isinstance(item, dict) and item.get("type") == "function_call":
                        self._record_tool_response(event, str(item.get("id", "")))
            if isinstance(response_id, str):
                self.active_response_ids.discard(response_id)
            if isinstance(response.get("usage"), dict) and response_id not in self._backend_usage_ids:
                self._backend_usage_ids.add(response_id)
                self.backend_usages.append(response["usage"])
            if response_id in self._completed_response_ids:
                return None
            if isinstance(response_id, str):
                self._completed_response_ids.add(response_id)
        self.backend_completed_ms = elapsed

    def _on_response_failed(self, event: dict[str, Any], elapsed: float) -> bool | None:
        response = event.get("response", {})
        error = response.get("error", {}) if isinstance(response, dict) else {}
        message = error.get("message", "delegated Responses backend failed") if isinstance(error, dict) else str(error)
        raise LiveResponseError(message, failure_stage="delegated_response")

    def _on_session_closed(self, event: dict[str, Any], elapsed: float) -> bool | None:
        raise LiveResponseError("GPT Live session closed before the turn completed", failure_stage="session_close")

    _HANDLERS = {
        "error": _on_error,
        "session.input_transcript.delta": _on_input_transcript_added,
        "session.output_transcript.delta": _on_output_transcript_added,
        "session.output_audio.delta": _on_output_audio_delta,
        "session.delegation.created": _on_delegation_created,
        "response.created": _on_response_created,
        "response.output_item.added": _on_response_output_item_added,
        "response.output_text.delta": _on_response_output_text_delta,
        "response.output_text.done": _on_response_output_text_done,
        "response.output_item.done": _on_response_output_item_done,
        "tool.called": _on_tool_called,
        "tool.completed": _on_tool_completed,
        "tool.failed": _on_tool_completed,
        "client_delegation.completed": _on_client_delegation_completed,
        "evaluation.command.sent": _on_command_sent,
        "response.completed": _on_response_completed,
        "response.done": _on_response_completed,
        "response.failed": _on_response_failed,
        "response.incomplete": _on_response_failed,
        "session.closed": _on_session_closed,
    }

    def result(self, response_done_ms: float) -> dict[str, Any]:
        def fragment_text(fragments: list[dict[str, Any]]) -> str:
            return "".join(str(event.get("delta", "")) for event in fragments).strip()

        assistant_turns = [item for item in self.turns if item.get("role") == "assistant"]
        user_turns = [item for item in self.turns if item.get("role") == "user"]
        assistant_turn_transcript = " ".join(
            str(item.get("transcript", "")).strip() for item in assistant_turns
        ).strip()
        input_transcript = " ".join(str(item.get("transcript", "")).strip() for item in user_turns).strip()
        projected_user_ends = [turn["end_ms"] for turn in user_turns if isinstance(turn.get("end_ms"), int)]
        user_turn_end_ms = max(projected_user_ends) if projected_user_ends else None
        self.first_audio_ms = (
            round(self.first_speech_offset - user_turn_end_ms, 3)
            if self.first_speech_offset is not None and user_turn_end_ms is not None
            else None
        )
        self.first_text_ms = (
            round(self.first_text_offset - user_turn_end_ms, 3)
            if self.first_text_offset is not None and user_turn_end_ms is not None
            else None
        )
        if self.caller_audio_completion is not None and self.caller_audio_completion.completed_at is not None:
            reference_shift_ms = (self.caller_audio_completion.completed_at - self.response_started_at) * 1000

            def from_caller_completion(value: float | None) -> float | None:
                return round(value - reference_shift_ms, 3) if value is not None else None

            response_done_ms = from_caller_completion(response_done_ms)
            self.first_delegation_ms = from_caller_completion(self.first_delegation_ms)
            self.first_tool_call_ms = from_caller_completion(self.first_tool_call_ms)
            self.first_tool_completed_ms = from_caller_completion(self.first_tool_completed_ms)
            self.backend_completed_ms = from_caller_completion(self.backend_completed_ms)
        return {
            "assistant_text": assistant_turn_transcript or fragment_text(self.assistant_fragments),
            "assistant_turn_transcript": assistant_turn_transcript,
            "input_transcript": input_transcript or fragment_text(self.input_fragments),
            "input_fragments": self.input_fragments,
            "assistant_fragments": self.assistant_fragments,
            "post_tool_assistant_fragments": self.post_tool_assistant_fragments,
            "post_tool_assistant_text": fragment_text(self.post_tool_assistant_fragments),
            "backend_messages": self.backend_messages,
            "backend_text": " ".join(item["text"] for item in self.backend_messages).strip(),
            "backend_usage_events": self.backend_usages,
            "projected_user_turn_end_ms": user_turn_end_ms,
            "first_assistant_speech_offset_ms": self.first_speech_offset,
            "first_assistant_text_offset_ms": self.first_text_offset,
            "turns": self.turns,
            "delegations": self.delegations,
            "tool_calls": self.tool_calls,
            "tool_executions": copy.deepcopy(self.tool_observer.executions),
            "final_state": self.tool_observer.snapshot(),
            "evaluation_transcript": self.event_timeline.evaluation_transcript(),
            "agent_events": [event.model_dump() for event in self.event_timeline.agent_events],
            "output_audio_bytes": bytes(self.output_audio),
            "backend_usage": aggregate_backend_usage(self.backend_usages),
            "first_audio_time_ms": self.first_audio_ms,
            "first_text_time_ms": self.first_text_ms,
            "response_done_time_ms": response_done_ms,
            "delegation_time_ms": self.first_delegation_ms,
            "first_tool_call_time_ms": self.first_tool_call_ms,
            "first_tool_completed_time_ms": self.first_tool_completed_ms,
            "backend_completed_time_ms": self.backend_completed_ms,
        }
