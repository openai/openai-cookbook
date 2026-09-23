"""Managed, explicitly opted-in AgentCore testnet notebook runner."""

from __future__ import annotations

import argparse
import asyncio
import importlib.metadata
import json
import os
from collections.abc import Awaitable, Callable, Mapping, Sequence
from decimal import Decimal
from pathlib import Path

from agents.models.openai_responses import OpenAIResponsesModel
from openai import AsyncOpenAI
from openai.providers import bedrock

from .agentcore_agent import AgentCoreAgentRun, run_agentcore_access
from .agentcore_payments import (
    _REQUIRED_CONFIGURATION,
    _SUPPORTED_AGENTCORE_PAYMENT_REGIONS,
    AgentCorePaymentsSettings,
    _positive_integer_text,
    _proxy_environment_clear,
    _reject_proxy_environment,
    _resolve_agentcore_region,
)
from .agentcore_runtime import build_live_agentcore_context
from .agentcore_session import (
    PaymentSessionManager,
    _manager,
    _read_session_state,
    _session_file,
    create_bounded_session,
    delete_recorded_session,
    runtime_environment_from_recorded_session,
)
from .errors import CommerceError

_MASTER_OPT_IN = "RUN_AGENTCORE_E2E"
_REQUIRED_OPT_INS = (
    _MASTER_OPT_IN,
    "ALLOW_AGENTCORE_SESSION_ADMIN",
    "ALLOW_PAID_INFERENCE",
    "ALLOW_AGENTCORE_TESTNET",
    "APPROVE_AGENTCORE_TESTNET_PURCHASE",
)
_SESSION_EXPIRY_MINUTES = 15
_USDC_ATOMIC_SCALE = Decimal(1_000_000)
_MAX_SESSION_BUDGET_USD = Decimal("0.01")
_PURPOSE = "testnet_integration_validation"

ManagerFactory = Callable[[Mapping[str, str]], PaymentSessionManager]
CombinedRunner = Callable[[Mapping[str, str]], Awaitable[dict[str, object]]]


def _blocked_report(exc: Exception) -> dict[str, object]:
    return {
        "result": "BLOCKED",
        "category": "combined_runtime_error",
        "exception_type": type(exc).__name__,
        "next_action": (
            "Review the local provider and AgentCore logs, then rerun only "
            "after confirming the bounded testnet controls."
        ),
        "proof_headers_logged": False,
        "value_transferred": "unknown",
    }


def _bedrock_profile(values: Mapping[str, str]) -> str:
    profile = values.get("BEDROCK_AWS_PROFILE", "").strip()
    if not profile:
        raise CommerceError(
            "bedrock_profile_missing",
            "BEDROCK_AWS_PROFILE is required for paid model inference.",
        )
    return profile


def _require_live_opt_ins(values: Mapping[str, str]) -> None:
    missing = [name for name in _REQUIRED_OPT_INS if values.get(name) != "1"]
    if missing:
        raise CommerceError(
            "agentcore_live_opt_ins_missing",
            "The combined live path requires these explicit opt-ins: "
            + ", ".join(f"{name}=1" for name in missing),
        )


def _combined_success_report(result: AgentCoreAgentRun) -> dict[str, object]:
    if result.access.status_code != 200:
        raise CommerceError(
            "merchant_paid_retry_incomplete",
            "The merchant did not return HTTP 200 for the paid retry.",
        )

    return {
        "result": "PASSED",
        "model_run_completed": True,
        "agentcore_payment_path_completed": True,
        "merchant_paid_retry_completed": True,
        "merchant": result.access.merchant,
        "status_code": result.access.status_code,
        "payment_attempts": result.access.payment_attempts,
        "authorized_amount": str(result.access.challenge.amount),
        "currency": result.access.challenge.currency,
        "network": result.access.challenge.network,
        "response_sha256": result.access.response_sha256,
        "proof_headers_logged": False,
        "settlement_verified": False,
        "testnet_only": True,
    }


