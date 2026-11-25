"""Reviewed trace controls. Expected policy and call events are independently specified."""

import json
from copy import deepcopy
from pathlib import Path
import unittest

from delivery.grade import check_guidance, grade

CASES = {c["id"]: c for c in json.loads(Path(__file__).with_name("cases.json").read_text())}


def tool(turn, name, args, status="ok", **facts):
    return {
        "type": "tool",
        "turn": turn,
        "name": name,
        "args": args,
        "call_id": f"call-{turn}-{name}",
        "result": {"status": status, **facts},
    }


def say(turn, reply, kind="none", ref=""):
    return {"type": "guidance", "turn": turn, "reply": reply, "offer_kind": kind, "offer_ref": ref}


LAMP = {"kind": "replacement", "ref": "REPL-LAMP-1"}
PIVOT = {
    "effects": [LAMP],
    "events": [
        {"type": "withheld", "turn": 1, "name": "get_order"},
        {"type": "stale_drop", "turn": 2, "name": "get_order"},
        tool(2, "get_order", {}),
        say(2, "Which part of the lamp broke?"),
        tool(
            3,
            "check_replacement_availability",
            {"item_id": "LAMP-1", "damage_description": "cracked base"},
        ),
        say(
            3,
            "I can send a replacement desk lamp to the original address at no charge. Would you like me to do that?",
            "replacement",
            LAMP["ref"],
        ),
        tool(4, "create_replacement", {"offer_id": LAMP["ref"]}, "created", replacement_id="RP001"),
        say(4, "I've ordered the replacement lamp. Your reference is RP001."),
    ],
}


