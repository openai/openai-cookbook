from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from agentic_commerce import agentcore_session
from agentic_commerce.agentcore_session import (
    create_bounded_session,
    delete_recorded_session,
    runtime_environment_from_recorded_session,
)
from agentic_commerce.errors import AgentCorePaymentError


class FakeSessionManager:
    def __init__(
        self,
        *,
        create_error: Exception | None = None,
        delete_error: Exception | None = None,
        delete_status: str = "DELETED",
    ) -> None:
        self.create_error = create_error
        self.delete_error = delete_error
        self.delete_status = delete_status
        self.create_calls: list[dict[str, Any]] = []
        self.delete_calls: list[dict[str, Any]] = []

    def create_payment_session(self, **kwargs: Any) -> dict[str, Any]:
        self.create_calls.append(kwargs)
        if self.create_error:
            raise self.create_error
        return {"paymentSessionId": "session-sensitive-test"}

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
        if self.delete_error:
            raise self.delete_error
        return {"status": self.delete_status}


def environment(*, enabled: bool = True) -> dict[str, str]:
    return {
        "ALLOW_AGENTCORE_SESSION_ADMIN": "1" if enabled else "0",
        "AGENTCORE_AWS_REGION": "us-east-1",
        "PAYMENT_MANAGER_ARN": "manager-sensitive-test",
        "PAYMENT_USER_ID": "user-sensitive-test",
    }


def test_create_requires_explicit_session_admin_opt_in(tmp_path: Path) -> None:
    manager = FakeSessionManager()

    with pytest.raises(AgentCorePaymentError) as exc_info:
        create_bounded_session(
            manager,
            environ=environment(enabled=False),
            session_file=tmp_path / "session.env",
        )

    assert exc_info.value.code == "payment_session_admin_disabled"
    assert manager.create_calls == []


