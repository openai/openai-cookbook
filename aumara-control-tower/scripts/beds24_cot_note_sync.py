#!/usr/bin/env python3
"""Write verified baby-cot infoItems for safe El Cid bookings.

This worker is deliberately narrow:

* property 324903 only;
* Twin Room with Terrace only;
* one infant cot request with no adult-capacity breach;
* infoItems only;
* at most one live write per run;
* mandatory GET read-back after POST.

It never sends guest messages or changes booking dates, room, occupancy,
status, price, inventory, invoice, or payment fields.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import re
import urllib.parse
from collections import defaultdict
from typing import Any, Iterable

from beds24_elcid_studio_audit import data_rows, get_access_token
from beds24_guest_note_sync import Beds24Client, NoteSyncError


PROPERTY_ID = 324903
TWIN_ROOM_ID = 674485
TWIN_ADULT_CAPACITY = 2
NOTE_CODE = "GUESTREQUEST"
ACTIVE_STATUSES = {"confirmed", "new", "request"}
POLICY_ID = "elcid.baby-cot-infoitem"
POLICY_VERSION = "2026.07.27.1"
LIVE_CONFIRMATION = "INFOITEMS_ONLY_ELCID_COT_POLICY_2026_07_30_1"
TRUE_VALUES = {"1", "true", "yes", "on"}
DEFAULT_POLICY_PATH = (
    pathlib.Path(__file__).resolve().parents[1] / "policies" / "elcid.yaml"
)
COT_RE = re.compile(
    r"\b(?:cuna|baby\s+cot|cot|crib|lit\s+b[ée]b[ée]|детск\w*\s+кроват\w*)\b",
    re.IGNORECASE,
)
MONTHS_RE = re.compile(
    r"\b(\d{1,2})\s*(?:mes(?:es)?|month(?:s)?|mois|месяц\w*)\b",
    re.IGNORECASE,
)
OUTPUT = pathlib.Path(
    os.environ.get(
        "BEDS24_COT_NOTE_OUTPUT",
        "aumara-control-tower/evidence/beds24-cot-note-write.json",
    )
)


class CotNoteError(RuntimeError):
    """Raised when the cot-note boundary cannot be proved."""


def enabled(values: dict[str, str], name: str) -> bool:
    return str(values.get(name) or "").strip().lower() in TRUE_VALUES


def require_live_guards(values: dict[str, str]) -> None:
    if str(values.get("BEDS24_COT_NOTE_MODE") or "").strip().lower() != "live":
        raise CotNoteError("BEDS24_COT_NOTE_MODE must be live")
    if enabled(values, "AUMARA_DISABLE_BOOKING_MUTATIONS"):
        raise CotNoteError("The booking mutation kill switch is enabled")
    if not enabled(values, "AUMARA_LIVE_BOOKING_WRITES_CONFIRMED"):
        raise CotNoteError("Live booking writes are not confirmed")
    confirmation = str(
        values.get("AUMARA_BEDS24_COT_WRITE_CONFIRMATION") or ""
    )
    if confirmation != LIVE_CONFIRMATION:
        raise CotNoteError("The exact cot infoItems confirmation is missing")
    if int(values.get("BEDS24_COT_NOTE_MAX_WRITES") or "0") != 1:
        raise CotNoteError("BEDS24_COT_NOTE_MAX_WRITES must be exactly 1")
    if str(values.get("BEDS24_COT_NOTE_POLICY_ID") or "") != POLICY_ID:
        raise CotNoteError("The approved cot policy ID is missing")
    if str(values.get("BEDS24_COT_NOTE_POLICY_VERSION") or "") != POLICY_VERSION:
        raise CotNoteError("The approved cot policy version is missing")


def load_approved_policy(values: dict[str, str]) -> dict[str, str]:
    """Load and verify the canonical fail-closed EL CID cot-note policy."""
    path = pathlib.Path(
        values.get("BEDS24_COT_NOTE_POLICY_PATH") or DEFAULT_POLICY_PATH
    )
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CotNoteError("The canonical EL CID policy cannot be loaded") from exc

    if document.get("property") != "elcid":
        raise CotNoteError("The cot policy has the wrong property boundary")
    if document.get("policy_version") != POLICY_VERSION:
        raise CotNoteError("The EL CID policy registry version is not approved")

    policies = document.get("policies")
    if not isinstance(policies, list):
        raise CotNoteError("The EL CID policy registry is malformed")
    policy = next(
        (
            item
            for item in policies
            if isinstance(item, dict) and item.get("policy_id") == POLICY_ID
        ),
        None,
    )
    if not policy:
        raise CotNoteError("The approved cot policy is absent")
    if (
        policy.get("property") != "elcid"
        or policy.get("policy_version") != POLICY_VERSION
        or policy.get("status") != "verified"
        or not policy.get("verified_at")
        or "record_guest_request"
        not in (policy.get("allowed_beds24_action") or [])
    ):
        raise CotNoteError("The cot policy does not authorize this Beds24 action")
    return {"id": POLICY_ID, "version": POLICY_VERSION}


def iter_strings(value: object, *, parent_key: str = "") -> Iterable[str]:
    """Yield booking text while excluding existing operational note text."""
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


def integer(row: dict[str, Any], *names: str) -> int:
    for name in names:
        raw = row.get(name)
        if raw not in {None, ""}:
            try:
                return int(raw)
            except (TypeError, ValueError):
                return 0
    return 0


def canonical_group_id(row: dict[str, Any]) -> int:
    return integer(row, "masterId") or integer(row, "id")


def info_item_has_cot_note(info_items: object) -> bool:
    if not isinstance(info_items, list):
        return False
    for item in info_items:
        if not isinstance(item, dict):
            continue
        if str(item.get("code") or "").strip().upper() != NOTE_CODE:
            continue
        if "BABY COT REQUIRED" in str(item.get("text") or "").upper():
            return True
    return False


def request_text(rows: list[dict[str, Any]]) -> str:
    return "\n".join(
        text
        for row in rows
        for text in iter_strings(row)
        if COT_RE.search(text)
    )


def infant_age_months(text: str) -> int | None:
    match = MONTHS_RE.search(text)
    if not match:
        return None
    months = int(match.group(1))
    return months if 0 <= months <= 24 else None


def target_booking(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the booked Twin carrying one infant without adult overflow."""
    candidates: list[dict[str, Any]] = []
    for row in rows:
        if integer(row, "propertyId") not in {0, PROPERTY_ID}:
            continue
        if integer(row, "roomId") != TWIN_ROOM_ID:
            continue
        status = str(row.get("status") or "").strip().lower()
        if status not in ACTIVE_STATUSES:
            continue
        adults = integer(row, "numAdult", "numAdults", "adults")
        children = integer(row, "numChild", "numChildren", "children")
        if adults and adults <= TWIN_ADULT_CAPACITY and children == 1:
            candidates.append(row)
    return candidates[0] if len(candidates) == 1 else None


