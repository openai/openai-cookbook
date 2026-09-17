"""Authentication and resource limits for the reference client service."""

from __future__ import annotations

import hmac
import math
import os
from dataclasses import dataclass
from urllib.parse import urlsplit

from assistants.frontend.security import validate_live_endpoint

TOKEN_ENV = "OPENAI_CLIENT_ASSISTANT_TOKEN"
INSECURE_LOOPBACK_ENV = "OPENAI_CLIENT_ASSISTANT_ALLOW_INSECURE_LOOPBACK"


def service_token(value: str | None = None) -> str:
    """Require a dedicated secret without putting its value in errors or settings."""
    token = os.getenv(TOKEN_ENV, "") if value is None else value
    if not 32 <= len(token) <= 512 or any(not 33 <= ord(char) <= 126 for char in token):
        raise ValueError(f"{TOKEN_ENV} must contain a separate random token of at least 32 characters")
    if any(
        hmac.compare_digest(token.encode("ascii"), os.getenv(name, "").encode("utf-8"))
        for name in ("OPENAI_API_KEY", "OPENAI_RESPONSES_API_KEY")
    ):
        raise ValueError(f"{TOKEN_ENV} must not reuse an OpenAI API key")
    return token


def validate_origin(origin: str) -> str:
    parsed = urlsplit(origin)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
        or origin == "null"
    ):
        raise ValueError("Allowed Origins must be exact HTTP(S) origins without paths or credentials")
    return origin


def validate_endpoint(endpoint: str, *, allow_insecure_loopback: bool | None = None) -> str:
    """Never send the service bearer token over a remote plaintext connection."""
    if allow_insecure_loopback is None:
        allow_insecure_loopback = os.getenv(INSECURE_LOOPBACK_ENV, "").strip().lower() in {"1", "true", "yes"}
    try:
        validate_live_endpoint(endpoint, allow_insecure_loopback=allow_insecure_loopback)
    except ValueError:
        raise ValueError(
            "Client assistant endpoint requires TLS and must not contain credentials; "
            f"local plaintext development requires {INSECURE_LOOPBACK_ENV}=true"
        ) from None
    return endpoint


@dataclass(frozen=True, slots=True)
class ServiceLimits:
    max_connections: int = 8
    max_pending_delegations: int = 4
    max_delegations: int = 64
    max_message_bytes: int = 256 * 1024
    max_session_bytes: int = 8 * 1024 * 1024
    max_events: int = 20_000
    configure_timeout: float = 10
    session_timeout: float = 600
    delegation_timeout: float = 60
    cleanup_timeout: float = 5

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if name.startswith("max_"):
                valid = type(value) is int and value > 0
            else:
                valid = type(value) in {int, float} and math.isfinite(value) and value > 0
            if not valid:
                raise ValueError("Client service limits must be finite positive numbers; counts must be integers")
