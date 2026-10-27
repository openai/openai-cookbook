"""Application-owned receipts for exact, one-time tool approvals."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from dataclasses import asdict, dataclass
from typing import Any


class ReceiptError(RuntimeError):
    """Raised when an approval receipt cannot authorize execution."""


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def action_digest(tool_name: str, tool_call_id: str, raw_arguments: str) -> str:
    arguments = json.loads(raw_arguments)
    if not isinstance(arguments, dict):
        raise ReceiptError("tool arguments must be a JSON object")
    action = {
        "tool_name": tool_name,
        "tool_call_id": tool_call_id,
        "arguments": arguments,
    }
    return hashlib.sha256(_canonical_json(action)).hexdigest()


@dataclass
class ApprovalReceipt:
    receipt_id: str
    tool_call_id: str
    action_digest: str
    reviewer: str
    issued_at: float
    expires_at: float
    signature: str = ""
    consumed_at: float | None = None

    def signed_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("signature")
        payload.pop("consumed_at")
        return payload


class ReceiptLedger:
    """Minimal in-memory ledger; use a transactional store in production."""

    def __init__(self, secret: bytes):
        if len(secret) < 32:
            raise ValueError("APPROVAL_RECEIPT_SECRET must be at least 32 bytes")
        self._secret = secret
        self._by_call_id: dict[str, ApprovalReceipt] = {}

    def _sign(self, receipt: ApprovalReceipt) -> str:
        return hmac.new(
            self._secret,
            _canonical_json(receipt.signed_payload()),
            hashlib.sha256,
        ).hexdigest()

    def issue(
        self,
        *,
        tool_name: str,
        tool_call_id: str,
        raw_arguments: str,
        reviewer: str,
        ttl_seconds: int = 900,
        now: float | None = None,
    ) -> ApprovalReceipt:
        issued_at = time.time() if now is None else now
        receipt = ApprovalReceipt(
            receipt_id=f"approval_{uuid.uuid4().hex}",
            tool_call_id=tool_call_id,
            action_digest=action_digest(tool_name, tool_call_id, raw_arguments),
            reviewer=reviewer,
            issued_at=issued_at,
            expires_at=issued_at + ttl_seconds,
        )
        receipt.signature = self._sign(receipt)
        self._by_call_id[tool_call_id] = receipt
        return receipt

    def consume(
        self,
        *,
        tool_name: str,
        tool_call_id: str,
        raw_arguments: str,
        now: float | None = None,
    ) -> ApprovalReceipt:
        evaluated_at = time.time() if now is None else now
        receipt = self._by_call_id.get(tool_call_id)
        if receipt is None:
            raise ReceiptError("missing approval receipt")
        if not hmac.compare_digest(receipt.signature, self._sign(receipt)):
            raise ReceiptError("invalid approval receipt signature")
        if receipt.consumed_at is not None:
            raise ReceiptError("approval receipt already consumed")
        if evaluated_at > receipt.expires_at:
            raise ReceiptError("approval receipt expired")
        expected = action_digest(tool_name, tool_call_id, raw_arguments)
        if not hmac.compare_digest(receipt.action_digest, expected):
            raise ReceiptError("approval receipt does not match this exact action")

        # Reserve before the side effect. A production store should make this
        # compare-and-set atomic and reconcile an indeterminate provider result.
        receipt.consumed_at = evaluated_at
        return receipt
