from __future__ import annotations

import base64
import hashlib
import json
import sys
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from types import ModuleType
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from agentic_commerce.agentcore_payments import (
    AgentCorePaymentsSettings,
    AgentCoreX402Client,
)
from agentic_commerce.errors import (
    AgentCorePaymentError,
    LivePaymentDisabled,
)

RESOURCE_URL = "https://merchant.example/report"
PUBLIC_ADDRESS = "8.8.8.8"
BASE_SEPOLIA_USDC = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"
APPROVED_PAY_TO = "synthetic-testnet-recipient"


def challenge_header(
    *,
    amount: str = "2000",
    network: str = "eip155:84532",
    asset: str = BASE_SEPOLIA_USDC,
    scheme: str = "exact",
    resource_url: str = RESOURCE_URL,
    pay_to: str = APPROVED_PAY_TO,
    max_timeout_seconds: int = 300,
    extra_update: dict[str, Any] | None = None,
    requirement_update: dict[str, Any] | None = None,
    extensions: dict[str, Any] | None = None,
) -> str:
    extra = {"name": "USDC", "version": "2"}
    extra.update(extra_update or {})
    requirement = {
        "scheme": scheme,
        "network": network,
        "amount": amount,
        "asset": asset,
        "payTo": pay_to,
        "maxTimeoutSeconds": max_timeout_seconds,
        "extra": extra,
    }
    requirement.update(requirement_update or {})
    challenge = {
        "x402Version": 2,
        "resource": {
            "url": resource_url,
            "description": "Synthetic paid test resource",
            "mimeType": "application/json",
        },
        "accepts": [requirement],
    }
    if extensions is not None:
        challenge["extensions"] = extensions
    return base64.b64encode(json.dumps(challenge).encode("utf-8")).decode("ascii")


