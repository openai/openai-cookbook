#!/usr/bin/env python3
"""Build deterministic AUMARA/EL CID guest-care proposals with zero sends."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import re
import unicodedata
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


DEFAULT_POLICY_ROOT = pathlib.Path(__file__).resolve().parents[1] / "policies"
SNAPSHOT_FILE = "guest_journey_runtime.json"
EXPECTED_POLICY_VERSION = "2026.07.27.1"
EXPECTED_SNAPSHOT_VERSION = "2026.08.17.2"
PROPOSAL_GUARDS = {
    "AUMARA_GUEST_JOURNEY_MODE": "proposal",
    "AUMARA_DISABLE_GUEST_SEND": "true",
    "AUMARA_DISABLE_BOOKING_MUTATIONS": "true",
}
IN_HOUSE_STATUSES = {"checked_in", "in_house"}
SUPPORTED_EVENTS = {"post_checkin", "first_morning"}
PROPERTY_NAMES = {
    "aumara": "AUMARA",
    "elcid": "El Cid Country Club",
}
LANGUAGE_ALIASES = {
    "de-de": "de",
    "deutsch": "de",
    "dutch": "nl",
    "en-gb": "en",
    "en-us": "en",
    "english": "en",
    "es-es": "es",
    "español": "es",
    "fr-fr": "fr",
    "français": "fr",
    "french": "fr",
    "german": "de",
    "nederlands": "nl",
    "nl-nl": "nl",
    "spanish": "es",
}
HIGH_PRIORITY_PATTERNS = (
    "unsafe",
    "danger",
    "fire",
    "smoke",
    "injury",
    "locked out",
    "no access",
    "charged twice",
    "payment problem",
    "peligro",
    "incendio",
    "sin acceso",
    "cobrado dos veces",
    "dangereux",
    "incendie",
    "sans accès",
    "doppelt berechnet",
    "gevaar",
    "brand",
    "dubbel afgeschreven",
    "door will not open",
    "door won't open",
    "cannot get in",
    "no puedo entrar",
    "no podemos entrar",
    "puerta no abre",
    "porte ne s'ouvre pas",
    "tur offnet nicht",
    "deur gaat niet open",
)
SERVICE_ISSUE_PATTERNS = (
    "not clean",
    "dirty",
    "noise",
    "too loud",
    "wifi not",
    "wi-fi not",
    "air conditioning not",
    "ac not",
    "broken",
    "doesn't work",
    "does not work",
    "sucio",
    "ruido",
    "no funciona",
    "climatisation ne",
    "sale",
    "bruit",
    "ne fonctionne pas",
    "schmutzig",
    "lärm",
    "funktioniert nicht",
    "vies",
    "lawaai",
    "werkt niet",
    "no hot water",
    "sin agua caliente",
    "no tenemos agua caliente",
    "pas d'eau chaude",
    "kein warmes wasser",
    "geen warm water",
)
URGENT_ISSUE_FLAGS = {
    "access_locked_out",
    "duplicate_charge",
    "fire",
    "medical",
    "safety",
}


class GuestJourneyError(ValueError):
    """Raised when a guest-journey decision cannot be made safely."""


def _load(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GuestJourneyError(f"cannot load {path.name}") from exc
    if not isinstance(value, dict):
        raise GuestJourneyError(f"{path.name} is not an object")
    return value


def _policy_bundle(
    root: pathlib.Path = DEFAULT_POLICY_ROOT,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    root = pathlib.Path(root)
    snapshot = _load(root / SNAPSHOT_FILE)
    if snapshot.get("snapshot_version") != EXPECTED_SNAPSHOT_VERSION:
        raise GuestJourneyError("guest journey snapshot version mismatch")
    if snapshot.get("registry_policy_version") != EXPECTED_POLICY_VERSION:
        raise GuestJourneyError("guest journey registry version mismatch")
    if snapshot.get("mode") != "proposal_only":
        raise GuestJourneyError("guest journey runtime is not proposal-only")

    index = _load(root / "registry.yaml")
    if index.get("policy_version") != EXPECTED_POLICY_VERSION:
        raise GuestJourneyError("policy version mismatch")

    approved_ids = snapshot.get("policy_ids")
    if not isinstance(approved_ids, list) or not approved_ids:
        raise GuestJourneyError("guest journey snapshot has no policies")

    result: dict[str, dict[str, Any]] = {}
    registries = index.get("registries") or {}
    for property_key in ("shared", "aumara", "elcid"):
        filename = registries.get(property_key)
        if not isinstance(filename, str):
            raise GuestJourneyError("policy registry mapping is incomplete")
        document = _load(root / filename)
        if document.get("policy_version") != EXPECTED_POLICY_VERSION:
            raise GuestJourneyError(f"{property_key} policy version mismatch")
        for policy in document.get("policies") or []:
            if isinstance(policy, dict) and policy.get("policy_id") in approved_ids:
                result[str(policy["policy_id"])] = policy

    missing = sorted(set(approved_ids) - set(result))
    if missing:
        raise GuestJourneyError(
            "guest journey snapshot policies are missing: " + ", ".join(missing)
        )
    for policy_id, policy in result.items():
        if policy.get("status") != "verified":
            raise GuestJourneyError(f"policy {policy_id} is not verified")
        if policy.get("allowed_beds24_action"):
            raise GuestJourneyError(f"policy {policy_id} permits a Beds24 action")
    return snapshot, result


def _normalize_language(language: str, supported: list[str]) -> str:
    value = (language or "en").strip().lower()
    normalized = LANGUAGE_ALIASES.get(value, value.split("-", 1)[0] or "en")
    return normalized if normalized in supported else "en"


def _parse_timestamp(value: Any, field: str) -> dt.datetime:
    if not isinstance(value, str) or not value.strip():
        raise GuestJourneyError(f"{field} is required")
    try:
        parsed = dt.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise GuestJourneyError(f"{field} is invalid") from exc
    if parsed.tzinfo is None:
        raise GuestJourneyError(f"{field} must include a timezone")
    return parsed


def _safe_name(value: Any) -> str:
    name = re.sub(r"[\r\n\t]+", " ", str(value or "Guest")).strip()
    return (name or "Guest")[:80]


def _normalize_signal_text(value: Any) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or "").casefold())
    without_marks = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    return re.sub(r"\s+", " ", without_marks).strip()


def _signal_priority(event: dict[str, Any]) -> str | None:
    severity = str(event.get("issue_severity") or "").strip().lower()
    if severity in {"urgent", "critical"}:
        return "urgent"
    if severity in {"high", "open"}:
        return "high"
    issue_flags = event.get("issue_flags") or []
    if not isinstance(issue_flags, list):
        raise GuestJourneyError("issue_flags must be a list")
    normalized_flags = {
        str(flag).strip().lower() for flag in issue_flags if str(flag).strip()
    }
    if normalized_flags & URGENT_ISSUE_FLAGS:
        return "urgent"
    if normalized_flags:
        return "high"
    if bool(event.get("open_issue")):
        return "high"
    text = _normalize_signal_text(event.get("last_guest_message"))
    if any(
        _normalize_signal_text(pattern) in text for pattern in HIGH_PRIORITY_PATTERNS
    ):
        return "urgent"
    if any(
        _normalize_signal_text(pattern) in text for pattern in SERVICE_ISSUE_PATTERNS
    ):
        return "high"
    return None


def _base_decision(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "property": str(event.get("property") or "").strip().lower(),
        "booking_ref": str(event.get("booking_ref") or "").strip(),
        "event_type": str(event.get("event_type") or "").strip().lower(),
        "decision": "blocked",
        "reason": "unclassified",
        "email_send_requested": False,
        "beds24_send_requested": False,
        "whatsapp_send_requested": False,
        "booking_mutation_requested": False,
    }


def evaluate_event(
    event: dict[str, Any],
    root: pathlib.Path = DEFAULT_POLICY_ROOT,
) -> dict[str, Any]:
    """Return one fail-closed proposal, skip, block or manual-review decision."""
    if not isinstance(event, dict):
        raise GuestJourneyError("event is not an object")
    snapshot, policies = _policy_bundle(root)
    decision = _base_decision(event)
    event_type = decision["event_type"]

    if event_type in set(snapshot.get("hard_blocked_event_types") or []):
        decision["reason"] = "checkout_pressure_hard_block"
        decision["policy_id"] = "shared.lifecycle-checkout-reminder-block"
        return decision
    if event_type not in SUPPORTED_EVENTS:
        decision["reason"] = "unsupported_event_type"
        return decision

    property_key = decision["property"]
    if property_key not in PROPERTY_NAMES:
        decision["reason"] = "property_unresolved"
        return decision
    if not decision["booking_ref"]:
        decision["reason"] = "booking_reference_missing"
        return decision
    status = str(event.get("status") or "").strip().lower()
    if status not in IN_HOUSE_STATUSES:
        decision.update(decision="skip", reason="booking_not_in_house")
        return decision

    now = _parse_timestamp(event.get("now"), "now")
    check_in = _parse_timestamp(event.get("check_in_at"), "check_in_at")
    departure = _parse_timestamp(event.get("departure_at"), "departure_at")
    if not check_in <= now < departure:
        decision.update(decision="skip", reason="stay_not_active")
        return decision

    policy_key = f"{property_key}:{event_type}"
    event_policy_ids = snapshot.get("event_policy_ids") or {}
    policy_id = event_policy_ids.get(policy_key)
    policy = policies.get(str(policy_id))
    if not policy:
        raise GuestJourneyError(f"missing event policy {policy_key}")

    priority = _signal_priority(event)
    if priority:
        decision.update(
            decision="manual_review",
            reason="negative_or_open_issue",
            priority=priority,
            policy_id="shared.lifecycle-negative-signal-escalation",
        )
        return decision

    dedupe_key = ":".join(
        (property_key, decision["booking_ref"].casefold(), event_type)
    )
    decision["dedupe_key"] = dedupe_key
    decision["policy_id"] = policy_id
    sent_keys = event.get("sent_dedupe_keys") or []
    if not isinstance(sent_keys, list):
        raise GuestJourneyError("sent_dedupe_keys must be a list")
    if dedupe_key in sent_keys:
        decision.update(decision="skip", reason="already_proposed_or_sent")
        return decision

    if event_type == "post_checkin":
        elapsed = (
            now.astimezone(dt.timezone.utc) - check_in.astimezone(dt.timezone.utc)
        ).total_seconds() / 60
        if elapsed < 60 or elapsed > 180:
            decision.update(decision="skip", reason="outside_post_checkin_window")
            return decision
    else:
        timezone_map = snapshot.get("property_timezones") or {}
        timezone_name = timezone_map.get(property_key)
        if not isinstance(timezone_name, str) or not timezone_name:
            raise GuestJourneyError(f"timezone missing for {property_key}")
        try:
            property_timezone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise GuestJourneyError(
                f"timezone invalid for {property_key}"
            ) from exc
        now_local = now.astimezone(property_timezone)
        check_in_local = check_in.astimezone(property_timezone)
        departure_local = departure.astimezone(property_timezone)
        try:
            nights = int(event.get("nights") or 0)
        except (TypeError, ValueError) as exc:
            raise GuestJourneyError("nights must be an integer") from exc
        if nights < 2:
            decision.update(decision="skip", reason="stay_too_short")
            return decision
        if now_local.date() >= departure_local.date():
            decision.update(decision="skip", reason="departure_day")
            return decision
        if now_local.date() != check_in_local.date() + dt.timedelta(days=1):
            decision.update(decision="skip", reason="not_first_morning")
            return decision
        local_minutes = now_local.hour * 60 + now_local.minute
        if not 510 <= local_minutes <= 690:
            decision.update(decision="skip", reason="outside_first_morning_window")
            return decision

    templates = policy.get("response_templates")
    if not isinstance(templates, dict):
        raise GuestJourneyError(f"policy {policy_id} has no templates")
    supported = snapshot.get("supported_languages") or []
    language = _normalize_language(str(event.get("language") or "en"), supported)
    template = templates.get(language) or templates.get("en")
    if not isinstance(template, str) or not template.strip():
        raise GuestJourneyError(f"policy {policy_id} lacks language {language}")
    message = template.replace("{guest_first_name}", _safe_name(event.get("guest_first_name")))
    decision.update(
        decision="proposal",
        reason="eligible",
        language=language,
        property_name=PROPERTY_NAMES[property_key],
        message=message,
        snapshot_version=snapshot["snapshot_version"],
        durable_claim_required=True,
    )
    return decision


def assert_proposal_guards() -> None:
    missing = [
        name
        for name, expected in PROPOSAL_GUARDS.items()
        if os.environ.get(name, "").strip().lower() != expected
    ]
    if missing:
        raise GuestJourneyError(
            "refusing to run without proposal guards: " + ", ".join(missing)
        )


def build_report(
    events: list[dict[str, Any]],
    root: pathlib.Path = DEFAULT_POLICY_ROOT,
) -> dict[str, Any]:
    decisions: list[dict[str, Any]] = []
    claimed_in_batch: set[str] = set()
    for source_event in events:
        if not isinstance(source_event, dict):
            raise GuestJourneyError("event is not an object")
        event = dict(source_event)
        supplied_keys = event.get("sent_dedupe_keys") or []
        if not isinstance(supplied_keys, list):
            raise GuestJourneyError("sent_dedupe_keys must be a list")
        event["sent_dedupe_keys"] = list(
            dict.fromkeys([*supplied_keys, *sorted(claimed_in_batch)])
        )
        decision = evaluate_event(event, root)
        decisions.append(decision)
        if decision["decision"] == "proposal":
            claimed_in_batch.add(str(decision["dedupe_key"]))
    counts = {
        state: sum(item["decision"] == state for item in decisions)
        for state in ("proposal", "manual_review", "skip", "blocked")
    }
    return {
        "schema": "aumara-guest-service-journey-v1",
        "mode": "proposal_only",
        "summary": counts,
        "external_network_calls": 0,
        "guest_messages_sent": 0,
        "booking_mutations": 0,
        "durable_claims_written": 0,
        "decisions": decisions,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=pathlib.Path)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args()
    assert_proposal_guards()
    payload = _load(args.input)
    events = payload.get("events")
    if not isinstance(events, list):
        raise GuestJourneyError("input must contain an events list")
    report = build_report(events)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
