import datetime as dt
import json
import os
import pathlib
import subprocess
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

API_BASE = "https://beds24.com/api/v2"
ROOT = pathlib.Path(__file__).resolve().parents[1]
REQUEST_FILE = ROOT / "beds24-requests" / "AUMARA-MEDINA-20260718-660.json"
EVIDENCE_DIR = ROOT / "evidence"
VAULT_DIR = ROOT / "vault"
BOOKING_EVIDENCE = EVIDENCE_DIR / "beds24-AUMARA-MEDINA-20260718-660.json"
EXECUTION_EVIDENCE = EVIDENCE_DIR / "beds24-finalize-status.json"
ENCRYPTED_REFRESH = VAULT_DIR / "beds24-refresh-token.enc"
TMP_DIR = pathlib.Path("/tmp/aumara-beds24")

EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
VAULT_DIR.mkdir(parents=True, exist_ok=True)
TMP_DIR.mkdir(parents=True, exist_ok=True)
req = json.loads(REQUEST_FILE.read_text())


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


# Live Beds24 state is managed by Beds24 itself (booking status, Auto Actions,
# API Arrivals and Remotelock). This obsolete V2 recovery script previously
# attempted to create/deduplicate live bookings with the wrong credential type.
# Keep it hard-disabled so a GitHub retry cannot create, cancel or modify a stay.
EXECUTION_EVIDENCE.write_text(json.dumps({
    "verified_at_utc": now(),
    "status": "DISABLED_REDUNDANT_V2_BRIDGE",
    "request_id": req.get("request_id"),
    "reason": "Use native Beds24 booking and guest-action flow; external live writes are disabled.",
    "live_booking_mutations": False,
}, indent=2))
print(json.dumps({
    "status": "DISABLED_REDUNDANT_V2_BRIDGE",
    "request_id": req.get("request_id"),
    "live_booking_mutations": False,
}))
raise SystemExit(0)


def normalize(value):
    value = (value or "").strip().strip('"').strip("'")
    return "".join(
        ch for ch in value
        if not ch.isspace() and unicodedata.category(ch) not in {"Cc", "Cf"}
    )


credential = normalize(os.environ.get("BEDS24_BOOTSTRAP_CREDENTIAL", ""))
if not credential:
    raise SystemExit("Missing BEDS24_TOKEN_CREDENTIAL GitHub secret")


def request_json(method, path, headers=None, payload=None):
    body = None
    hdrs = {"accept": "application/json"}
    hdrs.update(headers or {})
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        hdrs["content-type"] = "application/json"
    elif method == "POST":
        body = b""
    request = urllib.request.Request(
        f"{API_BASE}{path}",
        data=body,
        headers=hdrs,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            raw = response.read().decode("utf-8", "replace")
            try:
                parsed = json.loads(raw) if raw else {}
            except Exception:
                parsed = {"raw": raw[:500]}
            return response.status, parsed
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
            key: (
                "[REDACTED]"
                if key.lower() in {"token", "refreshtoken", "code"}
                else safe(value)
            )
            for key, value in obj.items()
        }
    if isinstance(obj, list):
        return [safe(item) for item in obj[:20]]
    if isinstance(obj, str):
        return obj[:500]
    return obj


