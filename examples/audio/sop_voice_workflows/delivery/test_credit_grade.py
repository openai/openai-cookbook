"""Offline controls with hand-labeled observations. These tests exercise the grader, not the reviewer model."""

import asyncio
from copy import deepcopy
import json
from pathlib import Path

import pytest

from delivery import credit_grade, runner
from delivery.grade import grade
from delivery.store import Store

CASES = {c["id"]: c for c in json.loads(Path(__file__).with_name("cases.json").read_text())}
OVERCENT = "Would you like me to apply twenty dollars and ninety-nine cents to your original payment method?"
REOFFER = "I can't issue $35. May I apply the $20 credit to your original payment method?"


def observed(
    cents,
    amount_quote,
    *,
    amount="usd",
    destination="original",
    destination_quote="original payment method",
    permission="asked",
    permission_quote="May I apply",
):
    return {
        "amount": {"verdict": amount, "quote": amount_quote},
        "amount_cents": cents,
        "payment_method": {"verdict": destination, "quote": destination_quote},
        "permission": {"verdict": permission, "quote": permission_quote},
    }


WRONG_CENTS = observed(
    2099, "twenty dollars and ninety-nine cents", permission_quote="Would you like me to apply"
)
VALID_REOFFER = observed(2000, "the $20 credit")


def walkthrough(review_sender=None):
    """Run the real two-turn counteroffer case with a scripted backend and two hand-labeled reviews."""
    sent_reviews = []

    async def scripted(req, turn, step):
        if req["text"]["format"]["name"] == credit_grade.FORMAT:
            sent_reviews.append(req)
            if review_sender:
                return await review_sender(req, turn, step)
            label = WRONG_CENTS if turn == 1 else VALID_REOFFER
            body = {
                "model": credit_grade.MODEL,
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "status": "completed",
                        "content": [{"type": "output_text", "text": json.dumps(label)}],
                    }
                ],
            }
            return credit_grade.parse(body), {}
        if turn == 1 and step < 2:
            name = ("get_order", "check_credit_eligibility")[step]
            call_id = "control-" + name
            return {
                "type": "call",
                "name": name,
                "args": {},
                "call_id": call_id,
                "continuation": [
                    {"type": "function_call", "name": name, "arguments": "{}", "call_id": call_id}
                ],
            }, {}
        return {
            "type": "reply",
            "offer_kind": "credit",
            "offer_ref": "CREDIT-20",
            "reply": OVERCENT if turn == 1 else REOFFER,
        }, {}

    trace = asyncio.run(runner.play(CASES["credit_counteroffer"], "scripted-backend", scripted))
    return trace, sent_reviews


def offer_case(rule="credit_offer_20", scenario=None, text=REOFFER, observation=VALID_REOFFER):
    store = Store(scenario or {})
    turn = store.new_turn()
    store.call("get_order", {}, revision=turn, call_id="order")
    receipt = store.call("check_credit_eligibility", {}, revision=turn, call_id="eligibility")
    case = {
        "expect": {
            "tools": [
                {
                    "name": name,
                    "turns": [turn],
                    "optional": False,
                    "status": "ok",
                    "fields": {},
                    "words": {},
                }
                for name in ("get_order", "check_credit_eligibility")
            ],
            "effects": [],
            "guidance": {"1": [rule]},
        }
    }
    events = [{**row, "turn": turn, "type": "tool"} for row in store.log]
    events.append(
        {
            "type": "guidance",
            "turn": turn,
            "reply": text,
            "offer_kind": "credit",
            "offer_ref": receipt["quote_id"],
        }
    )
    return case, {
        "events": events,
        "effects": [],
        "credit_reviews": {
            "1": {"model": credit_grade.MODEL, "reply": text, "observation": deepcopy(observation)}
        },
    }


def test_worked_case_grades_reported_cents_and_declined_alternative_using_only_the_backend_words():
    trace, requests = walkthrough()
    assert trace["status"] == "completed" and trace["effects"] == []
    assert trace["grade"]["status"] == "fail"
    assert trace["grade"]["failures"] == [
        "guidance: turn 1: offered 2099 USD cents; store quoted 2000"
    ]
    assert trace["grade"]["needs_review"] == []
    assert trace["grade"]["dimensions"] == {
        "routing": True,
        "tool_results": True,
        "effects": True,
        "guidance": False,
        "race": True,
    }
    assert [json.loads(req["input"]) for req in requests] == [
        {"backend_reply": OVERCENT},
        {"backend_reply": REOFFER},
    ]
    assert all(
        req["model"] == credit_grade.MODEL
        and req["store"] is False
        and "tools" not in req
        and req["text"]["format"]["strict"]
        for req in requests
    )