class FakeManager:
    def __init__(
        self,
        *,
        result: dict[str, Any] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result or {
            "status": "PROOF_GENERATED",
            "paymentOutput": {
                "cryptoX402": {
                    "version": "2",
                    "payload": {"signature": "sensitive-test-proof"},
                }
            },
        }
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def process_payment(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.result


class RecordingClientFactory:
    def __init__(
        self,
        handler: Callable[[httpx.Request], httpx.Response],
    ) -> None:
        self.handler = handler
        self.created = 0

    def __call__(self) -> httpx.Client:
        self.created += 1
        return httpx.Client(transport=httpx.MockTransport(self.handler))


def settings(*, enabled: bool = True) -> AgentCorePaymentsSettings:
    return AgentCorePaymentsSettings(
        enabled=enabled,
        aws_region="us-east-1",
        payment_manager_arn="arn:test:manager",
        payment_instrument_id="instrument-test",
        payment_session_id="session-test",
        payment_user_id="user-test",
        allowed_merchants=frozenset({"merchant.example"}),
        approved_asset=BASE_SEPOLIA_USDC,
        approved_pay_to=APPROVED_PAY_TO,
        max_approved_amount_atomic=2000,
    )


def client(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    configured: AgentCorePaymentsSettings | None = None,
    manager: FakeManager | None = None,
    resolver: Callable[[str], list[str]] | None = None,
    clock: Callable[[], datetime] | None = None,
) -> tuple[AgentCoreX402Client, RecordingClientFactory, FakeManager]:
    factory = RecordingClientFactory(handler)
    fake_manager = manager or FakeManager()
    adapter = AgentCoreX402Client(
        configured or settings(),
        manager=fake_manager,
        client_factory=factory,
        resolver=resolver or (lambda _: [PUBLIC_ADDRESS]),
        authorize_challenge=lambda _: None,
        **({"clock": clock} if clock is not None else {}),
    )
    return adapter, factory, fake_manager


def test_successful_402_retry_uses_stable_token_and_fresh_client() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if "PAYMENT-SIGNATURE" not in request.headers:
            return httpx.Response(
                402,
                headers={"PAYMENT-REQUIRED": challenge_header()},
                text="payment required",
            )
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            json={"report": "synthetic"},
        )

    adapter, factory, manager = client(handler)
    result = adapter.fetch(
        RESOURCE_URL,
        client_token="purchase-test-001",
    )

    assert result.status_code == 200
    assert result.payment_attempted is True
    assert result.payment_attempts == 1
    assert result.merchant == "merchant.example"
    assert factory.created == 2
    assert len(requests) == 2
    assert all(request.url.host == PUBLIC_ADDRESS for request in requests)
    assert all(request.headers["host"] == "merchant.example" for request in requests)
    assert len(manager.calls) == 1
    assert manager.calls[0]["client_token"] == "purchase-test-001"
    assert manager.calls[0]["payment_type"] == "CRYPTO_X402"
    assert manager.calls[0]["payment_input"]["cryptoX402"]["version"] == "2"
    assert (
        manager.calls[0]["payment_input"]["cryptoX402"]["payload"]["amount"] == "2000"
    )
    assert "sensitive-test-proof" not in result.model_dump_json()


def test_bazaar_discovery_extension_is_validated_but_not_forwarded() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "PAYMENT-SIGNATURE" not in request.headers:
            return httpx.Response(
                402,
                headers={
                    "PAYMENT-REQUIRED": challenge_header(
                        extensions={
                            "bazaar": {
                                "info": {"input": {"method": "GET"}},
                                "schema": {},
                            }
                        }
                    )
                },
            )
        return httpx.Response(200, json={"report": "synthetic"})

    adapter, _, manager = client(handler)

    result = adapter.fetch(RESOURCE_URL, client_token="purchase-bazaar-test")

    assert result.status_code == 200
    assert len(manager.calls) == 1
    assert (
        "extensions" not in manager.calls[0]["payment_input"]["cryptoX402"]["payload"]
    )


@pytest.mark.parametrize(
    ("header", "expected_code"),
    [
        (
            challenge_header(pay_to="different-recipient"),
            "payment_challenge_recipient_denied",
        ),
        (
            challenge_header(resource_url="https://merchant.example/other"),
            "payment_challenge_resource_mismatch",
        ),
        (
            challenge_header(max_timeout_seconds=301),
            "payment_challenge_timeout_denied",
        ),
        (
            challenge_header(requirement_update={"unapproved": "value"}),
            "payment_challenge_fields_denied",
        ),
        (
            challenge_header(extensions={"unapproved": {}}),
            "payment_challenge_extensions_denied",
        ),
        (
            challenge_header(
                extensions={"bazaar": {"info": {}, "schema": {}, "unapproved": {}}}
            ),
            "payment_challenge_extensions_denied",
        ),
        (
            challenge_header(extensions={"bazaar": {"info": [], "schema": {}}}),
            "payment_challenge_extensions_denied",
        ),
    ],
)
def test_unapproved_challenge_semantics_never_reach_manager(
    header: str,
    expected_code: str,
) -> None:
    adapter, _, manager = client(
        lambda _: httpx.Response(
            402,
            headers={"PAYMENT-REQUIRED": header},
        )
    )

    with pytest.raises(AgentCorePaymentError) as exc_info:
        adapter.fetch(RESOURCE_URL, client_token="purchase-binding-test")

    assert exc_info.value.code == expected_code
    assert manager.calls == []


def test_expired_challenge_never_reaches_manager() -> None:
    now = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)
    header = challenge_header(
        extra_update={"expiresAt": (now - timedelta(seconds=1)).isoformat()}
    )
    adapter, _, manager = client(
        lambda _: httpx.Response(
            402,
            headers={"PAYMENT-REQUIRED": header},
        ),
        clock=lambda: now,
    )

    with pytest.raises(AgentCorePaymentError) as exc_info:
        adapter.fetch(RESOURCE_URL, client_token="purchase-expired-test")

    assert exc_info.value.code == "payment_challenge_expired"
    assert manager.calls == []


