"""Separately deployable WebSocket application backend for client delegation."""

from __future__ import annotations

import argparse
import asyncio
import copy
import hmac
import json
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from aiohttp import web

from assistants.client.backend import ApplicationBackend, ToolCallback
from assistants.client.delegation import ClientDelegationController, DelegationLimitError
from assistants.client.openai_backend import ResponsesBackend
from assistants.client.security import ServiceLimits, service_token, validate_origin
from assistants.client.service_protocol import ClientProtocolError, validate_configuration, validate_live_event
from assistants.config import assistant_env, assistant_prompt, render_authorized_context
from assistants.resources import assistant_resources
from assistants.runtime import ToolExecutor
from shared.environment import load_environment

BackendFactory = Callable[[dict[str, Any], ToolCallback], ApplicationBackend]
ToolFactory = Callable[[dict[str, Any]], ToolExecutor]
BACKEND_FACTORY = web.AppKey("client_backend_factory")
TOOL_FACTORY = web.AppKey("client_tool_factory")
LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class ServiceState:
    token: str = field(repr=False)
    allowed_origins: frozenset[str]
    limits: ServiceLimits
    active_connections: int = 0


SERVICE_STATE = web.AppKey("client_service_state", ServiceState)


def application_tools(_configuration: dict[str, Any]) -> ToolExecutor:
    """Create application-owned tools inside the remote assistant service."""
    resources = assistant_resources(assistant_mode="client")
    return resources.create_executor({}, resources.load_facts())


def openai_backend(configuration: dict[str, Any], execute_tool: ToolCallback) -> ApplicationBackend:
    """Use OpenAI only for the optional bundled reference backend."""
    key = os.getenv("OPENAI_RESPONSES_API_KEY", "").strip() or os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise ValueError("OPENAI_RESPONSES_API_KEY or OPENAI_API_KEY is required for the OpenAI backend")
    resources = assistant_resources(assistant_mode="client")
    tools = json.loads(resources.tools_file.read_text(encoding="utf-8"))
    if not isinstance(tools, list):
        raise ValueError("Application tools must be a JSON array")
    instructions = render_authorized_context(
        assistant_prompt("backend", assistant_mode="client"),
        facts=resources.load_facts(),
        initial_state={},
    )
    return ResponsesBackend(
        api_key=key,
        model=assistant_env("OPENAI_LIVE_BACKEND_MODEL"),
        instructions=instructions,
        tools=tools,
        reasoning_effort=assistant_env("OPENAI_LIVE_BACKEND_REASONING_EFFORT"),
        max_output_tokens=int(assistant_env("OPENAI_LIVE_BACKEND_MAX_OUTPUT_TOKENS")),
        execute_tool=execute_tool,
    )


async def health(_: web.Request) -> web.Response:
    return web.json_response({"status": "ok", "assistant": "client"})


async def assistant_connection(request: web.Request) -> web.WebSocketResponse:
    state = request.app[SERVICE_STATE]
    authorization = request.headers.getall("Authorization", [])
    if len(authorization) != 1 or not hmac.compare_digest(
        authorization[0].encode("utf-8"), f"Bearer {state.token}".encode("ascii")
    ):
        raise web.HTTPUnauthorized(text="Client assistant authentication required")
    origins = request.headers.getall("Origin", [])
    if origins and (len(origins) != 1 or origins[0] not in state.allowed_origins):
        raise web.HTTPForbidden(text="Client assistant Origin is not allowed")
    if state.active_connections >= state.limits.max_connections:
        raise web.HTTPServiceUnavailable(text="Client assistant connection limit reached")
    state.active_connections += 1
    try:
        return await _serve_connection(request, state.limits)
    finally:
        state.active_connections -= 1


