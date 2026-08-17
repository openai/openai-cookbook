#!/usr/bin/env python3
"""Send approved guest-journey proposals through Beds24 after an atomic claim."""

from __future__ import annotations

import abc
import argparse
import datetime as dt
import json
import os
import pathlib
import unicodedata
import urllib.error
import urllib.request
from typing import Any, Callable

try:
    from .guest_service_journey import GuestJourneyError, build_report
except ImportError:  # Direct script execution remains supported.
    from guest_service_journey import GuestJourneyError, build_report


DEFAULT_POLICY_ROOT = pathlib.Path(__file__).resolve().parents[1] / "policies"
AUMARA_PROPERTY_ID = 324882
PROPERTY_MAP_LIVE = {AUMARA_PROPERTY_ID: "aumara"}
AUMARA_CANARY_ROOM_SCOPE = (
    {"name": "SL", "physicalUnits": 4},
    {"name": "Chalet Super", "physicalUnits": 2},
)
AUMARA_CANARY_PHYSICAL_UNITS = 6
DYNAMODB_TABLE_NAME = "aumara-guest-journey-claims"
CLAIM_TTL_SECONDS = 7 * 24 * 60 * 60
HARD_BLOCKED_EVENT_TYPES = frozenset(
    {"checkout_reminder", "departure_deadline", "vacate_request"}
)
SENDABLE_EVENT_TYPES = frozenset({"post_checkin", "first_morning"})
LIVE_GUARDS = {
    "BEDS24_GUEST_JOURNEY_MODE": "live",
    "BEDS24_LIVE_SEND_AUTHORIZED": "true",
    "AUMARA_DISABLE_GUEST_SEND": "false",
    "AUMARA_DISABLE_EMAIL_SEND": "true",
    "AUMARA_DISABLE_BOOKING_MUTATIONS": "true",
}
FORBIDDEN_MESSAGE_MARKERS = (
    "rating",
    "review",
    "stars",
    "resena",
    "valoracion",
    "etoiles",
    "bewertung",
    "sterne",
    "beoordeling",
    "recensie",
    "sterren",
    "respond within",
    "reply within",
    "answer within",
    "respond in",
    "reply in",
    "responderemos en",
    "repondons dans",
    "repondrons dans",
    "antworten innerhalb",
    "reageren binnen",
    "mattress",
    "colchon",
    "matelas",
    "matratze",
    "matras",
    "linen",
    "sheets",
    "ropa de cama",
    "linge de lit",
    "bettwasche",
    "beddengoed",
    "satin",
    "saten",
    "satijn",
)


class LiveJourneyError(RuntimeError):
    """Raised when a live send cannot preserve every required guard."""


class AtomicClaimBackend(abc.ABC):
    """Only implementations with a single atomic create operation are accepted."""

    @abc.abstractmethod
    def claim_once(self, dedupe_key: str) -> bool:
        """Return true exactly once for a dedupe key."""


class DynamoAtomicClaimBackend(AtomicClaimBackend):
    """Claim with one DynamoDB conditional PutItem operation."""

    def __init__(
        self,
        table_name: str,
        client: Any,
        *,
        clock: Callable[[], dt.datetime] | None = None,
    ) -> None:
        if table_name.strip() != DYNAMODB_TABLE_NAME:
            raise LiveJourneyError("DynamoDB claim table is not authorized")
        self.table_name = DYNAMODB_TABLE_NAME
        self.client = client
        self.clock = clock or (lambda: dt.datetime.now(dt.timezone.utc))

    def claim_once(self, dedupe_key: str) -> bool:
        if not dedupe_key.strip():
            raise LiveJourneyError("DynamoDB dedupe key is missing")
        now = self.clock()
        if now.tzinfo is None:
            raise LiveJourneyError("DynamoDB claim clock must include a timezone")
        now_utc = now.astimezone(dt.timezone.utc)
        ttl = int(now_utc.timestamp()) + CLAIM_TTL_SECONDS
        try:
            self.client.put_item(
                TableName=self.table_name,
                Item={
                    "dedupe_key": {"S": dedupe_key},
                    "created_at": {"S": now_utc.isoformat()},
                    "ttl": {"N": str(ttl)},
                },
                ConditionExpression="attribute_not_exists(dedupe_key)",
            )
        except Exception as exc:
            response = getattr(exc, "response", {})
            code = str(
                (response.get("Error") or {}).get("Code")
                if isinstance(response, dict)
                else ""
            )
            if code == "ConditionalCheckFailedException":
                return False
            raise LiveJourneyError("DynamoDB atomic claim failed") from None
        return True


