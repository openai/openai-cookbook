"""GPT Live frontend protocol validation, session configuration, and WebSocket transport."""

from __future__ import annotations

import copy
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import aiohttp

from assistants.frontend.security import MAX_LIVE_MESSAGE_BYTES, live_trace_config, validate_live_endpoint

DEFAULT_RESPONSE_TIMEOUT_SECONDS = 30.0
DEFAULT_SAMPLE_RATE_HZ = 24_000
MAX_INITIAL_ITEMS = 128
MAX_INITIAL_TEXT_TOKENS = 8_192


def validate_audio_config(sample_rate_hz: int, input_format: str, output_format: str) -> None:
    if sample_rate_hz != DEFAULT_SAMPLE_RATE_HZ:
        raise ValueError("GPT Live requires a 24,000 Hz audio sample rate")
    if input_format != "pcm16" or output_format != "pcm16":
        raise ValueError("GPT Live requires mono signed 16-bit PCM input and output")


def validate_initial_items(items: list[dict[str, Any]]) -> None:
    """Reject invalid startup history; the server remains authoritative for exact tokenization."""
    if len(items) > MAX_INITIAL_ITEMS:
        raise ValueError(f"GPT Live initial_items accepts at most {MAX_INITIAL_ITEMS} messages")
    minimum_text_tokens = 0
    for item in items:
        if not isinstance(item, dict) or item.get("type") != "message":
            raise ValueError("GPT Live initial_items requires message objects")
        role = item.get("role")
        if role not in {"developer", "user", "assistant"}:
            raise ValueError("GPT Live input role must be developer, user, or assistant")
        content = item.get("content")
        if not isinstance(content, list) or len(content) != 1 or not isinstance(content[0], dict):
            raise ValueError("GPT Live initial_items messages require exactly one text content part")
        part = content[0]
        valid_types = {"output_text", "text"} if role == "assistant" else {"input_text"}
        if part.get("type") not in valid_types or not isinstance(part.get("text"), str):
            raise ValueError(f"GPT Live initial_items has an invalid text part for the {role} role")
        minimum_text_tokens += len(str(part["text"]).split())
    if minimum_text_tokens > MAX_INITIAL_TEXT_TOKENS:
        raise ValueError("GPT Live initial_items exceeds the 8,192 rendered-token limit")


def build_context_append(
    text: str,
    *,
    kind: Literal["commentary", "thinking", "instructions"] = "commentary",
    delegation_id: str | None = None,
) -> dict[str, Any]:
    """Build a validated text context event without rewriting caller-supplied content."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("GPT Live context text must be nonempty")
    if kind not in {"commentary", "thinking", "instructions"}:
        raise ValueError("Unsupported GPT Live context intent")
    return {
        "type": f"session.{kind}.append",
        "event_id": f"event_{uuid4().hex}",
        "delegation_id": delegation_id,
        "content": text,
    }


def unwrap_response_event(event: dict[str, Any]) -> dict[str, Any]:
    """Keep native Live events and retain the wire envelope around backend evidence."""
    if event.get("type") != "response.event":
        return event
    nested = event.get("event")
    if not isinstance(nested, dict) or not isinstance(nested.get("type"), str):
        raise ValueError("GPT Live returned an invalid Responses envelope")
    return {**nested, "delegation_id": event.get("delegation_id"), "_raw_live_event": event}


def build_live_websocket_url(endpoint: str, model: str) -> str:
    validate_live_endpoint(endpoint)
    parts = urlsplit(endpoint)
    scheme = {"http": "ws", "https": "wss", "ws": "ws", "wss": "wss"}.get(parts.scheme)
    if not scheme or not parts.netloc:
        raise ValueError("GPT Live endpoint must be an absolute HTTP or WebSocket URL")
    if parts.path.rstrip("/") == "/v1/live":
        raise ValueError("GPT Live v3 requires /v1/live/sessions; update OPENAI_LIVE_ENDPOINT or --endpoint")
    return urlunsplit((scheme, parts.netloc, parts.path, "", ""))


def build_live_headers(api_key: str) -> dict[str, str]:
    if not api_key.strip():
        raise ValueError("OPENAI_API_KEY is required for a live GPT Live evaluation")
    return {
        "Authorization": f"Bearer {api_key.strip()}",
    }


def normalize_live_response_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Adapt cookbook function schemas to the GPT Live Responses alpha."""
    normalized: list[dict[str, Any]] = []
    for original in tools:
        tool = copy.deepcopy(original)
        if tool.get("type") != "function":
            normalized.append(tool)
            continue
        parameters = tool.get("parameters")
        if not isinstance(parameters, dict):
            raise ValueError(f"Function tool {tool.get('name', '<missing>')} requires a parameters object")
        properties = parameters.get("properties")
        if not isinstance(properties, dict):
            raise ValueError(f"Function tool {tool.get('name', '<missing>')} requires parameter properties")
        originally_required = set(parameters.get("required", []))
        for name, definition in list(properties.items()):
            if name in originally_required:
                continue
            if not isinstance(definition, dict):
                raise ValueError(f"Function parameter {name} must have a JSON object schema")
            nullable_definition = copy.deepcopy(definition)
            properties[name] = {"anyOf": [nullable_definition, {"type": "null"}]}
        parameters["required"] = list(properties)
        parameters["additionalProperties"] = False
        tool.pop("strict", None)
        normalized.append(tool)
    return normalized


def build_session_update(
    system_prompt: str,
    tools: list[dict[str, Any]],
    backend_model: str,
    voice: str,
    *,
    model: str = "gpt-live-1",
    backend_system_prompt: str,
    backend_reasoning_effort: str | None = None,
    backend_max_output_tokens: int | None = None,
    backend_verbosity: str | None = None,
    initial_items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    voice_config: str | dict[str, str] = {"id": voice} if voice.startswith("voice_") else voice
    responses: dict[str, Any] = {
        "model": backend_model,
        "instructions": backend_system_prompt,
        "tools": normalize_live_response_tools(tools),
        "tool_choice": "auto",
        "parallel_tool_calls": True,
    }
    if backend_reasoning_effort is not None:
        responses["reasoning"] = {"effort": backend_reasoning_effort}
    if backend_max_output_tokens is not None:
        responses["max_output_tokens"] = backend_max_output_tokens
    if backend_verbosity is not None:
        responses["text"] = {"verbosity": backend_verbosity}
    session: dict[str, Any] = {
        "model": model,
        "instructions": system_prompt,
        "audio": {"format": {"type": "audio/pcm", "rate": DEFAULT_SAMPLE_RATE_HZ}, "output": {"voice": voice_config}},
        "delegation": {
            "type": "responses",
            "responses": responses,
        },
    }
    if initial_items:
        validate_initial_items(initial_items)
        session["input"] = copy.deepcopy(initial_items)
    return {
        "type": "session.start",
        "event_id": "event_start",
        "session": session,
    }


@asynccontextmanager
async def open_live_websocket(
    *,
    endpoint: str,
    model: str = "gpt-live-1",
    api_key: str,
    timeout_seconds: float,
) -> AsyncIterator[Any]:
    """Open the authenticated assistant WebSocket without evaluator fixtures."""
    timeout = aiohttp.ClientTimeout(total=None, sock_connect=timeout_seconds, sock_read=None)
    async with (
        aiohttp.ClientSession(timeout=timeout, trace_configs=[live_trace_config()]) as session,
        session.ws_connect(
            build_live_websocket_url(endpoint, model),
            headers=build_live_headers(api_key),
            heartbeat=20,
            max_msg_size=MAX_LIVE_MESSAGE_BYTES,
        ) as connection,
    ):
        yield connection
