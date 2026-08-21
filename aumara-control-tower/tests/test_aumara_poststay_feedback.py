from __future__ import annotations

import json
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "aumara-control-tower/policies/aumara-poststay-followup.json"
HTML_PATH = ROOT / "aumara-site/feedback.html"
FUNCTION_PATH = ROOT / "supabase/functions/aumara-feedback/index.ts"
MIGRATION_PATH = ROOT / "supabase/migrations/20260814160000_aumara_poststay_feedback.sql"


class _Parser(HTMLParser):
    pass


class AumaraPostStayFeedbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        cls.html = HTML_PATH.read_text(encoding="utf-8")
        cls.function = FUNCTION_PATH.read_text(encoding="utf-8")
        cls.migration = MIGRATION_PATH.read_text(encoding="utf-8")

    def test_checkout_reminder_is_hard_blocked(self) -> None:
        checkout = self.policy["checkoutReminder"]
        self.assertFalse(checkout["enabled"])
        self.assertTrue(checkout["hardBlock"])
        self.assertIn("send_departure_deadline_message", checkout["prohibitedIntents"])

    def test_discount_contract(self) -> None:
        incentive = self.policy["incentive"]
        self.assertEqual(incentive["discountPercent"], 10)
        self.assertEqual(incentive["minimumNights"], 5)
        self.assertTrue(incentive["transferable"])
        self.assertTrue(incentive["stackableWithActiveAumaraOffers"])
        self.assertEqual(incentive["maximumRedemptions"], 1)

    def test_html_is_parseable_and_token_stays_in_fragment(self) -> None:
        _Parser().feed(self.html)
        self.assertIn('new URLSearchParams(location.hash.replace(/^#/, ""))', self.html)
        self.assertIn('const token = hashParams.get("t") || "";', self.html)
        self.assertNotIn('const token = params.get("t")', self.html)
        self.assertNotRegex(self.html, r"[?&]t=[a-f0-9]{48,128}")

    def test_language_switch_preserves_reward_state(self) -> None:
        self.assertIn("if(state.reward)renderReward(state.reward)", self.html)
        self.assertNotIn("renderReward(state.reward.source", self.html)

    def test_qr_is_dynamic_and_not_committed(self) -> None:
        self.assertIn("action=qr", self.html)
        self.assertNotIn("assets/vouchers/", self.html)
        voucher_dir = ROOT / "aumara-site/assets/vouchers"
        if voucher_dir.exists():
            self.assertEqual(list(voucher_dir.glob("*.svg")), [])

    def test_function_gates_public_offer_qr_and_booking(self) -> None:
        self.assertIn('npm:qrcode@1.5.4', self.function)
        self.assertIn('action === "qr"', self.function)
        self.assertIn('QRCode.toDataURL', self.function)
        self.assertIn('"content-type": "image/png"', self.function)
        self.assertGreaterEqual(self.function.count("survey_submitted_at"), 5)
        self.assertIn('row.beds24_status !== "active"', self.function)
        self.assertIn('url.searchParams.set("voucher", row.discount_code)', self.function)
        self.assertIn('url.searchParams.set("referer", row.discount_code)', self.function)

    def test_rpc_is_not_publicly_executable(self) -> None:
        normalized = " ".join(self.migration.lower().split())
        self.assertIn("revoke execute on function public.aumara_submit_feedback", normalized)
        self.assertIn("from public, anon, authenticated", normalized)
        self.assertIn("to service_role", normalized)

    def test_public_files_contain_no_bearer_link_or_guest_specific_code(self) -> None:
        public_runtime = self.html + "\n" + self.function
        self.assertNotRegex(public_runtime, r"#t=[a-f0-9]{48,128}")
        self.assertNotRegex(public_runtime, r"AUM[A-Z0-9]{8,32}")

    def test_guest_runtime_contains_no_checkout_pressure_copy(self) -> None:
        runtime = (self.html + "\n" + self.function).casefold()
        for phrase in (
            "leave immediately",
            "vacate faster",
            "free the house now",
            "liberate the room",
            "salga inmediatamente",
            "lasciare immediatamente",
        ):
            self.assertNotIn(phrase, runtime)


if __name__ == "__main__":
    unittest.main()
