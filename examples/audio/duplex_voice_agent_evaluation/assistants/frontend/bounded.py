"""Opt-in transport policy and finalization validation for finite Live callers."""

from __future__ import annotations

import math
from typing import Any
from urllib.parse import urlsplit
from urllib.request import getproxies, proxy_bypass

import aiohttp

from assistants.frontend.security import live_trace_config

SUPPORTED_AIOHTTP_VERSION = "3.14.3"


def exception_classes(error: BaseException) -> list[str]:
    """Retain diagnostic classes without exception text, URLs, or credentials."""
    classes: list[str] = []
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen and len(classes) < 16:
        seen.add(id(current))
        classes.append(type(current).__name__)
        current = current.__cause__ or (None if current.__suppress_context__ else current.__context__)
    return classes


def bounded_trace_config(observations: dict[str, Any]) -> aiohttp.TraceConfig:
    """Count transport activity without recording destinations or header values."""
    trace = live_trace_config()

    async def connection_started(*_: Any) -> None:
        observations["connection_attempts"] += 1

    async def headers_sent(*_: Any) -> None:
        observations["request_headers_sent"] += 1

    async def request_failed(_session: Any, _context: Any, params: Any) -> None:
        observations["error_classes"] = exception_classes(params.exception)

    trace.on_connection_create_start.append(connection_started)
    trace.on_request_headers_sent.append(headers_sent)
    trace.on_request_exception.append(request_failed)
    return trace


def check_transport_support() -> None:
    """Require the tested transport version before creating a session or reading keys."""
    if aiohttp.__version__ != SUPPORTED_AIOHTTP_VERSION or not hasattr(aiohttp, "ClientWSTimeout"):
        raise RuntimeError("This aiohttp version cannot support the bounded Live transport")


def configured_proxy(url: str) -> str | None:
    """Honor configured WSS/HTTPS proxies and NO_PROXY without exposing values."""
    parts = urlsplit(url)
    if proxy_bypass(parts.hostname or ""):
        return None
    proxies = getproxies()
    scheme = {"wss": "https", "ws": "http"}.get(parts.scheme, parts.scheme)
    proxy = proxies.get(parts.scheme) or proxies.get(scheme) or proxies.get("all")
    if proxy and urlsplit(proxy).scheme not in {"http", "https"}:
        raise ValueError("Configured proxy scheme is unsupported by the Live transport")
    return proxy


def disable_connection_retry(session: aiohttp.ClientSession) -> None:
    """Fail before dispatch if aiohttp's internal one-retry switch changes.

    aiohttp currently exposes no public constructor option for this behavior.
    Keep the compatibility dependency isolated and covered by a real-session
    offline test; silently allowing the default is unsafe for a finite caller.
    """
    if type(getattr(session, "_retry_connection", None)) is not bool:
        raise RuntimeError("This aiohttp version cannot enforce one handshake attempt")
    session._retry_connection = False
    if session._retry_connection is not False:
        raise RuntimeError("Could not disable automatic connection retry")


def valid_start(event: Any, model: str) -> bool:
    if not isinstance(event, dict) or event.get("type") != "session.started" or event.get("_synthetic"):
        return False
    session = event.get("session")
    return (
        isinstance(session, dict)
        and isinstance(session.get("id"), str)
        and bool(session["id"])
        and session.get("model") == model
    )


def confirmed_close(start: Any, final: Any, model: str) -> bool:
    """A local/synthetic terminal event cannot establish provider final usage."""
    if not valid_start(start, model) or not isinstance(final, dict):
        return False
    if final.get("type") != "session.closed" or final.get("_synthetic"):
        return False
    session, usage = final.get("session"), final.get("usage")
    if not isinstance(session, dict) or not isinstance(usage, dict):
        return False
    seconds = usage.get("seconds")
    if type(seconds) not in {int, float}:
        return False
    try:
        finite = math.isfinite(seconds)
    except OverflowError:
        return False
    return session.get("id") == start["session"]["id"] and session.get("model") == model and finite and seconds >= 0
