import importlib.util
import pathlib
import sys
import unittest


SCRIPTS_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))
SPEC = importlib.util.spec_from_file_location(
    "beds24_aumara_access_audit", SCRIPTS_DIR / "beds24_aumara_access_audit.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class AumaraAccessAuditTests(unittest.TestCase):
    def test_query_is_aumara_and_read_only(self):
        path = MODULE.booking_query(MODULE.dt.date(2026, 8, 2))
        self.assertTrue(path.startswith("/bookings?"))
        self.assertIn("propertyId=324882", path)
        self.assertIn("arrivalFrom=2026-08-02", path)
        self.assertNotIn("write", path.casefold())

    def test_lock_pin_is_detected_without_returning_value(self):
        booking = {
            "infoItems": [{"code": "LOCK_PIN", "value": "123456"}],
        }
        self.assertEqual(MODULE.lock_pin_state(booking), (True, True))
        result = MODULE.audit_booking(booking, [])
        self.assertNotIn("123456", str(result))

    def test_host_access_message_marker_is_detected(self):
        found, sent_at = MODULE.access_message_state(
            [
                {"source": "guest", "message": "What is the access code?"},
                {
                    "source": "host",
                    "message": "Sus instrucciones de acceso incluyen su código de acceso.",
                    "createdAt": "2026-08-01T18:00:00Z",
                },
            ]
        )
        self.assertTrue(found)
        self.assertEqual(sent_at, "2026-08-01T18:00:00Z")

    def test_pin_and_message_confirm_sent(self):
        booking = {
            "id": 90754013,
            "arrival": "2026-08-02",
            "departure": "2026-08-04",
            "infoItems": [{"code": "LOCK_PIN", "value": "123456"}],
        }
        messages = [{"source": "host", "message": "PIN para el acceso: 123456"}]
        result = MODULE.audit_booking(booking, messages)
        self.assertEqual(result["status"], "PIN_SENT_CONFIRMED")
        self.assertNotIn("123456", str(result))


if __name__ == "__main__":
    unittest.main()
