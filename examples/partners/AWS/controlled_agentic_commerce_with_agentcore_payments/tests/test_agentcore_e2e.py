from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from agentic_commerce import agentcore_e2e
from agentic_commerce.agentcore_e2e import (
    readiness_report,
    run_managed_e2e,
)
from agentic_commerce.errors import AgentCorePaymentError, CommerceError

ASSET = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"


class FakeSessionManager:
    def __init__(
        self,
        *,
        delete_error: Exception | None = None,
    ) -> None:
        self.delete_error = delete_error
        self.create_calls: list[dict[str, Any]] = []
        self.delete_calls: list[dict[str, Any]] = []

    def create_payment_session(self, **kwargs: Any) -> dict[str, Any]:
        self.create_calls.append(kwargs)
        return {"paymentSessionId": "session-sensitive-e2e"}

    def delete_payment_session(
        self,
        payment_session_id: str,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        self.delete_calls.append(
            {
                "payment_session_id": payment_session_id,
                "user_id": user_id,
            }
        )
        if self.delete_error is not None:
            raise self.delete_error
        return {"status": "DELETED"}


def environment(tmp_path: Path) -> dict[str, str]:
    return {
        "RUN_AGENTCORE_E2E": "1",
        "ALLOW_AGENTCORE_SESSION_ADMIN": "1",
        "ALLOW_PAID_INFERENCE": "1",
        "ALLOW_AGENTCORE_TESTNET": "1",
        "APPROVE_AGENTCORE_TESTNET_PURCHASE": "1",
        "BEDROCK_AWS_PROFILE": "model-inference",
        "AGENTCORE_SESSION_AWS_PROFILE": "session-admin",
        "AGENTCORE_RUNTIME_AWS_PROFILE": "payment-runtime",
        "AGENTCORE_SESSION_FILE": str(tmp_path / "session.env"),
        "AGENTCORE_AWS_REGION": "us-east-1",
        "PAYMENT_MANAGER_ARN": "manager-sensitive-e2e",
        "PAYMENT_INSTRUMENT_ID": "instrument-sensitive-e2e",
        "PAYMENT_USER_ID": "user-sensitive-e2e",
        "X402_ALLOWED_MERCHANTS": "merchant.example",
        "X402_APPROVED_ASSET": ASSET,
        "X402_APPROVED_PAY_TO": "synthetic-testnet-recipient",
        "X402_MAX_APPROVED_AMOUNT_ATOMIC": "2000",
        "X402_MAX_PAYMENT_ATTEMPTS": "1",
        "X402_RESOURCE_URL": "https://merchant.example/report",
        "X402_IDEMPOTENCY_KEY": "purchase-e2e-test-001",
    }


def sdk_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        agentcore_e2e.importlib.metadata,
        "version",
        lambda _: "1.18.1",
    )


def test_readiness_requires_master_gate_before_any_live_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sdk_available(monkeypatch)
    values = environment(tmp_path)
    values["RUN_AGENTCORE_E2E"] = "0"

    report = readiness_report(values)

    assert report["result"] == "NOT_READY"
    assert report["missing_opt_ins"] == ["RUN_AGENTCORE_E2E=1"]
    assert report["live_calls"] == 0
    assert report["value_transferred"] is False


def test_execute_combined_rechecks_all_live_opt_ins() -> None:
    with pytest.raises(CommerceError) as exc_info:
        asyncio.run(agentcore_e2e._execute_combined({}))

    assert exc_info.value.code == "agentcore_live_opt_ins_missing"


def test_combined_report_rejects_incomplete_paid_retry() -> None:
    result = SimpleNamespace(access=SimpleNamespace(status_code=204))

    with pytest.raises(CommerceError) as exc_info:
        agentcore_e2e._combined_success_report(result)

    assert exc_info.value.code == "merchant_paid_retry_incomplete"


