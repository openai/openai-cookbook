#!/usr/bin/env python3
"""Seed AUMARA bookings with fixed guest LOCK_PIN = 1531.

Read-only by default (audit). Live write only with explicit confirmations.
Never prints the PIN value into evidence beyond a redacted presence flag.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import urllib.error
import urllib.parse
import urllib.request
from typing import Any
from zoneinfo import ZoneInfo

from beds24_elcid_studio_audit import AuditError, data_rows, get_access_token, request_json

PROPERTY_ID = 324882
FIXED_PIN = (os.environ.get("AUMARA_FIXED_GUEST_PIN") or "1531").strip()
NOTE_CODE = "LOCK_PIN"
MADRID = ZoneInfo("Europe/Madrid")
LIVE_CONFIRMATION = "AUMARA_FIXED_GUEST_PIN_1531_2026_08_03"
OUTPUT = pathlib.Path(
    os.environ.get(
        "AUMARA_FIXED_PIN_SEED_OUTPUT",
        "aumara-control-tower/evidence/aumara-fixed-pin-seed.json",
    )
)
TRUE = {"1", "true", "yes", "on"}


def enabled(name: str) -> bool:
    return str(os.environ.get(name) or "").strip().lower() in TRUE


def mode() -> str:
    value = str(os.environ.get("AUMARA_FIXED_PIN_MODE") or "audit").strip().lower()
    if value not in {"audit", "live"}:
        raise SystemExit("AUMARA_FIXED_PIN_MODE must be audit or live")
    if value == "live":
        if enabled("AUMARA_DISABLE_BOOKING_MUTATIONS"):
            raise SystemExit("live blocked by AUMARA_DISABLE_BOOKING_MUTATIONS")
        if not enabled("AUMARA_LIVE_BOOKING_WRITES_CONFIRMED"):
            raise SystemExit("live requires AUMARA_LIVE_BOOKING_WRITES_CONFIRMED=true")
        if os.environ.get("AUMARA_FIXED_PIN_WRITE_CONFIRMATION") != LIVE_CONFIRMATION:
            raise SystemExit("live requires exact AUMARA_FIXED_PIN_WRITE_CONFIRMATION")
    return value


def horizon() -> tuple[dt.date, dt.date]:
    today = dt.datetime.now(MADRID).date()
    days = int(os.environ.get("AUMARA_FIXED_PIN_HORIZON_DAYS") or "45")
    return today, today + dt.timedelta(days=max(1, days))


def fetch_bookings(token: str, api_base: str, start: dt.date, end: dt.date) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode(
        [
            ("propertyId", PROPERTY_ID),
            ("arrivalFrom", start.isoformat()),
            ("arrivalTo", end.isoformat()),
            ("includeGuests", "false"),
            ("includeBookingGroup", "true"),
        ]
    )
    status, response = request_json(
        "GET", f"/bookings?{query}", headers={"token": token}, api_base=api_base
    )
    if not 200 <= status < 300:
        raise AuditError(f"booking list failed HTTP {status}")
    rows = data_rows(response, "booking")
    active = {"confirmed", "new", "request"}
    out = []
    for row in rows:
        if int(row.get("propertyId") or PROPERTY_ID) != PROPERTY_ID:
            continue
        if str(row.get("status") or "").lower() not in active:
            continue
        out.append(row)
    return out


def lock_pin_text(booking: dict[str, Any]) -> str | None:
    for item in booking.get("infoItems") or []:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or item.get("name") or "").strip().upper()
        if code != NOTE_CODE:
            continue
        return str(item.get("text") or item.get("value") or "").strip() or None
    return None


def write_lock_pins(token: str, api_base: str, booking_ids: list[int]) -> None:
    payload = [
        {"id": booking_id, "infoItems": [{"code": NOTE_CODE, "text": FIXED_PIN}]}
        for booking_id in booking_ids
    ]
    if not payload:
        return
    raw = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{api_base}/bookings",
        data=raw,
        headers={
            "accept": "application/json",
            "content-type": "application/json",
            "token": token,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            body = response.read().decode("utf-8", "replace")
            status = response.status
            parsed = json.loads(body) if body else []
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise AuditError(f"LOCK_PIN write failed HTTP {exc.code}: {body[:300]}") from exc
    if status not in (200, 201) or not isinstance(parsed, list):
        raise AuditError(f"LOCK_PIN write failed HTTP {status}")
    if not all(isinstance(item, dict) and item.get("success") is True for item in parsed):
        raise AuditError("LOCK_PIN write incomplete")


def main() -> int:
    run_mode = mode()
    start, end = horizon()
    try:
        token, auth_mode, api_base, auth_source, _ = get_access_token()
    except AuditError as exc:
        payload = {
            "schema": "aumara-fixed-pin-seed-v1",
            "status": "AUTH_FAILED",
            "error": str(exc),
        }
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(payload, separators=(",", ":")))
        return 1

    bookings = fetch_bookings(token, api_base, start, end)
    already = []
    need = []
    for booking in bookings:
        bid = int(booking.get("id") or 0)
        current = lock_pin_text(booking)
        row = {
            "bookingId": bid,
            "arrival": booking.get("arrival"),
            "departure": booking.get("departure"),
            "hasLockPin": current is not None,
            "matchesFixed": current == FIXED_PIN,
        }
        if current == FIXED_PIN:
            already.append(row)
        else:
            need.append(row)

    written = 0
    if run_mode == "live" and need:
        write_lock_pins(token, api_base, [int(r["bookingId"]) for r in need])
        written = len(need)
        for row in need:
            row["matchesFixed"] = True
            row["hasLockPin"] = True

    payload = {
        "schema": "aumara-fixed-pin-seed-v1",
        "checkedAtUtc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "propertyId": PROPERTY_ID,
        "mode": run_mode,
        "windowStart": start.isoformat(),
        "windowEnd": end.isoformat(),
        "fixedPinConfigured": True,
        "pinValueExposed": False,
        "bookingsScanned": len(bookings),
        "alreadyCorrect": len(already),
        "neededUpdate": len(need) if run_mode == "audit" else 0,
        "written": written,
        "authMode": auth_mode,
        "authSource": auth_source,
        "apiHost": urllib.parse.urlparse(api_base).netloc,
        "results": already + need,
        "status": "OK",
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
