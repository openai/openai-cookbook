"""Opt-in AgentCore Payments adapter for approved x402 testnet resources."""

from __future__ import annotations

import base64
import binascii
import hashlib
import ipaddress
import json
import logging
import os
import socket
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal, Protocol
from urllib.parse import urlsplit, urlunsplit

import httpx
from pydantic import Field, SecretStr, field_validator

from .errors import AgentCorePaymentError, LivePaymentDisabled
from .models import FrozenModel

_PAYMENT_HEADER_NAMES = frozenset({"payment-signature", "x-payment"})
_REQUIRED_CONFIGURATION = (
    "PAYMENT_MANAGER_ARN",
    "PAYMENT_INSTRUMENT_ID",
    "PAYMENT_SESSION_ID",
    "PAYMENT_USER_ID",
    "X402_ALLOWED_MERCHANTS",
    "X402_APPROVED_ASSET",
    "X402_APPROVED_PAY_TO",
    "X402_MAX_APPROVED_AMOUNT_ATOMIC",
)
_AGENTCORE_REGION_ENV = "AGENTCORE_AWS_REGION"
_AWS_REGION_FALLBACK_ENV = "AWS_REGION"
_PROXY_ENV_NAMES = (
    "ALL_PROXY",
    "HTTPS_PROXY",
    "HTTP_PROXY",
    "all_proxy",
    "https_proxy",
    "http_proxy",
)
_SUPPORTED_AGENTCORE_PAYMENT_REGIONS = frozenset(
    {
        "ap-southeast-2",
        "eu-central-1",
        "us-east-1",
        "us-west-2",
    }
)
_SUPPORTED_TESTNET_NETWORKS = frozenset({"eip155:84532"})
_AGENTCORE_MANAGER_LOGGER = "bedrock_agentcore.payments.manager"
_PROVIDER_ERROR_CATEGORIES = {
    "InsufficientBudget": "session_budget_exceeded",
    "InvalidPaymentInstrument": "payment_instrument_invalid",
    "PaymentInstrumentNotFound": "payment_instrument_not_found",
    "PaymentSessionExpired": "payment_session_expired",
    "PaymentSessionNotFound": "payment_session_not_found",
}
_AWS_ERROR_CATEGORIES = {
    "AccessDeniedException": "aws_access_denied",
    "ConflictException": "aws_conflict",
    "InternalServerException": "aws_service_error",
    "ResourceNotFoundException": "aws_resource_not_found",
    "ServiceUnavailableException": "aws_service_unavailable",
    "ThrottlingException": "aws_throttled",
    "ValidationException": "aws_validation",
}
_REQUIREMENT_FIELDS = frozenset(
    {
        "scheme",
        "network",
        "amount",
        "asset",
        "payTo",
        "maxTimeoutSeconds",
        "extra",
    }
)
_EXTRA_FIELDS = frozenset(
    {
        "name",
        "version",
        "decimals",
        "currency",
        "merchantDomain",
        "challengeId",
        "expiresAt",
    }
)
_CHALLENGE_EXTENSION_FIELDS = frozenset({"bazaar"})
_BAZAAR_EXTENSION_FIELDS = frozenset({"info", "schema"})


def _disable_agentcore_sdk_logging() -> None:
    logging.getLogger(_AGENTCORE_MANAGER_LOGGER).disabled = True


def _safe_symbol(value: object) -> str | None:
    if not isinstance(value, str) or not 1 <= len(value) <= 64:
        return None
    if not value[0].isalpha() or not value.replace("_", "").isalnum():
        return None
    return value


def _positive_integer_text(value: str) -> bool:
    """Accept only non-empty ASCII decimal integer text."""

    return bool(value) and value.isascii() and value.isdecimal()


def _safe_payment_diagnostics(exc: Exception) -> dict[str, object]:
    """Extract non-secret failure metadata without rendering exceptions."""

    provider_error_type = _safe_symbol(type(exc).__name__)
    diagnostics: dict[str, object] = {
        "stage": "agentcore_process_payment",
        "category": _PROVIDER_ERROR_CATEGORIES.get(
            provider_error_type or "",
            "provider_error",
        ),
        "provider_message_logged": False,
        "request_id_logged": False,
    }
    if provider_error_type in _PROVIDER_ERROR_CATEGORIES:
        diagnostics["provider_error_type"] = provider_error_type

    current: BaseException | None = exc
    visited: set[int] = set()
    for _ in range(4):
        if current is None or id(current) in visited:
            break
        visited.add(id(current))
        response = getattr(current, "response", None)
        if isinstance(response, Mapping):
            error = response.get("Error")
            metadata = response.get("ResponseMetadata")
            if isinstance(error, Mapping):
                aws_error_code = _safe_symbol(error.get("Code"))
                if aws_error_code is not None:
                    diagnostics["aws_error_code"] = aws_error_code
                    diagnostics["category"] = _AWS_ERROR_CATEGORIES.get(
                        aws_error_code,
                        "aws_service_error",
                    )
            if isinstance(metadata, Mapping):
                http_status = metadata.get("HTTPStatusCode")
                if isinstance(http_status, int) and 100 <= http_status <= 599:
                    diagnostics["http_status_code"] = http_status
            break
        current = current.__cause__ or current.__context__
    return diagnostics


