"""Client-delegation control over the evaluator's authenticated Live WebSocket."""

from __future__ import annotations

import asyncio
import os
from typing import Any

from assistants.client.backend import ApplicationBackend
from assistants.client.delegation import ClientDelegationController
from assistants.client.openai_backend import ResponsesBackend
from assistants.client.remote import RemoteClientDelegationController
from assistants.config import LiveAgentSettings
from assistants.frontend.connection import AssistantConnection
from assistants.frontend.events import EventQueue
from assistants.runtime import ToolExecutor

ClientDelegatedConnection = AssistantConnection


async def bind_client_delegation(
    connection: Any,
    *,
    config: LiveAgentSettings,
    instructions: str,
    tools: list[dict[str, Any]],
    executor: ToolExecutor,
    api_key: str,
    initial_items: list[dict[str, Any]] | None = None,
    backend: ApplicationBackend | None = None,
) -> ClientDelegatedConnection:
    """Attach application-owned reasoning to an existing authenticated Live session."""
    events = EventQueue()

    async def execute(name: str, arguments: dict[str, Any], call_id: str) -> dict[str, Any]:
        return await asyncio.to_thread(executor.execute, name, arguments, call_id=call_id)

    if config.client_endpoint:
        controller: ClientDelegationController | RemoteClientDelegationController = RemoteClientDelegationController(
            endpoint=config.client_endpoint,
            configuration={
                "initial_items": initial_items or [],
            },
            send_live=connection.send_json,
            emit=events.put,
            tool_observer=executor,
        )
        await controller.start()
    else:
        backend = backend or ResponsesBackend(
            api_key=os.getenv("OPENAI_RESPONSES_API_KEY", "").strip() or api_key,
            model=config.backend_model,
            instructions=instructions,
            tools=tools,
            reasoning_effort=config.backend_reasoning_effort,
            max_output_tokens=config.backend_max_output_tokens,
            execute_tool=execute,
        )
        controller = ClientDelegationController(
            backend=backend,
            send_live=connection.send_json,
            emit=events.put,
            initial_items=initial_items,
        )
    wrapped = ClientDelegatedConnection(connection, controller, events=events)
    controller.send_live = wrapped.send_json
    await wrapped.start()
    return wrapped
