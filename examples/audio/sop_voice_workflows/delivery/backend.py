"""Responses requests for Blossom Store's SOP and consent check."""

import asyncio
import hashlib
import json
from pathlib import Path
import time

from . import consent, credit_grade
from .store import TOOLS

ROOT = Path(__file__).resolve().parent
DEFAULT_BACKEND_MODEL = "gpt-6.1-terra"
RULES = (ROOT / "backend_prompt.txt").read_text() + "\n\n" + (ROOT / "SOP.md").read_text()
FUNCTIONS = [
    {"type": "function", **{k: t[k] for k in ("name", "description", "parameters", "strict")}}
    for t in TOOLS.values()
]
OUTPUT = {
    "type": "object",
    "properties": {
        "reply": {"type": "string"},
        "offer_kind": {"type": "string", "enum": ["none", "credit", "replacement"]},
        "offer_ref": {"type": "string"},
    },
    "required": ["reply", "offer_kind", "offer_ref"],
    "additionalProperties": False,
}


def digest(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def request(model, conversation, exchanges):
    return {
        "model": model,
        "instructions": RULES,
        "input": [
            {
                "role": "user",
                "content": json.dumps({"call_history": conversation}, ensure_ascii=False),
            }
        ]
        + exchanges,
        "reasoning": {"effort": "low"},
        "store": False,
        "include": ["reasoning.encrypted_content"],
        "tools": FUNCTIONS,
        "parallel_tool_calls": False,
        "tool_choice": "auto",
        "text": {
            "format": {
                "type": "json_schema",
                "name": "store_guidance",
                "strict": True,
                "schema": OUTPUT,
            }
        },
    }


def parse_model(body, model):
    if body.get("status") != "completed" or body.get("model") != model:
        raise ValueError(
            f"Unexpected Responses status/model: {body.get('status')} / {body.get('model')}"
        )
    output = body["output"]
    items = [x for x in output if x["type"] != "reasoning"]
    if len(items) != 1:
        raise ValueError("Expected one tool proposal or final guidance")
    item = items[0]
    if item["type"] == "function_call":
        # In a completed HTTP response, the function item's own status is optional.
        if item.get("status", "completed") != "completed":
            raise ValueError("The function call was incomplete")
        return {
            "type": "call",
            "name": item["name"],
            "args": json.loads(item["arguments"]),
            "call_id": item["call_id"],
            "continuation": output,
        }
    if item["type"] != "message" or item.get("status") != "completed":
        raise ValueError("The guidance message was incomplete")
    parts = item["content"]
    if len(parts) != 1 or parts[0]["type"] != "output_text":
        raise ValueError("Expected a final guidance message")
    msg = json.loads(parts[0]["text"])
    if (
        not isinstance(msg, dict)
        or set(msg) != set(OUTPUT["required"])
        or not all(isinstance(v, str) for v in msg.values())
        or not msg["reply"].strip()
        or msg["offer_kind"] not in OUTPUT["properties"]["offer_kind"]["enum"]
        or bool(msg["offer_ref"].strip()) != (msg["offer_kind"] != "none")
    ):
        raise ValueError("Malformed backend guidance")
    return {"type": "reply", **msg}


def conversation_context(history):
    """Give short references in the offer their conversational context."""
    lines = [f"{entry['speaker']}: {entry['words']}" for entry in history if "speaker" in entry]
    return "\n".join(lines[-4:])


async def dispatch_tool(store, name, args, *, revision, call_id, send, step, on_review):
    async def review(evidence):
        decision = "unavailable"
        receipt = {}
        audit = {}
        try:
            row, receipt = await asyncio.wait_for(
                send(consent.request(evidence), revision, step), timeout=12
            )
            if row.get("type") == "consent" and row.get("decision") in consent.DECISIONS:
                decision = row["decision"]
                audit = {
                    key: row[key] for key in ("model_decision", "spoken_evidence") if key in row
                }
        except (TimeoutError, OSError) as exc:
            receipt = {"requested_model": consent.MODEL, "error": type(exc).__name__}
        on_review(
            {"decision": decision, "evidence": evidence, "tool": name, "call_id": call_id, **audit},
            receipt,
        )
        return decision

    return await store.dispatch(name, args, revision=revision, call_id=call_id, review=review)


async def http_sender(http, req, turn, step):
    begin = time.perf_counter()
    receipt = {
        "turn": turn,
        "step": step,
        "requested_model": req["model"],
        "purpose": req["text"]["format"]["name"],
        "request_sha256": digest(req),
    }
    try:
        async with http.post("https://api.openai.com/v1/responses", json=req) as response:
            receipt.update(http=response.status, request_id=response.headers.get("x-request-id"))
            if response.status != 200:
                # Error bodies can include the invalid credential or other request data.
                return {"type": "error", "error": f"Responses returned HTTP {response.status}"}, {
                    **receipt,
                    "ms": (time.perf_counter() - begin) * 1000,
                }
            body = await response.json()
            receipt.update(id=body.get("id"), model=body.get("model"), usage=body.get("usage"))
        fmt = req["text"]["format"]
        if fmt["name"] == "offer_consent":
            row = consent.parse(body, json.loads(req["input"][0]["content"]))
        elif fmt["name"] == credit_grade.FORMAT:
            row = credit_grade.parse(body)
        else:
            row = parse_model(body, req["model"])
    except Exception as exc:
        row = {"type": "error", "error": f"Responses request failed ({type(exc).__name__})"}
    receipt["ms"] = (time.perf_counter() - begin) * 1000
    return row, receipt
