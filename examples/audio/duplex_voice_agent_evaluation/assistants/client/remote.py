"""Application-side WebSocket for separately deployed client assistants."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import aiohttp

from assistants.client.protocol import client_delegation
from assistants.client.security import ServiceLimits, service_token, validate_endpoint
from assistants.client.service_protocol import FORWARDED_TYPES, validate_live_event
from assistants.frontend.events import transport_error
from assistants.lifecycle import PendingWork
from assistants.runtime import RemoteToolObserver, ToolExecutor

EventCallback = Callable[[dict[str, Any]], Awaitable[None]]


class RemoteClientDelegationController:
    """Bridge Live control events to an independently running application endpoint."""

    def __init__(
        self,
        *,
        endpoint: str,
        configuration: dict[str, Any],
        send_live: EventCallback,
        emit: EventCallback,
        tool_observer: ToolExecutor,
        token: str | None = None,
    ) -> None:
        self.endpoint = endpoint
        self._token = token
        self._closing = False
        self._closed = False
        self._expected_close = False
        self._terminal = False
        self._close_lock = asyncio.Lock()
        self.configuration = configuration
        self.send_live = send_live
        self.emit = emit
        self.tool_observer = tool_observer
        self.session: aiohttp.ClientSession | None = None
        self.connection: aiohttp.ClientWebSocketResponse | None = None
        self.receiver: asyncio.Task[None] | None = None
        self._send_lock = asyncio.Lock()
        self._work = PendingWork(failure_stage="client_assistant_connection")
        self._seen: set[str] = set()
        self._injected: set[str] = set()

    @property
    def pending(self) -> bool:
        return self._work.pending

    async def start(self) -> None:
        self._work.ensure_open()
        endpoint = validate_endpoint(self.endpoint)
        token = service_token(self._token)
        timeout = aiohttp.ClientTimeout(total=None, sock_connect=15, sock_read=None)
        trace = aiohttp.TraceConfig()

        async def reject_redirect(*_: Any) -> None:
            raise RuntimeError("Client assistant redirects are not permitted")

        trace.on_request_redirect.append(reject_redirect)
        self.session = aiohttp.ClientSession(timeout=timeout, trace_configs=[trace])
        try:
            self.connection = await self.session.ws_connect(
                endpoint,
                headers={"Authorization": f"Bearer {token}"},
                heartbeat=20,
                max_msg_size=ServiceLimits().max_message_bytes,
            )
            await self._send({**self.configuration, "type": "session.configure"})
            response = await self.connection.receive_json(timeout=15)
            if not isinstance(response, dict) or response.get("type") != "session.ready":
                raise RuntimeError("Client assistant endpoint rejected the evaluation session")
            self.receiver = asyncio.create_task(self._receive(), name="remote-client-assistant")
            self.receiver.add_done_callback(self._receiver_finished)
        except asyncio.CancelledError:
            await self.close()
            raise
        except Exception as error:
            await self.close()
            raise RuntimeError(f"Client assistant connection failed ({type(error).__name__})") from None

    async def observe(self, event: dict[str, Any]) -> None:
        self._work.ensure_open()
        if event.get("type") not in FORWARDED_TYPES:
            return
        validate_live_event(event)
        if delegation := client_delegation(event):
            identifier, _ = delegation
            if identifier in self._seen:
                return
            self._work.begin(identifier)
            self._seen.add(identifier)
        if event["type"] == "session.closed":
            self._expected_close = True
            self._work.seal()
        try:
            await self._send({"type": "live.event", "event": event})
        except asyncio.CancelledError:
            self._work.abort("Client assistant forwarding was cancelled")
            raise
        except Exception as error:
            await self._fail("client_assistant_connection", f"Client assistant send failed ({type(error).__name__})")
            self._work.raise_if_failed()

    async def _send(self, event: dict[str, Any]) -> None:
        if self.connection is None or self.connection.closed:
            raise RuntimeError("Client assistant endpoint is not connected")
        async with self._send_lock:
            await self.connection.send_json(event)

    async def _fail(self, code: str, message: str) -> None:
        if not self._terminal and not self._closing:
            self._terminal = True
            self._work.fail(message)
            self._work.abort(message)
            await self.emit(transport_error(code, message))

    def _receiver_finished(self, task: asyncio.Task[None]) -> None:
        """Wake lifecycle waiters even when cancellation preceded coroutine startup."""
        if self._closing:
            return
        if task.cancelled():
            self._work.abort("Client assistant receiver was cancelled")
        elif error := task.exception():
            self._work.fail(f"Client assistant receiver failed ({type(error).__name__})")
            self._work.abort("Client assistant receiver stopped")

    async def _observe_assistant_event(self, observed: dict[str, Any]) -> bool:
        if observed.get("type") == "error":
            await self._fail("client_assistant_error", "Client assistant backend work failed")
            return True
        if observed.get("type") == "client_delegation.completed":
            identifier = observed.get("delegation_id")
            if not isinstance(identifier, str) or identifier not in self._seen:
                raise ValueError("Client assistant completed an unknown delegation")
            if not self._work.contains(identifier):
                return False
            if identifier not in self._injected:
                raise ValueError("Client assistant completed a delegation before publishing its result")
            await self.emit(observed)
            self._injected.discard(identifier)
            self._work.finish(identifier)
            return False
        if isinstance(self.tool_observer, RemoteToolObserver):
            self.tool_observer.observe(observed)
        await self.emit(observed)
        return False

    async def _forward_result(self, event: dict[str, Any]) -> None:
        identifier = event.get("delegation_id")
        if (
            event.get("type") != "session.commentary.append"
            or not isinstance(identifier, str)
            or not self._work.contains(identifier)
            or not isinstance(event.get("content"), str)
            or not event["content"].strip()
        ):
            raise ValueError("Client assistant returned an uncorrelated delegation result")
        await self.send_live(event)
        self._injected.add(identifier)

    async def _handle_message(self, event: dict[str, Any]) -> bool:
        kind = event.get("type")
        if kind == "assistant.event" and isinstance(event.get("event"), dict):
            return await self._observe_assistant_event(event["event"])
        if kind == "live.send" and isinstance(event.get("event"), dict):
            await self._forward_result(event["event"])
            return False
        if kind == "session.closed" and self._expected_close:
            await self._finish_receiver()
            return True
        if kind == "error":
            await self._fail("client_assistant_error", "Client assistant session failed")
            return True
        raise ValueError("Client assistant endpoint returned an unsupported event")

    async def _finish_receiver(self) -> None:
        if self._expected_close and not self.pending:
            self._terminal = True
            self._work.seal()
        elif self._expected_close:
            await self._fail("client_assistant_incomplete", "Client assistant closed with unfinished delegations")
        else:
            await self._fail("client_assistant_unexpected_eof", "Client assistant WebSocket ended unexpectedly")

    async def _receive(self) -> None:
        try:
            if self.connection is None:
                raise RuntimeError("Client assistant endpoint is not connected")
            async for message in self.connection:
                if message.type != aiohttp.WSMsgType.TEXT:
                    if message.type == aiohttp.WSMsgType.ERROR:
                        raise ConnectionError("Client assistant WebSocket failed")
                    continue
                event = message.json()
                if not isinstance(event, dict):
                    raise ValueError("Client assistant endpoint returned a non-object event")
                if await self._handle_message(event):
                    return
        except asyncio.CancelledError:
            self._terminal = True
            if not self._closing:
                self._work.abort("Client assistant receiver was cancelled")
            raise
        except Exception as error:
            await self._fail(
                "client_assistant_protocol_error"
                if isinstance(error, (ValueError, TypeError))
                else "client_assistant_connection",
                f"Client assistant receiver failed ({type(error).__name__})",
            )
        finally:
            await self._finish_receiver()

    async def wait(self) -> None:
        await self._work.wait()

    async def close(self) -> None:
        async with self._close_lock:
            if self._closed:
                return
            self._closing = True
            self._work.seal()
            try:
                if self.receiver is not None:
                    self.receiver.cancel()
                    await asyncio.gather(self.receiver, return_exceptions=True)
                    self.receiver = None
                try:
                    if self.connection is not None and not self.connection.closed:
                        await self.connection.close()
                finally:
                    if self.session is not None:
                        await self.session.close()
                        self.session = None
            finally:
                self._work.abort("Client assistant closed before delegated work completed")
                self._injected.clear()
                self._closed = True
