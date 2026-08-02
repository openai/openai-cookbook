from __future__ import annotations

import json
import pathlib
import sys
import unittest


SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import beds24_guest_note_sync as worker  # noqa: E402


AUDIT_ENV = {
    "BEDS24_NOTE_MODE": "audit",
    "AUMARA_DISABLE_BOOKING_MUTATIONS": "true",
    "BEDS24_NOTE_CODE": "GUESTREQUEST",
}
LIVE_ENV = {
    "BEDS24_NOTE_MODE": "live",
    "AUMARA_DISABLE_BOOKING_MUTATIONS": "false",
    "AUMARA_LIVE_BOOKING_WRITES_CONFIRMED": "true",
    "AUMARA_BEDS24_NOTE_WRITE_CONFIRMATION": worker.LIVE_CONFIRMATION,
    "BEDS24_NOTE_CODE": "GUESTREQUEST",
    "BEDS24_NOTE_MAX_WRITES": str(worker.MAX_WRITES_CAP),
    "BEDS24_NOTE_MAX_AGE_DAYS": str(worker.MAX_AGE_DAYS),
    "BEDS24_NOTE_POLICY_ID": worker.POLICY_ID,
    "BEDS24_NOTE_POLICY_VERSION": worker.POLICY_VERSION,
}


class FakeClient:
    def __init__(self, messages, bookings, post_response=None, read_back=True):
        self.messages = messages
        self.bookings = bookings
        self.post_response = post_response
        self.read_back = read_back
        self.get_requests = 0
        self.post_requests = 0
        self.payloads = []

    def request_json(self, method, path, body=None):
        if method == "GET":
            self.get_requests += 1
            if path.startswith("/bookings/messages?"):
                return 200, {"data": self.messages}
            if path.startswith("/bookings?"):
                return 200, {"data": self.bookings}
        if method == "POST":
            self.post_requests += 1
            self.payloads.append((path, body))
            response = self.post_response
            if response is None:
                response = [{"success": True} for _ in body]
            if self.read_back and all(item.get("success") is True for item in response):
                by_id = {int(item["id"]): item for item in self.bookings}
                for update in body:
                    target = by_id[int(update["id"])]
                    target.setdefault("infoItems", []).extend(update["infoItems"])
            return 201, response
        raise AssertionError(f"Unexpected request: {method} {path}")


def message(message_id=10, booking_id=20, text="large double bed"):
    return {
        "id": message_id,
        "bookingId": booking_id,
        "propertyId": worker.PROPERTY_ID,
        "source": "guest",
        "message": text,
        "time": "2026-07-27T10:00:00Z",
    }


def booking(booking_id=20, status="confirmed", info_items=None):
    return {
        "id": booking_id,
        "propertyId": worker.PROPERTY_ID,
        "status": status,
        "infoItems": info_items or [],
    }


