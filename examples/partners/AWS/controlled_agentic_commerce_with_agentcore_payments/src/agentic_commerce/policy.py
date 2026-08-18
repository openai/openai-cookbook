"""Deterministic application authorization for synthetic paid resources."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from .models import (
    ApprovalGrant,
    AuthorizationDecision,
    CommercePolicy,
    PaymentReceipt,
    PaymentRequired,
    PurchaseRequest,
)


class PolicyEngine:
    """Authorize purchases independently of model reasoning."""

    def __init__(self, policy: CommercePolicy) -> None:
        self.policy = policy
        self._spent_by_idempotency: dict[str, Decimal] = {}

    @property
    def spent(self) -> Decimal:
        return sum(self._spent_by_idempotency.values(), start=Decimal(0))

    def preflight(
        self,
        request: PurchaseRequest,
        *,
        now: datetime | None = None,
    ) -> AuthorizationDecision:
        """Reject unsafe destinations and purposes before any HTTP request."""

        now = now or datetime.now(UTC)
        if request.resource_url.scheme != "https":
            return self._deny("https_required", "Paid resources must use HTTPS.")
        if request.resource_url.host not in self.policy.allowed_merchants:
            return self._deny(
                "merchant_not_allowed",
                "The merchant is not in the application allowlist.",
            )
        if request.purpose not in self.policy.allowed_purposes:
            return self._deny(
                "purpose_not_allowed",
                "The requested purchase purpose is not allowed.",
            )
        if now >= self.policy.session_expires_at:
            return self._deny(
                "session_expired",
                "The application payment session has expired.",
            )
        return AuthorizationDecision(
            allowed=True,
            code="preflight_allowed",
            reason="The request destination and purpose satisfy preflight policy.",
            requires_human_approval=False,
        )

    def authorize(
        self,
        request: PurchaseRequest,
        required: PaymentRequired,
        *,
        approval: ApprovalGrant | None,
        now: datetime | None = None,
    ) -> AuthorizationDecision:
        now = now or datetime.now(UTC)
        requirement = required.accepts[0]
        host = request.resource_url.host
        amount = requirement.decimal_amount

        preflight = self.preflight(request, now=now)
        if not preflight.allowed:
            return preflight
        if required.resource.url != request.resource_url:
            return self._deny(
                "resource_mismatch",
                "The payment challenge refers to a different resource.",
            )
        if requirement.merchant_domain != host:
            return self._deny(
                "merchant_mismatch",
                "The payment challenge merchant does not match the URL.",
            )
        return self.authorize_challenge(
            request,
            merchant_domain=requirement.merchant_domain,
            network=requirement.network,
            currency=requirement.currency,
            amount=amount,
            approval=approval,
            expires_at=requirement.expires_at,
            now=now,
        )

    def authorize_challenge(
        self,
        request: PurchaseRequest,
        *,
        merchant_domain: str,
        network: str,
        currency: str,
        amount: Decimal,
        approval: ApprovalGrant | None,
        expires_at: datetime | None = None,
        now: datetime | None = None,
    ) -> AuthorizationDecision:
        """Authorize normalized challenge facts from any x402 transport."""

        now = now or datetime.now(UTC)
        host = request.resource_url.host
        preflight = self.preflight(request, now=now)
        if not preflight.allowed:
            return preflight
        if merchant_domain != host:
            return self._deny(
                "merchant_mismatch",
                "The payment challenge merchant does not match the URL.",
            )
        if network != self.policy.network:
            return self._deny(
                "network_not_allowed",
                "The payment network is outside the configured policy.",
            )
        if currency != self.policy.currency:
            return self._deny(
                "currency_not_allowed",
                "The payment currency is outside the configured policy.",
            )
        if expires_at is not None and now >= expires_at:
            return self._deny(
                "challenge_expired",
                "The merchant payment challenge has expired.",
            )
        if amount > self.policy.per_request_limit:
            return self._deny(
                "request_limit_exceeded",
                "The amount exceeds the per-request spending limit.",
            )
        new_spend = (
            Decimal(0)
            if request.idempotency_key in self._spent_by_idempotency
            else amount
        )
        if self.spent + new_spend > self.policy.per_run_limit:
            return self._deny(
                "run_limit_exceeded",
                "The amount exceeds the remaining run budget.",
            )

        requires_approval = amount > self.policy.approval_threshold
        if requires_approval:
            approval_error = self._validate_approval(
                request,
                approval,
                amount=amount,
                now=now,
            )
            if approval_error is not None:
                return approval_error

        return AuthorizationDecision(
            allowed=True,
            code="authorized",
            reason="The request satisfies application-owned commerce policy.",
            requires_human_approval=requires_approval,
            approved_amount=amount,
        )

    def record_spend(self, idempotency_key: str, amount: Decimal) -> None:
        """Record one authorized amount without inventing receipt fields."""

        self._spent_by_idempotency.setdefault(idempotency_key, amount)

    def record(self, receipt: PaymentReceipt) -> None:
        self.record_spend(receipt.idempotency_key, receipt.amount)

    def _validate_approval(
        self,
        request: PurchaseRequest,
        approval: ApprovalGrant | None,
        *,
        amount: Decimal,
        now: datetime,
    ) -> AuthorizationDecision | None:
        if approval is None:
            return self._deny(
                "human_approval_required",
                "A human approval grant is required above the threshold.",
                requires_human_approval=True,
            )
        if now >= approval.expires_at:
            return self._deny(
                "approval_expired",
                "The human approval grant has expired.",
                requires_human_approval=True,
            )
        if (
            approval.request_id != request.request_id
            or approval.resource_url != request.resource_url
            or approval.purpose != request.purpose
        ):
            return self._deny(
                "approval_scope_mismatch",
                "The human approval grant is not bound to this request.",
                requires_human_approval=True,
            )
        if approval.currency != self.policy.currency:
            return self._deny(
                "approval_currency_mismatch",
                "The human approval grant uses a different currency.",
                requires_human_approval=True,
            )
        if amount > approval.maximum_amount:
            return self._deny(
                "approval_amount_exceeded",
                "The amount exceeds the human-approved maximum.",
                requires_human_approval=True,
            )
        return None

    @staticmethod
    def _deny(
        code: str,
        reason: str,
        *,
        requires_human_approval: bool = False,
    ) -> AuthorizationDecision:
        return AuthorizationDecision(
            allowed=False,
            code=code,
            reason=reason,
            requires_human_approval=requires_human_approval,
        )
