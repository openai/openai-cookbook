import asyncio
from concurrent.futures import ThreadPoolExecutor

import pytest
from jsonschema import Draft202012Validator

from delivery.store import Store, TOOLS

DAMAGE = {"item_id": "LAMP-1", "damage_description": "The shade arrived broken."}
CREDIT = ("credit", "check_credit_eligibility", {}, "register_credit", {"quote_id": "CREDIT-20"})
REPLACEMENT = (
    "replacement",
    "check_replacement_availability",
    DAMAGE,
    "create_replacement",
    {"offer_id": "REPL-LAMP-1"},
)


def call(store, name, args=None, *, rev=None, cid=None, reply=None, decision="accepted"):
    args = {} if args is None else args
    if rev is None:
        rev = store.revision
    if cid is None:
        cid = f"call-{len(store.log)}"
    if reply is not None:
        store.update_reply(rev, reply)

    async def reviewed(evidence):
        return decision  # This fixture controls the verdict to exercise the write boundary.

    out = asyncio.run(store.dispatch(name, args, revision=rev, call_id=cid, review=reviewed))
    Draft202012Validator(TOOLS[name]["returns"]).validate(out)
    return out


def present(store, kind, ref, *, revision):
    words = (
        f"May I apply a ${store.credit_amount:.2f} credit to your original payment method?"
        if kind == "credit"
        else "May I send a free replacement desk lamp to your original address?"
    )
    return store.present(kind, ref, revision=revision, words=words)


def present_offer(store, case):
    kind, read, args, _, write_args = case
    store.new_turn()
    call(store, "get_order")
    assert call(store, read, args)["status"] == "ok"
    assert present(store, kind, next(iter(write_args.values())), revision=store.revision)


def test_tool_schemas_are_strict_and_only_include_five_operations():
    assert set(TOOLS) == {
        "get_order",
        "check_credit_eligibility",
        "register_credit",
        "check_replacement_availability",
        "create_replacement",
    }
    for tool in TOOLS.values():
        assert set(tool) == {"name", "description", "strict", "parameters", "returns"}
        assert tool["strict"] is True
        schema = tool["parameters"]
        Draft202012Validator.check_schema(schema)
        Draft202012Validator.check_schema(tool["returns"])
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == set(schema["properties"])


def test_order_status_then_damage_creates_one_replacement_on_a_later_turn():
    store = Store({})
    assert store.new_turn() == 1
    order = call(store, "get_order")
    assert (order["item_id"], order["shipping_status"]) == ("LAMP-1", "delivered")
    assert "delivered" in order["tracking_update"] and order["estimated_delivery"] is None
    assert store.snapshot()["effects"] == []

    assert store.new_turn() == 2
    offer = call(store, REPLACEMENT[1], DAMAGE)
    assert (offer["offer_id"], offer["item"], offer["cost"], offer["destination"]) == (
        "REPL-LAMP-1",
        "Desk lamp",
        0,
        "original order address",
    )
    assert present(store, "replacement", offer["offer_id"], revision=2)
    assert call(store, REPLACEMENT[3], REPLACEMENT[4])["status"] == "rejected"
    assert store.new_turn() == 3
    assert (
        call(store, REPLACEMENT[3], REPLACEMENT[4], reply="Yes, send the replacement.")["status"]
        == "created"
    )
    assert store.snapshot()["effects"] == [{"kind": "replacement", "ref": "REPL-LAMP-1"}]
    assert [e["name"] for e in store.log] == [
        "get_order",
        "check_replacement_availability",
        "create_replacement",
        "create_replacement",
    ]


@pytest.mark.parametrize("case", [CREDIT, REPLACEMENT], ids=["credit", "replacement"])
def test_missing_presentation_wrong_reference_and_stale_write(case):
    kind, read, read_args, write, write_args = case
    store = Store({})
    first = store.new_turn()
    call(store, "get_order")
    assert call(store, read, read_args)["status"] == "ok"
    assert not present(store, kind, "not-the-offer", revision=first)
    second = store.new_turn()
    assert not present(store, kind, next(iter(write_args.values())), revision=first)
    assert call(store, write, write_args)["status"] == "rejected"
    assert present(store, kind, next(iter(write_args.values())), revision=second)
    store.new_turn()
    assert call(store, write, write_args, rev=second)["status"] == "stale"
    assert call(store, write, dict.fromkeys(write_args, "not-the-offer"))["status"] == "rejected"
    assert store.snapshot()["effects"] == []