class NoteSyncTests(unittest.TestCase):
    def test_off_mode_cannot_make_network_requests(self):
        client = FakeClient([message()], [booking()])
        with self.assertRaisesRegex(worker.NoteSyncError, "is off"):
            worker.run(
                client,
                mode="off",
                code="GUESTREQUEST",
                max_age_days=3,
                env={"BEDS24_NOTE_MODE": "off"},
            )
        self.assertEqual(client.get_requests, 0)
        self.assertEqual(client.post_requests, 0)

    def test_audit_mode_requires_booking_kill_switch(self):
        with self.assertRaisesRegex(worker.NoteSyncError, "requires"):
            worker.operating_mode({"BEDS24_NOTE_MODE": "audit"})

    def test_live_mode_requires_both_exact_guards(self):
        with self.assertRaisesRegex(worker.NoteSyncError, "requires"):
            worker.operating_mode({
                "BEDS24_NOTE_MODE": "live",
                "AUMARA_DISABLE_BOOKING_MUTATIONS": "false",
                "BEDS24_NOTE_CODE": "GUESTREQUEST",
            })
        self.assertEqual(worker.operating_mode(LIVE_ENV), "live")

    def test_supported_requests_are_classified_for_notes(self):
        examples = {
            "large double bed": "bed_request",
            "baby cot please": "cot_request",
            "travelling with a dog": "pet_request",
            "is parking available": "parking_request",
            "can we arrive early": "early_checkin",
            "we will arrive late": "late_checkin",
            "can we have late checkout": "late_checkout",
        }
        for text, expected in examples.items():
            with self.subTest(text=text):
                self.assertEqual(
                    worker.classify_event({"body": text}),
                    expected,
                )
                self.assertIsNotNone(worker.proposed_booking_note(expected))

    def test_audit_builds_redacted_candidate_without_post(self):
        client = FakeClient(
            [message(text="guest@example.com wants a large double bed, code 1234")],
            [booking()],
        )
        report = worker.run(
            client,
            mode="audit",
            code="GUESTREQUEST",
            max_age_days=3,
            env=AUDIT_ENV,
        )
        serialized = json.dumps(report)
        self.assertEqual(report["summary"]["noteCandidates"], 1)
        self.assertEqual(report["summary"]["notesWritten"], 0)
        self.assertEqual(report["safety"]["postRequests"], 0)
        self.assertNotIn("guest@example.com", serialized)
        self.assertNotIn("code 1234", serialized)
        self.assertNotIn("noteText", report["events"][0])
        self.assertFalse(report["safety"]["noteTextPersisted"])

    def test_existing_type_is_idempotently_deduplicated(self):
        existing = [{
            "code": "GUESTREQUEST",
            "text": "[AUMARA:BED_REQUEST:old] BED REQUEST — already noted",
        }]
        client = FakeClient([message()], [booking(info_items=existing)])
        report = worker.run(
            client,
            mode="audit",
            code="GUESTREQUEST",
            max_age_days=3,
            env=AUDIT_ENV,
        )
        self.assertEqual(report["summary"]["noteCandidates"], 0)
        self.assertEqual(report["summary"]["duplicates"], 1)

    def test_inactive_booking_is_never_a_candidate(self):
        client = FakeClient([message()], [booking(status="cancelled")])
        report = worker.run(
            client,
            mode="audit",
            code="GUESTREQUEST",
            max_age_days=3,
            env=AUDIT_ENV,
        )
        self.assertEqual(report["summary"]["noteCandidates"], 0)
        self.assertEqual(client.post_requests, 0)

    def test_missing_message_id_requires_manual_review(self):
        client = FakeClient([message(message_id=0)], [booking()])
        report = worker.run(
            client,
            mode="audit",
            code="GUESTREQUEST",
            max_age_days=3,
            env=AUDIT_ENV,
        )
        self.assertEqual(report["summary"]["noteCandidates"], 0)
        self.assertEqual(report["summary"]["manualReview"], 1)

    def test_guarded_live_payload_contains_only_id_and_info_items(self):
        client = FakeClient([message()], [booking()])
        report = worker.run(
            client,
            mode="live",
            code="GUESTREQUEST",
            max_age_days=worker.MAX_AGE_DAYS,
            env=LIVE_ENV,
        )
        self.assertEqual(report["summary"]["notesWritten"], 1)
        self.assertEqual(client.post_requests, 1)
        path, payload = client.payloads[0]
        self.assertEqual(path, "/bookings")
        self.assertEqual(set(payload[0]), {"id", "infoItems"})
        self.assertEqual(set(payload[0]["infoItems"][0]), {"code", "text"})
        self.assertEqual(report["summary"]["notesReadBackVerified"], 1)
        self.assertEqual(client.get_requests, 3)

    def test_failed_live_response_is_not_reported_as_success(self):
        client = FakeClient(
            [message()],
            [booking()],
            post_response=[{"success": False, "errors": [{"message": "no"}]}],
        )
        with self.assertRaisesRegex(worker.NoteSyncError, "incomplete"):
            worker.run(
                client,
                mode="live",
                code="GUESTREQUEST",
                max_age_days=worker.MAX_AGE_DAYS,
                env=LIVE_ENV,
            )

    def test_cot_is_delegated_to_specialized_worker(self):
        client = FakeClient([message(text="baby cot please")], [booking()])
        report = worker.run(
            client,
            mode="live",
            code="GUESTREQUEST",
            max_age_days=worker.MAX_AGE_DAYS,
            env=LIVE_ENV,
        )
        self.assertEqual(report["summary"]["noteCandidates"], 0)
        self.assertEqual(report["summary"]["notesWritten"], 0)
        self.assertEqual(client.post_requests, 0)
        self.assertEqual(
            report["events"][0]["reason"],
            "cot_requires_specialized_worker",
        )

    def test_live_batch_above_cap_is_refused_before_post(self):
        messages = [
            message(message_id=index, booking_id=index, text="large double bed")
            for index in range(1, worker.MAX_WRITES_CAP + 2)
        ]
        bookings = [booking(booking_id=index) for index in range(1, len(messages) + 1)]
        client = FakeClient(messages, bookings)
        with self.assertRaisesRegex(worker.NoteSyncError, "exceeds"):
            worker.run(
                client,
                mode="live",
                code="GUESTREQUEST",
                max_age_days=worker.MAX_AGE_DAYS,
                env=LIVE_ENV,
            )
        self.assertEqual(client.post_requests, 0)

    def test_live_write_requires_exact_get_read_back(self):
        client = FakeClient([message()], [booking()], read_back=False)
        with self.assertRaisesRegex(worker.NoteSyncError, "read-back"):
            worker.run(
                client,
                mode="live",
                code="GUESTREQUEST",
                max_age_days=worker.MAX_AGE_DAYS,
                env=LIVE_ENV,
            )

    def test_new_info_item_does_not_replace_existing_items(self):
        existing = {"id": 88, "code": "KEEP", "text": "existing operational note"}
        client = FakeClient([message()], [booking(info_items=[existing])])
        worker.run(
            client,
            mode="live",
            code="GUESTREQUEST",
            max_age_days=worker.MAX_AGE_DAYS,
            env=LIVE_ENV,
        )
        self.assertIn(existing, client.bookings[0]["infoItems"])


if __name__ == "__main__":
    unittest.main()
