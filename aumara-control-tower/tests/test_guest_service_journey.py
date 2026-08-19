from __future__ import annotations

import json
import pathlib
import shutil
import sys
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import guest_service_journey as journey  # noqa: E402


def event(**updates):
    value = {
        "property": "aumara",
        "booking_ref": "TEST-BOOKING",
        "event_type": "post_checkin",
        "status": "checked_in",
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
    value.update(updates)
    return value


class GuestServiceJourneyTests(unittest.TestCase):
    def test_aumara_post_checkin_proposes_spanish_without_sending(self) -> None:
        result = journey.evaluate_event(event(), ROOT / "policies")
        self.assertEqual(result["decision"], "proposal")
        self.assertIn("Lucía", result["message"])
        self.assertIn("casa AUMARA", result["message"])
        self.assertFalse(result["beds24_send_requested"])
        self.assertFalse(result["whatsapp_send_requested"])
        self.assertFalse(result["email_send_requested"])

    def test_elcid_first_morning_proposes_once_in_window(self) -> None:
        result = journey.evaluate_event(
            event(
                property="elcid",
                event_type="first_morning",
                language="en",
                guest_first_name="Ana",
                check_in_at="2026-08-17T17:00:00+02:00",
                departure_at="2026-08-20T11:00:00+02:00",
                now="2026-08-18T09:15:00+02:00",
            ),
            ROOT / "policies",
        )
        self.assertEqual(result["decision"], "proposal")
        self.assertIn("Did you sleep well?", result["message"])

    def test_checkout_pressure_is_hard_blocked(self) -> None:
        result = journey.evaluate_event(
            {"event_type": "checkout_reminder"}, ROOT / "policies"
        )
        self.assertEqual(result["decision"], "blocked")
        self.assertEqual(result["reason"], "checkout_pressure_hard_block")

    def test_negative_signal_routes_to_human(self) -> None:
        result = journey.evaluate_event(
            event(last_guest_message="El wifi no funciona y hay mucho ruido"),
            ROOT / "policies",
        )
        self.assertEqual(result["decision"], "manual_review")
        self.assertEqual(result["priority"], "high")
        self.assertNotIn("message", result)

    def test_negative_signal_wins_over_existing_dedupe(self) -> None:
        first = journey.evaluate_event(event(), ROOT / "policies")
        result = journey.evaluate_event(
            event(
                sent_dedupe_keys=[first["dedupe_key"]],
                last_guest_message="No tenemos agua caliente y la puerta no abre",
            ),
            ROOT / "policies",
        )
        self.assertEqual(result["decision"], "manual_review")
        self.assertEqual(result["priority"], "urgent")

    def test_structured_issue_flag_routes_to_human(self) -> None:
        result = journey.evaluate_event(
            event(issue_flags=["maintenance"]), ROOT / "policies"
        )
        self.assertEqual(result["decision"], "manual_review")
        self.assertEqual(result["priority"], "high")

    def test_accented_issue_patterns_survive_normalization(self) -> None:
        for message in ("Nous sommes sans accès", "Zu viel Lärm im Zimmer"):
            with self.subTest(message=message):
                result = journey.evaluate_event(
                    event(last_guest_message=message), ROOT / "policies"
                )
                self.assertEqual(result["decision"], "manual_review")

    def test_departure_day_morning_is_skipped(self) -> None:
        result = journey.evaluate_event(
            event(
                event_type="first_morning",
                check_in_at="2026-08-16T17:00:00+02:00",
                departure_at="2026-08-18T11:00:00+02:00",
                now="2026-08-18T09:15:00+02:00",
                nights=2,
            ),
            ROOT / "policies",
        )
        self.assertEqual(result["decision"], "skip")
        self.assertEqual(result["reason"], "departure_day")

    def test_dedupe_key_suppresses_second_message(self) -> None:
        first = journey.evaluate_event(event(), ROOT / "policies")
        second = journey.evaluate_event(
            event(sent_dedupe_keys=[first["dedupe_key"]]), ROOT / "policies"
        )
        self.assertEqual(second["decision"], "skip")
        self.assertEqual(second["reason"], "already_proposed_or_sent")
        self.assertEqual(first["dedupe_key"], "aumara:test-booking:post_checkin")

    def test_duplicate_events_in_one_batch_are_suppressed(self) -> None:
        report = journey.build_report([event(), event()], ROOT / "policies")
        self.assertEqual(report["summary"]["proposal"], 1)
        self.assertEqual(report["summary"]["skip"], 1)
        self.assertEqual(
            report["decisions"][1]["reason"], "already_proposed_or_sent"
        )

    def test_first_morning_uses_property_timezone(self) -> None:
        result = journey.evaluate_event(
            event(
                event_type="first_morning",
                check_in_at="2026-08-17T15:00:00Z",
                departure_at="2026-08-20T09:00:00Z",
                now="2026-08-18T11:30:00Z",
            ),
            ROOT / "policies",
        )
        self.assertEqual(result["decision"], "skip")
        self.assertEqual(result["reason"], "outside_first_morning_window")

    def test_five_operating_languages_are_present(self) -> None:
        for language in ("en", "es", "fr", "de", "nl"):
            with self.subTest(language=language):
                result = journey.evaluate_event(
                    event(language=language), ROOT / "policies"
                )
                self.assertEqual(result["decision"], "proposal")
                self.assertEqual(result["language"], language)
                self.assertTrue(result["message"])

    def test_outside_post_checkin_window_is_skipped(self) -> None:
        result = journey.evaluate_event(
            event(now="2026-08-17T19:30:00+02:00"), ROOT / "policies"
        )
        self.assertEqual(result["reason"], "outside_post_checkin_window")

    def test_snapshot_drift_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory) / "policies"
            shutil.copytree(ROOT / "policies", root)
            snapshot = json.loads(
                (root / "guest_journey_runtime.json").read_text(encoding="utf-8")
            )
            snapshot["snapshot_version"] = "2026.08.17.3"
            (root / "guest_journey_runtime.json").write_text(
                json.dumps(snapshot), encoding="utf-8"
            )
            with self.assertRaisesRegex(
                journey.GuestJourneyError, "snapshot version mismatch"
            ):
                journey.evaluate_event(event(), root)

    def test_cli_guards_are_required(self) -> None:
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(
                journey.GuestJourneyError, "proposal guards"
            ):
                journey.assert_proposal_guards()


if __name__ == "__main__":
    unittest.main()