def test_readiness_rejects_proxy_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sdk_available(monkeypatch)
    values = environment(tmp_path)
    values["HTTPS_PROXY"] = "http://proxy.example:8080"

    report = readiness_report(values)

    assert report["result"] == "NOT_READY"
    assert report["merchant_proxy_environment_clear"] is False


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "2e3"])
def test_readiness_rejects_invalid_session_budget(
    value: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sdk_available(monkeypatch)
    values = environment(tmp_path)
    values["X402_MAX_APPROVED_AMOUNT_ATOMIC"] = value

    report = readiness_report(values)

    assert report["result"] == "NOT_READY"
    assert report["session_budget_valid"] is False


def test_readiness_requires_distinct_admin_and_runtime_profiles(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sdk_available(monkeypatch)
    values = environment(tmp_path)
    values["AGENTCORE_RUNTIME_AWS_PROFILE"] = "session-admin"

    report = readiness_report(values)

    assert report["result"] == "NOT_READY"
    assert report["separate_aws_profiles_present"] is True
    assert report["aws_profiles_are_distinct"] is False


def test_readiness_requires_distinct_model_and_payment_profiles(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sdk_available(monkeypatch)
    values = environment(tmp_path)
    values["BEDROCK_AWS_PROFILE"] = "payment-runtime"

    report = readiness_report(values)

    assert report["result"] == "NOT_READY"
    assert report["bedrock_profile_present"] is True
    assert report["model_and_payment_profiles_are_distinct"] is False
    assert report["aws_profiles_are_distinct"] is False


def test_managed_e2e_checks_the_overridden_session_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sdk_available(monkeypatch)
    values = environment(tmp_path)
    override = tmp_path / "override.env"
    override.write_text(
        "PAYMENT_SESSION_ID=existing-session\n",
        encoding="utf-8",
    )
    manager = FakeSessionManager()

    report = asyncio.run(
        run_managed_e2e(
            values,
            manager_factory=lambda _: manager,
            session_file=override,
        )
    )

    assert report["result"] == "SKIPPED"
    assert report["recorded_session_present"] is True
    assert manager.create_calls == []
    assert manager.delete_calls == []


def test_check_cli_never_starts_managed_workflow(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        agentcore_e2e,
        "readiness_report",
        lambda: {"result": "READY", "live_calls": 0},
    )
    monkeypatch.setattr(
        agentcore_e2e.asyncio,
        "run",
        lambda _: pytest.fail("managed workflow must not start"),
    )

    agentcore_e2e.main(["--check"])

    assert json.loads(capsys.readouterr().out) == {
        "result": "READY",
        "live_calls": 0,
    }


def test_check_cli_returns_nonzero_when_not_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        agentcore_e2e,
        "readiness_report",
        lambda: {"result": "NOT_READY", "live_calls": 0},
    )

    with pytest.raises(SystemExit) as exc_info:
        agentcore_e2e.main(["--check"])

    assert exc_info.value.code == 2


def test_live_cli_returns_nonzero_when_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def skipped() -> dict[str, object]:
        return {"result": "SKIPPED"}

    monkeypatch.setattr(agentcore_e2e, "run_managed_e2e", skipped)

    with pytest.raises(SystemExit) as exc_info:
        asyncio.run(agentcore_e2e.run())

    assert exc_info.value.code == 2


def test_managed_e2e_creates_runs_and_deletes_without_logging_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sdk_available(monkeypatch)
    values = environment(tmp_path)
    manager = FakeSessionManager()
    observed_session_id = ""

    async def combined_runner(
        runtime_environment: dict[str, str],
    ) -> dict[str, object]:
        nonlocal observed_session_id
        observed_session_id = runtime_environment["PAYMENT_SESSION_ID"]
        return {
            "result": "PASSED",
            "model_run_completed": True,
            "agentcore_payment_path_completed": True,
            "merchant_paid_retry_completed": True,
            "status_code": 200,
            "payment_attempts": 1,
            "authorized_amount": "0.002",
            "currency": "USDC",
            "network": "eip155:84532",
            "proof_headers_logged": False,
            "settlement_verified": False,
        }

    report = asyncio.run(
        run_managed_e2e(
            values,
            manager_factory=lambda _: manager,
            combined_runner=combined_runner,
        )
    )
    rendered = json.dumps(report)

    assert report["result"] == "PASSED"
    assert report["session_created"] is True
    assert report["session_budget_usd"] == "0.002"
    assert report["session_expiry_minutes"] == 15
    assert report["session_cleanup"] == "DELETED"
    assert report["identifiers_logged"] is False
    assert report["settlement_verified"] is False
    assert observed_session_id == "session-sensitive-e2e"
    assert len(manager.create_calls) == 1
    assert len(manager.delete_calls) == 1
    assert not (tmp_path / "session.env").exists()
    assert "session-sensitive-e2e" not in rendered
    assert "manager-sensitive-e2e" not in rendered
    assert "instrument-sensitive-e2e" not in rendered
    assert "user-sensitive-e2e" not in rendered


def test_managed_e2e_deletes_session_after_runtime_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sdk_available(monkeypatch)
    values = environment(tmp_path)
    manager = FakeSessionManager()

    async def failing_runner(_: dict[str, str]) -> dict[str, object]:
        raise RuntimeError("provider-secret session-sensitive-e2e")

    report = asyncio.run(
        run_managed_e2e(
            values,
            manager_factory=lambda _: manager,
            combined_runner=failing_runner,
        )
    )
    rendered = json.dumps(report)

    assert report["result"] == "BLOCKED"
    assert report["session_cleanup"] == "DELETED"
    assert report["value_transferred"] == "unknown"
    assert len(manager.delete_calls) == 1
    assert not (tmp_path / "session.env").exists()
    assert "provider-secret" not in rendered
    assert "session-sensitive-e2e" not in rendered


def test_managed_e2e_returns_safe_payment_diagnostics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sdk_available(monkeypatch)
    values = environment(tmp_path)
    manager = FakeSessionManager()

    async def failing_runner(_: dict[str, str]) -> dict[str, object]:
        raise AgentCorePaymentError(
            "payment_header_generation_failed",
            "AgentCore Payments could not generate a testnet payment header.",
            diagnostics={
                "stage": "agentcore_process_payment",
                "category": "aws_validation",
                "provider_message_logged": False,
                "request_id_logged": False,
                "aws_error_code": "ValidationException",
                "http_status_code": 400,
            },
        )

    report = asyncio.run(
        run_managed_e2e(
            values,
            manager_factory=lambda _: manager,
            combined_runner=failing_runner,
        )
    )
    rendered = json.dumps(report)

    assert report["result"] == "FAILED"
    assert report["session_cleanup"] == "DELETED"
    assert report["diagnostics"] == {
        "stage": "agentcore_process_payment",
        "category": "aws_validation",
        "provider_message_logged": False,
        "request_id_logged": False,
        "aws_error_code": "ValidationException",
        "http_status_code": 400,
    }
    assert "manager-sensitive-e2e" not in rendered
    assert "instrument-sensitive-e2e" not in rendered
    assert "user-sensitive-e2e" not in rendered


def test_managed_e2e_retains_state_when_cleanup_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sdk_available(monkeypatch)
    values = environment(tmp_path)
    manager = FakeSessionManager(delete_error=RuntimeError("provider-secret"))

    async def combined_runner(_: dict[str, str]) -> dict[str, object]:
        return {"result": "PASSED", "status_code": 200}

    report = asyncio.run(
        run_managed_e2e(
            values,
            manager_factory=lambda _: manager,
            combined_runner=combined_runner,
        )
    )
    rendered = json.dumps(report)

    assert report["result"] == "BLOCKED"
    assert report["category"] == "payment_session_cleanup_error"
    assert report["session_cleanup"] == "FAILED"
    assert (tmp_path / "session.env").exists()
    assert "provider-secret" not in rendered
    assert "session-sensitive-e2e" not in rendered


def test_runtime_failure_and_cleanup_failure_preserve_cleanup_action(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sdk_available(monkeypatch)
    values = environment(tmp_path)
    manager = FakeSessionManager(delete_error=RuntimeError("cleanup-secret"))

    async def failing_runner(_: dict[str, str]) -> dict[str, object]:
        raise RuntimeError("runtime-secret")

    report = asyncio.run(
        run_managed_e2e(
            values,
            manager_factory=lambda _: manager,
            combined_runner=failing_runner,
        )
    )
    rendered = json.dumps(report)

    assert report["result"] == "BLOCKED"
    assert report["session_cleanup"] == "FAILED"
    assert "Delete the recorded bounded session" in str(report["cleanup_next_action"])
    assert "runtime-secret" not in rendered
    assert "cleanup-secret" not in rendered
