"""Assistant-owned delegation layered over an existing GPT Live connection."""

from __future__ import annotations

import asyncio
from typing import Any, Protocol

from assistants.frontend.events import EventQueue, transport_error
from assistants.frontend.transport import unwrap_response_event


class DelegationController(Protocol):
    """Own accepted work through result publication; never delegate execution to evaluators.

    wait() reaches quiescence or raises a retained lifecycle failure. Canceling
    a waiter does not cancel work. close() stops acceptance, cancels/joins owned
    tasks, releases resources once, and wakes waiters if work was abandoned.
    """

    @property
    def pending(self) -> bool: ...

    async def observe(self, event: dict[str, Any]) -> None: ...

    async def wait(self) -> None: ...

    async def close(self) -> None: ...


class AssistantConnection:
    """Expose voice and assistant-observation events through one read-only stream."""

    def __init__(
        self,
        connection: Any,
        controller: DelegationController,
        *,
        events: EventQueue | None = None,
    ) -> None:
        self.connection = connection
        self.controller = controller
        self.events = events if events is not None else EventQueue()
        self._closing = False
        self._closed = False
        self._close_lock = asyncio.Lock()
        self.receiver: asyncio.Task[None] | None = None

    @property
    def pending_tools(self) -> bool:
        """Tell evaluators whether the assistant still owns unfinished work."""
        return self.controller.pending

    async def start(self) -> None:
        self.receiver = asyncio.create_task(self._receive(), name="assistant-delegation-control")
        self.events.watch(self.receiver, closing=lambda: self._closing, code="assistant_unexpected_eof")

    async def _receive(self) -> None:
        try:
            while True:
                event = await self.connection.receive_json(timeout=None)
                if not isinstance(event, dict) or not isinstance(event.get("type"), str):
                    raise ValueError("GPT Live returned a non-object or untyped event")
                event = unwrap_response_event(event)
                await self.events.put(event)
                if self.events.terminal is not None and event.get("type") not in {"error", "session.closed"}:
                    return
                await self.controller.observe(event)
                if self.events.terminal is not None:
                    return
        except asyncio.CancelledError:
            self.events.finish(closing=True, code="", message="")
            raise
        except Exception as error:
            if not self._closing:
                await self.events.put(
                    transport_error(
                        "assistant_protocol_error"
                        if isinstance(error, (ValueError, TypeError))
                        else "assistant_transport_error",
                        f"GPT Live receiver failed ({type(error).__name__})",
                    )
                )
        finally:
            self.events.finish(
                closing=self._closing,
                code="assistant_unexpected_eof",
                message="GPT Live connection ended before session.closed",
            )

    async def send_json(self, event: dict[str, Any]) -> None:
        await self.connection.send_json(event)
        if event.get("type") != "session.input_audio.append":
            await self.events.put(
                {
                    "type": "evaluation.command.sent",
                    "command_type": event.get("type"),
                    "client_event_id": event.get("event_id"),
                    "delegation_id": event.get("delegation_id"),
                }
            )

    async def receive_json(self, *, timeout: float | None = None) -> dict[str, Any]:  # noqa: ASYNC109
        if timeout is None:
            return await self.events.receive()
        return await asyncio.wait_for(self.events.receive(), timeout=timeout)

    async def wait_for_tools(self) -> None:
        await self.controller.wait()

    async def close(self) -> None:
        async with self._close_lock:
            if self._closed:
                return
            self._closing = True
            try:
                try:
                    await self.controller.close()
                finally:
                    if self.receiver is not None:
                        self.receiver.cancel()
                        await asyncio.gather(self.receiver, return_exceptions=True)
                        self.receiver = None
            finally:
                self.events.finish(closing=True, code="", message="")
                self._closed = True
