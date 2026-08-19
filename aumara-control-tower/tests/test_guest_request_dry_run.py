from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import guest_request_dry_run as worker  # noqa: E402


SAFE_ENV = {
    "AUMARA_DRY_RUN": "true",
    "AUMARA_DISABLE_EMAIL_SEND": "true",
    "AUMARA_DISABLE_BOOKING_MUTATIONS": "true",
}


class GuestRequestDryRunTests(unittest.TestCase):
    def test_refuses_to_run_without_all_guards(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "Refusing to run"):
                worker.assert_dry_run_guards()

    def test_cancellation_wins_over_embedded_bed_preference(self) -> None:
        event = {
            "subject": "Booking Cancelled: test",
            "body": (
                "This Booking has been cancelled by the guest. "
                "BED PREFERENCE: 1 extra-large double"
            ),
        }
        self.assertEqual(worker.classify_event(event), "cancellation")

    def test_sent_thread_is_deduplicated_without_writes(self) -> None:
        event = {
            "message_id": "message-1",
            "thread_id": "thread-1",
            "booking_ref": "12345678",
            "event_type": "bed_request",
            "language": "ee",
            "guest_first_name": "Test",
            "reply_already_sent": True,
        }
        result = worker.decision_for(event)
        self.assertEqual(result["outcome"], "deduplicated")
        self.assertFalse(result["email_send_requested"])
        self.assertFalse(result["booking_mutation_requested"])
        self.assertIn("BED REQUEST", result["proposed_booking_note"])

    def test_price_request_requires_manual_review(self) -> None:
        event = {
            "message_id": "message-2",
            "subject": "7-8 agosto",
            "body": "¿Qué precio tiene una noche para dos personas?",
            "language": "es",
        }
        result = worker.decision_for(event)
        self.assertEqual(result["event_type"], "pricing_or_availability")
        self.assertEqual(result["outcome"], "manual_review")
        self.assertIsNone(result["proposed_reply"])

    def test_report_has_zero_external_actions(self) -> None:
        snapshot = {
            "source": "unit-test",
            "events": [
                {
                    "message_id": "message-3",
                    "event_type": "pet_request",
                    "language": "es",
                    "guest_first_name": "Test",
                },
                {
                    "message_id": "message-4",
                    "event_type": "booking_notification",
                },
            ],
        }
        with mock.patch.dict(os.environ, SAFE_ENV, clear=True):
            report = worker.build_report(snapshot)

        self.assertEqual(report["summary"]["emails_sent"], 0)
        self.assertEqual(report["summary"]["booking_mutations"], 0)
        self.assertEqual(report["safety"]["external_network_calls"], 0)
        worker.validate_report(report)

    def test_output_never_contains_source_contact_or_security_code(self) -> None:
        snapshot = {
            "source": "unit-test",
            "events": [
                {
                    "message_id": "message-5",
                    "event_type": "bed_request",
                    "body": (
                        "Email guest@example.com, phone +34 600 123 456, "
                        "Security Code = do-not-store"
                    ),
                }
            ],
        }
        with mock.patch.dict(os.environ, SAFE_ENV, clear=True):
            report = worker.build_report(snapshot)
        serialized = json.dumps(report)
        self.assertNotIn("guest@example.com", serialized)
        self.assertNotIn("+34 600 123 456", serialized)
        self.assertNotIn("do-not-store", serialized)

    def test_csv_is_an_audit_log_not_an_action_queue(self) -> None:
        snapshot = {
            "source": "unit-test",
            "events": [
                {
                    "message_id": "message-6",
                    "event_type": "cancellation",
                    "language": "es",
                }
            ],
        }
        with mock.patch.dict(os.environ, SAFE_ENV, clear=True):
            report = worker.build_report(snapshot)
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "audit.csv"
            worker.write_csv(report, path)
            csv_text = path.read_text(encoding="utf-8")
        self.assertIn("email_send_requested", csv_text)
        self.assertIn("booking_mutation_requested", csv_text)
        self.assertIn("False", csv_text)


if __name__ == "__main__":
    unittest.main()
