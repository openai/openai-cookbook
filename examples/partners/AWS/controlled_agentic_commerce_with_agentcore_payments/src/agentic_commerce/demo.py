"""Build the deterministic demo used by the notebook and tests."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from .application import CommerceApplication
from .merchant import SyntheticMerchant
from .models import CommercePolicy
from .payments import LocalPaymentProcessor
from .policy import PolicyEngine


def build_demo(
    now: datetime,
) -> tuple[CommerceApplication, SyntheticMerchant, LocalPaymentProcessor]:
    payments = LocalPaymentProcessor()
    merchant = SyntheticMerchant(payments, now=now)
    policy = PolicyEngine(
        CommercePolicy(
            allowed_merchants=frozenset({"merchant.invalid"}),
            allowed_purposes=frozenset({"supplier_due_diligence"}),
            per_request_limit=Decimal("0.50"),
            per_run_limit=Decimal("1.00"),
            approval_threshold=Decimal("0.10"),
            session_expires_at=now + timedelta(minutes=15),
        )
    )
    application = CommerceApplication(
        client=merchant.client(),
        policy=policy,
        payments=payments,
    )
    return application, merchant, payments
