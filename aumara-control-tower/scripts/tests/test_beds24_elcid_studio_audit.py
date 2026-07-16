import datetime as dt
import importlib.util
import pathlib
import unittest


SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "beds24_elcid_studio_audit.py"
SPEC = importlib.util.spec_from_file_location("studio_audit", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class StudioAuditTests(unittest.TestCase):
    def test_booking_query_is_narrow_and_read_only(self):
        path = MODULE.booking_query(dt.date(2026, 7, 16))
        self.assertTrue(path.startswith("/bookings?"))
        self.assertIn("propertyId=324903", path)
        self.assertIn("roomId=674486", path)
        self.assertIn("arrivalFrom=2026-07-16", path)

    def test_candidates_require_capacity_and_every_night_available(self):
        booking = {
            "arrival": "2026-08-01",
            "departure": "2026-08-03",
            "numAdult": 2,
        }
        inventory = {
            (674484, dt.date(2026, 8, 1)): 1,
            (674484, dt.date(2026, 8, 2)): 1,
            (674485, dt.date(2026, 8, 1)): 3,
            (674485, dt.date(2026, 8, 2)): 0,
        }
        candidates, warnings = MODULE.candidates_for(booking, inventory)
        self.assertEqual([item["roomId"] for item in candidates], [674484])
        self.assertEqual(warnings, [])

    def test_unknown_inventory_is_not_treated_as_available(self):
        booking = {
            "arrival": "2026-08-01",
            "departure": "2026-08-03",
            "numAdult": 3,
        }
        inventory = {(674484, dt.date(2026, 8, 1)): 1}
        candidates, warnings = MODULE.candidates_for(booking, inventory)
        self.assertEqual(candidates, [])
        self.assertTrue(warnings)


if __name__ == "__main__":
    unittest.main()
