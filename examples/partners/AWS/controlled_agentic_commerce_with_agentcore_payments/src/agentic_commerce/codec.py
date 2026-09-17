"""Base64 JSON helpers used by the protocol-shaped local transport."""

from __future__ import annotations

import base64
import json
from typing import Any

from pydantic import BaseModel

from .errors import ProtocolError


def encode_model(model: BaseModel) -> str:
    """Serialize a model to standard Base64-encoded JSON."""

    payload = model.model_dump_json(by_alias=True, exclude_none=True)
    return base64.b64encode(payload.encode("utf-8")).decode("ascii")


def decode_json(value: str, *, header_name: str) -> dict[str, Any]:
    """Decode a Base64 JSON header without leaking its raw value in errors."""

    try:
        decoded = base64.b64decode(value, validate=True)
        payload = json.loads(decoded)
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError(
            "malformed_protocol_header",
            f"{header_name} is not valid Base64-encoded JSON.",
        ) from exc

    if not isinstance(payload, dict):
        raise ProtocolError(
            "malformed_protocol_header",
            f"{header_name} must decode to a JSON object.",
        )
    return payload
