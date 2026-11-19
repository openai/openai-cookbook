import asyncio
from functools import partial
import json

import pytest

from delivery import consent
from delivery.runner import dispatch_tool, grade, http_sender
from delivery.store import Store


def response(content):
    return {
        "model": consent.MODEL,
        "status": "completed",
        "output": [{"type": "message", "status": "completed", "content": [content]}],
    }


def test_consent_request_has_only_observed_evidence_and_no_tools():
    evidence = {
        "verified_offer": {"kind": "credit", "amount": 20},
        "preceding_context": "",
        "offer_as_spoken": "I can return $20 to the card you used. Shall I issue it?",
        "caller_reply": "That would work.",
    }
    req = consent.request(evidence)
    assert req["store"] is False and "tools" not in req
    assert json.loads(req["input"][0]["content"]) == evidence
    fmt = req["text"]["format"]
    assert fmt["type"] == "json_schema" and fmt["strict"]
    assert fmt["schema"]["required"] == ["spoken_evidence", "decision"]
    assert fmt["schema"]["additionalProperties"] is False
    assert fmt["schema"]["properties"]["decision"]["enum"] == list(consent.DECISIONS)
    expected = {
        "amount": "$20",
        "payment_method": "card you used",
        "permission_request": "Shall I issue it?",
    }
    assert set(fmt["schema"]["properties"]["spoken_evidence"]["required"]) == set(expected)
    raw = json.dumps({"spoken_evidence": expected, "decision": "accepted"})
    assert (
        consent.parse(response({"type": "output_text", "text": raw}), evidence)["decision"]
        == "accepted"
    )


@pytest.mark.parametrize(
    "content",
    [
        {"type": "refusal", "refusal": "Unable to decide"},
        {"type": "output_text", "text": '{"decision":"probably"}'},
        {"type": "output_text", "text": '{"decision":"accepted","quote_id":"CREDIT-35"}'},
    ],
)
def test_refusals_and_malformed_decisions_cannot_authorize_a_write(content):
    with pytest.raises(ValueError):
        consent.parse(
            response(content), {"verified_offer": {"kind": "credit"}, "offer_as_spoken": ""}
        )


def test_a_review_error_leaves_the_ledger_empty():
    store = Store({})
    rev = store.new_turn()
    store.call("get_order", {}, revision=rev, call_id="order")
    quote = store.call("check_credit_eligibility", {}, revision=rev, call_id="offer")
    store.present(
        "credit", quote["quote_id"], revision=rev, words="May I credit $20 to your original card?"
    )
    rev = store.new_turn("That works for me.")
    events = []

    async def offline_error(req, turn, step):
        return {"type": "error", "error": "service unavailable"}, {"http": 503}

    result = asyncio.run(
        dispatch_tool(
            store,
            "register_credit",
            {"quote_id": quote["quote_id"]},
            revision=rev,
            call_id="write",
            send=offline_error,
            step=0,
            on_review=lambda event, receipt: events.append((event, receipt)),
        )
    )
    assert events[0][0]["decision"] == "unavailable" and events[0][1]["http"] == 503
    assert result["status"] == "rejected" and store.snapshot()["effects"] == []


def test_missing_spoken_term_blocks_a_model_yes():
    proof = {
        "item": "another desk lamp",
        "total_replacement_charge": None,
        "destination": "original order address",
        "permission_request": "Should I send it?",
    }
    raw = json.dumps({"spoken_evidence": proof, "decision": "accepted"})
    evidence = {
        "verified_offer": {"kind": "replacement"},
        "offer_as_spoken": "I can send another desk lamp to your original order address. Should I send it?",
    }
    parsed = consent.parse(response({"type": "output_text", "text": raw}), evidence)
    assert parsed["model_decision"] == "accepted" and parsed["decision"] == "unclear"


@pytest.mark.parametrize(
    "spoken",
    [
        "I can return $200 to the card you used. May I do that?",
        "I can return $20.50 to the card you used. May I do that?",
        "I can return $20. May I do that?",
    ],
)
def test_a_model_cannot_invent_or_partially_match_a_quoted_term(spoken):
    evidence = {
        "verified_offer": {"kind": "credit"},
        "offer_as_spoken": spoken,
        "preceding_context": "I can return $20 to the card you used.",
    }
    proof = {
        "amount": "$20",
        "payment_method": "the card you used",
        "permission_request": "May I do that?",
    }
    body = response(
        {
            "type": "output_text",
            "text": json.dumps({"spoken_evidence": proof, "decision": "accepted"}),
        }
    )
    result = consent.parse(body, evidence)
    assert result["model_decision"] == "accepted" and result["decision"] == "unclear"


def test_partial_item_cannot_authorize_a_write_even_in_a_completed_http_response():
    proof = {"amount": "$20", "payment_method": "your card", "permission_request": "May I?"}
    body = response(
        {
            "type": "output_text",
            "text": json.dumps({"spoken_evidence": proof, "decision": "accepted"}),
        }
    )
    body["output"][0]["status"] = "incomplete"
    with pytest.raises(ValueError):
        consent.parse(
            body,
            {"verified_offer": {"kind": "credit"}, "offer_as_spoken": "$20 to your card. May I?"},
        )


def replay_invented_card_quote():
    offer = "I can return $20. Would you like me to arrange it?"
    reply = "Yes, please go ahead."
    proof = {
        "amount": "$20",
        "payment_method": "the card you used",
        "permission_request": "Would you like me to arrange it?",
    }

    class Reviewer:
        status = 200
        headers = {"x-request-id": "offline-quote-review"}

        def post(self, url, *, json):
            self.request = json
            return self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            pass

        async def json(self):
            return response(
                {
                    "type": "output_text",
                    "text": json.dumps({"decision": "accepted", "spoken_evidence": proof}),
                }
            )

    store = Store({})
    turn = store.new_turn()
    store.call("get_order", {}, revision=turn, call_id="order")
    quote = store.call("check_credit_eligibility", {}, revision=turn, call_id="quote")
    assert store.present("credit", quote["quote_id"], revision=turn, words=offer)
    turn = store.new_turn(reply)
    reviewer = Reviewer()
    events = []
    args = {"quote_id": quote["quote_id"]}
    receipt = asyncio.run(
        dispatch_tool(
            store,
            "register_credit",
            args,
            revision=turn,
            call_id="write",
            step=0,
            send=partial(http_sender, reviewer),
            on_review=lambda event, _: events.append(
                {"type": "consent_review", "turn": turn, **event}
            ),
        )
    )
    evidence = json.loads(reviewer.request["input"][0]["content"])
    assert evidence["offer_as_spoken"] == offer and evidence["caller_reply"] == reply
    assert reviewer.request["model"] == consent.MODEL and "tools" not in reviewer.request
    events.append(
        {"type": "tool", "turn": turn, "name": "register_credit", "args": args, "result": receipt}
    )
    case = {
        "expect": {
            "tools": [
                {
                    "name": "register_credit",
                    "turns": [turn],
                    "optional": False,
                    "fields": args,
                    "words": {},
                    "status": "rejected",
                }
            ],
            "effects": [],
            "guidance": {},
        }
    }
    effects = store.snapshot()["effects"]
    return events[0], receipt, effects, grade(case, {"events": events, "effects": effects})


def test_invented_card_quote_cannot_register_credit_for_an_incomplete_offer():
    review, receipt, effects, verdict = replay_invented_card_quote()
    assert (review["model_decision"], review["decision"]) == ("accepted", "unclear")
    assert receipt["status"] == "rejected" and effects == []
    assert verdict["pass"], verdict["failures"]