def test_delayed_read_cannot_replace_current_offer_or_enable_an_older_action():
    store = Store({})
    present_offer(store, CREDIT)
    old = store.revision
    cur = store.new_turn()
    current = call(store, REPLACEMENT[1], DAMAGE)
    assert present(store, "replacement", current["offer_id"], revision=cur)
    assert call(store, "check_credit_eligibility", rev=old)["status"] == "stale"
    assert call(store, "register_credit", CREDIT[4], rev=old)["status"] == "stale"
    assert call(store, "register_credit", CREDIT[4])["status"] == "rejected"
    store.new_turn()
    assert call(store, "create_replacement", REPLACEMENT[4], reply="Yes.")["status"] == "created"
    assert store.snapshot()["effects"] == [{"kind": "replacement", "ref": current["offer_id"]}]


@pytest.mark.parametrize("case", [CREDIT, REPLACEMENT], ids=["credit", "replacement"])
def test_same_call_distinct_calls_and_lost_acknowledgment(case):
    kind, _, _, write, args = case
    store = Store({"unknown_tool": write})
    present_offer(store, case)
    store.new_turn()
    assert call(store, write, args, cid="one", reply="Yes.")["status"] == "unconfirmed"
    assert call(store, write, args, cid="one")["status"] == "unconfirmed"
    assert call(store, write, args, cid="two")["status"] == "unconfirmed"
    assert call(store, write, dict.fromkeys(args, "changed"), cid="one")["status"] == "rejected"
    assert store.snapshot()["effects"] == [{"kind": kind, "ref": next(iter(args.values()))}]
    store.new_turn()
    assert call(store, write, args, cid="three")["status"] == "unconfirmed"
    assert len(store.snapshot()["effects"]) == 1


@pytest.mark.parametrize("case", [CREDIT, REPLACEMENT], ids=["credit", "replacement"])
def test_late_duplicate_delegations_dispatch_once(case):
    kind, _, _, write, args = case
    store = Store({})
    present_offer(store, case)
    store.new_turn()
    with ThreadPoolExecutor(max_workers=2) as pool:
        result = list(
            pool.map(lambda cid: call(store, write, args, cid=cid, reply="Yes."), ["first", "late"])
        )
    first = "created" if kind == "replacement" else "registered"
    assert sorted(r["status"] for r in result) == sorted([first, "already_" + first])
    assert len(store.snapshot()["effects"]) == 1


@pytest.mark.parametrize(
    "hours,total,expected,ref",
    [
        (24, 100, None, None),
        (24.01, 100, 20, "CREDIT-20"),
        (48, 12.50, 12.50, "CREDIT-12.50"),
    ],
)
def test_credit_boundary_and_original_terms(hours, total, expected, ref):
    store = Store({"late_hours": hours, "total": total})
    store.new_turn()
    assert call(store, "check_credit_eligibility")["status"] == "rejected"
    call(store, "get_order")
    res = call(store, "check_credit_eligibility")
    assert (res["eligible"], res["amount"], res["quote_id"]) == (ref is not None, expected, ref)
    assert (res["currency"], res["payment_method"]) == ("USD", "original payment method")
    if ref is not None:
        assert present(store, "credit", ref, revision=store.revision)
        store.new_turn()
        receipt = call(store, "register_credit", {"quote_id": ref}, reply="Yes, go ahead.")
        assert receipt["amount"] == expected and receipt["status"] == "registered"


@pytest.mark.parametrize(
    "scenario,hint",
    [
        ({"shipping_status": "in_transit"}, "no verified delivery"),
        ({"shipping_status": "delivered", "in_stock": False}, "out of stock"),
    ],
)
def test_unavailable_remedy_has_no_offer(scenario, hint):
    store = Store(scenario)
    store.new_turn()
    assert call(store, REPLACEMENT[1], DAMAGE)["status"] == "rejected"
    call(store, "get_order")
    offer = call(store, REPLACEMENT[1], DAMAGE)
    assert not offer["available"] and offer["offer_id"] is None and hint in offer["reason"]
    assert (offer["cost"], offer["destination"]) == (None, None)
    assert not present(store, "replacement", "REPL-LAMP-1", revision=store.revision)
    store.new_turn()
    assert call(store, REPLACEMENT[3], REPLACEMENT[4])["status"] == "rejected"


@pytest.mark.parametrize("name", list(TOOLS))
def test_explicit_tool_failure_schema_and_effect(name):
    store = Store({"fail_tool": name})
    store.new_turn()
    args = {}
    if name != "get_order":
        call(store, "get_order")
        if name == REPLACEMENT[1]:
            args = DAMAGE
        if name in {CREDIT[3], REPLACEMENT[3]}:
            case = CREDIT if name == CREDIT[3] else REPLACEMENT
            present_offer(store, case)
            store.new_turn()
            args = case[4]
    assert call(store, name, args, reply="Yes.")["status"] == "failed"
    assert store.snapshot()["effects"] == []


