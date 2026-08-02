import importlib.util
import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock


SCRIPTS_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))
SPEC = importlib.util.spec_from_file_location(
    "beds24_aumara_access_audit", SCRIPTS_DIR / "beds24_aumara_access_audit.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class AumaraAccessAuditTests(unittest.TestCase):
    def test_query_covers_today_and_tomorrow_and_is_read_only(self):
        path = MODULE.booking_query(
            MODULE.dt.date(2026, 8, 2),
            MODULE.dt.date(2026, 8, 3),
        )
        self.assertTrue(path.startswith("/bookings?"))
        self.assertIn("propertyId=324882", path)
        self.assertIn("arrivalFrom=2026-08-02", path)
        self.assertIn("arrivalTo=2026-08-03", path)
        self.assertNotIn("write", path.casefold())

    def test_manual_arrival_is_one_exact_day(self):
        with mock.patch.dict(os.environ, {"AUMARA_AUDIT_ARRIVAL": "2026-08-02"}):
            start, end = MODULE.target_window()
        self.assertEqual(start, MODULE.dt.date(2026, 8, 2))
        self.assertEqual(end, MODULE.dt.date(2026, 8, 2))

    def test_lock_pin_is_detected_without_returning_value(self):
        booking = {"infoItems": [{"code": "LOCK_PIN", "value": "123456"}]}
        self.assertEqual(MODULE.lock_pin_state(booking), (True, True))
        result = MODULE.audit_booking(booking, [])
        self.assertNotIn("123456", json.dumps(result))
        self.assertEqual(result["status"], "PIN_PRESENT_SEND_UNCONFIRMED")

    def test_exact_current_pin_in_latest_host_message_is_matched(self):
        booking = {
            "id": 90754013,
            "arrival": "2026-08-02",
            "departure": "2026-08-04",
            "infoItems": [{"code": "LOCK_PIN", "value": "123456"}],
        }
        messages = [
            {
                "source": "host",
                "message": "Sus instrucciones de acceso: PIN 123456.",
                "createdAt": "2026-08-01T18:00:00Z",
            }
        ]
        result = MODULE.audit_booking(booking, messages)
        self.assertEqual(result["status"], "PIN_MESSAGE_MATCHED")
        self.assertTrue(result["hostMessageMatchesCurrentPin"])
        self.assertTrue(result["distributionIntegrityVerified"])
        self.assertFalse(result["physicalDoorOperationVerified"])
        self.assertNotIn("123456", json.dumps(result))

    def test_stale_pin_in_latest_host_message_is_mismatch(self):
        booking = {
            "id": 90754013,
            "infoItems": [{"code": "LOCK_PIN", "value": "123456"}],
        }
        messages = [
            {"source": "host", "message": "Access code PIN 654321."}
        ]
        result = MODULE.audit_booking(booking, messages)
        self.assertEqual(result["status"], "PIN_MESSAGE_MISMATCH")
        self.assertFalse(result["hostMessageMatchesCurrentPin"])
        serialized = json.dumps(result)
        self.assertNotIn("123456", serialized)
        self.assertNotIn("654321", serialized)

    def test_guest_message_cannot_confirm_distribution(self):
        booking = {"infoItems": [{"code": "LOCK_PIN", "value": "123456"}]}
        messages = [{"source": "guest", "message": "My PIN 123456 does not work"}]
        result = MODULE.audit_booking(booking, messages)
        self.assertEqual(result["status"], "PIN_PRESENT_SEND_UNCONFIRMED")

    def test_no_arrivals_is_a_successful_audited_state(self):
        with tempfile.TemporaryDirectory() as directory:
            output = pathlib.Path(directory) / "evidence.json"
            with (
                mock.patch.object(MODULE, "OUTPUT", output),
                mock.patch.object(
                    MODULE,
                    "target_window",
                    return_value=(
                        MODULE.dt.date(2026, 8, 2),
                        MODULE.dt.date(2026, 8, 3),
                    ),
                ),
                mock.patch.object(
                    MODULE,
                    "get_access_token",
                    return_value=("token", "refresh_token", "https://api.beds24.com/v2", "secret", False),
                ),
                mock.patch.object(MODULE, "fetch_arrivals", return_value=[]),
            ):
                exit_code = MODULE.main()
            payload = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "NO_ARRIVALS")
        self.assertEqual(payload["results"], [])
        self.assertFalse(payload["pinValueExposed"])


if __name__ == "__main__":
    unittest.main()
