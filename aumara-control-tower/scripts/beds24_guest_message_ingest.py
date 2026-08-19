#!/usr/bin/env python3
"""Read and normalize Beds24 guest/host messages without external writes.

The worker is intentionally read-only. It uses GET requests only, persists no raw
message text or guest contact data, and produces a redacted event/conversation
artifact suitable for validating future Guest Ops ingestion.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import os
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from typing import Any, Iterable

from beds24_elcid_studio_audit import AuditError, get_access_token
from guest_request_dry_run import classify_event


PROPERTY_ID = 324903
ALLOWED_SOURCES = ("guest", "host")
OUTPUT = pathlib.Path(
    os.environ.get(
        "BEDS24_MESSAGE_INGEST_OUTPUT",
        "aumara-control-tower/evidence/beds24-guest-message-ingest.json",
    )
)


class IngestError(RuntimeError):
    """Raised when the read-only ingestion cannot establish reliable state."""


def keyed_hash(redaction_key: str, namespace: str, value: object) -> str:
    key = redaction_key.encode("utf-8")
    if not key:
        raise IngestError("A non-empty redaction key is required")
    material = f"{namespace}|{value}".encode("utf-8")
    return hmac.new(key, material, hashlib.sha256).hexdigest()[:16]


def parse_timestamp(value: object) -> dt.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def iso_timestamp(value: dt.datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def data_rows(response: object, label: str) -> list[dict[str, Any]]:
    if not isinstance(response, dict) or not isinstance(response.get("data"), list):
        raise IngestError(f"{label} response did not contain a data array")
    rows = response["data"]
    if not all(isinstance(row, dict) for row in rows):
        raise IngestError(f"{label} response contained a non-object row")
    return rows


class Beds24ReadOnlyClient:
    """GET-only client with request counters included in the audit artifact."""

    def __init__(
        self,
        token: str,
        api_base: str,
        opener: Any = urllib.request.urlopen,
    ) -> None:
        self.token = token
        self.api_base = api_base.rstrip("/")
        self.opener = opener
        self.get_requests = 0
        self.non_get_requests = 0

    def request_json(self, method: str, path: str) -> tuple[int, object]:
        if method != "GET":
            self.non_get_requests += 1
            raise IngestError(f"Read-only client rejected HTTP method: {method}")
        self.get_requests += 1
        request = urllib.request.Request(
            f"{self.api_base}{path}",
            headers={"accept": "application/json", "token": self.token},
            method="GET",
        )
        try:
            with self.opener(request, timeout=45) as response:
                raw = response.read().decode("utf-8", "replace")
                return response.status, json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace")
            try:
                parsed: object = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                parsed = {"error": raw[:300]}
            return exc.code, parsed


def fetch_messages(
    client: Beds24ReadOnlyClient,
    *,
    source: str,
    max_age_days: int,
) -> list[dict[str, Any]]:
    if source not in ALLOWED_SOURCES:
        raise IngestError(f"Unsupported message source: {source}")
    rows: list[dict[str, Any]] = []
    for page in range(1, 21):
        params: list[tuple[str, object]] = [
            ("propertyId", PROPERTY_ID),
            ("maxAge", max_age_days),
            ("source", source),
        ]
        if page > 1:
            params.append(("page", page))
        path = f"/bookings/messages?{urllib.parse.urlencode(params)}"
        status, response = client.request_json("GET", path)
        if not 200 <= status < 300:
            raise IngestError(
                f"{source.title()}-message lookup failed with HTTP {status}"
            )
        rows.extend(data_rows(response, f"{source.title()} message"))
        pages = response.get("pages") if isinstance(response, dict) else None
        if not isinstance(pages, dict) or not pages.get("nextPageExists"):
            return rows
    raise IngestError(f"{source.title()}-message pagination exceeded 20 pages")


def fetch_bookings(
    client: Beds24ReadOnlyClient,
    booking_ids: Iterable[int],
) -> dict[int, dict[str, Any]]:
    unique = sorted({int(item) for item in booking_ids if int(item)})
    bookings: dict[int, dict[str, Any]] = {}
    for start in range(0, len(unique), 100):
        chunk = unique[start : start + 100]
        params: list[tuple[str, object]] = [("propertyId", PROPERTY_ID)]
        params.extend(("id", booking_id) for booking_id in chunk)
        path = f"/bookings?{urllib.parse.urlencode(params)}"
        status, response = client.request_json("GET", path)
        if not 200 <= status < 300:
            raise IngestError(f"Booking lookup failed with HTTP {status}")
        for row in data_rows(response, "Booking"):
            booking_id = int(row.get("id") or 0)
            if booking_id:
                bookings[booking_id] = row
    return bookings


def booking_metadata(booking: dict[str, Any] | None) -> dict[str, Any]:
    value = booking or {}
    return {
        "bookingStatus": str(value.get("status") or "").strip().lower() or None,
        "channel": str(value.get("channel") or value.get("referer") or "").strip()
        or None,
        "arrival": str(value.get("arrival") or "").strip() or None,
        "departure": str(value.get("departure") or "").strip() or None,
    }


def first_later_host(
    host_rows: list[tuple[dt.datetime, int]],
    guest_time: dt.datetime,
    guest_id: int,
) -> tuple[dt.datetime, int] | None:
    for host_time, host_id in host_rows:
        if (host_time, host_id) > (guest_time, guest_id):
            return host_time, host_id
    return None


def normalize_messages(
    messages: list[dict[str, Any]],
    bookings: dict[int, dict[str, Any]],
    *,
    now: dt.datetime,
    redaction_key: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    current = now.astimezone(dt.timezone.utc)
    deduplicated: dict[tuple[str, int], dict[str, Any]] = {}
    duplicates = 0
    unsupported_sources = 0

    for index, message in enumerate(messages):
        source = str(message.get("source") or "").strip().lower()
        if source not in ALLOWED_SOURCES:
            unsupported_sources += 1
            continue
        message_id = int(message.get("id") or 0)
        key = (source, message_id if message_id else -(index + 1))
        if message_id and key in deduplicated:
            duplicates += 1
            continue
        deduplicated[key] = message

    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    manual_review = 0
    for message in deduplicated.values():
        property_id = int(message.get("propertyId") or PROPERTY_ID)
        if property_id != PROPERTY_ID:
            continue
        booking_id = int(message.get("bookingId") or 0)
        message_id = int(message.get("id") or 0)
        timestamp = parse_timestamp(message.get("time"))
        if not booking_id or not message_id or timestamp is None:
            manual_review += 1
            continue
        grouped[booking_id].append(message)

    event_rows: list[tuple[dt.datetime, int, int, dict[str, Any]]] = []
    conversations: list[dict[str, Any]] = []

    for booking_id, rows in sorted(grouped.items()):
        ordered = sorted(
            rows,
            key=lambda item: (
                parse_timestamp(item.get("time")) or dt.datetime.min.replace(
                    tzinfo=dt.timezone.utc
                ),
                int(item.get("id") or 0),
            ),
        )
        host_rows = sorted(
            (
                (parse_timestamp(item.get("time")), int(item.get("id") or 0))
                for item in ordered
                if str(item.get("source") or "").lower() == "host"
                and parse_timestamp(item.get("time")) is not None
            ),
            key=lambda item: (item[0], item[1]),
        )
        typed_host_rows = [(time, message_id) for time, message_id in host_rows if time]

        normalized_for_booking: list[dict[str, Any]] = []
        for message in ordered:
            message_id = int(message.get("id") or 0)
            source = str(message.get("source") or "").strip().lower()
            timestamp = parse_timestamp(message.get("time"))
            assert timestamp is not None
            text = str(message.get("message") or "")
            response = (
                first_later_host(typed_host_rows, timestamp, message_id)
                if source == "guest"
                else None
            )
            response_time = response[0] if response else None
            response_lag = (
                max(0, int((response_time - timestamp).total_seconds()))
                if response_time
                else None
            )
            event = {
                "eventId": keyed_hash(
                    redaction_key,
                    "beds24-event",
                    f"{booking_id}|{message_id}|{source}|{timestamp.isoformat()}",
                ),
                "messageHash": keyed_hash(
                    redaction_key, "beds24-message", message_id
                ),
                "bookingHash": keyed_hash(
                    redaction_key, "beds24-booking", booking_id
                ),
                "propertyId": PROPERTY_ID,
                "direction": source,
                "eventType": (
                    classify_event({"body": text})
                    if source == "guest"
                    else "host_reply"
                ),
                "occurredAtUtc": iso_timestamp(timestamp),
                "answered": bool(response) if source == "guest" else None,
                "responseLagSeconds": response_lag,
                **booking_metadata(bookings.get(booking_id)),
            }
            event_rows.append((timestamp, booking_id, message_id, event))
            normalized_for_booking.append(event)

        latest = normalized_for_booking[-1]
        guest_events = [
            item for item in normalized_for_booking if item["direction"] == "guest"
        ]
        host_events = [
            item for item in normalized_for_booking if item["direction"] == "host"
        ]
        latest_guest = guest_events[-1] if guest_events else None
        latest_guest_time = (
            parse_timestamp(latest_guest["occurredAtUtc"]) if latest_guest else None
        )
        unanswered = bool(latest_guest and latest["direction"] == "guest")
        unanswered_age = (
            max(0, int((current - latest_guest_time).total_seconds()))
            if unanswered and latest_guest_time
            else None
        )
        conversations.append(
            {
                "conversationId": keyed_hash(
                    redaction_key, "beds24-conversation", booking_id
                ),
                "bookingHash": keyed_hash(
                    redaction_key, "beds24-booking", booking_id
                ),
                "propertyId": PROPERTY_ID,
                "lastDirection": latest["direction"],
                "lastEventType": latest["eventType"],
                "lastMessageAtUtc": latest["occurredAtUtc"],
                "guestMessageCount": len(guest_events),
                "hostMessageCount": len(host_events),
                "unanswered": unanswered,
                "unansweredAgeSeconds": unanswered_age,
                **booking_metadata(bookings.get(booking_id)),
            }
        )

    events = [
        event
        for _, _, _, event in sorted(
            event_rows,
            key=lambda item: (item[0], item[1], item[2]),
        )
    ]
    conversations.sort(
        key=lambda item: (str(item["lastMessageAtUtc"]), str(item["conversationId"]))
    )

    counters = {
        "duplicates": duplicates,
        "manualReview": manual_review,
        "unsupportedSources": unsupported_sources,
    }
    return events, conversations, counters


def run(
    client: Beds24ReadOnlyClient,
    *,
    max_age_days: int,
    now: dt.datetime | None = None,
    redaction_key: str,
) -> dict[str, Any]:
    if not 1 <= max_age_days <= 7:
        raise IngestError("BEDS24_MESSAGE_MAX_AGE_DAYS must be between 1 and 7")
    current = now or dt.datetime.now(dt.timezone.utc)
    guest_messages = fetch_messages(
        client, source="guest", max_age_days=max_age_days
    )
    host_messages = fetch_messages(client, source="host", max_age_days=max_age_days)
    messages = guest_messages + host_messages
    booking_ids = [int(item.get("bookingId") or 0) for item in messages]
    bookings = fetch_bookings(client, booking_ids) if any(booking_ids) else {}
    events, conversations, counters = normalize_messages(
        messages,
        bookings,
        now=current,
        redaction_key=redaction_key,
    )
    report = {
        "schema": "aumara-beds24-guest-message-ingest-v1",
        "generatedAtUtc": iso_timestamp(current),
        "propertyId": PROPERTY_ID,
        "windowDays": max_age_days,
        "summary": {
            "messagesScanned": len(messages),
            "guestMessages": len(guest_messages),
            "hostMessages": len(host_messages),
            "eventsNormalized": len(events),
            "conversations": len(conversations),
            "unansweredConversations": sum(
                bool(item["unanswered"]) for item in conversations
            ),
            "bookingsResolved": len(bookings),
            **counters,
        },
        "safety": {
            "httpMethods": ["GET"],
            "getRequests": client.get_requests,
            "nonGetRequests": client.non_get_requests,
            "guestMessagesSent": 0,
            "bookingMutations": 0,
            "rawGuestMessagePersisted": False,
            "guestContactDataPersisted": False,
            "rawBookingIdPersisted": False,
        },
        "events": events,
        "conversations": conversations,
    }
    if client.non_get_requests:
        raise IngestError("Read-only ingestion violated the GET-only invariant")
    serialized = json.dumps(report, ensure_ascii=False)
    for row in messages:
        raw_text = str(row.get("message") or "")
        if raw_text and raw_text in serialized:
            raise IngestError("Raw guest message text reached the persisted artifact")
    return report


def main() -> int:
    try:
        max_age_days = int(os.environ.get("BEDS24_MESSAGE_MAX_AGE_DAYS", "3"))
        token, auth_mode, api_base, auth_source, _ = get_access_token()
        client = Beds24ReadOnlyClient(token, api_base)
        configured_key = "".join(
            (os.environ.get("BEDS24_TOKEN_CREDENTIAL") or token).split()
        )
        report = run(
            client,
            max_age_days=max_age_days,
            redaction_key=configured_key,
        )
        report["authentication"] = {
            "mode": auth_mode,
            "source": auth_source,
            "apiHost": urllib.parse.urlparse(api_base).netloc,
            "secretLogged": False,
        }
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(report["summary"], sort_keys=True))
        return 0
    except (AuditError, IngestError, OSError, ValueError) as exc:
        print(f"Beds24 guest-message ingestion failed safely: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
