#!/usr/bin/env python3
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from beds24_aumara_voucher_autogen import (
    KNOWN_ALIASES,
    booking_url,
    code_for,
    merge_vouchers,
)


class CodeTests(unittest.TestCase):
    def test_known_alias_is_stable(self):
        self.assertEqual(code_for(90754013), "AUMARAIBANEZ10")
        self.assertEqual(code_for(91062629), "AUMARAMARTINEZ10")
        self.assertEqual(code_for(91036023), "AUMARAAYALA10")

    def test_new_booking_is_deterministic(self):
        self.assertEqual(code_for(90045089), "AUM90045089")

    def test_all_codes_are_alphanumeric(self):
        for booking_id in list(KNOWN_ALIASES) + [90045089, 91191923]:
            self.assertRegex(code_for(booking_id), r"^[A-Z0-9]{8,32}$")


class MergeTests(unittest.TestCase):
    def test_keeps_existing_and_appends_missing(self):
        current = [{"phrase": "AUMARAIBANEZ10", "discount": 10}]
        merged, added = merge_vouchers(current, ["AUMARAIBANEZ10", "AUM90045089"])
        phrases = [row["phrase"] for row in merged]
        self.assertEqual(phrases, ["AUMARAIBANEZ10", "AUM90045089"])
        self.assertEqual(added, ["AUM90045089"])

    def test_idempotent_second_pass(self):
        current = [{"phrase": "AUM90045089", "discount": 10}]
        merged, added = merge_vouchers(current, ["AUM90045089"])
        self.assertEqual(added, [])
        self.assertEqual(len(merged), 1)

    def test_booking_url_has_no_hyphen(self):
        url = booking_url("AUMARAIBANEZ10")
        self.assertIn("voucher=AUMARAIBANEZ10", url)
        self.assertNotIn("AUMARA-IBANEZ", url)


if __name__ == "__main__":
    unittest.main()