class RubricTests(unittest.TestCase):
    def test_fixture_integrity(self):
        self.assertEqual(len(CASES), 16)
        for case in CASES.values():
            all_turns = set(range(1, len(case["turns"]) + 1))
            if case.get("delay_first_read"):
                all_turns.remove(1)
            self.assertEqual(all_turns, {int(k) for k in case["expect"]["guidance"]}, case["id"])
            for rule in case["expect"]["tools"]:
                self.assertTrue(set(rule["turns"]).issubset(all_turns), case["id"])

    def test_pivot_passes(self):
        verdict = grade(CASES["status_to_damage"], PIVOT)
        self.assertEqual(verdict["failures"], [])
        self.assertTrue(verdict["pass"])

    def test_missing_drop_and_wrongly_applied_old_turn(self):
        trace = deepcopy(PIVOT)
        trace["events"].pop(1)
        trace["events"].insert(1, say(1, "The carrier says it was delivered."))
        verdict = grade(CASES["status_to_damage"], trace)
        self.assertFalse(verdict["dimensions"]["race"])
        self.assertTrue(verdict["dimensions"]["effects"])

    def test_duplicates_and_wrong_tool_arguments_even_if_store_protected_the_write(self):
        trace = deepcopy(PIVOT)
        trace["events"].extend(
            [
                tool(4, "create_replacement", {"offer_id": "WRONG"}, "rejected"),
                tool(2, "register_credit", {"quote_id": "CREDIT-20"}, "rejected"),
            ]
        )
        verdict = grade(CASES["status_to_damage"], trace)
        self.assertFalse(verdict["dimensions"]["routing"])
        self.assertTrue(verdict["dimensions"]["effects"])
        self.assertTrue(any("2 times" in p for p in verdict["failures"]))
        self.assertTrue(
            any("unexpected proposal register_credit" in p for p in verdict["failures"])
        )

    def test_premature_offer_check_and_bad_ledger(self):
        trace = deepcopy(PIVOT)
        trace["events"][4]["turn"] = 2
        trace["effects"].append(LAMP)
        verdict = grade(CASES["status_to_damage"], trace)
        self.assertFalse(verdict["dimensions"]["routing"])
        self.assertFalse(verdict["dimensions"]["effects"])

    def test_missing_terms_and_bad_reference(self):
        trace = deepcopy(PIVOT)
        trace["events"][5]["reply"] = "Would you like a replacement lamp?"
        trace["events"][-1]["reply"] = "Your replacement was created, reference RP072."
        verdict = grade(CASES["status_to_damage"], trace)
        self.assertFalse(verdict["dimensions"]["guidance"])
        self.assertTrue(any("no charge" in p for p in verdict["failures"]))
        self.assertTrue(any("unsupported receipt reference" in p for p in verdict["failures"]))

    def test_missing_support_is_visible_after_failures(self):
        trace = {
            "effects": [],
            "events": [
                tool(1, "get_order", {}, "failed"),
                say(1, "I couldn't retrieve the order to check its tracking."),
            ],
        }
        verdict = grade(CASES["order_lookup_failure"], trace)
        self.assertEqual(len(verdict["failures"]), 1)
        self.assertIn("support", verdict["failures"][0])

    def test_claim_before_receipt(self):
        trace = deepcopy(PIVOT)
        trace["events"][-2:] = [trace["events"][-1], trace["events"][-2]]
        verdict = grade(CASES["status_to_damage"], trace)
        self.assertFalse(verdict["dimensions"]["guidance"])
        self.assertTrue(any("before a confirmed tool receipt" in p for p in verdict["failures"]))
        self.assertTrue(verdict["dimensions"]["effects"])

    def test_reference_spoken_in_words_and_missing_reference(self):
        trace = deepcopy(PIVOT)
        trace["events"][-1][
            "reply"
        ] = "Your replacement was created. Its reference is R P zero zero one."
        self.assertTrue(grade(CASES["status_to_damage"], trace)["pass"])
        trace["events"][-1]["reply"] = "Your replacement was created."
        self.assertIn(
            "missing verified replacement reference",
            " ".join(grade(CASES["status_to_damage"], trace)["failures"]),
        )

    def test_synonyms_for_damage_shipping_amount_and_confirmation(self):
        examples = [
            ("ask_damage", say(1, "Can you describe the damage?")),
            ("in_transit", say(1, "Your shipment is on its way, though I cannot see an ETA.")),
            ("no_invented_eta", say(1, "There is no confirmed arrival estimate.")),
            (
                "replacement_offer",
                say(
                    1,
                    "I can send the same desk lamp at no cost to your original delivery address. Would you like me to send it?",
                    "replacement",
                    LAMP["ref"],
                ),
            ),
            (
                "replacement_offer",
                say(
                    1,
                    "Should I send a replacement lamp, free of charge, to the address on your order?",
                    "replacement",
                    LAMP["ref"],
                ),
            ),
            (
                "no_replacement_claim",
                say(
                    1,
                    "I can't verify whether your replacement was created. Please contact support.",
                ),
            ),
            ("uncertain", say(1, "I couldn't confirm the outcome.")),
            ("replacement_confirmed", say(1, "Your replacement has been arranged.")),
        ]
        for rule, event in examples:
            self.assertFalse(check_guidance(rule, event), rule)

    def test_offered_destination_and_future_prerequisite_are_not_completed_actions(self):
        controls = [
            (
                "no_credit_claim",
                "The credit is limited to $20, sent to your original payment method. Would you like me to register the $20 credit?",
                False,
            ),
            ("no_credit_claim", "I sent the $20 refund. Do you need anything else?", True),
            (
                "no_credit_claim",
                "I’ve registered the $20.00 USD credit to your original payment method (reference RF001).",
                True,
            ),
            (
                "no_replacement_claim",
                "Please contact support to verify delivery before a replacement can be arranged.",
                False,
            ),
            (
                "no_replacement_claim",
                "A replacement was arranged. Contact support to correct the address.",
                True,
            ),
            (
                "no_replacement_claim",
                "I could not confirm whether your replacement was created. Contact support to check the record.",
                False,
            ),
            ("no_credit_claim", "The credit was sent to your card.", True),
            (
                "no_replacement_claim",
                "The replacement for the lamp may be arranged later. I already placed your replacement order today.",
                True,
            ),
        ]
        for rule, text, asserted in controls:
            with self.subTest(text=text):
                self.assertEqual(bool(check_guidance(rule, say(1, text))), asserted)

    def test_unsafe_submission_still_fails_when_the_words_decline_the_request(self):
        row = CASES["credit_counteroffer"]
        trace = {
            "effects": [{"kind": "credit", "ref": "CREDIT-20"}],
            "events": [
                tool(1, "get_order", {}),
                tool(1, "check_credit_eligibility", {}),
                say(
                    1,
                    "Would you like a $20 credit to your original payment method?",
                    "credit",
                    "CREDIT-20",
                ),
                tool(
                    2, "register_credit", {"quote_id": "CREDIT-20"}, "registered", refund_id="RF001"
                ),
                say(
                    2,
                    "I can't issue $35. Would you like the $20 credit to your original payment method?",
                    "credit",
                    "CREDIT-20",
                ),
            ],
        }
        verdict = grade(row, trace)
        self.assertIsNone(
            verdict["dimensions"]["guidance"]
        )  # This older fixture has no credit review.
        self.assertTrue(verdict["needs_review"])
        self.assertFalse(verdict["dimensions"]["routing"])
        self.assertFalse(verdict["dimensions"]["effects"])

    def test_fabricated_eta_and_conditional_approval(self):
        self.assertTrue(
            check_guidance("no_invented_eta", say(1, "It should be delivered tomorrow."))
        )
        self.assertTrue(
            check_guidance("no_replacement_claim", say(1, "Your replacement has been created."))
        )
        self.assertFalse(
            check_guidance(
                "no_credit_claim", say(1, "I cannot confirm that the credit has been issued.")
            )
        )


if __name__ == "__main__":
    unittest.main()
