#!/usr/bin/env python3
"""Credential-backed entrypoint for read-only Beds24 message ingestion.

This entrypoint reuses the credential-mode detection proven by PR #14. It
accepts the existing secret as either an access token or refresh credential,
performs read-only authentication probes, and then calls the GET-only ingestion
worker. It never calls /authentication/setup and has no write endpoint.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
import urllib.parse
from typing import Any

import beds24_auth_check as auth
import beds24_guest_message_ingest as ingest


KNOWN_SCOPES = {
    "accounts",
    "bookings",
    "bookings-financial",
    "bookings-personal",
    "channels",
    "inventory",
    "properties",
}


def extract_scope_names(value: Any) -> list[str]:
    """Extract only recognized scope names from sanitized auth diagnostics."""
    found: set[str] = set()

    def visit(item: Any) -> None:
        if isinstance(item, dict):
            for nested in item.values():
                visit(nested)
        elif isinstance(item, list):
            for nested in item:
                visit(nested)
        elif isinstance(item, str):
            for token in re.findall(r"[a-z]+(?:-[a-z]+)*", item.casefold()):
                if token in KNOWN_SCOPES:
                    found.add(token)

    visit(value)
    return sorted(found)


def resolve_access_token() -> tuple[str, str, str, str, list[str]]:
    """Resolve the existing credential without printing or replacing it."""
    credential = auth.get_credential()
    if not credential:
        raise ingest.IngestError("BEDS24_TOKEN_CREDENTIAL is missing")

    direct_status, direct_body = auth.request_json(
        f"{auth.API_BASE}/authentication/details",
        {"token": credential},
        secrets=(credential,),
    )
    if 200 <= direct_status < 300:
        return (
            credential,
            "access_token",
            auth.API_BASE,
            auth.CREDENTIAL_SOURCE,
            extract_scope_names(direct_body),
        )

    exchange_status, exchange_body = auth.request_json(
        f"{auth.API_BASE}/authentication/token",
        {"refreshToken": credential},
        secrets=(credential,),
        redact=False,
    )
    access_token = auth.normalize_secret(
        str(exchange_body.get("token") or "")
        if isinstance(exchange_body, dict)
        else ""
    )
    if not 200 <= exchange_status < 300 or not access_token:
        raise ingest.IngestError(
            "Beds24 credential failed access-token probe and refresh-token "
            f"exchange (HTTP {direct_status}/{exchange_status})"
        )

    probe_status, probe_body = auth.request_json(
        f"{auth.API_BASE}/authentication/details",
        {"token": access_token},
        secrets=(credential, access_token),
    )
    if not 200 <= probe_status < 300:
        raise ingest.IngestError(
            "Beds24 temporary access-token probe failed with HTTP "
            f"{probe_status}"
        )
    return (
        access_token,
        "refresh_token",
        auth.API_BASE,
        auth.CREDENTIAL_SOURCE,
        extract_scope_names(probe_body),
    )


def authentication_metadata(
    auth_mode: str,
    api_base: str,
    auth_source: str,
    scopes: list[str],
) -> dict[str, Any]:
    return {
        "mode": auth_mode,
        "source": auth_source,
        "apiHost": urllib.parse.urlparse(api_base).netloc,
        "scopes": scopes,
        "bookingsPersonalScopePresent": (
            "bookings-personal" in scopes if scopes else None
        ),
        "secretLogged": False,
    }


def blocked_report(
    *,
    error: str,
    auth_mode: str,
    api_base: str,
    auth_source: str,
    scopes: list[str],
    max_age_days: int,
) -> dict[str, Any]:
    missing_scope = bool(scopes) and "bookings-personal" not in scopes
    return {
        "schema": "aumara-beds24-guest-message-ingest-v1",
        "generatedAtUtc": ingest.iso_timestamp(dt.datetime.now(dt.timezone.utc)),
        "propertyId": ingest.PROPERTY_ID,
        "windowDays": max_age_days,
        "status": "BLOCKED",
        "summary": {
            "messagesScanned": 0,
            "guestMessages": 0,
            "hostMessages": 0,
            "eventsNormalized": 0,
            "conversations": 0,
            "unansweredConversations": 0,
            "bookingsResolved": 0,
            "duplicates": 0,
            "manualReview": 0,
            "unsupportedSources": 0,
        },
        "blocker": {
            "code": (
                "MISSING_BOOKINGS_PERSONAL_SCOPE"
                if missing_scope
                else "BOOKINGS_PERSONAL_ACCESS_DENIED"
            ),
            "requiredScope": "bookings-personal",
            "httpStatus": 401,
            "detail": error,
        },
        "authentication": authentication_metadata(
            auth_mode, api_base, auth_source, scopes
        ),
        "safety": {
            "httpMethods": ["GET"],
            "guestMessagesSent": 0,
            "bookingMutations": 0,
            "rawGuestMessagePersisted": False,
            "guestContactDataPersisted": False,
            "rawBookingIdPersisted": False,
        },
        "events": [],
        "conversations": [],
    }


def build_report(max_age_days: int) -> dict[str, Any]:
    token, auth_mode, api_base, auth_source, scopes = resolve_access_token()
    client = ingest.Beds24ReadOnlyClient(token, api_base)
    try:
        report = ingest.run(client, max_age_days=max_age_days)
    except ingest.IngestError as exc:
        text = str(exc)
        if "message lookup failed with HTTP 401" in text:
            return blocked_report(
                error=text,
                auth_mode=auth_mode,
                api_base=api_base,
                auth_source=auth_source,
                scopes=scopes,
                max_age_days=max_age_days,
            )
        raise
    report["status"] = "OK"
    report["authentication"] = authentication_metadata(
        auth_mode, api_base, auth_source, scopes
    )
    return report


def main() -> int:
    try:
        max_age_days = int(os.environ.get("BEDS24_MESSAGE_MAX_AGE_DAYS", "3"))
        report = build_report(max_age_days)
        ingest.OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        ingest.OUTPUT.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(report["summary"], sort_keys=True))
        if report.get("status") == "BLOCKED":
            blocker = report.get("blocker") or {}
            print(
                "Beds24 guest-message ingestion blocked safely: "
                f"{blocker.get('code')}; required scope="
                f"{blocker.get('requiredScope')}",
                file=sys.stderr,
            )
            return 2
        return 0
    except (ingest.IngestError, OSError, ValueError) as exc:
        print(f"Beds24 guest-message ingestion failed safely: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