def _validate_challenge_extensions(extensions: object) -> None:
    if not isinstance(extensions, dict):
        raise AgentCorePaymentError(
            "payment_challenge_extensions_denied",
            "The merchant challenge contains unsupported extensions.",
        )
    if not extensions:
        return
    if set(extensions) - _CHALLENGE_EXTENSION_FIELDS:
        raise AgentCorePaymentError(
            "payment_challenge_extensions_denied",
            "The merchant challenge contains unsupported extensions.",
        )
    bazaar = extensions.get("bazaar")
    if (
        not isinstance(bazaar, dict)
        or set(bazaar) != _BAZAAR_EXTENSION_FIELDS
        or not isinstance(bazaar.get("info"), dict)
        or not isinstance(bazaar.get("schema"), dict)
    ):
        raise AgentCorePaymentError(
            "payment_challenge_extensions_denied",
            "The merchant challenge contains an invalid Bazaar extension.",
        )


def _resolve_agentcore_region(values: Mapping[str, str]) -> str:
    """Resolve the payment Region without overriding the model Region."""

    return (
        values.get(_AGENTCORE_REGION_ENV, "").strip()
        or values.get(_AWS_REGION_FALLBACK_ENV, "").strip()
    )


class PaymentProcessor(Protocol):
    """Least-privilege protocol implemented by AgentCore PaymentManager."""

    def process_payment(
        self,
        *,
        payment_session_id: str,
        payment_instrument_id: str,
        payment_type: str,
        payment_input: dict[str, Any],
        user_id: str | None = None,
        client_token: str | None = None,
        payment_connector_id: str | None = None,
    ) -> dict[str, Any]:
        """Generate one bounded payment proof."""


