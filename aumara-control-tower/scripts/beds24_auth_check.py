#!/usr/bin/env python3
"""Safely validate the existing Beds24 refresh credential.

This script only performs read-only authentication checks. It never calls
/authentication/setup and never creates, changes, or cancels bookings.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import stat
import subprocess
import sys
import tempfile
import unicodedata
import urllib.error
import urllib.request
from typing import Any

API_BASE = "https://api.beds24.com/v2"
ROOT = pathlib.Path(__file__).resolve().parents[1]
EVIDENCE_PATH = ROOT / "evidence" / "beds24-auth-check.json"
ENCRYPTED_REFRESH_FILE = ROOT / "vault" / "beds24-refresh-token.enc"
ACCESS_TOKEN_FILE = pathlib.Path(
    os.environ.get("BEDS24_ACCESS_TOKEN_FILE", "/tmp/beds24-access-token")
)
REDACTED = "[REDACTED]"
DECRYPT_FAILED_MESSAGE = "Failed to decrypt Beds24 refresh token vault."
DECRYPT_EMPTY_MESSAGE = "Beds24 refresh token vault decrypted to an empty value."
DIAGNOSTIC_FIELDS = (
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


def credential_source() -> str:
    if ENCRYPTED_REFRESH_FILE.exists():
        try:
            return str(ENCRYPTED_REFRESH_FILE.relative_to(ROOT))
        except ValueError:
            return str(ENCRYPTED_REFRESH_FILE)
    return "B24_TOKEN_CREDENTIAL"


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
    """Recursively redact secret-bearing keys and secret text from response data."""
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
    """Parse an HTTP response body into a dictionary for downstream handling."""
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


def sanitize_response_body(body: dict[str, Any], secrets: tuple[str, ...]) -> dict[str, Any]:
    """Convert a response payload into a persisted diagnostic dict with redactions."""
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


def primary_diagnostic(diagnostics: dict[str, Any]) -> str | None:
    """Return the highest-priority human-readable diagnostic string, if any."""
    for key in ("message", "detail", "error", "error_description"):
        value = diagnostics.get(key)
        if isinstance(value, str) and value:
            return value
    return None


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
        "credential_source": "B24_TOKEN_CREDENTIAL",
        "token_exchange_http_status": None,
        "readonly_probe_http_status": None,
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


def resolve_refresh_token(
    credential: str,
) -> tuple[str, str | None, dict[str, Any] | None]:
    source = credential_source()
    if not ENCRYPTED_REFRESH_FILE.exists():
        return source, credential, None

    with tempfile.NamedTemporaryFile(prefix="beds24-refresh-", delete=False) as handle:
        output_path = pathlib.Path(handle.name)
    output_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    try:
        environment = os.environ.copy()
        environment["BEDS24_VAULT_PASSPHRASE"] = credential
        proc = subprocess.run(
            [
                "openssl",
                "enc",
                "-d",
                "-aes-256-cbc",
                "-pbkdf2",
                "-iter",
                "200000",
                "-pass",
                "env:BEDS24_VAULT_PASSPHRASE",
                "-in",
                str(ENCRYPTED_REFRESH_FILE),
                "-out",
                str(output_path),
            ],
            env=environment,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0 or not output_path.exists():
            diagnostics: dict[str, Any] = {"message": DECRYPT_FAILED_MESSAGE}
            detail = redact_text((proc.stderr or "").strip(), (credential,))
            if detail:
                diagnostics["detail"] = detail
            return source, None, diagnostics
        try:
            refresh_token = normalize_secret(output_path.read_text(encoding="utf-8"))
        except UnicodeDecodeError:
            return source, None, {
                "message": DECRYPT_FAILED_MESSAGE,
                "detail": "Decrypted vault content was not valid UTF-8.",
            }
        if not refresh_token:
            return source, None, {"message": DECRYPT_EMPTY_MESSAGE}
        return source, refresh_token, None
    finally:
        output_path.unlink(missing_ok=True)


def request_json(
    url: str,
    headers: dict[str, str],
    secrets: tuple[str, ...] = (),
    *,
    redact: bool = True,
) -> tuple[int, dict[str, Any]]:
    """Fetch a JSON response and optionally redact provided secrets from the body."""
    request = urllib.request.Request(
        url,
        headers={"accept": "application/json", **headers},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            raw = response.read()
            body = parse_response(raw, secrets)
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
    credential = normalize_secret(os.environ.get("B24_TOKEN_CREDENTIAL"))
    evidence = load_evidence()
    evidence.update(
        {
            "status": "CREDENTIAL_PRESENT" if credential else "AUTH_FAILED",
            "credential_source": credential_source(),
            "token_exchange_http_status": None,
            "readonly_probe_http_status": None,
            "token_exchange_diagnostics": {},
            "readonly_probe_diagnostics": {},
            "failure_stage": None,
            "secret_present": bool(credential),
            "secret_length": len(credential),
        }
    )
    save_evidence(evidence)
    if not credential:
        print("Missing GitHub Actions secret B24_TOKEN_CREDENTIAL", file=sys.stderr)
        return 1
    print("B24_TOKEN_CREDENTIAL is present; value was not printed.")
    return 0


def command_exchange() -> int:
    credential = normalize_secret(os.environ.get("B24_TOKEN_CREDENTIAL"))
    evidence = load_evidence()
    evidence.update(
        {
            "credential_source": credential_source(),
            "token_exchange_http_status": None,
            "readonly_probe_http_status": None,
            "secret_present": bool(credential),
            "secret_length": len(credential),
            "token_exchange_diagnostics": {},
            "readonly_probe_diagnostics": {},
            "failure_stage": None,
        }
    )
    if not credential:
        evidence["status"] = "AUTH_FAILED"
        evidence["failure_stage"] = "validate"
        save_evidence(evidence)
        print("Missing GitHub Actions secret B24_TOKEN_CREDENTIAL", file=sys.stderr)
        return 1

    source, refresh_token, decrypt_diagnostics = resolve_refresh_token(credential)
    evidence["credential_source"] = source
    if decrypt_diagnostics:
        evidence["status"] = "AUTH_FAILED"
        evidence["failure_stage"] = "decrypt"
        evidence["token_exchange_diagnostics"] = decrypt_diagnostics
        save_evidence(evidence)
        message = decrypt_diagnostics.get("message") or DECRYPT_FAILED_MESSAGE
        if message == DECRYPT_EMPTY_MESSAGE:
            print(DECRYPT_EMPTY_MESSAGE, file=sys.stderr)
        else:
            print(DECRYPT_FAILED_MESSAGE, file=sys.stderr)
        return 1

    status, body = request_json(
        f"{API_BASE}/authentication/token",
        {"refreshToken": refresh_token},
        secrets=(refresh_token,),
        redact=False,
    )
    evidence["token_exchange_http_status"] = status
    token = body.get("token") if isinstance(body, dict) else None
    secrets = tuple(
        secret
        for secret in (refresh_token, token)
        if isinstance(secret, str) and secret
    )
    evidence["token_exchange_diagnostics"] = extract_diagnostics(
        sanitize_response_body(body, secrets)
    )
    if not (200 <= status < 300 and isinstance(token, str) and token):
        evidence["status"] = "AUTH_FAILED"
        evidence["failure_stage"] = "exchange"
        save_evidence(evidence)
        detail = primary_diagnostic(evidence["token_exchange_diagnostics"])
        print(
            f"Beds24 refresh-token exchange failed with HTTP status {status}"
            f"{': ' + detail if detail else ''}.",
            file=sys.stderr,
        )
        return 1

    ACCESS_TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    ACCESS_TOKEN_FILE.write_text(token, encoding="utf-8")
    ACCESS_TOKEN_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)
    evidence["status"] = "TOKEN_EXCHANGED"
    evidence["failure_stage"] = None
    save_evidence(evidence)
    print("Beds24 access token created in a protected temporary file.")
    return 0


def command_probe() -> int:
    evidence = load_evidence()
    try:
        if not ACCESS_TOKEN_FILE.exists():
            evidence["status"] = "AUTH_FAILED"
            evidence["failure_stage"] = "probe"
            save_evidence(evidence)
            print("Temporary Beds24 access token file is missing.", file=sys.stderr)
            return 1

        access_token = normalize_secret(ACCESS_TOKEN_FILE.read_text(encoding="utf-8"))
        if not access_token:
            evidence["status"] = "AUTH_FAILED"
            evidence["failure_stage"] = "probe"
            save_evidence(evidence)
            print("Temporary Beds24 access token file is empty.", file=sys.stderr)
            return 1

        status, body = request_json(
            f"{API_BASE}/authentication/details",
            {"token": access_token},
            secrets=(access_token,),
        )
        evidence["readonly_probe_http_status"] = status
        evidence["readonly_probe_diagnostics"] = extract_diagnostics(body)
        if 200 <= status < 300:
            evidence["status"] = "AUTH_OK"
            evidence["failure_stage"] = None
            save_evidence(evidence)
            print("Beds24 read-only authentication probe succeeded.")
            return 0

        evidence["status"] = "AUTH_FAILED"
        evidence["failure_stage"] = "probe"
        save_evidence(evidence)
        detail = primary_diagnostic(evidence["readonly_probe_diagnostics"])
        print(
            f"Beds24 read-only authentication probe failed with HTTP status {status}"
            f"{': ' + detail if detail else ''}.",
            file=sys.stderr,
        )
        return 1
    finally:
        try:
            ACCESS_TOKEN_FILE.unlink(missing_ok=True)
        except OSError:
            pass


def command_report() -> int:
    if not EVIDENCE_PATH.exists():
        print("Beds24 authentication evidence was not created.", file=sys.stderr)
        return 1

    evidence = load_evidence()
    if evidence.get("status") == "AUTH_OK":
        print("Beds24 authentication probe succeeded.")
        return 0

    stage = evidence.get("failure_stage") or "unknown"
    if stage in {"decrypt", "exchange"}:
        http_status = evidence.get("token_exchange_http_status")
        diagnostics = evidence.get("token_exchange_diagnostics") or {}
    elif stage == "probe":
        http_status = evidence.get("readonly_probe_http_status")
        diagnostics = evidence.get("readonly_probe_diagnostics") or {}
    else:
        http_status = None
        diagnostics = {}

    print(
        (
            f"Beds24 authentication failed during {stage} "
            f"(HTTP status: {http_status}); {summarize_diagnostics(diagnostics)}."
        ),
        file=sys.stderr,
    )
    return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("validate", "exchange", "probe", "report"))
    return parser.parse_args()


def main() -> int:
    command = parse_args().command
    if command == "validate":
        return command_validate()
    if command == "exchange":
        return command_exchange()
    if command == "probe":
        return command_probe()
    return command_report()


if __name__ == "__main__":
    raise SystemExit(main())
