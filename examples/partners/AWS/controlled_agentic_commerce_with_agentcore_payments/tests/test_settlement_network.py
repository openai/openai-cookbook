from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from agentic_commerce.application import CommerceApplication
from agentic_commerce.errors import ProtocolError
from agentic_commerce.merchant import RESOURCE_URL, SyntheticMerchant
from agentic_commerce.models import ApprovalGrant, CommercePolicy, PurchaseRequest
from agentic_commerce.payments import LocalPaymentProcessor
from agentic_commerce.policy import PolicyEngine

NOW = datetime(2026, 8, 21, 8, 0, tzinfo=UTC)


def test_settlement_network_must_match_local_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payments = LocalPaymentProcessor()
    merchant = SyntheticMerchant(payments, price=Decimal("0.25"), now=NOW)
    policy = PolicyEngine(
        CommercePolicy(
            allowed_merchants=frozenset({"merchant.invalid"}),
            allowed_purposes=frozenset({"supplier_due_diligence"}),
            per_request_limit=Decimal("0.50"),
            per_run_limit=Decimal("1.00"),
            approval_threshold=Decimal("0.10"),
            session_expires_at=NOW + timedelta(minutes=15),
        )
    )
    app = CommerceApplication(
        client=merchant.client(),
        policy=policy,
        payments=payments,
    )
    request = PurchaseRequest(
        request_id="request-001",
        resource_url=RESOURCE_URL,
        purpose="supplier_due_diligence",
        idempotency_key="purchase-001",
    )
    approval = ApprovalGrant(
        approval_id="approval-001",
        request_id=request.request_id,
        resource_url=request.resource_url,
        purpose=request.purpose,
        maximum_amount=Decimal("0.25"),
        approved_by="synthetic-reviewer",
        approved_at=NOW,
        expires_at=NOW + timedelta(minutes=10),
    )

    original_verify = payments.verify

    def verify_with_wrong_network(proof_header: str, requirement):
        settlement = original_verify(proof_header, requirement)
        return settlement.model_copy(update={"network": "eip155:1"})

    monkeypatch.setattr(payments, "verify", verify_with_wrong_network)

    with pytest.raises(ProtocolError) as exc_info:
        app.purchase(request, approval=approval, now=NOW)

    assert exc_info.value.code == "settlement_receipt_mismatch"
