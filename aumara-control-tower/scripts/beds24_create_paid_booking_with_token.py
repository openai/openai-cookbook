import datetime as dt
import json
import os
import pathlib
import urllib.error
import urllib.parse
import urllib.request

API_BASE = "https://beds24.com/api/v2"
ROOT = pathlib.Path(__file__).resolve().parents[1]
REQUEST_FILE = ROOT / "beds24-requests" / "AUMARA-MEDINA-20260718-660.json"
EVIDENCE_DIR = ROOT / "evidence"
BOOKING_EVIDENCE = EVIDENCE_DIR / "beds24-AUMARA-MEDINA-20260718-660.json"
AUTH_EVIDENCE = EVIDENCE_DIR / "beds24-token-auth-status.json"

EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
TOKEN = "".join((os.environ.get("BEDS24_TOKEN_CREDENTIAL") or os.environ.get("BEDS24_BOOTSTRAP_CREDENTIAL") or "").split())
if not TOKEN:
    raise SystemExit("Missing Beds24 token credential")


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def request_json(method: str, path: str, payload=None):
    body = None
    headers = {"accept": "application/json", "token": TOKEN}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["content-type"] = "application/json"
    req = urllib.request.Request(f"{API_BASE}{path}", data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            raw = response.read().decode("utf-8", "replace")
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            parsed = json.loads(raw) if raw else {}
        except Exception:
            parsed = {"raw": raw[:500]}
        return exc.code, parsed


def safe_response(obj):
    if isinstance(obj, dict):
        out = {}
        for key, value in obj.items():
            if key.lower() in {"token", "refreshtoken", "code"}:
                out[key] = "[REDACTED]"
            else:
                out[key] = value
        return out
    return str(obj)[:500]


req = json.loads(REQUEST_FILE.read_text())
api_reference = req["request_id"]
query = urllib.parse.urlencode(
    [
        ("apiReference", api_reference),
        ("includeInvoiceItems", "true"),
        ("includeGuests", "true"),
    ]
)

status, probe = request_json("GET", f"/bookings?{query}")
AUTH_EVIDENCE.write_text(
    json.dumps(
        {
            "verified_at_utc": now(),
            "status": "TOKEN_OK" if 200 <= status < 300 else "TOKEN_REJECTED",
            "http_status": status,
            "response": safe_response(probe) if not (200 <= status < 300) else {"success": True},
            "secret_present": True,
            "plaintext_secret_committed": False,
        },
        indent=2,
    )
)
if not (200 <= status < 300):
    raise SystemExit(f"Beds24 direct token rejected with HTTP {status}")

rows = probe.get("data") or []
active = [row for row in rows if row.get("status") != "cancelled"]
outcome = "reused_existing"

if not active:
    payload = [
        {
            "roomId": req["room_id"],
            "status": "confirmed",
            "arrival": req["arrival"],
            "departure": req["departure"],
            "firstName": req["first_name"],
            "lastName": req["last_name"],
            "country": req.get("country", "Spain"),
            "apiReference": api_reference,
            "price": req["total_price"],
            "comment": req["comments"],
            "invoiceItems": [
                {
                    "type": "charge",
                    "description": req["charge_description"],
                    "qty": 1,
                    "amount": req["total_price"],
                },
                {
                    "type": "payment",
                    "description": req["payment_description"],
                    "qty": 1,
                    "amount": req["amount_paid"],
                },
            ],
        }
    ]
    status, created = request_json("POST", "/bookings", payload)
    if not (200 <= status < 300):
        raise SystemExit(f"Beds24 booking create failed HTTP {status}: {safe_response(created)}")
    if not isinstance(created, list) or not created or not created[0].get("success"):
        raise SystemExit(f"Beds24 booking create returned unexpected result: {safe_response(created)}")
    outcome = "created_new"
    status, verified = request_json("GET", f"/bookings?{query}")
    if not (200 <= status < 300):
        raise SystemExit(f"Beds24 booking read-back failed HTTP {status}: {safe_response(verified)}")
    rows = verified.get("data") or []
    active = [row for row in rows if row.get("status") != "cancelled"]

if len(active) != 1:
    raise SystemExit(f"Expected exactly one active booking for {api_reference}; found {len(active)}")

booking = active[0]
if str(booking.get("roomId")) != str(req["room_id"]):
    raise SystemExit(f"Room mismatch: expected {req['room_id']}, got {booking.get('roomId')}")
if booking.get("arrival") != req["arrival"] or booking.get("departure") != req["departure"]:
    raise SystemExit("Date mismatch after Beds24 verification")

items = booking.get("invoiceItems") or []
charge_total = sum(
    float(item.get("amount") or 0) * float(item.get("qty") or 1)
    for item in items
    if item.get("type") == "charge"
)
payment_total = sum(
    float(item.get("amount") or 0) * float(item.get("qty") or 1)
    for item in items
    if item.get("type") == "payment"
)

BOOKING_EVIDENCE.write_text(
    json.dumps(
        {
            "verified_at_utc": now(),
            "outcome": outcome,
            "auth_source": "direct_token_credential",
            "api_reference": api_reference,
            "booking_id": booking.get("id"),
            "property_id": booking.get("propertyId"),
            "room_id": booking.get("roomId"),
            "guest_name": req["guest_name"],
            "arrival": booking.get("arrival"),
            "departure": booking.get("departure"),
            "status": booking.get("status"),
            "price": booking.get("price"),
            "invoice_charge_total": charge_total,
            "invoice_payment_total": payment_total,
            "paid_bank_transfer": payment_total >= float(req["amount_paid"]),
            "plaintext_secret_committed": False,
        },
        indent=2,
    )
)

print(json.dumps({"status": "BOOKING_VERIFIED", "booking_id": booking.get("id"), "outcome": outcome}))
