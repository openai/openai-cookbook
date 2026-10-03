"""Shared GPT Live connection, audio streaming, and event lifecycle."""

from __future__ import annotations

import asyncio
import base64
import copy
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import suppress
from typing import Any

import aiohttp

from assistants.config import LiveAgentSettings, session_update, websocket_url
from assistants.frontend.bounded import (
    bounded_trace_config,
    check_transport_support,
    configured_proxy,
    confirmed_close,
    disable_connection_retry,
    valid_start,
)
from assistants.frontend.connection import DelegationController
from assistants.frontend.events import TERMINAL_TYPES, EventQueue, transport_error
from assistants.frontend.security import MAX_LIVE_MESSAGE_BYTES, live_trace_config
from assistants.frontend.transport import build_context_append, build_live_headers, unwrap_response_event
from assistants.runtime import ToolExecutor


class LiveFrontend:
    """Own the common voice session while subclasses implement delegation.

    ``bounded=True`` opts into a single connection attempt and separate raw
    startup/finalization receipts. Its synchronous ``raw_observer(event,
    direction)`` sees copied server events and client dispatch intents; it must
    not block. Observer failure seals work but preserves the finalization reader.
    The ordinary consumer stream keeps its existing one-terminal-event contract.
    """

    def __init__(
        self,
        *,
        scenario: object,
        settings: Any | None,
        api_key: str,
        config: LiveAgentSettings,
        tool_executor: ToolExecutor | None = None,
        bounded: bool = False,
        raw_observer: Callable[[dict[str, Any], str], None] | None = None,
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
        self.bounded = bounded
        self.raw_observer = raw_observer
        self.start_event: dict[str, Any] | None = None
        self.final_event: dict[str, Any] | None = None
        self.start_sent = False
        self.cleanup_errors: list[dict[str, str]] = []
        self.cleanup_warnings: list[dict[str, str]] = []
        self.transport_closed = False
        self.transport_observations: dict[str, Any] = {
            "connection_attempts": 0,
            "request_headers_sent": 0,
            "error_classes": [],
        }
        self._startup_ready = asyncio.Event()
        self._close_received = asyncio.Event()
        self._bounded_failed = False
        self._send_lock = asyncio.Lock()
        self._cleanup_tasks: set[asyncio.Future[Any]] = set()
        self._delegation_shutdown: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self.bounded:
            await self._start_bounded()
            return
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
        if self.bounded:
            await self.send_json(event)
            return
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
        if self.bounded:
            await self.send_json({"type": "session.input_audio.append", "audio": base64.b64encode(pcm).decode()})
            return
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
        if self.bounded:
            await self._close_bounded()
            return
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

    @property
    def finalization_confirmed(self) -> bool:
        """Whether matching, genuine provider receipts establish final voice usage."""
        return confirmed_close(self.start_event, self.final_event, self.config.model)

    def _record_raw(self, event: dict[str, Any], direction: str) -> None:
        if self.raw_observer is not None:
            try:
                self.raw_observer(copy.deepcopy(event), direction)
            except Exception as error:
                self.raw_observer = None
                self._bounded_failed = True
                self.cleanup_errors.append({"stage": "raw_observer", "error_class": type(error).__name__})
                self._begin_delegation_close()
                raise

    async def send_json(self, event: dict[str, Any]) -> None:
        """Single-turn runtime facade; a dispatch receipt is not an API acknowledgment."""
        if not self.bounded:
            await self._send_live(event)
            return
        async with self._send_lock:
            kind = event.get("type")
            if kind != "session.close" and (self._closing or self._bounded_failed or self.events.terminal is not None):
                raise RuntimeError("Live dispatch is sealed")
            if self.ws is None or self.ws.closed:
                raise RuntimeError("Live WebSocket is closed")
            if kind == "session.start" and self.start_sent:
                raise RuntimeError("Live startup was already attempted")
            try:
                self._record_raw(event, "client_dispatch_intent")
            except Exception:
                if kind != "session.close":
                    raise
                # Observation is now disabled and the error retained. A failing
                # sink must not prevent the shutdown command from reaching Live.
            if kind == "session.start":
                self.start_sent = True
            await self.ws.send_json(event)
            if kind not in {"session.input_audio.append", "session.start", "session.close"}:
                await self.events.put(
                    {
                        "type": "evaluation.command.sent",
                        "command_type": kind,
                        "client_event_id": event.get("event_id"),
                        "delegation_id": event.get("delegation_id"),
                    }
                )

    async def receive_json(self, *, timeout: float | None = None) -> dict[str, Any]:  # noqa: ASYNC109
        """Read the consumer queue without taking ownership of the raw socket reader."""
        async with asyncio.timeout(timeout):
            return await self.events.receive()

    async def _start_bounded(self) -> None:
        if self.session is not None or self.start_sent or self._closed:
            raise RuntimeError("This Live frontend cannot reconnect")
        try:
            check_transport_support()
            # Fail local delegation setup before sending provider startup.
            await self._start_delegation()
            url = websocket_url(self.config.endpoint, self.config.model)
            proxy = configured_proxy(url)
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=None, sock_connect=10, sock_read=None),
                trust_env=False,
                trace_configs=[bounded_trace_config(self.transport_observations)],
            )
            disable_connection_retry(self.session)
            self.ws = await self.session.ws_connect(
                url,
                headers=build_live_headers(self.api_key),
                proxy=proxy,
                heartbeat=20,
                max_msg_size=MAX_LIVE_MESSAGE_BYTES,
                timeout=aiohttp.ClientWSTimeout(ws_receive=None, ws_close=0.25),
            )
            self.receiver = asyncio.create_task(self._receive_bounded(), name="bounded-live-receiver")
            self.events.watch(self.receiver, closing=lambda: self._closing, code="live_unexpected_eof")
            async with asyncio.timeout(10):
                await self.send_json(session_update(self.scenario, self.config, self.settings))
                await self._startup_ready.wait()
            if not valid_start(self.start_event, self.config.model) or self._bounded_failed:
                raise RuntimeError("Live did not return a valid matching session.started")
            self._started = True
        except BaseException:
            # Preserve the initiating error; close separately retains cleanup failures.
            with suppress(BaseException):
                await self.close()
            raise

    async def _bounded_failure(self, code: str, error: BaseException | None = None) -> None:
        self._bounded_failed = True
        self._startup_ready.set()
        self._begin_delegation_close()
        await self.events.put(transport_error(code, type(error).__name__ if error else "Live session failed"))

    def _begin_delegation_close(self) -> asyncio.Task[None]:
        if self._delegation_shutdown is None:
            self._delegation_shutdown = asyncio.create_task(self._close_delegation(), name="bounded-delegation-close")
            self._delegation_shutdown.add_done_callback(lambda task: None if task.cancelled() else task.exception())
        return self._delegation_shutdown

    async def _receive_bounded(self) -> None:
        try:
            if self.ws is None:
                raise RuntimeError("Live receiver has no connection")
            async for message in self.ws:
                if message.type == aiohttp.WSMsgType.ERROR:
                    raise ConnectionError("Live WebSocket transport failed")
                if message.type != aiohttp.WSMsgType.TEXT:
                    continue
                try:
                    raw = json.loads(message.data)
                    if not isinstance(raw, dict) or not isinstance(raw.get("type"), str):
                        raise ValueError("Invalid Live event")
                except (ValueError, TypeError) as error:
                    await self._bounded_failure("live_protocol_error", error)
                    continue  # Retain the reader for a subsequent real close receipt.
                kind = raw["type"]
                if kind == "session.started":
                    if self.start_event is not None:
                        await self._bounded_failure("live_duplicate_start")
                    else:
                        self.start_event = copy.deepcopy(raw)
                    self._startup_ready.set()
                elif kind == "session.closed":
                    self.final_event = copy.deepcopy(raw)
                    self._close_received.set()
                    if self.finalization_confirmed:
                        self._finalized.set()
                try:
                    self._record_raw(raw, "server_to_client")
                except Exception as error:
                    await self._bounded_failure("live_observation_error", error)
                if kind == "error":
                    self._bounded_failed = True
                    self._startup_ready.set()
                    self._begin_delegation_close()
                try:
                    event = unwrap_response_event(raw)
                except (ValueError, TypeError) as error:
                    await self._bounded_failure("live_protocol_error", error)
                    continue
                await self.events.put(event)
                if kind == "session.closed":
                    return
                if self.events.terminal is not None:
                    self._bounded_failed = True
                    self._begin_delegation_close()
                if not self._closing and not self._bounded_failed:
                    try:
                        await self._observe_event(raw)
                    except Exception as error:
                        await self._bounded_failure("live_application_error", error)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            await self._bounded_failure("live_transport_error", error)
        finally:
            self._startup_ready.set()
            self.events.finish(closing=self._closing, code="live_unexpected_eof", message="No provider close receipt")

    async def _cleanup_step(self, awaitable: Awaitable[Any], seconds: float, deadline: float) -> Any:
        """Bound this wait so backend cleanup cannot consume transport's budget.

        Python cannot forcibly stop a coroutine that suppresses cancellation.
        Such work remains tracked and is reported as failed cleanup; it can also
        delay an enclosing asyncio.run shutdown beyond this method's deadline.
        """
        task = asyncio.ensure_future(awaitable)
        self._cleanup_tasks.add(task)

        def finished(completed: asyncio.Future[Any]) -> None:
            self._cleanup_tasks.discard(completed)
            if not completed.cancelled():
                completed.exception()

        task.add_done_callback(finished)
        try:
            remaining = max(0, min(seconds, deadline - asyncio.get_running_loop().time()))
            done, _ = await asyncio.wait({task}, timeout=remaining)
            if not done:
                raise TimeoutError("Live cleanup deadline exceeded")
            return task.result()
        finally:
            if not task.done():
                task.cancel()

    async def _close_bounded(self) -> None:
        async with self._close_lock:
            if self._closed:
                return
            self._closing = True
            deadline = asyncio.get_running_loop().time() + 9.5
            errors: list[BaseException] = []

            async def attempt(stage: str, work: Awaitable[Any], seconds: float) -> None:
                try:
                    await self._cleanup_step(work, seconds, deadline)
                except BaseException as error:
                    errors.append(error)
                    self.cleanup_errors.append({"stage": stage, "error_class": type(error).__name__})

            async def finalize() -> None:
                if not self.start_sent:
                    return
                if self.final_event is None:
                    await self.send_json({"type": "session.close", "event_id": "event_client_close"})
                    await self._close_received.wait()
                if not self.finalization_confirmed:
                    raise RuntimeError("Live final usage is unconfirmed")

            # Stop/invalidate backend work before closing Live; keep its raw reader
            # available while the provider finalizes independently of consumer errors.
            await attempt("delegation", self._begin_delegation_close(), 2)
            await attempt("finalization", finalize(), 5)
            if self.receiver is not None:
                self.receiver.cancel()
                await attempt("receiver", asyncio.gather(self.receiver, return_exceptions=True), 0.5)
                self.receiver = None
            handshake_timeout: TimeoutError | None = None
            if self.ws is not None:
                try:
                    await self._cleanup_step(self.ws.close(), 0.5, deadline)
                    internal_error = self.ws.exception()
                    if internal_error is not None:
                        raise internal_error
                except TimeoutError as error:
                    handshake_timeout = error
                except BaseException as error:
                    errors.append(error)
                    self.cleanup_errors.append({"stage": "websocket", "error_class": type(error).__name__})
            if self.session is not None:
                connector = self.session.connector
                await attempt("http", self.session.close(), 0.5)
                self.transport_closed = self.session.closed is True and (connector is None or connector.closed is True)
            else:
                self.transport_closed = self.ws is None or self.ws.closed is True
            if handshake_timeout is not None:
                if self.finalization_confirmed and self.transport_closed:
                    self.cleanup_warnings.append({"stage": "websocket", "error_class": "TimeoutError"})
                else:
                    errors.append(handshake_timeout)
                    self.cleanup_errors.append({"stage": "websocket", "error_class": "TimeoutError"})
            if not self.transport_closed:
                errors.append(RuntimeError("Owned Live transport closure was not verified"))
                self.cleanup_errors.append({"stage": "http", "error_class": "UnverifiedClosure"})
            # Join timed-out owned tasks once more after the independent transport
            # cleanup. Retain any cancellation-resistant tasks for the caller;
            # their continued execution is a failure, never successful teardown.
            pending = {task for task in self._cleanup_tasks if not task.done()}
            if pending:
                for task in pending:
                    task.cancel()
                try:
                    _, pending = await asyncio.wait(
                        pending, timeout=max(0, min(0.5, deadline - asyncio.get_running_loop().time()))
                    )
                except BaseException as error:
                    errors.append(error)
                    self.cleanup_errors.append({"stage": "owned_tasks", "error_class": type(error).__name__})
                if pending:
                    errors.append(RuntimeError("Owned Live cleanup tasks remain pending"))
                    self.cleanup_errors.append({"stage": "owned_tasks", "error_class": "IncompleteCleanup"})
            self.events.finish(closing=True, code="", message="")
            self._closed = True
            if len(errors) == 1:
                raise errors[0]
            if errors:
                raise BaseExceptionGroup("Live cleanup failed", errors)
