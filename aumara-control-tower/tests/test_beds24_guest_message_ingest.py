from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys
import unittest
import urllib.parse

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import beds24_guest_message_ingest as worker  # noqa: E402


NOW = dt.datetime(2026, 7, 30, 12, 0, tzinfo=dt.timezone.utc)
REDACTION_KEY = "unit-test-redaction-key"


def run_report(client, *, max_age_days=3, now=NOW):
    return worker.run(
        client,
        max_age_days=max_age_days,
        now=now,
        redaction_key=REDACTION_KEY,
    )


class FakeClient:
    def __init__(self, guest=None, host=None, bookings=None):
        self.guest = list(guest or [])
        self.host = list(host or [])
        self.bookings = list(bookings or [])
        self.get_requests = 0
        self.non_get_requests = 0
        self.paths = []

    def request_json(self, method, path):
        self.paths.append((method, path))
        if method != "GET":
            self.non_get_requests += 1
            raise AssertionError("non-GET request")
        self.get_requests += 1
        if path.startswith("/bookings/messages?"):
            query = urllib.parse.parse_qs(urllib.parse.urlparse(path).query)
            source = query["source"][0]
            return 200, {"data": self.guest if source == "guest" else self.host}
        if path.startswith("/bookings?"):
            return 200, {"data": self.bookings}
        raise AssertionError(f"unexpected path {path}")


def message(
    message_id,
    booking_id=90522148,
    source="guest",
    text="large double bed please",
    time="2026-07-30T10:00:00Z",
    property_id=worker.PROPERTY_ID,
):
    return {
        "id": message_id,
        "bookingId": booking_id,
        "propertyId": property_id,
        "source": source,
        "message": text,
        "time": time,
        "guestName": "Private Guest",
        "guestEmail": "guest@example.com",
    }


def booking(booking_id=90522148):
    return {
        "id": booking_id,
        "propertyId": worker.PROPERTY_ID,
        "status": "confirmed",
        "channel": "booking.com",
        "arrival": "2026-08-02",
        "departure": "2026-08-03",
        "guestName": "Private Guest",
        "email": "guest@example.com",
    }


