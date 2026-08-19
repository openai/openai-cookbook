from __future__ import annotations

import datetime as dt
import importlib.util
import json
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "beds24_bed_nonsmoking_note_sync.py"
POLICY = ROOT / "policies" / "elcid-bed-nonsmoking.json"
sys.path.insert(0, str(ROOT / "scripts"))

spec = importlib.util.spec_from_file_location("bed_note_worker", SCRIPT)
worker = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(worker)


TODAY = dt.date(2026, 8, 2)
LIVE_ENV = {
    "BEDS24_BED_NONSMOKING_MODE": "live",
    "AUMARA_DISABLE_BOOKING_MUTATIONS": "false",
    "AUMARA_LIVE_BOOKING_WRITES_CONFIRMED": "true",
    "AUMARA_BEDS24_BED_NONSMOKING_CONFIRMATION": worker.LIVE_CONFIRMATION,
    "BEDS24_BED_NONSMOKING_MAX_WRITES": "10",
    "BEDS24_BED_NONSMOKING_BOOKING_MAX_AGE_DAYS": "7",
    "BEDS24_BED_NONSMOKING_POLICY_ID": worker.POLICY_ID,
    "BEDS24_BED_NONSMOKING_POLICY_VERSION": worker.POLICY_VERSION,
    "BEDS24_BED_NONSMOKING_POLICY_PATH": str(POLICY),
}


def booking(
    booking_id: int,
    *,
    info_items=None,
    room_id=None,
    status="confirmed",
    include_requests=True,
    booking_time="2026-07-30 10:00:00",
):
    return {
        "id": booking_id,
        "propertyId": worker.PROPERTY_ID,
        "roomId": room_id or worker.TWIN_ROOM_ID,
        "status": status,
        "arrival": "2026-09-10",
        "bookingTime": booking_time,
        "guestComments": (
            "BED PREFERENCE:Twin Room with Terrace: 1 extra-large double\n"
            "Non Smoking Requested"
            if include_requests
            else ""
        ),
        "infoItems": info_items or [],
    }


class FakeClient:
    def __init__(self, bookings, *, post_ok=True):
        self.bookings = {int(row["id"]): dict(row) for row in bookings}
        self.post_ok = post_ok
        self.post_requests = 0

    def request_json(self, method, path, body=None):
        if method == "GET" and path.startswith("/bookings?"):
            return 200, {"data": list(self.bookings.values())}
        if method == "POST" and path == "/bookings":
            self.post_requests += 1
            if not self.post_ok:
                return 201, [{"success": False} for _ in body]
            for item in body:
                self.bookings[int(item["id"])]["infoItems"] = item["infoItems"]
            return 201, [{"success": True} for _ in body]
        raise AssertionError(f"Unexpected request: {method} {path}")


class BedNonSmokingNoteTests(unittest.TestCase):
    def test_live_guards_require_exact_ten_write_boundary(self):
        worker.require_live_guards(LIVE_ENV)
        unsafe = dict(LIVE_ENV, BEDS24_BED_NONSMOKING_MAX_WRITES="11")
        with self.assertRaisesRegex(worker.BedNonSmokingNoteError, "exactly ten"):
            worker.require_live_guards(unsafe)
        unsafe_window = dict(
            LIVE_ENV, BEDS24_BED_NONSMOKING_BOOKING_MAX_AGE_DAYS="90"
        )
        with self.assertRaisesRegex(worker.BedNonSmokingNoteError, "7 days"):
            worker.require_live_guards(unsafe_window)

    def test_only_active_future_twin_with_both_requests_is_selected(self):
        valid = booking(1)
        wrong_room = booking(2, room_id=999)
        one_request = booking(3)
        one_request["guestComments"] = "Non Smoking Requested"
        cancelled = booking(4, status="cancelled")
        candidates, audit = worker.plan_notes(
            [valid, wrong_room, one_request, cancelled],
            today=TODAY,
        )
        self.assertEqual([item["bookingId"] for item in candidates], [1])
        self.assertEqual(
            audit,
            [{"action": "pending_write", "reason": "safe_rule_proved"}],
        )

    def test_existing_combined_note_is_deduplicated(self):
        existing = [{"code": "GUESTREQUEST", "text": worker.NOTE_MARKER}]
        candidates, audit = worker.plan_notes(
            [booking(1, info_items=existing)],
            today=TODAY,
        )
        self.assertEqual(candidates, [])
        self.assertEqual(audit[0]["action"], "duplicate")

    def test_old_booking_is_not_part_of_current_queue(self):
        candidates, _ = worker.plan_notes(
            [booking(1, booking_time="2026-07-20 10:00:00")], today=TODAY
        )
        self.assertEqual(candidates, [])

    def test_four_notes_are_written_and_exactly_read_back(self):
        client = FakeClient(
            [booking(value) for value in range(1, 5)],
        )
        report = worker.run(client, today=TODAY, values=LIVE_ENV)
        self.assertEqual(report["summary"]["requestsResolved"], 4)
        self.assertEqual(report["summary"]["notesWritten"], 4)
        self.assertEqual(report["summary"]["notesReadBackVerified"], 4)
        self.assertEqual(report["summary"]["bookingMaxAgeDays"], 7)
        self.assertEqual(report["summary"]["manualReview"], 0)
        self.assertEqual(report["safety"]["guestMessagesSent"], 0)
        self.assertEqual(report["safety"]["bookingFieldsChanged"], ["infoItems"])
        self.assertEqual(client.post_requests, 1)
        durable = json.dumps(report)
        self.assertNotIn('"bookingId"', durable)
        self.assertNotIn(worker.NOTE_MARKER, durable)

    def test_empty_queue_is_a_successful_noop(self):
        client = FakeClient([])
        report = worker.run(client, today=TODAY, values=LIVE_ENV)
        self.assertEqual(report["summary"]["requestsResolved"], 0)
        self.assertEqual(report["summary"]["notesWritten"], 0)
        self.assertEqual(client.post_requests, 0)

    def test_batch_above_cap_refuses_all_writes(self):
        client = FakeClient([booking(value) for value in range(1, 12)])
        with self.assertRaisesRegex(
            worker.BedNonSmokingNoteError, "exceeds the live write limit"
        ):
            worker.run(client, today=TODAY, values=LIVE_ENV)
        self.assertEqual(client.post_requests, 0)

    def test_incomplete_post_result_fails(self):
        client = FakeClient(
            [booking(value) for value in range(1, 5)],
            post_ok=False,
        )
        with self.assertRaisesRegex(
            worker.BedNonSmokingNoteError, "incomplete write result"
        ):
            worker.run(client, today=TODAY, values=LIVE_ENV)


if __name__ == "__main__":
    unittest.main()
