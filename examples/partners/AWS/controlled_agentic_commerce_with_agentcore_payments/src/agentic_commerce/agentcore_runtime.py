"""No-call construction helpers for the live AgentCore testnet path."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from .agentcore_application import AgentCoreAuthorizedApplication
from .agentcore_payments import (
    AgentCorePaymentsSettings,
    AgentCoreX402Client,
    AuthorizationCallback,
)
from .models import ApprovalGrant, CommercePolicy, PurchaseRequest
from .policy import PolicyEngine


@dataclass(frozen=True)
class LiveAgentCoreContext:
    application: AgentCoreAuthorizedApplication
    request: PurchaseRequest
    approval: ApprovalGrant


def build_live_agentcore_context(
    settings: AgentCorePaymentsSettings,
    *,
    resource_url: str,
    idempotency_key: str,
    purpose: str,
    now: datetime | None = None,
) -> LiveAgentCoreContext:
    """Build exact-scope policy and approval without making a live call."""

    now = now or datetime.now(UTC)
    amount = Decimal(settings.max_approved_amount_atomic) / Decimal(1_000_000)
    request = PurchaseRequest(
        request_id="request-agentcore-testnet-smoke",
        resource_url=resource_url,
        purpose=purpose,
        idempotency_key=idempotency_key,
    )
    approval = ApprovalGrant(
        approval_id="approval-agentcore-testnet-smoke",
        request_id=request.request_id,
        resource_url=request.resource_url,
        purpose=request.purpose,
        maximum_amount=amount,
        approved_by="interactive-testnet-operator",
        approved_at=now,
        expires_at=now + timedelta(minutes=5),
    )
    policy = PolicyEngine(
        CommercePolicy(
            allowed_merchants=settings.allowed_merchants,
            allowed_purposes=frozenset({purpose}),
            per_request_limit=amount,
            per_run_limit=amount,
            approval_threshold=Decimal(0),
            session_expires_at=now + timedelta(minutes=10),
        )
    )

    def client_factory(
        authorize_challenge: AuthorizationCallback,
    ) -> AgentCoreX402Client:
        return AgentCoreX402Client(
            settings,
            authorize_challenge=authorize_challenge,
        )

    return LiveAgentCoreContext(
        application=AgentCoreAuthorizedApplication(
            policy=policy,
            client_factory=client_factory,
        ),
        request=request,
        approval=approval,
    )
