from datetime import UTC, datetime, timedelta
from decimal import Decimal

from agentic_commerce.models import ApprovalGrant, CommercePolicy, PurchaseRequest
from agentic_commerce.policy import PolicyEngine

NOW = datetime(2026, 8, 21, 8, 0, tzinfo=UTC)


def _policy() -> PolicyEngine:
    return PolicyEngine(
        CommercePolicy(
            allowed_merchants=frozenset({"merchant.invalid"}),
            allowed_purposes=frozenset({"supplier_due_diligence"}),
            per_request_limit=Decimal("0.50"),
            per_run_limit=Decimal("1.00"),
            approval_threshold=Decimal("0.10"),
            session_expires_at=NOW + timedelta(minutes=15),
        )
    )


def _request() -> PurchaseRequest:
    return PurchaseRequest(
        request_id="request-001",
        resource_url="https://merchant.invalid/report",
        purpose="supplier_due_diligence",
        idempotency_key="purchase-001",
    )


def _approval(request: PurchaseRequest, *, approved_at: datetime) -> ApprovalGrant:
    return ApprovalGrant(
        approval_id="approval-001",
        request_id=request.request_id,
        resource_url=request.resource_url,
        purpose=request.purpose,
        maximum_amount=Decimal("0.25"),
        approved_by="synthetic-reviewer",
        approved_at=approved_at,
        expires_at=NOW + timedelta(minutes=10),
    )


def _authorize(approved_at: datetime):
    request = _request()
    return _policy().authorize_challenge(
        request,
        merchant_domain="merchant.invalid",
        network="eip155:84532",
        currency="USDC",
        amount=Decimal("0.25"),
        approval=_approval(request, approved_at=approved_at),
        expires_at=NOW + timedelta(minutes=5),
        now=NOW,
    )


def test_future_dated_approval_is_denied() -> None:
    decision = _authorize(NOW + timedelta(seconds=1))

    assert decision.allowed is False
    assert decision.code == "approval_not_yet_valid"
    assert decision.requires_human_approval is True


def test_approval_becomes_valid_at_approved_at() -> None:
    decision = _authorize(NOW)

    assert decision.allowed is True
    assert decision.code == "authorized"
