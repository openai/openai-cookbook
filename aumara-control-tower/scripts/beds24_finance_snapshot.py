#!/usr/bin/env python3
"""Read-only Beds24 financial booking snapshot for AUMARA / EL CID.

No booking mutation, guest messaging, access-code handling, or secret output.
The output intentionally excludes all guest PII and keeps only operational and
financial fields needed for management reporting.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import urllib.parse
from collections import defaultdict
from typing import Any

from beds24_elcid_studio_audit import AuditError, data_rows, get_access_token, request_json

PROPERTIES = {
    324903: "EL CID",
    324882: "AUMARA",
}
INACTIVE = {"cancelled", "canceled", "black", "inquiry"}
AS_OF = dt.date.fromisoformat(os.environ.get("BEDS24_FINANCE_AS_OF", "2026-08-14"))
QUERY_FROM = dt.date.fromisoformat(os.environ.get("BEDS24_FINANCE_FROM", "2026-06-01"))
QUERY_TO = dt.date.fromisoformat(os.environ.get("BEDS24_FINANCE_TO", "2026-09-30"))
OUTPUT = pathlib.Path(
    os.environ.get(
        "BEDS24_FINANCE_OUTPUT",
        "aumara-control-tower/evidence/beds24-finance-snapshot-2026-08-14.json",
    )
)


class FinanceSnapshotError(AuditError):
    pass


def num(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def iso_date(value: Any) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(value or ""))
    except ValueError:
        return None


def invoice_totals(row: dict[str, Any]) -> tuple[float, float]:
    charges = 0.0
    payments = 0.0
    items = row.get("invoiceItems") or []
    if not isinstance(items, list):
        return charges, payments
    for item in items:
        if not isinstance(item, dict):
            continue
        amount = num(item.get("amount")) * num(item.get("qty") or 1)
        kind = str(item.get("type") or "").strip().lower()
        if kind == "charge":
            charges += amount
        elif kind == "payment":
            payments += amount
    return charges, payments


def query_for(property_id: int) -> str:
    params = [
        ("propertyId", property_id),
        ("arrivalFrom", QUERY_FROM.isoformat()),
        ("arrivalTo", QUERY_TO.isoformat()),
        ("includeInvoiceItems", "true"),
        ("includeBookingGroup", "true"),
        ("includeGuests", "false"),
    ]
    return "/bookings?" + urllib.parse.urlencode(params)


def fetch_property_bookings(token: str, api_base: str, property_id: int) -> list[dict[str, Any]]:
    status, response = request_json(
        "GET",
        query_for(property_id),
        headers={"token": token},
        api_base=api_base,
    )
    if not 200 <= status < 300:
        raise FinanceSnapshotError(f"Beds24 bookings GET failed for {property_id}: HTTP {status}")
    rows = data_rows(response, f"Beds24 property {property_id}")
    out: list[dict[str, Any]] = []
    seen: set[int] = set()
    for row in rows:
        booking_id = int(row.get("id") or 0)
        if not booking_id or booking_id in seen:
            continue
        seen.add(booking_id)
        if int(row.get("propertyId") or property_id) != property_id:
            continue
        status_name = str(row.get("status") or "").strip().lower()
        if status_name in INACTIVE:
            continue
        arrival = iso_date(row.get("arrival"))
        departure = iso_date(row.get("departure"))
        if not arrival or not departure or departure <= arrival:
            continue
        charges, payments = invoice_totals(row)
        price = num(row.get("price"))
        gross = price if price else charges
        nights = (departure - arrival).days
        out.append(
            {
                "booking_id": booking_id,
                "property_id": property_id,
                "property": PROPERTIES[property_id],
                "room_id": int(row.get("roomId") or 0) or None,
                "arrival": arrival.isoformat(),
                "departure": departure.isoformat(),
                "status": row.get("status"),
                "nights": nights,
                "gross_booked_eur": round(gross, 2),
                "invoice_charge_eur": round(charges, 2),
                "invoice_payment_eur": round(payments, 2),
                "commission_eur": round(
                    num(
                        row.get("commission")
                        or row.get("commissionAmount")
                        or row.get("commissionValue")
                    ),
                    2,
                ),
                "channel": row.get("apiSource") or row.get("bookingSource") or row.get("referer") or row.get("channel"),
                "currency": row.get("currency") or "EUR",
            }
        )
    return out


def occupied_nights(arrival: dt.date, departure: dt.date):
    day = arrival
    while day < departure:
        yield day
        day += dt.timedelta(days=1)


def summarize(bookings: list[dict[str, Any]]) -> dict[str, Any]:
    buckets: dict[tuple[str, str], dict[str, float]] = defaultdict(
        lambda: {
            "bookings": 0,
            "room_nights": 0,
            "gross_allocated_eur": 0.0,
            "commission_allocated_eur": 0.0,
        }
    )
    unique_by_bucket: dict[tuple[str, str], set[int]] = defaultdict(set)

    for row in bookings:
        arrival = dt.date.fromisoformat(row["arrival"])
        departure = dt.date.fromisoformat(row["departure"])
        nights = int(row["nights"])
        gross_per_night = num(row["gross_booked_eur"]) / nights if nights else 0.0
        commission_per_night = num(row["commission_eur"]) / nights if nights else 0.0
        for night in occupied_nights(arrival, departure):
            month = night.strftime("%Y-%m")
            key = (row["property"], month)
            unique_by_bucket[key].add(int(row["booking_id"]))
            buckets[key]["room_nights"] += 1
            buckets[key]["gross_allocated_eur"] += gross_per_night
            buckets[key]["commission_allocated_eur"] += commission_per_night

    month_rows = []
    for (prop, month), values in sorted(buckets.items()):
        values["bookings"] = len(unique_by_bucket[(prop, month)])
        month_rows.append(
            {
                "property": prop,
                "month": month,
                "bookings": int(values["bookings"]),
                "room_nights": int(values["room_nights"]),
                "gross_allocated_eur": round(values["gross_allocated_eur"], 2),
                "commission_allocated_eur": round(values["commission_allocated_eur"], 2),
            }
        )

    august_mtd = []
    august_full = []
    for prop in PROPERTIES.values():
        prop_bookings = [b for b in bookings if b["property"] == prop]
        mtd_ids: set[int] = set()
        full_ids: set[int] = set()
        mtd_nights = full_nights = 0
        mtd_gross = full_gross = 0.0
        for row in prop_bookings:
            arr = dt.date.fromisoformat(row["arrival"])
            dep = dt.date.fromisoformat(row["departure"])
            per_night = num(row["gross_booked_eur"]) / int(row["nights"])
            for night in occupied_nights(arr, dep):
                if night.year == 2026 and night.month == 8:
                    full_ids.add(int(row["booking_id"]))
                    full_nights += 1
                    full_gross += per_night
                    if night <= AS_OF:
                        mtd_ids.add(int(row["booking_id"]))
                        mtd_nights += 1
                        mtd_gross += per_night
        august_mtd.append(
            {
                "property": prop,
                "as_of": AS_OF.isoformat(),
                "active_bookings_touching_mtd": len(mtd_ids),
                "room_nights_through_as_of": mtd_nights,
                "gross_allocated_through_as_of_eur": round(mtd_gross, 2),
            }
        )
        august_full.append(
            {
                "property": prop,
                "month": "2026-08",
                "active_bookings_on_books": len(full_ids),
                "room_nights_on_books": full_nights,
                "gross_allocated_on_books_eur": round(full_gross, 2),
            }
        )

    return {
        "monthly_stay_allocation": month_rows,
        "august_through_as_of": august_mtd,
        "august_full_on_books": august_full,
    }


def main() -> int:
    token, credential_mode, api_base, credential_source, _ = get_access_token()
    bookings: list[dict[str, Any]] = []
    for property_id in PROPERTIES:
        bookings.extend(fetch_property_bookings(token, api_base, property_id))
    bookings.sort(key=lambda row: (row["arrival"], row["property"], row["booking_id"]))

    payload = {
        "schema": "aumara-beds24-finance-snapshot-v1",
        "captured_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "as_of_date": AS_OF.isoformat(),
        "query_window": {"from": QUERY_FROM.isoformat(), "to": QUERY_TO.isoformat()},
        "properties": PROPERTIES,
        "credential_mode": credential_mode,
        "credential_source": credential_source,
        "api_base": api_base,
        "read_only": True,
        "guest_pii_included": False,
        "booking_mutations": 0,
        "message_sends": 0,
        "booking_count": len(bookings),
        "summary": summarize(bookings),
        "bookings": bookings,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "OK",
                "booking_count": len(bookings),
                "output": str(OUTPUT),
                "guest_pii_included": False,
                "booking_mutations": 0,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
