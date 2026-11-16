from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
import pytest

from agentic_commerce.application import CommerceApplication
from agentic_commerce.codec import encode_model
from agentic_commerce.errors import (
    IdempotencyConflict,
    PolicyDenied,
    ProtocolError,
)
from agentic_commerce.merchant import (
    PAYMENT_REQUIRED_HEADER,
    PAYMENT_SIGNATURE_HEADER,
    RESOURCE_URL,
    SyntheticMerchant,
)
from agentic_commerce.models import (
    ApprovalGrant,
    AuditEventType,
    CommercePolicy,
    PurchaseRequest,
)
from agentic_commerce.payments import LocalPaymentProcessor
from agentic_commerce.policy import PolicyEngine
from agentic_commerce.tool import build_x402_fetch_tool

NOW = datetime(2026, 7, 30, 16, 0, tzinfo=UTC)


def make_system(
    *,
    price: Decimal = Decimal("0.25"),
    request_limit: Decimal = Decimal("0.50"),
    run_limit: Decimal = Decimal("1.00"),
    threshold: Decimal = Decimal("0.10"),
    session_expires_at: datetime | None = None,
    malformed_challenge: bool = False,
) -> tuple[CommerceApplication, SyntheticMerchant, LocalPaymentProcessor]:
    payments = LocalPaymentProcessor()
    merchant = SyntheticMerchant(
        payments,
        price=price,
        now=NOW,
        malformed_challenge=malformed_challenge,
    )
    policy = PolicyEngine(
        CommercePolicy(
            allowed_merchants=frozenset({"merchant.invalid"}),
            allowed_purposes=frozenset({"supplier_due_diligence"}),
            per_request_limit=request_limit,
            per_run_limit=run_limit,
            approval_threshold=threshold,
            session_expires_at=(session_expires_at or NOW + timedelta(minutes=15)),
        )
    )
    app = CommerceApplication(
        client=merchant.client(),
        policy=policy,
        payments=payments,
    )
    return app, merchant, payments


def request(
    *,
    request_id: str = "request-001",
    resource_url: str = RESOURCE_URL,
    purpose: str = "supplier_due_diligence",
    idempotency_key: str = "purchase-001",
) -> PurchaseRequest:
    return PurchaseRequest(
        request_id=request_id,
        resource_url=resource_url,
        purpose=purpose,
        idempotency_key=idempotency_key,
    )


def approval(
    purchase: PurchaseRequest,
    *,
    maximum_amount: Decimal = Decimal("0.25"),
    expires_at: datetime | None = None,
) -> ApprovalGrant:
    return ApprovalGrant(
        approval_id=f"approval-{purchase.request_id}",
        request_id=purchase.request_id,
        resource_url=purchase.resource_url,
        purpose=purchase.purpose,
        maximum_amount=maximum_amount,
        approved_by="synthetic-reviewer",
        approved_at=NOW,
        expires_at=expires_at or NOW + timedelta(minutes=10),
    )


def payment_required_client(payload: dict[str, Any]) -> httpx.Client:
    encoded = base64.b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")

    def handle(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            402,
            headers={PAYMENT_REQUIRED_HEADER: encoded},
            json={"error": "payment_required"},
        )

    return httpx.Client(transport=httpx.MockTransport(handle))


def test_approved_purchase_completes_full_402_sequence() -> None:
    app, merchant, payments = make_system()
    purchase = request()

    result = app.purchase(purchase, approval=approval(purchase), now=NOW)

    assert result.status == "completed"
    assert result.receipt.amount == Decimal("0.25")
    assert result.authorization.requires_human_approval is True
    assert result.report.report_id == "SYNTH-SUPPLIER-RISK-001"
    assert merchant.request_count == 2
    assert merchant.fulfilled_count == 1
    assert payments.charge_count == 1
    assert [event.event_type for event in result.audit_events] == [
        AuditEventType.RESOURCE_REQUESTED,
        AuditEventType.PAYMENT_REQUIRED,
        AuditEventType.AUTHORIZATION_CHECKED,
        AuditEventType.PAYMENT_ATTEMPTED,
        AuditEventType.PROOF_CREATED,
        AuditEventType.MERCHANT_RETRY,
        AuditEventType.CONTENT_RETURNED,
    ]


