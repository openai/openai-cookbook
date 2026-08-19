import importlib.util
import pathlib
import sys
import unittest

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))
SPEC = importlib.util.spec_from_file_location(
    "beds24_finance_snapshot", SCRIPTS_DIR / "beds24_finance_snapshot.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class Beds24FinanceSnapshotTests(unittest.TestCase):
    def test_invoice_totals(self):
        row = {
            "invoiceItems": [
                {"type": "charge", "amount": 100, "qty": 2},
                {"type": "payment", "amount": 50, "qty": 1},
            ]
        }
        charges, payments = MODULE.invoice_totals(row)
        self.assertEqual(charges, 200.0)
        self.assertEqual(payments, 50.0)

    def test_summary_allocates_cross_month_stay_by_night(self):
        bookings = [
            {
                "booking_id": 1,
                "property": "EL CID",
                "arrival": "2026-07-31",
                "departure": "2026-08-03",
                "nights": 3,
                "gross_booked_eur": 300.0,
                "commission_eur": 30.0,
            }
        ]
        summary = MODULE.summarize(bookings)
        by_month = {
            (row["property"], row["month"]): row
            for row in summary["monthly_stay_allocation"]
        }
        self.assertEqual(by_month[("EL CID", "2026-07")]["room_nights"], 1)
        self.assertEqual(by_month[("EL CID", "2026-07")]["gross_allocated_eur"], 100.0)
        self.assertEqual(by_month[("EL CID", "2026-08")]["room_nights"], 2)
        self.assertEqual(by_month[("EL CID", "2026-08")]["gross_allocated_eur"], 200.0)

    def test_august_on_books_is_separate_from_as_of_slice(self):
        bookings = [
            {
                "booking_id": 2,
                "property": "AUMARA",
                "arrival": "2026-08-10",
                "departure": "2026-08-20",
                "nights": 10,
                "gross_booked_eur": 1000.0,
                "commission_eur": 0.0,
            }
        ]
        summary = MODULE.summarize(bookings)
        mtd = next(row for row in summary["august_through_as_of"] if row["property"] == "AUMARA")
        full = next(row for row in summary["august_full_on_books"] if row["property"] == "AUMARA")
        self.assertEqual(mtd["room_nights_through_as_of"], 5)
        self.assertEqual(mtd["gross_allocated_through_as_of_eur"], 500.0)
        self.assertEqual(full["room_nights_on_books"], 10)
        self.assertEqual(full["gross_allocated_on_books_eur"], 1000.0)


if __name__ == "__main__":
    unittest.main()