def test_provider_receives_only_canonical_approved_requirement() -> None:
    header = challenge_header(
        extra_update={
            "decimals": 6,
            "currency": "USDC",
            "merchantDomain": "merchant.example",
            "challengeId": "synthetic-challenge",
        }
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if "PAYMENT-SIGNATURE" not in request.headers:
            return httpx.Response(
                402,
                headers={"PAYMENT-REQUIRED": header},
            )
        return httpx.Response(200, text="ok")

    adapter, _, manager = client(handler)
    adapter.fetch(RESOURCE_URL, client_token="purchase-canonical-test")

    payload = manager.calls[0]["payment_input"]["cryptoX402"]["payload"]
    assert payload == {
        "scheme": "exact",
        "network": "eip155:84532",
        "amount": "2000",
        "asset": BASE_SEPOLIA_USDC,
        "payTo": APPROVED_PAY_TO,
        "maxTimeoutSeconds": 300,
        "extra": {
            "name": "USDC",
            "version": "2",
            "decimals": 6,
            "merchantDomain": "merchant.example",
            "challengeId": "synthetic-challenge",
        },
    }


def test_retry_limit_reuses_same_client_token() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            402,
            headers={"PAYMENT-REQUIRED": challenge_header()},
            text="still unpaid",
        )

    adapter, factory, manager = client(handler)
    with pytest.raises(AgentCorePaymentError) as exc_info:
        adapter.fetch(
            RESOURCE_URL,
            client_token="purchase-test-002",
        )

    assert exc_info.value.code == "payment_attempts_exhausted"
    assert factory.created == 3
    assert [call["client_token"] for call in manager.calls] == [
        "purchase-test-002",
        "purchase-test-002",
    ]


def test_retry_rejects_a_changed_challenge_before_second_signature() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        amount = "1000" if len(requests) == 1 else "2000"
        return httpx.Response(
            402,
            headers={"PAYMENT-REQUIRED": challenge_header(amount=amount)},
            text="payment required",
        )

    adapter, factory, manager = client(handler)

    with pytest.raises(AgentCorePaymentError) as exc_info:
        adapter.fetch(
            RESOURCE_URL,
            client_token="purchase-test-challenge-change",
        )

    assert exc_info.value.code == "payment_challenge_changed"
    assert factory.created == 2
    assert len(manager.calls) == 1


def test_response_size_limit_is_enforced_while_streaming() -> None:
    adapter, factory, manager = client(
        lambda _: httpx.Response(200, content=b"12345"),
        configured=settings().model_copy(update={"max_response_bytes": 4}),
    )

    with pytest.raises(AgentCorePaymentError) as exc_info:
        adapter.fetch(
            RESOURCE_URL,
            client_token="purchase-test-response-limit",
        )

    assert exc_info.value.code == "merchant_response_too_large"
    assert factory.created == 1
    assert manager.calls == []


def test_response_evidence_hashes_original_http_bytes() -> None:
    response = httpx.Response(
        200,
        content=b"\xff\xfe\x00raw-response",
        headers={"content-type": "application/octet-stream"},
    )

    result = AgentCoreX402Client._result(
        response,
        merchant="merchant.example",
        payment_attempts=1,
    )

    assert result.response_sha256 == hashlib.sha256(response.content).hexdigest()
    assert result.response_bytes == len(response.content)


def test_default_client_rejects_proxy_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example:8080")
    adapter = AgentCoreX402Client(settings())

    with pytest.raises(AgentCorePaymentError) as exc_info:
        adapter._default_client()

    assert exc_info.value.code == "merchant_proxy_unsupported"


def test_disabled_adapter_fails_before_network_or_manager() -> None:
    adapter, factory, manager = client(
        lambda _: httpx.Response(200),
        configured=settings(enabled=False),
    )

    with pytest.raises(LivePaymentDisabled) as exc_info:
        adapter.fetch(
            RESOURCE_URL,
            client_token="purchase-test-003",
        )

    assert exc_info.value.code == "agentcore_testnet_disabled"
    assert factory.created == 0
    assert manager.calls == []


def test_missing_application_authorizer_fails_before_network() -> None:
    factory = RecordingClientFactory(lambda _: httpx.Response(200))
    manager = FakeManager()
    adapter = AgentCoreX402Client(
        settings(),
        manager=manager,
        client_factory=factory,
        resolver=lambda _: [PUBLIC_ADDRESS],
    )

    with pytest.raises(AgentCorePaymentError) as exc_info:
        adapter.fetch(
            RESOURCE_URL,
            client_token="purchase-test-no-authorizer",
        )

    assert exc_info.value.code == "application_authorization_missing"
    assert factory.created == 0
    assert manager.calls == []


