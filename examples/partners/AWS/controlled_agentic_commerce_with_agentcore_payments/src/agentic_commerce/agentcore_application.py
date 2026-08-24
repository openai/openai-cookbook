"""Application-owned authorization around the AgentCore x402 adapter."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Literal

from pydantic import Field

from .agentcore_payments import (
    AgentCorePaymentChallenge,
    AgentCoreX402Client,
    AuthorizationCallback,
)
from .audit import AuditTrail, Clock, utc_now
from .errors import AgentCorePaymentError, PolicyDenied
from .models import (
    ApprovalGrant,
    AuditEvent,
    AuditEventType,
    AuthorizationDecision,
    FrozenModel,
    PurchaseRequest,
)
from .policy import PolicyEngine

AgentCoreClientFactory = Callable[[AuthorizationCallback], AgentCoreX402Client]


class AgentCoreAccessResult(FrozenModel):
    """Sanitized application evidence for one paid testnet access."""

    status: Literal["completed"] = "completed"
    request_id: str
    merchant: str
    status_code: int = Field(ge=200, lt=300)
    content_type: str | None = None
    response_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    response_bytes: int = Field(ge=0)
    payment_attempts: int = Field(ge=1)
    challenge: AgentCorePaymentChallenge
    authorization: AuthorizationDecision
    audit_events: tuple[AuditEvent, ...]


class AgentCoreAuthorizedApplication:
    """Own policy, approval, budget reservation, and audit state."""

    def __init__(
        self,
        *,
        policy: PolicyEngine,
        client_factory: AgentCoreClientFactory,
        audit: AuditTrail | None = None,
        clock: Clock = utc_now,
    ) -> None:
        self.policy = policy
        self.client_factory = client_factory
        self.audit = audit or AuditTrail()
        self._clock = clock

    def access(
        self,
        request: PurchaseRequest,
        *,
        approval: ApprovalGrant | None,
        now: datetime | None = None,
    ) -> AgentCoreAccessResult:
        """Access one resource after challenge-specific authorization."""

        fixed_now = now
        preflight_now = fixed_now or self._clock()
        self.audit.append(
            request_id=request.request_id,
            event_type=AuditEventType.RESOURCE_REQUESTED,
            detail={
                "resource_url": str(request.resource_url),
                "purpose": request.purpose,
            },
        )
        preflight = self.policy.preflight(request, now=preflight_now)
        if not preflight.allowed:
            self._deny(request, preflight)

        authorized: list[tuple[AgentCorePaymentChallenge, AuthorizationDecision]] = []

        def authorize_challenge(
            challenge: AgentCorePaymentChallenge,
        ) -> None:
            authorization_now = fixed_now or self._clock()
            self.audit.append(
                request_id=request.request_id,
                event_type=AuditEventType.PAYMENT_REQUIRED,
                detail={
                    "amount": str(challenge.amount),
                    "currency": challenge.currency,
                    "merchant_domain": challenge.merchant,
                    "network": challenge.network,
                },
            )
            decision = self.policy.authorize_challenge(
                request,
                merchant_domain=challenge.merchant,
                network=challenge.network,
                currency=challenge.currency,
                amount=challenge.amount,
                approval=approval,
                expires_at=challenge.expires_at,
                now=authorization_now,
            )
            self.audit.append(
                request_id=request.request_id,
                event_type=AuditEventType.AUTHORIZATION_CHECKED,
                detail={
                    "allowed": decision.allowed,
                    "code": decision.code,
                    "requires_human_approval": (decision.requires_human_approval),
                },
            )
            if not decision.allowed:
                self._deny(request, decision)

            # Reserve the amount before proof generation. A transport failure
            # must not make a potentially spent amount available again.
            self.policy.record_spend(
                request.idempotency_key,
                challenge.amount,
            )
            authorized.append((challenge, decision))

        client = self.client_factory(authorize_challenge)
        result = client.fetch(
            str(request.resource_url),
            client_token=request.idempotency_key,
        )
        if not authorized:
            raise AgentCorePaymentError(
                "payment_challenge_not_observed",
                "The merchant did not present an authorized payment challenge.",
            )
        if not result.payment_attempted or result.payment_attempts < 1:
            raise AgentCorePaymentError(
                "payment_not_attempted",
                "The paid testnet resource was not accessed through the "
                "approved payment path.",
            )
        if result.status_code != 200:
            raise AgentCorePaymentError(
                "paid_resource_unavailable",
                "The merchant did not return the expected paid resource.",
            )

        self.audit.append(
            request_id=request.request_id,
            event_type=AuditEventType.PAYMENT_ATTEMPTED,
            detail={
                "idempotency_key": request.idempotency_key,
                "attempts": result.payment_attempts,
            },
        )
        self.audit.append(
            request_id=request.request_id,
            event_type=AuditEventType.CONTENT_RETURNED,
            detail={
                "merchant_domain": result.merchant,
                "status_code": result.status_code,
                "response_sha256": result.response_sha256,
            },
        )
        challenge, decision = authorized[-1]
        return AgentCoreAccessResult(
            request_id=request.request_id,
            merchant=result.merchant,
            status_code=result.status_code,
            content_type=result.content_type,
            response_sha256=result.response_sha256,
            response_bytes=result.response_bytes,
            payment_attempts=result.payment_attempts,
            challenge=challenge,
            authorization=decision,
            audit_events=self.audit.for_request(request.request_id),
        )

    def _deny(
        self,
        request: PurchaseRequest,
        decision: AuthorizationDecision,
    ) -> None:
        self.audit.append(
            request_id=request.request_id,
            event_type=AuditEventType.REQUEST_DENIED,
            detail={"code": decision.code},
        )
        raise PolicyDenied(decision.code, decision.reason)
