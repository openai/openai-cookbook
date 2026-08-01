#!/usr/bin/env python3
"""Read-only AUMARA arrival and access-message audit.

The audit is deliberately non-mutating.  It authenticates with the single
``BEDS24_REFRESH_TOKEN`` secret, reads arrivals for AUMARA property 324882,
and checks whether Beds24 exposes both a generated ``LOCK_PIN`` and a host
access-message marker.  The PIN value and message body are never written to
logs or artifacts.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import re
import urllib.parse
from typing import Any
from zoneinfo import ZoneInfo

from beds24_elcid_studio_audit import AuditError, data_rows, get_access_token, request_json


PROPERTY_ID = 324882
MADRID = ZoneInfo("Europe/Madrid")
OUTPUT = pathlib.Path(
    os.environ.get(
        "AUMARA_ACCESS_AUDIT_OUTPUT",
        "aumara-control-tower/evidence/aumara-access-audit.json",
    )
)
ACCESS_MARKERS = (
    "lock_pin",
    "pin",
    "código de acceso",
    "codigo de acceso",
    "access code",
    "instrucciones de acceso",
    "access instructions",
)


def target_arrival() -> dt.date:
    configured = (os.environ.get("AUMARA_AUDIT_ARRIVAL") or "").strip()
    if configured:
        return dt.date.fromisoformat(configured)
    return dt.datetime.now(MADRID).date() + dt.timedelta(days=1)


def target_booking_id() -> int | None:
    configured = (os.environ.get("AUMARA_AUDIT_BOOKING_ID") or "").strip()
    return int(configured) if configured else None


def booking_query(arrival: dt.date) -> str:
    query = urllib.parse.urlencode(
        [
            ("propertyId", PROPERTY_ID),
            ("arrivalFrom", arrival.isoformat()),
            ("arrivalTo", arrival.isoformat()),
            ("includeGuests", "true"),
            ("includeBookingGroup", "true"),
        ]
    )
    return f"/bookings?{query}"


def fetch_arrivals(token: str, api_base: str, arrival: dt.date) -> list[dict[str, Any]]:
    status, response = request_json(
        "GET",
        booking_query(arrival),
        headers={"token": token},
        api_base=api_base,
    )
    if not 200 <= status < 300:
        details = {
            key: response.get(key)
            for key in ("diagnostics", "message", "error", "detail", "code")
            if isinstance(response, dict) and response.get(key) not in (None, "", [], {})
        }
        suffix = f"; diagnostics={json.dumps(details, ensure_ascii=False)}" if details else ""
        raise AuditError(f"AUMARA booking lookup failed with HTTP {status}{suffix}")
    rows = data_rows(response, "AUMARA booking")
    return [row for row in rows if int(row.get("propertyId") or PROPERTY_ID) == PROPERTY_ID]


def fetch_messages(token: str, api_base: str, booking_id: int) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode({"bookingId": booking_id, "maxAge": 90})
    status, response = request_json(
        "GET",
        f"/bookings/messages?{query}",
        headers={"token": token},
        api_base=api_base,
    )
    if not 200 <= status < 300:
        raise AuditError(f"AUMARA message lookup failed with HTTP {status}")
    return data_rows(response, "AUMARA message")


def _walk(value: Any, path: tuple[str, ...] = ()):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _walk(item, (*path, str(key)))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk(item, (*path, str(index)))
    else:
        yield path, value


def lock_pin_state(booking: dict[str, Any]) -> tuple[bool, bool]:
    """Return descriptor/value presence without returning the secret PIN."""
    items = booking.get("infoItems") or booking.get("bookingInfo") or []
    flattened = list(_walk(items))
    descriptor = any(
        "lock_pin" in " ".join(path).casefold()
        or (isinstance(value, str) and "lock_pin" in value.casefold())
        for path, value in flattened
    )
    pin_value = False
    for path, value in flattened:
        context = " ".join(path).casefold()
        text = str(value or "").strip()
        if "lock_pin" in context and re.fullmatch(r"\d{6,9}", text):
            pin_value = True
            break
    if descriptor and not pin_value:
        # Beds24 may place the descriptor and value in sibling fields.
        pin_value = any(re.fullmatch(r"\d{6,9}", str(value or "").strip()) for _, value in flattened)
    return descriptor, pin_value


def access_message_state(messages: list[dict[str, Any]]) -> tuple[bool, str | None]:
    evidence = []
    for message in messages:
        source = str(message.get("source") or message.get("sender") or "").casefold()
        body = str(
            message.get("message")
            or message.get("text")
            or message.get("body")
            or ""
        ).casefold()
        if source not in {"host", "property", "owner"}:
            continue
        if any(marker in body for marker in ACCESS_MARKERS):
            evidence.append(message)
    if not evidence:
        return False, None
    latest = evidence[-1]
    sent_at = latest.get("time") or latest.get("createdAt") or latest.get("date")
    return True, str(sent_at) if sent_at else None


def audit_booking(booking: dict[str, Any], messages: list[dict[str, Any]]) -> dict[str, Any]:
    descriptor, pin_value = lock_pin_state(booking)
    message_found, message_at = access_message_state(messages)
    if pin_value and message_found:
        status = "PIN_SENT_CONFIRMED"
    elif pin_value:
        status = "PIN_PRESENT_SEND_UNCONFIRMED"
    else:
        status = "PIN_NOT_FOUND"
    return {
        "bookingId": int(booking.get("id") or 0),
        "arrival": booking.get("arrival"),
        "departure": booking.get("departure"),
        "lockPinDescriptorPresent": descriptor,
        "lockPinValuePresent": pin_value,
        "hostAccessMessagePresent": message_found,
        "hostAccessMessageAt": message_at,
        "status": status,
    }


def main() -> int:
    arrival = target_arrival()
    requested_id = target_booking_id()
    try:
        token, auth_mode, api_base, auth_source, _ = get_access_token()
    except AuditError as exc:
        payload = {
            "schema": "aumara-access-audit-v1",
            "checkedAtUtc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "propertyId": PROPERTY_ID,
            "arrival": arrival.isoformat(),
            "mutations": False,
            "pinValueExposed": False,
            "messageBodyExposed": False,
            "status": "AUTH_FAILED",
            "error": str(exc),
            "results": [],
        }
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        return 1
    try:
        bookings = fetch_arrivals(token, api_base, arrival)
    except AuditError as exc:
        payload = {
            "schema": "aumara-access-audit-v1",
            "checkedAtUtc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "propertyId": PROPERTY_ID,
            "arrival": arrival.isoformat(),
            "authMode": auth_mode,
            "authSource": auth_source,
            "apiHost": urllib.parse.urlparse(api_base).netloc,
            "mutations": False,
            "pinValueExposed": False,
            "messageBodyExposed": False,
            "status": "BOOKINGS_READ_FAILED",
            "error": str(exc),
            "results": [],
        }
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        return 1
    if requested_id is not None:
        bookings = [row for row in bookings if int(row.get("id") or 0) == requested_id]
    if not bookings:
        raise AuditError("No matching AUMARA arrival was returned by Beds24")

    results = []
    for booking in bookings:
        booking_id = int(booking.get("id") or 0)
        messages = fetch_messages(token, api_base, booking_id)
        results.append(audit_booking(booking, messages))

    payload = {
        "schema": "aumara-access-audit-v1",
        "checkedAtUtc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "propertyId": PROPERTY_ID,
        "arrival": arrival.isoformat(),
        "authMode": auth_mode,
        "authSource": auth_source,
        "apiHost": urllib.parse.urlparse(api_base).netloc,
        "mutations": False,
        "pinValueExposed": False,
        "messageBodyExposed": False,
        "results": results,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return 0 if all(item["status"] == "PIN_SENT_CONFIRMED" for item in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