def plan_cot_notes(
    bookings: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for booking in bookings:
        group_id = canonical_group_id(booking)
        if group_id:
            grouped[group_id].append(booking)

    candidates: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []
    for group_id, rows in sorted(grouped.items()):
        text = request_text(rows)
        if not text:
            continue
        record: dict[str, Any] = {
            "action": "manual_review",
            "reason": "safe_cot_rule_not_proved",
        }
        age_months = infant_age_months(text)
        target = target_booking(rows)
        if age_months is None:
            record["reason"] = "infant_age_not_proved"
        elif target is None:
            record["reason"] = "room_or_occupancy_not_proved"
        elif any(info_item_has_cot_note(row.get("infoItems")) for row in rows):
            record.update(action="duplicate", reason="cot_note_already_exists")
        else:
            booking_id = integer(target, "id")
            note = (
                "BABY COT REQUIRED — PREPARE BEFORE ARRIVAL — "
                f"Booking {group_id} — infant age {age_months} months."
            )
            candidates.append(
                {
                    "bookingId": booking_id,
                    "groupId": group_id,
                    "code": NOTE_CODE,
                    "text": note,
                }
            )
            record.update(action="pending_write", reason="safe_cot_rule_proved")
        audit.append(record)
    return candidates, audit


def fetch_future_bookings(
    client: Beds24Client,
    *,
    today: dt.date,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for page in range(1, 21):
        params: list[tuple[str, object]] = [
            ("propertyId", PROPERTY_ID),
            ("arrivalFrom", today.isoformat()),
            ("includeGuests", "true"),
            ("includeBookingGroup", "true"),
            ("includeInfoItems", "true"),
        ]
        if page > 1:
            params.append(("page", page))
        status, response = client.request_json(
            "GET",
            f"/bookings?{urllib.parse.urlencode(params)}",
        )
        if not 200 <= status < 300:
            raise CotNoteError(f"Future booking lookup failed with HTTP {status}")
        rows.extend(data_rows(response, "Booking"))
        pages = response.get("pages") if isinstance(response, dict) else None
        if not isinstance(pages, dict) or not pages.get("nextPageExists"):
            return rows
    raise CotNoteError("Booking pagination exceeded the 20-page safety limit")


def fetch_by_ids(
    client: Beds24Client,
    booking_ids: list[int],
) -> dict[int, dict[str, Any]]:
    rows: dict[int, dict[str, Any]] = {}
    params: list[tuple[str, object]] = [
        ("propertyId", PROPERTY_ID),
        ("includeInfoItems", "true"),
    ]
    params.extend(("id", booking_id) for booking_id in booking_ids)
    status, response = client.request_json(
        "GET",
        f"/bookings?{urllib.parse.urlencode(params)}",
    )
    if not 200 <= status < 300:
        raise CotNoteError(f"Read-back lookup failed with HTTP {status}")
    for row in data_rows(response, "Booking"):
        booking_id = integer(row, "id")
        if booking_id:
            rows[booking_id] = row
    return rows


def write_and_verify(
    client: Beds24Client,
    candidates: list[dict[str, Any]],
) -> int:
    if len(candidates) > 1:
        raise CotNoteError("More than one cot note candidate; refusing live write")
    if not candidates:
        return 0
    candidate = candidates[0]
    payload = [
        {
            "id": int(candidate["bookingId"]),
            "infoItems": [
                {
                    "code": str(candidate["code"]),
                    "text": str(candidate["text"]),
                }
            ],
        }
    ]
    status, response = client.request_json("POST", "/bookings", payload)
    if status != 201 or not isinstance(response, list):
        raise CotNoteError(f"Beds24 infoItem write failed with HTTP {status}")
    if len(response) != 1 or not isinstance(response[0], dict):
        raise CotNoteError("Beds24 returned an incomplete write response")
    if response[0].get("success") is not True:
        raise CotNoteError("Beds24 rejected the cot infoItem")

    booking_id = int(candidate["bookingId"])
    read_back = fetch_by_ids(client, [booking_id]).get(booking_id)
    if not read_back:
        raise CotNoteError("Written booking was absent from read-back")
    expected = str(candidate["text"])
    if not any(
        isinstance(item, dict)
        and str(item.get("code") or "").strip().upper() == NOTE_CODE
        and str(item.get("text") or "") == expected
        for item in (read_back.get("infoItems") or [])
    ):
        raise CotNoteError("Cot infoItem was not confirmed by read-back")
    return 1


def run(
    client: Beds24Client,
    *,
    today: dt.date,
    values: dict[str, str],
) -> dict[str, Any]:
    require_live_guards(values)
    policy = load_approved_policy(values)
    bookings = fetch_future_bookings(client, today=today)
    candidates, audit = plan_cot_notes(bookings)
    duplicates = sum(item["action"] == "duplicate" for item in audit)
    if not candidates and not duplicates:
        raise CotNoteError("No safe cot request was resolved")
    notes_written = write_and_verify(client, candidates)
    for item in audit:
        if item["action"] == "pending_write":
            item["action"] = "written_and_verified"
    return {
        "schema": "elcid-beds24-cot-note-sync-v1",
        "generatedAtUtc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "property": "elcid",
        "policy": policy,
        "summary": {
            "bookingsScanned": len(bookings),
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
            "maximumWrites": 1,
            "rawGuestDataPersisted": False,
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
                "BEDS24_COT_NOTE_TODAY",
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
    except (CotNoteError, NoteSyncError, OSError, ValueError) as exc:
        print(f"Beds24 cot note sync failed safely: {exc}", file=os.sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
