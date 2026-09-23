"""Application-owned GPT Live delegation orchestration."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from assistants.client.backend import ApplicationBackend, DelegationHandoff
from assistants.client.memory import TranscriptLedger
from assistants.client.protocol import build_context_events, client_delegation
from assistants.lifecycle import PendingWork


class DelegationLimitError(RuntimeError):
    """The session exhausted its bounded backend-work allowance."""


EventCallback = Callable[[dict[str, Any]], Awaitable[None]]


class ClientDelegationController:
    """Own backend context while GPT Live keeps its continuous voice session."""

    def __init__(
        self,
        *,
        backend: ApplicationBackend,
        send_live: EventCallback,
        emit: EventCallback,
        initial_items: list[dict[str, Any]] | None = None,
        max_pending: int | None = None,
        max_delegations: int | None = None,
        work_timeout: float | None = None,
    ) -> None:
        self.backend = backend
        self.send_live = send_live
        self.emit = emit
        self.transcript = TranscriptLedger()
        if initial_items:
            self.transcript.add_history(initial_items)
        self._seen: set[str] = set()
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._count = 0
        self.max_pending = max_pending
        self.max_delegations = max_delegations
        self.work_timeout = work_timeout
        self._closed = False
        self._close_lock = asyncio.Lock()
        self._work = PendingWork(failure_stage="client_delegation")

    @property
    def pending(self) -> bool:
        return self._work.pending

    async def observe(self, event: dict[str, Any]) -> None:
        self._work.ensure_open()
        self.transcript.record_event(event)
        delegation = client_delegation(event)
        if delegation is None:
            return
        identifier, task = delegation
        if identifier in self._seen:
            return
        if (self.max_pending is not None and len(self._tasks) >= self.max_pending) or (
            self.max_delegations is not None and self._count >= self.max_delegations
        ):
            raise DelegationLimitError("Client delegation limit reached")
        self._seen.add(identifier)
        self._count += 1
        handoff = DelegationHandoff(
            task=task,
            transcript_srt=self.transcript.consume_srt(),
            follow_up=self._count > 1,
        )
        self._work.begin(identifier)
        background = asyncio.create_task(self._run(identifier, handoff), name=f"client-delegation-{identifier}")
        self._tasks[identifier] = background
        background.add_done_callback(lambda completed, key=identifier: self._finished(key, completed))

    async def _run(self, identifier: str, handoff: DelegationHandoff) -> None:
        async def publish(event: dict[str, Any]) -> None:
            await self.emit({**event, "delegation_id": identifier, "_client_managed": True})

        try:
            async with asyncio.timeout(self.work_timeout):
                await publish(
                    {
                        "type": "client_delegation.handoff",
                        "task": handoff.task,
                        "transcript": handoff.transcript_srt,
                        "follow_up": handoff.follow_up,
                    }
                )
                answer = await self.backend.run(handoff, publish)
                for event in build_context_events(identifier, answer):
                    await self.send_live(event)
                await publish({"type": "client_delegation.completed", "text": answer})
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self._work.fail(f"Client delegation failed ({type(error).__name__})")
            await self.emit(
                {
                    "type": "error",
                    "error": {"code": "client_delegation_failed", "message": str(error)},
                    "delegation_id": identifier,
                }
            )

    def _finished(self, identifier: str, task: asyncio.Task[None]) -> None:
        self._tasks.pop(identifier, None)
        if task.cancelled():
            self._work.fail("Client delegation was cancelled")
        elif error := task.exception():
            self._work.fail(f"Client delegation publication failed ({type(error).__name__})")
        self._work.finish(identifier)

    async def wait(self) -> None:
        await self._work.wait()

    async def close(self) -> None:
        async with self._close_lock:
            if self._closed:
                return
            self._work.seal()
            try:
                tasks = list(self._tasks.values())
                for task in tasks:
                    task.cancel()
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
                await self.backend.close()
            finally:
                self._work.abort("Client delegation was cancelled during close")
                self._closed = True
