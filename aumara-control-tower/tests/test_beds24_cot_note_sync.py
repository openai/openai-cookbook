from __future__ import annotations

import datetime as dt
import pathlib
import re
import sys
import unittest


SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import beds24_cot_note_sync as worker  # noqa: E402


PRIMARY_BOOKING_ID = 91000001
SECONDARY_BOOKING_ID = 91000002
TODAY = dt.date(2026, 7, 30)


LIVE_ENV = {
    "BEDS24_COT_NOTE_MODE": "live",
    "AUMARA_DISABLE_BOOKING_MUTATIONS": "false",
    "AUMARA_LIVE_BOOKING_WRITES_CONFIRMED": "true",
    "AUMARA_BEDS24_COT_WRITE_CONFIRMATION": worker.LIVE_CONFIRMATION,
    "BEDS24_COT_NOTE_MAX_WRITES": "5",
    "BEDS24_COT_NOTE_MAX_AGE_DAYS": "7",
    "BEDS24_COT_NOTE_POLICY_ID": worker.POLICY_ID,
    "BEDS24_COT_NOTE_POLICY_VERSION": worker.POLICY_VERSION,
}


def regression_group():
    shared = {
        "propertyId": worker.PROPERTY_ID,
        "roomId": worker.TWIN_ROOM_ID,
        "status": "confirmed",
        "masterId": PRIMARY_BOOKING_ID,
        "bookingTime": "2026-07-29 10:00:00",
        "guestComments": (
            "En la triple una cuna que tendrá 8 meses mi hija, gracias. "
            "Habitaciones juntas y no fumadores."
        ),
        "infoItems": [],
    }
    return [
        {
            **shared,
            "id": PRIMARY_BOOKING_ID,
            "numAdult": 2,
            "numChild": 1,
        },
        {
            **shared,
            "id": SECONDARY_BOOKING_ID,
            "numAdult": 2,
            "numChild": 0,
        },
    ]


class FakeClient:
    def __init__(self, bookings, *, post_success=True):
        self.bookings = bookings
        self.post_success = post_success
        self.get_requests = 0
        self.post_requests = 0
        self.posted = []

    def request_json(self, method, path, body=None):
        if method == "GET":
            self.get_requests += 1
            if path.startswith("/bookings?") and "id=" not in path:
                return 200, {"data": self.bookings}
            if path.startswith("/bookings?") and "id=" in path:
                ids = {
                    int(value)
                    for value in re.findall(r"(?:[?&])id=(\d+)", path)
                }
                return 200, {
                    "data": [
                        row
                        for row in self.bookings
                        if int(row["id"]) in ids
                    ]
                }
        if method == "POST":
            self.post_requests += 1
            self.posted.append(body)
            if not self.post_success:
                return 400, {"error": "rejected"}
            for payload in body:
                for row in self.bookings:
                    if int(row["id"]) == int(payload["id"]):
                        row["infoItems"] = payload["infoItems"]
            return 201, [{"success": True} for _ in body]
        raise AssertionError(f"Unexpected request: {method} {path}")


