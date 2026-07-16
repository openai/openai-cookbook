#!/usr/bin/env python3
"""Idempotent Booking.com guest replies for El Cid Country Club.

The script is deliberately narrow:
- property 324903 only;
- Booking.com bookings only;
- messages only (it never changes prices, availability, status or payments);
- dry-run unless BEDS24_AUTO_REPLY_EXECUTE=1;
- an identical host message is never sent twice.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import urllib.error
import urllib.parse
import urllib.request

from beds24_elcid_studio_audit import AuditError, data_rows, get_access_token


PROPERTY_ID = 324903
STUDIO_ROOM_ID = 674486
ACTIVE_STATUSES = {"confirmed", "new", "request"}
OUTPUT = pathlib.Path(
    os.environ.get(
        "BEDS24_AUTO_REPLY_OUTPUT",
        "aumara-control-tower/evidence/elcid-auto-replies.json",
    )
)

# These four bookings were reviewed from the Beds24 notification and get a
# precise reply. Future bookings receive a conservative language template.
TARGET_MESSAGES = {
    89955894: (
        "Hola Manuel:\n\nGracias por tu reserva. Hemos anotado tu preferencia "
        "por una cama doble grande. No se trata de una cama adicional; la "
        "petición queda sujeta a la configuración disponible de la habitación. "
        "Si necesitas una medida concreta, escríbenos antes de tu llegada.\n\n"
        "Saludos,\nEl Cid Country Club"
    ),
    89957150: (
        "Dzień dobry,\n\ndziękujemy za rezerwację. Odnotowaliśmy preferencję "
        "dotyczącą jednego dużego łóżka podwójnego. Nie jest to dodatkowe łóżko; "
        "prośba zależy od dostępnej konfiguracji pokoju. Śniadanie Genius jest "
        "uwzględnione w rezerwacji.\n\nPozdrawiamy,\nEl Cid Country Club"
    ),
    89952542: (
        "Hola Sergio:\n\nGracias por tu reserva. Hemos anotado la preferencia "
        "por una cama doble grande y que viajan con un bebé. La petición de cama "
        "depende de la configuración disponible. El parking gratuito está sujeto "
        "a disponibilidad; lo confirmaremos antes de la llegada.\n\nSaludos,\n"
        "El Cid Country Club"
    ),
    89950498: (
        "Hola Alejandro:\n\nGracias por tu reserva. Estamos verificando la "
        "disponibilidad operativa del Studio para tus fechas. Si fuera necesario "
        "un cambio, te ofreceremos una alternativa en El Cid Country Club y "
        "pediremos tu confirmación antes de modificar la reserva.\n\nSaludos,\n"
        "El Cid Country Club"
    ),
}

GENERIC_MESSAGES = {
    "es": (
        "Hola:\n\nGracias por reservar en El Cid Country Club. Hemos recibido "
        "y confirmado tu reserva. Revisaremos cualquier petición especial y te "
        "contactaremos si necesitamos aclarar algún detalle. Las preferencias de "
        "cama y parking dependen de la configuración y disponibilidad existentes."
        "\n\nSaludos,\nEl Cid Country Club"
    ),
    "pl": (
        "Dzień dobry,\n\ndziękujemy za rezerwację w El Cid Country Club. "
        "Otrzymaliśmy i potwierdziliśmy rezerwację. Sprawdzimy wszystkie prośby "
        "specjalne i skontaktujemy się, jeśli potrzebne będą dodatkowe informacje. "
        "Preferencje dotyczące łóżka i parkingu zależą od dostępności.\n\n"
        "Pozdrawiamy,\nEl Cid Country Club"
    ),
    "en": (
        "Hello,\n\nThank you for booking El Cid Country Club. We have received "
        "and confirmed your reservation. We will review any special requests and "
        "contact you if clarification is needed. Bed and parking preferences are "
        "subject to the existing room configuration and availability.\n\n"
        "Kind regards,\nEl Cid Country Club"
    ),
}

STUDIO_MESSAGES = {
    "es": (
        "Hola:\n\nGracias por tu reserva. Estamos verificando la disponibilidad "
        "operativa del Studio para tus fechas. Si fuera necesario un cambio, te "
        "ofreceremos una alternativa en El Cid Country Club y pediremos tu "
        "confirmación antes de modificar la reserva.\n\nSaludos,\n"
        "El Cid Country Club"
    ),
    "en": (
        "Hello,\n\nThank you for your reservation. We are verifying the Studio's "
        "operational availability for your dates. If a change is required, we will "
        "offer an alternative at El Cid Country Club and ask for your confirmation "
        "before modifying the reservation.\n\nKind regards,\nEl Cid Country Club"
    ),
}


def normalize_text(value: object) -> str:
    """Normalize a message for reliable duplicate checks."""
    return " ".join(str(value or "").split()).casefold()


def language_for(booking: dict[str, object]) -> str:
    """Resolve a small supported language set without guessing from a name."""
    raw = str(
        booking.get("language")
        or booking.get("lang")
        or booking.get("country")
        or ""
    ).strip().lower()
    if raw.startswith("es"):
        return "es"
    if raw.startswith("pl"):
        return "pl"
    return "en"


def reply_for(booking: dict[str, object]) -> str | None:
    """Return the reviewed or conservative message for one booking."""
    booking_id = int(booking.get("id") or 0)
    if booking_id in TARGET_MESSAGES:
        return TARGET_MESSAGES[booking_id]
    language = language_for(booking)
    if int(booking.get("roomId") or 0) == STUDIO_ROOM_ID:
        return STUDIO_MESSAGES.get(language, STUDIO_MESSAGES["en"])
    return GENERIC_MESSAGES.get(language, GENERIC_MESSAGES["en"])


def booking_in_scope(booking: dict[str, object]) -> bool:
    """Enforce the property, channel and active-status safety boundary."""
    property_id = int(booking.get("propertyId") or PROPERTY_ID)
    channel = str(booking.get("channel") or booking.get("referer") or "").lower()
    status = str(booking.get("status") or "").lower()
    return (
        property_id == PROPERTY_ID
        and channel.startswith("booking")
        and status in ACTIVE_STATUSES
    )


def request_json(
    method: str,
    path: str,
    token: str,
    api_base: str,
    body: object | None = None,
) -> tuple[int, object]:
    """Call the exact documented API V2 endpoint."""
    payload = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        f"{api_base}{path}",
        data=payload,
        headers={
            "accept": "application/json",
            "content-type": "application/json",
            "token": token,
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            raw = response.read().decode("utf-8", "replace")
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            parsed: object = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {"error": raw[:300]}
        return exc.code, parsed


def fetch_new_bookings(token: str, api_base: str) -> list[dict[str, object]]:
    """Fetch Booking.com bookings created in the past 24 hours."""
    query = urllib.parse.urlencode(
        [
            ("filter", "new"),
            ("propertyId", PROPERTY_ID),
            ("channel", "booking"),
            ("includeGuests", "true"),
        ]
    )
    status, response = request_json(
        "GET", f"/bookings?{query}", token, api_base
    )
    if not 200 <= status < 300:
        raise AuditError(f"Booking lookup failed with HTTP {status}")
    return data_rows(response, "Booking")


def fetch_messages(
    token: str, api_base: str, booking_id: int
) -> list[dict[str, object]]:
    """Fetch the full available message history for duplicate protection."""
    query = urllib.parse.urlencode(
        {"bookingId": booking_id, "maxAge": 999}
    )
    status, response = request_json(
        "GET", f"/bookings/messages?{query}", token, api_base
    )
    if not 200 <= status < 300:
        raise AuditError(
            f"Message lookup failed for booking {booking_id} with HTTP {status}"
        )
    return data_rows(response, "Message")


def already_sent(messages: list[dict[str, object]], reply: str) -> bool:
    """Return true if Beds24 already has the same host reply."""
    expected = normalize_text(reply)
    for item in messages:
        source = str(item.get("source") or "").lower()
        text = item.get("message") or item.get("text") or item.get("body")
        if source == "host" and normalize_text(text) == expected:
            return True
    return False


def send_message(
    token: str, api_base: str, booking_id: int, reply: str
) -> None:
    """Send one documented host message."""
    status, _ = request_json(
        "POST",
        "/bookings/messages",
        token,
        api_base,
        [{"bookingId": booking_id, "message": reply}],
    )
    if status != 201:
        raise AuditError(
            f"Message send failed for booking {booking_id} with HTTP {status}"
        )


def run(
    bookings: list[dict[str, object]],
    *,
    token: str,
    api_base: str,
    execute: bool,
) -> dict[str, object]:
    """Plan or execute idempotent replies and return sanitized results."""
    results: list[dict[str, object]] = []
    for booking in bookings:
        booking_id = int(booking.get("id") or 0)
        item = {"bookingId": booking_id, "action": "skip"}
        if not booking_id or not booking_in_scope(booking):
            item["reason"] = "outside_scope"
            results.append(item)
            continue
        reply = reply_for(booking)
        if not reply:
            item["reason"] = "no_template"
            results.append(item)
            continue
        try:
            messages = fetch_messages(token, api_base, booking_id)
        except AuditError as exc:
            item["reason"] = "message_lookup_failed"
            item["error"] = str(exc)
            results.append(item)
            continue
        if already_sent(messages, reply):
            item["reason"] = "already_sent"
            results.append(item)
            continue
        item["action"] = "would_send" if not execute else "sent"
        item["template"] = (
            "reviewed" if booking_id in TARGET_MESSAGES else "generic"
        )
        if execute:
            send_message(token, api_base, booking_id, reply)
        results.append(item)
    return {
        "schema": "elcid-auto-replies-v1",
        "executed": execute,
        "propertyId": PROPERTY_ID,
        "processed": len(results),
        "sent": sum(item["action"] == "sent" for item in results),
        "wouldSend": sum(item["action"] == "would_send" for item in results),
        "results": results,
    }


def main() -> None:
    """Authenticate, process new bookings and write a sanitized audit artifact."""
    execute = os.environ.get("BEDS24_AUTO_REPLY_EXECUTE") == "1"
    token, auth_mode, api_base, auth_source, _ = get_access_token()
    bookings = fetch_new_bookings(token, api_base)
    result = run(
        bookings,
        token=token,
        api_base=api_base,
        execute=execute,
    )
    result.update(
        {
            "runAtUtc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "authMode": auth_mode,
            "authSource": auth_source,
            "apiHost": urllib.parse.urlparse(api_base).netloc,
            "secretLogged": False,
            "priceMutations": False,
            "bookingMutations": False,
        }
    )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