def test_live_session_admin_fails_cleanly_without_posix_locking(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = FakeSessionManager()
    monkeypatch.setattr(agentcore_session, "fcntl", None)

    with pytest.raises(AgentCorePaymentError) as exc_info:
        create_bounded_session(
            manager,
            environ=environment(),
            session_file=tmp_path / "session.env",
        )

    assert exc_info.value.code == "payment_session_platform_unsupported"
    assert manager.create_calls == []


def test_cli_checks_opt_in_before_constructing_manager(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("ALLOW_AGENTCORE_SESSION_ADMIN", "0")
    monkeypatch.setattr(
        agentcore_session,
        "_manager",
        lambda environ: pytest.fail("manager must not be constructed"),
    )

    with pytest.raises(SystemExit) as exc_info:
        agentcore_session.main(["create"])

    assert exc_info.value.code == 1
    assert "payment_session_admin_disabled" in capsys.readouterr().out


def test_session_admin_profile_is_passed_to_payment_manager(
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
    values = environment()
    values["AGENTCORE_SESSION_AWS_PROFILE"] = "session-admin"

    agentcore_session._manager(values)

    assert captured["profile_name"] == "session-admin"
    assert captured["region_name"] == "us-east-1"
    manager_kwargs = captured["manager_kwargs"]
    assert isinstance(manager_kwargs, dict)
    assert manager_kwargs["boto3_session"] is captured["boto3_session"]


def test_create_records_identifiers_without_returning_them(tmp_path: Path) -> None:
    manager = FakeSessionManager()
    session_file = tmp_path / "session.env"

    report = create_bounded_session(
        manager,
        environ=environment(),
        session_file=session_file,
        budget_usd=Decimal("0.01"),
        expiry_minutes=30,
        token_factory=lambda: "stable-session-token",
    )

    rendered = str(report)
    state = session_file.read_text(encoding="utf-8")
    assert report["result"] == "CREATED"
    assert report["value_transferred"] is False
    assert "session-sensitive-test" not in rendered
    assert "stable-session-token" not in rendered
    assert "PAYMENT_SESSION_ID=session-sensitive-test" in state
    assert "PAYMENT_SESSION_CLIENT_TOKEN=stable-session-token" in state
    assert session_file.stat().st_mode & 0o777 == 0o600
    assert manager.create_calls == [
        {
            "user_id": "user-sensitive-test",
            "limits": {
                "maxSpendAmount": {
                    "value": "0.01",
                    "currency": "USD",
                }
            },
            "expiry_time_in_minutes": 30,
            "client_token": "stable-session-token",
        }
    ]


def test_failed_create_reuses_the_recorded_client_token(tmp_path: Path) -> None:
    session_file = tmp_path / "session.env"
    failing = FakeSessionManager(create_error=RuntimeError("provider detail"))

    with pytest.raises(AgentCorePaymentError) as exc_info:
        create_bounded_session(
            failing,
            environ=environment(),
            session_file=session_file,
            token_factory=lambda: "stable-session-token",
        )

    assert exc_info.value.code == "payment_session_create_failed"
    assert "provider detail" not in str(exc_info.value)
    succeeding = FakeSessionManager()
    create_bounded_session(
        succeeding,
        environ=environment(),
        session_file=session_file,
        token_factory=lambda: "different-token",
    )
    assert succeeding.create_calls[0]["client_token"] == "stable-session-token"


def test_existing_recorded_session_prevents_overwrite(tmp_path: Path) -> None:
    session_file = tmp_path / "session.env"
    session_file.write_text(
        "PAYMENT_SESSION_CLIENT_TOKEN=stable-session-token\n"
        "PAYMENT_SESSION_ID=existing-session\n",
        encoding="utf-8",
    )
    manager = FakeSessionManager()

    with pytest.raises(AgentCorePaymentError) as exc_info:
        create_bounded_session(
            manager,
            environ=environment(),
            session_file=session_file,
        )

    assert exc_info.value.code == "payment_session_already_recorded"
    assert manager.create_calls == []


def test_persistence_failure_deletes_newly_created_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_file = tmp_path / "session.env"
    manager = FakeSessionManager()
    original_write = agentcore_session._write_session_state
    writes = 0

    def fail_second_write(path: Path, state: dict[str, str]) -> None:
        nonlocal writes
        writes += 1
        if writes == 2:
            raise AgentCorePaymentError(
                "payment_session_state_write_failed",
                "Synthetic persistence failure.",
            )
        original_write(path, state)

    monkeypatch.setattr(agentcore_session, "_write_session_state", fail_second_write)

    with pytest.raises(AgentCorePaymentError) as exc_info:
        create_bounded_session(
            manager,
            environ=environment(),
            session_file=session_file,
            token_factory=lambda: "stable-session-token",
        )

    assert exc_info.value.code == "payment_session_state_write_failed"
    assert manager.delete_calls == [
        {
            "payment_session_id": "session-sensitive-test",
            "user_id": "user-sensitive-test",
        }
    ]
    assert not session_file.exists()


def test_concurrent_creation_allows_only_one_session(tmp_path: Path) -> None:
    session_file = tmp_path / "session.env"
    manager = FakeSessionManager()

    def create() -> str:
        try:
            create_bounded_session(
                manager,
                environ=environment(),
                session_file=session_file,
                token_factory=lambda: "stable-session-token",
            )
        except AgentCorePaymentError as exc:
            return exc.code
        return "CREATED"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = sorted(executor.map(lambda _: create(), range(2)))

    assert results == ["CREATED", "payment_session_already_recorded"]
    assert len(manager.create_calls) == 1


def test_delete_removes_local_state_after_agentcore_success(
    tmp_path: Path,
) -> None:
    session_file = tmp_path / "session.env"
    session_file.write_text(
        "PAYMENT_SESSION_CLIENT_TOKEN=stable-session-token\n"
        "PAYMENT_SESSION_ID=session-sensitive-test\n",
        encoding="utf-8",
    )
    manager = FakeSessionManager()

    report = delete_recorded_session(
        manager,
        environ=environment(),
        session_file=session_file,
    )

    assert report["result"] == "DELETED"
    assert report["value_transferred"] is False
    assert "session-sensitive-test" not in str(report)
    assert manager.delete_calls == [
        {
            "payment_session_id": "session-sensitive-test",
            "user_id": "user-sensitive-test",
        }
    ]
    assert not session_file.exists()


def test_runtime_environment_uses_recorded_id_without_mutating_input(
    tmp_path: Path,
) -> None:
    session_file = tmp_path / "session.env"
    session_file.write_text(
        "PAYMENT_SESSION_CLIENT_TOKEN=stable-session-token\n"
        "PAYMENT_SESSION_ID=session-sensitive-test\n",
        encoding="utf-8",
    )
    original = environment()

    runtime = runtime_environment_from_recorded_session(
        original,
        session_file=session_file,
    )

    assert "PAYMENT_SESSION_ID" not in original
    assert runtime["PAYMENT_SESSION_ID"] == "session-sensitive-test"


def test_delete_failure_retains_local_state(tmp_path: Path) -> None:
    session_file = tmp_path / "session.env"
    session_file.write_text(
        "PAYMENT_SESSION_CLIENT_TOKEN=stable-session-token\n"
        "PAYMENT_SESSION_ID=session-sensitive-test\n",
        encoding="utf-8",
    )
    manager = FakeSessionManager(delete_error=RuntimeError("provider detail"))

    with pytest.raises(AgentCorePaymentError) as exc_info:
        delete_recorded_session(
            manager,
            environ=environment(),
            session_file=session_file,
        )

    assert exc_info.value.code == "payment_session_delete_failed"
    assert "provider detail" not in str(exc_info.value)
    assert session_file.exists()


def test_unconfirmed_delete_retains_local_state(tmp_path: Path) -> None:
    session_file = tmp_path / "session.env"
    session_file.write_text(
        "PAYMENT_SESSION_CLIENT_TOKEN=stable-session-token\n"
        "PAYMENT_SESSION_ID=session-sensitive-test\n",
        encoding="utf-8",
    )
    manager = FakeSessionManager(delete_status="PENDING")

    with pytest.raises(AgentCorePaymentError) as exc_info:
        delete_recorded_session(
            manager,
            environ=environment(),
            session_file=session_file,
        )

    assert exc_info.value.code == "payment_session_delete_unconfirmed"
    assert session_file.exists()


def test_delete_rejects_shell_unsafe_local_state(tmp_path: Path) -> None:
    session_file = tmp_path / "session.env"
    session_file.write_text(
        "PAYMENT_SESSION_CLIENT_TOKEN=stable-session-token\n"
        "PAYMENT_SESSION_ID=$(unsafe-command)\n",
        encoding="utf-8",
    )
    manager = FakeSessionManager()

    with pytest.raises(AgentCorePaymentError) as exc_info:
        delete_recorded_session(
            manager,
            environ=environment(),
            session_file=session_file,
        )

    assert exc_info.value.code == "payment_session_state_invalid"
    assert manager.delete_calls == []


@pytest.mark.parametrize(
    ("budget", "expiry", "expected_code"),
    [
        (Decimal(0), 30, "payment_session_budget_invalid"),
        (Decimal("0.02"), 30, "payment_session_budget_invalid"),
        (Decimal("NaN"), 30, "payment_session_budget_invalid"),
        (Decimal("Infinity"), 30, "payment_session_budget_invalid"),
        (Decimal("0.01"), 14, "payment_session_expiry_invalid"),
        (Decimal("0.01"), 61, "payment_session_expiry_invalid"),
    ],
)
def test_create_rejects_unbounded_settings(
    tmp_path: Path,
    budget: Decimal,
    expiry: int,
    expected_code: str,
) -> None:
    manager = FakeSessionManager()

    with pytest.raises(AgentCorePaymentError) as exc_info:
        create_bounded_session(
            manager,
            environ=environment(),
            session_file=tmp_path / "session.env",
            budget_usd=budget,
            expiry_minutes=expiry,
        )

    assert exc_info.value.code == expected_code
    assert manager.create_calls == []
