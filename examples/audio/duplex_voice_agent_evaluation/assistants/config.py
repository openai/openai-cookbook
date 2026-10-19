"""Assistant configuration and authorized context shared by evaluation harnesses."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from assistants.frontend.transport import build_live_websocket_url
from assistants.resources import assistant_resources
from shared.environment import load_environment
from shared.scenarios import ConversationHistoryItem

ASSISTANT_ENV_DEFAULTS: dict[str, str] = {
    "OPENAI_LIVE_ENDPOINT": "https://api.openai.com/v1/live/sessions",
    "OPENAI_LIVE_MODEL": "gpt-live-1",
    "OPENAI_LIVE_VOICE": "marin",
    "OPENAI_LIVE_BACKEND_MODEL": "gpt-5.6-terra",
    "OPENAI_LIVE_BACKEND_REASONING_EFFORT": "none",
    "OPENAI_LIVE_BACKEND_MAX_OUTPUT_TOKENS": "1000",
    "OPENAI_LIVE_BACKEND_VERBOSITY": "low",
}

ReasoningEffort = Literal["none", "low", "medium", "high", "xhigh", "max"]
Verbosity = Literal["low", "medium", "high"]
AssistantMode = Literal["responses", "client"]


def assistant_env(name: str) -> str:
    """Read assistant configuration from the environment or application defaults."""
    if name not in ASSISTANT_ENV_DEFAULTS:
        raise ValueError(f"Unknown assistant setting: {name}")
    value = os.getenv(name, ASSISTANT_ENV_DEFAULTS[name]).strip()
    if not value:
        raise ValueError(f"{name} is required; configure it in .env")
    return value


def assistant_prompt(kind: Literal["frontend", "backend"], *, assistant_mode: AssistantMode = "responses") -> str:
    """Read the selected assistant's prompt from its editable text file."""
    resources = assistant_resources(assistant_mode=assistant_mode)
    path = resources.system_prompt_file if kind == "frontend" else resources.backend_system_prompt_file
    prompt = path.read_text(encoding="utf-8").strip()
    if not prompt:
        raise ValueError(f"Assistant prompt file is empty: {path}")
    return prompt


def assistant_default_tools(*, assistant_mode: AssistantMode = "responses") -> list[dict[str, Any]]:
    """Load application tools owned by the selected assistant module."""
    try:
        tools = json.loads(assistant_resources(assistant_mode=assistant_mode).tools_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("Assistant tools must be a valid JSON array") from exc
    if not isinstance(tools, list) or not all(isinstance(tool, dict) and tool.get("type") for tool in tools):
        raise ValueError("Assistant tools must be a JSON array of typed tool objects")
    return tools


class LiveAgentSettings(BaseModel):
    """Configure the evaluated assistant, never its caller or semantic judge."""

    @model_validator(mode="before")
    @classmethod
    def load_local_environment(cls, value: Any) -> Any:
        load_environment()
        return value

    endpoint: str = Field(default_factory=lambda: assistant_env("OPENAI_LIVE_ENDPOINT"))
    model: str = Field(default_factory=lambda: assistant_env("OPENAI_LIVE_MODEL"))
    voice: str = Field(default_factory=lambda: assistant_env("OPENAI_LIVE_VOICE"))
    backend_model: str = Field(default_factory=lambda: assistant_env("OPENAI_LIVE_BACKEND_MODEL"))
    assistant_mode: AssistantMode = Field(
        default_factory=lambda: os.getenv("OPENAI_ASSISTANT_MODE", "responses").strip() or "responses",
        validate_default=True,
    )
    client_endpoint: str = Field(default_factory=lambda: os.getenv("OPENAI_CLIENT_ASSISTANT_ENDPOINT", "").strip())
    backend_reasoning_effort: ReasoningEffort = Field(
        default_factory=lambda: assistant_env("OPENAI_LIVE_BACKEND_REASONING_EFFORT"),
        validate_default=True,
    )
    backend_max_output_tokens: int = Field(
        default_factory=lambda: int(assistant_env("OPENAI_LIVE_BACKEND_MAX_OUTPUT_TOKENS")),
        gt=0,
    )
    backend_verbosity: Verbosity = Field(
        default_factory=lambda: assistant_env("OPENAI_LIVE_BACKEND_VERBOSITY"),
        validate_default=True,
    )


def build_assistant_session(
    config: LiveAgentSettings,
    *,
    instructions: str,
    backend_instructions: str,
    tools: list[dict[str, Any]],
    initial_items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Select independent managed/client session configurations without sharing agents."""
    if config.assistant_mode == "client":
        from assistants.client.session import build_client_session

        return build_client_session(
            model=config.model, instructions=instructions, voice=config.voice, initial_items=initial_items
        )
    from assistants.responses.session import build_managed_session

    return build_managed_session(
        model=config.model,
        instructions=instructions,
        backend_instructions=backend_instructions,
        tools=tools,
        backend_model=config.backend_model,
        voice=config.voice,
        reasoning_effort=config.backend_reasoning_effort,
        max_output_tokens=config.backend_max_output_tokens,
        verbosity=config.backend_verbosity,
        initial_items=initial_items,
    )


def build_initial_items(history: Sequence[ConversationHistoryItem]) -> list[dict[str, Any]]:
    """Hydrate prior caller/assistant turns using GPT Live's text-only item format."""
    return [
        {
            "type": "message",
            "role": item.role,
            "content": [{"type": "input_text" if item.role == "user" else "output_text", "text": item.text}],
        }
        for item in history
    ]


def render_authorized_context(
    prompt: str,
    *,
    facts: Mapping[str, Any],
    initial_state: Mapping[str, Any],
    conversation_context: str = "",
) -> str:
    """Append public facts and authorized state, never private grading data."""
    context: dict[str, Any] = {
        "business_facts": {key: value for key, value in facts.items() if key != "availability_overrides"},
        "authorized_application_state": dict(initial_state),
    }
    if conversation_context:
        context["previous_conversation_summary"] = conversation_context
    return f"{prompt}\n\n## Authorized factual application context\n{json.dumps(context, ensure_ascii=False)}"


def websocket_url(endpoint: str, model: str) -> str:
    """Resolve either HTTPS or WebSocket Live endpoints consistently."""
    return build_live_websocket_url(endpoint, model)


def session_update(
    scenario: object,
    config: LiveAgentSettings,
    settings: Any | None = None,
) -> dict[str, Any]:
    """Adapt existing RUN settings without exposing any scenario to the target."""
    context = getattr(getattr(scenario, "input", None), "context", None)
    instructions = (
        settings.agent_instructions
        if settings is not None
        else assistant_prompt("frontend", assistant_mode=config.assistant_mode)
    )
    backend_instructions = (
        settings.backend_instructions
        if settings is not None
        else assistant_prompt("backend", assistant_mode=config.assistant_mode)
    )
    tools = (
        settings.delegation_tools
        if settings is not None
        else assistant_default_tools(assistant_mode=config.assistant_mode)
    )
    return build_assistant_session(
        config,
        instructions=instructions,
        backend_instructions=backend_instructions,
        tools=tools,
        initial_items=build_initial_items(context.history) if context is not None else None,
    )
