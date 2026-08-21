import datetime as dt
import json
import os
import pathlib
import subprocess
import urllib.error
import urllib.parse
import urllib.request

API_BASE = "https://beds24.com/api/v2"
ROOT = pathlib.Path(__file__).resolve().parents[1]
REQUEST_FILE = ROOT / "beds24-requests" / "AUMARA-MEDINA-20260718-660.json"
EVIDENCE_DIR = ROOT / "evidence"
VAULT_DIR = ROOT / "vault"
BOOKING_EVIDENCE = EVIDENCE_DIR / "beds24-AUMARA-MEDINA-20260718-660.json"
AUTH_EVIDENCE = EVIDENCE_DIR / "beds24-auth-bootstrap-status.json"
ENCRYPTED_REFRESH = VAULT_DIR / "beds24-refresh-token.enc"
TMP = pathlib.Path("/tmp/aumara-beds24")

EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
VAULT_DIR.mkdir(parents=True, exist_ok=True)
TMP.mkdir(parents=True, exist_ok=True)

BOOTSTRAP = "".join(os.environ.get("BEDS24_BOOTSTRAP_CREDENTIAL", "").split())
if not BOOTSTRAP:
    raise SystemExit("Missing BEDS24_BOOTSTRAP_CREDENTIAL")


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def redact(text: str) -> str:
    return text.replace(BOOTSTRAP, "[REDACTED]")[:1500]


