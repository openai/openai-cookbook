from datetime import UTC, datetime, timedelta
from decimal import Decimal

from agentic_commerce.models import CommercePolicy, PurchaseRequest
from agentic_commerce.policy import PolicyEngine

NOW = datetime(2026, 8, 21, 8, 0, tzinfo=UTC)


def _engine() -> PolicyEngine:
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


def _authorize(issued_at: datetime):
    return _engine().authorize_challenge(
        _request(),
        merchant_domain="merchant.invalid",
        network="eip155:84532",
        currency="USDC",
        amount=Decimal("0.05"),
        approval=None,
        issued_at=issued_at,
        expires_at=NOW + timedelta(minutes=5),
        now=NOW,
    )


def test_future_issued_challenge_is_denied() -> None:
    decision = _authorize(NOW + timedelta(seconds=1))

    assert decision.allowed is False
    assert decision.code == "challenge_not_yet_valid"


def test_challenge_becomes_valid_at_issued_at() -> None:
    decision = _authorize(NOW)

    assert decision.allowed is True
    assert decision.code == "authorized"
