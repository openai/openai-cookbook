import base64
import datetime as dt
import importlib.util
import os
import pathlib
import unittest
from unittest import mock

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "eposnow_reporting_export.py"
spec = importlib.util.spec_from_file_location("eposnow_reporting_export", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)


class ExportTests(unittest.TestCase):
    def test_parse_dt_accepts_iso_formats(self):
        self.assertEqual(
            module.parse_dt("2026-04-01T12:34:56"),
            dt.datetime(2026, 4, 1, 12, 34, 56),
        )
        self.assertEqual(
            module.parse_dt("2026-04-01 12:34:56"),
            dt.datetime(2026, 4, 1, 12, 34, 56),
        )
        self.assertIsNone(module.parse_dt("bad timestamp"))

    def test_money_rounds_to_two_decimals(self):
        self.assertEqual(module.money("10"), "10.00")
        self.assertEqual(module.money("1.236"), "1.24")
        self.assertEqual(module.money(None), "0.00")

    def test_by_id_builds_reference_map(self):
        rows = [
            {"ProductID": 1, "Name": "Coffee"},
            {"ProductID": 2, "Name": "Breakfast"},
            {"ProductID": None, "Name": "Ignore"},
        ]
        self.assertEqual(module.by_id(rows, "ProductID"), {1: "Coffee", 2: "Breakfast"})

    def test_access_token_can_be_built_from_key_and_secret(self):
        with mock.patch.dict(
            os.environ,
            {
                "EPOSNOW_ACCESS_TOKEN": "",
                "EPOSNOW_API_KEY": "key",
                "EPOSNOW_API_SECRET": "secret",
            },
            clear=False,
        ):
            expected = base64.b64encode(b"key:secret").decode()
            self.assertEqual(module.access_token(), expected)

    def test_access_token_prefers_preencoded_token(self):
        with mock.patch.dict(
            os.environ,
            {"EPOSNOW_ACCESS_TOKEN": "ready-token"},
            clear=False,
        ):
            self.assertEqual(module.access_token(), "ready-token")


if __name__ == "__main__":
    unittest.main()
