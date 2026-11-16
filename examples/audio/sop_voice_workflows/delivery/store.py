"""Call-scoped Blossom Store tools. Only the five declared operations are callable."""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation
import json
import math
from pathlib import Path
from threading import RLock

TOOLS = {t["name"]: t for t in json.loads(Path(__file__).with_name("tools.json").read_text())}
WRITE_TOOLS = {"register_credit": "credit", "create_replacement": "replacement"}
_NEEDS_REVIEW = object()
ORDER_ID = "ORD-100101"
ITEM_ID = "LAMP-1"
ITEM = "Desk lamp"


def rejected(reason):
    return {"status": "rejected", "reason": reason}


class Store:
    """Model proposes a tool. The application checks scope, freshness and write identity."""

    def __init__(self, scenario: dict):
        self.shipping_status = scenario.get("shipping_status", "delivered")
        self.in_stock = scenario.get("in_stock", True)
        self.late_hours = scenario.get("late_hours", 48)
        if (
            self.shipping_status not in {"delivered", "in_transit"}
            or type(self.in_stock) is not bool
        ):
            raise ValueError("Invalid shipping status or stock availability")
        if (
            type(self.late_hours) not in (int, float)
            or not math.isfinite(self.late_hours)
            or self.late_hours < 0
        ):
            raise ValueError("Verified lateness must be a finite nonnegative number of hours")
        try:
            self.total = Decimal(str(scenario.get("total", 124.70)))
            if (
                not self.total.is_finite()
                or self.total <= 0
                or self.total.quantize(Decimal("0.01")) != self.total
            ):
                raise ValueError("Order total must be positive USD with at most two decimals")
        except InvalidOperation as exc:
            raise ValueError("Invalid order total") from exc
        self.credit_amount = min(self.total, Decimal("20"))
        self.fail_tool = scenario.get("fail_tool")
        self.unknown_tool = scenario.get("unknown_tool")
        if self.fail_tool is not None and self.fail_tool not in TOOLS:
            raise ValueError("Unknown failure fixture tool")
        if self.unknown_tool is not None and self.unknown_tool not in WRITE_TOOLS:
            raise ValueError("Only a write can lose its acknowledgment")
        if self.fail_tool is not None and self.fail_tool == self.unknown_tool:
            raise ValueError("Choose one outcome for a given tool")
        self.revision = 0
        self.log = []
        self._verified = False
        self._active_offer = None  # (kind, reference) for this selected order
        self._presented = None  # Actual offer words and the revision in which they were presented.
        self._offer_terms = {}
        self._caller_reply = ""
        self._evidence_version = 0
        self._responses = {}
        self._outcomes = {}
        self._effects = []
        self._lock = RLock()

    def new_turn(self, caller_reply: str = "") -> int:
        with self._lock:
            self.revision += 1
            self._caller_reply = caller_reply
            self._evidence_version += 1
            return self.revision

    def update_reply(self, revision: int, words: str):
        """Invalidate pending reviews when more speech or a revised transcript arrives."""
        with self._lock:
            if revision == self.revision and words != self._caller_reply:
                self._caller_reply = words
                self._evidence_version += 1

    def is_current_reply(self, revision: int, words: str) -> bool:
        with self._lock:
            return self.revision == revision and bool(words.strip()) and self._caller_reply == words

    def present(self, kind: str, ref: str, *, revision: int, words: str, context: str = "") -> bool:
        """Record what was presented. The review checks whether it contains the verified terms."""
        with self._lock:
            if revision != self.revision or self._active_offer != (kind, ref) or not words.strip():
                return False
            self._presented = (revision, words, context)
            self._evidence_version += 1
            return True

    def snapshot(self) -> dict:
        with self._lock:
            return {"revision": self.revision, "effects": deepcopy(self._effects)}

    async def dispatch(self, name, args, *, revision, call_id, review):
        """Review a new write outside the lock, then recheck the evidence before committing."""
        with self._lock:
            result = self._call(name, args, revision, call_id, _NEEDS_REVIEW)
            if result is not _NEEDS_REVIEW:
                return result  # Reads, invalid requests and retries are already resolved.
            version = self._evidence_version
            _, spoken, context = self._presented
            evidence = {
                "verified_offer": {"kind": WRITE_TOOLS[name], **self._offer_terms},
                "preceding_context": context,
                "offer_as_spoken": spoken,
                "caller_reply": self._caller_reply,
            }
        decision = await review(evidence)
        with self._lock:
            if self._evidence_version != version:
                decision = "superseded"
            return self._call(name, args, revision, call_id, decision)

    def call(self, name: str, args: dict, *, revision: int, call_id: str) -> dict:
        """Read tools and replay known outcomes. New writes require dispatch's semantic review."""
        with self._lock:
            return self._call(name, args, revision, call_id, None)

    def _call(self, name, args, revision, call_id, decision):
        # Called under the lock by both entry points.
        if revision != self.revision or decision == "superseded":
            result = {"status": "stale", "reason": "The caller's reply or the offer has changed."}
        elif (
            name not in TOOLS
            or not isinstance(args, dict)
            or not isinstance(call_id, str)
            or not call_id
        ):
            result = rejected("Unknown tool, invalid arguments, or missing call ID.")
        elif call_id in self._responses:
            old_name, old_args, old_revision, original = self._responses[call_id]
            result = (
                original
                if (name, args, revision) == (old_name, old_args, old_revision)
                else rejected("The call ID was reused for different input.")
            )
        else:
            required = TOOLS[name]["parameters"]["required"]
            if set(args) != set(required) or any(
                not isinstance(v, str) or not v.strip() for v in args.values()
            ):
                result = rejected("Arguments do not match the tool definition.")
            else:
                result = self._execute(name, args, decision)
            if result is _NEEDS_REVIEW:
                return result  # The proposed action has no outcome to log or cache yet.
            self._responses[call_id] = (name, deepcopy(args), revision, deepcopy(result))
        self.log.append(
            {
                "call_id": call_id,
                "name": name,
                "args": deepcopy(args),
                "revision": revision,
                "result": deepcopy(result),
            }
        )
        return deepcopy(result)

    def _select_offer(self, kind: str, ref: str | None, **terms) -> None:
        next_offer = (kind, ref) if ref is not None else None
        if self._active_offer != next_offer or self._offer_terms != terms:
            self._active_offer = next_offer
            self._offer_terms = terms
            self._presented = None
            self._evidence_version += 1

    def _execute(self, name, args, decision):
        if name in WRITE_TOOLS:
            field = "quote_id" if name == "register_credit" else "offer_id"
            return self._write(name, args[field], decision)
        if self.fail_tool == name:
            if name == "get_order":
                self._verified = False
            self._select_offer("", None)
            return {
                "status": "failed",
                "reason": "The lookup failed. Contact Blossom Store support.",
            }
        if name == "get_order":
            self._verified = True
            update = (
                "Carrier marked the parcel delivered."
                if self.shipping_status == "delivered"
                else "The carrier reports the parcel is in transit."
            )
            return {
                "status": "ok",
                "order_id": ORDER_ID,
                "item_id": ITEM_ID,
                "item": ITEM,
                "shipping_status": self.shipping_status,
                "tracking_update": update,
                "estimated_delivery": None,
                "late_hours": self.late_hours,
                "total": float(self.total),
                "currency": "USD",
            }
        if not self._verified:
            return rejected("Retrieve the selected order first.")
        if name == "check_credit_eligibility":
            eligible = self.late_hours > 24
            amount = self.credit_amount
            dollar_text = f"{amount:.2f}".removesuffix(".00")
            ref = f"CREDIT-{dollar_text}" if eligible else None
            terms = {
                "amount": float(amount) if eligible else None,
                "currency": "USD",
                "payment_method": "original payment method",
            }
            self._select_offer("credit", ref, **terms)
            return {
                "status": "ok",
                "order_id": ORDER_ID,
                "eligible": eligible,
                "quote_id": ref,
                **terms,
                "reason": (
                    "Verified lateness exceeds 24 hours."
                    if eligible
                    else "A credit requires more than 24 hours of verified lateness."
                ),
            }
        if args["item_id"] != ITEM_ID:
            self._select_offer("", None)
            return rejected("This item is outside the selected order.")
        delivered = self.shipping_status == "delivered"
        available = delivered and self.in_stock
        ref = "REPL-LAMP-1" if available else None
        terms = {
            "item": ITEM,
            "cost": 0 if available else None,
            "currency": "USD",
            "destination": "original order address" if available else None,
        }
        self._select_offer("replacement", ref, **terms)
        reason = (
            "The selected order has no verified delivery."
            if not delivered
            else (
                "The same item is out of stock."
                if not self.in_stock
                else "The same item is in stock."
            )
        )
        return {
            "status": "ok",
            "order_id": ORDER_ID,
            "available": available,
            "offer_id": ref,
            "item_id": ITEM_ID,
            "damage_description": args["damage_description"],
            **terms,
            "reason": reason,
        }

    def _write(self, name, ref, decision):
        kind = WRITE_TOOLS[name]
        identity = (kind, ref)
        if identity in self._outcomes:
            result = dict(self._outcomes[identity])
            if result["status"] in {"created", "registered"}:
                result["status"] = "already_" + result["status"]
            return result
        if not self._verified or identity != self._active_offer:
            return rejected("This is not the current offer for the selected order.")
        if (
            not self._presented
            or self._presented[0] != self.revision - 1
            or not self._caller_reply.strip()
        ):
            return rejected("Restate the offer and ask permission before submitting it.")
        if decision is _NEEDS_REVIEW:
            return _NEEDS_REVIEW
        if decision == "unavailable":
            return rejected(
                "Consent could not be verified. Leave the offer open and offer support."
            )
        if decision != "accepted":
            return rejected(
                "No clear acceptance of the complete offer. Respond to the caller and ask permission if appropriate."
            )
        if self.fail_tool == name:
            result = {
                "status": "failed",
                "reason": "The request failed. Contact Blossom Store support.",
            }
        else:
            # The store applied the change even if its reply to the app was lost.
            self._effects.append({"kind": kind, "ref": ref})
            if self.unknown_tool == name:
                result = {
                    "status": "unconfirmed",
                    "reason": "The outcome could not be confirmed. Do not resubmit. Contact support.",
                }
            elif kind == "credit":
                result = {
                    "status": "registered",
                    "order_id": ORDER_ID,
                    "quote_id": ref,
                    "refund_id": "RF001",
                    "amount": float(self.credit_amount),
                    "currency": "USD",
                    "payment_method": "original payment method",
                }
            else:
                result = {
                    "status": "created",
                    "order_id": ORDER_ID,
                    "offer_id": ref,
                    "replacement_id": "RP001",
                    "item": ITEM,
                    "cost": 0,
                    "currency": "USD",
                    "destination": "original order address",
                }
        self._outcomes[identity] = result
        return result
