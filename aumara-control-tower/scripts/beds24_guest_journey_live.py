#!/usr/bin/env python3
"""Send approved guest-journey proposals through Beds24 after an atomic claim."""

from __future__ import annotations

import abc
import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import unicodedata
import urllib.error
import urllib.request
from typing import Any

from guest_service_journey import GuestJourneyError, build_report


DEFAULT_POLICY_ROOT = pathlib.Path(__file__).resolve().parents[1] / "policies"
DEFAULT_CLAIM_ROOT = pathlib.Path("/tmp/claims")
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


class FileAtomicClaimBackend(AtomicClaimBackend):
    """Claim with O_CREAT|O_EXCL; safe between processes on one filesystem."""

    def __init__(self, root: pathlib.Path = DEFAULT_CLAIM_ROOT) -> None:
        self.root = pathlib.Path(root)

    def claim_once(self, dedupe_key: str) -> bool:
        digest = hashlib.sha256(dedupe_key.encode("utf-8")).hexdigest()
        try:
            self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
            if not self.root.is_dir():
                raise LiveJourneyError("atomic file claim backend is unavailable")
            claim_path = self.root / f"{digest}.claim"
            flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
            flags |= getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(claim_path, flags, 0o600)
        except FileExistsError:
            return False
        except OSError:
            raise LiveJourneyError("atomic file claim backend failed") from None
        try:
            os.write(descriptor, (digest + "\n").encode("ascii"))
            os.fsync(descriptor)
        except OSError:
            raise LiveJourneyError("atomic file claim persistence failed") from None
        finally:
            os.close(descriptor)
        return True


class DynamoAtomicClaimBackend(AtomicClaimBackend):
    """Claim with one DynamoDB conditional PutItem operation."""

    def __init__(self, table_name: str, client: Any) -> None:
        if not table_name.strip():
            raise LiveJourneyError("DynamoDB claim table is missing")
        self.table_name = table_name.strip()
        self.client = client

    def claim_once(self, dedupe_key: str) -> bool:
        digest = hashlib.sha256(dedupe_key.encode("utf-8")).hexdigest()
        try:
            self.client.put_item(
                TableName=self.table_name,
                Item={
                    "claimKey": {"S": digest},
                    "claimedAt": {
                        "S": dt.datetime.now(dt.timezone.utc).isoformat()
                    },
                },
                ConditionExpression="attribute_not_exists(claimKey)",
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
    table_name = str(values.get("BEDS24_CLAIM_DYNAMODB_TABLE") or "").strip()
    if table_name:
        try:
            import boto3  # type: ignore[import-not-found]
        except ImportError:
            raise LiveJourneyError("DynamoDB atomic claim backend is unavailable")
        try:
            client = boto3.client("dynamodb")
        except Exception:
            raise LiveJourneyError("DynamoDB atomic claim backend is unavailable") from None
        return DynamoAtomicClaimBackend(table_name, client)
    claim_root = pathlib.Path(
        str(values.get("BEDS24_CLAIM_DIR") or DEFAULT_CLAIM_ROOT)
    )
    return FileAtomicClaimBackend(claim_root)


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
        event_type = str(event.get("event_type") or "").strip().lower()
        if event_type in HARD_BLOCKED_EVENT_TYPES:
            raise LiveJourneyError("hard-blocked lifecycle event in live input")

    try:
        report = build_report(events, policy_root)
    except GuestJourneyError:
        raise LiveJourneyError("guest journey policy rejected live input") from None

    summary = {
        "schema": "aumara-beds24-guest-journey-live-v1",
        "mode": "live_authorized",
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
        booking_ref = str(decision.get("booking_ref") or "").strip()
        dedupe_key = f"{property_key}:{booking_ref.lower()}:{event_type}"
        if decision.get("dedupe_key") != dedupe_key:
            raise LiveJourneyError("proposal dedupe key failed canonical validation")
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
    summary["authenticationGetRequests"] = auth_get_requests
    summary["externalNetworkCalls"] = auth_get_requests + summary["postAttempts"]
    return summary


def _load_events(path: pathlib.Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise LiveJourneyError("live input is unavailable") from None
    events = payload.get("events") if isinstance(payload, dict) else None
    if not isinstance(events, list) or not all(isinstance(item, dict) for item in events):
        raise LiveJourneyError("live input must contain an events array")
    return events


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=pathlib.Path)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args()
    events = _load_events(args.input)
    backend = claim_backend_from_env()
    summary = execute_live(events, claim_backend=backend)
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
    except (LiveJourneyError, GuestJourneyError):
        print("ERROR: live guest journey aborted", file=__import__("sys").stderr)
        raise SystemExit(2)
