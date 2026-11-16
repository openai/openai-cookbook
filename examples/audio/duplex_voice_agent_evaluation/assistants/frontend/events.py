"""Single-consumer event streams with one explicit terminal outcome."""

from __future__ import annotations

import asyncio
import json
from collections import deque
from collections.abc import Callable
from typing import Any

TERMINAL_TYPES = frozenset({"session.closed", "error"})
MAX_QUEUED_EVENTS = 1024
MAX_QUEUED_BYTES = 16 * 1024 * 1024
MAX_TERMINAL_BYTES = 64 * 1024


def transport_error(code: str, message: str) -> dict[str, Any]:
    return {"type": "error", "error": {"code": code, "message": message}}


class LimitedQueue[T](asyncio.Queue[T]):
    """Fail promptly on count/serialized-byte overflow instead of distorting timing."""

    def __init__(self, maxsize: int = MAX_QUEUED_EVENTS, *, max_bytes: int = MAX_QUEUED_BYTES) -> None:
        if maxsize <= 0 or max_bytes <= 0:
            raise ValueError("Event queue limits must be positive")
        super().__init__(maxsize=maxsize)
        self.max_bytes = max_bytes
        self.queued_bytes = 0
        self._sizes: deque[int] = deque()

    def _put(self, item: T) -> None:
        size = len(json.dumps(item, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        if self.queued_bytes + size > self.max_bytes:
            raise asyncio.QueueFull
        super()._put(item)
        self._sizes.append(size)
        self.queued_bytes += size

    def _get(self) -> T:
        item = super()._get()
        self.queued_bytes -= self._sizes.popleft()
        return item

    async def put(self, item: T) -> None:
        self.put_nowait(item)


class EventQueue(LimitedQueue[dict[str, Any]]):
    """Keep queued events in order, enqueue termination once, and reject late events."""

    def __init__(self, maxsize: int = MAX_QUEUED_EVENTS, *, max_bytes: int = MAX_QUEUED_BYTES) -> None:
        super().__init__(maxsize=maxsize, max_bytes=max_bytes)
        self.terminal: dict[str, Any] | None = None

    def put_nowait(self, item: dict[str, Any]) -> None:
        if self.terminal is not None:
            return
        if item.get("type") in TERMINAL_TYPES:
            self._terminate(item)
            return
        try:
            super().put_nowait(item)
        except asyncio.QueueFull:
            self._terminate(transport_error("event_queue_overflow", "Assistant event buffer capacity exceeded"))

    def _terminate(self, item: dict[str, Any]) -> None:
        # One reserved terminal slot, even if the data budget is exhausted. Do not
        # drop buffered audio or wait for a consumer during cancellation/cleanup.
        if len(json.dumps(item, ensure_ascii=False).encode("utf-8")) > MAX_TERMINAL_BYTES:
            item = transport_error("event_queue_overflow", "Assistant terminal event exceeded its size limit")
        self.terminal = item
        asyncio.Queue._put(self, item)
        self._sizes.append(0)
        self._unfinished_tasks += 1
        self._finished.clear()
        self._wakeup_next(self._getters)

    async def receive(self) -> dict[str, Any]:
        if self.terminal is not None and self.empty():
            raise EOFError("Assistant event stream is closed")
        return await self.get()

    def finish(self, *, closing: bool, code: str, message: str) -> None:
        self.put_nowait({"type": "session.closed", "_synthetic": True} if closing else transport_error(code, message))

    def watch(self, task: asyncio.Task[None], *, closing: Callable[[], bool], code: str) -> None:
        """Also cover cancellation before the receiver coroutine starts executing."""

        def finished(receiver: asyncio.Task[None]) -> None:
            cancelled = receiver.cancelled()
            error = None if cancelled else receiver.exception()
            self.finish(
                closing=closing() or cancelled,
                code=code,
                message=f"Assistant receiver stopped ({type(error).__name__ if error else 'EOF'})",
            )

        task.add_done_callback(finished)