def test_below_threshold_purchase_does_not_need_human_approval() -> None:
    app, _, payments = make_system(price=Decimal("0.05"))

    result = app.purchase(request(), now=NOW)

    assert result.authorization.requires_human_approval is False
    assert payments.charge_count == 1


def test_missing_human_approval_is_denied_before_payment() -> None:
    app, merchant, payments = make_system()

    with pytest.raises(PolicyDenied) as exc_info:
        app.purchase(request(), now=NOW)

    assert exc_info.value.code == "human_approval_required"
    assert merchant.request_count == 1
    assert payments.charge_count == 0


def test_unapproved_destination_is_denied_before_http() -> None:
    app, merchant, payments = make_system()

    with pytest.raises(PolicyDenied) as exc_info:
        app.purchase(
            request(
                resource_url=(
                    "https://unapproved.invalid/reports/SYNTH-SUPPLIER-RISK-001"
                )
            ),
            now=NOW,
        )

    assert exc_info.value.code == "merchant_not_allowed"
    assert merchant.request_count == 0
    assert payments.charge_count == 0


def test_challenge_merchant_mismatch_is_denied_before_payment() -> None:
    app, merchant, payments = make_system()
    merchant.payment_required = merchant.payment_required.model_copy(
        update={
            "accepts": (
                merchant.requirement.model_copy(
                    update={
                        "extra": merchant.requirement.extra.model_copy(
                            update={"merchant_domain": "unapproved.invalid"}
                        )
                    }
                ),
            )
        }
    )

    with pytest.raises(PolicyDenied) as exc_info:
        app.purchase(request(), now=NOW)

    assert exc_info.value.code == "merchant_mismatch"
    assert merchant.request_count == 1
    assert payments.charge_count == 0


def test_http_resource_is_rejected_before_http() -> None:
    app, merchant, payments = make_system()

    with pytest.raises(PolicyDenied) as exc_info:
        app.purchase(
            request(resource_url=RESOURCE_URL.replace("https://", "http://")),
            now=NOW,
        )

    assert exc_info.value.code == "https_required"
    assert merchant.request_count == 0
    assert payments.charge_count == 0


def test_per_request_limit_denies_before_payment() -> None:
    app, merchant, payments = make_system(request_limit=Decimal("0.20"))

    with pytest.raises(PolicyDenied) as exc_info:
        app.purchase(request(), now=NOW)

    assert exc_info.value.code == "request_limit_exceeded"
    assert merchant.request_count == 1
    assert payments.charge_count == 0


def test_run_budget_is_enforced_across_distinct_purchases() -> None:
    app, _, payments = make_system(
        price=Decimal("0.05"),
        run_limit=Decimal("0.05"),
    )
    app.purchase(request(idempotency_key="purchase-001"), now=NOW)

    with pytest.raises(PolicyDenied) as exc_info:
        app.purchase(
            request(
                request_id="request-002",
                idempotency_key="purchase-002",
            ),
            now=NOW,
        )

    assert exc_info.value.code == "run_limit_exceeded"
    assert payments.charge_count == 1


def test_expired_session_denies_before_http() -> None:
    app, merchant, payments = make_system(session_expires_at=NOW - timedelta(seconds=1))

    with pytest.raises(PolicyDenied) as exc_info:
        app.purchase(request(), now=NOW)

    assert exc_info.value.code == "session_expired"
    assert merchant.request_count == 0
    assert payments.charge_count == 0


def test_expired_challenge_denies_before_payment() -> None:
    app, merchant, payments = make_system()
    expired = merchant.requirement.model_copy(
        update={
            "extra": merchant.requirement.extra.model_copy(
                update={"expires_at": NOW - timedelta(seconds=1)}
            )
        }
    )
    merchant.payment_required = merchant.payment_required.model_copy(
        update={"accepts": (expired,)}
    )

    with pytest.raises(PolicyDenied) as exc_info:
        app.purchase(request(), now=NOW)

    assert exc_info.value.code == "challenge_expired"
    assert payments.charge_count == 0