@pytest.mark.parametrize(
    ("resource_url", "expected_code"),
    [
        ("http://merchant.example/report", "https_resource_required"),
        ("https://other.example/report", "merchant_not_allowed"),
        (
            "https://user:password@merchant.example/report",
            "https_resource_required",
        ),
        (
            "https://merchant.example:abc/report",
            "https_resource_required",
        ),
    ],
)
def test_invalid_destinations_fail_before_network(
    resource_url: str,
    expected_code: str,
) -> None:
    adapter, factory, manager = client(
        lambda _: httpx.Response(200),
    )

    with pytest.raises(AgentCorePaymentError) as exc_info:
        adapter.fetch(
            resource_url,
            client_token="purchase-test-004",
        )

    assert exc_info.value.code == expected_code
    assert factory.created == 0
    assert manager.calls == []


def test_private_dns_resolution_fails_before_network() -> None:
    adapter, factory, manager = client(
        lambda _: httpx.Response(200),
        resolver=lambda _: ["127.0.0.1"],
    )

    with pytest.raises(AgentCorePaymentError) as exc_info:
        adapter.fetch(
            RESOURCE_URL,
            client_token="purchase-test-005",
        )

    assert exc_info.value.code == "private_merchant_address_denied"
    assert factory.created == 0
    assert manager.calls == []


def test_mixed_public_and_private_dns_answers_fail_before_network() -> None:
    adapter, factory, manager = client(
        lambda _: httpx.Response(200),
        resolver=lambda _: [PUBLIC_ADDRESS, "127.0.0.1"],
    )

    with pytest.raises(AgentCorePaymentError) as exc_info:
        adapter.fetch(RESOURCE_URL, client_token="purchase-mixed-dns-test")

    assert exc_info.value.code == "private_merchant_address_denied"
    assert factory.created == 0
    assert manager.calls == []


def test_signed_retry_revalidates_dns_and_rejects_changed_answer() -> None:
    answers = iter([[PUBLIC_ADDRESS], ["127.0.0.1"]])
    adapter, factory, manager = client(
        lambda _: httpx.Response(
            402,
            headers={"PAYMENT-REQUIRED": challenge_header()},
        ),
        resolver=lambda _: next(answers),
    )

    with pytest.raises(AgentCorePaymentError) as exc_info:
        adapter.fetch(RESOURCE_URL, client_token="purchase-dns-change-test")

    assert exc_info.value.code == "private_merchant_address_denied"
    assert factory.created == 1
    assert len(manager.calls) == 1


def test_global_ipv6_address_is_pinned_with_original_host_header() -> None:
    requests: list[httpx.Request] = []
    ipv6_address = "2606:4700:4700::1111"

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, text="ok")

    adapter, _, _ = client(
        handler,
        resolver=lambda _: [ipv6_address],
    )
    adapter.fetch(RESOURCE_URL, client_token="purchase-ipv6-test")

    assert requests[0].url.host == ipv6_address
    assert requests[0].headers["host"] == "merchant.example"


def test_manager_failure_is_sanitized() -> None:
    secret = "wallet-provider-secret"
    adapter, _, _ = client(
        lambda _: httpx.Response(
            402,
            headers={"PAYMENT-REQUIRED": challenge_header()},
            text="payment required",
        ),
        manager=FakeManager(error=RuntimeError(secret)),
    )

    with pytest.raises(AgentCorePaymentError) as exc_info:
        adapter.fetch(
            RESOURCE_URL,
            client_token="purchase-test-006",
        )

    assert exc_info.value.code == "payment_header_generation_failed"
    assert exc_info.value.diagnostics == {
        "stage": "agentcore_process_payment",
        "category": "provider_error",
        "provider_message_logged": False,
        "request_id_logged": False,
    }
    assert secret not in str(exc_info.value)
    assert exc_info.value.__cause__ is None


