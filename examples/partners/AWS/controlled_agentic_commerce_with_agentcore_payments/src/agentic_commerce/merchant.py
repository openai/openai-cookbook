"""In-memory synthetic merchant that exposes a protocol-shaped x402 flow."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx

from .codec import encode_model
from .errors import CommerceError
from .models import (
    PaymentRequired,
    PaymentRequirement,
    ResourceInfo,
    SupplierRiskReport,
)
from .payments import LocalPaymentProcessor

PAYMENT_REQUIRED_HEADER = "PAYMENT-REQUIRED"
PAYMENT_SIGNATURE_HEADER = "PAYMENT-SIGNATURE"
PAYMENT_RESPONSE_HEADER = "PAYMENT-RESPONSE"

RESOURCE_URL = "https://merchant.invalid/reports/SYNTH-SUPPLIER-RISK-001"


class SyntheticMerchant:
    """Serve one fictional paid report through an in-memory HTTP transport."""

    def __init__(
        self,
        payment_processor: LocalPaymentProcessor,
        *,
        price: Decimal = Decimal("0.25"),
        now: datetime | None = None,
        malformed_challenge: bool = False,
    ) -> None:
        self.payment_processor = payment_processor
        self.request_count = 0
        self.fulfilled_count = 0
        self.invalid_proof_count = 0
        self.malformed_challenge = malformed_challenge
        issued_at = now or datetime.now(UTC)
        expires_at = issued_at + timedelta(minutes=5)
        amount = str(int(price * Decimal(1_000_000)))

        self.requirement = PaymentRequirement(
            amount=amount,
            asset="synthetic-usdc-base-sepolia",
            payTo="synthetic-merchant-wallet",
            maxTimeoutSeconds=300,
            extra={
                "challengeId": "challenge-synth-report-001",
                "currency": "USDC",
                "decimals": 6,
                "merchantDomain": "merchant.invalid",
                "issuedAt": issued_at.isoformat(),
                "expiresAt": expires_at.isoformat(),
                "simulation": True,
            },
        )
        self.payment_required = PaymentRequired(
            resource=ResourceInfo(
                url=RESOURCE_URL,
                description="Synthetic supplier-risk report",
                mimeType="application/json",
            ),
            accepts=(self.requirement,),
            error="Payment is required for this synthetic report.",
        )
        self.report = SupplierRiskReport(
            report_id="SYNTH-SUPPLIER-RISK-001",
            supplier="Northstar Components",
            generated_from="synthetic data",
            signals=(
                "Delivery concentration increased in the last synthetic quarter.",
                "Two fictional certifications require manual verification.",
            ),
            disclaimer=(
                "Training-only synthetic report; not purchasing, legal, "
                "compliance, or risk advice."
            ),
        )

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self._handle))

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.request_count += 1
        if request.method != "GET" or str(request.url) != RESOURCE_URL:
            return httpx.Response(
                404,
                json={"error": "synthetic_resource_not_found"},
            )

        proof_header = request.headers.get(PAYMENT_SIGNATURE_HEADER)
        if proof_header is None:
            challenge = (
                "not-base64-json"
                if self.malformed_challenge
                else encode_model(self.payment_required)
            )
            return httpx.Response(
                402,
                headers={PAYMENT_REQUIRED_HEADER: challenge},
                json={"error": "payment_required"},
            )

        try:
            settlement = self.payment_processor.verify(
                proof_header,
                self.requirement,
            )
        except CommerceError as exc:
            self.invalid_proof_count += 1
            return httpx.Response(
                402,
                headers={PAYMENT_REQUIRED_HEADER: encode_model(self.payment_required)},
                json={"error": exc.code},
            )

        self.fulfilled_count += 1
        return httpx.Response(
            200,
            headers={PAYMENT_RESPONSE_HEADER: encode_model(settlement)},
            json=self.report.model_dump(mode="json"),
        )