async def _serve_connection(request: web.Request, limits: ServiceLimits) -> web.WebSocketResponse:
    connection = web.WebSocketResponse(heartbeat=20, max_msg_size=limits.max_message_bytes)
    await connection.prepare(request)
    controller: ClientDelegationController | None = None
    executor: ToolExecutor | None = None
    send_lock = asyncio.Lock()

    async def send(event: dict[str, Any]) -> None:
        # Backend exception text can contain credentials or application internals.
        nested = event.get("event") if event.get("type") == "assistant.event" else event
        if isinstance(nested, dict) and nested.get("type") == "error":
            LOGGER.warning("Client assistant reported a backend failure")
            safe = {"type": "error", "error": {"code": "client_assistant_error", "message": "Backend work failed"}}
            event = {"type": "assistant.event", "event": safe} if nested is not event else safe
        if len(json.dumps(event).encode("utf-8")) > limits.max_message_bytes:
            raise DelegationLimitError("Client assistant output message limit reached")
        async with asyncio.timeout(min(limits.delegation_timeout, max(0, deadline - loop.time()))), send_lock:
            await connection.send_json(event)

    async def execute(name: str, arguments: dict[str, Any], call_id: str) -> dict[str, Any]:
        if executor is None:
            raise RuntimeError("The application assistant has not initialized its tools")
        try:
            return await asyncio.to_thread(executor.execute, name, arguments, call_id=call_id)
        except ValueError as error:
            executor.executions.append(
                {
                    "call_id": call_id,
                    "name": name,
                    "arguments": copy.deepcopy(arguments),
                    "status": "failed",
                    "output": {"ok": False, "error": str(error)},
                }
            )
            raise

    loop = asyncio.get_running_loop()
    deadline = loop.time() + limits.session_timeout
    configure_deadline = loop.time() + limits.configure_timeout
    received_bytes = 0
    received_events = 0
    try:
        while True:
            remaining = (deadline if controller is not None else min(deadline, configure_deadline)) - loop.time()
            if remaining <= 0:
                raise TimeoutError("Client assistant session deadline reached")
            message = await connection.receive(timeout=remaining)
            if message.type in {web.WSMsgType.CLOSE, web.WSMsgType.CLOSED, web.WSMsgType.CLOSING}:
                break
            if message.type != web.WSMsgType.TEXT:
                raise ClientProtocolError("Expected a JSON text message")
            received_bytes += len(message.data.encode("utf-8"))
            received_events += 1
            if received_bytes > limits.max_session_bytes or received_events > limits.max_events:
                raise DelegationLimitError("Client assistant session limit reached")
            try:
                event = message.json()
            except (ValueError, TypeError) as error:
                raise ClientProtocolError("Invalid JSON message") from error
            if not isinstance(event, dict):
                raise ClientProtocolError("Client assistant requires JSON-object events")
            kind = event.get("type")
            if kind == "session.configure":
                if controller is not None:
                    raise ClientProtocolError("The client assistant session is already configured")
                validate_configuration(event)
                tool_factory: ToolFactory = request.app[TOOL_FACTORY]
                executor = tool_factory(event)
                backend_factory: BackendFactory = request.app[BACKEND_FACTORY]
                backend = backend_factory(event, execute)

                async def emit(item: dict[str, Any], *, application_executor: ToolExecutor = executor) -> None:
                    observed = dict(item)
                    if observed.get("type") in {"tool.completed", "tool.failed"}:
                        observed["application_state"] = application_executor.snapshot()
                        call_id = str(observed.get("call_id", ""))
                        execution = next(
                            (
                                entry
                                for entry in reversed(application_executor.executions)
                                if not call_id or entry.get("call_id") == call_id
                            ),
                            None,
                        )
                        if execution is not None:
                            observed["tool_execution"] = copy.deepcopy(execution)
                            observed.setdefault("call_id", execution.get("call_id"))
                    await send({"type": "assistant.event", "event": observed})

                async def send_live(item: dict[str, Any]) -> None:
                    await send({"type": "live.send", "event": item})

                controller = ClientDelegationController(
                    backend=backend,
                    send_live=send_live,
                    emit=emit,
                    initial_items=event.get("initial_items") if isinstance(event.get("initial_items"), list) else None,
                    max_pending=limits.max_pending_delegations,
                    max_delegations=limits.max_delegations,
                    work_timeout=limits.delegation_timeout,
                )
                await send({"type": "session.ready"})
            elif kind == "live.event":
                if controller is None or not isinstance(event.get("event"), dict):
                    raise ClientProtocolError("Configure the assistant before forwarding GPT Live events")
                if set(event) != {"type", "event"}:
                    raise ClientProtocolError("Unsupported Live message field")
                observed = validate_live_event(event["event"])
                if observed["type"] == "session.closed":
                    await send({"type": "session.closed"})
                    break
                await controller.observe(observed)
            else:
                raise ClientProtocolError("Unsupported client assistant message")
    except asyncio.CancelledError:
        raise
    except Exception as error:
        LOGGER.warning("Client assistant session stopped (%s)", type(error).__name__)
        if not connection.closed:
            code = (
                "client_protocol_error"
                if isinstance(error, ClientProtocolError)
                else "client_limit_reached"
                if isinstance(error, DelegationLimitError)
                else "client_session_timeout"
                if isinstance(error, TimeoutError)
                else "client_assistant_error"
            )
            async with asyncio.timeout(limits.cleanup_timeout), send_lock:
                await connection.send_json({"type": "error", "error": {"code": code, "message": "Session stopped"}})
    finally:
        try:
            if controller is not None:
                async with asyncio.timeout(limits.cleanup_timeout):
                    await controller.close()
        finally:
            await connection.close()
    return connection


def create_app(
    *,
    backend_factory: BackendFactory = openai_backend,
    tool_factory: ToolFactory = application_tools,
    token: str | None = None,
    allowed_origins: tuple[str, ...] = (),
    limits: ServiceLimits | None = None,
) -> web.Application:
    app = web.Application()
    app[SERVICE_STATE] = ServiceState(
        service_token(token),
        frozenset(validate_origin(origin) for origin in allowed_origins),
        limits or ServiceLimits(),
    )
    app[BACKEND_FACTORY] = backend_factory
    app[TOOL_FACTORY] = tool_factory
    app.router.add_get("/health", health)
    app.router.add_get("/ws/assistant", assistant_connection)
    return app


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse service options without opening a socket."""
    parser = argparse.ArgumentParser(description="Serve the separately deployable GPT Live client assistant.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8795)
    parser.add_argument("--allow-origin", action="append", default=[], help="Exact trusted browser Origin; repeatable.")
    args = parser.parse_args(argv)
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("The reference assistant must bind to a loopback address")
    try:
        for origin in args.allow_origin:
            validate_origin(origin)
    except ValueError as error:
        parser.error(str(error))
    return args


def main(argv: list[str] | None = None) -> None:
    load_environment()
    args = parse_args(argv)
    web.run_app(create_app(allowed_origins=tuple(args.allow_origin)), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