async def _execute_combined(
    environ: Mapping[str, str],
) -> dict[str, object]:
    _require_live_opt_ins(environ)
    _reject_proxy_environment(environ)
    settings = AgentCorePaymentsSettings.from_env(environ)
    resource_url = environ.get("X402_RESOURCE_URL", "").strip()
    idempotency_key = environ.get("X402_IDEMPOTENCY_KEY", "").strip()
    if not resource_url or not idempotency_key:
        raise CommerceError(
            "agentcore_agent_configuration_missing",
            "X402_RESOURCE_URL and X402_IDEMPOTENCY_KEY are required.",
        )
    context = build_live_agentcore_context(
        settings,
        resource_url=resource_url,
        idempotency_key=idempotency_key,
        purpose=_PURPOSE,
    )
    model_region = environ.get("AWS_REGION", "us-east-2")
    model_id = environ.get("BEDROCK_MODEL", "openai.gpt-5.6-sol")
    model = OpenAIResponsesModel(
        model=model_id,
        openai_client=AsyncOpenAI(
            provider=bedrock(
                region=model_region,
                profile=_bedrock_profile(environ),
            )
        ),
    )
    result = await run_agentcore_access(
        context.application,
        model=model,
        request_id=context.request.request_id,
        idempotency_key=context.request.idempotency_key,
        approval=context.approval,
        resource_url=str(context.request.resource_url),
        purpose=context.request.purpose,
    )
    return _combined_success_report(result)


def _session_budget(values: Mapping[str, str]) -> Decimal | None:
    raw_amount_atomic = values.get("X402_MAX_APPROVED_AMOUNT_ATOMIC", "").strip()
    if not _positive_integer_text(raw_amount_atomic):
        return None
    amount_atomic = Decimal(int(raw_amount_atomic))
    budget = amount_atomic / _USDC_ATOMIC_SCALE
    if budget <= 0 or budget > _MAX_SESSION_BUDGET_USD:
        return None
    return budget


def readiness_report(
    environ: Mapping[str, str] | None = None,
    *,
    session_file: Path | None = None,
) -> dict[str, object]:
    """Return presence and gate status without making a live call."""

    values = environ if environ is not None else os.environ
    missing_opt_ins = [
        f"{name}=1" for name in _REQUIRED_OPT_INS if values.get(name) != "1"
    ]
    required_runtime_names = tuple(
        name for name in _REQUIRED_CONFIGURATION if name != "PAYMENT_SESSION_ID"
    ) + ("X402_RESOURCE_URL", "X402_IDEMPOTENCY_KEY")
    configuration_present = {
        name: bool(values.get(name, "").strip()) for name in required_runtime_names
    }
    session_profile = values.get("AGENTCORE_SESSION_AWS_PROFILE", "").strip()
    model_profile = values.get("BEDROCK_AWS_PROFILE", "").strip()
    runtime_profile = values.get("AGENTCORE_RUNTIME_AWS_PROFILE", "").strip()
    profiles_present = bool(session_profile and model_profile and runtime_profile)
    profiles_separated = (
        profiles_present
        and session_profile != runtime_profile
        and model_profile != runtime_profile
    )
    agentcore_region = _resolve_agentcore_region(values)
    region_supported = agentcore_region in _SUPPORTED_AGENTCORE_PAYMENT_REGIONS
    one_payment_attempt = values.get("X402_MAX_PAYMENT_ATTEMPTS") == "1"
    session_budget = _session_budget(values)
    proxy_environment_clear = _proxy_environment_clear(values)
    path = _session_file(values, session_file)
    try:
        state = _read_session_state(path)
        session_state_valid = True
        recorded_session_present = bool(state.get("PAYMENT_SESSION_ID"))
    except (CommerceError, OSError):
        session_state_valid = False
        recorded_session_present = False
    try:
        sdk_version = importlib.metadata.version("bedrock-agentcore")
    except importlib.metadata.PackageNotFoundError:
        sdk_version = None

    ready = (
        not missing_opt_ins
        and all(configuration_present.values())
        and profiles_separated
        and region_supported
        and one_payment_attempt
        and session_budget is not None
        and proxy_environment_clear
        and session_state_valid
        and not recorded_session_present
        and sdk_version == "1.18.1"
    )
    return {
        "result": "READY" if ready else "NOT_READY",
        "live_calls": 0,
        "value_transferred": False,
        "missing_opt_ins": missing_opt_ins,
        "configuration_present": configuration_present,
        "separate_aws_profiles_present": profiles_present,
        "aws_profiles_are_distinct": profiles_separated,
        "bedrock_profile_present": bool(model_profile),
        "model_and_payment_profiles_are_distinct": bool(
            model_profile and runtime_profile and model_profile != runtime_profile
        ),
        "agentcore_region": agentcore_region or "missing",
        "agentcore_region_supported": region_supported,
        "one_payment_attempt_configured": one_payment_attempt,
        "session_budget_valid": session_budget is not None,
        "merchant_proxy_environment_clear": proxy_environment_clear,
        "session_expiry_minutes": _SESSION_EXPIRY_MINUTES,
        "local_session_state_valid": session_state_valid,
        "recorded_session_present": recorded_session_present,
        "bedrock_agentcore_sdk": sdk_version or "missing",
        "bedrock_agentcore_sdk_expected": "1.18.1",
        "note": (
            "This check does not contact AWS, the model, the merchant, "
            "the wallet, or a blockchain."
        ),
    }


