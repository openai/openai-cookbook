"""Timestamped caller/assistant memory for client-owned delegations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class TranscriptSegment:
    identifier: str
    role: str
    start_ms: int
    end_ms: int
    text: str
    delivered_characters: int = 0
    projected: bool = False


class TranscriptLedger:
    """Prefer actual transcript items; use projected turns only as fallback."""

    def __init__(self) -> None:
        self._segments: list[TranscriptSegment] = []
        self._identifiers: dict[str, TranscriptSegment] = {}
        self._anonymous = 0
        self._event_ids: set[str] = set()

    def add_history(self, history: list[dict[str, Any]]) -> None:
        for index, item in enumerate(history):
            role = str(item.get("role", ""))
            content = item.get("content", [])
            text = " ".join(
                str(part.get("text", "")) for part in content if isinstance(part, dict) and part.get("text")
            )
            if role in {"user", "assistant"} and text.strip():
                self.record(role, text, 0, index + 1, f"history:{index}")

    def record_event(self, event: dict[str, Any]) -> None:
        event_id = event.get("event_id")
        if isinstance(event_id, str):
            if event_id in self._event_ids:
                return
            self._event_ids.add(event_id)
        kind = str(event.get("type", ""))
        if kind in {"turn.created", "turn.done"}:
            turn = event.get("turn", {})
            if isinstance(turn, dict) and turn.get("transcript") and turn.get("role") in {"user", "assistant"}:
                self.record(
                    str(turn["role"]),
                    str(turn["transcript"]),
                    int(turn.get("start_ms", 0)),
                    int(turn.get("end_ms", 0)),
                    f"turn:{turn.get('id', '')}",
                    projected=True,
                )
            return
        prefix, _, suffix = kind.removeprefix("session.").removeprefix("conversation.").rpartition(".")
        if prefix not in {"input_transcript", "output_transcript"} or suffix not in {"delta", "added", "done"}:
            return
        item = event.get("item") if isinstance(event.get("item"), dict) else {}
        text = event.get("delta") if suffix == "delta" else item.get("text") or event.get("text")
        if not isinstance(text, str) or not text:
            return
        identifier = str(event.get("item_id") or item.get("id") or event.get("turn_id") or "")
        role = "user" if prefix.startswith("input") else "assistant"
        if kind.startswith("session.") and suffix == "delta" and not identifier:
            start = int(event["start_ms"])
            prior = next(
                (
                    segment
                    for segment in reversed(self._segments)
                    if segment.role == role.upper()
                    and segment.identifier.startswith("live:")
                    and start <= segment.end_ms + 500
                    and int(event["end_ms"]) >= segment.start_ms
                ),
                None,
            )
            identifier = prior.identifier if prior else f"live:{event_id or len(self._segments)}"
        self.record(
            role,
            text,
            int(event.get("start_ms", 0)),
            int(event.get("end_ms", event.get("start_ms", 0))),
            identifier or None,
            append=suffix == "delta",
        )

    def record(
        self,
        role: str,
        text: str,
        start_ms: int,
        end_ms: int,
        identifier: str | None,
        *,
        append: bool = False,
        projected: bool = False,
    ) -> None:
        if not text or (not append and not text.strip()):
            return
        if not identifier:
            self._anonymous += 1
            identifier = f"segment:{self._anonymous}"
        normalized_role = role.upper()
        existing = self._identifiers.get(identifier)
        if existing is None:
            existing = next(
                (
                    segment
                    for segment in reversed(self._segments)
                    if segment.projected != projected
                    and segment.role == normalized_role
                    and abs(segment.start_ms - start_ms) <= 1_000
                    and (segment.text in text or text in segment.text)
                ),
                None,
            )
        if existing is None:
            existing = TranscriptSegment(
                identifier,
                normalized_role,
                max(0, start_ms),
                max(start_ms + 1, end_ms),
                text,
                projected=projected,
            )
            self._segments.append(existing)
            self._identifiers[identifier] = existing
            return
        self._identifiers[identifier] = existing
        existing.start_ms = min(existing.start_ms, max(0, start_ms))
        existing.end_ms = max(existing.end_ms, end_ms, existing.start_ms + 1)
        if projected and not existing.projected:
            return
        if existing.projected and not projected:
            existing.identifier = identifier
            existing.projected = False
            existing.text = text
            existing.delivered_characters = 0
            return
        existing.text = existing.text + text if append else text
        if existing.delivered_characters > len(existing.text):
            existing.delivered_characters = 0

    def consume_srt(self) -> str:
        pending: list[TranscriptSegment] = []
        actual = [segment for segment in self._segments if not segment.projected]
        for segment in sorted(self._segments, key=lambda item: (item.start_ms, item.end_ms)):
            if segment.projected and any(
                item.role == segment.role and item.start_ms <= segment.end_ms and segment.start_ms <= item.end_ms
                for item in actual
            ):
                segment.delivered_characters = len(segment.text)
                continue
            fresh = segment.text[segment.delivered_characters :].strip()
            if fresh:
                pending.append(
                    TranscriptSegment(segment.identifier, segment.role, segment.start_ms, segment.end_ms, fresh)
                )
                segment.delivered_characters = len(segment.text)
        return "\n\n".join(
            f"{index}\n{_timestamp(segment.start_ms)} --> {_timestamp(segment.end_ms)}\n{segment.role}: {segment.text}"
            for index, segment in enumerate(pending, start=1)
        )


def _timestamp(milliseconds: int) -> str:
    hours, remainder = divmod(max(0, milliseconds), 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"
