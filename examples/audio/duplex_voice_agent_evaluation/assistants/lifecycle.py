"""Pending-work accounting shared by local and remote delegation controllers."""

from __future__ import annotations

import asyncio

from assistants.errors import LiveResponseError


class PendingWork:
    """Track accepted work independently of the tasks waiting for it."""

    def __init__(self, *, failure_stage: str) -> None:
        self.failure_stage = failure_stage
        self._identifiers: set[str] = set()
        self._idle = asyncio.Event()
        self._idle.set()
        self._error: LiveResponseError | None = None
        self._closed = False

    @property
    def pending(self) -> bool:
        return bool(self._identifiers)

    def contains(self, identifier: str) -> bool:
        return identifier in self._identifiers

    def ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("Delegation controller is closed")
        self.raise_if_failed()

    def begin(self, identifier: str) -> None:
        self.ensure_open()
        if identifier in self._identifiers:
            raise ValueError("Delegation work is already pending")
        self._identifiers.add(identifier)
        self._idle.clear()

    def finish(self, identifier: str) -> None:
        self._identifiers.discard(identifier)
        if not self.pending:
            self._idle.set()

    def fail(self, message: str) -> None:
        if self._error is None:
            self._error = LiveResponseError(message, failure_stage=self.failure_stage)

    def raise_if_failed(self) -> None:
        if self._error is not None:
            raise self._error

    def seal(self) -> None:
        """Stop accepting work without claiming that owned tasks have stopped."""
        self._closed = True

    def abort(self, message: str) -> None:
        """Release abandoned remote work or already-joined local tasks."""
        self.seal()
        if self.pending:
            self.fail(message)
        self._identifiers.clear()
        self._idle.set()

    async def wait(self) -> None:
        """Wait for quiescence; canceling this waiter never cancels owned work."""
        while self.pending:
            await self._idle.wait()
        self.raise_if_failed()