async def run_managed_e2e(
    environ: Mapping[str, str] | None = None,
    *,
    manager_factory: ManagerFactory | None = None,
    combined_runner: CombinedRunner | None = None,
    session_file: Path | None = None,
) -> dict[str, object]:
    """Create, use, and delete one bounded session around one live run."""

    values = dict(environ if environ is not None else os.environ)
    readiness = readiness_report(values, session_file=session_file)
    if readiness["result"] != "READY":
        return {
            **readiness,
            "result": "SKIPPED",
            "reason": "The managed end-to-end gates are not ready.",
        }

    build_manager = manager_factory or _manager
    run_combined = combined_runner or _execute_combined
    manager: PaymentSessionManager | None = None
    session_created = False
    execution_started = False
    cleanup_result = "NOT_REQUIRED"
    run_report: dict[str, object] | None = None
    failure_report: dict[str, object] | None = None
    budget = _session_budget(values)
    if budget is None:
        raise AssertionError("readiness accepted an invalid session budget")

    try:
        manager = build_manager(values)
        create_bounded_session(
            manager,
            environ=values,
            session_file=session_file,
            budget_usd=budget,
            expiry_minutes=_SESSION_EXPIRY_MINUTES,
        )
        session_created = True
        runtime_environment = runtime_environment_from_recorded_session(
            values,
            session_file=session_file,
        )
        execution_started = True
        run_report = await run_combined(runtime_environment)
        if run_report.get("result") != "PASSED":
            raise CommerceError(
                "agentcore_e2e_result_invalid",
                "The combined runner did not return a passing result.",
            )
    except CommerceError as exc:
        failure_report = {
            "result": "FAILED",
            "code": exc.code,
            "message": str(exc),
            "proof_headers_logged": False,
            "value_transferred": ("unknown" if execution_started else False),
        }
        if exc.diagnostics:
            failure_report["diagnostics"] = exc.diagnostics
    except Exception as exc:  # noqa: BLE001
        failure_report = _blocked_report(exc)
    finally:
        if session_created and manager is not None:
            try:
                deletion = delete_recorded_session(
                    manager,
                    environ=values,
                    session_file=session_file,
                )
                cleanup_result = str(deletion["result"])
            except Exception as exc:  # noqa: BLE001
                cleanup_result = "FAILED"
                if failure_report is None:
                    failure_report = {
                        **_blocked_report(exc),
                        "category": "payment_session_cleanup_error",
                        "next_action": (
                            "Delete the recorded bounded session with the "
                            "session-administration role before another run."
                        ),
                    }
                else:
                    failure_report["cleanup_next_action"] = (
                        "Delete the recorded bounded session with the "
                        "session-administration role before another run."
                    )

    if failure_report is not None:
        return {
            **failure_report,
            "mode": "managed_agentcore_testnet_e2e",
            "session_created": session_created,
            "session_cleanup": cleanup_result,
            "identifiers_logged": False,
            "testnet_only": True,
        }
    if run_report is None:
        raise AssertionError("managed run completed without a report")
    return {
        **run_report,
        "mode": "managed_agentcore_testnet_e2e",
        "session_created": True,
        "session_budget_usd": format(budget, "f"),
        "session_expiry_minutes": _SESSION_EXPIRY_MINUTES,
        "session_cleanup": cleanup_result,
        "identifiers_logged": False,
        "settlement_verified": False,
        "testnet_only": True,
    }


async def run() -> None:
    report = await run_managed_e2e()
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["result"] != "PASSED":
        raise SystemExit(2 if report["result"] == "SKIPPED" else 1)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one managed AgentCore testnet integration test."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Print no-call readiness only; never start the live workflow.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    if args.check:
        report = readiness_report()
        print(json.dumps(report, indent=2, sort_keys=True))
        if report["result"] != "READY":
            raise SystemExit(2)
        return
    asyncio.run(run())


if __name__ == "__main__":
    main()
