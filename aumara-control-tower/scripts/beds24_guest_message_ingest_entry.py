#!/usr/bin/env python3
"""Credential-backed entrypoint for read-only Beds24 message ingestion.

This entrypoint reuses the credential-mode detection proven by PR #14. It
accepts the existing secret as either an access token or refresh credential,
performs read-only authentication probes, and then calls the GET-only ingestion
worker. It never calls /authentication/setup and has no write endpoint.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
from typing import Any

import beds24_auth_check as auth
import beds24_guest_message_ingest as ingest


def resolve_access_token() -> tuple[str, str, str, str]:
    """Resolve the existing credential without printing or replacing it."""
    credential = auth.get_credential()
    if not credential:
        raise ingest.IngestError("BEDS24_TOKEN_CREDENTIAL is missing")

    direct_status, _ = auth.request_json(
        f"{auth.API_BASE}/authentication/details",
        {"token": credential},
        secrets=(credential,),
    )
    if 200 <= direct_status < 300:
        return credential, "access_token", auth.API_BASE, auth.CREDENTIAL_SOURCE

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

    probe_status, _ = auth.request_json(
        f"{auth.API_BASE}/authentication/details",
        {"token": access_token},
        secrets=(credential, access_token),
    )
    if not 200 <= probe_status < 300:
        raise ingest.IngestError(
            "Beds24 temporary access-token probe failed with HTTP "
            f"{probe_status}"
        )
    return access_token, "refresh_token", auth.API_BASE, auth.CREDENTIAL_SOURCE


def build_report(max_age_days: int) -> dict[str, Any]:
    token, auth_mode, api_base, auth_source = resolve_access_token()
    client = ingest.Beds24ReadOnlyClient(token, api_base)
    report = ingest.run(client, max_age_days=max_age_days)
    report["authentication"] = {
        "mode": auth_mode,
        "source": auth_source,
        "apiHost": urllib.parse.urlparse(api_base).netloc,
        "secretLogged": False,
    }
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
        return 0
    except (ingest.IngestError, OSError, ValueError) as exc:
        print(f"Beds24 guest-message ingestion failed safely: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
