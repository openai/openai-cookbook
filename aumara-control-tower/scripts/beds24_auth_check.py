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
import sys
import unicodedata
import urllib.error
import urllib.request
from typing import Any

API_BASE = "https://api.beds24.com/v2"
ROOT = pathlib.Path(__file__).resolve().parents[1]
EVIDENCE_PATH = ROOT / "evidence" / "beds24-auth-check.json"
ACCESS_TOKEN_FILE = pathlib.Path(
    os.environ.get("BEDS24_ACCESS_TOKEN_FILE", "/tmp/beds24-access-token")
)


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def normalize_secret(value: str | None) -> str:
    raw = (value or "").strip().strip('"').strip("'")
    return "".join(
        char
        for char in raw
        if not char.isspace() and unicodedata.category(char) not in {"Cc", "Cf"}
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


def request_json(url: str, headers: dict[str, str]) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(
        url,
        headers={"accept": "application/json", **headers},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            raw = response.read().decode("utf-8", "replace")
            try:
                body = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                body = {}
            return response.status, body if isinstance(body, dict) else {}
    except urllib.error.HTTPError as exc:
        exc.read()
        return exc.code, {}
    except urllib.error.URLError:
        return 0, {}


def command_validate() -> int:
    credential = normalize_secret(os.environ.get("B24_TOKEN_CREDENTIAL"))
    evidence = load_evidence()
    evidence.update(
        {
            "status": "CREDENTIAL_PRESENT" if credential else "AUTH_FAILED",
            "credential_source": "B24_TOKEN_CREDENTIAL",
            "token_exchange_http_status": None,
            "readonly_probe_http_status": None,
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
            "credential_source": "B24_TOKEN_CREDENTIAL",
            "secret_present": bool(credential),
            "secret_length": len(credential),
        }
    )
    if not credential:
        evidence["status"] = "AUTH_FAILED"
        save_evidence(evidence)
        print("Missing GitHub Actions secret B24_TOKEN_CREDENTIAL", file=sys.stderr)
        return 1

    status, body = request_json(
        f"{API_BASE}/authentication/token",
        {"refreshToken": credential},
    )
    evidence["token_exchange_http_status"] = status
    token = body.get("token") if isinstance(body, dict) else None
    if not (200 <= status < 300 and isinstance(token, str) and token):
        evidence["status"] = "AUTH_FAILED"
        save_evidence(evidence)
        print(
            f"Beds24 refresh-token exchange failed with HTTP status {status}.",
            file=sys.stderr,
        )
        return 1

    ACCESS_TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    ACCESS_TOKEN_FILE.write_text(token, encoding="utf-8")
    ACCESS_TOKEN_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)
    evidence["status"] = "TOKEN_EXCHANGED"
    save_evidence(evidence)
    print("Beds24 access token created in a protected temporary file.")
    return 0


def command_probe() -> int:
    evidence = load_evidence()
    try:
        if not ACCESS_TOKEN_FILE.exists():
            evidence["status"] = "AUTH_FAILED"
            save_evidence(evidence)
            print("Temporary Beds24 access token file is missing.", file=sys.stderr)
            return 1

        access_token = normalize_secret(ACCESS_TOKEN_FILE.read_text(encoding="utf-8"))
        if not access_token:
            evidence["status"] = "AUTH_FAILED"
            save_evidence(evidence)
            print("Temporary Beds24 access token file is empty.", file=sys.stderr)
            return 1

        status, _ = request_json(
            f"{API_BASE}/authentication/details",
            {"token": access_token},
        )
        evidence["readonly_probe_http_status"] = status
        if 200 <= status < 300:
            evidence["status"] = "AUTH_OK"
            save_evidence(evidence)
            print("Beds24 read-only authentication probe succeeded.")
            return 0

        evidence["status"] = "AUTH_FAILED"
        save_evidence(evidence)
        print(
            f"Beds24 read-only authentication probe failed with HTTP status {status}.",
            file=sys.stderr,
        )
        return 1
    finally:
        try:
            ACCESS_TOKEN_FILE.unlink(missing_ok=True)
        except OSError:
            pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("validate", "exchange", "probe"))
    return parser.parse_args()


def main() -> int:
    command = parse_args().command
    if command == "validate":
        return command_validate()
    if command == "exchange":
        return command_exchange()
    return command_probe()


if __name__ == "__main__":
    raise SystemExit(main())
