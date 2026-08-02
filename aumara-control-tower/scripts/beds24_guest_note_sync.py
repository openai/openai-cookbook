#!/usr/bin/env python3
"""Continuously write idempotent direct guest-request infoItems in Beds24.

Live mode is deliberately narrow: only approved operational request types are
eligible, every run is bounded, and every new infoItem must be confirmed by an
exact GET read-back. Cot requests remain delegated to the stricter worker that
also proves infant age, room and occupancy. This worker never sends guest
messages or changes dates, rooms, prices, status, inventory or payments.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from typing import Any

from beds24_elcid_studio_audit import AuditError, data_rows, get_access_token
from guest_request_dry_run import classify_event, proposed_booking_note


PROPERTY_ID = 324903
DEFAULT_NOTE_CODE = "GUESTREQUEST"
ACTIVE_STATUSES = {"confirmed", "new", "request"}
CLASSIFIED_EVENT_TYPES = {
    "bed_request",
    "cot_request",
    "pet_request",
    "parking_request",
    "early_checkin",
    "late_checkin",
    "late_checkout",
}
LIVE_SUPPORTED_EVENT_TYPES = CLASSIFIED_EVENT_TYPES - {"cot_request"}
TRUE_VALUES = {"1", "true", "yes", "on"}
POLICY_ID = "elcid.direct-guest-request-infoitem"
POLICY_VERSION = "2026.08.02.1"
LIVE_CONFIRMATION = "INFOITEMS_ONLY_ELCID_DIRECT_GUEST_REQUESTS_2026_08_02_1"
MAX_WRITES_CAP = 10
MAX_AGE_DAYS = 7
DEFAULT_POLICY_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "policies"
    / "elcid-direct-guest-notes.json"
)
NOTE_CODE_RE = re.compile(r"^[A-Z0-9]{1,20}$")
OUTPUT = pathlib.Path(
    os.environ.get(
        "BEDS24_NOTE_AUDIT_OUTPUT",
        "aumara-control-tower/evidence/beds24-guest-note-audit.json",
    )
)


class NoteSyncError(RuntimeError):
    """Raised when the note sync cannot preserve its safety boundary."""


def enabled(env: dict[str, str], name: str) -> bool:
    return str(env.get(name) or "").strip().lower() in TRUE_VALUES


def operating_mode(env: dict[str, str] | None = None) -> str:
    values = env if env is not None else os.environ
    mode = str(values.get("BEDS24_NOTE_MODE") or "off").strip().lower()
    if mode not in {"off", "audit", "live"}:
        raise NoteSyncError("BEDS24_NOTE_MODE must be off, audit, or live")
    if mode == "audit" and not enabled(values, "AUMARA_DISABLE_BOOKING_MUTATIONS"):
        raise NoteSyncError("Audit mode requires AUMARA_DISABLE_BOOKING_MUTATIONS=true")
    if mode == "live":
        if enabled(values, "AUMARA_DISABLE_BOOKING_MUTATIONS"):
            raise NoteSyncError(
                "Live mode conflicts with the booking mutation kill switch"
            )
        if not enabled(values, "AUMARA_LIVE_BOOKING_WRITES_CONFIRMED"):
            raise NoteSyncError(
                "Live mode requires AUMARA_LIVE_BOOKING_WRITES_CONFIRMED=true"
            )
        if (
            values.get("AUMARA_BEDS24_NOTE_WRITE_CONFIRMATION")
            != LIVE_CONFIRMATION
        ):
            raise NoteSyncError(
                "Live mode requires the exact infoItems-only confirmation"
            )
        if not str(values.get("BEDS24_NOTE_CODE") or "").strip():
            raise NoteSyncError("Live mode requires an explicit BEDS24_NOTE_CODE")
        if int(values.get("BEDS24_NOTE_MAX_WRITES") or "0") != MAX_WRITES_CAP:
            raise NoteSyncError("BEDS24_NOTE_MAX_WRITES must be exactly 10")
        if int(values.get("BEDS24_NOTE_MAX_AGE_DAYS") or "0") != MAX_AGE_DAYS:
            raise NoteSyncError("BEDS24_NOTE_MAX_AGE_DAYS must be exactly 7")
        if str(values.get("BEDS24_NOTE_POLICY_ID") or "") != POLICY_ID:
            raise NoteSyncError("The approved direct-note policy ID is missing")
        if str(values.get("BEDS24_NOTE_POLICY_VERSION") or "") != POLICY_VERSION:
            raise NoteSyncError("The approved direct-note policy version is missing")
    return mode


def load_approved_policy(env: dict[str, str]) -> dict[str, str]:
    path = pathlib.Path(env.get("BEDS24_NOTE_POLICY_PATH") or DEFAULT_POLICY_PATH)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NoteSyncError("The approved direct-note policy cannot be loaded") from exc
    policies = document.get("policies") if isinstance(document, dict) else None
    policy = next(
        (
            item
            for item in (policies or [])
            if isinstance(item, dict) and item.get("policy_id") == POLICY_ID
        ),
        None,
    )
    if (
        document.get("property") != "elcid"
        or document.get("policy_version") != POLICY_VERSION
        or not policy
        or policy.get("property") != "elcid"
        or policy.get("policy_version") != POLICY_VERSION
        or policy.get("status") != "verified"
        or not policy.get("verified_at")
        or "record_guest_request"
        not in (policy.get("allowed_beds24_action") or [])
    ):
        raise NoteSyncError("The approved direct-note policy boundary is invalid")
    return {"id": POLICY_ID, "version": POLICY_VERSION}


def note_code(env: dict[str, str] | None = None) -> str:
    values = env if env is not None else os.environ
    code = str(values.get("BEDS24_NOTE_CODE") or DEFAULT_NOTE_CODE).strip().upper()
    if not NOTE_CODE_RE.fullmatch(code):
        raise NoteSyncError("BEDS24_NOTE_CODE must be 1-20 uppercase letters or digits")
    return code


def stable_hash(value: object) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:16]


def marker(event_type: str, message_id: object) -> str:
    suffix = stable_hash(f"beds24-message|{message_id}")[:12]
    return f"[AUMARA:{event_type.upper()}:{suffix}]"


def info_item_exists(
    info_items: list[dict[str, Any]],
    *,
    code: str,
    event_type: str,
) -> bool:
    event_marker = f"[AUMARA:{event_type.upper()}:"
    base_note = proposed_booking_note(event_type) or ""
    prefix = base_note.split(" —", 1)[0].casefold()
    for item in info_items:
        if str(item.get("code") or "").strip().upper() != code:
            continue
        text = str(item.get("text") or "")
        if event_marker in text or (prefix and prefix in text.casefold()):
            return True
    return False


class Beds24Client:
    """Small client whose write counter is included in every audit artifact."""

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
        self.post_requests = 0

    def request_json(
        self,
        method: str,
        path: str,
        body: object | None = None,
    ) -> tuple[int, object]:
        if method not in {"GET", "POST"}:
            raise NoteSyncError(f"Unsupported HTTP method: {method}")
        if method == "GET":
            self.get_requests += 1
        else:
            self.post_requests += 1
        payload = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            f"{self.api_base}{path}",
            data=payload,
            headers={
                "accept": "application/json",
                "content-type": "application/json",
                "token": self.token,
            },
            method=method,
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


def fetch_guest_messages(
    client: Beds24Client,
    *,
    max_age_days: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for page in range(1, 21):
        params = {
            "propertyId": PROPERTY_ID,
            "maxAge": max_age_days,
            "source": "guest",
        }
        if page > 1:
            params["page"] = page
        query = urllib.parse.urlencode(params)
        status, response = client.request_json("GET", f"/bookings/messages?{query}")
        if not 200 <= status < 300:
            raise NoteSyncError(f"Guest-message lookup failed with HTTP {status}")
        rows.extend(data_rows(response, "Message"))
        pages = response.get("pages") if isinstance(response, dict) else None
        if not isinstance(pages, dict) or not pages.get("nextPageExists"):
            return rows
    raise NoteSyncError("Guest-message pagination exceeded the 20-page safety limit")


def fetch_bookings(
    client: Beds24Client,
    booking_ids: list[int],
) -> dict[int, dict[str, Any]]:
    bookings: dict[int, dict[str, Any]] = {}
    for start in range(0, len(booking_ids), 100):
        chunk = booking_ids[start:start + 100]
        params: list[tuple[str, object]] = [
            ("propertyId", PROPERTY_ID),
            ("includeInfoItems", "true"),
        ]
        params.extend(("id", booking_id) for booking_id in chunk)
        status, response = client.request_json(
            "GET",
            f"/bookings?{urllib.parse.urlencode(params)}",
        )
        if not 200 <= status < 300:
            raise NoteSyncError(f"Booking lookup failed with HTTP {status}")
        for row in data_rows(response, "Booking"):
            booking_id = int(row.get("id") or 0)
            if booking_id:
                bookings[booking_id] = row
    return bookings


def plan_notes(
    messages: list[dict[str, Any]],
    bookings: dict[int, dict[str, Any]],
    *,
    code: str,
    mode: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidates: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []
    seen_types: set[tuple[int, str]] = set()

    for message in sorted(
        messages,
        key=lambda row: (str(row.get("time") or ""), int(row.get("id") or 0)),
    ):
        message_id = int(message.get("id") or 0)
        booking_id = int(message.get("bookingId") or 0)
        event_type = classify_event({"body": str(message.get("message") or "")})
        record = {
            "messageHash": stable_hash(message_id),
            "bookingHash": stable_hash(booking_id),
            "eventType": event_type,
            "action": "no_action",
            "reason": "unsupported_guest_message",
            "noteCode": code,
        }

        if str(message.get("source") or "").lower() != "guest":
            record["reason"] = "not_guest_source"
        elif int(message.get("propertyId") or 0) != PROPERTY_ID:
            record["reason"] = "outside_property_scope"
        elif event_type == "cot_request":
            record["reason"] = "cot_requires_specialized_worker"
        elif event_type not in LIVE_SUPPORTED_EVENT_TYPES:
            record["reason"] = "unsupported_guest_message"
        elif not message_id:
            record.update(action="manual_review", reason="message_id_missing")
        elif not booking_id or booking_id not in bookings:
            record.update(action="manual_review", reason="booking_not_resolved")
        else:
            booking = bookings[booking_id]
            status = str(booking.get("status") or "").lower()
            info_items = booking.get("infoItems") or []
            if int(booking.get("propertyId") or 0) != PROPERTY_ID:
                record["reason"] = "booking_outside_property_scope"
            elif status not in ACTIVE_STATUSES:
                record["reason"] = "booking_not_active"
            elif (booking_id, event_type) in seen_types:
                record.update(action="duplicate", reason="same_type_in_current_batch")
            elif info_item_exists(
                info_items if isinstance(info_items, list) else [],
                code=code,
                event_type=event_type,
            ):
                record.update(action="duplicate", reason="info_item_already_exists")
            else:
                seen_types.add((booking_id, event_type))
                text = (
                    f"{marker(event_type, message_id)} "
                    f"{proposed_booking_note(event_type)}"
                )
                record.update(
                    action="would_write" if mode == "audit" else "pending_write",
                    reason="approved_request_type",
                )
                candidates.append(
                    {
                        "bookingId": booking_id,
                        "messageId": message_id,
                        "eventType": event_type,
                        "code": code,
                        "text": text,
                    }
                )
        audit.append(record)
    return candidates, audit


def write_notes(
    client: Beds24Client,
    candidates: list[dict[str, Any]],
    *,
    limit: int,
) -> int:
    if len(candidates) > limit:
        raise NoteSyncError("Direct-note candidate count exceeds the live write limit")
    grouped: dict[int, list[dict[str, str]]] = defaultdict(list)
    for item in candidates:
        grouped[int(item["bookingId"])].append(
            {"code": str(item["code"]), "text": str(item["text"])}
        )
    payload = [
        {"id": booking_id, "infoItems": info_items}
        for booking_id, info_items in sorted(grouped.items())
    ]
    if not payload:
        return 0
    status, response = client.request_json("POST", "/bookings", payload)
    if status != 201 or not isinstance(response, list):
        raise NoteSyncError(f"Beds24 infoItem write failed with HTTP {status}")
    if len(response) != len(payload) or not all(
        isinstance(item, dict) and item.get("success") is True
        for item in response
    ):
        raise NoteSyncError("Beds24 returned an incomplete infoItem write result")

    expected: dict[int, set[tuple[str, str]]] = defaultdict(set)
    for item in candidates:
        expected[int(item["bookingId"])].add(
            (str(item["code"]).strip().upper(), str(item["text"]))
        )
    read_back = fetch_bookings(client, sorted(expected))
    for booking_id, expected_items in expected.items():
        row = read_back.get(booking_id)
        actual = {
            (
                str(info_item.get("code") or "").strip().upper(),
                str(info_item.get("text") or ""),
            )
            for info_item in ((row or {}).get("infoItems") or [])
            if isinstance(info_item, dict)
        }
        if not row or not expected_items.issubset(actual):
            raise NoteSyncError("Exact direct-note read-back was not confirmed")
    return len(candidates)


def run(
    client: Beds24Client,
    *,
    mode: str,
    code: str,
    max_age_days: int,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    values = env if env is not None else os.environ
    guarded_mode = operating_mode(values)
    if guarded_mode == "off":
        raise NoteSyncError("BEDS24 note sync is off")
    if guarded_mode != mode:
        raise NoteSyncError("Requested mode does not match the guarded environment")
    if note_code(values) != code:
        raise NoteSyncError(
            "Requested note code does not match the guarded environment"
        )
    if not 1 <= max_age_days <= 7:
        raise NoteSyncError("BEDS24_NOTE_MAX_AGE_DAYS must be between 1 and 7")

    policy = load_approved_policy(values)

    messages = fetch_guest_messages(client, max_age_days=max_age_days)
    booking_ids = sorted(
        {
            int(message.get("bookingId") or 0)
            for message in messages
            if int(message.get("bookingId") or 0)
        }
    )
    bookings = fetch_bookings(client, booking_ids) if booking_ids else {}
    candidates, audit = plan_notes(messages, bookings, code=code, mode=mode)

    notes_written = 0
    if mode == "live":
        notes_written = write_notes(
            client,
            candidates,
            limit=int(values["BEDS24_NOTE_MAX_WRITES"]),
        )
        for item in audit:
            if item["action"] == "pending_write":
                item["action"] = "written_and_verified"

    report = {
        "schema": "aumara-beds24-guest-note-sync-v1",
        "generatedAtUtc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "mode": mode,
        "propertyId": PROPERTY_ID,
        "policy": policy,
        "summary": {
            "messagesScanned": len(messages),
            "bookingsResolved": len(bookings),
            "noteCandidates": len(candidates),
            "notesWritten": notes_written,
            "notesReadBackVerified": notes_written,
            "manualReview": sum(item["action"] == "manual_review" for item in audit),
            "duplicates": sum(item["action"] == "duplicate" for item in audit),
        },
        "safety": {
            "guestMessagesSent": 0,
            "bookingFieldsChanged": ["infoItems"] if notes_written else [],
            "getRequests": client.get_requests,
            "postRequests": client.post_requests,
            "rawGuestMessagePersisted": False,
            "guestContactDataPersisted": False,
            "noteTextPersisted": False,
            "maximumWrites": (
                int(values.get("BEDS24_NOTE_MAX_WRITES") or "0")
                if mode == "live"
                else 0
            ),
        },
        "events": audit,
    }
    if mode == "audit" and (client.post_requests or notes_written):
        raise NoteSyncError("Audit mode violated the zero-write invariant")
    return report


def main() -> int:
    try:
        mode = operating_mode()
        code = note_code()
        max_age_days = int(os.environ.get("BEDS24_NOTE_MAX_AGE_DAYS", "3"))
        token, auth_mode, api_base, auth_source, _ = get_access_token()
        client = Beds24Client(token, api_base)
        report = run(
            client,
            mode=mode,
            code=code,
            max_age_days=max_age_days,
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
    except (AuditError, NoteSyncError, OSError, ValueError) as exc:
        print(f"Beds24 note sync failed safely: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
