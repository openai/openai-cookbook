import datetime as dt
import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "daily_ops_snapshot.py"
FIXTURES = ROOT / "fixtures" / "daily-ops"
SPEC = importlib.util.spec_from_file_location("daily_ops_snapshot", SCRIPT)
module = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(module)


class DailyOpsSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.now = dt.datetime(2026, 7, 30, 21, 0, tzinfo=dt.timezone.utc)
        self.day = dt.date(2026, 7, 30)

    def build(self, **overrides):
        values = {
            "business_date": self.day,
            "now": self.now,
            "gmail_path": FIXTURES / "gmail.json",
            "beds24_path": FIXTURES / "beds24.json",
            "epos_directory": FIXTURES / "epos",
            "b24_path": FIXTURES / "b24.json",
        }
        values.update(overrides)
        return module.build_snapshot(**values)

    def test_combines_existing_source_exports(self):
        snapshot = self.build()

        self.assertEqual(snapshot["schema"], "aumara-daily-ops-v1")
        self.assertEqual(snapshot["businessDate"], "2026-07-30")
        self.assertEqual(snapshot["timezone"], "Europe/Madrid")
        self.assertEqual(snapshot["dataQuality"]["status"], "ready")
        self.assertEqual(snapshot["metrics"]["guestEvents"], 3)
        self.assertEqual(snapshot["metrics"]["newBookings"], 2)
        self.assertEqual(snapshot["metrics"]["bookedRevenueCancelledEur"], 78.4)
        self.assertEqual(snapshot["metrics"]["bookedRevenueNetEur"], 281.6)
        self.assertEqual(snapshot["metrics"]["restaurantSalesGrossEur"], 642.5)
        self.assertEqual(snapshot["metrics"]["restaurantCashEur"], 142.5)
        self.assertEqual(snapshot["metrics"]["restaurantCardEur"], 480.0)
        self.assertEqual(snapshot["metrics"]["restaurantRefundsEur"], 10.0)
        self.assertEqual(snapshot["metrics"]["b24OverdueTasks"], 1)
        self.assertEqual(len(snapshot["events"]), 5)

    def test_missing_source_is_not_reported_as_zero_activity(self):
        snapshot = self.build(b24_path=None)

        b24 = next(source for source in snapshot["sources"] if source["id"] == "b24")
        self.assertEqual(b24["status"], "unavailable")
        self.assertIsNone(snapshot["metrics"]["b24OpenTasks"])
        self.assertIsNone(snapshot["metrics"]["b24ClosedToday"])
        self.assertEqual(snapshot["dataQuality"]["status"], "partial")
        self.assertTrue(snapshot["dataQuality"]["unavailableMetricsAreNull"])

    def test_blocked_source_stays_blocked_and_does_not_emit_false_zeros(self):
        blocked = {
            "schema": "aumara-beds24-guest-message-ingest-v1",
            "status": "BLOCKED",
            "generatedAtUtc": "2026-07-30T20:40:00Z",
            "summary": {
                "newBookings": 0,
                "cancelledBookings": 0,
            },
            "blocker": {
                "code": "MISSING_BOOKINGS_PERSONAL_SCOPE",
            },
        }
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / "beds24.json"
            path.write_text(json.dumps(blocked), encoding="utf-8")
            snapshot = self.build(beds24_path=path)

        beds24 = next(
            source for source in snapshot["sources"] if source["id"] == "beds24"
        )
        self.assertEqual(beds24["status"], "blocked")
        self.assertIsNone(snapshot["metrics"]["newBookings"])
        self.assertIsNone(snapshot["metrics"]["cancelledBookings"])
        self.assertIn(
            "MISSING_BOOKINGS_PERSONAL_SCOPE",
            " ".join(snapshot["dataQuality"]["issues"]),
        )

    def test_missing_metric_inside_available_source_stays_null(self):
        payload = json.loads((FIXTURES / "gmail.json").read_text(encoding="utf-8"))
        del payload["counters"]["deliveryErrors"]
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / "gmail.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            snapshot = self.build(gmail_path=path)

        self.assertIsNone(snapshot["metrics"]["deliveryErrors"])
        self.assertEqual(snapshot["dataQuality"]["status"], "partial")
        self.assertIn(
            "gmail metric is unavailable: deliveryErrors",
            snapshot["dataQuality"]["issues"],
        )

    def test_missing_epos_tenders_do_not_become_zero_cash_and_card(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = pathlib.Path(folder)
            (directory / "manifest.json").write_text(
                (FIXTURES / "epos" / "manifest.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            snapshot = self.build(epos_directory=directory)

        self.assertIsNone(snapshot["metrics"]["restaurantCashEur"])
        self.assertIsNone(snapshot["metrics"]["restaurantCardEur"])
        self.assertEqual(snapshot["dataQuality"]["status"], "partial")

    def test_duplicate_events_are_removed_by_event_id(self):
        payload = json.loads((FIXTURES / "gmail.json").read_text(encoding="utf-8"))
        payload["events"].append(dict(payload["events"][0]))
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / "gmail.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            snapshot = self.build(gmail_path=path)

        self.assertEqual(snapshot["dataQuality"]["duplicateEventsRemoved"], 1)
        self.assertEqual(len(snapshot["events"]), 5)

    def test_events_from_other_business_dates_are_filtered(self):
        payload = json.loads((FIXTURES / "gmail.json").read_text(encoding="utf-8"))
        payload["events"].append(
            {
                "eventId": "old-event",
                "occurredAtUtc": "2026-07-29T12:00:00Z",
                "eventType": "old",
            }
        )
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / "gmail.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            snapshot = self.build(gmail_path=path)

        self.assertNotIn(
            "old-event", {event["eventId"] for event in snapshot["events"]}
        )

    def test_cli_writes_one_canonical_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            output = pathlib.Path(folder) / "latest.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--date",
                    "2026-07-30",
                    "--now",
                    "2026-07-30T21:00:00Z",
                    "--gmail",
                    str(FIXTURES / "gmail.json"),
                    "--beds24",
                    str(FIXTURES / "beds24.json"),
                    "--epos-dir",
                    str(FIXTURES / "epos"),
                    "--b24",
                    str(FIXTURES / "b24.json"),
                    "--output",
                    str(output),
                    "--history-dir",
                    str(pathlib.Path(folder) / "history"),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            snapshot = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(snapshot["schema"], "aumara-daily-ops-v1")
            self.assertEqual(snapshot["dataQuality"]["status"], "ready")
            history = list((pathlib.Path(folder) / "history" / "2026-07-30").glob("*.json"))
            self.assertEqual(len(history), 1)
            self.assertEqual(
                json.loads(history[0].read_text(encoding="utf-8")),
                snapshot,
            )


if __name__ == "__main__":
    unittest.main()