class AgentCorePaymentsSettings(FrozenModel):
    """Runtime configuration with identifiers redacted from repr output."""

    enabled: bool = False
    aws_region: str = Field(min_length=1)
    payment_manager_arn: SecretStr
    payment_instrument_id: SecretStr
    payment_session_id: SecretStr
    payment_user_id: SecretStr
    runtime_aws_profile: SecretStr | None = None
    allowed_merchants: frozenset[str] = Field(min_length=1)
    approved_asset: str = Field(min_length=1)
    approved_pay_to: SecretStr = Field(min_length=1)
    max_approved_amount_atomic: int = Field(gt=0)
    max_challenge_timeout_seconds: int = Field(default=300, gt=0, le=900)
    network_preferences: tuple[str, ...] = Field(
        default=("eip155:84532",),
        min_length=1,
    )
    max_payment_attempts: int = Field(default=2, ge=1, le=3)
    timeout_seconds: float = Field(default=30.0, gt=0, le=60)
    max_response_bytes: int = Field(
        default=1_000_000,
        ge=1,
        le=5_000_000,
    )

    @field_validator("aws_region")
    @classmethod
    def validate_agentcore_region(cls, value: str) -> str:
        """Fail closed when AgentCore Payments is unavailable in a Region."""

        if value not in _SUPPORTED_AGENTCORE_PAYMENT_REGIONS:
            supported = ", ".join(sorted(_SUPPORTED_AGENTCORE_PAYMENT_REGIONS))
            raise ValueError(
                "AgentCore Payments is unavailable in this Region. "
                f"Use one of: {supported}."
            )
        return value

    @field_validator("network_preferences")
    @classmethod
    def validate_testnet_networks(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        """Prevent configuration from widening this adapter to mainnet."""

        if any(network not in _SUPPORTED_TESTNET_NETWORKS for network in value):
            raise ValueError(
                "Only the Base Sepolia testnet network eip155:84532 is allowed."
            )
        return value

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> AgentCorePaymentsSettings:
        """Load settings without printing or persisting their values."""

        values = environ if environ is not None else os.environ
        aws_region = _resolve_agentcore_region(values)
        missing = [
            name for name in _REQUIRED_CONFIGURATION if not values.get(name, "").strip()
        ]
        if not aws_region:
            missing.append(f"{_AGENTCORE_REGION_ENV} (or {_AWS_REGION_FALLBACK_ENV})")
        if missing:
            raise AgentCorePaymentError(
                "agentcore_configuration_missing",
                "AgentCore Payments configuration is incomplete: " + ", ".join(missing),
            )
        if aws_region not in _SUPPORTED_AGENTCORE_PAYMENT_REGIONS:
            supported = ", ".join(sorted(_SUPPORTED_AGENTCORE_PAYMENT_REGIONS))
            raise AgentCorePaymentError(
                "agentcore_region_unsupported",
                "AgentCore Payments is unavailable in the configured "
                f"Region. Use one of: {supported}.",
            )

        allowed_merchants = frozenset(
            host.strip().lower().rstrip(".")
            for host in values["X402_ALLOWED_MERCHANTS"].split(",")
            if host.strip()
        )
        network_preferences = tuple(
            network.strip()
            for network in values.get(
                "X402_NETWORK_PREFERENCES",
                "eip155:84532",
            ).split(",")
            if network.strip()
        )
        try:
            max_attempts = int(values.get("X402_MAX_PAYMENT_ATTEMPTS", "2"))
        except ValueError as exc:
            raise AgentCorePaymentError(
                "agentcore_configuration_invalid",
                "X402_MAX_PAYMENT_ATTEMPTS must be an integer.",
            ) from exc
        raw_max_approved_amount_atomic = values[
            "X402_MAX_APPROVED_AMOUNT_ATOMIC"
        ].strip()
        if not _positive_integer_text(raw_max_approved_amount_atomic):
            raise AgentCorePaymentError(
                "agentcore_configuration_invalid",
                "X402_MAX_APPROVED_AMOUNT_ATOMIC must be a positive integer.",
            )
        max_approved_amount_atomic = int(raw_max_approved_amount_atomic)
        if max_approved_amount_atomic <= 0:
            raise AgentCorePaymentError(
                "agentcore_configuration_invalid",
                "X402_MAX_APPROVED_AMOUNT_ATOMIC must be a positive integer.",
            )
        try:
            max_challenge_timeout_seconds = int(
                values.get("X402_MAX_CHALLENGE_TIMEOUT_SECONDS", "300")
            )
        except ValueError as exc:
            raise AgentCorePaymentError(
                "agentcore_configuration_invalid",
                "X402_MAX_CHALLENGE_TIMEOUT_SECONDS must be an integer.",
            ) from exc

        return cls(
            enabled=values.get("ALLOW_AGENTCORE_TESTNET") == "1",
            aws_region=aws_region,
            payment_manager_arn=values["PAYMENT_MANAGER_ARN"].strip(),
            payment_instrument_id=values["PAYMENT_INSTRUMENT_ID"].strip(),
            payment_session_id=values["PAYMENT_SESSION_ID"].strip(),
            payment_user_id=values["PAYMENT_USER_ID"].strip(),
            runtime_aws_profile=(
                values.get("AGENTCORE_RUNTIME_AWS_PROFILE", "").strip() or None
            ),
            allowed_merchants=allowed_merchants,
            approved_asset=values["X402_APPROVED_ASSET"].strip(),
            approved_pay_to=values["X402_APPROVED_PAY_TO"].strip(),
            max_approved_amount_atomic=max_approved_amount_atomic,
            max_challenge_timeout_seconds=(max_challenge_timeout_seconds),
            network_preferences=network_preferences,
            max_payment_attempts=max_attempts,
        )


class AgentCoreFetchResult(FrozenModel):
    """Sanitized result; payment proof and configured IDs are excluded."""

    status_code: int
    content_type: str | None = None
    response_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    response_bytes: int = Field(ge=0)
    payment_attempted: bool
    payment_attempts: int = Field(ge=0)
    merchant: str


class AgentCorePaymentChallenge(FrozenModel):
    """Sanitized, validated challenge presented to application policy."""

    resource_url: str
    resource_description: str
    resource_mime_type: str
    merchant: str
    x402_version: Literal[2] = 2
    scheme: Literal["exact"] = "exact"
    network: Literal["eip155:84532"]
    asset: str
    pay_to: SecretStr
    max_timeout_seconds: int = Field(gt=0)
    amount_atomic: int = Field(gt=0)
    amount: Decimal = Field(gt=0)
    currency: Literal["USDC"] = "USDC"
    asset_version: Literal["2"] = "2"
    decimals: Literal[6] | None = None
    merchant_domain: str | None = None
    challenge_id: str | None = None
    expires_at: datetime | None = None

    def provider_requirement(self) -> dict[str, Any]:
        """Construct provider input only from approved canonical fields."""

        extra: dict[str, Any] = {
            "name": self.currency,
            "version": self.asset_version,
        }
        if self.decimals is not None:
            extra["decimals"] = self.decimals
        if self.merchant_domain is not None:
            extra["merchantDomain"] = self.merchant_domain
        if self.challenge_id is not None:
            extra["challengeId"] = self.challenge_id
        if self.expires_at is not None:
            extra["expiresAt"] = self.expires_at.isoformat()
        return {
            "scheme": self.scheme,
            "network": self.network,
            "amount": str(self.amount_atomic),
            "asset": self.asset,
            "payTo": self.pay_to.get_secret_value(),
            "maxTimeoutSeconds": self.max_timeout_seconds,
            "extra": extra,
        }

    def provider_resource(self) -> dict[str, str]:
        """Construct the signed resource from validated canonical fields."""

        return {
            "url": self.resource_url,
            "description": self.resource_description,
            "mimeType": self.resource_mime_type,
        }


Resolver = Callable[[str], list[str]]
ClientFactory = Callable[[], httpx.Client]
AuthorizationCallback = Callable[[AgentCorePaymentChallenge], None]
PaymentsClock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _resolve_addresses(host: str) -> list[str]:
    return sorted(
        {
            item[4][0]
            for item in socket.getaddrinfo(
                host,
                443,
                type=socket.SOCK_STREAM,
            )
        }
    )


def _reject_proxy_environment(
    environ: Mapping[str, str] | None = None,
) -> None:
    values = environ if environ is not None else os.environ
    configured = [name for name in _PROXY_ENV_NAMES if values.get(name, "").strip()]
    if configured:
        raise AgentCorePaymentError(
            "merchant_proxy_unsupported",
            "Proxy-based merchant networking is not supported by the "
            "DNS-pinned live path. Unset HTTP_PROXY, HTTPS_PROXY, and "
            "ALL_PROXY variants before the approved testnet run.",
        )


def _proxy_environment_clear(environ: Mapping[str, str]) -> bool:
    return not any(environ.get(name, "").strip() for name in _PROXY_ENV_NAMES)


class AgentCoreX402Client:
    """Fetch an allowlisted testnet resource using AgentCore Payments.

    This adapter does not decide whether a purchase is justified. The caller
    must supply an application-owned authorization callback. The adapter
    invokes it with the validated HTTP 402 challenge before requesting a
    payment header from AgentCore Payments.
    """

    def __init__(
        self,
        settings: AgentCorePaymentsSettings,
        *,
        manager: PaymentProcessor | None = None,
        client_factory: ClientFactory | None = None,
        resolver: Resolver | None = None,
        authorize_challenge: AuthorizationCallback | None = None,
        clock: PaymentsClock = _utc_now,
    ) -> None:
        self.settings = settings
        self._manager = manager
        self._client_factory = client_factory or self._default_client
        self._resolver = resolver or _resolve_addresses
        self._authorize_challenge = authorize_challenge
        self._clock = clock

    def fetch(
        self,
        resource_url: str,
        *,
        client_token: str,
    ) -> AgentCoreFetchResult:
        """Perform one explicitly enabled x402 GET with bounded retries."""

        if not self.settings.enabled:
            raise LivePaymentDisabled(
                "agentcore_testnet_disabled",
                "Set ALLOW_AGENTCORE_TESTNET=1 only after the payment "
                "session, allowlist, approval, and testnet funding are ready.",
            )
        if len(client_token.strip()) < 8:
            raise AgentCorePaymentError(
                "idempotency_token_invalid",
                "The client token must contain at least eight characters.",
            )
        if self._authorize_challenge is None:
            raise AgentCorePaymentError(
                "application_authorization_missing",
                "Application-owned challenge authorization is required "
                "before AgentCore Payments can generate a payment header.",
            )

        merchant = self._validated_merchant(resource_url)
        response = self._request(resource_url, merchant=merchant)
        if response.status_code != 402:
            return self._result(
                response,
                merchant=merchant,
                payment_attempts=0,
            )

        approved_challenge: AgentCorePaymentChallenge | None = None
        for attempt in range(1, self.settings.max_payment_attempts + 1):
            challenge = self._validate_payment_challenge(
                response,
                resource_url=resource_url,
                merchant=merchant,
            )
            if approved_challenge is None:
                approved_challenge = challenge
            elif challenge != approved_challenge:
                raise AgentCorePaymentError(
                    "payment_challenge_changed",
                    "The merchant changed the payment challenge during the "
                    "approved retry sequence.",
                )
            self._authorize_challenge(challenge)
            payment_headers = self._generate_payment_headers(
                challenge=challenge,
                client_token=client_token,
            )
            response = self._request(
                resource_url,
                merchant=merchant,
                headers=payment_headers,
            )
            if response.status_code != 402:
                return self._result(
                    response,
                    merchant=merchant,
                    payment_attempts=attempt,
                )

        raise AgentCorePaymentError(
            "payment_attempts_exhausted",
            "The approved merchant continued to require payment after the "
            "configured testnet retry limit.",
        )

    def _validate_payment_challenge(
        self,
        response: httpx.Response,
        *,
        resource_url: str,
        merchant: str,
    ) -> AgentCorePaymentChallenge:
        """Validate the payable requirement before asking AWS to sign it."""

        challenge = self._decode_payment_challenge(response)
        resource = challenge.get("resource")
        if not isinstance(resource, dict):
            raise AgentCorePaymentError(
                "payment_challenge_resource_invalid",
                "The merchant challenge does not identify the approved resource.",
            )
        if resource.get("url") != resource_url:
            raise AgentCorePaymentError(
                "payment_challenge_resource_mismatch",
                "The merchant challenge refers to a different resource.",
            )
        resource_description = resource.get("description")
        resource_mime_type = resource.get("mimeType")
        if (
            not isinstance(resource_description, str)
            or len(resource_description) > 1_024
            or not isinstance(resource_mime_type, str)
            or not 1 <= len(resource_mime_type) <= 255
        ):
            raise AgentCorePaymentError(
                "payment_challenge_resource_invalid",
                "The merchant challenge contains invalid resource metadata.",
            )
        _validate_challenge_extensions(challenge.get("extensions", {}))

        requirements = challenge["accepts"]
        candidates = [
            item
            for item in requirements
            if item.get("network") in self.settings.network_preferences
        ]
        if not candidates:
            raise AgentCorePaymentError(
                "payment_challenge_network_denied",
                "The merchant challenge does not offer an approved testnet network.",
            )
        if len(candidates) != 1:
            raise AgentCorePaymentError(
                "payment_challenge_ambiguous",
                "The merchant challenge contains more than one payable "
                "requirement for an approved network.",
            )

        requirement = candidates[0]
        if set(requirement) - _REQUIREMENT_FIELDS:
            raise AgentCorePaymentError(
                "payment_challenge_fields_denied",
                "The merchant challenge contains unsupported payment fields.",
            )
        if requirement.get("scheme") != "exact":
            raise AgentCorePaymentError(
                "payment_challenge_scheme_denied",
                "The merchant challenge does not use the approved exact "
                "payment scheme.",
            )

        asset = requirement.get("asset")
        if (
            not isinstance(asset, str)
            or asset.lower() != self.settings.approved_asset.lower()
        ):
            raise AgentCorePaymentError(
                "payment_challenge_asset_denied",
                "The merchant challenge does not use the approved asset.",
            )

        pay_to = requirement.get("payTo")
        if (
            not isinstance(pay_to, str)
            or pay_to != self.settings.approved_pay_to.get_secret_value()
        ):
            raise AgentCorePaymentError(
                "payment_challenge_recipient_denied",
                "The merchant challenge does not use the "
                "application-approved recipient.",
            )

        max_timeout_seconds = requirement.get("maxTimeoutSeconds")
        if (
            type(max_timeout_seconds) is not int
            or max_timeout_seconds <= 0
            or max_timeout_seconds > self.settings.max_challenge_timeout_seconds
        ):
            raise AgentCorePaymentError(
                "payment_challenge_timeout_denied",
                "The merchant challenge exceeds the application-approved timeout.",
            )

        extra = requirement.get("extra")
        if (
            not isinstance(extra, dict)
            or set(extra) - _EXTRA_FIELDS
            or extra.get("name") != "USDC"
            or extra.get("version") != "2"
        ):
            raise AgentCorePaymentError(
                "payment_challenge_asset_denied",
                "The merchant challenge does not identify the approved USDC asset.",
            )

        decimals = extra.get("decimals")
        if decimals is not None and decimals != 6:
            raise AgentCorePaymentError(
                "payment_challenge_asset_denied",
                "The merchant challenge uses unsupported asset decimals.",
            )
        currency = extra.get("currency")
        if currency is not None and currency != "USDC":
            raise AgentCorePaymentError(
                "payment_challenge_asset_denied",
                "The merchant challenge uses an unsupported currency.",
            )
        merchant_domain = extra.get("merchantDomain")
        if merchant_domain is not None and merchant_domain != merchant:
            raise AgentCorePaymentError(
                "payment_challenge_merchant_mismatch",
                "The merchant challenge identity does not match the "
                "approved resource host.",
            )
        challenge_id = extra.get("challengeId")
        if challenge_id is not None and (
            not isinstance(challenge_id, str) or not 1 <= len(challenge_id) <= 256
        ):
            raise AgentCorePaymentError(
                "payment_challenge_invalid",
                "The merchant challenge identifier is invalid.",
            )

        expires_at: datetime | None = None
        raw_expires_at = extra.get("expiresAt")
        if raw_expires_at is not None:
            if not isinstance(raw_expires_at, str):
                raise AgentCorePaymentError(
                    "payment_challenge_expiry_invalid",
                    "The merchant challenge expiry is invalid.",
                )
            try:
                expires_at = datetime.fromisoformat(raw_expires_at)
            except ValueError:
                raise AgentCorePaymentError(
                    "payment_challenge_expiry_invalid",
                    "The merchant challenge expiry is invalid.",
                ) from None
            if expires_at.tzinfo is None:
                raise AgentCorePaymentError(
                    "payment_challenge_expiry_invalid",
                    "The merchant challenge expiry is invalid.",
                )
            now = self._clock()
            if now >= expires_at:
                raise AgentCorePaymentError(
                    "payment_challenge_expired",
                    "The merchant payment challenge has expired.",
                )
            if expires_at > now + timedelta(
                seconds=self.settings.max_challenge_timeout_seconds
            ):
                raise AgentCorePaymentError(
                    "payment_challenge_expiry_denied",
                    "The merchant challenge expiry exceeds the "
                    "application-approved lifetime.",
                )

        amount = requirement.get("amount")
        if not isinstance(amount, str) or not amount.isdecimal() or len(amount) > 32:
            raise AgentCorePaymentError(
                "payment_challenge_amount_invalid",
                "The merchant challenge amount is invalid.",
            )
        amount_atomic = int(amount)
        if amount_atomic <= 0:
            raise AgentCorePaymentError(
                "payment_challenge_amount_invalid",
                "The merchant challenge amount is invalid.",
            )
        if amount_atomic > self.settings.max_approved_amount_atomic:
            raise AgentCorePaymentError(
                "payment_challenge_amount_exceeds_approval",
                "The merchant challenge exceeds the application-approved "
                "maximum amount.",
            )
        return AgentCorePaymentChallenge(
            resource_url=resource_url,
            resource_description=resource_description,
            resource_mime_type=resource_mime_type,
            merchant=merchant,
            network=requirement["network"],
            asset=asset,
            pay_to=pay_to,
            max_timeout_seconds=max_timeout_seconds,
            amount_atomic=amount_atomic,
            amount=Decimal(amount_atomic) / Decimal(1_000_000),
            decimals=decimals,
            merchant_domain=merchant_domain,
            challenge_id=challenge_id,
            expires_at=expires_at,
        )

    def _decode_payment_challenge(
        self,
        response: httpx.Response,
    ) -> dict[str, Any]:
        """Decode the x402 v2 challenge without retaining proof material."""

        encoded = response.headers.get("payment-required", "").strip()
        if not encoded:
            raise AgentCorePaymentError(
                "payment_challenge_missing",
                "The approved merchant returned HTTP 402 without a "
                "PAYMENT-REQUIRED challenge.",
            )
        if len(encoded) > 32_768:
            raise AgentCorePaymentError(
                "payment_challenge_invalid",
                "The PAYMENT-REQUIRED challenge is invalid.",
            )

        padded = encoded + "=" * (-len(encoded) % 4)
        try:
            decoded = base64.b64decode(
                padded,
                altchars=b"-_",
                validate=True,
            )
            challenge = json.loads(decoded)
        except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError):
            raise AgentCorePaymentError(
                "payment_challenge_invalid",
                "The PAYMENT-REQUIRED challenge is invalid.",
            ) from None

        if (
            not isinstance(challenge, dict)
            or challenge.get("x402Version") != 2
            or not isinstance(challenge.get("accepts"), list)
        ):
            raise AgentCorePaymentError(
                "payment_challenge_invalid",
                "The PAYMENT-REQUIRED challenge is invalid.",
            )

        requirements = challenge["accepts"]
        if any(not isinstance(item, dict) for item in requirements):
            raise AgentCorePaymentError(
                "payment_challenge_invalid",
                "The PAYMENT-REQUIRED challenge is invalid.",
            )
        return challenge

    def _default_client(self) -> httpx.Client:
        _reject_proxy_environment()
        return httpx.Client(
            timeout=self.settings.timeout_seconds,
            follow_redirects=False,
            verify=True,
            trust_env=False,
            headers={"User-Agent": ("openai-agentcore-payments-cookbook/0.1")},
        )

    def _request(
        self,
        resource_url: str,
        *,
        merchant: str,
        headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        pinned_url = self._pinned_resource_url(resource_url, merchant=merchant)
        request_headers = dict(headers or {})
        request_headers["Host"] = merchant
        try:
            with (
                self._client_factory() as client,
                client.stream(
                    "GET",
                    pinned_url,
                    headers=request_headers,
                    extensions={"sni_hostname": merchant},
                ) as streamed,
            ):
                content = bytearray()
                for chunk in streamed.iter_bytes():
                    content.extend(chunk)
                    if len(content) > self.settings.max_response_bytes:
                        raise AgentCorePaymentError(
                            "merchant_response_too_large",
                            "The approved merchant response exceeded "
                            "the configured size limit.",
                        )
                response = httpx.Response(
                    status_code=streamed.status_code,
                    headers=streamed.headers,
                    content=bytes(content),
                    request=streamed.request,
                    extensions=streamed.extensions,
                )
        except httpx.HTTPError:
            raise AgentCorePaymentError(
                "merchant_request_failed",
                "The approved testnet merchant request failed.",
            ) from None
        return response

    def _generate_payment_headers(
        self,
        *,
        challenge: AgentCorePaymentChallenge,
        client_token: str,
    ) -> dict[str, str]:
        manager = self._manager or self._build_manager()
        if challenge.expires_at is not None and self._clock() >= (challenge.expires_at):
            raise AgentCorePaymentError(
                "payment_challenge_expired",
                "The merchant payment challenge expired before proof generation.",
            )
        selected_accept = challenge.provider_requirement()
        try:
            payment_result = manager.process_payment(
                payment_session_id=(
                    self.settings.payment_session_id.get_secret_value()
                ),
                payment_instrument_id=(
                    self.settings.payment_instrument_id.get_secret_value()
                ),
                payment_type="CRYPTO_X402",
                payment_input={
                    "cryptoX402": {
                        "version": "2",
                        "payload": selected_accept,
                    }
                },
                user_id=(self.settings.payment_user_id.get_secret_value()),
                client_token=client_token,
            )
        # Preview SDK implementations can surface provider-specific exception
        # types; normalize them without exposing credential-adjacent details.
        except Exception as exc:  # noqa: BLE001
            diagnostics = _safe_payment_diagnostics(exc)
            if type(exc).__name__ == "InsufficientBudget":
                raise AgentCorePaymentError(
                    "payment_session_budget_exceeded",
                    "AgentCore Payments rejected the testnet payment "
                    "because it exceeded the bounded session budget.",
                    diagnostics=diagnostics,
                ) from None
            raise AgentCorePaymentError(
                "payment_header_generation_failed",
                "AgentCore Payments could not generate a testnet payment header.",
                diagnostics=diagnostics,
            ) from None

        if not isinstance(payment_result, dict):
            raise AgentCorePaymentError(
                "payment_header_invalid",
                "AgentCore Payments returned an invalid testnet proof.",
            )
        payment_output = payment_result.get("paymentOutput")
        crypto_x402 = (
            payment_output.get("cryptoX402")
            if isinstance(payment_output, dict)
            else None
        )
        proof_payload = (
            crypto_x402.get("payload") if isinstance(crypto_x402, dict) else None
        )
        if (
            payment_result.get("status") != "PROOF_GENERATED"
            or not isinstance(crypto_x402, dict)
            or crypto_x402.get("version") != "2"
            or not isinstance(proof_payload, dict)
            or not proof_payload
        ):
            raise AgentCorePaymentError(
                "payment_header_invalid",
                "AgentCore Payments returned an invalid testnet proof.",
            )
        signature = {
            "x402Version": 2,
            "resource": challenge.provider_resource(),
            "accepted": selected_accept,
            "extensions": {},
            "payload": proof_payload,
        }
        encoded = base64.b64encode(
            json.dumps(signature, separators=(",", ":")).encode("utf-8")
        ).decode("ascii")
        generated = {"PAYMENT-SIGNATURE": encoded}
        if any(
            name.lower() not in _PAYMENT_HEADER_NAMES
            or not isinstance(value, str)
            or not value
            for name, value in generated.items()
        ):
            raise AgentCorePaymentError(
                "payment_header_invalid",
                "AgentCore Payments returned an unsupported payment header.",
            )
        return generated

    def _build_manager(self) -> PaymentProcessor:
        try:
            from bedrock_agentcore.payments import PaymentManager
        except ImportError:
            raise AgentCorePaymentError(
                "agentcore_sdk_missing",
                "Install the pinned AgentCore adapter dependency with "
                "`uv sync --extra agentcore --group dev`.",
            ) from None

        _disable_agentcore_sdk_logging()
        try:
            boto3_session = None
            if self.settings.runtime_aws_profile is not None:
                import boto3

                boto3_session = boto3.Session(
                    profile_name=(self.settings.runtime_aws_profile.get_secret_value()),
                    region_name=self.settings.aws_region,
                )
            return PaymentManager(
                payment_manager_arn=(
                    self.settings.payment_manager_arn.get_secret_value()
                ),
                region_name=self.settings.aws_region,
                boto3_session=boto3_session,
            )
        # Keep the adapter fail-closed across preview SDK exception variants.
        except Exception:  # noqa: BLE001
            raise AgentCorePaymentError(
                "payment_manager_initialization_failed",
                "AgentCore PaymentManager initialization failed.",
            ) from None

    def _validated_merchant(self, resource_url: str) -> str:
        parsed = urlsplit(resource_url)
        host = (parsed.hostname or "").lower().rstrip(".")
        try:
            port = parsed.port
        except ValueError:
            raise AgentCorePaymentError(
                "https_resource_required",
                "The AgentCore testnet adapter accepts only HTTPS resources "
                "without embedded credentials or nonstandard ports.",
            ) from None
        if (
            parsed.scheme != "https"
            or not host
            or parsed.username is not None
            or parsed.password is not None
            or port not in (None, 443)
        ):
            raise AgentCorePaymentError(
                "https_resource_required",
                "The AgentCore testnet adapter accepts only HTTPS resources "
                "without embedded credentials or nonstandard ports.",
            )
        if host not in self.settings.allowed_merchants:
            raise AgentCorePaymentError(
                "merchant_not_allowed",
                "The resource host is not in the exact merchant allowlist.",
            )

        return host

    def _pinned_resource_url(
        self,
        resource_url: str,
        *,
        merchant: str,
    ) -> str:
        """Resolve, validate, and pin one address for this request."""

        try:
            addresses = self._resolver(merchant)
        except OSError:
            raise AgentCorePaymentError(
                "merchant_resolution_failed",
                "The approved merchant hostname could not be resolved.",
            ) from None
        if not addresses:
            raise AgentCorePaymentError(
                "merchant_resolution_failed",
                "The approved merchant hostname returned no addresses.",
            )
        validated: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
        for address in addresses:
            try:
                ip = ipaddress.ip_address(address)
            except ValueError:
                raise AgentCorePaymentError(
                    "merchant_address_invalid",
                    "The approved merchant resolved to an invalid address.",
                ) from None
            if not ip.is_global:
                raise AgentCorePaymentError(
                    "private_merchant_address_denied",
                    "The approved merchant resolved to a non-public address.",
                )
            validated.append(ip)

        selected = min(
            validated,
            key=lambda item: (item.version, item.packed),
        )
        netloc = f"[{selected}]" if selected.version == 6 else str(selected)
        parsed = urlsplit(resource_url)
        return urlunsplit(
            (
                parsed.scheme,
                netloc,
                parsed.path,
                parsed.query,
                parsed.fragment,
            )
        )

    @staticmethod
    def _result(
        response: httpx.Response,
        *,
        merchant: str,
        payment_attempts: int,
    ) -> AgentCoreFetchResult:
        content = response.content
        return AgentCoreFetchResult(
            status_code=response.status_code,
            content_type=response.headers.get("content-type"),
            response_sha256=hashlib.sha256(content).hexdigest(),
            response_bytes=len(content),
            payment_attempted=payment_attempts > 0,
            payment_attempts=payment_attempts,
            merchant=merchant,
        )