class Beds24MessageClient:
    """The only network mutation boundary in this module."""

    def __init__(self, token: str, api_base: str, *, auth_get_requests: int = 0) -> None:
        self.token = str(token or "").strip()
        self.api_base = str(api_base or "").rstrip("/")
        self.auth_get_requests = int(auth_get_requests)
        if not self.token or not self.api_base.startswith("https://"):
            raise LiveJourneyError("Beds24 live client configuration is invalid")

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Beds24MessageClient":
        values = env if env is not None else os.environ
        try:
            from .beds24_elcid_studio_audit import API_BASES, request_json
            from .beds24_guest_journey_shadow import (
                GetOnlyRequester,
                authenticate_get_only,
            )
        except ImportError:  # Direct script execution remains supported.
            from beds24_elcid_studio_audit import API_BASES, request_json
            from beds24_guest_journey_shadow import (
                GetOnlyRequester,
                authenticate_get_only,
            )

        requester = GetOnlyRequester(request_json)
        token, api_base = authenticate_get_only(
            values.get("BEDS24_REFRESH_TOKEN", ""), API_BASES, requester
        )
        return cls(
            token,
            api_base,
            auth_get_requests=requester.get_requests,
        )

    def send_message(self, booking_id: int, message: str) -> None:
        payload = json.dumps(
            [{"bookingId": booking_id, "message": message}],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.api_base}/bookings/messages",
            data=payload,
            headers={
                "accept": "application/json",
                "content-type": "application/json",
                "token": self.token,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                raw = response.read().decode("utf-8", "replace")
                status = response.status
        except urllib.error.HTTPError as exc:
            raise LiveJourneyError(
                f"Beds24 message POST failed with HTTP {exc.code}"
            ) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise LiveJourneyError("Beds24 message POST transport failed") from None
        try:
            result = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            result = None
        if (
            status != 201
            or not isinstance(result, list)
            or len(result) != 1
            or not isinstance(result[0], dict)
            or result[0].get("success") is not True
        ):
            raise LiveJourneyError("Beds24 message POST was not confirmed")


def assert_live_guards(env: dict[str, str] | None = None) -> None:
    values = env if env is not None else os.environ
    missing = [
        name
        for name, expected in LIVE_GUARDS.items()
        if str(values.get(name) or "").strip().lower() != expected
    ]
    if missing:
        raise LiveJourneyError(
            "refusing live mode without guards: " + ", ".join(missing)
        )


def claim_backend_from_env(
    env: dict[str, str] | None = None,
) -> AtomicClaimBackend:
    values = env if env is not None else os.environ
    table_name = str(values.get("DYNAMODB_TABLE") or "").strip()
    if table_name != DYNAMODB_TABLE_NAME:
        raise LiveJourneyError("authorized DynamoDB claim table is required")
    required_credentials = ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY")
    if any(not str(values.get(name) or "").strip() for name in required_credentials):
        raise LiveJourneyError("AWS claim credentials are missing")
    region = str(
        values.get("AWS_REGION") or values.get("AWS_DEFAULT_REGION") or ""
    ).strip()
    if not region:
        raise LiveJourneyError("AWS claim region is missing")
    try:
        import boto3  # type: ignore[import-not-found]
    except ImportError:
        raise LiveJourneyError("DynamoDB atomic claim backend is unavailable")
    try:
        client = boto3.client("dynamodb", region_name=region)
    except Exception:
        raise LiveJourneyError("DynamoDB atomic claim backend is unavailable") from None
    return DynamoAtomicClaimBackend(table_name, client)


def _normalized_text(value: Any) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or "").casefold())
    return "".join(
        character for character in normalized if not unicodedata.combining(character)
    )


def _assert_message_allowed(message: Any) -> str:
    text = str(message or "").strip()
    if not text:
        raise LiveJourneyError("proposal message is empty")
    normalized = _normalized_text(text)
    if any(marker in normalized for marker in FORBIDDEN_MESSAGE_MARKERS):
        raise LiveJourneyError("proposal message violates the live content boundary")
    return text


def _booking_id(value: Any) -> int:
    text = str(value or "").strip()
    if not text.isdigit() or int(text) <= 0:
        raise LiveJourneyError("proposal booking reference is not a Beds24 id")
    return int(text)


