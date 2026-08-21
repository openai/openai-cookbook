#!/usr/bin/env python3
"""Read Beds24 guest state and emit a PII-free journey shadow summary."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import urllib.parse
from collections import Counter
from typing import Any, Callable
from zoneinfo import ZoneInfo

from guest_service_journey import (
    GuestJourneyError,
    assert_proposal_guards,
    build_report,
)


MADRID = ZoneInfo("Europe/Madrid")
INACTIVE_STATUSES = {"black", "cancelled", "canceled", "inquiry", "no_show"}
GUEST_SOURCES = {"booker", "customer", "guest"}
HOST_SOURCES = {"host", "owner", "property"}
SHADOW_GUARDS = {
    "BEDS24_GUEST_JOURNEY_MODE": "shadow",
    "AUMARA_DISABLE_GUEST_SEND": "true",
    "AUMARA_DISABLE_EMAIL_SEND": "true",
    "AUMARA_DISABLE_BOOKING_MUTATIONS": "true",
    "BEDS24_AUTO_REPLY_EXECUTE": "0",
    "BEDS24_NOTE_MODE": "off",
}
PROPERTY_MAP = {
    324882: "aumara",
    324903: "elcid",
}
PROPERTY_ROOM_SCOPE = {
    324882: (
        {"roomId": 674465, "name": "SL", "physicalUnits": 4},
        {"roomId": 674466, "name": "Chalet Super", "physicalUnits": 2},
    ),
    324903: (
        {"roomId": 674484, "name": "Triple Room", "physicalUnits": 1},
        {
            "roomId": 674485,
            "name": "Twin Room with Terrace",
            "physicalUnits": 4,
        },
        {"roomId": 674486, "name": "Studio", "physicalUnits": 1},
    ),
}
RECOVERABLE_SHADOW_ERROR_PREFIXES = (
    "Beds24 authentication failed",
    "Beds24 GET request failed",
    "booking lookup failed",
    "booking lookup returned no data array",
    "message lookup failed",
    "message lookup returned no data array",
)


class ShadowFeedError(RuntimeError):
    """Raised when the read-only feed cannot preserve its boundary."""


class GetOnlyRequester:
    """Count reads and reject any non-GET method before the network boundary."""

    def __init__(self, delegate: Callable[..., tuple[int, object]]) -> None:
        self.delegate = delegate
        self.get_requests = 0
        self.non_get_attempts = 0

    def __call__(self, method: str, path: str, **kwargs: Any) -> tuple[int, object]:
        if method.upper() != "GET":
            self.non_get_attempts += 1
            raise ShadowFeedError("shadow requester permits GET only")
        self.get_requests += 1
        try:
            return self.delegate("GET", path, **kwargs)
        except Exception:
            raise ShadowFeedError("Beds24 GET request failed") from None


def _normalize_credential(value: Any) -> str:
    return "".join(str(value or "").strip().strip('"').strip("'").split())


def authenticate_get_only(
    credential: str,
    api_bases: tuple[str, ...],
    requester: GetOnlyRequester,
) -> tuple[str, str]:
    """Resolve a Beds24 access token using GET requests through one guard."""
    normalized = _normalize_credential(credential)
    if not normalized:
        raise ShadowFeedError("Beds24 refresh credential is missing")
    last_status = 0
    for api_base in api_bases:
        status, details = requester(
            "GET",
            "/authentication/details",
            headers={"token": normalized},
            api_base=api_base,
        )
        last_status = status
        if (
            200 <= status < 300
            and isinstance(details, dict)
            and details.get("validToken") is True
        ):
            return normalized, api_base
        status, response = requester(
            "GET",
            "/authentication/token",
            headers={"refreshToken": normalized},
            api_base=api_base,
        )
        last_status = status
        if 200 <= status < 300 and isinstance(response, dict):
            token = _normalize_credential(response.get("token"))
            if token:
                return token, api_base
    raise ShadowFeedError(
        "Beds24 authentication failed with HTTP status " + str(last_status)
    )


def assert_shadow_guards(env: dict[str, str] | None = None) -> None:
    values = env if env is not None else os.environ
    missing = [
        name
        for name, expected in SHADOW_GUARDS.items()
        if str(values.get(name) or "").strip().lower() != expected
    ]
    if missing:
        raise ShadowFeedError(
            "refusing to run without shadow guards: " + ", ".join(missing)
        )


def _date(value: Any, field: str) -> dt.date:
    try:
        return dt.date.fromisoformat(str(value or ""))
    except ValueError as exc:
        raise ShadowFeedError(f"{field} is invalid") from exc


def _timestamp(value: Any) -> dt.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=MADRID)


def _message_source(item: dict[str, Any]) -> str:
    return str(
        item.get("source")
        or item.get("senderType")
        or item.get("actor")
        or ""
    ).strip().lower()


def _message_text(item: dict[str, Any]) -> str:
    return str(
        item.get("message") or item.get("text") or item.get("body") or ""
    ).strip()


def unresolved_guest_message(messages: list[dict[str, Any]]) -> str:
    """Return the latest guest text only when no later host response exists."""
    minimum = dt.datetime.min.replace(tzinfo=dt.timezone.utc)

    def ordering(pair: tuple[int, dict[str, Any]]) -> tuple[bool, dt.datetime, int]:
        index, item = pair
        parsed = _timestamp(
            item.get("createdAt") or item.get("time") or item.get("dateTime")
        )
        return (
            parsed is not None,
            parsed.astimezone(dt.timezone.utc) if parsed else minimum,
            index,
        )

    ordered = sorted(
        enumerate(messages),
        key=ordering,
    )
    for _, item in reversed(ordered):
        source = _message_source(item)
        if source in HOST_SOURCES:
            return ""
        if source in GUEST_SOURCES:
            return _message_text(item)
    return ""


def _guest_first_name(booking: dict[str, Any]) -> str:
    guests = booking.get("guests")
    if isinstance(guests, list) and guests and isinstance(guests[0], dict):
        nested = guests[0]
        value = nested.get("firstName") or nested.get("name")
        if value:
            return str(value).split()[0]
    value = (
        booking.get("guestFirstName")
        or booking.get("firstName")
        or booking.get("guestName")
        or "Guest"
    )
    return str(value).split()[0]


def _language(booking: dict[str, Any]) -> str:
    return str(
        booking.get("language") or booking.get("guestLanguage") or "en"
    )


def booking_query(property_id: int, today: dt.date) -> str:
    query = urllib.parse.urlencode(
        [
            ("propertyId", property_id),
            ("arrivalTo", today.isoformat()),
            ("departureFrom", today.isoformat()),
            ("includeGuests", "true"),
            ("includeBookingGroup", "true"),
        ]
    )
    return f"/bookings?{query}"


def fetch_active_bookings(
    token: str,
    api_base: str,
    property_id: int,
    today: dt.date,
    requester: Callable[..., tuple[int, object]],
) -> list[dict[str, Any]]:
    status, response = requester(
        "GET",
        booking_query(property_id, today),
        headers={"token": token},
        api_base=api_base,
    )
    if not 200 <= status < 300:
        raise ShadowFeedError(f"booking lookup failed with HTTP {status}")
    if not isinstance(response, dict) or not isinstance(response.get("data"), list):
        raise ShadowFeedError("booking lookup returned no data array")
    result: list[dict[str, Any]] = []
    for row in response["data"]:
        if not isinstance(row, dict):
            continue
        if int(row.get("propertyId") or property_id) != property_id:
            continue
        if str(row.get("status") or "").strip().lower() in INACTIVE_STATUSES:
            continue
        try:
            arrival = _date(row.get("arrival"), "arrival")
            departure = _date(row.get("departure"), "departure")
        except ShadowFeedError:
            continue
        if arrival <= today < departure:
            result.append(row)
    return result


def fetch_messages(
    token: str,
    api_base: str,
    booking_id: int,
    requester: Callable[..., tuple[int, object]],
) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode({"bookingId": booking_id, "maxAge": 7})
    status, response = requester(
        "GET",
        f"/bookings/messages?{query}",
        headers={"token": token},
        api_base=api_base,
    )
    if not 200 <= status < 300:
        raise ShadowFeedError(
            f"message lookup failed for one booking with HTTP {status}"
        )
    if not isinstance(response, dict) or not isinstance(response.get("data"), list):
        raise ShadowFeedError("message lookup returned no data array")
    return [item for item in response["data"] if isinstance(item, dict)]


def _scheduled_check_in(arrival: dt.date) -> dt.datetime:
    return dt.datetime.combine(arrival, dt.time(hour=15), tzinfo=MADRID)


def _scheduled_departure(departure: dt.date) -> dt.datetime:
    return dt.datetime.combine(departure, dt.time(hour=11), tzinfo=MADRID)


def _actual_check_in(booking: dict[str, Any]) -> dt.datetime | None:
    for field in ("actualCheckInAt", "checkedInAt"):
        value = booking.get(field)
        if "T" not in str(value or ""):
            continue
        parsed = _timestamp(value)
        if parsed:
            return parsed
    return None


def build_shadow_events(
    bookings: list[dict[str, Any]],
    messages_by_booking: dict[int, list[dict[str, Any]]],
    *,
    now: dt.datetime,
    property_map: dict[int, str],
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for booking in bookings:
        booking_id = int(booking.get("id") or 0)
        property_id = int(booking.get("propertyId") or 0)
        property_key = property_map.get(property_id)
        if not booking_id or property_key not in {"aumara", "elcid"}:
            continue
        arrival = _date(booking.get("arrival"), "arrival")
        departure = _date(booking.get("departure"), "departure")
        unresolved = unresolved_guest_message(
            messages_by_booking.get(booking_id, [])
        )
        common = {
            "property": property_key,
            "booking_ref": str(booking_id),
            "status": "in_house",
            "status_source": "date_window_shadow_only",
            "guest_first_name": _guest_first_name(booking),
            "language": _language(booking),
            "departure_at": _scheduled_departure(departure).isoformat(),
            "now": now.isoformat(),
            "nights": (departure - arrival).days,
            "sent_dedupe_keys": [],
            "last_guest_message": unresolved,
            "open_issue": bool(unresolved),
            "issue_flags": ["unanswered_guest_message"] if unresolved else [],
            "issue_severity": "high" if unresolved else "",
        }
        actual_check_in = _actual_check_in(booking)
        if unresolved:
            events.append(
                {
                    **common,
                    "event_type": "post_checkin",
                    "check_in_at": (
                        actual_check_in or _scheduled_check_in(arrival)
                    ).isoformat(),
                }
            )
            continue
        if actual_check_in:
            events.append(
                {
                    **common,
                    "event_type": "post_checkin",
                    "check_in_at": actual_check_in.isoformat(),
                }
            )
        events.append(
            {
                **common,
                "event_type": "first_morning",
                "check_in_at": _scheduled_check_in(arrival).isoformat(),
            }
        )
    return events


def sanitized_summary(
    report: dict[str, Any],
    *,
    run_at: dt.datetime,
    get_requests: int = 0,
    post_requests: int = 0,
) -> dict[str, Any]:
    if post_requests:
        raise ShadowFeedError("shadow boundary recorded a non-GET attempt")
    decisions = report.get("decisions") or []
    properties = Counter(str(item.get("property") or "unknown") for item in decisions)
    reasons = Counter(str(item.get("reason") or "unknown") for item in decisions)
    return {
        "schema": "aumara-beds24-guest-journey-shadow-v1",
        "mode": "shadow_read_only",
        "runAtUtc": run_at.astimezone(dt.timezone.utc).isoformat(),
        "summary": report["summary"],
        "properties": dict(sorted(properties.items())),
        "reasons": dict(sorted(reasons.items())),
        "getRequests": get_requests,
        "postRequests": post_requests,
        "guestMessagesSent": 0,
        "bookingMutations": 0,
        "durableClaimsWritten": 0,
        "containsGuestPii": False,
    }


def configured_scope() -> dict[str, Any]:
    """Return the PII-free property scope used by the live shadow reader."""
    return {
        "schema": "aumara-beds24-guest-journey-scope-v1",
        "mode": "shadow_read_only",
        "properties": [
            {
                "key": "aumara",
                "propertyId": 324882,
                "coverage": "all_rooms_in_property",
                "roomIdFilter": None,
                "roomCategories": list(PROPERTY_ROOM_SCOPE[324882]),
            },
            {
                "key": "elcid",
                "propertyId": 324903,
                "coverage": "all_rooms_in_property",
                "roomIdFilter": None,
                "roomCategories": list(PROPERTY_ROOM_SCOPE[324903]),
            },
        ],
        "externalWritesEnabled": False,
        "guestMessagesEnabled": False,
        "bookingMutationsEnabled": False,
        "containsGuestPii": False,
    }


def is_recoverable_shadow_error(exc: ShadowFeedError) -> bool:
    message = str(exc)
    return message.startswith(RECOVERABLE_SHADOW_ERROR_PREFIXES)


def degraded_summary(*, run_at: dt.datetime, reason: str) -> dict[str, Any]:
    return {
        "schema": "aumara-beds24-guest-journey-shadow-v1",
        "mode": "shadow_read_only",
        "runAtUtc": run_at.astimezone(dt.timezone.utc).isoformat(),
        "summary": {
            "proposal": 0,
            "manual_review": 0,
            "skip": 0,
            "blocked": 0,
            "degraded": 1,
        },
        "properties": {},
        "reasons": {},
        "getRequests": 0,
        "postRequests": 0,
        "guestMessagesSent": 0,
        "bookingMutations": 0,
        "durableClaimsWritten": 0,
        "containsGuestPii": False,
        "degraded": True,
        "degradedReason": reason,
    }


def build_live_shadow_summary() -> dict[str, Any]:
    """Read Beds24 through the GET-only boundary and return aggregate output."""
    assert_shadow_guards()
    assert_proposal_guards()

    from beds24_elcid_studio_audit import (
        API_BASES,
        request_json,
    )

    requester = GetOnlyRequester(request_json)
    token, api_base = authenticate_get_only(
        os.environ.get("BEDS24_REFRESH_TOKEN", ""), API_BASES, requester
    )
    now = dt.datetime.now(dt.timezone.utc)
    today = now.astimezone(MADRID).date()
    property_map = dict(PROPERTY_MAP)
    bookings: list[dict[str, Any]] = []
    for property_id in property_map:
        bookings.extend(
            fetch_active_bookings(
                token, api_base, property_id, today, requester
            )
        )
    messages = {
        int(booking["id"]): fetch_messages(
            token, api_base, int(booking["id"]), requester
        )
        for booking in bookings
        if booking.get("id")
    }
    events = build_shadow_events(
        bookings, messages, now=now, property_map=property_map
    )
    try:
        report = build_report(events)
    except GuestJourneyError as exc:
        raise ShadowFeedError("guest journey policy rejected the feed") from exc
    summary = sanitized_summary(
        report,
        run_at=now,
        get_requests=requester.get_requests,
        post_requests=requester.non_get_attempts,
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args()
    try:
        summary = build_live_shadow_summary()
    except ShadowFeedError as exc:
        if not is_recoverable_shadow_error(exc):
            raise
        summary = degraded_summary(
            run_at=dt.datetime.now(dt.timezone.utc),
            reason=str(exc),
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ShadowFeedError as exc:
        print(f"ERROR: {exc}", file=__import__("sys").stderr)
        raise SystemExit(2)
