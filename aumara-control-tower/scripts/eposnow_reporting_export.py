#!/usr/bin/env python3
"""Read-only Epos Now reporting export.

Authentication:
- EPOSNOW_ACCESS_TOKEN, or
- EPOSNOW_API_KEY + EPOSNOW_API_SECRET.

The date range is half-open. For Q2 2026 use 2026-04-01 through 2026-07-01.
The script performs GET requests only and never mutates the till or Back Office.
"""

from __future__ import annotations

import argparse
import base64
import csv
import datetime as dt
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any

ROOT = "https://api.eposnowhq.com"
PAGE_SIZE = 200
RETRYABLE = {408, 429, 500, 502, 503, 504}


class ExportError(RuntimeError):
    pass


def dec(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def money(value: Any) -> str:
    return f"{dec(value).quantize(Decimal('0.01'))}"


def parse_dt(value: Any) -> dt.datetime | None:
    text = str(value or "").strip().replace("Z", "+00:00")
    if not text:
        return None
    if " " in text and "T" not in text:
        text = text.replace(" ", "T", 1)
    try:
        parsed = dt.datetime.fromisoformat(text)
        if parsed.tzinfo:
            parsed = parsed.astimezone(dt.timezone.utc).replace(tzinfo=None)
        return parsed
    except ValueError:
        return None


def access_token() -> str:
    ready = os.environ.get("EPOSNOW_ACCESS_TOKEN", "").strip()
    if ready:
        return ready
    key = os.environ.get("EPOSNOW_API_KEY", "").strip()
    secret = os.environ.get("EPOSNOW_API_SECRET", "").strip()
    if not key or not secret:
        raise ExportError("Set EPOSNOW_ACCESS_TOKEN or EPOSNOW_API_KEY and EPOSNOW_API_SECRET")
    return base64.b64encode(f"{key}:{secret}".encode()).decode()


class Client:
    def __init__(self, token: str) -> None:
        self.headers = {
            "Authorization": f"Basic {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "ELCID-EposNow-Reporting/1.0",
        }

    def get(self, path: str, params: list[tuple[str, Any]] | None = None) -> Any:
        query = urllib.parse.urlencode(params or [], doseq=True)
        url = f"{ROOT}{path}" + (f"?{query}" if query else "")
        req = urllib.request.Request(url, headers=self.headers, method="GET")
        for attempt in range(5):
            try:
                with urllib.request.urlopen(req, timeout=60) as response:
                    body = response.read().decode("utf-8", "replace")
                    return json.loads(body) if body else None
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", "replace")[:600]
                if exc.code not in RETRYABLE or attempt == 4:
                    raise ExportError(f"GET {path}: HTTP {exc.code}: {body}") from exc
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                if attempt == 4:
                    raise ExportError(f"GET {path}: {exc}") from exc
            time.sleep(min(2**attempt, 12))
        raise ExportError(f"GET {path} failed")

    def pages(self, endpoint: str, params: list[tuple[str, Any]] | None = None) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for page in range(1, 10001):
            payload = self.get(f"/api/V2/{endpoint}/", [*(params or []), ("page", page)])
            if not payload:
                break
            if not isinstance(payload, list) or not all(isinstance(row, dict) for row in payload):
                raise ExportError(f"{endpoint} page {page} was not a list of objects")
            rows.extend(payload)
            if len(payload) < PAGE_SIZE:
                break
        return rows


def save_json(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def save_csv(path: pathlib.Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def by_id(rows: list[dict[str, Any]], field: str, name: str = "Name") -> dict[int, str]:
    out: dict[int, str] = {}
    for row in rows:
        try:
            key = int(row.get(field) or 0)
        except (TypeError, ValueError):
            continue
        if key:
            out[key] = str(row.get(name) or key)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", required=True, type=dt.date.fromisoformat)
    parser.add_argument("--end-date", required=True, type=dt.date.fromisoformat)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args()
    if args.end_date <= args.start_date:
        parser.error("end-date must be later than start-date")

    start = dt.datetime.combine(args.start_date, dt.time.min)
    end = dt.datetime.combine(args.end_date, dt.time.min)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    raw = output / "raw"
    client = Client(access_token())
    warnings: list[str] = []

    search = [
        ("search", f"(DateTime|>=|{start.isoformat(timespec='seconds')})"),
        ("search", f"(DateTime|<|{end.isoformat(timespec='seconds')})"),
        ("OrderBy", "DateTime"),
    ]
    try:
        tx_candidates = client.pages("Transaction", search)
    except ExportError as exc:
        warnings.append(f"Server-side date search failed; full pagination used: {exc}")
        tx_candidates = client.pages("Transaction", [("OrderBy", "DateTime")])

    transactions = [row for row in tx_candidates if (stamp := parse_dt(row.get("DateTime"))) and start <= stamp < end]
    transactions.sort(key=lambda row: parse_dt(row.get("DateTime")) or dt.datetime.min)
    tx_ids = {int(row.get("TransactionID") or 0) for row in transactions}

    all_items = client.pages("TransactionItem")
    all_tenders = client.pages("Tender")
    items = [row for row in all_items if int(row.get("TransactionID") or 0) in tx_ids]
    tenders = [row for row in all_tenders if int(row.get("TransactionID") or 0) in tx_ids]
    tender_types = client.pages("TenderType")
    products = client.pages("Product")
    tax_rates = client.pages("TaxRate")
    devices = client.pages("Device")
    locations = client.pages("Location")

    report_params = [("FromDate", start.isoformat()), ("ToDate", end.isoformat())]
    try:
        daily_sales = client.get("/api/V2/DailySales/", report_params)
    except ExportError as exc:
        warnings.append(f"DailySales unavailable: {exc}")
        daily_sales = None
    try:
        bookkeeping = client.get("/api/Reports/BookkeepingReport/", [*report_params, ("ExtendedDetails", 1)])
    except ExportError as exc:
        warnings.append(f"BookkeepingReport unavailable: {exc}")
        bookkeeping = None

    product_names = by_id(products, "ProductID")
    tender_names = by_id(tender_types, "TenderTypeID") or by_id(tender_types, "TypeID")
    device_names = by_id(devices, "DeviceID")
    location_names = by_id(locations, "LocationID")
    device_location = {int(row.get("DeviceID") or 0): int(row.get("LocationID") or 0) for row in devices if row.get("DeviceID")}
    product_tax = {int(row.get("ProductID") or 0): int(row.get("TaxRateID") or 0) for row in products if row.get("ProductID")}
    tax_name = by_id(tax_rates, "TaxRateID")
    tax_pct = {int(row.get("TaxRateID") or 0): dec(row.get("Percentage")) for row in tax_rates if row.get("TaxRateID")}

    items_by_tx: dict[int, list[dict[str, Any]]] = defaultdict(list)
    tenders_by_tx: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in items:
        items_by_tx[int(row.get("TransactionID") or 0)].append(row)
    for row in tenders:
        tenders_by_tx[int(row.get("TransactionID") or 0)].append(row)

    tx_csv: list[dict[str, Any]] = []
    item_csv: list[dict[str, Any]] = []
    tender_csv: list[dict[str, Any]] = []
    vat: dict[tuple[int, str], dict[str, Decimal]] = defaultdict(lambda: {"gross": Decimal(0), "vat": Decimal(0), "net": Decimal(0)})

    for row in items:
        product_id = int(row.get("ProductID") or 0)
        tax_id = product_tax.get(product_id, 0)
        gross = dec(row.get("Quantity")) * dec(row.get("Price")) - dec(row.get("Discount"))
        vat_amount = dec(row.get("VATAmount"))
        net = gross - vat_amount
        name = tax_name.get(tax_id, str(tax_id) if tax_id else "Unmapped")
        item_csv.append({
            "TransactionItemID": row.get("TransactionItemID", ""), "TransactionID": row.get("TransactionID", ""),
            "ProductID": product_id, "ProductName": product_names.get(product_id, str(product_id)),
            "Quantity": row.get("Quantity", ""), "UnitPrice": money(row.get("Price")), "Discount": money(row.get("Discount")),
            "Gross": money(gross), "VAT": money(vat_amount), "Net": money(net),
            "TaxRateID": tax_id, "TaxRateName": name, "TaxRatePercent": str(tax_pct.get(tax_id, Decimal(0))),
            "RefundReasonID": row.get("RefundReasonID", ""), "Notes": row.get("Notes", ""),
        })
        bucket = vat[(tax_id, name)]
        bucket["gross"] += gross
        bucket["vat"] += vat_amount
        bucket["net"] += net

    for row in tenders:
        type_id = int(row.get("TypeID") or 0)
        tender_csv.append({
            "TenderID": row.get("TenderID", ""), "TransactionID": row.get("TransactionID", ""),
            "TenderTypeID": type_id, "TenderType": tender_names.get(type_id, str(type_id)),
            "Amount": money(row.get("Amount")), "Change": money(row.get("Change")),
            "NetTender": money(dec(row.get("Amount")) - dec(row.get("Change"))),
        })

    for row in transactions:
        tx_id = int(row.get("TransactionID") or 0)
        tx_items = items_by_tx.get(tx_id, [])
        tx_tenders = tenders_by_tx.get(tx_id, [])
        item_gross = sum((dec(i.get("Quantity")) * dec(i.get("Price")) - dec(i.get("Discount")) for i in tx_items), Decimal(0))
        item_vat = sum((dec(i.get("VATAmount")) for i in tx_items), Decimal(0))
        tender_total = sum((dec(t.get("Amount")) - dec(t.get("Change")) for t in tx_tenders), Decimal(0))
        device_id = int(row.get("DeviceID") or 0)
        location_id = device_location.get(device_id, 0)
        tx_csv.append({
            "TransactionID": tx_id, "DateTime": row.get("DateTime", ""), "PaymentStatus": row.get("PaymentStatus", ""),
            "TransactionTotal": money(row.get("Total")), "ItemGross": money(item_gross), "ItemVAT": money(item_vat),
            "ItemNet": money(item_gross - item_vat), "TenderTotal": money(tender_total),
            "DeviceID": device_id, "DeviceName": device_names.get(device_id, str(device_id)),
            "LocationID": location_id, "LocationName": location_names.get(location_id, str(location_id) if location_id else ""),
            "StaffID": row.get("StaffID", ""), "CustomerID": row.get("CustomerID", ""), "Barcode": row.get("Barcode", ""),
        })

    vat_csv = [{
        "TaxRateID": key[0], "TaxRateName": key[1], "TaxRatePercent": str(tax_pct.get(key[0], Decimal(0))),
        "Gross": money(value["gross"]), "VAT": money(value["vat"]), "Net": money(value["net"]),
    } for key, value in sorted(vat.items())]

    for name, value in {
        "transactions": transactions, "transaction_items": items, "tenders": tenders,
        "tender_types": tender_types, "products": products, "tax_rates": tax_rates,
        "devices": devices, "locations": locations, "daily_sales_report": daily_sales,
        "bookkeeping_report": bookkeeping,
    }.items():
        save_json(raw / f"{name}.json", value)

    save_csv(output / "transactions.csv", list(tx_csv[0].keys()) if tx_csv else ["TransactionID"], tx_csv)
    save_csv(output / "transaction_items.csv", list(item_csv[0].keys()) if item_csv else ["TransactionItemID"], item_csv)
    save_csv(output / "tenders.csv", list(tender_csv[0].keys()) if tender_csv else ["TenderID"], tender_csv)
    save_csv(output / "vat_summary.csv", list(vat_csv[0].keys()) if vat_csv else ["TaxRateID"], vat_csv)

    manifest = {
        "schema": "elcid-eposnow-reporting-v1", "read_only": True,
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "start_inclusive": args.start_date.isoformat(), "end_exclusive": args.end_date.isoformat(),
        "counts": {"transactions": len(transactions), "items": len(items), "tenders": len(tenders)},
        "totals": {
            "transaction_total": money(sum((dec(r.get("Total")) for r in transactions), Decimal(0))),
            "item_vat": money(sum((dec(r.get("VATAmount")) for r in items), Decimal(0))),
        },
        "warnings": warnings,
    }
    save_json(output / "manifest.json", manifest)
    (output / "SUMMARY.md").write_text(
        f"# Epos Now export\n\nPeriod: {args.start_date} to {args.end_date} (exclusive)\n\n"
        f"Transactions: {len(transactions)}\n\nVAT from items: EUR {manifest['totals']['item_vat']}\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ExportError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