def execute_live(
    events: list[dict[str, Any]],
    *,
    claim_backend: AtomicClaimBackend,
    message_client: Any | None = None,
    env: dict[str, str] | None = None,
    policy_root: pathlib.Path = DEFAULT_POLICY_ROOT,
) -> dict[str, Any]:
    """Build proposals, atomically claim each key, then send at most once."""
    assert_live_guards(env)
    if not isinstance(claim_backend, AtomicClaimBackend):
        raise LiveJourneyError("live mode requires an atomic claim backend")
    for event in events:
        if not isinstance(event, dict):
            raise LiveJourneyError("live input event is invalid")
        event_type = str(event.get("event_type") or "").strip().lower()
        if event_type in HARD_BLOCKED_EVENT_TYPES:
            raise LiveJourneyError("hard-blocked lifecycle event in live input")
        if str(event.get("property") or "").strip().lower() != "aumara":
            raise LiveJourneyError("live input is outside the AUMARA canary")
        supplied_property_id = event.get("property_id", AUMARA_PROPERTY_ID)
        try:
            property_id = int(supplied_property_id)
        except (TypeError, ValueError):
            raise LiveJourneyError("live property id is invalid") from None
        if property_id != AUMARA_PROPERTY_ID:
            raise LiveJourneyError("live property is outside the AUMARA canary")
        if event.get("status_source") != "actual_check_in_timestamp":
            raise LiveJourneyError("live event lacks verified check-in evidence")

    try:
        report = build_report(events, policy_root)
    except GuestJourneyError:
        raise LiveJourneyError("guest journey policy rejected live input") from None

    summary = {
        "schema": "aumara-beds24-guest-journey-live-v1",
        "mode": "live_authorized",
        "propertyId": AUMARA_PROPERTY_ID,
        "physicalUnitsInScope": AUMARA_CANARY_PHYSICAL_UNITS,
        "proposals": int(report["summary"]["proposal"]),
        "manualReview": int(report["summary"]["manual_review"]),
        "skippedByPolicy": int(report["summary"]["skip"]),
        "blockedByPolicy": int(report["summary"]["blocked"]),
        "claimsWritten": 0,
        "claimConflicts": 0,
        "postAttempts": 0,
        "messagesSent": 0,
        "sendFailures": 0,
        "bookingMutations": 0,
        "gmailSends": 0,
        "whatsappSends": 0,
        "containsGuestPii": False,
        "aborted": False,
    }

    proposals = [
        decision
        for decision in report["decisions"]
        if decision.get("decision") == "proposal"
    ]
    client = message_client
    if proposals and client is None:
        try:
            client = Beds24MessageClient.from_env(env)
        except Exception:
            raise LiveJourneyError("Beds24 live authentication failed") from None

    for decision in proposals:
        event_type = str(decision.get("event_type") or "").strip().lower()
        if event_type in HARD_BLOCKED_EVENT_TYPES or event_type not in SENDABLE_EVENT_TYPES:
            raise LiveJourneyError("non-sendable lifecycle event reached live boundary")
        property_key = str(decision.get("property") or "").strip().lower()
        if property_key != PROPERTY_MAP_LIVE[AUMARA_PROPERTY_ID]:
            raise LiveJourneyError("proposal escaped the AUMARA canary")
        booking_ref = str(decision.get("booking_ref") or "").strip()
        policy_dedupe_key = f"{property_key}:{booking_ref.lower()}:{event_type}"
        if decision.get("dedupe_key") != policy_dedupe_key:
            raise LiveJourneyError("proposal dedupe key failed canonical validation")
        dedupe_key = (
            f"{AUMARA_PROPERTY_ID}:{booking_ref.lower()}:{event_type}"
        )
        booking_id = _booking_id(booking_ref)
        message = _assert_message_allowed(decision.get("message"))

        if not claim_backend.claim_once(dedupe_key):
            summary["claimConflicts"] += 1
            continue
        summary["claimsWritten"] += 1

        summary["postAttempts"] += 1
        try:
            client.send_message(booking_id, message)
        except Exception:
            summary["sendFailures"] += 1
            summary["aborted"] = True
            break
        summary["messagesSent"] += 1

    auth_get_requests = int(getattr(client, "auth_get_requests", 0)) if client else 0
    summary["beds24GetRequests"] = auth_get_requests
    summary["externalNetworkCalls"] = auth_get_requests + summary["postAttempts"]
    return summary


def fetch_aumara_canary_bookings(
    token: str,
    api_base: str,
    today: dt.date,
    requester: Callable[..., tuple[int, object]],
) -> list[dict[str, Any]]:
    """Fetch every active AUMARA booking by property, never by room."""
    try:
        from .beds24_guest_journey_shadow import fetch_active_bookings
    except ImportError:  # Direct script execution remains supported.
        from beds24_guest_journey_shadow import fetch_active_bookings

    try:
        bookings = fetch_active_bookings(
            token,
            api_base,
            AUMARA_PROPERTY_ID,
            today,
            requester,
        )
    except Exception:
        raise LiveJourneyError("AUMARA booking read failed") from None
    booking_ids = [_booking_id(item.get("id")) for item in bookings]
    if len(booking_ids) != len(set(booking_ids)):
        raise LiveJourneyError("AUMARA booking feed contains duplicates")
    if len(bookings) > AUMARA_CANARY_PHYSICAL_UNITS:
        raise LiveJourneyError("AUMARA active booking count exceeds canary scope")
    return bookings


