"""Shared GPT Live connection, audio streaming, and event lifecycle."""

from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Any

import aiohttp

from assistants.config import LiveAgentSettings, session_update, websocket_url
from assistants.frontend.connection import DelegationController
from assistants.frontend.events import TERMINAL_TYPES, EventQueue, transport_error
from assistants.frontend.security import MAX_LIVE_MESSAGE_BYTES, live_trace_config
from assistants.frontend.transport import build_context_append, build_live_headers, unwrap_response_event
from assistants.runtime import ToolExecutor


class LiveFrontend:
    """Own the common voice session while subclasses implement delegation."""

    def __init__(
        self,
        *,
        scenario: object,
        settings: Any | None,
        api_key: str,
        config: LiveAgentSettings,
        tool_executor: ToolExecutor | None = None,
    ) -> None:
        self.scenario = scenario
        self.settings = settings
        self.api_key = api_key
        self.config = config
        self.tool_executor = tool_executor
        self.agent_id = config.model
        self.session: aiohttp.ClientSession | None = None
        self.ws: aiohttp.ClientWebSocketResponse | None = None
        self.events = EventQueue()
        self.receiver: asyncio.Task[None] | None = None
        self._closing = False
        self._started = False
        self._finalized = asyncio.Event()
        self._closed = False
        self._close_lock = asyncio.Lock()

    async def start(self) -> None:
        timeout = aiohttp.ClientTimeout(total=None, sock_connect=15, sock_read=None)
        self.session = aiohttp.ClientSession(timeout=timeout, trace_configs=[live_trace_config()])
        try:
            self.ws = await self.session.ws_connect(
                websocket_url(self.config.endpoint, self.config.model),
                headers=build_live_headers(self.api_key),
                heartbeat=20,
                max_msg_size=MAX_LIVE_MESSAGE_BYTES,
            )
            await self.ws.send_json(session_update(self.scenario, self.config, self.settings))
            message = await self.ws.receive(timeout=20)
            if message.type != aiohttp.WSMsgType.TEXT:
                raise RuntimeError(f"GPT Live session did not start: {message.type.name}")
            event = json.loads(message.data)
            if not isinstance(event, dict) or not isinstance(event.get("type"), str):
                raise RuntimeError("GPT Live returned an invalid startup event")
            if event.get("type") == "error":
                error = event.get("error", {})
                raise RuntimeError(
                    f"GPT Live startup rejected: {error.get('code', 'unknown')} {error.get('message', '')}"
                )
            if event.get("type") != "session.started":
                raise RuntimeError(f"Expected session.started, received {event.get('type')}")
            self._started = True
            await self._start_delegation()
            await self.events.put(event)
            self.receiver = asyncio.create_task(self._receive(), name="live-frontend-receiver")
            self.events.watch(self.receiver, closing=lambda: self._closing, code="live_unexpected_eof")
        except (Exception, asyncio.CancelledError):
            await self.close()
            raise

    async def _start_delegation(self) -> None:
        """Initialize delegation-specific state after the voice session starts."""

    async def _observe_event(self, event: dict[str, Any]) -> None:
        """Let the selected delegation implementation inspect voice events."""

    async def _close_delegation(self) -> None:
        """Release delegation-specific tasks before closing the voice session."""
        if controller := self._delegation_controller():
            await controller.close()

    def _delegation_controller(self) -> DelegationController | None:
        """Frontend-only callers deliberately have no controller attribute."""
        return getattr(self, "controller", None)

    async def _receive(self) -> None:
        try:
            if self.ws is None:
                raise RuntimeError("GPT Live receiver has no connection")
            async for message in self.ws:
                if message.type == aiohttp.WSMsgType.TEXT:
                    event = json.loads(message.data)
                    if not isinstance(event, dict) or not isinstance(event.get("type"), str):
                        raise ValueError("GPT Live returned a non-object or untyped event")
                    event = unwrap_response_event(event)
                    if event.get("type") == "session.closed" and not event.get("_synthetic"):
                        seconds = event.get("usage", {}).get("seconds")
                        if isinstance(seconds, (int, float)) and seconds >= 0:
                            self._finalized.set()
                    await self.events.put(event)
                    if self.events.terminal is not None and event.get("type") not in TERMINAL_TYPES:
                        return
                    if not self._closing:
                        await self._observe_event(event)
                    if self.events.terminal is not None:
                        return
                elif message.type == aiohttp.WSMsgType.ERROR:
                    raise ConnectionError("GPT Live WebSocket failed")
        except asyncio.CancelledError:
            # Receiver cancellation is a normal end, not a model-quality failure.
            self.events.finish(closing=True, code="", message="")
            raise
        except Exception as error:
            if not self._closing:
                await self.events.put(
                    transport_error(
                        "live_protocol_error" if isinstance(error, (ValueError, TypeError)) else "live_transport_error",
                        f"GPT Live receiver failed ({type(error).__name__})",
                    )
                )
        finally:
            self.events.finish(
                closing=self._closing,
                code="live_unexpected_eof",
                message="GPT Live WebSocket ended before session.closed",
            )

    async def _send_live(self, event: dict[str, Any]) -> None:
        if self.ws is None or getattr(self.ws, "closed", False):
            raise RuntimeError("GPT Live connection closed during client delegation")
        await self.ws.send_json(event)
        await self.events.put(
            {
                "type": "evaluation.command.sent",
                "command_type": event.get("type"),
                "client_event_id": event.get("event_id"),
                "delegation_id": event.get("delegation_id"),
            }
        )

    async def send_audio(self, pcm: bytes) -> None:
        if self.ws is None or self.ws.closed:
            raise RuntimeError("cannot send audio: GPT Live WebSocket is closed")
        await self.ws.send_json({"type": "session.input_audio.append", "audio": base64.b64encode(pcm).decode()})

    async def append_context(self, text: str) -> None:
        """Append text through the shared GPT Live frontend protocol."""
        await self._send_live(build_context_append(text))

    async def incoming(self) -> AsyncIterator[dict[str, Any]]:
        while True:
            try:
                event = await self.events.receive()
            except EOFError:
                return
            yield event
            if event.get("type") in TERMINAL_TYPES:
                return

    @property
    def pending_tools(self) -> bool:
        """Include accepted backend work as well as application tool execution."""
        controller = self._delegation_controller()
        return controller is not None and controller.pending

    async def wait_for_tools(self) -> None:
        """Wait for the selected controller's accepted work to settle."""
        if controller := self._delegation_controller():
            await controller.wait()

    async def close(self) -> None:
        async with self._close_lock:
            if self._closed:
                return
            self._closing = True
            try:
                if self._started and not self._finalized.is_set():
                    if self.ws is None or self.ws.closed:
                        raise RuntimeError("GPT Live transport closed before session.closed")
                    if self.receiver is None:
                        self.receiver = asyncio.create_task(self._receive(), name="live-finalization-receiver")
                    await self.ws.send_json({"type": "session.close", "event_id": "event_client_close"})
                    await asyncio.wait_for(self._finalized.wait(), timeout=5)
            finally:
                try:
                    await self._close_delegation()
                finally:
                    if self.receiver is not None:
                        self.receiver.cancel()
                        await asyncio.gather(self.receiver, return_exceptions=True)
                        self.receiver = None
                    try:
                        if self.ws is not None and not self.ws.closed:
                            with suppress(aiohttp.ClientError, ConnectionError):
                                await self.ws.close()
                    finally:
                        if self.session is not None:
                            await self.session.close()
                            self.session = None
                        self.events.finish(closing=True, code="", message="")
                        self._closed = True