@pytest.mark.parametrize(
    "name,args",
    [
        ("get_order", {"order_id": "another-order"}),
        ("check_credit_eligibility", {"amount": 35}),
        ("register_credit", {"quote_id": 3}),
        ("create_replacement", {"offer_id": ""}),
        ("check_replacement_availability", {"item_id": "LAMP-1"}),
        ("check_replacement_availability", {"item_id": "LAMP-1", "damage_description": " "}),
        (
            "check_replacement_availability",
            {"item_id": "another-order-item", "damage_description": "broken"},
        ),
    ],
)
def test_bad_arguments_cannot_escape_order_scope(name, args):
    store = Store({})
    store.new_turn()
    call(store, "get_order")
    assert call(store, name, args)["status"] == "rejected"
    assert not store.snapshot()["effects"]


def test_unfinished_offer_and_restated_terms_need_a_subsequent_reply():
    store = Store({})
    store.new_turn()
    call(store, "get_order")
    quote = call(store, "check_credit_eligibility")
    # No presentation receipt for an interrupted first offer.
    interrupted_turn = store.new_turn()
    assert call(store, "register_credit", CREDIT[4])["status"] == "rejected"
    assert present(store, "credit", quote["quote_id"], revision=interrupted_turn)
    clarification_turn = store.new_turn()
    # The workflow restates the terms when the customer asks for a different amount.
    assert present(store, "credit", quote["quote_id"], revision=clarification_turn)
    assert call(store, "register_credit", CREDIT[4])["status"] == "rejected"
    assert store.snapshot()["effects"] == []
    store.new_turn()
    assert call(store, "register_credit", CREDIT[4], reply="Yes.")["status"] == "registered"


@pytest.mark.parametrize("decision", ["not_accepted", "unclear", "unavailable", "unexpected"])
def test_a_new_write_requires_an_accepted_review(decision):
    store = Store({})
    present_offer(store, CREDIT)
    store.new_turn("Yes, but can you make it $35?")
    assert call(store, "register_credit", CREDIT[4], decision=decision)["status"] == "rejected"
    assert store.snapshot()["effects"] == []


def test_a_tool_cannot_supply_its_own_approval():
    store = Store({})
    present_offer(store, CREDIT)
    rev = store.new_turn("That works for me.")
    direct = store.call("register_credit", CREDIT[4], revision=rev, call_id="without-review")
    forged = call(store, "register_credit", {**CREDIT[4], "decision": "accepted"}, cid="forged")
    assert [direct["status"], forged["status"]] == ["rejected", "rejected"]
    assert store.snapshot()["effects"] == []


def test_stale_duplicate_request_does_not_replay_an_earlier_carrier_result():
    store = Store({})
    earlier_turn = store.new_turn()
    assert call(store, "get_order", cid="old-read")["status"] == "ok"
    store.new_turn()
    assert call(store, "get_order", rev=earlier_turn, cid="old-read")["status"] == "stale"
    assert call(store, "get_order", cid="old-read")["status"] == "rejected"


def test_review_gets_actual_amount_spoken_offer_and_entire_current_reply():
    store = Store({"total": 12.50})
    present_offer(store, ("credit", CREDIT[1], {}, CREDIT[3], {"quote_id": "CREDIT-12.50"}))
    revision = store.new_turn("Go ahead and put it back on that card.")
    seen = []

    async def review(evidence):
        seen.append(evidence)
        return "accepted"

    result = asyncio.run(
        store.dispatch(
            "register_credit",
            {"quote_id": "CREDIT-12.50"},
            revision=revision,
            call_id="first",
            review=review,
        )
    )
    assert result["amount"] == 12.5
    assert seen == [
        {
            "verified_offer": {
                "kind": "credit",
                "amount": 12.5,
                "currency": "USD",
                "payment_method": "original payment method",
            },
            "preceding_context": "",
            "offer_as_spoken": "May I apply a $12.50 credit to your original payment method?",
            "caller_reply": "Go ahead and put it back on that card.",
        }
    ]
    assert (
        call(store, "register_credit", {"quote_id": "CREDIT-12.50"}, cid="late")["status"]
        == "already_registered"
    )


def test_a_correction_while_consent_is_being_checked_invalidates_the_decision():
    store = Store({})
    present_offer(store, CREDIT)
    rev = store.new_turn("Go ahead.")

    async def slow_review(evidence):
        assert evidence["caller_reply"] == "Go ahead."
        store.update_reply(rev, "Go ahead. Actually, hold on.")
        return "accepted"

    outcome = asyncio.run(
        store.dispatch(
            CREDIT[3], CREDIT[4], revision=rev, call_id="late-review", review=slow_review
        )
    )
    assert outcome["status"] == "stale" and store.snapshot()["effects"] == []
