"""Configurable, best-effort secret removal from persisted diagnostic payloads."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterable
from functools import lru_cache

REDACTED = "[redacted]"
REDACT_FIELDS_ENV = "GPT_LIVE_EVALS_REDACT_FIELDS"
DEFAULT_FIELDS = frozenset(
    {
        "authorization",
        "proxyauthorization",
        "apikey",
        "xapikey",
        "openaiapikey",
        "openairesponsesapikey",
        "token",
        "authtoken",
        "bearertoken",
        "sessiontoken",
        "servicetoken",
        "openaiclientassistanttoken",
        "accesstoken",
        "refreshtoken",
        "idtoken",
        "password",
        "passwd",
        "secret",
        "clientsecret",
        "secretkey",
        "privatekey",
        "cookie",
        "setcookie",
        "credential",
        "credentials",
    }
)
_BEARER = re.compile(r"(?i)\b(bearer|basic)\s+[^\s,;\"'<>]+")
_OPENAI_KEY = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}")
_URL_USERINFO = re.compile(r"(?i)(https?://|wss?://)[^\s/@]+@")


def normalized_field(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _environment_secrets() -> tuple[str, ...]:
    return tuple(
        value
        for name, value in os.environ.items()
        if len(value) >= 8 and normalized_field(name).endswith(("apikey", "token", "password", "secret"))
    )


@lru_cache(maxsize=4)
def _configured_redactor(fields: str, secrets: tuple[str, ...]) -> TraceRedactor:
    return TraceRedactor(fields=fields.split(","), secrets=secrets)


def default_redactor() -> TraceRedactor:
    """Reuse compiled patterns while noticing environment changes between runs."""
    return _configured_redactor(os.getenv(REDACT_FIELDS_ENV, ""), _environment_secrets())


class TraceRedactor:
    """Redact known fields, embedded JSON, and common credential-bearing error text."""

    def __init__(self, *, fields: Iterable[str] = (), secrets: Iterable[str] = ()) -> None:
        configured = os.getenv(REDACT_FIELDS_ENV, "").split(",")
        self.fields = DEFAULT_FIELDS | {normalized_field(name) for name in [*configured, *fields] if name.strip()}
        environment_secrets = _environment_secrets()
        self.secrets = sorted({value for value in [*environment_secrets, *secrets] if value}, key=len, reverse=True)
        # Separators may differ between JSON, headers, query strings, and exception text.
        names = [r"[-_ ]*".join(re.escape(char) for char in name) for name in sorted(self.fields)]
        self.assignment = re.compile(
            r"(?i)(?<![\w])((?:" + "|".join(names) + r")[\"']?\s*[:=]\s*)(?:\"[^\"]*\"|'[^']*'|[^\s&,;\}\]]+)"
        )

    def text(self, value: str) -> str:
        for secret in self.secrets:
            value = value.replace(secret, REDACTED)
        value = _BEARER.sub(lambda match: match.group(1) + " " + REDACTED, value)
        value = _OPENAI_KEY.sub(REDACTED, value)
        value = _URL_USERINFO.sub(lambda match: match.group(1) + REDACTED + "@", value)
        return self.assignment.sub(lambda match: match.group(1) + REDACTED, value)

    def sanitize(self, value: object, *, max_string_length: int = 800) -> object:
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                if normalized_field(str(key)) in self.fields:
                    result[key] = REDACTED
                elif (
                    key == "audio" or key == "delta" and value.get("type") == "session.output_audio.delta"
                ) and isinstance(item, str):
                    result[key] = f"[base64 PCM; {len(item)} characters]"
                else:
                    result[key] = self.sanitize(item, max_string_length=max_string_length)
            return result
        if isinstance(value, (list, tuple)):
            return [self.sanitize(item, max_string_length=max_string_length) for item in value]
        if isinstance(value, str):
            embedded_json = False
            if value.lstrip().startswith(("{", "[")):
                try:
                    embedded = json.loads(value)
                except (ValueError, RecursionError):
                    pass
                else:
                    if isinstance(embedded, (dict, list)):
                        value = json.dumps(
                            self.sanitize(embedded, max_string_length=max_string_length), ensure_ascii=False
                        )
                        embedded_json = True
            if not embedded_json:
                value = self.text(value)
            if len(value) > max_string_length:
                return f"{value[:max_string_length]}...[truncated {len(value) - max_string_length} chars]"
        return value