class IngestTests(unittest.TestCase):
    def test_readonly_client_rejects_non_get(self):
        client = worker.Beds24ReadOnlyClient("secret", "https://example.invalid")
        with self.assertRaisesRegex(worker.IngestError, "rejected"):
            client.request_json("POST", "/bookings")
        self.assertEqual(client.get_requests, 0)
        self.assertEqual(client.non_get_requests, 1)

    def test_answered_guest_message_is_paired_with_first_later_host(self):
        client = FakeClient(
            guest=[message(10, text="large double bed")],
            host=[
                message(
                    11,
                    source="host",
                    text="not persisted host reply",
                    time="2026-07-30T10:05:00Z",
                )
            ],
            bookings=[booking()],
        )
        report = run_report(client)
        guest_event = next(
            item for item in report["events"] if item["direction"] == "guest"
        )
        self.assertTrue(guest_event["answered"])
        self.assertEqual(guest_event["responseLagSeconds"], 300)
        self.assertEqual(guest_event["eventType"], "bed_request")
        self.assertFalse(report["conversations"][0]["unanswered"])
        self.assertEqual(report["summary"]["unansweredConversations"], 0)

    def test_latest_guest_message_is_unanswered(self):
        client = FakeClient(
            guest=[
                message(10, time="2026-07-30T09:00:00Z"),
                message(
                    12,
                    text="can we arrive early",
                    time="2026-07-30T11:30:00Z",
                ),
            ],
            host=[
                message(
                    11,
                    source="host",
                    text="first response",
                    time="2026-07-30T09:10:00Z",
                )
            ],
            bookings=[booking()],
        )
        report = run_report(client)
        conversation = report["conversations"][0]
        self.assertTrue(conversation["unanswered"])
        self.assertEqual(conversation["unansweredAgeSeconds"], 1800)
        self.assertEqual(conversation["lastEventType"], "early_checkin")

    def test_artifact_contains_no_raw_message_contact_or_booking_id(self):
        raw = "guest@example.com asks for code 1234 and a large double bed"
        client = FakeClient(
            guest=[message(10, text=raw)],
            host=[],
            bookings=[booking()],
        )
        report = run_report(client)
        serialized = json.dumps(report, ensure_ascii=False)
        self.assertNotIn(raw, serialized)
        self.assertNotIn("guest@example.com", serialized)
        self.assertNotIn("Private Guest", serialized)
        self.assertNotIn("90522148", serialized)
        self.assertNotIn(REDACTION_KEY, serialized)
        self.assertIn(
            worker.keyed_hash(
                REDACTION_KEY, "beds24-booking", 90522148
            ),
            serialized,
        )
        self.assertFalse(report["safety"]["rawGuestMessagePersisted"])
        self.assertFalse(report["safety"]["guestContactDataPersisted"])
        self.assertFalse(report["safety"]["rawBookingIdPersisted"])

    def test_duplicate_message_ids_are_removed(self):
        duplicate = message(10)
        client = FakeClient(
            guest=[duplicate, dict(duplicate)],
            host=[],
            bookings=[booking()],
        )
        report = run_report(client)
        self.assertEqual(report["summary"]["messagesScanned"], 2)
        self.assertEqual(report["summary"]["eventsNormalized"], 1)
        self.assertEqual(report["summary"]["duplicates"], 1)

    def test_missing_identity_or_time_is_manual_review(self):
        broken = message(0)
        broken["time"] = "not-a-time"
        client = FakeClient(guest=[broken], host=[], bookings=[])
        report = run_report(client)
        self.assertEqual(report["summary"]["eventsNormalized"], 0)
        self.assertEqual(report["summary"]["manualReview"], 1)

    def test_outside_property_is_not_normalized(self):
        client = FakeClient(
            guest=[message(10, property_id=999)],
            host=[],
            bookings=[],
        )
        report = run_report(client)
        self.assertEqual(report["summary"]["eventsNormalized"], 0)
        self.assertEqual(report["summary"]["conversations"], 0)

    def test_booking_metadata_is_reduced_to_allowed_fields(self):
        client = FakeClient(
            guest=[message(10)],
            host=[],
            bookings=[booking()],
        )
        report = run_report(client)
        event = report["events"][0]
        self.assertEqual(event["bookingStatus"], "confirmed")
        self.assertEqual(event["channel"], "booking.com")
        self.assertEqual(event["arrival"], "2026-08-02")
        self.assertEqual(event["departure"], "2026-08-03")
        self.assertNotIn("guestName", event)
        self.assertNotIn("email", event)

    def test_run_uses_get_only(self):
        client = FakeClient(guest=[message(10)], host=[], bookings=[booking()])
        report = run_report(client)
        self.assertGreaterEqual(client.get_requests, 3)
        self.assertEqual(client.non_get_requests, 0)
        self.assertEqual(report["safety"]["httpMethods"], ["GET"])
        self.assertEqual(report["safety"]["guestMessagesSent"], 0)
        self.assertEqual(report["safety"]["bookingMutations"], 0)
        self.assertTrue(all(method == "GET" for method, _ in client.paths))

    def test_same_timestamp_uses_message_order_for_unanswered_state(self):
        client = FakeClient(
            guest=[message(12, time="2026-07-30T10:00:00Z")],
            host=[
                message(
                    11,
                    source="host",
                    text="earlier id at same second",
                    time="2026-07-30T10:00:00Z",
                )
            ],
            bookings=[booking()],
        )
        report = run_report(client)
        self.assertTrue(report["conversations"][0]["unanswered"])
        guest_event = next(
            item for item in report["events"] if item["direction"] == "guest"
        )
        self.assertFalse(guest_event["answered"])
        self.assertEqual(
            [item["direction"] for item in report["events"]],
            ["host", "guest"],
        )

    def test_same_timestamp_higher_host_id_answers_guest(self):
        client = FakeClient(
            guest=[message(12, time="2026-07-30T10:00:00Z")],
            host=[
                message(
                    13,
                    source="host",
                    text="later id at same second",
                    time="2026-07-30T10:00:00Z",
                )
            ],
            bookings=[booking()],
        )
        report = run_report(client)
        guest_event = next(
            item for item in report["events"] if item["direction"] == "guest"
        )
        self.assertTrue(guest_event["answered"])
        self.assertEqual(guest_event["responseLagSeconds"], 0)
        self.assertFalse(report["conversations"][0]["unanswered"])
        self.assertEqual(
            [item["direction"] for item in report["events"]],
            ["guest", "host"],
        )

    def test_hmac_identifiers_change_with_redaction_key(self):
        first = worker.keyed_hash(
            "first-key", "beds24-booking", 90522148
        )
        second = worker.keyed_hash(
            "second-key", "beds24-booking", 90522148
        )
        self.assertNotEqual(first, second)
        self.assertNotEqual(
            first,
            worker.keyed_hash(
                "first-key", "beds24-message", 90522148
            ),
        )

    def test_multiple_malformed_messages_are_all_counted(self):
        first = message(0, time="bad-one")
        second = message(0, time="bad-two")
        client = FakeClient(guest=[first, second], host=[], bookings=[])
        report = run_report(client)
        self.assertEqual(report["summary"]["manualReview"], 2)

    def test_fetch_messages_paginates_with_get_only(self):
        class PagingClient:
            def __init__(self):
                self.get_requests = 0
                self.non_get_requests = 0
                self.paths = []

            def request_json(self, method, path):
                self.paths.append((method, path))
                self.get_requests += 1
                query = urllib.parse.parse_qs(urllib.parse.urlparse(path).query)
                page = int(query.get("page", ["1"])[0])
                if page == 1:
                    return 200, {
                        "data": [message(10)],
                        "pages": {"nextPageExists": True},
                    }
                return 200, {
                    "data": [message(11)],
                    "pages": {"nextPageExists": False},
                }

        client = PagingClient()
        rows = worker.fetch_messages(client, source="guest", max_age_days=3)
        self.assertEqual([row["id"] for row in rows], [10, 11])
        self.assertEqual(client.get_requests, 2)
        self.assertTrue(all(method == "GET" for method, _ in client.paths))

    def test_fetch_failure_is_reported_without_fallback_write(self):
        class FailingClient:
            get_requests = 0
            non_get_requests = 0

            def request_json(self, method, path):
                self.get_requests += 1
                return 503, {"error": "unavailable"}

        client = FailingClient()
        with self.assertRaisesRegex(worker.IngestError, "HTTP 503"):
            worker.fetch_messages(client, source="guest", max_age_days=3)
        self.assertEqual(client.non_get_requests, 0)

    def test_invalid_window_fails_before_network(self):
        client = FakeClient()
        with self.assertRaisesRegex(worker.IngestError, "between 1 and 7"):
            run_report(client, max_age_days=0)
        self.assertEqual(client.get_requests, 0)


if __name__ == "__main__":
    unittest.main()
