"""Typed contracts for authorization, x402 transport, receipts, and audit."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    computed_field,
    field_validator,
)
from pydantic_core import PydanticCustomError


class FrozenModel(BaseModel):
    """Immutable model used for application and protocol contracts."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)


class AuditEventType(StrEnum):
    RESOURCE_REQUESTED = "resource_requested"
    PAYMENT_REQUIRED = "payment_required"
    AUTHORIZATION_CHECKED = "authorization_checked"
    PAYMENT_ATTEMPTED = "payment_attempted"
    PROOF_CREATED = "proof_created"
    PROOF_REUSED = "proof_reused"
    MERCHANT_RETRY = "merchant_retry"
    CONTENT_RETURNED = "content_returned"
    REQUEST_DENIED = "request_denied"


class AuditEvent(FrozenModel):
    sequence: int = Field(ge=1)
    occurred_at: datetime
    request_id: str
    event_type: AuditEventType
    detail: dict[str, Any] = Field(default_factory=dict)


class CommercePolicy(FrozenModel):
    allowed_merchants: frozenset[str]
    allowed_purposes: frozenset[str]
    per_request_limit: Decimal = Field(gt=0)
    per_run_limit: Decimal = Field(gt=0)
    approval_threshold: Decimal = Field(ge=0)
    currency: Literal["USDC"] = "USDC"
    network: Literal["eip155:84532"] = "eip155:84532"
    session_expires_at: datetime


class PurchaseRequest(FrozenModel):
    request_id: str = Field(min_length=1)
    resource_url: HttpUrl
    purpose: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=8)


class ApprovalGrant(FrozenModel):
    approval_id: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    resource_url: HttpUrl
    purpose: str = Field(min_length=1)
    maximum_amount: Decimal = Field(gt=0)
    currency: Literal["USDC"] = "USDC"
    approved_by: str = Field(min_length=1)
    approved_at: datetime
    expires_at: datetime


class ResourceInfo(FrozenModel):
    url: HttpUrl
    description: str
    mime_type: str = Field(alias="mimeType")


class PaymentRequirementExtra(FrozenModel):
    """Validated x402 metadata used by local policy computed fields."""

    model_config = ConfigDict(frozen=True, populate_by_name=True, extra="forbid")

    decimals: int = Field(strict=True, ge=0)
    currency: Literal["USDC"]
    merchant_domain: str = Field(
        alias="merchantDomain",
        strict=True,
        min_length=1,
    )
    challenge_id: str = Field(
        alias="challengeId",
        strict=True,
        min_length=1,
    )
    issued_at: AwareDatetime | None = Field(default=None, alias="issuedAt")
    expires_at: AwareDatetime = Field(alias="expiresAt")
    simulation: bool | None = Field(default=None, strict=True)

    @field_validator("issued_at", "expires_at", mode="before")
    @classmethod
    def require_iso_timestamp_text(cls, value: object) -> object:
        if value is None:
            return value
        if not isinstance(value, str):
            raise PydanticCustomError(
                "x402_timestamp_type",
                "x402 timestamps must be ISO 8601 strings.",
            )
        return value


class PaymentRequirement(FrozenModel):
    """Protocol-shaped x402 V2 exact-payment requirement.

    The local proof is deliberately synthetic. These fields mirror the
    current x402 V2 transport shape but do not claim chain conformance.
    """

    scheme: Literal["exact"] = "exact"
    network: Literal["eip155:84532"] = "eip155:84532"
    amount: str = Field(pattern=r"^[0-9]+$")
    asset: str
    pay_to: str = Field(alias="payTo")
    max_timeout_seconds: int = Field(alias="maxTimeoutSeconds", gt=0)
    extra: PaymentRequirementExtra

    @computed_field
    @property
    def decimal_amount(self) -> Decimal:
        return Decimal(self.amount) / (Decimal(10) ** self.extra.decimals)

    @computed_field
    @property
    def currency(self) -> Literal["USDC"]:
        return self.extra.currency

    @computed_field
    @property
    def merchant_domain(self) -> str:
        return self.extra.merchant_domain

    @computed_field
    @property
    def challenge_id(self) -> str:
        return self.extra.challenge_id

    @computed_field
    @property
    def expires_at(self) -> datetime:
        return self.extra.expires_at


class PaymentRequired(FrozenModel):
    x402_version: Literal[2] = Field(alias="x402Version", default=2)
    resource: ResourceInfo
    accepts: tuple[PaymentRequirement, ...] = Field(min_length=1)
    error: str | None = None


class PaymentPayload(FrozenModel):
    x402_version: Literal[2] = Field(alias="x402Version", default=2)
    accepted: PaymentRequirement
    payload: dict[str, str]


class SettlementResponse(FrozenModel):
    success: bool
    transaction: str
    network: str
    payer: str


class AuthorizationDecision(FrozenModel):
    allowed: bool
    code: str
    reason: str
    requires_human_approval: bool
    approved_amount: Decimal | None = None


class PaymentReceipt(FrozenModel):
    receipt_id: str
    request_id: str
    idempotency_key: str
    merchant_domain: str
    resource_url: HttpUrl
    amount: Decimal
    currency: Literal["USDC"]
    network: str
    transaction: str
    reused: bool = False


class PaymentAuthorization(FrozenModel):
    proof_header: str
    receipt: PaymentReceipt


class SupplierRiskReport(FrozenModel):
    report_id: Literal["SYNTH-SUPPLIER-RISK-001"]
    supplier: Literal["Northstar Components"]
    generated_from: Literal["synthetic data"]
    signals: tuple[str, ...]
    disclaimer: str


class PurchaseResult(FrozenModel):
    status: Literal["completed"]
    request_id: str
    authorization: AuthorizationDecision
    receipt: PaymentReceipt
    report: SupplierRiskReport
    audit_events: tuple[AuditEvent, ...]


class AgentPurchaseEvidence(FrozenModel):
    """Minimum purchase evidence returned to the model by the function tool."""

    status: Literal["completed"]
    report: SupplierRiskReport
    receipt_id: str
    amount: Decimal
    currency: Literal["USDC"]
    requires_human_approval: bool
