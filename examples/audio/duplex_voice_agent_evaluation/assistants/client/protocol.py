"""Client-owned delegation events and UTF-8-safe result injection."""

from __future__ import annotations

from typing import Any

from assistants.frontend.transport import build_context_append


def split_context_text(text: str, *, max_bytes: int = 400) -> list[str]:
    """Conservatively chunk text below the API token limit without a tokenizer."""
    if max_bytes < 4:
        raise ValueError("max_bytes must fit a complete UTF-8 character")
    if not text.strip():
        return []
    chunks: list[str] = []
    current: list[str] = []
    used = 0
    for character in text:
        size = len(character.encode("utf-8"))
        if current and used + size > max_bytes:
            chunks.append("".join(current))
            current = []
            used = 0
        current.append(character)
        used += size
    if current:
        chunks.append("".join(current))
    return chunks


def client_delegation(event: dict[str, Any]) -> tuple[str, str] | None:
    """Extract metadata; v3 delegates without supplying a task description."""
    if event.get("type") != "session.delegation.created":
        return None
    item = event.get("delegation")
    if not isinstance(item, dict) or item.get("target") != "client":
        return None
    identifier = item.get("id")
    if not isinstance(identifier, str) or not identifier:
        return None
    return (
        identifier,
        "Resolve the current user request and corrections from the voice conversation "
        "and verified application context.",
    )


def build_context_events(delegation_id: str, text: str) -> list[dict[str, Any]]:
    """Return natural language to its original GPT Live client delegation."""
    if not delegation_id:
        raise ValueError("delegation_id is required")
    chunks = split_context_text(text)
    if not chunks:
        raise ValueError("delegation output must contain user-facing text")
    return [build_context_append(chunk, delegation_id=delegation_id) for chunk in chunks]
