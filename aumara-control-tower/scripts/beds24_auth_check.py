#!/usr/bin/env python3
"""Safely verify the existing Beds24 API V2 credential.

The stored credential may be either an access token or a refresh credential.
The checker first calls the read-only authentication details endpoint. Only if
that fails does it attempt a refresh-token exchange and repeat the read-only
probe with the temporary access token. It never calls /authentication/setup
and never creates, changes, or cancels bookings.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import sys
import unicodedata
import urllib.error
import urllib.request
from typing import Any

API_BASE = "https://api.beds24.com/v2"
ROOT = pathlib.Path(__file__).resolve().parents[1]
EVIDENCE_PATH = ROOT / "evidence" / "beds24-auth-check.json"
CREDENTIAL_SOURCE = "BEDS24_TOKEN_CREDENTIAL"
REDACTED = "[REDACTED]"
DIAGNOSTIC_FIELDS = (
    "diagnostics",
    "message",
    "error",
    "detail",
    "error_description",
    "code",
    "status",
    "type",
)
SENSITIVE_KEYS = {"token", "refreshtoken", "accesstoken", "secret"}


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def normalize_secret(value: str | None) -> str:
    raw = (value or "").strip().strip('"').strip("'")
    return "".join(
        char
        for char in raw
        if not char.isspace() and unicodedata.category(char) not in {"Cc", "Cf"}
    )


def redact_text(value: str, secrets: tuple[str, ...]) -> str:
    redacted = value
    for secret in secrets:
        normalized = normalize_secret(secret)
        if normalized:
            redacted = redacted.replace(normalized, REDACTED)
    return redacted


def sanitize_value(value: Any, secrets: tuple[str, ...]) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            if str(key).lower() in SENSITIVE_KEYS:
                sanitized[str(key)] = REDACTED
            else:
                sanitized[str(key)] = sanitize_value(item, secrets)
        return sanitized
    if isinstance(value, list):
        return [sanitize_value(item, secrets) for item in value]
    if isinstance(value, str):
        return redact_text(value, secrets)
    return value


def parse_response(raw: bytes, secrets: tuple[str, ...] = ()) -> dict[str, Any]:
    text = raw.decode("utf-8", "replace")
    if not text:
        return {}
    try:
        body = json.loads(text)
    except json.JSONDecodeError:
        return {"message": redact_text(text, secrets)}
    if isinstance(body, dict):
        return body
    return {"message": json.dumps(body, ensure_ascii=False)}


def sanitize_response_body(
    body: dict[str, Any], secrets: tuple[str, ...]
) -> dict[str, Any]:
    sanitized = sanitize_value(body, secrets)
    if isinstance(sanitized, dict):
        return sanitized
    return {"message": json.dumps(sanitized, ensure_ascii=False)}


def extract_diagnostics(body: dict[str, Any]) -> dict[str, Any]:
    diagnostics = {
        key: value
        for key in DIAGNOSTIC_FIELDS
        if (value := body.get(key)) not in (None, "", [], {})
    }
    if diagnostics:
        return diagnostics
    if body:
        return {"body_keys": sorted(body.keys())}
    return {}


def summarize_diagnostics(diagnostics: dict[str, Any]) -> str:
    if not diagnostics:
        return "no Beds24 diagnostics returned"
    return ", ".join(
        f"{key}={json.dumps(value, ensure_ascii=False)}"
        for key, value in diagnostics.items()
    )


def load_evidence() -> dict[str, Any]:
    if EVIDENCE_PATH.exists():
        try:
            value = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                return value
        except (OSError, json.JSONDecodeError):
            pass
    return {
        "checked_at_utc": now_utc(),
        "status": "NOT_RUN",
        "credential_source": CREDENTIAL_SOURCE,
        "credential_mode": None,
        "direct_probe_http_status": None,
        "direct_probe_valid_token": None,
        "token_exchange_http_status": None,
        "readonly_probe_http_status": None,
        "readonly_probe_valid_token": None,
        "direct_probe_diagnostics": {},
        "token_exchange_diagnostics": {},
        "readonly_probe_diagnostics": {},
        "failure_stage": None,
        "secret_present": False,
        "secret_length": 0,
        "secret_exposed": False,
    }


def save_evidence(evidence: dict[str, Any]) -> None:
    EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    evidence["checked_at_utc"] = now_utc()
    evidence["secret_exposed"] = False
    EVIDENCE_PATH.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def get_credential() -> str:
    return normalize_secret(os.environ.get(CREDENTIAL_SOURCE))


def request_json(
    url: str,
    headers: dict[str, str],
    secrets: tuple[str, ...] = (),
    *,
    redact: bool = True,
) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(
        url,
        headers={"accept": "application/json", **headers},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            body = parse_response(response.read(), secrets)
            if redact:
                return response.status, sanitize_response_body(body, secrets)
            return response.status, body
    except urllib.error.HTTPError as exc:
        body = parse_response(exc.read(), secrets)
        if redact:
            return exc.code, sanitize_response_body(body, secrets)
        return exc.code, body
    except urllib.error.URLError:
        return 0, {}


def command_validate() -> int:
    credential = get_credential()
    evidence = load_evidence()
    evidence.update(
        {
            "status": "CREDENTIAL_PRESENT" if credential else "AUTH_FAILED",
            "credential_source": CREDENTIAL_SOURCE,
            "credential_mode": None,
            "direct_probe_http_status": None,
            "direct_probe_valid_token": None,
            "token_exchange_http_status": None,
            "readonly_probe_http_status": None,
            "readonly_probe_valid_token": None,
            "direct_probe_diagnostics": {},
            "token_exchange_diagnostics": {},
            "readonly_probe_diagnostics": {},
            "failure_stage": None if credential else "validate",
            "secret_present": bool(credential),
            "secret_length": len(credential),
        }
    )
    save_evidence(evidence)
    if not credential:
        print("Missing GitHub Actions secret BEDS24_TOKEN_CREDENTIAL", file=sys.stderr)
        return 1
    print("Beds24 credential is present; value was not printed.")
    return 0


def command_authenticate() -> int:
    credential = get_credential()
    evidence = load_evidence()
    evidence.update(
        {
            "credential_source": CREDENTIAL_SOURCE,
            "credential_mode": None,
            "direct_probe_http_status": None,
            "direct_probe_valid_token": None,
            "token_exchange_http_status": None,
            "readonly_probe_http_status": None,
            "readonly_probe_valid_token": None,
            "direct_probe_diagnostics": {},
            "token_exchange_diagnostics": {},
            "readonly_probe_diagnostics": {},
            "secret_present": bool(credential),
            "secret_length": len(credential),
            "failure_stage": None,
        }
    )
    if not credential:
        evidence["status"] = "AUTH_FAILED"
        evidence["failure_stage"] = "validate"
        save_evidence(evidence)
        print("Missing GitHub Actions secret BEDS24_TOKEN_CREDENTIAL", file=sys.stderr)
        return 1

    direct_status, direct_body = request_json(
        f"{API_BASE}/authentication/details",
        {"token": credential},
        secrets=(credential,),
    )
    evidence["direct_probe_http_status"] = direct_status
    direct_valid = (
        direct_body.get("validToken")
        if isinstance(direct_body.get("validToken"), bool)
        else None
    )
    evidence["direct_probe_valid_token"] = direct_valid
    evidence["direct_probe_diagnostics"] = extract_diagnostics(
        sanitize_response_body(direct_body, (credential,))
    )
    if 200 <= direct_status < 300 and direct_valid is True:
        evidence["status"] = "AUTH_OK"
        evidence["credential_mode"] = "access_token"
        evidence["readonly_probe_http_status"] = direct_status
        evidence["readonly_probe_diagnostics"] = evidence["direct_probe_diagnostics"]
        save_evidence(evidence)
        print("Beds24 read-only authentication probe succeeded with access token.")
        return 0

    exchange_status, exchange_body = request_json(
        f"{API_BASE}/authentication/token",
        {"refreshToken": credential},
        secrets=(credential,),
        redact=False,
    )
    access_token = exchange_body.get("token") if isinstance(exchange_body, dict) else None
    secrets = tuple(
        item
        for item in (credential, access_token)
        if isinstance(item, str) and item
    )
    evidence["token_exchange_http_status"] = exchange_status
    evidence["token_exchange_diagnostics"] = extract_diagnostics(
        sanitize_response_body(exchange_body, secrets)
    )
    if not (
        200 <= exchange_status < 300
        and isinstance(access_token, str)
        and access_token
    ):
        evidence["status"] = "AUTH_FAILED"
        evidence["failure_stage"] = "credential"
        save_evidence(evidence)
        print(
            "Beds24 credential failed both direct access-token probe and "
            f"refresh-token exchange (HTTP {direct_status}/{exchange_status}).",
            file=sys.stderr,
        )
        return 1

    probe_status, probe_body = request_json(
        f"{API_BASE}/authentication/details",
        {"token": access_token},
        secrets=secrets,
    )
    evidence["readonly_probe_http_status"] = probe_status
    probe_valid = (
        probe_body.get("validToken")
        if isinstance(probe_body.get("validToken"), bool)
        else None
    )
    evidence["readonly_probe_valid_token"] = probe_valid
    evidence["readonly_probe_diagnostics"] = extract_diagnostics(
        sanitize_response_body(probe_body, secrets)
    )
    if 200 <= probe_status < 300 and probe_valid is True:
        evidence["status"] = "AUTH_OK"
        evidence["credential_mode"] = "refresh_token"
        evidence["failure_stage"] = None
        save_evidence(evidence)
        print("Beds24 read-only authentication probe succeeded after token exchange.")
        return 0

    evidence["status"] = "AUTH_FAILED"
    evidence["credential_mode"] = "refresh_token"
    evidence["failure_stage"] = "probe"
    save_evidence(evidence)
    print(
        f"Beds24 temporary access-token probe failed with HTTP status {probe_status}.",
        file=sys.stderr,
    )
    return 1


def command_report() -> int:
    if not EVIDENCE_PATH.exists():
        print("Beds24 authentication evidence was not created.", file=sys.stderr)
        return 1
    evidence = load_evidence()
    if evidence.get("status") == "AUTH_OK":
        mode = evidence.get("credential_mode") or "unknown"
        print(f"Beds24 authentication probe succeeded; credential mode={mode}.")
        return 0

    stage = evidence.get("failure_stage") or "unknown"
    diagnostics = {
        "direct_probe_http_status": evidence.get("direct_probe_http_status"),
        "token_exchange_http_status": evidence.get("token_exchange_http_status"),
        "readonly_probe_http_status": evidence.get("readonly_probe_http_status"),
        "direct_probe": evidence.get("direct_probe_diagnostics") or {},
        "exchange": evidence.get("token_exchange_diagnostics") or {},
        "probe": evidence.get("readonly_probe_diagnostics") or {},
    }
    print(
        f"Beds24 authentication failed during {stage}; "
        f"{summarize_diagnostics(diagnostics)}.",
        file=sys.stderr,
    )
    return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("validate", "authenticate", "report"))
    return parser.parse_args()


def main() -> int:
    command = parse_args().command
    if command == "validate":
        return command_validate()
    if command == "authenticate":
        return command_authenticate()
    return command_report()


if __name__ == "__main__":
    raise SystemExit(main())
