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
EXECUTION_EVIDENCE = EVIDENCE_DIR / "beds24-finalize-status.json"

EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
REFRESH = "".join(os.environ.get("BEDS24_BOOTSTRAP_CREDENTIAL", "").split())
if not REFRESH:
    raise SystemExit("Missing mapped Beds24 refresh credential")


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def request_json(method, path, headers=None, payload=None):
    body = None
    hdrs = {"accept": "application/json"}
    hdrs.update(headers or {})
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        hdrs["content-type"] = "application/json"
    req = urllib.request.Request(f"{API_BASE}{path}", data=body, headers=hdrs, method=method)
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


def safe(obj):
    if isinstance(obj, dict):
        return {k: ("[REDACTED]" if k.lower() in {"token", "refreshtoken", "code"} else v) for k, v in obj.items()}
    return str(obj)[:500]


status, auth = request_json("GET", "/authentication/token", headers={"refreshToken": REFRESH})
TOKEN = auth.get("token") if isinstance(auth, dict) else None
if not (200 <= status < 300 and TOKEN):
    EXECUTION_EVIDENCE.write_text(json.dumps({"verified_at_utc": now(), "status": "AUTH_FAILED", "http_status": status, "response": safe(auth)}, indent=2))
    raise SystemExit(f"Beds24 refresh authentication failed HTTP {status}")

req = json.loads(REQUEST_FILE.read_text())
headers = {"token": TOKEN}


def api(method, path, payload=None):
    st, obj = request_json(method, path, headers=headers, payload=payload)
    if not (200 <= st < 300):
        raise RuntimeError(f"Beds24 {method} {path} failed HTTP {st}: {safe(obj)}")
    return obj


def invoice_totals(booking):
    items = booking.get("invoiceItems") or []
    charge = sum(float(i.get("amount") or 0) * float(i.get("qty") or 1) for i in items if i.get("type") == "charge")
    payment = sum(float(i.get("amount") or 0) * float(i.get("qty") or 1) for i in items if i.get("type") == "payment")
    return charge, payment


exact_q = urllib.parse.urlencode([
    ("roomId", req["room_id"]),
    ("arrival", req["arrival"]),
    ("departure", req["departure"]),
    ("includeInvoiceItems", "true"),
    ("includeGuests", "true"),
])
rows = api("GET", f"/bookings?{exact_q}").get("data") or []

wanted_first = req["first_name"].strip().casefold()
wanted_last = req["last_name"].strip().casefold()
matching = []
for row in rows:
    if row.get("status") == "cancelled":
        continue
    first = str(row.get("firstName") or "").strip().casefold()
    last = str(row.get("lastName") or "").strip().casefold()
    if first == wanted_first and last == wanted_last:
        matching.append(row)

outcome = "reused_existing_exact_match"
if len(matching) > 1:
    raise RuntimeError(f"Duplicate-risk stop: found {len(matching)} exact active bookings for same guest, room and dates")

if matching:
    booking = matching[0]
else:
    payload = [{
        "roomId": req["room_id"],
        "status": "confirmed",
        "arrival": req["arrival"],
        "departure": req["departure"],
        "firstName": req["first_name"],
        "lastName": req["last_name"],
        "country": req.get("country", "Spain"),
        "apiReference": req["request_id"],
        "price": req["total_price"],
        "comment": req["comments"],
        "invoiceItems": [
            {"type": "charge", "description": req["charge_description"], "qty": 1, "amount": req["total_price"]},
            {"type": "payment", "description": req["payment_description"], "qty": 1, "amount": req["amount_paid"]},
        ],
    }]
    created = api("POST", "/bookings", payload)
    if not isinstance(created, list) or not created or not created[0].get("success"):
        raise RuntimeError(f"Unexpected Beds24 create result: {safe(created)}")
    booking_id = created[0].get("id")
    if not booking_id:
        raise RuntimeError(f"Beds24 created booking but returned no booking id: {safe(created)}")
    outcome = "created_new"
    read_q = urllib.parse.urlencode([("id", booking_id), ("includeInvoiceItems", "true"), ("includeGuests", "true")])
    created_rows = api("GET", f"/bookings?{read_q}").get("data") or []
    if len(created_rows) != 1:
        raise RuntimeError(f"Created booking read-back by id {booking_id} returned {len(created_rows)} rows")
    booking = created_rows[0]

booking_id = booking.get("id")
if not booking_id:
    raise RuntimeError("Resolved booking has no Beds24 id")

charge_total, payment_total = invoice_totals(booking)
missing_items = []
if charge_total < float(req["total_price"]):
    missing_items.append({"type": "charge", "description": req["charge_description"], "qty": 1, "amount": float(req["total_price"]) - charge_total})
if payment_total < float(req["amount_paid"]):
    missing_items.append({"type": "payment", "description": req["payment_description"], "qty": 1, "amount": float(req["amount_paid"]) - payment_total})

update = {"id": booking_id, "status": "confirmed", "price": req["total_price"], "apiReference": req["request_id"], "comment": req["comments"]}
if missing_items:
    update["invoiceItems"] = missing_items
    api("POST", "/bookings", [update])
    outcome += "+financials_completed"
else:
    api("POST", "/bookings", [update])

verify_q = urllib.parse.urlencode([("id", booking_id), ("includeInvoiceItems", "true"), ("includeGuests", "true")])
verified_rows = api("GET", f"/bookings?{verify_q}").get("data") or []
if len(verified_rows) != 1:
    raise RuntimeError(f"Final read-back by id {booking_id} returned {len(verified_rows)} rows")
booking = verified_rows[0]
charge_total, payment_total = invoice_totals(booking)

checks = {
    "room": str(booking.get("roomId")) == str(req["room_id"]),
    "arrival": booking.get("arrival") == req["arrival"],
    "departure": booking.get("departure") == req["departure"],
    "status": booking.get("status") == "confirmed",
    "charge": charge_total >= float(req["total_price"]),
    "payment": payment_total >= float(req["amount_paid"]),
}
if not all(checks.values()):
    raise RuntimeError(f"Final Beds24 verification failed: {checks}")

BOOKING_EVIDENCE.write_text(json.dumps({
    "verified_at_utc": now(),
    "outcome": outcome,
    "auth_source": "BEDS24_TOKEN_CREDENTIAL_as_refresh_token",
    "api_reference": req["request_id"],
    "booking_id": booking_id,
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
    "checks": checks,
    "plaintext_secret_committed": False,
}, indent=2))
EXECUTION_EVIDENCE.write_text(json.dumps({"verified_at_utc": now(), "status": "BOOKING_VERIFIED", "booking_id": booking_id, "outcome": outcome}, indent=2))
print(json.dumps({"status": "BOOKING_VERIFIED", "booking_id": booking_id, "outcome": outcome}))
