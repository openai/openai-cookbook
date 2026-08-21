#!/usr/bin/env python3
"""Read-only audit for future El Cid Studio bookings and alternatives.

The script intentionally performs GET requests only. It never creates or
modifies a booking, price, availability, Auto Action, or guest message.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import urllib.error
import urllib.parse
import urllib.request


API_BASES = (
    "https://api.beds24.com/v2",
    "https://beds24.com/api/v2",
)
PROPERTY_ID = 324903
STUDIO_ROOM_ID = 674486
ROOMS = {
    674484: {"name": "Triple Room", "capacity": 3},
    674485: {"name": "Twin Room with Terrace", "capacity": 2},
    674486: {"name": "Studio", "capacity": 2},
}
ACTIVE_STATUS_EXCLUSIONS = {"cancelled", "canceled", "black", "inquiry"}
OUTPUT = pathlib.Path(
    os.environ.get(
        "BEDS24_STUDIO_AUDIT_OUTPUT",
        "aumara-control-tower/evidence/elcid-studio-audit.json",
    )
)
class AuditError(RuntimeError):
    """Raised when the read-only audit cannot establish reliable state."""


def normalize(value: str | None) -> str:
    """Normalize a copied credential without ever printing it."""
    return "".join((value or "").strip().strip('"').strip("'").split())


def request_json(
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    api_base: str | None = None,
) -> tuple[int, object]:
    """Call Beds24 and return the HTTP status plus decoded JSON."""
    request = urllib.request.Request(
        f"{api_base or API_BASES[0]}{path}",
        headers={"accept": "application/json", **(headers or {})},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            raw = response.read().decode("utf-8", "replace")
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            parsed: object = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {"error": raw[:300]}
        return exc.code, parsed


def credential_candidates() -> list[tuple[str, str]]:
    """Return the single durable refresh credential configured for runtime."""
    refresh_token = normalize(os.environ.get("BEDS24_REFRESH_TOKEN"))
    return [("beds24_refresh_token", refresh_token)] if refresh_token else []


def get_access_token() -> tuple[str, str, str, str, bool]:
    """Exchange the configured refresh token for a short-lived access token."""
    candidates = credential_candidates()
    if not candidates:
        raise AuditError("BEDS24_REFRESH_TOKEN is missing")

    last_status = 0
    for source, credential in candidates:
        for api_base in API_BASES:
            status, details = request_json(
                "GET",
                "/authentication/details",
                headers={"token": credential},
                api_base=api_base,
            )
            last_status = status
            if (
                200 <= status < 300
                and isinstance(details, dict)
                and details.get("validToken") is True
            ):
                return credential, "access_token", api_base, source, False

            status, response = request_json(
                "GET",
                "/authentication/token",
                headers={"refreshToken": credential},
                api_base=api_base,
            )
            last_status = status
            if 200 <= status < 300 and isinstance(response, dict):
                token = normalize(str(response.get("token") or ""))
                if token:
                    return token, "refresh_token", api_base, source, False

    raise AuditError(
        "The configured Beds24 refresh token could not produce a valid access "
        f"token (last HTTP status {last_status})"
    )


def data_rows(response: object, label: str) -> list[dict[str, object]]:
    """Extract and validate a Beds24 data array."""
    if not isinstance(response, dict) or not isinstance(response.get("data"), list):
        raise AuditError(f"{label} response did not contain a data array")
    rows = response["data"]
    if not all(isinstance(row, dict) for row in rows):
        raise AuditError(f"{label} response contained a non-object row")
    return rows


def booking_query(today: dt.date) -> str:
    """Build the narrow future-Studio booking query."""
    params: list[tuple[str, object]] = [
        ("propertyId", PROPERTY_ID),
        ("roomId", STUDIO_ROOM_ID),
        ("arrivalFrom", today.isoformat()),
        ("includeGuests", "true"),
        ("includeBookingGroup", "true"),
    ]
    return "/bookings?" + urllib.parse.urlencode(params)


def fetch_bookings(
    token: str,
    today: dt.date,
    api_base: str,
) -> list[dict[str, object]]:
    """Fetch future Studio bookings and enforce the expected room scope."""
    status, response = request_json(
        "GET",
        booking_query(today),
        headers={"token": token},
        api_base=api_base,
    )
    if not 200 <= status < 300:
        raise AuditError(f"Booking audit failed with HTTP {status}")
    rows = data_rows(response, "Booking")

    scoped: list[dict[str, object]] = []
    for row in rows:
        room_id = int(row.get("roomId") or 0)
        property_id = int(row.get("propertyId") or PROPERTY_ID)
        if room_id != STUDIO_ROOM_ID or property_id != PROPERTY_ID:
            continue
        status_name = str(row.get("status") or "").strip().lower()
        departure_text = str(row.get("departure") or "")
        try:
            departure = dt.date.fromisoformat(departure_text)
        except ValueError:
            continue
        if status_name in ACTIVE_STATUS_EXCLUSIONS or departure <= today:
            continue
        scoped.append(row)
    return scoped


def fetch_calendar(
    token: str,
    start: dt.date,
    end: dt.date,
    api_base: str,
) -> list[dict[str, object]]:
    """Read inventory for all El Cid rooms over the affected date span."""
    params: list[tuple[str, object]] = [
        ("startDate", start.isoformat()),
        ("endDate", end.isoformat()),
        ("propertyId", PROPERTY_ID),
        ("includePrices", "false"),
    ]
    params.extend(("roomId", room_id) for room_id in ROOMS)
    query = urllib.parse.urlencode(params)
    status, response = request_json(
        "GET",
        f"/inventory/rooms/calendar?{query}",
        headers={"token": token},
        api_base=api_base,
    )
    if not 200 <= status < 300:
        raise AuditError(f"Inventory audit failed with HTTP {status}")
    return data_rows(response, "Inventory")


def date_span(start: dt.date, end: dt.date):
    """Yield dates inclusively."""
    cursor = start
    while cursor <= end:
        yield cursor
        cursor += dt.timedelta(days=1)


def expand_inventory(
    rows: list[dict[str, object]],
) -> dict[tuple[int, dt.date], int | None]:
    """Expand compressed calendar ranges into nightly inventory values."""
    inventory: dict[tuple[int, dt.date], int | None] = {}
    for row in rows:
        room_id = int(row.get("roomId") or 0)
        if room_id not in ROOMS:
            continue
        calendar = row.get("calendar") or []
        if not isinstance(calendar, list):
            raise AuditError(f"Room {room_id} calendar was not an array")
        for item in calendar:
            if not isinstance(item, dict) or not item.get("from"):
                continue
            start = dt.date.fromisoformat(str(item["from"]))
            end = dt.date.fromisoformat(str(item.get("to") or item["from"]))
            raw = item.get("numAvail")
            value = int(raw) if raw is not None else None
            for day in date_span(start, end):
                inventory[(room_id, day)] = value
    return inventory


def guest_count(booking: dict[str, object]) -> int:
    """Calculate the booked party size without exposing personal details."""
    adults = int(booking.get("numAdult") or booking.get("numAdults") or 0)
    children = int(booking.get("numChild") or booking.get("numChildren") or 0)
    if adults + children:
        return adults + children
    guests = booking.get("guests") or []
    if isinstance(guests, list) and guests:
        return len(guests)
    return 1


def nightly_dates(arrival: dt.date, departure: dt.date) -> list[dt.date]:
    """Return occupied nights, excluding the departure day."""
    nights: list[dt.date] = []
    cursor = arrival
    while cursor < departure:
        nights.append(cursor)
        cursor += dt.timedelta(days=1)
    return nights


def candidates_for(
    booking: dict[str, object],
    inventory: dict[tuple[int, dt.date], int | None],
) -> tuple[list[dict[str, object]], list[str]]:
    """Find capacity-compatible rooms available on every occupied night."""
    arrival = dt.date.fromisoformat(str(booking["arrival"]))
    departure = dt.date.fromisoformat(str(booking["departure"]))
    nights = nightly_dates(arrival, departure)
    party = guest_count(booking)
    candidates: list[dict[str, object]] = []
    warnings: list[str] = []
    for room_id, room in ROOMS.items():
        if room_id == STUDIO_ROOM_ID or int(room["capacity"]) < party:
            continue
        nightly = [inventory.get((room_id, night)) for night in nights]
        if any(value is None for value in nightly):
            warnings.append(f"room {room_id}: inventory unknown for one or more nights")
            continue
        minimum = min(int(value) for value in nightly) if nightly else 0
        if minimum > 0:
            candidates.append(
                {
                    "roomId": room_id,
                    "roomName": room["name"],
                    "capacity": room["capacity"],
                    "minimumNightlyAvailability": minimum,
                }
            )
    return candidates, warnings


def fetch_message_count(
    token: str,
    booking_id: int,
    api_base: str,
) -> int | None:
    """Read message history when the endpoint is available for the channel."""
    query = urllib.parse.urlencode({"bookingId": booking_id})
    status, response = request_json(
        "GET",
        f"/bookings/messages?{query}",
        headers={"token": token},
        api_base=api_base,
    )
    if not 200 <= status < 300:
        return None
    try:
        return len(data_rows(response, "Message"))
    except AuditError:
        return None


def probe_url(url: str) -> dict[str, object]:
    """Perform a small public website reachability probe."""
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "ElCid-Control-Tower/1.0"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read(250_000).decode("utf-8", "replace")
            return {
                "url": url,
                "httpStatus": response.status,
                "reachable": 200 <= response.status < 400,
                "containsElCid": "el cid" in body.lower(),
            }
    except Exception as exc:  # only the exception class is retained
        return {
            "url": url,
            "reachable": False,
            "errorType": type(exc).__name__,
        }


def main() -> None:
    """Run the read-only audit and write a sanitized artifact."""
    today = dt.date.fromisoformat(
        os.environ.get("AUDIT_TODAY", dt.datetime.now(dt.timezone.utc).date().isoformat())
    )
    token, auth_mode, api_base, auth_source, bootstrap = get_access_token()
    bookings = fetch_bookings(token, today, api_base)

    inventory: dict[tuple[int, dt.date], int | None] = {}
    if bookings:
        start = min(dt.date.fromisoformat(str(row["arrival"])) for row in bookings)
        final_departure = max(
            dt.date.fromisoformat(str(row["departure"])) for row in bookings
        )
        calendar = fetch_calendar(
            token,
            start,
            final_departure - dt.timedelta(days=1),
            api_base,
        )
        inventory = expand_inventory(calendar)

    sanitized: list[dict[str, object]] = []
    for booking in sorted(bookings, key=lambda row: (str(row.get("arrival")), int(row.get("id") or 0))):
        booking_id = int(booking.get("id") or 0)
        candidates, warnings = candidates_for(booking, inventory)
        sanitized.append(
            {
                "bookingId": booking_id,
                "status": booking.get("status"),
                "arrival": booking.get("arrival"),
                "departure": booking.get("departure"),
                "guestCount": guest_count(booking),
                "channel": booking.get("channel") or booking.get("referer"),
                "externalReference": booking.get("bookingRef")
                or booking.get("apiReference"),
                "existingMessageCount": fetch_message_count(
                    token,
                    booking_id,
                    api_base,
                ),
                "availableAlternatives": candidates,
                "warnings": warnings,
            }
        )

    result = {
        "schema": "elcid-studio-audit-v1",
        "auditedAtUtc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "today": today.isoformat(),
        "readOnly": True,
        "authMode": auth_mode,
        "authSource": auth_source,
        "authBootstrapPerformed": bootstrap,
        "apiHost": urllib.parse.urlparse(api_base).netloc,
        "propertyId": PROPERTY_ID,
        "studioRoomId": STUDIO_ROOM_ID,
        "activeStudioBookingCount": len(sanitized),
        "bookings": sanitized,
        "website": [
            probe_url("https://elcidspain.com/"),
            probe_url("https://elcidspain.com/aumara/"),
            probe_url("https://beds24.com/booking2.php?propid=324903"),
        ],
        "secretPresent": True,
        "secretLogged": False,
        "mutationsPerformed": False,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
