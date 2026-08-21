from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys
import unittest
import urllib.request
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import beds24_guest_journey_shadow as shadow  # noqa: E402
import beds24_guest_journey_live as live  # noqa: E402
import guest_service_journey as journey  # noqa: E402


NOW = dt.datetime(2026, 8, 18, 7, 15, tzinfo=dt.timezone.utc)
PROPERTY_MAP = {101: "aumara", 202: "elcid"}
LIVE_ENV = {
    "BEDS24_GUEST_JOURNEY_MODE": "live",
    "BEDS24_LIVE_SEND_AUTHORIZED": "true",
    "AUMARA_DISABLE_GUEST_SEND": "false",
    "AUMARA_DISABLE_EMAIL_SEND": "true",
    "AUMARA_DISABLE_BOOKING_MUTATIONS": "true",
}


def booking(**updates):
    value = {
        "id": 9001,
        "propertyId": 101,
        "status": "confirmed",
        "arrival": "2026-08-17",
        "departure": "2026-08-20",
        "guestFirstName": "Lucía",
        "language": "es",
    }
    value.update(updates)
    return value


class Beds24GuestJourneyShadowTests(unittest.TestCase):
    def test_shadow_workflow_handles_auth_drift_with_fallback_summary(self) -> None:
        workflow = (
            ROOT.parent / ".github" / "workflows" / "aumara-guest-journey-shadow.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("id: auth_probe", workflow)
        self.assertIn("continue-on-error: true", workflow)
        self.assertIn(
            "steps.auth_probe.outcome == 'success'",
            workflow,
        )
        self.assertIn(
            "steps.auth_probe.outcome != 'success'",
            workflow,
        )
        self.assertIn("externalDependencyUnavailable", workflow)

    def test_shadow_maps_both_property_ids_without_room_filters(self) -> None:
        self.assertEqual(
            shadow.PROPERTY_MAP,
            {324882: "aumara", 324903: "elcid"},
        )
        for property_id in shadow.PROPERTY_MAP:
            query = shadow.booking_query(property_id, NOW.date())
            self.assertIn(f"propertyId={property_id}", query)
            self.assertNotIn("roomId=", query)
        self.assertEqual(
            sum(
                room["physicalUnits"]
                for room in shadow.PROPERTY_ROOM_SCOPE[324882]
            ),
            6,
        )

    def test_guards_are_mandatory(self) -> None:
        with self.assertRaisesRegex(shadow.ShadowFeedError, "shadow guards"):
            shadow.assert_shadow_guards({})

    def test_requester_rejects_non_get_methods(self) -> None:
        requester = shadow.GetOnlyRequester(lambda *args, **kwargs: (200, {}))
        with self.assertRaisesRegex(shadow.ShadowFeedError, "GET only"):
            requester("POST", "/bookings/messages", body={})
        self.assertEqual(requester.get_requests, 0)
        self.assertEqual(requester.non_get_attempts, 1)

    def test_requester_sanitizes_transport_exceptions(self) -> None:
        def delegate(*args, **kwargs):
            raise OSError("failed URL /bookings/messages?bookingId=9001")

        requester = shadow.GetOnlyRequester(delegate)
        with self.assertRaisesRegex(
            shadow.ShadowFeedError, "Beds24 GET request failed"
        ) as captured:
            requester("GET", "/bookings/messages?bookingId=9001")
        self.assertNotIn("9001", str(captured.exception))

    def test_authentication_uses_the_get_only_requester(self) -> None:
        calls = []

        def delegate(method, path, **kwargs):
            calls.append((method, path, kwargs))
            if path == "/authentication/details":
                return 401, {}
            return 200, {"token": "access-token"}

        requester = shadow.GetOnlyRequester(delegate)
        token, api_base = shadow.authenticate_get_only(
            "refresh-token", ("https://api.example.invalid/v2",), requester
        )
        self.assertEqual(token, "access-token")
        self.assertEqual(api_base, "https://api.example.invalid/v2")
        self.assertEqual(requester.get_requests, 2)
        self.assertEqual(requester.non_get_attempts, 0)
        self.assertTrue(all(call[0] == "GET" for call in calls))

    def test_unanswered_guest_message_routes_once_to_manual_review(self) -> None:
        messages = {
            9001: [
                {
                    "source": "guest",
                    "createdAt": "2026-08-18T07:00:00Z",
                    "message": "No tenemos agua caliente",
                }
            ]
        }
        events = shadow.build_shadow_events(
            [booking()], messages, now=NOW, property_map=PROPERTY_MAP
        )
        self.assertEqual(len(events), 1)
        self.assertTrue(events[0]["open_issue"])
        self.assertEqual(events[0]["status_source"], "date_window_shadow_only")
        report = journey.build_report(events, ROOT / "policies")
        self.assertEqual(report["summary"]["manual_review"], 1)
        self.assertEqual(report["summary"]["proposal"], 0)

    def test_host_reply_closes_guest_message_for_shadow_mapping(self) -> None:
        messages = {
            9001: [
                {
                    "source": "guest",
                    "createdAt": "2026-08-18T06:00:00Z",
                    "message": "Can you recommend a beach?",
                },
                {
                    "source": "host",
                    "createdAt": "2026-08-18T06:05:00Z",
                    "message": "Yes",
                },
            ]
        }
        events = shadow.build_shadow_events(
            [booking()], messages, now=NOW, property_map=PROPERTY_MAP
        )
        self.assertEqual([item["event_type"] for item in events], ["first_morning"])
        self.assertFalse(events[0]["open_issue"])

    def test_message_order_uses_absolute_time_across_offsets(self) -> None:
        messages = [
            {
                "source": "host",
                "createdAt": "2026-08-18T09:00:00+02:00",
                "message": "Earlier host reply",
            },
            {
                "source": "guest",
                "createdAt": "2026-08-18T08:30:00Z",
                "message": "Later guest issue",
            },
        ]
        self.assertEqual(
            shadow.unresolved_guest_message(messages), "Later guest issue"
        )

    def test_post_checkin_requires_actual_checkin_timestamp(self) -> None:
        without_actual = shadow.build_shadow_events(
            [booking()], {}, now=NOW, property_map=PROPERTY_MAP
        )
        with_actual = shadow.build_shadow_events(
            [booking(actualCheckInAt="2026-08-17T15:30:00+02:00")],
            {},
            now=NOW,
            property_map=PROPERTY_MAP,
        )
        self.assertEqual(
            [item["event_type"] for item in without_actual], ["first_morning"]
        )
        self.assertEqual(
            [item["event_type"] for item in with_actual],
            ["post_checkin", "first_morning"],
        )

    def test_scheduled_or_date_only_checkin_is_not_actual(self) -> None:
        events = shadow.build_shadow_events(
            [
                booking(
                    checkInAt="2026-08-17T15:00:00+02:00",
                    actualCheckInAt="2026-08-17",
                )
            ],
            {},
            now=NOW,
            property_map=PROPERTY_MAP,
        )
        self.assertEqual([item["event_type"] for item in events], ["first_morning"])

    def test_fetch_is_get_only_and_filters_inactive_rows(self) -> None:
        calls = []

        def requester(method, path, **kwargs):
            calls.append((method, path, kwargs))
            return 200, {
                "data": [
                    booking(),
                    booking(id=9002, status="cancelled"),
                    booking(id=9003, departure="2026-08-18"),
                ]
            }

        rows = shadow.fetch_active_bookings(
            "token", "https://example.invalid", 101, NOW.date(), requester
        )
        self.assertEqual([row["id"] for row in rows], [9001])
        self.assertEqual(calls[0][0], "GET")
        self.assertIn("propertyId=101", calls[0][1])

    def test_summary_contains_no_guest_pii(self) -> None:
        events = shadow.build_shadow_events(
            [booking()], {}, now=NOW, property_map=PROPERTY_MAP
        )
        report = journey.build_report(events, ROOT / "policies")
        summary = shadow.sanitized_summary(report, run_at=NOW)
        encoded = json.dumps(summary, ensure_ascii=False)
        self.assertNotIn("Lucía", encoded)
        self.assertNotIn("9001", encoded)
        self.assertNotIn("No tenemos agua caliente", encoded)
        self.assertFalse(summary["containsGuestPii"])
        self.assertEqual(summary["guestMessagesSent"], 0)
        self.assertEqual(summary["bookingMutations"], 0)
        self.assertEqual(summary["postRequests"], 0)

    def test_summary_rejects_any_shadow_post_attempt(self) -> None:
        report = journey.build_report([], ROOT / "policies")
        with self.assertRaisesRegex(
            shadow.ShadowFeedError, "non-GET attempt"
        ):
            shadow.sanitized_summary(report, run_at=NOW, post_requests=1)

    def test_live_sender_rejects_non_atomic_claim_backend(self) -> None:
        class NonAtomicClaimBackend:
            def claim_once(self, dedupe_key: str) -> bool:
                return True

        with self.assertRaisesRegex(
            live.LiveJourneyError, "atomic claim backend"
        ):
            live.execute_live(
                [],
                claim_backend=NonAtomicClaimBackend(),
                message_client=mock.Mock(),
                env=LIVE_ENV,
                policy_root=ROOT / "policies",
            )

    def test_live_guards_require_guest_send_to_be_explicitly_enabled(self) -> None:
        guarded = {**LIVE_ENV, "AUMARA_DISABLE_GUEST_SEND": "true"}
        with self.assertRaisesRegex(live.LiveJourneyError, "live mode"):
            live.assert_live_guards(guarded)

    def test_live_claim_precedes_post_and_duplicate_is_skipped(self) -> None:
        order = []

        class RecordingClaims(live.AtomicClaimBackend):
            def __init__(self) -> None:
                self.keys = set()

            def claim_once(self, dedupe_key: str) -> bool:
                order.append("claim")
                if dedupe_key in self.keys:
                    return False
                self.keys.add(dedupe_key)
                return True

        class RecordingClient:
            auth_get_requests = 0

            def send_message(self, booking_id: int, message: str) -> None:
                order.append("post")

        events = [
            {
                "property": "aumara",
                "property_id": 324882,
                "booking_ref": "9001",
                "event_type": "post_checkin",
                "status": "checked_in",
                "status_source": "actual_check_in_timestamp",
                "guest_first_name": "Lucía",
                "language": "es",
                "check_in_at": "2026-08-17T15:00:00+02:00",
                "departure_at": "2026-08-20T11:00:00+02:00",
                "now": "2026-08-17T16:30:00+02:00",
                "nights": 3,
                "sent_dedupe_keys": [],
                "last_guest_message": "",
                "open_issue": False,
            }
        ]
        claims = RecordingClaims()
        client = RecordingClient()
        first = live.execute_live(
            events,
            claim_backend=claims,
            message_client=client,
            env=LIVE_ENV,
            policy_root=ROOT / "policies",
        )
        second = live.execute_live(
            events,
            claim_backend=claims,
            message_client=client,
            env=LIVE_ENV,
            policy_root=ROOT / "policies",
        )
        self.assertEqual(order, ["claim", "post", "claim"])
        self.assertEqual(first["messagesSent"], 1)
        self.assertEqual(second["messagesSent"], 0)
        self.assertEqual(second["claimConflicts"], 1)
        self.assertEqual(claims.keys, {"324882:9001:post_checkin"})
        encoded = json.dumps(first, ensure_ascii=False)
        self.assertNotIn("Lucía", encoded)
        self.assertNotIn("9001", encoded)

    def test_live_hard_block_aborts_before_claim_or_post(self) -> None:
        claims = mock.create_autospec(live.AtomicClaimBackend, instance=True)
        client = mock.Mock()
        with self.assertRaisesRegex(live.LiveJourneyError, "hard-blocked"):
            live.execute_live(
                [{"event_type": "checkout_reminder"}],
                claim_backend=claims,
                message_client=client,
                env=LIVE_ENV,
                policy_root=ROOT / "policies",
            )
        claims.claim_once.assert_not_called()
        client.send_message.assert_not_called()

    def test_beds24_live_client_posts_only_official_message_payload(self) -> None:
        captured = {}

        class Response:
            status = 201

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return b'[{"success":true}]'

        def fake_urlopen(request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return Response()

        client = live.Beds24MessageClient("token", "https://api.example.invalid/v2")
        with mock.patch.object(urllib.request, "urlopen", side_effect=fake_urlopen):
            client.send_message(9001, "Hello")
        request = captured["request"]
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.full_url, "https://api.example.invalid/v2/bookings/messages")
        self.assertEqual(
            json.loads(request.data.decode("utf-8")),
            [{"bookingId": 9001, "message": "Hello"}],
        )


if __name__ == "__main__":
    unittest.main()