def request_json(method: str, url: str, headers=None, payload=None):
    body = None
    request_headers = dict(headers or {})
    request_headers.setdefault("accept", "application/json")
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        request_headers["content-type"] = "application/json"
    elif method == "POST":
        body = b""
    req = urllib.request.Request(url, data=body, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            raw = response.read().decode("utf-8", "replace")
            try:
                parsed = json.loads(raw) if raw else {}
            except Exception:
                parsed = {"raw": raw}
            return response.status, parsed
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            parsed = json.loads(raw) if raw else {}
        except Exception:
            parsed = {"raw": raw}
        return exc.code, parsed


def safe_public_response(obj):
    if isinstance(obj, dict):
        out = {}
        for key, value in obj.items():
            if key.lower() in {"token", "refreshtoken", "code"}:
                out[key] = "[REDACTED]"
            elif isinstance(value, str):
                out[key] = redact(value)
            else:
                out[key] = value
        return out
    return redact(str(obj))


def decrypt_refresh():
    if not ENCRYPTED_REFRESH.exists():
        return None
    out = TMP / "refresh.txt"
    env = os.environ.copy()
    env["BEDS24_VAULT_PASSPHRASE"] = BOOTSTRAP
    proc = subprocess.run(
        [
            "openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2", "-iter", "200000",
            "-pass", "env:BEDS24_VAULT_PASSPHRASE",
            "-in", str(ENCRYPTED_REFRESH), "-out", str(out),
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0 or not out.exists():
        return None
    value = out.read_text().strip()
    return value or None


def encrypt_refresh(refresh: str):
    src = TMP / "refresh.txt"
    src.write_text(refresh)
    env = os.environ.copy()
    env["BEDS24_VAULT_PASSPHRASE"] = BOOTSTRAP
    subprocess.run(
        [
            "openssl", "enc", "-aes-256-cbc", "-salt", "-pbkdf2", "-iter", "200000",
            "-pass", "env:BEDS24_VAULT_PASSPHRASE",
            "-in", str(src), "-out", str(ENCRYPTED_REFRESH),
        ],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    src.unlink(missing_ok=True)


def get_token_from_refresh(refresh: str):
    status, obj = request_json(
        "GET",
        f"{API_BASE}/authentication/token",
        headers={"refreshToken": refresh},
    )
    token = obj.get("token") if isinstance(obj, dict) else None
    if 200 <= status < 300 and token:
        return token, status
    return None, status


auth_attempts = []
refresh = decrypt_refresh()
auth_source = "encrypted_vault" if refresh else None
access_token = None

if refresh:
    access_token, status = get_token_from_refresh(refresh)
    auth_attempts.append({"mode": "encrypted_refresh", "method": "GET", "status": status})
    if not access_token:
        refresh = None
        auth_source = None

if not refresh:
    token, status = get_token_from_refresh(BOOTSTRAP)
    auth_attempts.append({"mode": "bootstrap_as_refresh", "method": "GET", "status": status})
    if token:
        refresh = BOOTSTRAP
        access_token = token
        auth_source = "bootstrap_refresh_token"
    else:
        setup_success = None
        for method in ("GET", "POST"):
            status, obj = request_json(
                method,
                f"{API_BASE}/authentication/setup",
                headers={"code": BOOTSTRAP, "deviceName": "AUMARA-Control-Tower"},
            )
            auth_attempts.append(
                {
                    "mode": "bootstrap_as_invite_code",
                    "method": method,
                    "status": status,
                    "response": safe_public_response(obj),
                }
            )
            candidate_refresh = obj.get("refreshToken") if isinstance(obj, dict) else None
            candidate_token = obj.get("token") if isinstance(obj, dict) else None
            if 200 <= status < 300 and candidate_refresh:
                refresh = candidate_refresh
                access_token = candidate_token
                auth_source = f"bootstrap_invite_code_{method.lower()}"
                setup_success = True
                break
        if not setup_success:
            AUTH_EVIDENCE.write_text(
                json.dumps(
                    {
                        "verified_at_utc": now(),
                        "status": "AUTH_FAILED",
                        "api_base": API_BASE,
                        "attempts": auth_attempts,
                        "secret_present": True,
                        "plaintext_secret_committed": False,
                    },
                    indent=2,
                )
            )
            raise SystemExit("Beds24 rejected the bootstrap credential; see sanitized auth evidence")

if not access_token:
    access_token, status = get_token_from_refresh(refresh)
    auth_attempts.append({"mode": "resolved_refresh", "method": "GET", "status": status})
    if not access_token:
        AUTH_EVIDENCE.write_text(
            json.dumps(
                {
                    "verified_at_utc": now(),
                    "status": "REFRESH_TOKEN_FAILED",
                    "api_base": API_BASE,
                    "auth_source": auth_source,
                    "attempts": auth_attempts,
                    "plaintext_secret_committed": False,
                },
                indent=2,
            )
        )
        raise SystemExit("Resolved Beds24 refresh token could not generate an access token")

encrypt_refresh(refresh)
AUTH_EVIDENCE.write_text(
    json.dumps(
        {
            "verified_at_utc": now(),
            "status": "AUTH_OK",
            "api_base": API_BASE,
            "auth_source": auth_source,
            "attempts": auth_attempts,
            "encrypted_refresh_vault": True,
            "plaintext_secret_committed": False,
        },
        indent=2,
    )
)


def api_call(method: str, path: str, payload=None):
    status, obj = request_json(
        method,
        f"{API_BASE}{path}",
        headers={"token": access_token},
        payload=payload,
    )
    if not (200 <= status < 300):
        raise RuntimeError(f"Beds24 {method} {path} failed HTTP {status}: {safe_public_response(obj)}")
    return obj


req = json.loads(REQUEST_FILE.read_text())
api_reference = req["request_id"]
query = urllib.parse.urlencode(
    [
        ("apiReference", api_reference),
        ("includeInvoiceItems", "true"),
        ("includeGuests", "true"),
    ]
)
rows = (api_call("GET", f"/bookings?{query}").get("data") or [])
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
    created = api_call("POST", "/bookings", payload)
    if not isinstance(created, list) or not created or not created[0].get("success"):
        raise RuntimeError(f"Beds24 booking create returned unexpected result: {safe_public_response(created)}")
    outcome = "created_new"
    rows = (api_call("GET", f"/bookings?{query}").get("data") or [])
    active = [row for row in rows if row.get("status") != "cancelled"]

if len(active) != 1:
    raise RuntimeError(f"Expected exactly one active booking for {api_reference}; found {len(active)}")

booking = active[0]
if str(booking.get("roomId")) != str(req["room_id"]):
    raise RuntimeError(f"Room mismatch: expected {req['room_id']}, got {booking.get('roomId')}")
if booking.get("arrival") != req["arrival"] or booking.get("departure") != req["departure"]:
    raise RuntimeError("Date mismatch after Beds24 verification")

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
            "auth_source": auth_source,
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
