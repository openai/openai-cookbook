"""Safe, typed errors for the synthetic commerce flow."""

from __future__ import annotations

from collections.abc import Mapping


class CommerceError(RuntimeError):
    """Base error with a stable, non-secret error code."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        diagnostics: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.diagnostics = dict(diagnostics or {})


class ProtocolError(CommerceError):
    """The merchant response did not satisfy the expected x402 shape."""


class PolicyDenied(CommerceError):
    """Application-owned policy denied the proposed purchase."""


class IdempotencyConflict(CommerceError):
    """An idempotency key was reused for a different purchase."""


class MerchantRejectedPayment(CommerceError):
    """The synthetic merchant rejected the supplied payment proof."""


class AgentCorePaymentError(CommerceError):
    """AgentCore Payments or the testnet transport failed safely."""


class LivePaymentDisabled(AgentCorePaymentError):
    """A networked testnet payment was attempted without explicit opt-in."""


class AgentResultInvalid(CommerceError):
    """The agent result did not match application-observed purchase evidence."""
