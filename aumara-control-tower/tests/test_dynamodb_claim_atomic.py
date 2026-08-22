from __future__ import annotations

import datetime as dt
import pathlib
import subprocess
import sys
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import beds24_guest_journey_live as live  # noqa: E402


NOW = dt.datetime(2026, 8, 18, 7, 15, tzinfo=dt.timezone.utc)
LIVE_ENV = {
    "BEDS24_GUEST_JOURNEY_MODE": "live",
    "BEDS24_LIVE_SEND_AUTHORIZED": "true",
    "AUMARA_DISABLE_GUEST_SEND": "false",
    "AUMARA_DISABLE_EMAIL_SEND": "true",
    "AUMARA_DISABLE_BOOKING_MUTATIONS": "true",
}


def booking(booking_id: int, **updates):
    value = {
        "id": booking_id,
        "propertyId": live.AUMARA_PROPERTY_ID,
        "status": "confirmed",
        "arrival": "2026-08-17",
        "departure": "2026-08-20",
        "guestFirstName": "Fixture",
        "language": "en",
    }
    value.update(updates)
    return value


def live_event(**updates):
    value = {
        "property": "aumara",
        "property_id": live.AUMARA_PROPERTY_ID,
        "booking_ref": "9001",
        "event_type": "post_checkin",
        "status": "checked_in",
        "status_source": "actual_check_in_timestamp",
        "guest_first_name": "Fixture",
        "language": "en",
        "check_in_at": "2026-08-17T15:00:00+02:00",
        "departure_at": "2026-08-20T11:00:00+02:00",
        "now": "2026-08-17T16:30:00+02:00",
        "nights": 3,
        "sent_dedupe_keys": [],
        "last_guest_message": "",
        "open_issue": False,
    }
    value.update(updates)
    return value


class ConditionalClaimFailed(Exception):
    response = {"Error": {"Code": "ConditionalCheckFailedException"}}


class RecordingDynamoClient:
    def __init__(self) -> None:
        self.claimed: set[str] = set()
        self.calls: list[dict] = []

    def put_item(self, **kwargs) -> None:
        self.calls.append(kwargs)
        key = kwargs["Item"]["dedupe_key"]["S"]
        if key in self.claimed:
            raise ConditionalClaimFailed()
        self.claimed.add(key)