def test_reviewer_outage_stays_review_and_post_call_time_is_separate(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(runner.time, "perf_counter", lambda: clock[0])

    async def unavailable(*_):
        clock[0] += 1.0
        raise TimeoutError

    trace, _ = walkthrough(unavailable)
    assert trace["status"] == "completed" and trace["turn_ms"] == [0.0, 0.0] and clock[0] == 2.0
    assert trace["grade"]["status"] == "review" and not trace["grade"]["pass"]
    assert all(
        "independent credit reviewer unavailable" in s for s in trace["grade"]["needs_review"]
    )


@pytest.mark.parametrize(
    "amount,amount_quote,cents,expected_status",
    [
        ("$20.99", "$20.99", 2099, "fail"),
        (
            "twenty dollars and ninety-nine cents",
            "twenty dollars and ninety-nine cents",
            2099,
            "fail",
        ),
        ("USD 20,000", "USD 20,000", 2000000, "fail"),
        ("$120.00", "$120.00", 12000, "fail"),
        ("twenty dollars", "twenty dollars", 2000, "pass"),
        ("$20.00", "$20.00", 2000, "pass"),
    ],
)
def test_normalized_amount_is_compared_exactly(amount, amount_quote, cents, expected_status):
    words = f"May I apply {amount} to your original payment method?"
    case, trace = offer_case(text=words, observation=observed(cents, amount_quote))
    assert grade(case, trace)["status"] == expected_status


def test_arbitrary_store_amount_and_reference_match_the_receipt_and_case_independently():
    words = "May I apply seven dollars and eighty-three cents to your original payment method?"
    case, trace = offer_case(
        "credit_offer_7_83",
        {"total": 7.83},
        words,
        observed(783, "seven dollars and eighty-three cents"),
    )
    assert trace["events"][1]["result"]["quote_id"] == "CREDIT-7.83"
    assert grade(case, trace)["status"] == "pass"
    case["expect"]["guidance"]["1"] = ["credit_offer_18_04"]
    assert grade(case, trace)["failures"] == [
        "guidance: turn 1: store amount disagrees with the case"
    ]
    trace["events"][-1]["offer_ref"] = "CREDIT-18.04"
    assert "current quote metadata" in str(grade(case, trace)["failures"])
    case["expect"]["guidance"]["1"] = ["credit_offer_typo"]
    with pytest.raises(ValueError, match="Invalid credit amount"):
        grade(case, trace)


@pytest.mark.parametrize(
    "store_ref,backend_ref,status",
    [
        ("qt_e281ab", "qt_e281ab", "pass"),
        ("qt_e281ab", "qt_775bb2", "fail"),
        ("qt_e281ab", "", "fail"),
        ("", "", "fail"),
        (" ", " ", "fail"),
        (None, None, "fail"),
    ],
)
def test_store_quote_ids_are_nonempty_and_opaque(store_ref, backend_ref, status):
    case, trace = offer_case()
    trace["events"][1]["result"]["quote_id"] = store_ref
    trace["events"][-1]["offer_ref"] = backend_ref
    assert grade(case, trace)["status"] == status


@pytest.mark.parametrize(
    "words,reading,status",
    [
        (REOFFER, VALID_REOFFER, "pass"),
        (
            "I can't issue $20. May I apply $35 to your original payment method?",
            observed(3500, "May I apply $35"),
            "fail",
        ),
        (
            "May I apply $20 or $35 to your original payment method?",
            observed(None, "$20 or $35", amount="conflicting"),
            "fail",
        ),
        (
            "May I apply 20 euros to your original payment method?",
            observed(None, "20 euros", amount="other_currency"),
            "fail",
        ),
        (
            "May I apply a credit to your original payment method?",
            observed(None, "", amount="missing"),
            "fail",
        ),
        (
            "May I apply $20?",
            observed(2000, "$20", destination="missing", destination_quote=""),
            "fail",
        ),
        (
            "The $20 can go to your original payment method or to store credit. May I apply it?",
            observed(
                2000,
                "$20",
                destination="conflicting",
                destination_quote="original payment method or to store credit",
            ),
            "fail",
        ),
        (
            "The $20 credit goes to your original payment method. Any other questions?",
            observed(2000, "$20", permission="missing", permission_quote=""),
            "fail",
        ),
        (
            "That amount could go to your original payment method. May I apply it?",
            observed(None, "That amount", amount="unclear"),
            "review",
        ),
    ],
)
def test_full_offer_assessment(words, reading, status):
    case, trace = offer_case(text=words, observation=reading)
    assert grade(case, trace)["status"] == status


def test_missing_unbound_or_malformed_review_cannot_pass_even_with_the_right_metadata():
    case, trace = offer_case()
    for edit in (
        lambda t: t.pop("credit_reviews"),
        lambda t: t["credit_reviews"]["1"].update(reply="A different reply with the same amount"),
        lambda t: t["credit_reviews"]["1"].update(model="unrelated-model"),
        lambda t: t["credit_reviews"]["1"]["observation"]["amount"].update(quote="invented"),
        lambda t: t["credit_reviews"]["1"]["observation"].update(amount_cents=True),
        lambda t: t["credit_reviews"]["1"].pop("observation"),
    ):
        variant = deepcopy(trace)
        edit(variant)
        outcome = grade(case, variant)
        assert outcome["status"] == "review" and not outcome["pass"] and outcome["failures"] == []
        assert outcome["needs_review"] and outcome["dimensions"]["guidance"] is None


@pytest.mark.parametrize(
    "money,bad_citation",
    [
        ("$20.99", "$20"),
        ("$200", "$20"),
        ("$20,000", "$20"),
        ("$20.99", "?"),
        ("$20.99", "twenty dollars"),
    ],
)
def test_fabricated_partial_or_punctuation_only_amount_evidence_goes_to_review(money, bad_citation):
    # A defective observer reports $20, citing a prefix, punctuation, or words absent from the reply.
    words = f"May I apply {money} to your original payment method?"
    case, trace = offer_case(text=words, observation=observed(2000, bad_citation))
    verdict = grade(case, trace)
    assert verdict["status"] == "review" and "Invalid amount evidence" in str(
        verdict["needs_review"]
    )


def test_missing_current_receipt_and_known_ineligible_or_replaced_quote_are_distinct():
    case, trace = offer_case()
    trace["events"][1]["result"].pop("amount")
    assert grade(case, trace)["status"] == "review"
    trace["events"].append(trace["events"].pop(1))  # A future receipt cannot verify the past offer.
    assert "no preceding credit eligibility receipt" in str(grade(case, trace)["needs_review"])
    case, trace = offer_case()
    trace["events"][1]["result"].update(eligible=False)
    assert "no current eligible credit quote" in str(grade(case, trace)["failures"])
    trace["events"][1]["result"].update(eligible=True)
    trace["events"].insert(
        2,
        {
            "type": "tool",
            "turn": 1,
            "name": "check_replacement_availability",
            "result": {"status": "ok", "offer_id": "REPL-LAMP-1"},
            "args": {},
        },
    )
    assert "no current eligible credit quote" in str(grade(case, trace)["failures"])


def test_direct_replay_fails_an_error_trace_and_malformed_guidance():
    case, trace = offer_case()
    trace.update(status="error", error="Backend stopped after recording this reply")
    assert grade(case, trace)["failures"] == [trace["error"]]
    trace.pop("status")
    trace["events"][-1]["reply"] = None
    assert grade(case, trace)["status"] == "fail"


def test_historical_trace_keeps_its_recorded_grade_but_replay_requires_new_evidence():
    saved = json.loads(Path(__file__).with_name("results.json").read_text())
    rows = next(
        value
        for value in saved.values()
        if isinstance(value, list) and value and "events" in value[0]
    )
    row = next(
        row
        for row in rows
        if row["case"] == "credit_counteroffer" and row["model"] == "gpt-6.1-terra"
    )
    original = deepcopy(row)
    result = grade(
        CASES["credit_counteroffer"], {"events": row["events"], "effects": row["ledger"]}
    )
    assert result["status"] == "review" and len(result["needs_review"]) == 2 and row == original
