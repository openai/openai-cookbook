"""Append-only in-memory audit trail for the deterministic local path."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from .models import AuditEvent, AuditEventType

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


class AuditTrail:
    """Record ordered events without exposing mutable internal state."""

    def __init__(self, *, clock: Clock = utc_now) -> None:
        self._clock = clock
        self._events: list[AuditEvent] = []

    def append(
        self,
        *,
        request_id: str,
        event_type: AuditEventType,
        detail: dict[str, Any] | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            sequence=len(self._events) + 1,
            occurred_at=self._clock(),
            request_id=request_id,
            event_type=event_type,
            detail=detail or {},
        )
        self._events.append(event)
        return event

    def for_request(self, request_id: str) -> tuple[AuditEvent, ...]:
        return tuple(event for event in self._events if event.request_id == request_id)

    @property
    def events(self) -> tuple[AuditEvent, ...]:
        return tuple(self._events)
