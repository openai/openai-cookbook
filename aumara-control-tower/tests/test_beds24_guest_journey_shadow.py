from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import beds24_guest_journey_shadow as shadow  # noqa: E402
import guest_service_journey as journey  # noqa: E402


NOW = dt.datetime(2026, 8, 18, 7, 15, tzinfo=dt.timezone.utc)
PROPERTY_MAP = {101: "aumara", 202: "elcid"}


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
    def test_shadow_maps_both_property_ids_without_room_filters(self) -> None:
        self.assertEqual(
            shadow.PROPERTY_MAP,
            {324882: "aumara", 324903: "elcid"},
        )
        for property_id in shadow.PROPERTY_MAP:
            query = shadow.booking_query(property_id, NOW.date())
            self.assertIn(f"propertyId={property_id}", query)
            self.assertNotIn("roomId=", query)

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


if __name__ == "__main__":
    unittest.main()
