"""GPT Live frontend using OpenAI-managed Responses delegation."""

from __future__ import annotations

from typing import Any

from assistants.config import LiveAgentSettings
from assistants.frontend.assistant import LiveFrontend
from assistants.responses.delegation import ResponsesDelegationController
from assistants.runtime import ToolExecutor


class ResponsesManagedAssistant(LiveFrontend):
    """Keep the common frontend and delegate backend orchestration to GPT Live."""

    def __init__(
        self,
        *,
        scenario: object,
        settings: Any | None,
        api_key: str,
        config: LiveAgentSettings | None = None,
        tool_executor: ToolExecutor | None = None,
    ) -> None:
        selected_config = config or (
            LiveAgentSettings(
                endpoint=settings.agent_endpoint,
                model=settings.agent_model,
                voice=settings.agent_voice,
                backend_model=settings.backend_model,
            )
            if settings is not None
            else LiveAgentSettings()
        )
        super().__init__(
            scenario=scenario,
            settings=settings,
            api_key=api_key,
            config=selected_config,
            tool_executor=tool_executor,
        )
        self.controller = (
            ResponsesDelegationController(executor=tool_executor, send_live=self._send_live, emit=self.events.put)
            if tool_executor is not None
            else None
        )
        self.handled_call_ids = self.controller.handled_call_ids if self.controller is not None else set()

    async def _observe_event(self, event: dict[str, Any]) -> None:
        if self.controller is not None:
            await self.controller.observe(event)

    async def _handle_function_event(self, event: dict[str, Any]) -> None:
        """Retain the existing diagnostic hook while execution stays assistant-owned."""
        if self.controller is not None:
            await self.controller.observe(event)
