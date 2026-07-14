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
CREDENTIAL = "".join(os.environ.get("BEDS24_BOOTSTRAP_CREDENTIAL", "").split())
if not CREDENTIAL:
    raise SystemExit("Missing mapped Beds24 credential")

req = json.loads(REQUEST_FILE.read_text())


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def request_json(method, path, headers=None, payload=None):
    body = None
    hdrs = {"accept": "application/json"}
    hdrs.update(headers or {})
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        hdrs["content-type"] = "application/json"
    elif method == "POST":
        body = b""
    request = urllib.request.Request(f"{API_BASE}{path}", data=body, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
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
        return {
            key: ("[REDACTED]" if key.lower() in {"token", "refreshtoken", "code"} else value)
            for key, value in obj.items()
        }
    if isinstance(obj, list):
        return [safe(item) for item in obj[:10]]
    return str(obj)[:500]


exact_q = urllib.parse.urlencode([
    ("roomId", req["room_id"]),
    ("arrival", req["arrival"]),
    ("departure", req["departure"]),
    ("includeInvoiceItems", "true"),
    ("includeGuests", "true"),
])

auth_attempts = []
TOKEN = None
auth_source = None

# 1. The stored value may already be a normal API token.
status, direct_probe = request_json("GET", f"/bookings?{exact_q}", headers={"token": CREDENTIAL})
auth_attempts.append({"mode": "direct_token", "status": status})
if 200 <= status < 300:
    TOKEN = CREDENTIAL
    auth_source = "direct_token"

# 2. The stored value may be a refresh token.
if not TOKEN:
    status, auth = request_json("GET", "/authentication/token", headers={"refreshToken": CREDENTIAL})
    candidate = auth.get("token") if isinstance(auth, dict) else None
    auth_attempts.append({"mode": "refresh_token", "status": status})
    if 200 <= status < 300 and candidate:
        TOKEN = candidate
        auth_source = "refresh_token"

# 3. The stored value may be a one-time invite code. Exchange and use the returned token immediately.
if not TOKEN:
    status, setup = request_json(
        "GET",
        "/authentication/setup",
        headers={"code": CREDENTIAL, "deviceName": "AUMARA-Control-Tower"},
    )
    candidate = setup.get("token") if isinstance(setup, dict) else None
    auth_attempts.append({"mode": "invite_code", "status": status, "response": safe(setup)})
    if 200 <= status < 300 and candidate:
        TOKEN = candidate
        auth_source = "invite_code"

if not TOKEN:
    EXECUTION_EVIDENCE.write_text(json.dumps({
        "verified_at_utc": now(),
        "status": "AUTH_FAILED",
        "attempts": auth_attempts,
        "secret_present": True,
        "plaintext_secret_committed": False,
    }, indent=2))
    raise SystemExit("Beds24 credential was rejected as direct token, refresh token and invite code")

headers = {"token": TOKEN}


def api(method, path, payload=None):
    status, obj = request_json(method, path, headers=headers, payload=payload)
    if not (200 <= status < 300):
        raise RuntimeError(f"Beds24 {method} {path} failed HTTP {status}: {safe(obj)}")
    return obj


def invoice_totals(booking):
    items = booking.get("invoiceItems") or []
    charge = sum(float(item.get("amount") or 0) * float(item.get("qty") or 1) for item in items if item.get("type") == "charge")
    payment = sum(float(item.get("amount") or 0) * float(item.get("qty") or 1) for item in items if item.get("type") == "payment")
    return charge, payment


def find_created_booking_id(response_item):
    new_part = response_item.get("new") if isinstance(response_item, dict) else None

    def walk(value):
        if isinstance(value, dict):
            for key in ("id", "bookingId"):
                candidate = value.get(key)
                if isinstance(candidate, int) or (isinstance(candidate, str) and candidate.isdigit()):
                    return int(candidate)
            for child in value.values():
                found = walk(child)
                if found:
                    return found
        elif isinstance(value, list):
            for child in value:
                found = walk(child)
                if found:
                    return found
        return None

    return walk(new_part)


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
    booking_id = find_created_booking_id(created[0])
    outcome = "created_new"

    if booking_id:
        read_q = urllib.parse.urlencode([("id", booking_id), ("includeInvoiceItems", "true"), ("includeGuests", "true")])
        created_rows = api("GET", f"/bookings?{read_q}").get("data") or []
    else:
        created_rows = api("GET", f"/bookings?{exact_q}").get("data") or []
        created_rows = [
            row for row in created_rows
            if row.get("status") != "cancelled"
            and str(row.get("firstName") or "").strip().casefold() == wanted_first
            and str(row.get("lastName") or "").strip().casefold() == wanted_last
        ]

    if len(created_rows) != 1:
        raise RuntimeError(f"Created booking read-back returned {len(created_rows)} exact rows; response={safe(created)}")
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

update = {
    "id": booking_id,
    "status": "confirmed",
    "price": req["total_price"],
    "apiReference": req["request_id"],
    "comment": req["comments"],
}
if missing_items:
    update["invoiceItems"] = missing_items
    outcome += "+financials_completed"
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
    "auth_source": auth_source,
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
EXECUTION_EVIDENCE.write_text(json.dumps({
    "verified_at_utc": now(),
    "status": "BOOKING_VERIFIED",
    "booking_id": booking_id,
    "outcome": outcome,
    "auth_source": auth_source,
}, indent=2))
print(json.dumps({"status": "BOOKING_VERIFIED", "booking_id": booking_id, "outcome": outcome, "auth_source": auth_source}))