def test_manager_failure_preserves_only_safe_aws_diagnostics() -> None:
    from botocore.exceptions import ClientError

    secret = "wallet-provider-secret"
    request_id = "request-sensitive-identifier"
    client_error = ClientError(
        {
            "Error": {
                "Code": "ValidationException",
                "Message": secret,
            },
            "ResponseMetadata": {
                "HTTPStatusCode": 400,
                "RequestId": request_id,
            },
        },
        "ProcessPayment",
    )

    class PaymentError(Exception):
        pass

    provider_error = PaymentError(secret)
    provider_error.__cause__ = client_error
    adapter, _, _ = client(
        lambda _: httpx.Response(
            402,
            headers={"PAYMENT-REQUIRED": challenge_header()},
            text="payment required",
        ),
        manager=FakeManager(error=provider_error),
    )

    with pytest.raises(AgentCorePaymentError) as exc_info:
        adapter.fetch(
            RESOURCE_URL,
            client_token="purchase-test-safe-diagnostics",
        )

    rendered = json.dumps(exc_info.value.diagnostics)
    assert exc_info.value.diagnostics == {
        "stage": "agentcore_process_payment",
        "category": "aws_validation",
        "provider_message_logged": False,
        "request_id_logged": False,
        "aws_error_code": "ValidationException",
        "http_status_code": 400,
    }
    assert secret not in rendered
    assert request_id not in rendered


def test_insufficient_session_budget_has_safe_specific_code() -> None:
    class InsufficientBudget(Exception):
        pass

    adapter, _, _ = client(
        lambda _: httpx.Response(
            402,
            headers={"PAYMENT-REQUIRED": challenge_header()},
            text="payment required",
        ),
        manager=FakeManager(error=InsufficientBudget("provider details")),
    )

    with pytest.raises(AgentCorePaymentError) as exc_info:
        adapter.fetch(
            RESOURCE_URL,
            client_token="purchase-test-budget",
        )

    assert exc_info.value.code == "payment_session_budget_exceeded"
    assert exc_info.value.diagnostics["category"] == ("session_budget_exceeded")
    assert exc_info.value.diagnostics["provider_error_type"] == ("InsufficientBudget")
    assert "provider details" not in str(exc_info.value)
    assert exc_info.value.__cause__ is None


def test_invalid_generated_proof_is_rejected() -> None:
    adapter, factory, _ = client(
        lambda _: httpx.Response(
            402,
            headers={"PAYMENT-REQUIRED": challenge_header()},
            text="payment required",
        ),
        manager=FakeManager(
            result={
                "status": "PROOF_GENERATED",
                "paymentOutput": {"cryptoX402": {"version": "2"}},
            }
        ),
    )

    with pytest.raises(AgentCorePaymentError) as exc_info:
        adapter.fetch(
            RESOURCE_URL,
            client_token="purchase-test-007",
        )

    assert exc_info.value.code == "payment_header_invalid"
    assert factory.created == 1


def test_agentcore_region_is_separate_from_model_region() -> None:
    environment = {
        "AGENTCORE_AWS_REGION": "us-east-1",
        "AWS_REGION": "us-east-2",
        "PAYMENT_MANAGER_ARN": "manager",
        "PAYMENT_INSTRUMENT_ID": "instrument",
        "PAYMENT_SESSION_ID": "session",
        "PAYMENT_USER_ID": "user",
        "X402_ALLOWED_MERCHANTS": "merchant.example",
        "X402_APPROVED_ASSET": BASE_SEPOLIA_USDC,
        "X402_APPROVED_PAY_TO": APPROVED_PAY_TO,
        "X402_MAX_APPROVED_AMOUNT_ATOMIC": "2000",
    }

    configured = AgentCorePaymentsSettings.from_env(environment)

    assert configured.aws_region == "us-east-1"


@pytest.mark.parametrize("value", ["2e3", "2000.0", "+2000"])
def test_non_integer_max_amount_configuration_fails_closed(value: str) -> None:
    environment = {
        "AGENTCORE_AWS_REGION": "us-east-1",
        "PAYMENT_MANAGER_ARN": "manager",
        "PAYMENT_INSTRUMENT_ID": "instrument",
        "PAYMENT_SESSION_ID": "session",
        "PAYMENT_USER_ID": "user",
        "X402_ALLOWED_MERCHANTS": "merchant.example",
        "X402_APPROVED_ASSET": BASE_SEPOLIA_USDC,
        "X402_APPROVED_PAY_TO": APPROVED_PAY_TO,
        "X402_MAX_APPROVED_AMOUNT_ATOMIC": value,
    }

    with pytest.raises(AgentCorePaymentError) as exc_info:
        AgentCorePaymentsSettings.from_env(environment)

    assert exc_info.value.code == "agentcore_configuration_invalid"


