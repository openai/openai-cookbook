#!/usr/bin/env python3
"""Write and verify safe EL CID bed/non-smoking guest-request notes.

The worker is deliberately fail-closed:

* property 324903 and Twin Room with Terrace only;
* active future bookings only;
* both requests must exist on a booking created in the last 7 days;
* only the Beds24 ``infoItems`` field is changed;
* no more than four live writes are allowed;
* exactly four current requests must be resolved by a write or a duplicate;
* every write is confirmed by an exact GET read-back.

It never sends a guest message or changes booking dates, rooms, occupancy,
status, price, inventory, invoice, payment, or Auto Action fields.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import re
import sys
import urllib.parse
from typing import Any, Iterable

from beds24_elcid_studio_audit import AuditError, data_rows, get_access_token
from beds24_guest_note_sync import Beds24Client, NoteSyncError


PROPERTY_ID = 324903
TWIN_ROOM_ID = 674485
NOTE_CODE = "GUESTREQUEST"
ACTIVE_STATUSES = {"confirmed", "new", "request"}
POLICY_ID = "elcid.bed-and-nonsmoking-infoitem"
POLICY_VERSION = "2026.08.02.2"
LIVE_CONFIRMATION = "INFOITEMS_ONLY_ELCID_BED_NONSMOKING_2026_08_02_3"
BOOKING_MAX_AGE_DAYS = 7
NOTE_MARKER = "BED + NON-SMOKING REQUEST"
TRUE_VALUES = {"1", "true", "yes", "on"}
DEFAULT_POLICY_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "policies"
    / "elcid-bed-nonsmoking.json"
)
BED_RE = re.compile(
    r"(?:bed\s+preference[^\n]{0,120}extra[-\s]?large\s+double|"
    r"extra[-\s]?large\s+double\s+bed|cama\s+doble\s+extra\s*grande)",
    re.IGNORECASE,
)
NONSMOKING_RE = re.compile(
    r"(?:non[\s-]*smoking(?:\s+requested|\s+accommodation|\s+room)?|"
    r"no\s+fumadores)",
    re.IGNORECASE,
)
OUTPUT = pathlib.Path(
    os.environ.get(
        "BEDS24_BED_NONSMOKING_OUTPUT",
        "aumara-control-tower/evidence/beds24-bed-nonsmoking-write.json",
    )
)


class BedNonSmokingNoteError(RuntimeError):
    """Raised when the exact safe write boundary cannot be proved."""


def integer(row: dict[str, Any], *names: str) -> int:
    for name in names:
        raw = row.get(name)
        if raw not in {None, ""}:
            try:
                return int(raw)
            except (TypeError, ValueError):
                return 0
    return 0


def enabled(values: dict[str, str], name: str) -> bool:
    return str(values.get(name) or "").strip().lower() in TRUE_VALUES


def expected_resolved(values: dict[str, str]) -> int:
    return int(values.get("BEDS24_BED_NONSMOKING_EXPECTED_RESOLVED") or "0")


def max_writes(values: dict[str, str]) -> int:
    return int(values.get("BEDS24_BED_NONSMOKING_MAX_WRITES") or "0")


def booking_max_age_days(values: dict[str, str]) -> int:
    return int(
        values.get("BEDS24_BED_NONSMOKING_BOOKING_MAX_AGE_DAYS") or "0"
    )


def require_live_guards(values: dict[str, str]) -> None:
    if (
        str(values.get("BEDS24_BED_NONSMOKING_MODE") or "").strip().lower()
        != "live"
    ):
        raise BedNonSmokingNoteError("Live mode is required")
    if enabled(values, "AUMARA_DISABLE_BOOKING_MUTATIONS"):
        raise BedNonSmokingNoteError("The booking mutation kill switch is enabled")
    if not enabled(values, "AUMARA_LIVE_BOOKING_WRITES_CONFIRMED"):
        raise BedNonSmokingNoteError("Live booking writes are not confirmed")
    if (
        str(values.get("AUMARA_BEDS24_BED_NONSMOKING_CONFIRMATION") or "")
        != LIVE_CONFIRMATION
    ):
        raise BedNonSmokingNoteError("The exact infoItems confirmation is missing")
    if max_writes(values) != 4:
        raise BedNonSmokingNoteError("Maximum writes must be exactly four")
    if expected_resolved(values) != 4:
        raise BedNonSmokingNoteError("Expected resolved requests must be exactly four")
    if booking_max_age_days(values) != BOOKING_MAX_AGE_DAYS:
        raise BedNonSmokingNoteError("Booking lookback must be exactly 7 days")
    if str(values.get("BEDS24_BED_NONSMOKING_POLICY_ID") or "") != POLICY_ID:
        raise BedNonSmokingNoteError("The approved policy ID is missing")
    if (
        str(values.get("BEDS24_BED_NONSMOKING_POLICY_VERSION") or "")
        != POLICY_VERSION
    ):
        raise BedNonSmokingNoteError("The approved policy version is missing")


def load_approved_policy(values: dict[str, str]) -> dict[str, str]:
    path = pathlib.Path(
        values.get("BEDS24_BED_NONSMOKING_POLICY_PATH") or DEFAULT_POLICY_PATH
    )
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BedNonSmokingNoteError("The approved policy cannot be loaded") from exc
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
        raise BedNonSmokingNoteError("The approved policy boundary is invalid")
    return {"id": POLICY_ID, "version": POLICY_VERSION}


def iter_strings(value: object, *, parent_key: str = "") -> Iterable[str]:
    """Yield booking source text, excluding existing operational notes."""
    if parent_key.casefold() in {"infoitems", "invoiceitems"}:
        return
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, child in value.items():
            yield from iter_strings(child, parent_key=str(key))
    elif isinstance(value, list):
        for child in value:
            yield from iter_strings(child, parent_key=parent_key)


def explicit_combined_request(
    row: dict[str, Any],
    messages: Iterable[dict[str, Any]] = (),
) -> bool:
    """Require both requests in the current booking notification payload."""
    del messages
    text = "\n".join(iter_strings(row))
    return bool(BED_RE.search(text) and NONSMOKING_RE.search(text))


def note_already_exists(info_items: object) -> bool:
    if not isinstance(info_items, list):
        return False
    texts = [
        str(item.get("text") or "")
        for item in info_items
        if isinstance(item, dict)
        and str(item.get("code") or "").strip().upper() == NOTE_CODE
    ]
    combined = "\n".join(texts).upper()
    return NOTE_MARKER in combined or (
        "BED REQUEST" in combined and "NON-SMOKING REQUEST" in combined
    )


def active_future_twin(row: dict[str, Any], today: dt.date) -> bool:
    if integer(row, "propertyId") not in {0, PROPERTY_ID}:
        return False
    if integer(row, "roomId") != TWIN_ROOM_ID:
        return False
    if str(row.get("status") or "").strip().lower() not in ACTIVE_STATUSES:
        return False
    arrival_text = str(row.get("arrival") or "")
    try:
        arrival = dt.date.fromisoformat(arrival_text)
    except ValueError:
        return False
    return arrival >= today


def recently_created_booking(
    row: dict[str, Any], *, today: dt.date, max_age_days: int
) -> bool:
    raw = str(row.get("bookingTime") or "").strip()
    match = re.match(r"^(\d{4}-\d{2}-\d{2})", raw)
    if not match:
        return False
    try:
        booked_on = dt.date.fromisoformat(match.group(1))
    except ValueError:
        return False
    oldest = today - dt.timedelta(days=max_age_days - 1)
    return oldest <= booked_on <= today


def plan_notes(
    bookings: list[dict[str, Any]],
    *,
    today: dt.date,
    max_age_days: int = BOOKING_MAX_AGE_DAYS,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    candidates: list[dict[str, Any]] = []
    audit: list[dict[str, str]] = []
    for row in sorted(bookings, key=lambda item: integer(item, "id")):
        booking_id = integer(row, "id")
        if (
            not active_future_twin(row, today)
            or not recently_created_booking(
                row, today=today, max_age_days=max_age_days
            )
            or not explicit_combined_request(row)
        ):
            continue
        if note_already_exists(row.get("infoItems")):
            audit.append({"action": "duplicate", "reason": "note_already_exists"})
            continue
        if not booking_id:
            audit.append({"action": "manual_review", "reason": "booking_id_missing"})
            continue
        candidates.append(
            {
                "bookingId": booking_id,
                "code": NOTE_CODE,
                "text": (
                    f"{NOTE_MARKER} — guest prefers one extra-large double bed "
                    "and non-smoking accommodation; subject to availability."
                ),
            }
        )
        audit.append({"action": "pending_write", "reason": "safe_rule_proved"})
    return candidates, audit


def fetch_future_twins(
    client: Beds24Client,
    *,
    today: dt.date,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for page in range(1, 21):
        params: list[tuple[str, object]] = [
            ("propertyId", PROPERTY_ID),
            ("roomId", TWIN_ROOM_ID),
            ("arrivalFrom", today.isoformat()),
            ("includeGuests", "true"),
            ("includeBookingGroup", "true"),
            ("includeInfoItems", "true"),
        ]
        if page > 1:
            params.append(("page", page))
        status, response = client.request_json(
            "GET", f"/bookings?{urllib.parse.urlencode(params)}"
        )
        if not 200 <= status < 300:
            raise BedNonSmokingNoteError(
                f"Future Twin lookup failed with HTTP {status}"
            )
        rows.extend(data_rows(response, "Booking"))
        pages = response.get("pages") if isinstance(response, dict) else None
        if not isinstance(pages, dict) or not pages.get("nextPageExists"):
            return rows
    raise BedNonSmokingNoteError("Booking pagination exceeded the safety limit")


def fetch_by_ids(
    client: Beds24Client,
    booking_ids: list[int],
) -> dict[int, dict[str, Any]]:
    params: list[tuple[str, object]] = [
        ("propertyId", PROPERTY_ID),
        ("includeInfoItems", "true"),
    ]
    params.extend(("id", booking_id) for booking_id in booking_ids)
    status, response = client.request_json(
        "GET", f"/bookings?{urllib.parse.urlencode(params)}"
    )
    if not 200 <= status < 300:
        raise BedNonSmokingNoteError(f"Read-back failed with HTTP {status}")
    return {
        integer(row, "id"): row
        for row in data_rows(response, "Booking")
        if integer(row, "id")
    }


def write_and_verify(
    client: Beds24Client,
    candidates: list[dict[str, Any]],
    *,
    limit: int,
) -> int:
    if len(candidates) > limit:
        raise BedNonSmokingNoteError("Candidate count exceeds the live write limit")
    if not candidates:
        return 0
    payload = [
        {
            "id": int(item["bookingId"]),
            "infoItems": [
                {"code": str(item["code"]), "text": str(item["text"])}
            ],
        }
        for item in candidates
    ]
    status, response = client.request_json("POST", "/bookings", payload)
    if status != 201 or not isinstance(response, list):
        raise BedNonSmokingNoteError(f"InfoItem write failed with HTTP {status}")
    if len(response) != len(payload) or not all(
        isinstance(item, dict) and item.get("success") is True
        for item in response
    ):
        raise BedNonSmokingNoteError("Beds24 returned an incomplete write result")

    expected = {int(item["bookingId"]): str(item["text"]) for item in candidates}
    read_back = fetch_by_ids(client, sorted(expected))
    for booking_id, note_text in expected.items():
        row = read_back.get(booking_id)
        if not row or not any(
            isinstance(item, dict)
            and str(item.get("code") or "").strip().upper() == NOTE_CODE
            and str(item.get("text") or "") == note_text
            for item in (row.get("infoItems") or [])
        ):
            raise BedNonSmokingNoteError("Exact note read-back was not confirmed")
    return len(candidates)


def run(
    client: Beds24Client,
    *,
    today: dt.date,
    values: dict[str, str],
) -> dict[str, Any]:
    require_live_guards(values)
    policy = load_approved_policy(values)
    bookings = fetch_future_twins(client, today=today)
    candidates, audit = plan_notes(
        bookings,
        today=today,
        max_age_days=booking_max_age_days(values),
    )
    duplicates = sum(item["action"] == "duplicate" for item in audit)
    resolved = len(candidates) + duplicates
    if resolved != expected_resolved(values):
        raise BedNonSmokingNoteError(
            f"Resolved request count {resolved}, expected "
            f"{expected_resolved(values)}; refusing all writes"
        )
    notes_written = write_and_verify(
        client, candidates, limit=max_writes(values)
    )
    for item in audit:
        if item["action"] == "pending_write":
            item["action"] = "written_and_verified"
    return {
        "schema": "elcid-beds24-bed-nonsmoking-sync-v1",
        "generatedAtUtc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "property": "elcid",
        "policy": policy,
        "summary": {
            "bookingsScanned": len(bookings),
            "bookingMaxAgeDays": booking_max_age_days(values),
            "requestsResolved": resolved,
            "safeCandidates": len(candidates),
            "notesWritten": notes_written,
            "notesReadBackVerified": notes_written,
            "duplicates": duplicates,
            "manualReview": sum(
                item["action"] == "manual_review" for item in audit
            ),
        },
        "safety": {
            "guestMessagesSent": 0,
            "bookingFieldsChanged": ["infoItems"] if notes_written else [],
            "maximumWrites": max_writes(values),
            "rawGuestDataPersisted": False,
            "bookingIdsPersisted": False,
            "noteTextPersisted": False,
        },
        "events": audit,
    }


def main() -> int:
    try:
        token, auth_mode, api_base, auth_source, _ = get_access_token()
        client = Beds24Client(token, api_base)
        today = dt.date.fromisoformat(
            os.environ.get(
                "BEDS24_BED_NONSMOKING_TODAY",
                dt.datetime.now(dt.timezone.utc).date().isoformat(),
            )
        )
        report = run(client, today=today, values=dict(os.environ))
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
    except (
        AuditError,
        BedNonSmokingNoteError,
        NoteSyncError,
        OSError,
        ValueError,
    ) as exc:
        print(f"Beds24 bed/non-smoking sync failed safely: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
