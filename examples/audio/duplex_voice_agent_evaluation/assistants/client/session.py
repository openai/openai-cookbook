"""GPT Live session configuration for application-managed delegation."""

from __future__ import annotations

import copy
from typing import Any

from assistants.frontend.transport import validate_initial_items


def build_client_session(
    *,
    model: str = "gpt-live-1",
    instructions: str,
    voice: str,
    initial_items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Advertise client delegation; backend instructions/tools never enter Live config."""
    voice_config: str | dict[str, str] = {"id": voice} if voice.startswith("voice_") else voice
    session: dict[str, Any] = {
        "model": model,
        "instructions": instructions,
        "audio": {"format": {"type": "audio/pcm", "rate": 24_000}, "output": {"voice": voice_config}},
        "delegation": {"type": "client"},
    }
    if initial_items:
        validate_initial_items(initial_items)
        session["input"] = copy.deepcopy(initial_items)
    return {"type": "session.start", "event_id": "event_start", "session": session}