def test_expired_approval_denies_before_payment() -> None:
    app, _, payments = make_system()
    purchase = request()

    with pytest.raises(PolicyDenied) as exc_info:
        app.purchase(
            purchase,
            approval=approval(
                purchase,
                expires_at=NOW - timedelta(seconds=1),
            ),
            now=NOW,
        )

    assert exc_info.value.code == "approval_expired"
    assert payments.charge_count == 0


def test_malformed_payment_required_header_fails_safely() -> None:
    app, _, payments = make_system(malformed_challenge=True)

    with pytest.raises(ProtocolError) as exc_info:
        app.purchase(request(), now=NOW)

    assert exc_info.value.code == "malformed_protocol_header"
    assert payments.charge_count == 0


@pytest.mark.parametrize(
    "field_name",
    ["decimals", "currency", "merchantDomain", "challengeId", "expiresAt"],
)
def test_missing_payment_requirement_metadata_fails_safely(
    field_name: str,
) -> None:
    app, merchant, payments = make_system()
    payload = merchant.payment_required.model_dump(mode="json", by_alias=True)
    del payload["accepts"][0]["extra"][field_name]
    app.client = payment_required_client(payload)

    with pytest.raises(ProtocolError) as exc_info:
        app.purchase(request(), now=NOW)

    assert exc_info.value.code == "invalid_payment_requirement"
    assert payments.charge_count == 0


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("decimals", "6"),
        ("currency", 6),
        ("merchantDomain", 6),
        ("challengeId", 6),
        ("expiresAt", 6),
    ],
)
def test_typed_payment_requirement_metadata_fails_safely(
    field_name: str,
    value: object,
) -> None:
    app, merchant, payments = make_system()
    payload = merchant.payment_required.model_dump(mode="json", by_alias=True)
    payload["accepts"][0]["extra"][field_name] = value
    app.client = payment_required_client(payload)

    with pytest.raises(ProtocolError) as exc_info:
        app.purchase(request(), now=NOW)

    assert exc_info.value.code == "invalid_payment_requirement"
    assert payments.charge_count == 0


def test_same_idempotency_key_reuses_receipt_without_second_charge() -> None:
    app, merchant, payments = make_system()
    purchase = request()
    grant = approval(purchase)

    first = app.purchase(purchase, approval=grant, now=NOW)
    second = app.purchase(purchase, approval=grant, now=NOW)

    assert first.receipt.receipt_id == second.receipt.receipt_id
    assert first.receipt.reused is False
    assert second.receipt.reused is True
    assert payments.charge_count == 1
    assert merchant.fulfilled_count == 2


def test_idempotency_key_cannot_be_reused_for_changed_purchase() -> None:
    app, _, payments = make_system(price=Decimal("0.05"))
    app.purchase(request(purpose="supplier_due_diligence"), now=NOW)

    changed = request(purpose="another_allowed_purpose")
    app.policy.policy = app.policy.policy.model_copy(
        update={
            "allowed_purposes": frozenset(
                {"supplier_due_diligence", "another_allowed_purpose"}
            )
        }
    )
    with pytest.raises(IdempotencyConflict) as exc_info:
        app.purchase(changed, now=NOW)

    assert exc_info.value.code == "idempotency_conflict"
    assert payments.charge_count == 1


def test_merchant_rejects_unrecognized_proof() -> None:
    _, merchant, payments = make_system()
    response = merchant.client().get(
        RESOURCE_URL,
        headers={PAYMENT_SIGNATURE_HEADER: encode_model(merchant.payment_required)},
    )

    assert response.status_code == 402
    assert PAYMENT_REQUIRED_HEADER in response.headers
    assert merchant.invalid_proof_count == 1
    assert payments.charge_count == 0


def test_agents_tool_has_prebound_authority_and_expected_name() -> None:
    app, _, _ = make_system()
    purchase = request()
    tool = build_x402_fetch_tool(
        app,
        request_id=purchase.request_id,
        idempotency_key=purchase.idempotency_key,
        approval=approval(purchase),
    )

    assert tool.name == "x402_fetch"
