#!/usr/bin/env python3
"""Build one read-only AUMARA Daily Ops snapshot from existing source exports.

The builder never connects to external services. It consumes reviewed snapshots
produced by the existing Gmail, Beds24, Epos Now and Bitrix24 paths and writes a
single canonical JSON document for the existing Control Tower.

Unavailable sources stay unavailable: missing inputs are never converted to
zero activity.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import pathlib
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo


SCHEMA = "aumara-daily-ops-v1"
TIMEZONE = "Europe/Madrid"
MADRID = ZoneInfo(TIMEZONE)
SOURCE_SLAS = {
    "gmail": 150,
    "beds24": 150,
    "epos": 1_440,
    "b24": 150,
}

METRIC_KEYS = (
    "guestEvents",
    "confirmedSentReplies",
    "cancellationFollowUps",
    "opsLogged",
    "needsDecision",
    "beds24NotesPending",
    "lostReplies",
    "deliveryErrors",
    "draftReplies",
    "newBookings",
    "modifiedBookings",
    "cancelledBookings",
    "bookedRevenueAddedEur",
    "bookedRevenueCancelledEur",
    "bookedRevenueNetEur",
    "arrivals",
    "departures",
    "occupiedRoomNights",
    "restaurantSalesGrossEur",
    "restaurantVatEur",
    "restaurantCashEur",
    "restaurantCardEur",
    "restaurantRefundsEur",
    "restaurantTransactions",
    "b24OpenTasks",
    "b24ClosedToday",
    "b24OverdueTasks",
)


class SnapshotError(RuntimeError):
    """Raised when a supplied snapshot cannot be trusted."""


def read_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SnapshotError(f"Cannot read JSON snapshot {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SnapshotError(f"JSON snapshot {path} must contain one object")
    return value


def parse_timestamp(value: Any) -> dt.datetime | None:
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


def iso_utc(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def number(value: Any) -> float:
    try:
        return float(Decimal(str(value or 0)))
    except (InvalidOperation, TypeError, ValueError):
        return 0.0


def optional_number(mapping: dict[str, Any], *keys: str) -> float | None:
    value = first_value(mapping, *keys)
    if value is None:
        return None
    try:
        return float(Decimal(str(value)))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise SnapshotError(f"Metric {keys[0]} must be numeric") from exc


def optional_integer(mapping: dict[str, Any], *keys: str) -> int | None:
    value = first_value(mapping, *keys)
    if value is None:
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise SnapshotError(f"Metric {keys[0]} must be an integer") from exc
    if parsed != parsed.to_integral_value():
        raise SnapshotError(f"Metric {keys[0]} must be an integer")
    return int(parsed)


def first_value(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None


def missing_metric_issues(
    source_id: str,
    metrics: dict[str, Any],
) -> list[str]:
    return [
        f"{source_id} metric is unavailable: {key}"
        for key, value in metrics.items()
        if value is None
    ]


def source_state(
    source_id: str,
    *,
    path: pathlib.Path | None,
    payload: dict[str, Any] | None,
    captured_at: dt.datetime | None,
    now: dt.datetime,
    message: str | None = None,
) -> dict[str, Any]:
    if payload is None:
        return {
            "id": source_id,
            "status": "unavailable",
            "capturedAtUtc": None,
            "freshnessMinutes": None,
            "freshnessSlaMinutes": SOURCE_SLAS[source_id],
            "message": message or "No reviewed input snapshot supplied",
            "input": None,
        }

    explicit = str(payload.get("status") or "").strip().upper()
    if explicit in {"BLOCKED", "ERROR", "FAILED"}:
        blocker = payload.get("blocker")
        detail = None
        if isinstance(blocker, dict):
            detail = blocker.get("code") or blocker.get("detail")
        return {
            "id": source_id,
            "status": "blocked",
            "capturedAtUtc": iso_utc(captured_at) if captured_at else None,
            "freshnessMinutes": None,
            "freshnessSlaMinutes": SOURCE_SLAS[source_id],
            "message": str(detail or message or explicit),
            "input": path.name if path else None,
        }

    if captured_at is None:
        return {
            "id": source_id,
            "status": "blocked",
            "capturedAtUtc": None,
            "freshnessMinutes": None,
            "freshnessSlaMinutes": SOURCE_SLAS[source_id],
            "message": message or "Snapshot has no valid capture timestamp",
            "input": path.name if path else None,
        }

    age = max(0, int((now - captured_at).total_seconds() // 60))
    return {
        "id": source_id,
        "status": "healthy" if age <= SOURCE_SLAS[source_id] else "stale",
        "capturedAtUtc": iso_utc(captured_at),
        "freshnessMinutes": age,
        "freshnessSlaMinutes": SOURCE_SLAS[source_id],
        "message": message,
        "input": path.name if path else None,
    }


def event_date(event: dict[str, Any]) -> dt.date | None:
    stamp = parse_timestamp(
        first_value(
            event,
            "occurredAtUtc",
            "occurred_at_utc",
            "at",
            "time",
            "timestamp",
        )
    )
    return stamp.astimezone(MADRID).date() if stamp else None


def normalize_event(
    event: dict[str, Any],
    *,
    source: str,
    business_date: dt.date,
) -> dict[str, Any] | None:
    day = event_date(event)
    if day is not None and day != business_date:
        return None

    occurred = first_value(
        event,
        "occurredAtUtc",
        "occurred_at_utc",
        "at",
        "time",
        "timestamp",
    )
    event_type = str(
        first_value(event, "eventType", "event_type", "type", "event") or "event"
    )
    booking_ref = first_value(
        event,
        "bookingRef",
        "booking_reference",
        "bookingHash",
        "booking_hash",
        "reference",
    )
    summary = str(
        first_value(event, "summary", "content", "action", "lastEventType")
        or event_type.replace("_", " ")
    ).strip()
    existing_id = first_value(event, "eventId", "event_id", "id")
    if existing_id:
        event_id = str(existing_id)
    else:
        material = "|".join(
            (
                source,
                str(occurred or business_date.isoformat()),
                str(booking_ref or ""),
                event_type,
                summary,
            )
        )
        event_id = hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]

    return {
        "eventId": event_id,
        "at": str(occurred or ""),
        "source": source,
        "property": first_value(event, "property", "object", "propertyName"),
        "guest": first_value(event, "guest", "guestName"),
        "bookingRef": booking_ref,
        "type": event_type,
        "status": str(first_value(event, "status", "result") or "recorded"),
        "amountEur": (
            number(first_value(event, "amountEur", "amount_eur", "amount"))
            if first_value(event, "amountEur", "amount_eur", "amount") is not None
            else None
        ),
        "recipient": first_value(event, "recipient", "to"),
        "summary": summary,
        "actionUrl": first_value(event, "actionUrl", "action_url", "url"),
        "requiresDecision": bool(
            first_value(event, "requiresDecision", "requires_decision")
            or event_type in {"needs_decision", "unanswered_guest_message"}
        ),
    }


def gmail_adapter(
    path: pathlib.Path | None,
    *,
    business_date: dt.date,
    now: dt.datetime,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], list[str]]:
    if path is None:
        return source_state(
            "gmail", path=None, payload=None, captured_at=None, now=now
        ), {}, [], ["Gmail input is unavailable"]
    payload = read_json(path)
    captured = parse_timestamp(
        first_value(payload, "generatedAtUtc", "capturedAtUtc", "generated_at_utc")
    )
    counters = payload.get("counters") or payload.get("summary") or {}
    if not isinstance(counters, dict):
        raise SnapshotError("Gmail counters must be an object")
    metrics = {
        "guestEvents": optional_integer(
            counters, "eventsReceived", "receivedEvents", "events"
        ),
        "confirmedSentReplies": optional_integer(
            counters, "confirmedSentReplies", "sentReplies"
        ),
        "cancellationFollowUps": optional_integer(
            counters, "cancellationFollowUps", "cancelFollowUps"
        ),
        "opsLogged": optional_integer(counters, "opsLogged", "logged"),
        "needsDecision": optional_integer(
            counters, "needsDecision", "manualDecisions"
        ),
        "beds24NotesPending": optional_integer(
            counters, "beds24NotesPending", "pendingBeds24Notes"
        ),
        "lostReplies": optional_integer(counters, "lostReplies", "unanswered"),
        "deliveryErrors": optional_integer(
            counters, "deliveryErrors", "bounces"
        ),
        "draftReplies": optional_integer(counters, "draftReplies", "drafts"),
    }
    raw_events = payload.get("events") or []
    if not isinstance(raw_events, list):
        raise SnapshotError("Gmail events must be a list")
    events = [
        normalized
        for row in raw_events
        if isinstance(row, dict)
        if (normalized := normalize_event(
            row, source="gmail", business_date=business_date
        ))
    ]
    return source_state(
        "gmail", path=path, payload=payload, captured_at=captured, now=now
    ), metrics, events, missing_metric_issues("gmail", metrics)


def beds24_adapter(
    path: pathlib.Path | None,
    *,
    business_date: dt.date,
    now: dt.datetime,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], list[str]]:
    if path is None:
        return source_state(
            "beds24", path=None, payload=None, captured_at=None, now=now
        ), {}, [], ["Beds24 input is unavailable"]
    payload = read_json(path)
    captured = parse_timestamp(
        first_value(payload, "generatedAtUtc", "capturedAtUtc", "generated_at_utc")
    )
    summary = payload.get("summary") or {}
    if not isinstance(summary, dict):
        raise SnapshotError("Beds24 summary must be an object")
    revenue_added = optional_number(
        summary, "bookedRevenueAddedEur", "revenueAddedEur"
    )
    revenue_cancelled = optional_number(
        summary, "bookedRevenueCancelledEur", "revenueCancelledEur"
    )
    metrics = {
        "newBookings": optional_integer(
            summary, "newBookings", "createdBookings"
        ),
        "modifiedBookings": optional_integer(
            summary, "modifiedBookings", "bookingModifications"
        ),
        "cancelledBookings": optional_integer(
            summary, "cancelledBookings", "cancellations"
        ),
        "bookedRevenueAddedEur": revenue_added,
        "bookedRevenueCancelledEur": revenue_cancelled,
        "bookedRevenueNetEur": (
            revenue_added - revenue_cancelled
            if revenue_added is not None and revenue_cancelled is not None
            else None
        ),
        "arrivals": optional_integer(summary, "arrivals", "checkIns"),
        "departures": optional_integer(summary, "departures", "checkOuts"),
        "occupiedRoomNights": optional_integer(
            summary, "occupiedRoomNights", "roomNights"
        ),
    }
    events: list[dict[str, Any]] = []
    conversations = payload.get("conversations") or []
    if isinstance(conversations, list):
        for row in conversations:
            if not isinstance(row, dict) or not row.get("unanswered"):
                continue
            normalized = normalize_event(
                {
                    **row,
                    "eventId": row.get("conversationId"),
                    "occurredAtUtc": row.get("lastMessageAtUtc"),
                    "eventType": "unanswered_guest_message",
                    "status": "attention",
                    "summary": "Beds24 conversation has no later host response",
                    "requiresDecision": True,
                },
                source="beds24",
                business_date=business_date,
            )
            if normalized:
                events.append(normalized)
    issues = missing_metric_issues("beds24", metrics)
    if payload.get("status") == "BLOCKED":
        blocker = payload.get("blocker")
        if isinstance(blocker, dict):
            issues.append(
                f"Beds24 blocked: {blocker.get('code') or blocker.get('detail')}"
            )
    return source_state(
        "beds24", path=path, payload=payload, captured_at=captured, now=now
    ), metrics, events, issues


def read_epos_tenders(
    path: pathlib.Path,
) -> tuple[float | None, float | None, float | None, list[str]]:
    cash = Decimal("0")
    card = Decimal("0")
    refunds = Decimal("0")
    if not path.exists():
        return None, None, None, ["epos input is unavailable: tenders.csv"]
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        required = {"TenderType", "NetTender"}
        if not required.issubset(set(reader.fieldnames or [])):
            return None, None, None, [
                "epos tenders.csv is missing TenderType or NetTender"
            ]
        for row in reader:
            tender = str(row.get("TenderType") or "").casefold()
            try:
                amount = Decimal(str(row.get("NetTender") or 0))
            except InvalidOperation as exc:
                raise SnapshotError("Epos NetTender must be numeric") from exc
            if amount < 0:
                refunds += abs(amount)
            if any(word in tender for word in ("cash", "efectivo", "contado")):
                cash += amount
            elif any(
                word in tender
                for word in ("card", "tarjeta", "visa", "mastercard", "amex")
            ):
                card += amount
    return float(cash), float(card), float(refunds), []


def epos_adapter(
    directory: pathlib.Path | None,
    *,
    now: dt.datetime,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], list[str]]:
    if directory is None:
        return source_state(
            "epos", path=None, payload=None, captured_at=None, now=now
        ), {}, [], ["Epos Now input is unavailable"]
    manifest_path = directory / "manifest.json"
    payload = read_json(manifest_path)
    captured = parse_timestamp(
        first_value(payload, "generated_at_utc", "generatedAtUtc")
    )
    totals = payload.get("totals") or {}
    counts = payload.get("counts") or {}
    if not isinstance(totals, dict) or not isinstance(counts, dict):
        raise SnapshotError("Epos manifest totals/counts must be objects")
    cash, card, refunds, tender_issues = read_epos_tenders(
        directory / "tenders.csv"
    )
    metrics = {
        "restaurantSalesGrossEur": optional_number(
            totals, "transaction_total", "salesGrossEur"
        ),
        "restaurantVatEur": optional_number(totals, "item_vat", "vatEur"),
        "restaurantCashEur": cash,
        "restaurantCardEur": card,
        "restaurantRefundsEur": refunds,
        "restaurantTransactions": optional_integer(
            counts, "transactions", "transactionCount"
        ),
    }
    issues = [
        *[str(value) for value in payload.get("warnings") or []],
        *tender_issues,
        *missing_metric_issues("epos", metrics),
    ]
    return source_state(
        "epos",
        path=manifest_path,
        payload=payload,
        captured_at=captured,
        now=now,
        message="; ".join(issues[:2]) or None,
    ), metrics, [], issues


def b24_adapter(
    path: pathlib.Path | None,
    *,
    business_date: dt.date,
    now: dt.datetime,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], list[str]]:
    if path is None:
        return source_state(
            "b24", path=None, payload=None, captured_at=None, now=now
        ), {}, [], ["Bitrix24 input is unavailable"]
    payload = read_json(path)
    captured = parse_timestamp(
        first_value(payload, "generatedAtUtc", "capturedAtUtc", "generated_at_utc")
    )
    summary = payload.get("summary") or {}
    if not isinstance(summary, dict):
        raise SnapshotError("Bitrix24 summary must be an object")
    metrics = {
        "b24OpenTasks": optional_integer(summary, "openTasks", "open"),
        "b24ClosedToday": optional_integer(
            summary, "closedToday", "closed"
        ),
        "b24OverdueTasks": optional_integer(
            summary, "overdueTasks", "overdue"
        ),
    }
    raw_events = payload.get("events") or []
    if not isinstance(raw_events, list):
        raise SnapshotError("Bitrix24 events must be a list")
    events = [
        normalized
        for row in raw_events
        if isinstance(row, dict)
        if (normalized := normalize_event(
            row, source="b24", business_date=business_date
        ))
    ]
    return source_state(
        "b24", path=path, payload=payload, captured_at=captured, now=now
    ), metrics, events, missing_metric_issues("b24", metrics)


def deduplicate_events(events: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    seen: set[str] = set()
    output: list[dict[str, Any]] = []
    duplicates = 0
    for event in sorted(events, key=lambda item: (str(item.get("at")), item["eventId"])):
        event_id = str(event["eventId"])
        if event_id in seen:
            duplicates += 1
            continue
        seen.add(event_id)
        output.append(event)
    return output, duplicates


def build_snapshot(
    *,
    business_date: dt.date,
    now: dt.datetime,
    gmail_path: pathlib.Path | None = None,
    beds24_path: pathlib.Path | None = None,
    epos_directory: pathlib.Path | None = None,
    b24_path: pathlib.Path | None = None,
) -> dict[str, Any]:
    current = now.astimezone(dt.timezone.utc)
    adapters = (
        gmail_adapter(gmail_path, business_date=business_date, now=current),
        beds24_adapter(beds24_path, business_date=business_date, now=current),
        epos_adapter(epos_directory, now=current),
        b24_adapter(b24_path, business_date=business_date, now=current),
    )
    sources: list[dict[str, Any]] = []
    metrics: dict[str, Any] = {key: None for key in METRIC_KEYS}
    events: list[dict[str, Any]] = []
    issues: list[str] = []

    for source, source_metrics, source_events, source_issues in adapters:
        sources.append(source)
        if source["status"] not in {"unavailable", "blocked"}:
            metrics.update(source_metrics)
            events.extend(source_events)
        issues.extend(source_issues)

    events, duplicates = deduplicate_events(events)
    if duplicates:
        issues.append(f"{duplicates} duplicate event(s) removed")

    unhealthy = [
        source for source in sources if source["status"] != "healthy"
    ]
    available = [
        source
        for source in sources
        if source["status"] not in {"unavailable", "blocked"}
    ]
    if not available:
        quality_status = "blocked"
    elif unhealthy or issues:
        quality_status = "partial"
    else:
        quality_status = "ready"

    for source in unhealthy:
        issues.append(
            f"{source['id']} source is {source['status']}: "
            f"{source.get('message') or 'freshness threshold exceeded'}"
        )

    return {
        "schema": SCHEMA,
        "businessDate": business_date.isoformat(),
        "timezone": TIMEZONE,
        "generatedAtUtc": iso_utc(current),
        "dataQuality": {
            "status": quality_status,
            "duplicateEventsRemoved": duplicates,
            "issues": list(dict.fromkeys(issues)),
            "unavailableMetricsAreNull": True,
        },
        "sources": sources,
        "metrics": metrics,
        "events": events,
    }


def write_json_atomic(path: pathlib.Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(serialized, encoding="utf-8")
    temporary.replace(path)


def write_history_snapshot(
    directory: pathlib.Path,
    value: dict[str, Any],
) -> pathlib.Path:
    generated = str(value["generatedAtUtc"]).replace("-", "").replace(":", "")
    generated = generated.replace("T", "-").replace("Z", "Z")
    target = directory / str(value["businessDate"]) / f"{generated}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    try:
        with target.open("x", encoding="utf-8") as handle:
            handle.write(serialized)
    except FileExistsError:
        if target.read_text(encoding="utf-8") != serialized:
            raise SnapshotError(
                f"History snapshot already exists with different content: {target}"
            )
    return target


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", type=dt.date.fromisoformat)
    parser.add_argument("--now", type=parse_timestamp)
    parser.add_argument("--gmail", type=pathlib.Path)
    parser.add_argument("--beds24", type=pathlib.Path)
    parser.add_argument("--epos-dir", type=pathlib.Path)
    parser.add_argument("--b24", type=pathlib.Path)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    parser.add_argument("--history-dir", type=pathlib.Path)
    args = parser.parse_args()

    now = args.now or dt.datetime.now(dt.timezone.utc)
    business_date = args.date or now.astimezone(MADRID).date()
    snapshot = build_snapshot(
        business_date=business_date,
        now=now,
        gmail_path=args.gmail,
        beds24_path=args.beds24,
        epos_directory=args.epos_dir,
        b24_path=args.b24,
    )
    write_json_atomic(args.output, snapshot)
    if args.history_dir:
        write_history_snapshot(args.history_dir, snapshot)
    print(
        json.dumps(
            {
                "schema": snapshot["schema"],
                "businessDate": snapshot["businessDate"],
                "dataQuality": snapshot["dataQuality"]["status"],
                "events": len(snapshot["events"]),
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SnapshotError as exc:
        print(f"ERROR: {exc}", file=__import__("sys").stderr)
        raise SystemExit(2)
