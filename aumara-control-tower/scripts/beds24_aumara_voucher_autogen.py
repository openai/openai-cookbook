#!/usr/bin/env python3
"""Generate one-time 10% AUMARA vouchers after checkout.

Idempotent. Reads confirmed Beds24 bookings that already departed, keeps every
existing one-time code, appends missing AUM{bookingId} codes, and writes a
phone-readable HTML card with a live booking QR.

Never prints credentials. Does not email guests.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import os
import pathlib
import re
import sys
import urllib.parse
import urllib.request
import urllib.error

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from beds24_elcid_studio_audit import (
    API_BASES,
    AuditError,
    data_rows,
    get_access_token,
    normalize,
    request_json,
)

PROPERTY_ID = 324882
DISCOUNT = 10
BOOKING_BASE = "https://beds24.com/booking2.php"
ROOM_NAMES = {
    674465: "Chalet",
    674466: "Superior Chalet",
}
# Pretty codes already live in Beds24 — do not replace them.
KNOWN_ALIASES = {
    90754013: "AUMARAIBANEZ10",
    91062629: "AUMARAMARTINEZ10",
    91036023: "AUMARAAYALA10",
}
SKIP_STATUS = {"cancelled", "canceled", "black", "inquiry", "request"}
OUTPUT_DIR = pathlib.Path(
    os.environ.get(
        "AUMARA_VOUCHER_OUT",
        "aumara-control-tower/evidence/vouchers",
    )
)


class VoucherError(AuditError):
    pass


def request_json_body(method: str, path: str, token: str, api_base: str, payload: object):
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    req = urllib.request.Request(
        f"{api_base}{path}",
        data=raw,
        headers={
            "accept": "application/json",
            "content-type": "application/json",
            "token": token,
        },
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


def resolve_access() -> tuple[str, str, str]:
    direct = normalize(os.environ.get("BEDS24_PROPERTIES_TOKEN"))
    if direct:
        for api_base in API_BASES:
            status, details = request_json(
                "GET",
                "/authentication/details",
                headers={"token": direct},
                api_base=api_base,
            )
            if 200 <= status < 300 and isinstance(details, dict) and details.get("validToken") is True:
                return direct, api_base, "long_life_token"
    token, credential_mode, api_base, _, _ = get_access_token()
    return token, api_base, credential_mode


def window(today: dt.date) -> tuple[dt.date, dt.date]:
    lookback = int(os.environ.get("AUMARA_VOUCHER_LOOKBACK_DAYS", "30"))
    return today - dt.timedelta(days=lookback), today


def code_for(booking_id: int) -> str:
    if booking_id in KNOWN_ALIASES:
        return KNOWN_ALIASES[booking_id]
    code = f"AUM{booking_id}"
    if not re.fullmatch(r"[A-Z0-9]{8,32}", code):
        raise VoucherError(f"Generated code is not alphanumeric: {code}")
    return code


def booking_url(code: str) -> str:
    query = urllib.parse.urlencode(
        {"propid": PROPERTY_ID, "voucher": code, "lang": "es", "mobile": 1}
    )
    return f"{BOOKING_BASE}?{query}"


def fetch_property(token: str, api_base: str) -> dict:
    status, response = request_json(
        "GET",
        f"/properties?id={PROPERTY_ID}",
        headers={"token": token},
        api_base=api_base,
    )
    if not 200 <= status < 300:
        raise VoucherError(f"Property GET failed: HTTP {status}")
    rows = data_rows(response, "AUMARA property")
    if len(rows) != 1 or int(rows[0].get("id") or 0) != PROPERTY_ID:
        raise VoucherError("AUMARA property response was not uniquely scoped")
    return rows[0]


def fetch_departed(token: str, api_base: str, start: dt.date, end: dt.date) -> list[dict]:
    query = urllib.parse.urlencode(
        {
            "propertyId": PROPERTY_ID,
            "departureFrom": start.isoformat(),
            "departureTo": end.isoformat(),
            "includeGuests": "true",
        }
    )
    status, response = request_json(
        "GET",
        f"/bookings?{query}",
        headers={"token": token},
        api_base=api_base,
    )
    if not 200 <= status < 300:
        raise VoucherError(f"Bookings GET failed: HTTP {status}")
    rows = data_rows(response, "Booking")
    out: list[dict] = []
    for row in rows:
        if int(row.get("propertyId") or PROPERTY_ID) != PROPERTY_ID:
            continue
        if str(row.get("status") or "").strip().lower() in SKIP_STATUS:
            continue
        try:
            departure = dt.date.fromisoformat(str(row.get("departure") or ""))
        except ValueError:
            continue
        if departure < start or departure > end:
            continue
        out.append(row)
    return out


def existing_phrases(vouchers: list) -> set[str]:
    phrases: set[str] = set()
    for row in vouchers:
        if not isinstance(row, dict):
            continue
        phrase = str(row.get("phrase") or "").strip().upper()
        if phrase:
            phrases.add(phrase)
    return phrases


def merge_vouchers(current: list, needed: list[str]) -> tuple[list[dict], list[str]]:
    merged = []
    for row in current:
        if isinstance(row, dict) and str(row.get("phrase") or "").strip():
            merged.append(
                {
                    "phrase": str(row["phrase"]).strip().upper(),
                    "discount": int(row.get("discount") or DISCOUNT),
                }
            )
    have = existing_phrases(merged)
    added: list[str] = []
    for code in needed:
        if code in have:
            continue
        merged.append({"phrase": code, "discount": DISCOUNT})
        have.add(code)
        added.append(code)
    return merged, added


def qr_svg(url: str) -> str:
    import qrcode
    from qrcode.image.svg import SvgPathImage

    img = qrcode.make(url, image_factory=SvgPathImage, box_size=8, border=2)
    return img.to_string().decode("utf-8") if isinstance(img.to_string(), bytes) else str(img.to_string())


def card_html(item: dict, svg: str) -> str:
    guest = html.escape(str(item["guestFirstName"]))
    unit = html.escape(str(item["roomName"]))
    stay = html.escape(f"{item['arrival']} — {item['departure']}")
    code = html.escape(str(item["code"]))
    url = html.escape(str(item["bookingUrl"]))
    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>AUMARA · {code}</title>
  <style>
    :root {{ --forest:#213329; --gold:#c49a64; --cream:#f3ecde; --paper:#fffaf2; --ink:#182019; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--cream); color:var(--ink); font-family:Georgia,serif; }}
    .card {{ max-width:420px; margin:18px auto; background:var(--paper); border:1px solid #d8d0c2; border-radius:28px; overflow:hidden; box-shadow:0 18px 50px rgba(33,51,41,.14); }}
    .hero {{ padding:28px 24px 16px; background:linear-gradient(180deg,#2a4033,#213329); color:#fff; text-align:center; }}
    .kicker {{ margin:0; letter-spacing:.18em; font:700 11px/1 Inter,system-ui,sans-serif; color:#efc68d; text-transform:uppercase; }}
    h1 {{ margin:10px 0 0; font:500 34px/1 Georgia,serif; }}
    .body {{ padding:22px 22px 28px; }}
    .code {{ margin:0; padding:12px 14px; border-radius:16px; background:#213329; color:#fffaf2; text-align:center; font:500 22px/1.1 Georgia,serif; letter-spacing:.04em; }}
    .meta {{ display:grid; grid-template-columns:1fr 1fr; gap:10px; margin:16px 0 18px; font-family:Inter,system-ui,sans-serif; font-size:13px; }}
    .meta div {{ padding:10px 12px; border:1px solid #e4ddd0; border-radius:14px; }}
    .meta span {{ display:block; color:#687168; font-size:10px; letter-spacing:.12em; text-transform:uppercase; margin-bottom:4px; }}
    .qr {{ display:block; width:188px; height:188px; margin:0 auto 12px; }}
    .hint {{ margin:0; text-align:center; color:#405047; font:16px/1.45 Inter,system-ui,sans-serif; }}
    a {{ color:inherit; }}
  </style>
</head>
<body>
  <article class="card">
    <header class="hero">
      <p class="kicker">AUMARA · Mediterranean retreat</p>
      <h1>Tu 10% privado</h1>
    </header>
    <div class="body">
      <p class="code">{code}</p>
      <div class="meta">
        <div><span>Huésped</span>{guest}</div>
        <div><span>Estancia</span>{stay}</div>
        <div><span>Casa</span>{unit}</div>
        <div><span>Uso</span>Una vez · 10%</div>
      </div>
      {svg}
      <p class="hint">Escanea para reservar la próxima estancia con tu código.<br><a href="{url}">Abrir reserva</a></p>
    </div>
  </article>
</body>
</html>
"""


