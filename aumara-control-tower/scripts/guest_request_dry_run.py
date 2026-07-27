#!/usr/bin/env python3
"""Build guest-response and booking-note proposals without external writes.

The worker intentionally has no mail, Beds24, HTTP, or database client. It
accepts a JSON snapshot, classifies each event, and writes local audit evidence.
Three explicit environment guards must be enabled for every execution.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import sys
from typing import Any

TRUE_VALUES = {"1", "true", "yes", "on"}
SAFE_ENVIRONMENT = {
    "AUMARA_DRY_RUN": "true",
    "AUMARA_DISABLE_EMAIL_SEND": "true",
    "AUMARA_DISABLE_BOOKING_MUTATIONS": "true",
}

BOOKING_REFERENCE_RE = re.compile(r"\b(?:booking\s*ref(?:erence)?[:\s]*)?(\d{8})\b", re.I)

EVENT_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "cancellation",
        (
            "booking cancelled",
            "booking has been cancelled",
            "cancelled by the guest",
            "reserva cancelada",
            "ha cancelado su reserva",
        ),
    ),
    (
        "cot_request",
        (
            "baby cot",
            "crib",
            "cuna",
            "lit bébé",
            "детская кроват",
        ),
    ),
    (
        "pet_request",
        (
            "pet",
            "pets",
            "dog",
            "cat",
            "mascota",
            "perro",
            "gato",
            "животн",
            "собак",
            "кошк",
        ),
    ),
    (
        "bed_request",
        (
            "bed preference",
            "extra-large double",
            "large double bed",
            "matrimonial",
            "cama doble",
            "grand lit",
            "двуспальн",
        ),
    ),
    (
        "parking_request",
        (
            "parking",
            "car park",
            "aparcamiento",
            "estacionamiento",
            "парков",
        ),
    ),
    (
        "late_checkout",
        (
            "late check-out",
            "late checkout",
            "check out late",
            "salida tardía",
            "salida tarde",
            "поздний выезд",
        ),
    ),
    (
        "early_checkin",
        (
            "early check-in",
            "early check in",
            "check in early",
            "arrive early",
            "llegada anticipada",
            "entrada temprana",
            "ранний заезд",
        ),
    ),
    (
        "late_checkin",
        (
            "late check-in",
            "late check in",
            "arrive late",
            "late arrival",
            "llegada tardía",
            "поздний заезд",
        ),
    ),
    (
        "pricing_or_availability",
        (
            "what price",
            "how much",
            "precio",
            "tarifa",
            "availability",
            "disponibilidad",
            "available",
            "disponible",
        ),
    ),
)

SUPPORTED_AUTO_PROPOSALS = {
    "bed_request",
    "cot_request",
    "pet_request",
    "parking_request",
    "early_checkin",
    "late_checkin",
    "late_checkout",
    "cancellation",
}


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def env_enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in TRUE_VALUES


def input_flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in TRUE_VALUES
    return bool(value)


def assert_dry_run_guards() -> None:
    missing = [name for name in SAFE_ENVIRONMENT if not env_enabled(name)]
    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(
            f"Refusing to run without explicit dry-run guards: {joined}"
        )


def load_snapshot(path: pathlib.Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("events"), list):
        raise ValueError("Input must be an object containing an events list")
    return value


def stable_event_id(event: dict[str, Any]) -> str:
    source = "|".join(
        str(event.get(key) or "")
        for key in ("message_id", "thread_id", "booking_ref", "subject")
    )
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]


def booking_reference(event: dict[str, Any], text: str) -> str | None:
    explicit = str(event.get("booking_ref") or "").strip()
    if explicit:
        return explicit
    match = BOOKING_REFERENCE_RE.search(text)
    return match.group(1) if match else None


def classify_event(event: dict[str, Any]) -> str:
    explicit = str(event.get("event_type") or "").strip().lower()
    if explicit in {
        "bed_request",
        "cot_request",
        "pet_request",
        "cancellation",
        "pricing_or_availability",
        "booking_notification",
        "parking_request",
        "early_checkin",
        "late_checkin",
        "late_checkout",
    }:
        return explicit

    text = " ".join(
        str(event.get(key) or "")
        for key in ("subject", "body", "snippet")
    ).casefold()
    for event_type, patterns in EVENT_PATTERNS:
        if any(pattern in text for pattern in patterns):
            return event_type
    if "new booking" in text or "booking:" in text:
        return "booking_notification"
    return "other"


def normalized_language(event: dict[str, Any]) -> str:
    language = str(event.get("language") or "en").strip().lower()
    aliases = {
        "ee": "et",
        "est": "et",
        "estonian": "et",
        "es-es": "es",
        "spanish": "es",
        "english": "en",
    }
    return aliases.get(language, language.split("-", 1)[0] or "en")


def guest_first_name(event: dict[str, Any]) -> str:
    value = str(event.get("guest_first_name") or "").strip()
    return value or "Guest"


def signature() -> str:
    return (
        "El Cid Country Club\n"
        "+34 966 57 99 70\n"
        "https://elcidspain.com/"
    )


def bed_reply(language: str, name: str) -> str:
    if language == "et":
        return (
            f"Tere {name}!\n\n"
            "Täname broneeringu eest. Oleme märkinud teie soovi eriti suure "
            "kaheinimesevoodi kohta ning teeme kõik endast oleneva, et seda "
            "võimaluse korral arvestada. Palun mainige seda soovi ka saabumisel "
            "vastuvõtus. Soov sõltub saadavusest.\n\n"
            f"Parimate soovidega,\n{signature()}"
        )
    if language == "es":
        return (
            f"Hola {name}:\n\n"
            "Hemos registrado su preferencia por una cama doble grande. "
            "Haremos todo lo posible por atenderla según disponibilidad; "
            "por favor, recuérdela también en recepción a su llegada.\n\n"
            f"Un cordial saludo,\n{signature()}"
        )
    return (
        f"Hello {name},\n\n"
        "We have recorded your preference for a large double bed and will do "
        "everything possible to accommodate it, subject to availability. "
        "Please also mention the request at reception when you arrive.\n\n"
        f"Kind regards,\n{signature()}"
    )


def cot_reply(language: str, name: str) -> str:
    if language == "es":
        return (
            f"Hola {name}:\n\n"
            "Hemos registrado su solicitud de cuna. Haremos todo lo posible "
            "por prepararla, sujeto a disponibilidad; por favor, recuérdelo "
            "también en recepción a su llegada.\n\n"
            f"Un cordial saludo,\n{signature()}"
        )
    return (
        f"Hello {name},\n\n"
        "We have recorded your cot request and will do everything possible to "
        "prepare one, subject to availability. Please also mention it at "
        "reception when you arrive.\n\n"
        f"Kind regards,\n{signature()}"
    )


def pet_reply(language: str, name: str) -> str:
    if language == "es":
        return (
            f"Hola {name}:\n\n"
            "Hemos registrado su solicitud para alojarse con una mascota "
            "pequeña o mediana. La tarifa es de 35 €. La confirmación final "
            "queda sujeta a las condiciones de su reserva y a la validación "
            "del alojamiento.\n\n"
            f"Un cordial saludo,\n{signature()}"
        )
    return (
        f"Hello {name},\n\n"
        "We have recorded your request to stay with a small or medium-sized "
        "pet. The fee is €35. Final confirmation remains subject to the "
        "booking conditions and property review.\n\n"
        f"Kind regards,\n{signature()}"
    )


def cancellation_reply(language: str, name: str) -> str:
    if language == "es":
        return (
            f"Hola {name}:\n\n"
            "Hemos visto que ha cancelado su reserva y lo sentimos mucho. "
            "Si tiene un momento, le agradeceríamos que nos indicara el motivo. "
            "Si hay algo que podamos resolver desde el alojamiento, estaremos "
            "encantados de ayudarle.\n\n"
            f"Un cordial saludo,\n{signature()}"
        )
    return (
        f"Hello {name},\n\n"
        "We are sorry to see that you cancelled your reservation. If you have "
        "a moment, please tell us why. If there is anything we can help resolve "
        "at the property, we will be glad to assist.\n\n"
        f"Kind regards,\n{signature()}"
    )


def operational_request_reply(
    language: str,
    name: str,
    request_name_en: str,
    request_name_es: str,
) -> str:
    if language == "es":
        return (
            f"Hola {name}:\n\n"
            f"Hemos registrado su solicitud de {request_name_es}. "
            "La confirmación depende de la disponibilidad operativa. "
            "Por favor, confírmelo también en recepción.\n\n"
            f"Un cordial saludo,\n{signature()}"
        )
    return (
        f"Hello {name},\n\n"
        f"We have recorded your {request_name_en} request. Final confirmation "
        "depends on operational availability. Please also confirm it at "
        "reception.\n\n"
        f"Kind regards,\n{signature()}"
    )


def proposed_reply(event_type: str, language: str, name: str) -> str | None:
    if event_type == "bed_request":
        return bed_reply(language, name)
    if event_type == "cot_request":
        return cot_reply(language, name)
    if event_type == "pet_request":
        return pet_reply(language, name)
    if event_type == "cancellation":
        return cancellation_reply(language, name)
    operational = {
        "parking_request": ("parking", "aparcamiento"),
        "early_checkin": ("early check-in", "entrada anticipada"),
        "late_checkin": ("late check-in", "llegada tardía"),
        "late_checkout": ("late check-out", "salida tardía"),
    }
    if event_type in operational:
        english, spanish = operational[event_type]
        return operational_request_reply(language, name, english, spanish)
    return None


def proposed_booking_note(event_type: str) -> str | None:
    notes = {
        "bed_request": (
            "BED REQUEST — guest prefers one extra-large double bed. "
            "Confirm allocation at reception; subject to availability."
        ),
        "cot_request": (
            "COT REQUEST — prepare a baby cot if available and confirm at reception."
        ),
        "pet_request": (
            "PET REQUEST — small/medium pet, €35 fee; pending property validation."
        ),
        "parking_request": (
            "PARKING REQUEST — confirm a parking space at reception; "
            "subject to availability."
        ),
        "early_checkin": (
            "EARLY CHECK-IN REQUEST — confirm operational availability before arrival."
        ),
        "late_checkin": (
            "LATE CHECK-IN REQUEST — coordinate arrival time with reception."
        ),
        "late_checkout": (
            "LATE CHECK-OUT REQUEST — confirm operational availability at reception."
        ),
    }
    return notes.get(event_type)


def decision_for(event: dict[str, Any]) -> dict[str, Any]:
    combined_text = " ".join(
        str(event.get(key) or "")
        for key in ("subject", "body", "snippet")
    )
    event_type = classify_event(event)
    language = normalized_language(event)
    reply = proposed_reply(event_type, language, guest_first_name(event))
    already_sent = input_flag(event.get("reply_already_sent"))
    existing_draft = input_flag(event.get("existing_draft"))

    if already_sent:
        outcome = "deduplicated"
        reason = "A sent reply already exists in the source thread."
    elif existing_draft:
        outcome = "manual_review"
        reason = "An unsent draft already exists; no competing draft was created."
    elif event_type == "pricing_or_availability":
        outcome = "manual_review"
        reason = "Prices and availability require a current source-of-truth check."
    elif event_type in SUPPORTED_AUTO_PROPOSALS:
        outcome = "proposal_created"
        reason = "A reviewable proposal was generated in dry-run mode."
    else:
        outcome = "no_action"
        reason = "No approved guest-response rule matched."

    booking_note = proposed_booking_note(event_type)
    return {
        "event_id": stable_event_id(event),
        "source": str(event.get("source") or "snapshot"),
        "booking_ref": booking_reference(event, combined_text),
        "event_type": event_type,
        "language": language,
        "outcome": outcome,
        "reason": reason,
        "reply_already_sent": already_sent,
        "existing_draft": existing_draft,
        "proposed_reply": reply,
        "proposed_booking_note": booking_note,
        "email_send_requested": False,
        "booking_mutation_requested": False,
    }


def build_report(snapshot: dict[str, Any]) -> dict[str, Any]:
    assert_dry_run_guards()
    events = [decision_for(event) for event in snapshot["events"]]
    summary = {
        "events_total": len(events),
        "proposal_created": sum(
            item["outcome"] == "proposal_created" for item in events
        ),
        "deduplicated": sum(item["outcome"] == "deduplicated" for item in events),
        "manual_review": sum(item["outcome"] == "manual_review" for item in events),
        "no_action": sum(item["outcome"] == "no_action" for item in events),
        "emails_sent": 0,
        "booking_mutations": 0,
    }
    report = {
        "generated_at_utc": now_utc(),
        "mode": "dry-run",
        "source": str(snapshot.get("source") or "snapshot"),
        "safety": {
            "dry_run": True,
            "email_send_disabled": True,
            "booking_mutations_disabled": True,
            "external_network_calls": 0,
        },
        "summary": summary,
        "events": events,
    }
    validate_report(report)
    return report


def validate_report(report: dict[str, Any]) -> None:
    if report.get("mode") != "dry-run":
        raise RuntimeError("Unsafe report mode")
    safety = report.get("safety") or {}
    if not all(
        safety.get(key)
        for key in (
            "dry_run",
            "email_send_disabled",
            "booking_mutations_disabled",
        )
    ):
        raise RuntimeError("Dry-run safety invariant failed")
    if safety.get("external_network_calls") != 0:
        raise RuntimeError("Dry-run unexpectedly recorded a network call")
    for event in report.get("events") or []:
        if event.get("email_send_requested"):
            raise RuntimeError("Dry-run attempted to send an email")
        if event.get("booking_mutation_requested"):
            raise RuntimeError("Dry-run attempted a booking mutation")


def write_csv(report: dict[str, Any], path: pathlib.Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = (
        "event_id",
        "booking_ref",
        "event_type",
        "language",
        "outcome",
        "reason",
        "reply_already_sent",
        "existing_draft",
        "email_send_requested",
        "booking_mutation_requested",
    )
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for event in report["events"]:
            writer.writerow({field: event.get(field) for field in fields})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=pathlib.Path)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    parser.add_argument("--csv", type=pathlib.Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        snapshot = load_snapshot(args.input)
        report = build_report(snapshot)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        if args.csv:
            write_csv(report, args.csv)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"Dry-run failed safely: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(report["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
