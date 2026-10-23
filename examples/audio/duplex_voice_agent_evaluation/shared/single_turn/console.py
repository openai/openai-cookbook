"""Compact, redacted event logs for single-turn audio harnesses."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, TextIO

from assistants.frontend.transport import unwrap_response_event


@dataclass(slots=True)
class _ConsoleAudioGroup:
    event_type: str
    direction: str
    start_ms: int
    end_ms: int
    chunks: int
    event_time_ms: float
    audio_kind: str = ""


class SingleTurnConsoleEventLog:
    """Mirror the redacted trace to the console without dumping every audio frame."""

    def __init__(self, stream: TextIO, *, chunk_ms: int) -> None:
        self.stream = stream
        self.chunk_ms = chunk_ms
        self.input_offset_ms = 0
        self.audio_groups: dict[tuple[str, str], _ConsoleAudioGroup] = {}

    @staticmethod
    def _compact(value: Any, *, limit: int = 200) -> str:
        rendered = (
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            if isinstance(value, dict | list)
            else str(value)
        )
        return rendered if len(rendered) <= limit else f"{rendered[:limit]}…"

    @staticmethod
    def _direction(direction: str) -> str:
        return {"client_to_server": "->", "server_to_client": "<-", "application_internal": ".."}.get(direction, "..")

    def _line(self, event_time_ms: float, direction: str, message: str) -> None:
        print(f"{event_time_ms / 1_000:7.3f}s  {self._direction(direction)} {message}", flush=True)

    def _flush_audio(self) -> None:
        for key, group in list(self.audio_groups.items()):
            timeline = (
                "timing=untimed"
                if group.start_ms < 0
                else f"timeline={group.start_ms / 1_000:.1f}..{group.end_ms / 1_000:.1f}s"
            )
            audio_kind = f" kind={group.audio_kind}" if group.audio_kind else ""
            self._line(
                group.event_time_ms,
                group.direction,
                f"{group.event_type} {timeline} chunks={group.chunks}{audio_kind}",
            )
            del self.audio_groups[key]

    def _audio(self, event: dict[str, Any], direction: str, event_time_ms: float) -> None:
        kind = str(event.get("type", ""))
        if kind == "session.input_audio.append":
            start_ms = self.input_offset_ms
            end_ms = start_ms + self.chunk_ms
            self.input_offset_ms = end_ms
            audio_kind = str(event.get("audio_kind", "speech"))
        else:
            start_ms = int(event.get("start_ms", event.get("offset_ms", -1)))
            end_ms = int(event.get("end_ms", start_ms))
            audio_kind = ""

        key = (kind, audio_kind)
        group = self.audio_groups.get(key)
        if group is not None and start_ms != group.end_ms:
            self._flush_audio()
            group = None
        if group is None:
            group = _ConsoleAudioGroup(kind, direction, start_ms, end_ms, 1, event_time_ms, audio_kind)
            self.audio_groups[key] = group
        else:
            group.end_ms = end_ms
            group.chunks += 1
            group.event_time_ms = event_time_ms
        if group.end_ms - group.start_ms >= 1_000:
            self._flush_audio()

    def _observe(self, record: dict[str, Any]) -> None:
        raw_event = record.get("event", {})
        if not isinstance(raw_event, dict):
            return
        raw_event = unwrap_response_event(raw_event)
        event_time_ms = float(record.get("event_time_ms", 0))
        direction = str(record.get("direction", ""))
        kind = str(raw_event.get("type", "unknown"))
        if kind in {"session.input_audio.append", "session.output_audio.delta"}:
            self._audio(raw_event, direction, event_time_ms)
            return

        if kind in {"session.input_transcript.delta", "session.output_transcript.delta"}:
            text = str(raw_event.get("delta", ""))
            start_ms, end_ms = raw_event.get("start_ms"), raw_event.get("end_ms")
            timeline = (
                f" timeline={start_ms}..{end_ms}ms" if isinstance(start_ms, int) and isinstance(end_ms, int) else ""
            )
            role = "USER" if kind == "session.input_transcript.delta" else "ASSISTANT"
            self._line(event_time_ms, direction, f"{kind}{timeline} {role}: {self._compact(text)}")
            return

        if kind in {"turn.created", "turn.done"}:
            self._flush_audio()
            turn = raw_event.get("turn", {})
            if isinstance(turn, dict):
                role = str(turn.get("role", "unknown"))
                start_ms, end_ms = turn.get("start_ms"), turn.get("end_ms")
                timeline = (
                    f" timeline={start_ms}..{end_ms}ms" if isinstance(start_ms, int) and isinstance(end_ms, int) else ""
                )
                transcript = str(turn.get("transcript", "")).strip()
                speech = f" {role.upper()}: {self._compact(transcript)}" if transcript else ""
                self._line(event_time_ms, direction, f"{kind} role={role}{timeline}{speech}")
            return

        if kind == "session.delegation.created":
            self._flush_audio()
            item = raw_event.get("delegation", {})
            if isinstance(item, dict):
                content = item.get("content", [])
                text = " ".join(
                    str(part.get("text", "")) for part in content if isinstance(part, dict) and part.get("text")
                )
                arguments = f" arguments={self._compact(text)}" if text else ""
                self._line(event_time_ms, direction, f"{kind} target={item.get('target', 'unknown')}{arguments}")
            return

        if kind in {"tool.called", "tool.completed", "tool.failed"}:
            self._flush_audio()
            arguments = self._compact(raw_event.get("arguments", {}))
            result = raw_event.get("result")
            output = f" result={self._compact(result)}" if isinstance(result, dict) else ""
            error = f" error={self._compact(raw_event['error'])}" if raw_event.get("error") else ""
            self._line(
                event_time_ms,
                direction,
                f"{kind} name={raw_event.get('name', 'unknown')} arguments={arguments}{output}{error}",
            )
            return

        if kind in {
            "session.start",
            "session.update",
            "session.started",
            "session.closed",
            "response.created",
            "response.completed",
        }:
            if kind in {"session.closed", "response.completed"}:
                self._flush_audio()
            self._line(event_time_ms, direction, kind)

    def write(self, value: str) -> int:
        written = self.stream.write(value)
        try:
            record = json.loads(value)
        except (json.JSONDecodeError, TypeError, ValueError):
            return written
        if isinstance(record, dict):
            self._observe(record)
        return written

    def flush(self) -> None:
        self.stream.flush()

    def finish(self) -> None:
        self._flush_audio()
        self.stream.flush()
