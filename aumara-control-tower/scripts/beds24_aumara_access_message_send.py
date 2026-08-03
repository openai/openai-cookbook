#!/usr/bin/env python3
"""Send fixed guest access PIN via Beds24 booking messages (OTA channel).

Beds24 Auto Actions (email templates in SETTINGS) have NO public create/update
API. This worker does the part that IS available over API V2:

* ensure LOCK_PIN infoItem is 1531
* POST /bookings/messages for OTA bookings (Booking.com / Airbnb path)

Direct SMTP email from Auto Actions remains a Beds24 UI-only configuration.
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

from beds24_elcid_studio_audit import AuditError, data_rows, get_access_token

PROPERTY_ID = 324882
FIXED_PIN = (os.environ.get("AUMARA_FIXED_GUEST_PIN") or "1531").strip()
MADRID = ZoneInfo("Europe/Madrid")
LIVE_CONFIRMATION = "AUMARA_ACCESS_MESSAGE_SEND_1531_2026_08_03"
OUTPUT = pathlib.Path(
    os.environ.get(
        "AUMARA_ACCESS_MESSAGE_OUTPUT",
        "aumara-control-tower/evidence/aumara-access-message-send.json",
    )
)
TRUE = {"1", "true", "yes", "on"}

ACCESS_MESSAGE = (
    f"Codigo de acceso al chalet: {FIXED_PIN}\r\n"
    f"Introduzca {FIXED_PIN} y pulse #\r\n"
    "Check-in: 16:00 · Check-out: 12:00\r\n"
    "Si necesita ayuda, responda a este mensaje."
)


def enabled(name: str) -> bool:
    return str(os.environ.get(name) or "").strip().lower() in TRUE


def mode() -> str:
    value = str(os.environ.get("AUMARA_ACCESS_MESSAGE_MODE") or "audit").strip().lower()
    if value not in {"audit", "live"}:
        raise SystemExit("AUMARA_ACCESS_MESSAGE_MODE must be audit or live")
    if value == "live":
        if not enabled("AUMARA_LIVE_BOOKING_WRITES_CONFIRMED"):
            raise SystemExit("live requires AUMARA_LIVE_BOOKING_WRITES_CONFIRMED=true")
        if os.environ.get("AUMARA_ACCESS_MESSAGE_WRITE_CONFIRMATION") != LIVE_CONFIRMATION:
            raise SystemExit("live requires exact AUMARA_ACCESS_MESSAGE_WRITE_CONFIRMATION")
    return value


def post_json(api_base: str, path: str, token: str, body: object) -> tuple[int, object]:
    raw = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{api_base}{path}",
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
            text = response.read().decode("utf-8", "replace")
            return response.status, json.loads(text) if text else {}
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", "replace")
        try:
            parsed: object = json.loads(text) if text else {}
        except json.JSONDecodeError:
            parsed = {"error": text[:400]}
        return exc.code, parsed


def get_json(api_base: str, path: str, token: str) -> tuple[int, object]:
    req = urllib.request.Request(
        f"{api_base}{path}",
        headers={"accept": "application/json", "token": token},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            text = response.read().decode("utf-8", "replace")
            return response.status, json.loads(text) if text else {}
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", "replace")
        try:
            parsed: object = json.loads(text) if text else {}
        except json.JSONDecodeError:
            parsed = {"error": text[:400]}
        return exc.code, parsed


def horizon() -> tuple[dt.date, dt.date]:
    today = dt.datetime.now(MADRID).date()
    days = int(os.environ.get("AUMARA_ACCESS_MESSAGE_HORIZON_DAYS") or "45")
    return today, today + dt.timedelta(days=max(1, days))


def fetch_bookings(api_base: str, token: str, start: dt.date, end: dt.date) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode(
        [
            ("propertyId", PROPERTY_ID),
            ("arrivalFrom", start.isoformat()),
            ("arrivalTo", end.isoformat()),
            ("includeGuests", "false"),
            ("includeBookingGroup", "true"),
        ]
    )
    status, response = get_json(api_base, f"/bookings?{query}", token)
    if not 200 <= status < 300:
        raise AuditError(f"booking list failed HTTP {status}")
    rows = data_rows(response, "booking")
    active = {"confirmed", "new", "request"}
    out: list[dict[str, Any]] = []
    for row in rows:
        if int(row.get("propertyId") or PROPERTY_ID) != PROPERTY_ID:
            continue
        if str(row.get("status") or "").lower() not in active:
            continue
        out.append(row)
    return out


def already_has_fixed_pin_message(api_base: str, token: str, booking_id: int) -> bool:
    query = urllib.parse.urlencode({"bookingId": booking_id, "maxAge": 90})
    status, response = get_json(api_base, f"/bookings/messages?{query}", token)
    if not 200 <= status < 300:
        return False
    try:
        messages = data_rows(response, "message")
    except AuditError:
        return False
    needle = FIXED_PIN
    for item in messages:
        source = str(item.get("source") or "").lower()
        body = str(item.get("message") or item.get("text") or item.get("body") or "")
        if source in {"host", "property", "owner"} and needle in body:
            return True
    return False


def ensure_lock_pin(api_base: str, token: str, booking_ids: list[int]) -> int:
    if not booking_ids:
        return 0
    payload = [
        {"id": booking_id, "infoItems": [{"code": "LOCK_PIN", "text": FIXED_PIN}]}
        for booking_id in booking_ids
    ]
    status, response = post_json(api_base, "/bookings", token, payload)
    if status not in (200, 201):
        raise AuditError(f"LOCK_PIN write failed HTTP {status}: {response}")
    return len(booking_ids)


def send_message(api_base: str, token: str, booking_id: int) -> tuple[bool, str]:
    """Try Beds24 V2 message POST shapes used by OTA messaging."""
    candidates = [
        [{"bookingId": booking_id, "message": ACCESS_MESSAGE}],
        [{"bookingId": booking_id, "text": ACCESS_MESSAGE}],
        [{"bookingId": booking_id, "message": ACCESS_MESSAGE, "source": "host"}],
    ]
    last_error = "no_attempt"
    for body in candidates:
        status, response = post_json(api_base, "/bookings/messages", token, body)
        if 200 <= status < 300:
            return True, f"http_{status}"
        last_error = f"http_{status}:{json.dumps(response, ensure_ascii=False)[:180]}"
        # 400 with schema hint — try next shape
        if status in {401, 403}:
            return False, last_error
    return False, last_error


def main() -> int:
    run_mode = mode()
    start, end = horizon()
    try:
        token, auth_mode, api_base, auth_source, _ = get_access_token()
    except AuditError as exc:
        payload = {"schema": "aumara-access-message-send-v1", "status": "AUTH_FAILED", "error": str(exc)}
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(payload, separators=(",", ":")))
        return 1

    bookings = fetch_bookings(api_base, token, start, end)
    results: list[dict[str, Any]] = []
    need_pin: list[int] = []
    for booking in bookings:
        bid = int(booking.get("id") or 0)
        channel = str(booking.get("channel") or booking.get("referer") or "")
        item: dict[str, Any] = {
            "bookingId": bid,
            "arrival": booking.get("arrival"),
            "departure": booking.get("departure"),
            "channel": channel,
            "alreadyHadPinMessage": False,
            "action": "skip",
        }
        if not bid:
            item["reason"] = "missing_id"
            results.append(item)
            continue
        if already_has_fixed_pin_message(api_base, token, bid):
            item["alreadyHadPinMessage"] = True
            item["action"] = "already_sent"
            results.append(item)
            continue
        need_pin.append(bid)
        if run_mode == "audit":
            item["action"] = "would_send"
            results.append(item)
            continue
        ok, detail = send_message(api_base, token, bid)
        item["action"] = "sent" if ok else "send_failed"
        item["detail"] = detail
        results.append(item)

    pin_written = 0
    if run_mode == "live" and need_pin:
        pin_written = ensure_lock_pin(api_base, token, need_pin)

    payload = {
        "schema": "aumara-access-message-send-v1",
        "checkedAtUtc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "propertyId": PROPERTY_ID,
        "mode": run_mode,
        "windowStart": start.isoformat(),
        "windowEnd": end.isoformat(),
        "fixedPinConfigured": True,
        "pinValueExposed": False,
        "messageBodyExposed": False,
        "bookingsScanned": len(bookings),
        "wouldSend": sum(1 for r in results if r.get("action") == "would_send"),
        "sent": sum(1 for r in results if r.get("action") == "sent"),
        "sendFailed": sum(1 for r in results if r.get("action") == "send_failed"),
        "alreadySent": sum(1 for r in results if r.get("action") == "already_sent"),
        "lockPinWrites": pin_written,
        "authMode": auth_mode,
        "authSource": auth_source,
        "apiHost": urllib.parse.urlparse(api_base).netloc,
        "results": results,
        "status": "OK",
        "platformNote": (
            "Beds24 Auto Action email templates are UI-only; "
            "this job uses POST /bookings/messages (OTA) + LOCK_PIN seed."
        ),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