def build_aumara_canary_events(
    bookings: list[dict[str, Any]],
    messages_by_booking: dict[int, list[dict[str, Any]]],
    *,
    now: dt.datetime,
) -> list[dict[str, Any]]:
    """Build live events only for bookings with an actual check-in timestamp."""
    try:
        from .beds24_guest_journey_shadow import (
            _actual_check_in,
            build_shadow_events,
        )
    except ImportError:  # Direct script execution remains supported.
        from beds24_guest_journey_shadow import (
            _actual_check_in,
            build_shadow_events,
        )

    actual_check_ins: dict[int, dt.datetime] = {}
    verified_bookings: list[dict[str, Any]] = []
    for booking in bookings:
        try:
            property_id = int(booking.get("propertyId") or 0)
        except (TypeError, ValueError):
            raise LiveJourneyError("booking property id is invalid") from None
        if property_id != AUMARA_PROPERTY_ID:
            raise LiveJourneyError("booking escaped the AUMARA canary")
        booking_id = _booking_id(booking.get("id"))
        actual_check_in = _actual_check_in(booking)
        if actual_check_in is None:
            continue
        actual_check_ins[booking_id] = actual_check_in
        verified_bookings.append(booking)

    try:
        events = build_shadow_events(
            verified_bookings,
            messages_by_booking,
            now=now,
            property_map=PROPERTY_MAP_LIVE,
        )
    except Exception:
        raise LiveJourneyError("AUMARA event mapping failed") from None
    for event in events:
        booking_id = _booking_id(event.get("booking_ref"))
        actual_check_in = actual_check_ins.get(booking_id)
        if actual_check_in is None:
            raise LiveJourneyError("live event lost verified check-in evidence")
        event.update(
            property_id=AUMARA_PROPERTY_ID,
            status="checked_in",
            status_source="actual_check_in_timestamp",
            check_in_at=actual_check_in.isoformat(),
        )
    return events


def read_aumara_canary_state(
    env: dict[str, str],
    *,
    now: dt.datetime | None = None,
) -> tuple[list[dict[str, Any]], Beds24MessageClient, int]:
    """Read the AUMARA property and recent messages through GET-only guards."""
    try:
        from .beds24_elcid_studio_audit import API_BASES, request_json
        from .beds24_guest_journey_shadow import (
            MADRID,
            GetOnlyRequester,
            authenticate_get_only,
            fetch_messages,
        )
    except ImportError:  # Direct script execution remains supported.
        from beds24_elcid_studio_audit import API_BASES, request_json
        from beds24_guest_journey_shadow import (
            MADRID,
            GetOnlyRequester,
            authenticate_get_only,
            fetch_messages,
        )

    requester = GetOnlyRequester(request_json)
    try:
        token, api_base = authenticate_get_only(
            env.get("BEDS24_REFRESH_TOKEN", ""), API_BASES, requester
        )
    except Exception:
        raise LiveJourneyError("Beds24 live authentication failed") from None
    run_at = now or dt.datetime.now(dt.timezone.utc)
    today = run_at.astimezone(MADRID).date()
    bookings = fetch_aumara_canary_bookings(
        token, api_base, today, requester
    )
    try:
        messages = {
            _booking_id(booking.get("id")): fetch_messages(
                token,
                api_base,
                _booking_id(booking.get("id")),
                requester,
            )
            for booking in bookings
        }
    except Exception:
        raise LiveJourneyError("AUMARA message read failed") from None
    events = build_aumara_canary_events(bookings, messages, now=run_at)
    if requester.non_get_attempts:
        raise LiveJourneyError("AUMARA live reader recorded a non-GET attempt")
    client = Beds24MessageClient(
        token,
        api_base,
        auth_get_requests=requester.get_requests,
    )
    return events, client, len(bookings)


def run_aumara_canary(
    property_id: int,
    *,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Execute one manually authorized AUMARA-only canary run."""
    values = dict(env if env is not None else os.environ)
    assert_live_guards(values)
    if property_id != AUMARA_PROPERTY_ID:
        raise LiveJourneyError("only AUMARA property 324882 is authorized")
    backend = claim_backend_from_env(values)
    events, client, bookings_read = read_aumara_canary_state(values)
    summary = execute_live(
        events,
        claim_backend=backend,
        message_client=client,
        env=values,
    )
    summary["bookingsRead"] = bookings_read
    summary["verifiedCheckInEvents"] = len(events)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--property", required=True, type=int)
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args()
    summary = run_aumara_canary(args.property)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(summary, sort_keys=True))
    return 2 if summary["aborted"] else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        print("ERROR: live guest journey aborted", file=__import__("sys").stderr)
        raise SystemExit(2)
