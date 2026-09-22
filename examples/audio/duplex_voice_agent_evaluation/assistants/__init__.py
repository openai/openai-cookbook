"""One GPT Live frontend with selectable Responses or client delegation."""

from __future__ import annotations

from typing import Any

from assistants.client.assistant import ClientDelegatedAssistant
from assistants.config import LiveAgentSettings
from assistants.responses.assistant import ResponsesManagedAssistant
from assistants.runtime import ToolExecutor

EvaluatedAssistant = ResponsesManagedAssistant | ClientDelegatedAssistant


def create_assistant(
    *,
    scenario: object,
    settings: Any | None,
    api_key: str,
    config: LiveAgentSettings | None = None,
    tool_executor: ToolExecutor | None = None,
) -> EvaluatedAssistant:
    """Select delegation while keeping the GPT Live frontend identical."""
    mode = config.assistant_mode if config is not None else getattr(settings, "assistant_mode", "responses")
    selected = ClientDelegatedAssistant if mode == "client" else ResponsesManagedAssistant
    return selected(
        scenario=scenario,
        settings=settings,
        api_key=api_key,
        config=config,
        tool_executor=tool_executor,
    )


__all__ = [
    "ClientDelegatedAssistant",
    "EvaluatedAssistant",
    "LiveAgentSettings",
    "ResponsesManagedAssistant",
    "create_assistant",
]
