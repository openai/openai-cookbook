from __future__ import annotations

import json
import sys
from types import ModuleType
from typing import Any

import pytest

from agentic_commerce import agentcore_infrastructure
from agentic_commerce.agentcore_infrastructure import (
    inspect_payment_instrument,
    readiness_report,
)


class FakeInstrumentReader:
    def __init__(
        self,
        response: dict[str, Any] | None = None,
        balance_response: dict[str, Any] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.response = response or {}
        self.balance_response = balance_response or {
            "tokenBalance": {
                "amount": "1000000",
                "decimals": 6,
                "chain": "BASE_SEPOLIA",
                "token": "USDC",
            }
        }
        self.error = error
        self.calls: list[dict[str, object]] = []
        self.balance_calls: list[dict[str, object]] = []

    def get_payment_instrument(self, **kwargs: object) -> dict[str, Any]:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response

    def get_payment_instrument_balance(self, **kwargs: object) -> dict[str, Any]:
        self.balance_calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.balance_response


def environment() -> dict[str, str]:
    return {
        "ALLOW_AGENTCORE_READ_ONLY": "1",
        "AGENTCORE_AWS_REGION": "us-east-1",
        "AGENTCORE_RUNTIME_AWS_PROFILE": "payment-runtime",
        "PAYMENT_MANAGER_ARN": "manager-sensitive-read-only",
        "PAYMENT_CONNECTOR_ID": "connector-sensitive-read-only",
        "PAYMENT_INSTRUMENT_ID": "instrument-sensitive-read-only",
        "PAYMENT_USER_ID": "user-sensitive-read-only",
    }


def test_readiness_is_no_call_and_redacts_configuration() -> None:
    report = readiness_report(environment())
    rendered = json.dumps(report)

    assert report["result"] == "READY"
    assert report["aws_calls"] == 0
    assert report["value_transferred"] is False
    assert "manager-sensitive-read-only" not in rendered
    assert "connector-sensitive-read-only" not in rendered
    assert "instrument-sensitive-read-only" not in rendered
    assert "user-sensitive-read-only" not in rendered


def test_read_only_profile_uses_agentcore_region(
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

    agentcore_infrastructure._manager(environment())

    assert captured["profile_name"] == "payment-runtime"
    assert captured["region_name"] == "us-east-1"
    manager_kwargs = captured["manager_kwargs"]
    assert isinstance(manager_kwargs, dict)
    assert manager_kwargs["boto3_session"] is captured["boto3_session"]


def test_inspection_skips_without_explicit_read_only_gate() -> None:
    values = environment()
    values["ALLOW_AGENTCORE_READ_ONLY"] = "0"
    manager = FakeInstrumentReader()

    report = inspect_payment_instrument(
        values,
        manager_factory=lambda _: manager,
    )

    assert report["result"] == "SKIPPED"
    assert report["aws_calls"] == 0
    assert manager.calls == []


def test_active_instrument_returns_sanitized_read_only_evidence() -> None:
    manager = FakeInstrumentReader(
        {
            "paymentInstrumentId": "instrument-sensitive-response",
            "status": "ACTIVE",
            "paymentInstrumentDetails": {
                "embeddedCryptoWallet": {"network": "ETHEREUM"}
            },
        }
    )

    report = inspect_payment_instrument(
        environment(),
        manager_factory=lambda _: manager,
    )
    rendered = json.dumps(report)

    assert report["result"] == "PASSED"
    assert report["payment_manager_reachable"] is True
    assert report["payment_instrument_status"] == "ACTIVE"
    assert report["payment_instrument_network"] == "ETHEREUM"
    assert report["payment_instrument_chain"] == "BASE_SEPOLIA"
    assert report["payment_instrument_token"] == "USDC"
    assert report["exact_testnet_scope_verified"] is True
    assert report["aws_calls"] == 2
    assert report["payment_attempts"] == 0
    assert report["value_transferred"] is False
    assert "instrument-sensitive-response" not in rendered
    assert "instrument-sensitive-read-only" not in rendered
    assert "connector-sensitive-read-only" not in rendered
    assert manager.balance_calls == [
        {
            "payment_connector_id": "connector-sensitive-read-only",
            "payment_instrument_id": "instrument-sensitive-read-only",
            "chain": "BASE_SEPOLIA",
            "token": "USDC",
            "user_id": "user-sensitive-read-only",
        }
    ]


def test_active_instrument_on_wrong_network_is_not_ready() -> None:
    manager = FakeInstrumentReader(
        {
            "status": "ACTIVE",
            "paymentInstrumentDetails": {"embeddedCryptoWallet": {"network": "SOLANA"}},
        }
    )

    report = inspect_payment_instrument(
        environment(),
        manager_factory=lambda _: manager,
    )

    assert report["result"] == "NOT_READY"
    assert report["payment_instrument_network"] == "SOLANA"
    assert report["exact_testnet_scope_verified"] is False
    assert report["aws_calls"] == 1
    assert manager.balance_calls == []


def test_balance_scope_must_confirm_base_sepolia_usdc() -> None:
    manager = FakeInstrumentReader(
        {
            "status": "ACTIVE",
            "paymentInstrumentDetails": {
                "embeddedCryptoWallet": {"network": "ETHEREUM"}
            },
        },
        balance_response={
            "tokenBalance": {
                "amount": "1000000",
                "decimals": 6,
                "chain": "ETHEREUM",
                "token": "USDC",
            }
        },
    )

    report = inspect_payment_instrument(
        environment(),
        manager_factory=lambda _: manager,
    )

    assert report["result"] == "NOT_READY"
    assert report["payment_instrument_chain"] == "ETHEREUM"
    assert report["exact_testnet_scope_verified"] is False
    assert report["aws_calls"] == 2


def test_provider_failure_is_sanitized() -> None:
    manager = FakeInstrumentReader(
        error=RuntimeError("provider-secret instrument-sensitive-read-only")
    )

    report = inspect_payment_instrument(
        environment(),
        manager_factory=lambda _: manager,
    )
    rendered = json.dumps(report)

    assert report["result"] == "BLOCKED"
    assert report["category"] == "agentcore_read_only_check_failed"
    assert report["exception_type"] == "RuntimeError"
    assert report["value_transferred"] is False
    assert "provider-secret" not in rendered
    assert "instrument-sensitive-read-only" not in rendered


@pytest.mark.parametrize(
    ("result", "expected_exit"),
    [("NOT_READY", 2), ("SKIPPED", 2), ("BLOCKED", 1)],
)
def test_cli_returns_nonzero_for_nonpassing_result(
    result: str,
    expected_exit: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        agentcore_infrastructure,
        "inspect_payment_instrument",
        lambda: {"result": result},
    )

    with pytest.raises(SystemExit) as exc_info:
        agentcore_infrastructure.main()

    assert exc_info.value.code == expected_exit