class DynamoClaimAtomicTests(unittest.TestCase):
    def test_double_claim_is_one_atomic_put_and_then_conflict(self) -> None:
        client = RecordingDynamoClient()
        backend = live.DynamoAtomicClaimBackend(
            live.DYNAMODB_TABLE_NAME,
            client,
            clock=lambda: NOW,
        )
        key = "324882:abc123:post_checkin"

        self.assertTrue(backend.claim_once(key))
        self.assertFalse(backend.claim_once(key))

        first = client.calls[0]
        self.assertEqual(first["TableName"], "aumara-guest-journey-claims")
        self.assertEqual(first["ConditionExpression"], "attribute_not_exists(dedupe_key)")
        self.assertEqual(first["Item"]["dedupe_key"], {"S": key})
        self.assertEqual(first["Item"]["created_at"], {"S": NOW.isoformat()})
        self.assertEqual(
            first["Item"]["ttl"],
            {"N": str(int(NOW.timestamp()) + 7 * 24 * 60 * 60)},
        )

    def test_claim_backend_has_no_local_file_fallback(self) -> None:
        self.assertFalse(hasattr(live, "FileAtomicClaimBackend"))
        with self.assertRaisesRegex(live.LiveJourneyError, "DynamoDB"):
            live.claim_backend_from_env({})

    def test_dynamodb_error_aborts_before_post(self) -> None:
        client = mock.Mock()
        client.put_item.side_effect = RuntimeError("access denied")
        backend = live.DynamoAtomicClaimBackend(
            live.DYNAMODB_TABLE_NAME,
            client,
            clock=lambda: NOW,
        )
        message_client = mock.Mock()
        with self.assertRaisesRegex(live.LiveJourneyError, "atomic claim failed"):
            live.execute_live(
                [live_event()],
                claim_backend=backend,
                message_client=message_client,
                env=LIVE_ENV,
                policy_root=ROOT / "policies",
            )
        message_client.send_message.assert_not_called()

    def test_aumara_property_fetch_returns_all_six_without_room_filter(self) -> None:
        calls = []

        def requester(method, path, **kwargs):
            calls.append((method, path, kwargs))
            return 200, {"data": [booking(index) for index in range(1, 7)]}

        rows = live.fetch_aumara_canary_bookings(
            "token",
            "https://example.invalid/v2",
            NOW.date(),
            requester,
        )
        self.assertEqual(len(rows), 6)
        self.assertEqual(live.AUMARA_CANARY_PHYSICAL_UNITS, 6)
        self.assertEqual(
            sum(item["physicalUnits"] for item in live.AUMARA_CANARY_ROOM_SCOPE),
            6,
        )
        self.assertEqual(calls[0][0], "GET")
        self.assertIn("propertyId=324882", calls[0][1])
        self.assertNotIn("roomId=", calls[0][1])

    def test_elcid_is_rejected_before_claim_or_network(self) -> None:
        with mock.patch.object(live, "claim_backend_from_env") as backend:
            with self.assertRaisesRegex(live.LiveJourneyError, "only AUMARA"):
                live.run_aumara_canary(324903, env=LIVE_ENV)
        backend.assert_not_called()

    def test_live_event_requires_actual_checkin_evidence(self) -> None:
        claim_backend = mock.create_autospec(
            live.AtomicClaimBackend, instance=True
        )
        message_client = mock.Mock()
        with self.assertRaisesRegex(live.LiveJourneyError, "check-in evidence"):
            live.execute_live(
                [live_event(status_source="date_window_shadow_only")],
                claim_backend=claim_backend,
                message_client=message_client,
                env=LIVE_ENV,
                policy_root=ROOT / "policies",
            )
        claim_backend.claim_once.assert_not_called()
        message_client.send_message.assert_not_called()

    def test_canary_event_builder_skips_booking_without_actual_checkin(self) -> None:
        events = live.build_aumara_canary_events(
            [
                booking(1),
                booking(2, actualCheckInAt="2026-08-17T15:00:00+02:00"),
            ],
            {},
            now=NOW,
        )
        self.assertTrue(events)
        self.assertEqual({event["booking_ref"] for event in events}, {"2"})
        self.assertTrue(
            all(
                event["status_source"] == "actual_check_in_timestamp"
                and event["property_id"] == live.AUMARA_PROPERTY_ID
                for event in events
            )
        )

    def test_live_workflow_is_manual_aumara_only(self) -> None:
        workflow = (
            ROOT.parent / ".github" / "workflows" / "aumara-guest-journey-live.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", workflow)
        self.assertNotIn("schedule:", workflow)
        self.assertIn("environment: Production", workflow)
        self.assertIn("BEDS24_GUEST_JOURNEY_MODE: live", workflow)
        self.assertIn('BEDS24_LIVE_SEND_AUTHORIZED: "true"', workflow)
        self.assertIn('AUMARA_DISABLE_GUEST_SEND: "false"', workflow)
        self.assertIn("--property 324882", workflow)
        self.assertNotIn("324903", workflow)
        self.assertIn("secrets.BEDS24_REFRESH_CREDENTIAL", workflow)
        self.assertIn("secrets.AWS_ACCESS_KEY_ID", workflow)
        self.assertIn("secrets.AWS_SECRET_ACCESS_KEY", workflow)
        self.assertIn("secrets.DYNAMODB_TABLE", workflow)
        self.assertIn("python -m pip install --upgrade pip boto3", workflow)
        self.assertNotIn("pip install -r requirements.txt", workflow)

    def test_aumara_nominalia_workflow_has_host_and_user_fallbacks(self) -> None:
        workflow = (
            ROOT.parent / ".github" / "workflows" / "deploy-aumara-nominalia-v2.yml"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "FTP_HOST: ${{ secrets.NOMINALIA_FTP_HOST || vars.NOMINALIA_FTP_HOST || 'elcidt.ftp.tb-hosting.com' }}",
            workflow,
        )
        self.assertIn(
            "FTP_USER: ${{ secrets.NOMINALIA_FTP_USER || vars.NOMINALIA_FTP_USER || 'elcidspaincom@elcidspaincom' }}",
            workflow,
        )
        self.assertIn(
            "FTP_PASSWORD: ${{ secrets.NOMINALIA_FTP_PASSWORD || secrets.NOMINALIAFTPPASSWORD }}",
            workflow,
        )

    def test_photo_sync_discovery_fails_only_on_secret_name_matching(self) -> None:
        workflow = (
            ROOT.parent / ".github" / "workflows" / "beds24-photo-sync-discovery.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("receipt['status']='AMBIGUOUS_MATCH'", workflow)
        self.assertIn("receipt['status']='MISSING_MATCH'", workflow)
        self.assertIn("exit_code=2", workflow)
        self.assertIn("receipt['status']='TOKEN_EXCHANGE_FAILED'", workflow)
        self.assertIn("receipt['status']='LIVE_CONTENT_READ_OK' if 200 <= status < 300 else 'LIVE_CONTENT_READ_FAILED'", workflow)
        self.assertNotIn("exit_code=3", workflow)

    def test_photo_vault_dispatcher_accepts_owner_retry_comment(self) -> None:
        workflow = (
            ROOT.parent
            / ".github"
            / "workflows"
            / "beds24-live-recovery-dispatch-controller.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("issue_comment:", workflow)
        self.assertIn("types: [created]", workflow)
        self.assertIn("github.event.comment.user.login == 'elcidspain'", workflow)
        self.assertIn(
            "contains(github.event.comment.body, 'run Beds24 photo vault sync')",
            workflow,
        )
        self.assertIn(
            "'AUMARA control: run Beds24 photo vault sync':'beds24-photo-sync-vault-controller.yml'",
            workflow,
        )

    def test_photo_vault_controller_accepts_registered_retry_title(self) -> None:
        workflow = (
            ROOT.parent
            / ".github"
            / "workflows"
            / "beds24-photo-sync-vault-controller.yml"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "github.event.issue.title == 'AUMARA control: run Beds24 photo vault sync'",
            workflow,
        )

    def test_shadow_workflow_tolerates_auth_drift_with_degraded_summary(self) -> None:
        workflow = (
            ROOT.parent / ".github" / "workflows" / "aumara-guest-journey-shadow.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("auth-error.log", workflow)
        self.assertIn(
            'grep -q "Beds24 authentication failed with HTTP status"',
            workflow,
        )
        self.assertIn('"reasons": {"beds24_auth_unavailable": 1}', workflow)
        self.assertIn('"authStatus": "unavailable"', workflow)
        self.assertIn("/tmp/aumara-guest-journey-shadow/summary.json", workflow)

    def test_documented_module_entrypoint_resolves(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "aumara_control_tower.scripts.beds24_guest_journey_live",
                "--help",
            ],
            cwd=ROOT.parent,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--property", result.stdout)


if __name__ == "__main__":
    unittest.main()
