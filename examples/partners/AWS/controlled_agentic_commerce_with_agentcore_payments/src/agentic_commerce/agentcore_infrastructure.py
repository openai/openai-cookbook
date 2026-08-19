"""Explicitly gated, read-only checks for AgentCore payment resources."""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from typing import Any, Protocol

from .agentcore_payments import (
    _SUPPORTED_AGENTCORE_PAYMENT_REGIONS,
    _disable_agentcore_sdk_logging,
    _resolve_agentcore_region,
)

_READ_ONLY_OPT_IN = "ALLOW_AGENTCORE_READ_ONLY"
_EXPECTED_INSTRUMENT_NETWORK = "ETHEREUM"
_EXPECTED_CHAIN = "BASE_SEPOLIA"
_EXPECTED_TOKEN = "USDC"
_REQUIRED_CONFIGURATION = (
    "PAYMENT_MANAGER_ARN",
    "PAYMENT_CONNECTOR_ID",
    "PAYMENT_INSTRUMENT_ID",
    "PAYMENT_USER_ID",
    "AGENTCORE_RUNTIME_AWS_PROFILE",
)


class InstrumentReader(Protocol):
    """Narrow read-only surface used by the infrastructure check."""

    def get_payment_instrument(
        self,
        payment_instrument_id: str,
        user_id: str | None = None,
        payment_connector_id: str | None = None,
    ) -> dict[str, Any]: ...

    def get_payment_instrument_balance(
        self,
        payment_connector_id: str,
        payment_instrument_id: str,
        chain: str,
        token: str,
        user_id: str | None = None,
    ) -> dict[str, Any]: ...


ManagerFactory = Callable[[Mapping[str, str]], InstrumentReader]


def _manager(values: Mapping[str, str]) -> InstrumentReader:
    import boto3
    from bedrock_agentcore.payments import PaymentManager

    profile = values["AGENTCORE_RUNTIME_AWS_PROFILE"].strip()
    region = _resolve_agentcore_region(values)
    session = boto3.Session(profile_name=profile, region_name=region)
    _disable_agentcore_sdk_logging()
    return PaymentManager(
        payment_manager_arn=values["PAYMENT_MANAGER_ARN"].strip(),
        region_name=region,
        boto3_session=session,
    )


def _instrument_network(instrument: Mapping[str, Any]) -> str:
    details = instrument.get("paymentInstrumentDetails", {})
    if not isinstance(details, Mapping):
        return "unknown"
    wallet = details.get("embeddedCryptoWallet", {})
    if not isinstance(wallet, Mapping):
        return "unknown"
    network = wallet.get("network")
    return str(network) if network else "unknown"


def _balance_scope(balance: Mapping[str, Any]) -> tuple[str, str]:
    token_balance = balance.get("tokenBalance", {})
    if not isinstance(token_balance, Mapping):
        return "unknown", "unknown"
    chain = token_balance.get("chain")
    token = token_balance.get("token")
    return (
        str(chain).upper() if chain else "unknown",
        str(token).upper() if token else "unknown",
    )


def readiness_report(
    environ: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Report whether a read-only AWS check can run, without calling AWS."""

    values = environ if environ is not None else os.environ
    region = _resolve_agentcore_region(values)
    configured = {
        name: bool(values.get(name, "").strip()) for name in _REQUIRED_CONFIGURATION
    }
    configured["AGENTCORE_AWS_REGION"] = bool(region)
    enabled = values.get(_READ_ONLY_OPT_IN) == "1"
    ready = (
        enabled
        and all(configured.values())
        and region in _SUPPORTED_AGENTCORE_PAYMENT_REGIONS
    )
    return {
        "result": "READY" if ready else "NOT_READY",
        "read_only_opt_in": enabled,
        "configuration_present": configured,
        "agentcore_region": region or "missing",
        "agentcore_region_supported": (region in _SUPPORTED_AGENTCORE_PAYMENT_REGIONS),
        "aws_calls": 0,
        "payment_attempts": 0,
        "value_transferred": False,
        "identifiers_logged": False,
    }


def inspect_payment_instrument(
    environ: Mapping[str, str] | None = None,
    *,
    manager_factory: ManagerFactory | None = None,
) -> dict[str, object]:
    """Read and sanitize instrument status without creating payment state."""

    values = environ if environ is not None else os.environ
    readiness = readiness_report(values)
    if readiness["result"] != "READY":
        return {
            **readiness,
            "result": "SKIPPED",
            "reason": (
                "The explicit read-only gate and complete AWS configuration "
                "are required."
            ),
        }

    aws_calls = 0
    try:
        manager = (manager_factory or _manager)(values)
        aws_calls += 1
        instrument = manager.get_payment_instrument(
            payment_instrument_id=values["PAYMENT_INSTRUMENT_ID"].strip(),
            user_id=values["PAYMENT_USER_ID"].strip(),
        )
        status = str(instrument.get("status", "unknown")).upper()
        network = _instrument_network(instrument).upper()
        chain = "not_checked"
        token = "not_checked"
        if status == "ACTIVE" and network == _EXPECTED_INSTRUMENT_NETWORK:
            aws_calls += 1
            balance = manager.get_payment_instrument_balance(
                payment_connector_id=values["PAYMENT_CONNECTOR_ID"].strip(),
                payment_instrument_id=values["PAYMENT_INSTRUMENT_ID"].strip(),
                chain=_EXPECTED_CHAIN,
                token=_EXPECTED_TOKEN,
                user_id=values["PAYMENT_USER_ID"].strip(),
            )
            chain, token = _balance_scope(balance)
    except Exception as exc:  # noqa: BLE001
        return {
            "result": "BLOCKED",
            "category": "agentcore_read_only_check_failed",
            "exception_type": type(exc).__name__,
            "next_action": (
                "Review the local AWS profile and sanitized AgentCore logs. "
                "Do not paste provider errors into the notebook."
            ),
            "aws_calls": aws_calls,
            "payment_attempts": 0,
            "value_transferred": False,
            "identifiers_logged": False,
        }

    exact_scope = (
        status == "ACTIVE"
        and network == _EXPECTED_INSTRUMENT_NETWORK
        and chain == _EXPECTED_CHAIN
        and token == _EXPECTED_TOKEN
    )
    return {
        "result": "PASSED" if exact_scope else "NOT_READY",
        "payment_manager_reachable": True,
        "payment_instrument_status": status,
        "payment_instrument_network": network,
        "payment_instrument_chain": chain,
        "payment_instrument_token": token,
        "exact_testnet_scope_verified": exact_scope,
        "aws_calls": aws_calls,
        "payment_attempts": 0,
        "value_transferred": False,
        "identifiers_logged": False,
        "note": (
            "This verifies read access, active instrument state, and the "
            "configured Base Sepolia USDC balance scope only. It does not "
            "create a session, generate a proof, contact a merchant, or "
            "verify settlement."
        ),
    }


def main() -> None:
    report = inspect_payment_instrument()
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["result"] != "PASSED":
        raise SystemExit(2 if report["result"] in {"NOT_READY", "SKIPPED"} else 1)


if __name__ == "__main__":
    main()