def decrypt_vault(passphrase):
    if not ENCRYPTED_REFRESH.exists() or ENCRYPTED_REFRESH.stat().st_size == 0:
        return None
    out = TMP_DIR / "refresh.txt"
    out.unlink(missing_ok=True)
    env = os.environ.copy()
    env["BEDS24_VAULT_PASSPHRASE"] = passphrase
    proc = subprocess.run(
        [
            "openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2",
            "-iter", "200000", "-pass", "env:BEDS24_VAULT_PASSPHRASE",
            "-in", str(ENCRYPTED_REFRESH), "-out", str(out),
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0 or not out.exists():
        return None
    value = normalize(out.read_text(errors="replace"))
    out.unlink(missing_ok=True)
    return value or None


def encrypt_vault(refresh_token, passphrase):
    src = TMP_DIR / "refresh-to-encrypt.txt"
    src.write_text(refresh_token)
    env = os.environ.copy()
    env["BEDS24_VAULT_PASSPHRASE"] = passphrase
    subprocess.run(
        [
            "openssl", "enc", "-aes-256-cbc", "-salt", "-pbkdf2",
            "-iter", "200000", "-pass", "env:BEDS24_VAULT_PASSPHRASE",
            "-in", str(src), "-out", str(ENCRYPTED_REFRESH),
        ],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    src.unlink(missing_ok=True)


def token_from_refresh(refresh_token):
    status, obj = request_json(
        "GET",
        "/authentication/token",
        headers={"refreshToken": refresh_token},
    )
    token = obj.get("token") if isinstance(obj, dict) else None
    return token if 200 <= status < 300 else None, status, obj


auth_attempts = []
refresh_token = decrypt_vault(credential)
access_token = None
auth_source = None

if refresh_token:
    access_token, status, obj = token_from_refresh(refresh_token)
    auth_attempts.append({
        "mode": "encrypted_refresh",
        "status": status,
        "response": safe(obj) if not access_token else {"success": True},
    })
    if access_token:
        auth_source = "encrypted_refresh"

if not access_token:
    access_token, status, obj = token_from_refresh(credential)
    auth_attempts.append({
        "mode": "secret_as_refresh",
        "status": status,
        "response": safe(obj) if not access_token else {"success": True},
    })
    if access_token:
        refresh_token = credential
        auth_source = "secret_as_refresh"

if not access_token:
    status, setup = request_json(
        "GET",
        "/authentication/setup",
        headers={"code": credential, "deviceName": "AUMARA-Control-Tower"},
    )
    setup_refresh = setup.get("refreshToken") if isinstance(setup, dict) else None
    setup_token = setup.get("token") if isinstance(setup, dict) else None
    auth_attempts.append({
        "mode": "secret_as_invite_code",
        "status": status,
        "response": safe(setup),
    })
    if 200 <= status < 300 and setup_refresh:
        refresh_token = normalize(setup_refresh)
        access_token = setup_token
        auth_source = "secret_as_invite_code"
        if not access_token:
            access_token, status2, obj2 = token_from_refresh(refresh_token)
            auth_attempts.append({
                "mode": "new_refresh_exchange",
                "status": status2,
                "response": safe(obj2) if not access_token else {"success": True},
            })

if not access_token:
    EXECUTION_EVIDENCE.write_text(json.dumps({
        "verified_at_utc": now(),
        "status": "AUTH_FAILED",
        "attempts": auth_attempts,
        "plaintext_secret_committed": False,
    }, indent=2))
    raise SystemExit("Beds24 authentication failed")

if refresh_token:
    encrypt_vault(refresh_token, credential)

headers = {"token": access_token}


def api(method, path, payload=None):
    status, obj = request_json(method, path, headers=headers, payload=payload)
    if not (200 <= status < 300):
        raise RuntimeError(f"Beds24 {method} {path} failed HTTP {status}: {safe(obj)}")
    return obj


def invoice_totals(booking):
    items = booking.get("invoiceItems") or []
    charge = sum(
        abs(float(item.get("amount") or 0) * float(item.get("qty") or 1))
        for item in items if item.get("type") == "charge"
    )
    payment = sum(
        abs(float(item.get("amount") or 0) * float(item.get("qty") or 1))
        for item in items if item.get("type") == "payment"
    )
    return charge, payment


def find_created_booking_id(response_item):
    if not isinstance(response_item, dict):
        return None
    for key in ("bookingId", "id"):
        value = response_item.get(key)
        if isinstance(value, int) or (isinstance(value, str) and value.isdigit()):
            return int(value)
    def walk(value):
        if isinstance(value, dict):
            for key in ("bookingId", "id"):
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
    return walk(response_item.get("new"))


exact_q = urllib.parse.urlencode([
    ("roomId", req["room_id"]),
    ("arrival", req["arrival"]),
    ("departure", req["departure"]),
    ("includeInvoiceItems", "true"),
    ("includeGuests", "true"),
])

wanted_first = req["first_name"].strip().casefold()
wanted_last = req["last_name"].strip().casefold()
wanted_email = str(req.get("email") or "").strip().casefold()


def exact_matches(rows):
    matches = []
    for row in rows:
        if row.get("status") == "cancelled":
            continue
        first = str(row.get("firstName") or "").strip().casefold()
        last = str(row.get("lastName") or "").strip().casefold()
        email = str(row.get("email") or "").strip().casefold()
        if (first == wanted_first and last == wanted_last) or (wanted_email and email == wanted_email):
            matches.append(row)
    return matches


def score_booking(booking):
    charge, payment = invoice_totals(booking)
    score = 0
    if booking.get("apiReference") == req["request_id"]:
        score += 100
    if str(booking.get("email") or "").strip().casefold() == wanted_email:
        score += 50
    if (
        str(booking.get("firstName") or "").strip().casefold() == wanted_first
        and str(booking.get("lastName") or "").strip().casefold() == wanted_last
    ):
        score += 30
    if booking.get("status") == "confirmed":
        score += 10
    if charge >= float(req["total_price"]):
        score += 5
    if payment >= float(req["amount_paid"]):
        score += 5
    return score


rows = api("GET", f"/bookings?{exact_q}").get("data") or []
matching = exact_matches(rows)
outcome = "reused_existing_exact_match"
duplicate_ids_cancelled = []

if not matching:
    payload = [{
        "roomId": req["room_id"],
        "status": "confirmed",
        "arrival": req["arrival"],
        "departure": req["departure"],
        "numAdult": req.get("adults", 1),
        "firstName": req["first_name"],
        "lastName": req["last_name"],
        "email": req.get("email"),
        "mobile": req.get("phone"),
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
    matching = []
    for _ in range(6):
        if booking_id:
            read_q = urllib.parse.urlencode([
                ("id", booking_id),
                ("includeInvoiceItems", "true"),
                ("includeGuests", "true"),
            ])
            matching = api("GET", f"/bookings?{read_q}").get("data") or []
        else:
            matching = exact_matches(api("GET", f"/bookings?{exact_q}").get("data") or [])
        if len(matching) == 1:
            break
        time.sleep(2)
    if len(matching) != 1:
        raise RuntimeError(f"Created booking read-back returned {len(matching)} rows")

if len(matching) > 1:
    ranked = sorted(
        matching,
        key=lambda b: (-score_booking(b), int(b.get("id") or 9999999999)),
    )
    booking = ranked[0]
    canonical_id = booking.get("id")
    for duplicate in ranked[1:]:
        duplicate_id = duplicate.get("id")
        if not duplicate_id:
            continue
        removable_items = []
        for item in duplicate.get("invoiceItems") or []:
            item_id = item.get("id")
            description = str(item.get("description") or "")
            if item_id and description in {req["charge_description"], req["payment_description"]}:
                removable_items.append({"id": item_id})
        duplicate_update = {
            "id": duplicate_id,
            "status": "cancelled",
            "comment": (
                f"Duplicate created during API recovery; canonical Beds24 booking {canonical_id}. "
                f"Cancelled automatically {now()}."
            ),
        }
        if removable_items:
            duplicate_update["invoiceItems"] = removable_items
        api("POST", "/bookings", [duplicate_update])
        duplicate_ids_cancelled.append(duplicate_id)
    outcome = "deduplicated_existing_records"
else:
    booking = matching[0]

booking_id = booking.get("id")
if not booking_id:
    raise RuntimeError("Canonical booking has no Beds24 id")

read_q = urllib.parse.urlencode([
    ("id", booking_id),
    ("includeInvoiceItems", "true"),
    ("includeGuests", "true"),
])
booking_rows = api("GET", f"/bookings?{read_q}").get("data") or []
if len(booking_rows) != 1:
    raise RuntimeError(f"Canonical read-back returned {len(booking_rows)} rows")
booking = booking_rows[0]

charge_total, payment_total = invoice_totals(booking)
missing_items = []
if charge_total < float(req["total_price"]):
    missing_items.append({
        "type": "charge",
        "description": req["charge_description"],
        "qty": 1,
        "amount": float(req["total_price"]) - charge_total,
    })
if payment_total < float(req["amount_paid"]):
    missing_items.append({
        "type": "payment",
        "description": req["payment_description"],
        "qty": 1,
        "amount": float(req["amount_paid"]) - payment_total,
    })

canonical_update = {
    "id": booking_id,
    "status": "confirmed",
    "numAdult": req.get("adults", 1),
    "firstName": req["first_name"],
    "lastName": req["last_name"],
    "email": req.get("email"),
    "mobile": req.get("phone"),
    "country": req.get("country", "Spain"),
    "price": req["total_price"],
    "apiReference": req["request_id"],
    "comment": req["comments"],
}
if missing_items:
    canonical_update["invoiceItems"] = missing_items
    outcome += "+financials_completed"
api("POST", "/bookings", [canonical_update])

verified_rows = api("GET", f"/bookings?{read_q}").get("data") or []
if len(verified_rows) != 1:
    raise RuntimeError(f"Final canonical read-back returned {len(verified_rows)} rows")
booking = verified_rows[0]
charge_total, payment_total = invoice_totals(booking)

checks = {
    "room": str(booking.get("roomId")) == str(req["room_id"]),
    "arrival": booking.get("arrival") == req["arrival"],
    "departure": booking.get("departure") == req["departure"],
    "status": booking.get("status") == "confirmed",
    "email": str(booking.get("email") or "").strip().casefold() == wanted_email,
    "adults": int(booking.get("numAdult") or 0) == int(req.get("adults", 1)),
    "charge": charge_total >= float(req["total_price"]),
    "payment": payment_total >= float(req["amount_paid"]),
}
if not all(checks.values()):
    raise RuntimeError(f"Final Beds24 verification failed: {checks}")

for duplicate_id in duplicate_ids_cancelled:
    q = urllib.parse.urlencode([("id", duplicate_id)])
    rows = api("GET", f"/bookings?{q}").get("data") or []
    if len(rows) != 1 or rows[0].get("status") != "cancelled":
        raise RuntimeError(f"Duplicate {duplicate_id} cancellation verification failed")

BOOKING_EVIDENCE.write_text(json.dumps({
    "verified_at_utc": now(),
    "outcome": outcome,
    "api_base": API_BASE,
    "auth_source": auth_source,
    "api_reference": req["request_id"],
    "booking_id": booking_id,
    "duplicate_booking_ids_cancelled": duplicate_ids_cancelled,
    "property_id": booking.get("propertyId"),
    "room_id": booking.get("roomId"),
    "guest_name": req["guest_name"],
    "guest_email": booking.get("email"),
    "guest_phone": booking.get("mobile"),
    "adults": booking.get("numAdult"),
    "arrival": booking.get("arrival"),
    "departure": booking.get("departure"),
    "status": booking.get("status"),
    "price": booking.get("price"),
    "invoice_charge_total": charge_total,
    "invoice_payment_total": payment_total,
    "paid_bank_transfer": payment_total >= float(req["amount_paid"]),
    "checks": checks,
    "encrypted_refresh_vault": bool(ENCRYPTED_REFRESH.exists() and ENCRYPTED_REFRESH.stat().st_size),
    "plaintext_secret_committed": False,
}, indent=2))

EXECUTION_EVIDENCE.write_text(json.dumps({
    "verified_at_utc": now(),
    "status": "BOOKING_VERIFIED",
    "booking_id": booking_id,
    "duplicate_booking_ids_cancelled": duplicate_ids_cancelled,
    "outcome": outcome,
    "auth_source": auth_source,
}, indent=2))

print(json.dumps({
    "status": "BOOKING_VERIFIED",
    "booking_id": booking_id,
    "duplicate_booking_ids_cancelled": duplicate_ids_cancelled,
    "outcome": outcome,
    "auth_source": auth_source,
}))
