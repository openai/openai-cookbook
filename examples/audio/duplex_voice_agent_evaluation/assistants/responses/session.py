"""GPT Live session configuration for OpenAI-managed Responses delegation."""

from __future__ import annotations

from typing import Any

from assistants.frontend.transport import build_session_update


def build_managed_session(
    *,
    model: str = "gpt-live-1",
    instructions: str,
    backend_instructions: str,
    tools: list[dict[str, Any]],
    backend_model: str,
    voice: str,
    reasoning_effort: str | None = None,
    max_output_tokens: int | None = None,
    verbosity: str | None = None,
    initial_items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Let GPT Live own Responses context, orchestration, and output injection."""
    return build_session_update(
        instructions,
        tools,
        backend_model,
        voice,
        model=model,
        backend_system_prompt=backend_instructions,
        backend_reasoning_effort=reasoning_effort,
        backend_max_output_tokens=max_output_tokens,
        backend_verbosity=verbosity,
        initial_items=initial_items,
    )
