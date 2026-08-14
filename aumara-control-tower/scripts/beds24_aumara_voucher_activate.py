#!/usr/bin/env python3
"""Idempotently activate one AUMARA guest percentage voucher in Beds24.

Uses the existing BEDS24_REFRESH_TOKEN. Never prints credentials. Preserves all
existing voucher slots and only appends the requested code to a compatible
percentage slot or creates one free slot.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

from beds24_elcid_studio_audit import AuditError, data_rows, get_access_token, request_json

PROPERTY_ID = 324882
CODE = os.environ.get("AUMARA_VOUCHER_CODE", "AUMGIB90045089").strip()
DISCOUNT = float(os.environ.get("AUMARA_VOUCHER_PERCENT", "10"))
APPLY = os.environ.get("AUMARA_VOUCHER_APPLY", "0") == "1"


class VoucherError(AuditError):
    pass


def request_json_body(method: str, path: str, token: str, api_base: str, payload: object):
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    req = urllib.request.Request(
        f"{api_base}{path}",
        data=raw,
        headers={"accept": "application/json", "content-type": "application/json", "token": token},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            body = response.read().decode("utf-8", "replace")
            return response.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        try:
            parsed = json.loads(body) if body else {}
        except json.JSONDecodeError:
            parsed = {"error": body[:300]}
        return exc.code, parsed


def phrases(row: dict) -> list[str]:
    return [part.strip() for part in str(row.get("phrase") or "").split(",") if part.strip()]


def compatible(row: dict) -> bool:
    try:
        pct = float(row.get("discount") or 0)
    except (TypeError, ValueError):
        return False
    return str(row.get("type") or "") == "percentage" and abs(pct - DISCOUNT) < 0.0001


def fetch_property(token: str, api_base: str) -> dict:
    status, response = request_json("GET", f"/properties?id={PROPERTY_ID}", headers={"token": token}, api_base=api_base)
    if not 200 <= status < 300:
        raise VoucherError(f"Beds24 property GET failed: HTTP {status}")
    rows = data_rows(response, "AUMARA property")
    if len(rows) != 1 or int(rows[0].get("id") or 0) != PROPERTY_ID:
        raise VoucherError("AUMARA property response was not uniquely scoped")
    return rows[0]


def plan(vouchers: list[dict]) -> tuple[list[dict], int, bool]:
    occurrences = [(row, phrases(row)) for row in vouchers if CODE in phrases(row)]
    if occurrences:
        if len(occurrences) != 1 or not compatible(occurrences[0][0]):
            raise VoucherError("Voucher code already exists with conflicting Beds24 configuration")
        return vouchers, int(occurrences[0][0].get("number") or 0), False

    target = next((row for row in vouchers if compatible(row)), None)
    if target is None:
        used = {int(row.get("number") or 0) for row in vouchers}
        free = next((n for n in range(1, 9) if n not in used), None)
        if free is None:
            raise VoucherError("No free Beds24 discount voucher slot and no compatible 10% slot")
        target = {"number": free, "phrase": "", "discount": DISCOUNT, "type": "percentage"}
        vouchers.append(target)

    current = phrases(target)
    current.append(CODE)
    target["phrase"] = ",".join(dict.fromkeys(current))
    target["discount"] = DISCOUNT
    target["type"] = "percentage"
    return vouchers, int(target["number"]), True


def main() -> int:
    if not re.fullmatch(r"[A-Za-z0-9]+", CODE):
        raise VoucherError("Voucher code must be strictly alphanumeric")
    token, _, api_base, _, _ = get_access_token()
    prop = fetch_property(token, api_base)
    existing = prop.get("discountVouchers") or []
    if not isinstance(existing, list) or not all(isinstance(row, dict) for row in existing):
        raise VoucherError("Beds24 discountVouchers is not a valid array")
    vouchers = [dict(row) for row in existing]
    vouchers, slot, changed = plan(vouchers)

    if changed and APPLY:
        status, _ = request_json_body(
            "POST", "/properties", token, api_base, [{"id": PROPERTY_ID, "discountVouchers": vouchers}]
        )
        if not 200 <= status < 300:
            raise VoucherError(f"Beds24 property POST failed: HTTP {status}")
        verify = fetch_property(token, api_base)
        verified = [row for row in (verify.get("discountVouchers") or []) if CODE in phrases(row)]
        if len(verified) != 1 or not compatible(verified[0]):
            raise VoucherError("Beds24 voucher verification failed after write")
        slot = int(verified[0].get("number") or slot)

    print(json.dumps({
        "status": "active" if APPLY else "planned",
        "changed": changed,
        "property_id": PROPERTY_ID,
        "voucher_code": CODE,
        "discount_percent": DISCOUNT,
        "slot": slot,
        "voucher_type": "percentage",
        "credentials_exposed": False,
    }, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
