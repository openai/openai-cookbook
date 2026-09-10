"""Small, bounded protocol accepted by a separately deployed client assistant."""

from __future__ import annotations

from typing import Any

from assistants.client.protocol import client_delegation

TRANSCRIPT_TYPES = frozenset(
    f"{prefix}{direction}_transcript.{suffix}"
    for prefix in ("session.",)
    for direction in ("input", "output")
    for suffix in ("delta",)
)
FORWARDED_TYPES = TRANSCRIPT_TYPES | {"session.delegation.created", "session.closed"}


class ClientProtocolError(ValueError):
    """An authenticated peer sent an unsupported or malformed control event."""


def validate_configuration(event: dict[str, Any]) -> None:
    if set(event) - {"type", "initial_items", "model", "instructions", "tools"}:
        raise ClientProtocolError("Unsupported session configuration field")
    for key in ("model", "instructions"):
        if key in event and not isinstance(event[key], str):
            raise ClientProtocolError("Invalid session configuration")
    if "tools" in event and (
        not isinstance(event["tools"], list) or any(not isinstance(item, dict) for item in event["tools"])
    ):
        raise ClientProtocolError("Invalid tool configuration")
    history = event.get("initial_items", [])
    if not isinstance(history, list) or len(history) > 100:
        raise ClientProtocolError("Invalid initial conversation history")
    for item in history:
        if (
            not isinstance(item, dict)
            or item.get("type", "message") != "message"
            or item.get("role") not in {"user", "assistant"}
            or not _text_content(item.get("content"), {"input_text", "output_text"})
        ):
            raise ClientProtocolError("Invalid initial conversation message")


def _text_content(value: Any, kinds: set[str]) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(
            isinstance(part, dict) and part.get("type") in kinds and isinstance(part.get("text"), str) for part in value
        )
    )


def validate_live_event(event: Any) -> dict[str, Any]:
    if not isinstance(event, dict) or event.get("type") not in FORWARDED_TYPES:
        raise ClientProtocolError("Unsupported Live control event")
    kind = event["type"]
    if kind == "session.delegation.created":
        delegation = client_delegation(event)
        if delegation is None or len(delegation[0]) > 256:
            raise ClientProtocolError("Invalid client delegation")
    elif kind in TRANSCRIPT_TYPES:
        item = event.get("item", {})
        if not isinstance(item, dict):
            raise ClientProtocolError("Invalid transcript item")
        for value in (event.get("delta", ""), event.get("text", ""), item.get("text", "")):
            if not isinstance(value, str):
                raise ClientProtocolError("Invalid transcript text")
    _validate_timestamps(event)
    return event


def _validate_timestamps(value: dict[str, Any]) -> None:
    for key in ("start_ms", "end_ms"):
        if key in value and (type(value[key]) is not int or value[key] < 0):
            raise ClientProtocolError("Invalid transcript timestamp")
