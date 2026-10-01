"""Credential destination and message limits for GPT Live connections."""

from __future__ import annotations

import ipaddress
import os
from typing import Any
from urllib.parse import urlsplit

import aiohttp

MAX_LIVE_MESSAGE_BYTES = 4 * 1024 * 1024
INSECURE_LOOPBACK_ENV = "OPENAI_LIVE_ALLOW_INSECURE_LOOPBACK"


def validate_live_endpoint(endpoint: str, *, allow_insecure_loopback: bool | None = None) -> None:
    """Only an explicit local-development opt-in permits sending credentials without TLS."""
    if allow_insecure_loopback is None:
        allow_insecure_loopback = os.getenv(INSECURE_LOOPBACK_ENV, "").strip().lower() in {"1", "true", "yes"}
    try:
        parsed = urlsplit(endpoint)
        host = parsed.hostname or ""
        try:
            loopback = host == "localhost" or ipaddress.ip_address(host).is_loopback
        except ValueError:
            loopback = False
        valid = (
            parsed.scheme in {"http", "https", "ws", "wss"}
            and bool(host)
            and parsed.port != 0
            and parsed.username is None
            and parsed.password is None
            and not parsed.query
            and not parsed.fragment
            and not any(char.isspace() or ord(char) < 32 for char in endpoint)
            and (parsed.scheme in {"https", "wss"} or (loopback and allow_insecure_loopback))
        )
    except ValueError:
        valid = False
    if not valid:
        raise ValueError(
            "GPT Live endpoint requires TLS and must not contain URL credentials, query strings, or fragments; "
            f"local plaintext development requires {INSECURE_LOOPBACK_ENV}=true"
        )


def live_trace_config() -> aiohttp.TraceConfig:
    """Reject redirects before aiohttp can forward an authenticated handshake."""
    trace = aiohttp.TraceConfig()

    async def reject_redirect(*_: Any) -> None:
        raise RuntimeError("GPT Live redirects are not permitted")

    trace.on_request_redirect.append(reject_redirect)
    return trace