def test_runtime_profile_is_passed_to_payment_manager(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    boto3_module = ModuleType("boto3")
    payments_module = ModuleType("bedrock_agentcore.payments")
    agentcore_module = ModuleType("bedrock_agentcore")

    def build_session(*, profile_name: str, region_name: str) -> object:
        session = object()
        captured["profile_name"] = profile_name
        captured["region_name"] = region_name
        captured["boto3_session"] = session
        return session

    def build_manager(**kwargs: object) -> object:
        captured["manager_kwargs"] = kwargs
        return object()

    boto3_module.Session = build_session  # type: ignore[attr-defined]
    payments_module.PaymentManager = build_manager  # type: ignore[attr-defined]
    agentcore_module.payments = payments_module  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "boto3", boto3_module)
    monkeypatch.setitem(sys.modules, "bedrock_agentcore", agentcore_module)
    monkeypatch.setitem(
        sys.modules,
        "bedrock_agentcore.payments",
        payments_module,
    )
    configured = settings().model_copy(
        update={"runtime_aws_profile": SecretStr("payment-runtime")}
    )

    AgentCoreX402Client(configured)._build_manager()

    assert captured["profile_name"] == "payment-runtime"
    assert captured["region_name"] == "us-east-1"
    manager_kwargs = captured["manager_kwargs"]
    assert isinstance(manager_kwargs, dict)
    assert manager_kwargs["boto3_session"] is captured["boto3_session"]


def test_unsupported_agentcore_region_fails_closed() -> None:
    environment = {
        "AGENTCORE_AWS_REGION": "us-east-2",
        "PAYMENT_MANAGER_ARN": "manager",
        "PAYMENT_INSTRUMENT_ID": "instrument",
        "PAYMENT_SESSION_ID": "session",
        "PAYMENT_USER_ID": "user",
        "X402_ALLOWED_MERCHANTS": "merchant.example",
        "X402_APPROVED_ASSET": BASE_SEPOLIA_USDC,
        "X402_APPROVED_PAY_TO": APPROVED_PAY_TO,
        "X402_MAX_APPROVED_AMOUNT_ATOMIC": "2000",
    }

    with pytest.raises(AgentCorePaymentError) as exc_info:
        AgentCorePaymentsSettings.from_env(environment)

    assert exc_info.value.code == "agentcore_region_unsupported"


def test_mainnet_network_configuration_fails_closed() -> None:
    environment = {
        "AGENTCORE_AWS_REGION": "us-east-1",
        "PAYMENT_MANAGER_ARN": "manager",
        "PAYMENT_INSTRUMENT_ID": "instrument",
        "PAYMENT_SESSION_ID": "session",
        "PAYMENT_USER_ID": "user",
        "X402_ALLOWED_MERCHANTS": "merchant.example",
        "X402_APPROVED_ASSET": BASE_SEPOLIA_USDC,
        "X402_APPROVED_PAY_TO": APPROVED_PAY_TO,
        "X402_MAX_APPROVED_AMOUNT_ATOMIC": "2000",
        "X402_NETWORK_PREFERENCES": "eip155:8453",
    }

    with pytest.raises(ValueError, match="Only the Base Sepolia"):
        AgentCorePaymentsSettings.from_env(environment)


@pytest.mark.parametrize(
    ("header", "expected_code"),
    [
        (None, "payment_challenge_missing"),
        ("not-base64", "payment_challenge_invalid"),
        (
            challenge_header(network="eip155:8453"),
            "payment_challenge_network_denied",
        ),
        (
            challenge_header(amount="2001"),
            "payment_challenge_amount_exceeds_approval",
        ),
        (
            challenge_header(asset="0x0000000000000000000000000000000000000000"),
            "payment_challenge_asset_denied",
        ),
    ],
)
def test_unapproved_challenge_fails_before_manager(
    header: str | None,
    expected_code: str,
) -> None:
    headers = {"PAYMENT-REQUIRED": header} if header is not None else {}
    adapter, factory, manager = client(
        lambda _: httpx.Response(402, headers=headers),
    )

    with pytest.raises(AgentCorePaymentError) as exc_info:
        adapter.fetch(
            RESOURCE_URL,
            client_token="purchase-test-009",
        )

    assert exc_info.value.code == expected_code
    assert factory.created == 1
    assert manager.calls == []