def write_cards(items: list[dict]) -> list[str]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for item in items:
        svg = qr_svg(item["bookingUrl"])
        # keep the svg inline and sized
        svg = svg.replace("<svg ", '<svg class="qr" ', 1)
        path = OUTPUT_DIR / f"{item['code']}.html"
        path.write_text(card_html(item, svg), encoding="utf-8")
        written.append(str(path))
    return written


def public_item(booking: dict, code: str) -> dict:
    booking_id = int(booking.get("id") or 0)
    first = str(booking.get("firstName") or "Huésped").split()[0].title()
    room_id = int(booking.get("roomId") or 0)
    return {
        "bookingId": booking_id,
        "guestFirstName": first,
        "arrival": booking.get("arrival"),
        "departure": booking.get("departure"),
        "roomId": room_id,
        "roomName": ROOM_NAMES.get(room_id, "AUMARA"),
        "code": code,
        "discountPercent": DISCOUNT,
        "bookingUrl": booking_url(code),
        "oneTime": True,
    }


def main() -> int:
    apply = os.environ.get("AUMARA_VOUCHER_APPLY", "1") == "1"
    today = dt.date.fromisoformat(
        os.environ.get("AUMARA_TODAY", dt.datetime.now(dt.timezone.utc).date().isoformat())
    )
    start, end = window(today)
    token, api_base, mode = resolve_access()
    bookings = fetch_departed(token, api_base, start, end)
    needed = [code_for(int(row["id"])) for row in bookings]
    prop = fetch_property(token, api_base)
    current = prop.get("oneTimeVouchers") or []
    if not isinstance(current, list):
        raise VoucherError("oneTimeVouchers is not an array")
    merged, added = merge_vouchers(current, needed)

    if apply and added:
        status, body = request_json_body(
            "POST",
            "/properties",
            token,
            api_base,
            [{"id": PROPERTY_ID, "oneTimeVouchers": merged}],
        )
        if not 200 <= status < 300:
            raise VoucherError(f"Property POST failed: HTTP {status} {body}")
        verify = fetch_property(token, api_base)
        have = existing_phrases(verify.get("oneTimeVouchers") or [])
        missing = [code for code in needed if code not in have]
        if missing:
            raise VoucherError(f"Verification missed codes: {missing}")

    items = [public_item(row, code_for(int(row["id"]))) for row in bookings]
    cards = write_cards(items)
    report = {
        "schema": "aumara-voucher-autogen-v1",
        "status": "active" if apply else "planned",
        "propertyId": PROPERTY_ID,
        "window": {"from": start.isoformat(), "to": end.isoformat()},
        "credentialMode": mode,
        "bookingsScanned": len(bookings),
        "codesNeeded": needed,
        "codesAdded": added,
        "codesLive": [item["code"] for item in items],
        "cards": cards,
        "credentialsExposed": False,
        "emailsSent": 0,
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "manifest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
