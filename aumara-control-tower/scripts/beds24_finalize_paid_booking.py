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

API_BASE_CANDIDATES = [
    "https://beds24.com/api/v2",
    "https://api.beds24.com/v2",
]
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


def normalize(value):
    value = (value or "").strip().strip('"').strip("'")
    return "".join(
        ch for ch in value
        if not ch.isspace() and unicodedata.category(ch) not in {"Cc", "Cf"}
    )


credential_candidates = []
for label, env_name in (
    ("token_secret", "BEDS24_BOOTSTRAP_CREDENTIAL"),
    ("bootstrap_fallback_secret", "BEDS24_FALLBACK_CREDENTIAL"),
):
    value = normalize(os.environ.get(env_name, ""))
    if value and all(value != existing[1] for existing in credential_candidates):
        credential_candidates.append((label, value))

if not credential_candidates:
    raise SystemExit("No Beds24 credential anchors are available")


def request_json(base, method, path, headers=None, payload=None):
    body = None
    hdrs = {"accept": "application/json"}
    hdrs.update(headers or {})
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        hdrs["content-type"] = "application/json"
    elif method == "POST":
        body = b""
    request = urllib.request.Request(
        f"{base}{path}",
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
    except Exception as exc:
        return 0, {
            "network_error": type(exc).__name__,
            "message": str(exc)[:300],
        }


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
        return [safe(item) for item in obj[:10]]
    if isinstance(obj, str):
        return obj[:500]
    return obj


def decrypt_vault(passphrase, label):
    if not ENCRYPTED_REFRESH.exists() or ENCRYPTED_REFRESH.stat().st_size == 0:
        return None, "missing"
    out = TMP_DIR / f"refresh-{label}.txt"
    out.unlink(missing_ok=True)
    env = os.environ.copy()
    env["BEDS24_VAULT_PASSPHRASE"] = passphrase
    proc = subprocess.run(
        [
            "openssl",
            "enc",
            "-d",
            "-aes-256-cbc",
            "-pbkdf2",
            "-iter",
            "200000",
            "-pass",
            "env:BEDS24_VAULT_PASSPHRASE",
            "-in",
            str(ENCRYPTED_REFRESH),
            "-out",
            str(out),
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0 or not out.exists():
        return None, "decrypt_failed"
    value = normalize(out.read_text(errors="replace"))
    out.unlink(missing_ok=True)
    return (value or None), ("decrypted" if value else "empty")


def encrypt_vault(refresh_token, passphrase):
    src = TMP_DIR / "refresh-to-encrypt.txt"
    src.write_text(refresh_token)
    env = os.environ.copy()
    env["BEDS24_VAULT_PASSPHRASE"] = passphrase
    subprocess.run(
        [
            "openssl",
            "enc",
            "-aes-256-cbc",
            "-salt",
            "-pbkdf2",
            "-iter",
            "200000",
            "-pass",
            "env:BEDS24_VAULT_PASSPHRASE",
            "-in",
            str(src),
            "-out",
            str(ENCRYPTED_REFRESH),
        ],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    src.unlink(missing_ok=True)


stable_vault_passphrase = next(
    (
        value
        for label, value in credential_candidates
        if label == "bootstrap_fallback_secret"
    ),
    credential_candidates[0][1],
)

vault_attempts = []
refresh_candidates = []
for label, passphrase in credential_candidates:
    refresh, result = decrypt_vault(passphrase, label)
    vault_attempts.append({
        "passphrase_anchor": label,
        "result": result,
        "refresh_recovered": bool(refresh),
    })
    if refresh and all(refresh != existing[1] for existing in refresh_candidates):
        refresh_candidates.append((f"encrypted_vault:{label}", refresh))

exact_q = urllib.parse.urlencode([
    ("roomId", req["room_id"]),
    ("arrival", req["arrival"]),
    ("departure", req["departure"]),
    ("includeInvoiceItems", "true"),
    ("includeGuests", "true"),
])

auth_attempts = []
TOKEN = None
API_BASE = None
auth_source = None
resolved_refresh = None

for base in API_BASE_CANDIDATES:
    for refresh_label, refresh_value in refresh_candidates:
        status, auth = request_json(
            base,
            "GET",
            "/authentication/token",
            headers={"refreshToken": refresh_value},
        )
        candidate = auth.get("token") if isinstance(auth, dict) else None
        auth_attempts.append({
            "api_base": base,
            "credential": refresh_label,
            "mode": "refresh_token",
            "status": status,
            "response": safe(auth) if not (200 <= status < 300) else {"success": True},
        })
        if 200 <= status < 300 and candidate:
            TOKEN = candidate
            API_BASE = base
            auth_source = refresh_label
            resolved_refresh = refresh_value
            break
    if TOKEN:
        break

    for credential_label, credential in credential_candidates:
        status, auth = request_json(
            base,
            "GET",
            "/authentication/token",
            headers={"refreshToken": credential},
        )
        candidate = auth.get("token") if isinstance(auth, dict) else None
        auth_attempts.append({
            "api_base": base,
            "credential": credential_label,
            "mode": "refresh_token",
            "status": status,
            "response": safe(auth) if not (200 <= status < 300) else {"success": True},
        })
        if 200 <= status < 300 and candidate:
            TOKEN = candidate
            API_BASE = base
            auth_source = f"{credential_label}:refresh_token"
            resolved_refresh = credential
            break

        status, direct_probe = request_json(
            base,
            "GET",
            f"/bookings?{exact_q}",
            headers={"token": credential},
        )
        auth_attempts.append({
            "api_base": base,
            "credential": credential_label,
            "mode": "direct_token",
            "status": status,
            "response": safe(direct_probe) if not (200 <= status < 300) else {"success": True},
        })
        if 200 <= status < 300:
            TOKEN = credential
            API_BASE = base
            auth_source = f"{credential_label}:direct_token"
            break

        status, setup = request_json(
            base,
            "GET",
            "/authentication/setup",
            headers={
                "code": credential,
                "deviceName": "AUMARA-Control-Tower",
            },
        )
        setup_refresh = setup.get("refreshToken") if isinstance(setup, dict) else None
        setup_token = setup.get("token") if isinstance(setup, dict) else None
        auth_attempts.append({
            "api_base": base,
            "credential": credential_label,
            "mode": "invite_code",
            "status": status,
            "response": safe(setup),
        })
        if 200 <= status < 300 and setup_refresh:
            resolved_refresh = normalize(setup_refresh)
            if setup_token:
                TOKEN = setup_token
            else:
                token_status, token_obj = request_json(
                    base,
                    "GET",
                    "/authentication/token",
                    headers={"refreshToken": resolved_refresh},
                )
                TOKEN = token_obj.get("token") if isinstance(token_obj, dict) else None
                auth_attempts.append({
                    "api_base": base,
                    "credential": credential_label,
                    "mode": "invite_refresh_exchange",
                    "status": token_status,
                    "response": safe(token_obj) if not (200 <= token_status < 300) else {"success": True},
                })
            if TOKEN:
                API_BASE = base
                auth_source = f"{credential_label}:invite_code"
                break
    if TOKEN:
        break

if not TOKEN or not API_BASE:
    EXECUTION_EVIDENCE.write_text(json.dumps({
        "verified_at_utc": now(),
        "status": "AUTH_FAILED",
        "api_bases_checked": API_BASE_CANDIDATES,
        "vault_attempts": vault_attempts,
        "attempts": auth_attempts,
        "credential_anchors_checked": [label for label, _ in credential_candidates],
        "plaintext_secret_committed": False,
    }, indent=2))
    raise SystemExit(
        "Beds24 rejected the encrypted refresh vault and every current credential anchor"
    )

if resolved_refresh:
    encrypt_vault(resolved_refresh, stable_vault_passphrase)

headers = {"token": TOKEN}


def api(method, path, payload=None):
    status, obj = request_json(
        API_BASE,
        method,
        path,
        headers=headers,
        payload=payload,
    )
    if not (200 <= status < 300):
        raise RuntimeError(
            f"Beds24 {method} {path} failed HTTP {status}: {safe(obj)}"
        )
    return obj


def invoice_totals(booking):
    items = booking.get("invoiceItems") or []
    charge = sum(
        abs(float(item.get("amount") or 0) * float(item.get("qty") or 1))
        for item in items
        if item.get("type") == "charge"
    )
    payment = sum(
        abs(float(item.get("amount") or 0) * float(item.get("qty") or 1))
        for item in items
        if item.get("type") == "payment"
    )
    return charge, payment


def find_created_booking_id(response_item):
    if not isinstance(response_item, dict):
        return None

    for key in ("bookingId", "id"):
        candidate = response_item.get(key)
        if isinstance(candidate, int) or (
            isinstance(candidate, str) and candidate.isdigit()
        ):
            return int(candidate)

    new_part = response_item.get("new")

    def walk(value):
        if isinstance(value, dict):
            for key in ("bookingId", "id"):
                candidate = value.get(key)
                if isinstance(candidate, int) or (
                    isinstance(candidate, str) and candidate.isdigit()
                ):
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
        same_name = first == wanted_first and last == wanted_last
        same_email = bool(wanted_email and email == wanted_email)
        if same_name or same_email:
            matches.append(row)
    return matches


rows = api("GET", f"/bookings?{exact_q}").get("data") or []
matching = exact_matches(rows)
outcome = "reused_existing_exact_match"

if len(matching) > 1:
    raise RuntimeError(
        f"Duplicate-risk stop: found {len(matching)} exact active bookings "
        "for the same room and dates"
    )

if matching:
    booking = matching[0]
else:
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
    }]
    created = api("POST", "/bookings", payload)
    if not isinstance(created, list) or not created or not created[0].get("success"):
        raise RuntimeError(f"Unexpected Beds24 create result: {safe(created)}")

    booking_id = find_created_booking_id(created[0])
    outcome = "created_new"
    created_rows = []

    for _ in range(6):
        if booking_id:
            read_q = urllib.parse.urlencode([
                ("id", booking_id),
                ("includeInvoiceItems", "true"),
                ("includeGuests", "true"),
            ])
            created_rows = api("GET", f"/bookings?{read_q}").get("data") or []
        else:
            created_rows = exact_matches(
                api("GET", f"/bookings?{exact_q}").get("data") or []
            )
        if len(created_rows) == 1:
            break
        time.sleep(2)

    if len(created_rows) != 1:
        raise RuntimeError(
            f"Created booking read-back returned {len(created_rows)} exact rows; "
            f"response={safe(created)}"
        )
    booking = created_rows[0]

booking_id = booking.get("id")
if not booking_id:
    raise RuntimeError("Resolved booking has no Beds24 id")

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

update = {
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
    update["invoiceItems"] = missing_items
    outcome += "+financials_completed"
api("POST", "/bookings", [update])

verify_q = urllib.parse.urlencode([
    ("id", booking_id),
    ("includeInvoiceItems", "true"),
    ("includeGuests", "true"),
])
verified_rows = api("GET", f"/bookings?{verify_q}").get("data") or []
if len(verified_rows) != 1:
    raise RuntimeError(
        f"Final read-back by id {booking_id} returned {len(verified_rows)} rows"
    )

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

BOOKING_EVIDENCE.write_text(json.dumps({
    "verified_at_utc": now(),
    "outcome": outcome,
    "api_base": API_BASE,
    "auth_source": auth_source,
    "api_reference": req["request_id"],
    "booking_id": booking_id,
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
    "encrypted_refresh_vault": bool(
        ENCRYPTED_REFRESH.exists() and ENCRYPTED_REFRESH.stat().st_size
    ),
    "plaintext_secret_committed": False,
}, indent=2))

EXECUTION_EVIDENCE.write_text(json.dumps({
    "verified_at_utc": now(),
    "status": "BOOKING_VERIFIED",
    "api_base": API_BASE,
    "booking_id": booking_id,
    "outcome": outcome,
    "auth_source": auth_source,
}, indent=2))

print(json.dumps({
    "status": "BOOKING_VERIFIED",
    "api_base": API_BASE,
    "booking_id": booking_id,
    "outcome": outcome,
    "auth_source": auth_source,
}))