class CotNoteSyncTests(unittest.TestCase):
    def test_regression_group_uses_actual_twin_and_ignores_triple_phrase(self):
        candidates, audit = worker.plan_cot_notes(
            regression_group(), today=TODAY
        )
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["bookingId"], PRIMARY_BOOKING_ID)
        self.assertEqual(
            candidates[0]["text"],
            "BABY COT REQUIRED — PREPARE BEFORE ARRIVAL — "
            f"Booking {PRIMARY_BOOKING_ID} — infant age 8 months.",
        )
        self.assertEqual(audit[0]["action"], "pending_write")

    def test_conflict_is_manual_when_adults_exceed_room_capacity(self):
        rows = regression_group()
        rows[0]["numAdult"] = 3
        candidates, audit = worker.plan_cot_notes(rows, today=TODAY)
        self.assertEqual(candidates, [])
        self.assertEqual(audit[0]["action"], "manual_review")
        self.assertEqual(audit[0]["reason"], "room_or_occupancy_not_proved")

    def test_missing_status_is_manual_and_never_written(self):
        rows = regression_group()
        rows[0]["status"] = ""
        candidates, audit = worker.plan_cot_notes(rows, today=TODAY)
        self.assertEqual(candidates, [])
        self.assertEqual(audit[0]["action"], "manual_review")
        self.assertEqual(audit[0]["reason"], "room_or_occupancy_not_proved")

    def test_live_write_is_read_back_and_changes_only_infoitems(self):
        client = FakeClient(regression_group())
        report = worker.run(
            client,
            today=TODAY,
            values=LIVE_ENV,
        )
        self.assertEqual(report["summary"]["notesWritten"], 1)
        self.assertEqual(report["summary"]["notesReadBackVerified"], 1)
        self.assertEqual(report["safety"]["bookingFieldsChanged"], ["infoItems"])
        self.assertEqual(report["safety"]["guestMessagesSent"], 0)
        self.assertEqual(report["policy"]["id"], worker.POLICY_ID)
        self.assertEqual(client.post_requests, 1)

    def test_existing_note_is_idempotent(self):
        rows = regression_group()
        rows[0]["infoItems"] = [
            {
                "code": worker.NOTE_CODE,
                "text": (
                    "BABY COT REQUIRED — PREPARE BEFORE ARRIVAL — "
                    f"Booking {PRIMARY_BOOKING_ID} — infant age 8 months."
                ),
            }
        ]
        client = FakeClient(rows)
        report = worker.run(
            client,
            today=TODAY,
            values=LIVE_ENV,
        )
        self.assertEqual(report["summary"]["notesWritten"], 0)
        self.assertEqual(report["summary"]["duplicates"], 1)
        self.assertEqual(client.post_requests, 0)

    def test_live_guards_fail_closed(self):
        client = FakeClient(regression_group())
        with self.assertRaises(worker.CotNoteError):
            worker.run(
                client,
                today=TODAY,
                values={**LIVE_ENV, "BEDS24_COT_NOTE_MAX_WRITES": "1"},
            )
        self.assertEqual(client.post_requests, 0)

    def test_policy_must_authorize_before_any_network_request(self):
        client = FakeClient(regression_group())
        with self.assertRaisesRegex(worker.CotNoteError, "policy ID"):
            worker.run(
                client,
                today=TODAY,
                values={**LIVE_ENV, "BEDS24_COT_NOTE_POLICY_ID": "elcid.other"},
            )
        self.assertEqual(client.get_requests, 0)
        self.assertEqual(client.post_requests, 0)

    def test_multiple_safe_candidates_are_batched_and_read_back(self):
        rows = regression_group()
        second_group = regression_group()
        for index, row in enumerate(second_group):
            row["masterId"] = 92000001
            row["id"] = 92000001 + index
        client = FakeClient(rows + second_group)
        report = worker.run(client, today=TODAY, values=LIVE_ENV)
        self.assertEqual(report["summary"]["notesWritten"], 2)
        self.assertEqual(report["summary"]["notesReadBackVerified"], 2)
        self.assertEqual(client.post_requests, 1)

    def test_batch_above_cap_fails_before_write(self):
        rows = []
        for offset in range(6):
            group = regression_group()
            for index, row in enumerate(group):
                row["masterId"] = 93000000 + offset
                row["id"] = 94000000 + offset * 2 + index
            rows.extend(group)
        client = FakeClient(rows)
        with self.assertRaisesRegex(worker.CotNoteError, "exceeds"):
            worker.run(client, today=TODAY, values=LIVE_ENV)
        self.assertEqual(client.post_requests, 0)

    def test_empty_queue_is_a_successful_noop(self):
        client = FakeClient([])
        report = worker.run(client, today=TODAY, values=LIVE_ENV)
        self.assertEqual(report["summary"]["notesWritten"], 0)
        self.assertEqual(report["summary"]["duplicates"], 0)
        self.assertEqual(client.post_requests, 0)

    def test_old_booking_is_excluded_from_continuous_window(self):
        rows = regression_group()
        for row in rows:
            row["bookingTime"] = "2026-07-01 10:00:00"
        candidates, audit = worker.plan_cot_notes(rows, today=TODAY)
        self.assertEqual(candidates, [])
        self.assertEqual(audit, [])


if __name__ == "__main__":
    unittest.main()
