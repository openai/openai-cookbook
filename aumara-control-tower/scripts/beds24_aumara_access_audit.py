#!/usr/bin/env python3
"""Read-only AUMARA arrival and access-message integrity audit.

The audit never changes a booking, sends a message, calls TTLock, or exposes a
PIN. It verifies two distinct things for AUMARA property 324882:

* Beds24 currently contains a ``LOCK_PIN`` value for each audited arrival;
* the latest host access message contains that exact current PIN.

A matching message proves distribution integrity only. It does not prove that
the physical lock accepted the PIN; physical opening still requires an on-site
smoke test of the assigned unit and any common lock.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import re
import urllib.parse
from typing import Any, Iterable
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
PIN_RE = re.compile(r"(?<!\d)(\d{6,9})(?!\d)")
ACCESS_MARKERS = (
    "lock_pin",
    "pin",
    "código de acceso",
    "codigo de acceso",
    "access code",
    "instrucciones de acceso",
    "access instructions",
    "door code",
    "key code",
)
HOST_SOURCES = {"host", "property", "owner"}
HEALTHY_STATUSES = {"PIN_MESSAGE_MATCHED"}


class AccessAuditError(AuditError):
    """Raised when the access audit cannot establish a reliable state."""


def target_window() -> tuple[dt.date, dt.date]:
    """Return an exact requested date or the default today-through-tomorrow window."""
    configured = (os.environ.get("AUMARA_AUDIT_ARRIVAL") or "").strip()
    if configured:
        day = dt.date.fromisoformat(configured)
        return day, day
    today = dt.datetime.now(MADRID).date()
    return today, today + dt.timedelta(days=1)


def target_booking_id() -> int | None:
    configured = (os.environ.get("AUMARA_AUDIT_BOOKING_ID") or "").strip()
    return int(configured) if configured else None


def booking_query(start: dt.date, end: dt.date) -> str:
    query = urllib.parse.urlencode(
        [
            ("propertyId", PROPERTY_ID),
            ("arrivalFrom", start.isoformat()),
            ("arrivalTo", end.isoformat()),
            ("includeGuests", "true"),
            ("includeBookingGroup", "true"),
        ]
    )
    return f"/bookings?{query}"


def fetch_arrivals(
    token: str,
    api_base: str,
    start: dt.date,
    end: dt.date,
) -> list[dict[str, Any]]:
    status, response = request_json(
        "GET",
        booking_query(start, end),
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
        raise AccessAuditError(f"AUMARA booking lookup failed with HTTP {status}{suffix}")
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
        raise AccessAuditError(f"AUMARA message lookup failed with HTTP {status}")
    return data_rows(response, "AUMARA message")


def _walk(value: Any, path: tuple[str, ...] = ()) -> Iterable[tuple[tuple[str, ...], Any]]:
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _walk(item, (*path, str(key)))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk(item, (*path, str(index)))
    else:
        yield path, value


def _pin_candidates(value: Any) -> set[str]:
    text = str(value or "").strip()
    return set(PIN_RE.findall(text))


def current_lock_pins(booking: dict[str, Any]) -> tuple[bool, set[str]]:
    """Return descriptor presence and PINs privately; callers must never serialize PINs."""
    items = booking.get("infoItems") or booking.get("bookingInfo") or []
    descriptor = False
    pins: set[str] = set()

    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            descriptor_text = " ".join(
                str(item.get(key) or "")
                for key in ("code", "name", "key", "label", "type")
            ).casefold()
            if "lock_pin" not in descriptor_text:
                continue
            descriptor = True
            for key, value in item.items():
                if str(key).casefold() in {"code", "name", "key", "label", "type"}:
                    continue
                pins.update(_pin_candidates(value))

    for path, value in _walk(items):
        context = " ".join(path).casefold()
        text = str(value or "").casefold()
        if "lock_pin" in context or "lock_pin" in text:
            descriptor = True
            if "lock_pin" in context:
                pins.update(_pin_candidates(value))

    if descriptor and not pins:
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            if any("lock_pin" in str(value or "").casefold() for value in item.values()):
                for value in item.values():
                    pins.update(_pin_candidates(value))

    return descriptor, pins


def lock_pin_state(booking: dict[str, Any]) -> tuple[bool, bool]:
    descriptor, pins = current_lock_pins(booking)
    return descriptor, bool(pins)


def access_message_state(
    messages: list[dict[str, Any]],
    current_pins: set[str] | None = None,
) -> tuple[bool, bool, str | None]:
    """Return marker, exact-current-PIN match and timestamp without returning content."""
    current_pins = current_pins or set()
    evidence: list[tuple[dict[str, Any], bool]] = []
    for message in messages:
        source = str(message.get("source") or message.get("sender") or "").casefold()
        body = str(
            message.get("message")
            or message.get("text")
            or message.get("body")
            or ""
        )
        if source not in HOST_SOURCES:
            continue
        folded = body.casefold()
        marker_found = any(marker in folded for marker in ACCESS_MARKERS)
        exact_match = bool(current_pins) and any(pin in body for pin in current_pins)
        if marker_found or exact_match:
            evidence.append((message, exact_match))
    if not evidence:
        return False, False, None
    latest, latest_match = evidence[-1]
    sent_at = latest.get("time") or latest.get("createdAt") or latest.get("date")
    return True, latest_match, str(sent_at) if sent_at else None


def audit_booking(booking: dict[str, Any], messages: list[dict[str, Any]]) -> dict[str, Any]:
    descriptor, pins = current_lock_pins(booking)
    message_found, message_matches, message_at = access_message_state(messages, pins)
    if pins and message_matches:
        status = "PIN_MESSAGE_MATCHED"
    elif pins and message_found:
        status = "PIN_MESSAGE_MISMATCH"
    elif pins:
        status = "PIN_PRESENT_SEND_UNCONFIRMED"
    else:
        status = "PIN_NOT_FOUND"
    return {
        "bookingId": int(booking.get("id") or 0),
        "arrival": booking.get("arrival"),
        "departure": booking.get("departure"),
        "lockPinDescriptorPresent": descriptor,
        "lockPinValuePresent": bool(pins),
        "hostAccessMessagePresent": message_found,
        "hostMessageMatchesCurrentPin": message_matches,
        "hostAccessMessageAt": message_at,
        "distributionIntegrityVerified": status == "PIN_MESSAGE_MATCHED",
        "physicalDoorOperationVerified": False,
        "status": status,
    }


def _base_payload(
    start: dt.date,
    end: dt.date,
    *,
    status: str,
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema": "aumara-access-audit-v2",
        "checkedAtUtc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "propertyId": PROPERTY_ID,
        "windowStart": start.isoformat(),
        "windowEnd": end.isoformat(),
        "mutations": False,
        "pinValueExposed": False,
        "messageBodyExposed": False,
        "physicalDoorOperationVerified": False,
        "status": status,
        "results": results,
    }


def _write(payload: dict[str, Any]) -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def main() -> int:
    start, end = target_window()
    requested_id = target_booking_id()
    try:
        token, auth_mode, api_base, auth_source, _ = get_access_token()
    except AuditError as exc:
        payload = _base_payload(start, end, status="AUTH_FAILED", results=[])
        payload["error"] = str(exc)
        _write(payload)
        return 1

    try:
        bookings = fetch_arrivals(token, api_base, start, end)
    except AuditError as exc:
        payload = _base_payload(start, end, status="BOOKINGS_READ_FAILED", results=[])
        payload.update(
            {
                "authMode": auth_mode,
                "authSource": auth_source,
                "apiHost": urllib.parse.urlparse(api_base).netloc,
                "error": str(exc),
            }
        )
        _write(payload)
        return 1

    if requested_id is not None:
        bookings = [row for row in bookings if int(row.get("id") or 0) == requested_id]
        if not bookings:
            payload = _base_payload(start, end, status="BOOKING_NOT_FOUND", results=[])
            payload.update(
                {
                    "authMode": auth_mode,
                    "authSource": auth_source,
                    "apiHost": urllib.parse.urlparse(api_base).netloc,
                    "requestedBookingId": requested_id,
                }
            )
            _write(payload)
            return 2

    if not bookings:
        payload = _base_payload(start, end, status="NO_ARRIVALS", results=[])
        payload.update(
            {
                "authMode": auth_mode,
                "authSource": auth_source,
                "apiHost": urllib.parse.urlparse(api_base).netloc,
            }
        )
        _write(payload)
        return 0

    results: list[dict[str, Any]] = []
    for booking in bookings:
        booking_id = int(booking.get("id") or 0)
        try:
            messages = fetch_messages(token, api_base, booking_id)
        except AuditError as exc:
            results.append(
                {
                    "bookingId": booking_id,
                    "arrival": booking.get("arrival"),
                    "departure": booking.get("departure"),
                    "distributionIntegrityVerified": False,
                    "physicalDoorOperationVerified": False,
                    "status": "MESSAGE_READ_FAILED",
                    "error": str(exc),
                }
            )
            continue
        results.append(audit_booking(booking, messages))

    healthy = all(item.get("status") in HEALTHY_STATUSES for item in results)
    payload = _base_payload(
        start,
        end,
        status="ACCESS_DISTRIBUTION_OK" if healthy else "ACCESS_DISTRIBUTION_EXCEPTION",
        results=results,
    )
    payload.update(
        {
            "authMode": auth_mode,
            "authSource": auth_source,
            "apiHost": urllib.parse.urlparse(api_base).netloc,
        }
    )
    _write(payload)
    return 0 if healthy else 2


if __name__ == "__main__":
    raise SystemExit(main())
