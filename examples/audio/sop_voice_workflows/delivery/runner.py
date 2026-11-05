"""Compare two Responses backends on the same order, caller turns, and executable SOP."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import random
import sys
import time

from . import consent, credit_grade
from .backend import (
    DEFAULT_BACKEND_MODEL,
    FUNCTIONS,
    OUTPUT,
    ROOT,
    RULES,
    conversation_context,
    digest,
    dispatch_tool,
    http_sender,
    parse_model,
    request,
)
from .grade import grade
from .store import Store

MODELS = ("gpt-6-luna", DEFAULT_BACKEND_MODEL)


def save(path, value):
    tmp = path.with_suffix(".partial")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(path)


async def reference(req, turn, step):
    """A scripted backend for the preflight only. It goes through the same store and grader."""
    if req["text"]["format"]["name"] == "offer_consent":
        # A fixed verdict for the one offline happy path. Language quality is evaluated with real models.
        return {"type": "consent", "decision": "accepted"}, {}
    lookup = ("get_order", {})
    availability = (
        "check_replacement_availability",
        {"item_id": "LAMP-1", "damage_description": "The base is cracked."},
    )
    create = ("create_replacement", {"offer_id": "REPL-LAMP-1"})
    actions = {
        1: [lookup],
        2: [lookup, ("What part of the lamp is broken?", "none", "")],
        3: [
            availability,
            (
                "I can send the same desk lamp at no cost to your original delivery address. Would you like me to send it?",
                "replacement",
                "REPL-LAMP-1",
            ),
        ],
        4: [create, ("Your replacement was created. Its reference is RP001.", "none", "")],
    }
    item = actions[turn][step]
    if len(item) == 3:
        return {"type": "reply", "reply": item[0], "offer_kind": item[1], "offer_ref": item[2]}, {}
    name, args = item
    call_id = f"reference-{turn}-{step}"
    return {
        "type": "call",
        "name": name,
        "args": args,
        "call_id": call_id,
        "continuation": [
            {
                "type": "function_call",
                "call_id": call_id,
                "name": name,
                "arguments": json.dumps(args),
            }
        ],
    }, {}


async def review_credit_offers(case, trace, send):
    """Attach independent observations after the backend has finished and the ledger is recorded."""
    for turn, rules in case["expect"]["guidance"].items():
        if not any(credit_grade.applies(rule) for rule in rules):
            continue
        replies = [
            event["reply"]
            for event in trace["events"]
            if event["type"] == "guidance"
            and event["turn"] == int(turn)
            and isinstance(event.get("reply"), str)
        ]
        if len(replies) != 1 or not replies[0].strip():
            continue
        reply = replies[0]
        review = {"reply": reply, "model": credit_grade.MODEL}
        trace.setdefault("credit_reviews", {})[turn] = review
        try:
            row, receipt = await send(credit_grade.request(reply), int(turn), None)
            if receipt:
                trace["receipts"].append(receipt)
            if row.get("type") == credit_grade.FORMAT:
                review["observation"] = row["observation"]
            else:
                review["error"] = "Independent reviewer returned no observation"
        except (OSError, TimeoutError) as exc:
            review["error"] = type(exc).__name__


async def play(case, model, send):
    store = Store(case["scenario"])
    events = []
    receipts = []
    history = []
    pending = None
    turn_times = []
    trace = {
        "case": case["id"],
        "model": model,
        "events": events,
        "receipts": receipts,
        "turn_ms": turn_times,
        "input_sha256": digest(
            {
                "scenario": case["scenario"],
                "turns": case["turns"],
                "delay_first_read": case.get("delay_first_read", False),
                "rules": RULES,
                "functions": FUNCTIONS,
                "format": OUTPUT,
                "consent_check": {
                    "model": consent.MODEL,
                    "instructions": consent.INSTRUCTIONS,
                    "required_terms": consent.TERMS,
                },
            }
        ),
    }

    def event(event_type, rev, **kw):
        events.append({"type": event_type, "turn": rev, **kw})

    try:
        for turn, words in enumerate(case["turns"], 1):
            start = time.perf_counter()
            rev = store.new_turn(words)
            assert rev == turn
            event("caller", turn, words=words)
            history.append({"speaker": "caller", "words": words})
            if pending:
                old, call = pending
                late = store.call(call["name"], call["args"], revision=old, call_id=call["call_id"])
                event(
                    "stale_drop",
                    turn,
                    name=call["name"],
                    source_turn=old,
                    call_id=call["call_id"],
                    result=late,
                )
                assert late["status"] == "stale"
                pending = None
            exchanges = []
            for step in range(10):  # Treat a tool loop as a visible failed call.
                req = request(model, history, exchanges)
                row, receipt = await send(req, turn, step)
                if receipt:
                    receipts.append(receipt)
                if row["type"] == "error":
                    raise RuntimeError(row["error"])
                if row["type"] == "reply":
                    msg = {k: row[k] for k in OUTPUT["required"]}
                    event("guidance", turn, **msg)
                    ref = msg["offer_ref"]
                    if msg["offer_kind"] != "none":
                        presented = store.present(
                            msg["offer_kind"],
                            ref,
                            revision=rev,
                            words=msg["reply"],
                            context=conversation_context(history),
                        )
                        event(
                            "presentation",
                            turn,
                            accepted=bool(presented),
                            ref=ref,
                            kind=msg["offer_kind"],
                            source="scripted text delivery",
                        )
                    history.append({"speaker": "agent", "words": msg["reply"]})
                    break
                name, args, call_id = row["name"], row["args"], row["call_id"]
                if (
                    case.get("delay_first_read")
                    and turn == 1
                    and name == "get_order"
                    and pending is None
                ):
                    pending = (rev, row)
                    event("withheld", rev, name=name, args=args, call_id=call_id)
                    history.append(
                        {
                            "application": "A lookup was interrupted before this turn had a verified result or an agent reply."
                        }
                    )
                    break

                def record_review(review, receipt):
                    event("consent_review", rev, **review)
                    if receipt:
                        receipts.append(receipt)

                result = await dispatch_tool(
                    store,
                    name,
                    args,
                    revision=rev,
                    call_id=call_id,
                    send=send,
                    step=step,
                    on_review=record_review,
                )
                event("tool", turn, name=name, args=args, call_id=call_id, result=result)
                # Within one Responses tool loop, return the function output using the API call ID.
                exchanges.extend(row["continuation"])
                exchanges.append(
                    {
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": json.dumps(result),
                    }
                )
            else:
                raise RuntimeError(
                    "Backend did not finish the turn within ten consecutive tool proposals"
                )
            turn_tools = [
                {"tool": e["name"], "arguments": e["args"], "verified_result": e["result"]}
                for e in events
                if e["type"] == "tool" and e["turn"] == turn
            ]
            if turn_tools:
                if history[-1].get("speaker") == "agent":
                    history[-1:-1] = turn_tools
                else:
                    history.extend(turn_tools)
            turn_times.append((time.perf_counter() - start) * 1000)
        trace["status"] = "completed"
    except Exception as exc:
        trace.update(status="error", error=f"{type(exc).__name__}: {exc}")
    trace["effects"] = store.snapshot()["effects"]
    await review_credit_offers(case, trace, send)
    trace["grade"] = grade(case, trace)
    return trace


def token_totals(traces, models):
    totals = {
        model: {"input": 0, "cached": 0, "output": 0, "requests": 0, "unknown_usage": 0}
        for model in models
    }
    for trace in traces:
        for receipt in trace["receipts"]:
            model = receipt.get("requested_model", trace["model"])
            counts = totals.setdefault(
                model, {"input": 0, "cached": 0, "output": 0, "requests": 0, "unknown_usage": 0}
            )
            counts["requests"] += 1
            usage = receipt.get("usage")
            if not usage:
                counts["unknown_usage"] += 1
                continue
            counts["input"] += usage["input_tokens"]
            counts["cached"] += (usage.get("input_tokens_details") or {}).get("cached_tokens", 0)
            counts["output"] += usage["output_tokens"]
    return totals


async def main(args):
    cases = json.loads((ROOT / args.cases).read_text())
    out = Path(args.out)
    ids = (
        {part.strip() for part in args.ids.split(",")}
        if args.ids is not None
        else {c["id"] for c in cases}
    )
    selected = [c for c in cases if c["id"] in ids]
    if len(selected) != len(ids) or not selected or min(args.repeats, args.workers) < 1:
        raise ValueError("Select valid case IDs, one or more repetitions, and one or more workers")
    if args.reference:
        supported = [c for c in selected if c["id"].removeprefix("new_") == "status_to_damage"]
        if len(supported) != 1 or (args.ids is not None and len(selected) != 1):
            raise ValueError("--reference only supports the scripted status_to_damage case")
        out.mkdir(parents=True, exist_ok=False)
        result = await play(supported[0], "reference", reference)
        save(out / "reference.json", result)
        print(json.dumps(result["grade"]))
        return 0 if result["grade"]["pass"] else 1

    from voice.config import api_key

    key = api_key()
    from functools import partial
    import aiohttp

    out.mkdir(parents=True, exist_ok=False)
    pairs = [(n, c) for n in range(1, args.repeats + 1) for c in selected]
    random.Random(1013).shuffle(pairs)
    semaphore = asyncio.Semaphore(args.workers)
    async with aiohttp.ClientSession(
        headers={"Authorization": "Bearer " + key},
        trust_env=True,
        timeout=aiohttp.ClientTimeout(total=120),
    ) as http:

        async def one(model, case, repetition):
            async with semaphore:
                trace = await play(case, model, partial(http_sender, http))
                trace["rep"] = repetition
                save(out / f"{case['id']}__{model}__{repetition}.json", trace)
                print(
                    case["id"],
                    model,
                    repetition,
                    trace["status"],
                    trace["grade"]["status"],
                    flush=True,
                )
                return trace

        jobs = [
            one(model, case, n)
            for i, (n, case) in enumerate(pairs)
            for model in (args.models if i % 2 == 0 else reversed(args.models))
        ]
        traces = await asyncio.gather(*jobs)
    save(out / "usage.json", token_totals(traces, args.models))
    return 0 if all(trace["grade"]["pass"] for trace in traces) else 1


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reference",
        action="store_true",
        help="Run the scripted broken-lamp case without a model or key.",
    )
    parser.add_argument(
        "--cases",
        default="cases.json",
        help="Fixture file relative to this module or an absolute path.",
    )
    parser.add_argument("--ids", help="Comma-separated case IDs. Defaults to the entire suite.")
    parser.add_argument(
        "--models",
        nargs="+",
        choices=MODELS,
        default=[DEFAULT_BACKEND_MODEL],
        help="Blossom Store uses Terra. Pass both names to reproduce the backend comparison.",
    )
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument(
        "--out",
        required=True,
        help="A new directory for recordings of backend events and model usage.",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main(parse_args())))
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
