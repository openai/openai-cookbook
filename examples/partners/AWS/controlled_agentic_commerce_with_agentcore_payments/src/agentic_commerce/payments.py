"""Deterministic local proof creation; no wallet, chain, or value transfer."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from pydantic import ValidationError

from .codec import decode_json, encode_model
from .errors import IdempotencyConflict, ProtocolError
from .models import (
    PaymentAuthorization,
    PaymentPayload,
    PaymentReceipt,
    PaymentRequirement,
    PurchaseRequest,
    SettlementResponse,
)


@dataclass(frozen=True)
class _StoredAuthorization:
    fingerprint: str
    proof_header: str
    receipt: PaymentReceipt


class LocalPaymentProcessor:
    """A fake local payment adapter with idempotent proof generation."""

    payer = "synthetic-test-payer"

    def __init__(self) -> None:
        self._authorizations: dict[str, _StoredAuthorization] = {}

    @property
    def charge_count(self) -> int:
        return len(self._authorizations)

    def authorize(
        self,
        request: PurchaseRequest,
        requirement: PaymentRequirement,
    ) -> PaymentAuthorization:
        fingerprint = self._fingerprint(request, requirement)
        stored = self._authorizations.get(request.idempotency_key)
        if stored is not None:
            if stored.fingerprint != fingerprint:
                raise IdempotencyConflict(
                    "idempotency_conflict",
                    "The idempotency key is already bound to another purchase.",
                )
            return PaymentAuthorization(
                proof_header=stored.proof_header,
                receipt=stored.receipt.model_copy(update={"reused": True}),
            )

        digest = hashlib.sha256(
            f"{request.idempotency_key}:{fingerprint}".encode()
        ).hexdigest()
        receipt = PaymentReceipt(
            receipt_id=f"receipt-{digest[:16]}",
            request_id=request.request_id,
            idempotency_key=request.idempotency_key,
            merchant_domain=requirement.merchant_domain,
            resource_url=request.resource_url,
            amount=requirement.decimal_amount,
            currency=requirement.currency,
            network=requirement.network,
            transaction=f"synthetic-{digest[16:40]}",
        )
        payload = PaymentPayload(
            accepted=requirement,
            payload={
                "proof": f"synthetic-proof-{digest[40:]}",
                "receiptId": receipt.receipt_id,
            },
        )
        proof_header = encode_model(payload)
        self._authorizations[request.idempotency_key] = _StoredAuthorization(
            fingerprint=fingerprint,
            proof_header=proof_header,
            receipt=receipt,
        )
        return PaymentAuthorization(
            proof_header=proof_header,
            receipt=receipt,
        )

    def verify(
        self,
        proof_header: str,
        requirement: PaymentRequirement,
    ) -> SettlementResponse:
        payload_dict = decode_json(
            proof_header,
            header_name="PAYMENT-SIGNATURE",
        )
        try:
            payload = PaymentPayload.model_validate(payload_dict)
        except ValidationError as exc:
            raise ProtocolError(
                "invalid_payment_payload",
                "PAYMENT-SIGNATURE does not match the expected payload.",
            ) from exc

        if payload.accepted != requirement:
            raise ProtocolError(
                "payment_requirement_mismatch",
                "The proof does not match the merchant requirement.",
            )

        receipt_id = payload.payload.get("receiptId")
        proof = payload.payload.get("proof")
        stored = next(
            (
                candidate
                for candidate in self._authorizations.values()
                if candidate.receipt.receipt_id == receipt_id
            ),
            None,
        )
        if (
            stored is None
            or stored.proof_header != proof_header
            or not proof
            or not proof.startswith("synthetic-proof-")
        ):
            raise ProtocolError(
                "unrecognized_synthetic_proof",
                "The local payment proof is not recognized.",
            )

        return SettlementResponse(
            success=True,
            transaction=stored.receipt.transaction,
            network=stored.receipt.network,
            payer=self.payer,
        )

    @staticmethod
    def _fingerprint(
        request: PurchaseRequest,
        requirement: PaymentRequirement,
    ) -> str:
        stable = {
            "resource_url": str(request.resource_url),
            "purpose": request.purpose,
            "challenge_id": requirement.challenge_id,
            "amount": requirement.amount,
            "asset": requirement.asset,
            "network": requirement.network,
            "pay_to": requirement.pay_to,
        }
        raw = json.dumps(stable, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode()).hexdigest()
