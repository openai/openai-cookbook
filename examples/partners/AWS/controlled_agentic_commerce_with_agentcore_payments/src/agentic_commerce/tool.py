"""Agents SDK function-tool adapter with pre-bound application authority."""

from __future__ import annotations

import json
from collections.abc import Callable

from agents import FunctionTool, function_tool

from .application import CommerceApplication
from .errors import CommerceError
from .models import (
    AgentPurchaseEvidence,
    ApprovalGrant,
    PurchaseRequest,
    PurchaseResult,
)


def build_x402_fetch_tool(
    application: CommerceApplication,
    *,
    request_id: str,
    idempotency_key: str,
    approval: ApprovalGrant | None = None,
    on_purchase: Callable[[PurchaseResult], None] | None = None,
) -> FunctionTool:
    """Build a tool whose authority is supplied by the application.

    The model can propose a URL and purpose. It cannot mint an approval,
    choose its own spending policy, or access proof/wallet material.
    """

    @function_tool(
        name_override="x402_fetch",
        description_override=(
            "Fetch one paid HTTPS resource through application-controlled "
            "merchant, purpose, spending, approval, and audit policy."
        ),
    )
    def x402_fetch(resource_url: str, purpose: str) -> str:
        try:
            result = application.purchase(
                PurchaseRequest(
                    request_id=request_id,
                    resource_url=resource_url,
                    purpose=purpose,
                    idempotency_key=idempotency_key,
                ),
                approval=approval,
            )
            if on_purchase is not None:
                on_purchase(result)
            evidence = AgentPurchaseEvidence(
                status=result.status,
                report=result.report,
                receipt_id=result.receipt.receipt_id,
                amount=result.receipt.amount,
                currency=result.receipt.currency,
                requires_human_approval=(result.authorization.requires_human_approval),
            )
            return evidence.model_dump_json()
        except CommerceError as exc:
            return json.dumps(
                {
                    "status": "denied",
                    "code": exc.code,
                    "message": str(exc),
                },
                sort_keys=True,
            )

    return x402_fetch
