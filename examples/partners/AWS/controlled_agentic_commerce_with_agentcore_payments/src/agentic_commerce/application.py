"""Application controller for the deterministic x402 purchase sequence."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
from pydantic import ValidationError

from .audit import AuditTrail
from .codec import decode_json
from .errors import MerchantRejectedPayment, PolicyDenied, ProtocolError
from .merchant import (
    PAYMENT_REQUIRED_HEADER,
    PAYMENT_RESPONSE_HEADER,
    PAYMENT_SIGNATURE_HEADER,
)
from .models import (
    ApprovalGrant,
    AuditEventType,
    PaymentRequired,
    PurchaseRequest,
    PurchaseResult,
    SettlementResponse,
    SupplierRiskReport,
)
from .payments import LocalPaymentProcessor
from .policy import PolicyEngine


class CommerceApplication:
    """Orchestrate HTTP, authorization, payment, receipt, and audit state."""

    def __init__(
        self,
        *,
        client: httpx.Client,
        policy: PolicyEngine,
        payments: LocalPaymentProcessor,
        audit: AuditTrail | None = None,
    ) -> None:
        self.client = client
        self.policy = policy
        self.payments = payments
        self.audit = audit or AuditTrail()

    def purchase(
        self,
        request: PurchaseRequest,
        *,
        approval: ApprovalGrant | None = None,
        now: datetime | None = None,
    ) -> PurchaseResult:
        now = now or datetime.now(UTC)
        self.audit.append(
            request_id=request.request_id,
            event_type=AuditEventType.RESOURCE_REQUESTED,
            detail={
                "resource_url": str(request.resource_url),
                "purpose": request.purpose,
            },
        )
        preflight = self.policy.preflight(request, now=now)
        if not preflight.allowed:
            self.audit.append(
                request_id=request.request_id,
                event_type=AuditEventType.REQUEST_DENIED,
                detail={"code": preflight.code, "stage": "preflight"},
            )
            raise PolicyDenied(preflight.code, preflight.reason)

        initial = self.client.get(str(request.resource_url))
        if initial.status_code != 402:
            raise ProtocolError(
                "payment_challenge_expected",
                "The paid resource did not return HTTP 402.",
            )

        required = self._payment_required(initial)
        requirement = required.accepts[0]
        self.audit.append(
            request_id=request.request_id,
            event_type=AuditEventType.PAYMENT_REQUIRED,
            detail={
                "merchant_domain": requirement.merchant_domain,
                "amount": str(requirement.decimal_amount),
                "currency": requirement.currency,
                "network": requirement.network,
            },
        )

        decision = self.policy.authorize(
            request,
            required,
            approval=approval,
            now=now,
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
            self.audit.append(
                request_id=request.request_id,
                event_type=AuditEventType.REQUEST_DENIED,
                detail={"code": decision.code},
            )
            raise PolicyDenied(decision.code, decision.reason)

        self.audit.append(
            request_id=request.request_id,
            event_type=AuditEventType.PAYMENT_ATTEMPTED,
            detail={"idempotency_key": request.idempotency_key},
        )
        authorization = self.payments.authorize(request, requirement)
        self.policy.record(authorization.receipt)
        self.audit.append(
            request_id=request.request_id,
            event_type=(
                AuditEventType.PROOF_REUSED
                if authorization.receipt.reused
                else AuditEventType.PROOF_CREATED
            ),
            detail={"receipt_id": authorization.receipt.receipt_id},
        )

        self.audit.append(
            request_id=request.request_id,
            event_type=AuditEventType.MERCHANT_RETRY,
            detail={"payment_header": PAYMENT_SIGNATURE_HEADER},
        )
        paid = self.client.get(
            str(request.resource_url),
            headers={
                PAYMENT_SIGNATURE_HEADER: authorization.proof_header,
            },
        )
        if paid.status_code != 200:
            raise MerchantRejectedPayment(
                "merchant_rejected_payment",
                "The merchant did not accept the synthetic payment proof.",
            )

        settlement = self._settlement(paid)
        if (
            not settlement.success
            or settlement.transaction != authorization.receipt.transaction
        ):
            raise ProtocolError(
                "settlement_receipt_mismatch",
                "The settlement response does not match the local receipt.",
            )
        try:
            report = SupplierRiskReport.model_validate(paid.json())
        except (ValueError, ValidationError) as exc:
            raise ProtocolError(
                "invalid_paid_resource",
                "The paid resource did not match the typed report contract.",
            ) from exc

        self.audit.append(
            request_id=request.request_id,
            event_type=AuditEventType.CONTENT_RETURNED,
            detail={
                "report_id": report.report_id,
                "receipt_id": authorization.receipt.receipt_id,
            },
        )
        return PurchaseResult(
            status="completed",
            request_id=request.request_id,
            authorization=decision,
            receipt=authorization.receipt,
            report=report,
            audit_events=self.audit.for_request(request.request_id),
        )

    @staticmethod
    def _payment_required(response: httpx.Response) -> PaymentRequired:
        header = response.headers.get(PAYMENT_REQUIRED_HEADER)
        if header is None:
            raise ProtocolError(
                "payment_required_header_missing",
                "HTTP 402 did not include PAYMENT-REQUIRED.",
            )
        payload = decode_json(header, header_name=PAYMENT_REQUIRED_HEADER)
        try:
            return PaymentRequired.model_validate(payload)
        except ValidationError as exc:
            raise ProtocolError(
                "invalid_payment_requirement",
                "PAYMENT-REQUIRED does not match the expected contract.",
            ) from exc

    @staticmethod
    def _settlement(response: httpx.Response) -> SettlementResponse:
        header = response.headers.get(PAYMENT_RESPONSE_HEADER)
        if header is None:
            raise ProtocolError(
                "payment_response_header_missing",
                "Paid response did not include PAYMENT-RESPONSE.",
            )
        payload = decode_json(header, header_name=PAYMENT_RESPONSE_HEADER)
        try:
            return SettlementResponse.model_validate(payload)
        except ValidationError as exc:
            raise ProtocolError(
                "invalid_settlement_response",
                "PAYMENT-RESPONSE does not match the expected contract.",
            ) from exc
