"""Independent GPT Live assistant with customer-managed Responses delegation."""

from __future__ import annotations

import asyncio
import os
from typing import Any

from assistants.client.backend import ApplicationBackend
from assistants.client.delegation import ClientDelegationController
from assistants.client.openai_backend import ResponsesBackend
from assistants.client.remote import RemoteClientDelegationController
from assistants.config import LiveAgentSettings, assistant_prompt, build_initial_items
from assistants.frontend.assistant import LiveFrontend
from assistants.runtime import ToolExecutor


class ClientDelegatedAssistant(LiveFrontend):
    """Keep the common frontend while the application owns backend orchestration."""

    def __init__(
        self,
        *,
        scenario: object,
        settings: Any | None,
        api_key: str,
        config: LiveAgentSettings | None = None,
        tool_executor: ToolExecutor | None = None,
        backend: ApplicationBackend | None = None,
    ) -> None:
        selected_config = config or (
            LiveAgentSettings(
                endpoint=settings.agent_endpoint,
                model=settings.agent_model,
                voice=settings.agent_voice,
                backend_model=settings.backend_model,
                assistant_mode="client",
                client_endpoint=settings.assistant_endpoint,
            )
            if settings is not None
            else LiveAgentSettings(assistant_mode="client")
        )
        super().__init__(
            scenario=scenario,
            settings=settings,
            api_key=api_key,
            config=selected_config,
            tool_executor=tool_executor,
        )
        initial_context = getattr(getattr(scenario, "input", None), "context", None)
        initial_items = build_initial_items(initial_context.history) if initial_context is not None else []
        self.backend = backend
        self._initial_items = initial_items
        self.controller: ClientDelegationController | RemoteClientDelegationController | None = None
        if not self.config.client_endpoint:
            self.backend = backend or ResponsesBackend(
                api_key=os.getenv("OPENAI_RESPONSES_API_KEY", "").strip() or api_key,
                model=self.config.backend_model,
                instructions=(
                    settings.backend_instructions
                    if settings is not None
                    else assistant_prompt("backend", assistant_mode="client")
                ),
                tools=(settings.delegation_tools if settings is not None else []),
                reasoning_effort=self.config.backend_reasoning_effort,
                max_output_tokens=self.config.backend_max_output_tokens,
                execute_tool=self._execute_tool,
            )
            self.controller = ClientDelegationController(
                backend=self.backend,
                send_live=self._send_live,
                emit=self.events.put,
                initial_items=initial_items,
            )

    async def _execute_tool(self, name: str, arguments: dict[str, Any], call_id: str) -> dict[str, Any]:
        if self.tool_executor is None:
            raise RuntimeError(f"No application executor is available for {name}")
        return await asyncio.to_thread(self.tool_executor.execute, name, arguments, call_id=call_id)

    async def _start_delegation(self) -> None:
        if not self.config.client_endpoint:
            return
        if self.tool_executor is None:
            raise RuntimeError("A remote client assistant requires application-owned tools")
        controller = RemoteClientDelegationController(
            endpoint=self.config.client_endpoint,
            configuration={
                "initial_items": self._initial_items,
            },
            send_live=self._send_live,
            emit=self.events.put,
            tool_observer=self.tool_executor,
        )
        await controller.start()
        self.controller = controller

    async def _observe_event(self, event: dict[str, Any]) -> None:
        if self.controller is None:
            raise RuntimeError("Client delegation has not started")
        await self.controller.observe(event)
