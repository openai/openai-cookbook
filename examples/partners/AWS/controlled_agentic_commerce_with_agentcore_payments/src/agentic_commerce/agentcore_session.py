"""Fail-closed lifecycle helper for one bounded AgentCore payment session."""

from __future__ import annotations

import argparse
import json
import os
import re
import threading
import uuid
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Protocol

try:
    import fcntl
except ImportError:
    fcntl = None

from .agentcore_payments import (
    _SUPPORTED_AGENTCORE_PAYMENT_REGIONS,
    _disable_agentcore_sdk_logging,
    _resolve_agentcore_region,
)
from .errors import AgentCorePaymentError

_SESSION_ADMIN_OPT_IN = "ALLOW_AGENTCORE_SESSION_ADMIN"
_SESSION_FILE_ENV = "AGENTCORE_SESSION_FILE"
_DEFAULT_SESSION_FILE = Path(".agentcore-session.env")
_MAX_SESSION_BUDGET_USD = Decimal("0.01")
_MIN_SESSION_MINUTES = 15
_MAX_SESSION_MINUTES = 60
_SESSION_STATE_KEYS = {
    "PAYMENT_SESSION_CLIENT_TOKEN",
    "PAYMENT_SESSION_ID",
}
_SESSION_STATE_VALUE = re.compile(r"[A-Za-z0-9._:@/+,=-]+")
_PROCESS_SESSION_LOCK = threading.Lock()


class PaymentSessionManager(Protocol):
    """Narrow AgentCore PaymentManager session interface."""

    def create_payment_session(
        self,
        *,
        expiry_time_in_minutes: int,
        user_id: str | None = None,
        limits: dict[str, Any] | None = None,
        client_token: str | None = None,
    ) -> dict[str, Any]: ...

    def delete_payment_session(
        self,
        payment_session_id: str,
        user_id: str | None = None,
    ) -> dict[str, Any]: ...


TokenFactory = Callable[[], str]


def parse_budget(raw: str) -> Decimal:
    """Parse a positive USD session ceiling no greater than one cent."""

    try:
        value = Decimal(raw)
    except (InvalidOperation, ValueError) as exc:
        raise argparse.ArgumentTypeError("budget must be a decimal amount") from exc
    if not value.is_finite() or value <= 0 or value > _MAX_SESSION_BUDGET_USD:
        raise argparse.ArgumentTypeError(
            "budget must be greater than 0 and no greater than 0.01 USD"
        )
    return value


def _session_file(
    environ: Mapping[str, str],
    override: Path | None,
) -> Path:
    if override is not None:
        return override
    configured = environ.get(_SESSION_FILE_ENV, "").strip()
    return Path(configured) if configured else _DEFAULT_SESSION_FILE


def _read_session_state(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    state: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        name, separator, value = line.partition("=")
        if (
            not separator
            or name not in _SESSION_STATE_KEYS
            or name in state
            or not _SESSION_STATE_VALUE.fullmatch(value)
        ):
            raise AgentCorePaymentError(
                "payment_session_state_invalid",
                "The local payment-session state file is invalid.",
            )
        state[name] = value
    return state


def _write_session_state(path: Path, state: Mapping[str, str]) -> None:
    lines = []
    for name, value in state.items():
        if name not in _SESSION_STATE_KEYS or not _SESSION_STATE_VALUE.fullmatch(value):
            raise AgentCorePaymentError(
                "payment_session_state_invalid",
                "The payment-session state contains an invalid value.",
            )
        lines.append(f"{name}={value}\n")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor: int | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(path, flags, 0o600)
        handle = os.fdopen(descriptor, "w", encoding="utf-8")
        descriptor = None
        with handle:
            os.fchmod(handle.fileno(), 0o600)
            handle.writelines(lines)
    except OSError:
        if descriptor is not None:
            os.close(descriptor)
        raise AgentCorePaymentError(
            "payment_session_state_write_failed",
            "The local payment-session state file could not be written.",
        ) from None


@contextmanager
def _session_lock(path: Path) -> Iterator[None]:
    """Serialize session lifecycle changes across threads and processes."""

    if fcntl is None:
        raise AgentCorePaymentError(
            "payment_session_platform_unsupported",
            "Live payment-session administration requires POSIX file locking. "
            "The offline notebook path remains available on this platform.",
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = Path(f"{path}.lock")
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(lock_path, flags, 0o600)
        os.fchmod(descriptor, 0o600)
    except OSError:
        raise AgentCorePaymentError(
            "payment_session_lock_failed",
            "The local payment-session lock could not be acquired.",
        ) from None

    with (
        os.fdopen(descriptor, "a+", encoding="utf-8") as handle,
        _PROCESS_SESSION_LOCK,
    ):
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        except OSError:
            raise AgentCorePaymentError(
                "payment_session_lock_failed",
                "The local payment-session lock could not be acquired.",
            ) from None
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _delete_unpersisted_session(
    manager: PaymentSessionManager,
    *,
    session_id: str,
    user_id: str,
    path: Path,
    client_token: str,
) -> None:
    """Delete a session if its identifier cannot be persisted safely."""

    try:
        deletion = manager.delete_payment_session(
            payment_session_id=session_id,
            user_id=user_id,
        )
    except Exception:  # noqa: BLE001
        deletion = {}
    if str(deletion.get("status", "")).upper() == "DELETED":
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        return

    recovery_recorded = False
    try:
        _write_session_state(
            path,
            {
                "PAYMENT_SESSION_CLIENT_TOKEN": client_token,
                "PAYMENT_SESSION_ID": session_id,
            },
        )
        recovery_recorded = True
    except AgentCorePaymentError:
        pass
    raise AgentCorePaymentError(
        "payment_session_persistence_cleanup_failed",
        "AgentCore created a payment session, but local persistence and "
        "automatic deletion did not both complete. Do not create another "
        "session until an administrator verifies cleanup.",
        diagnostics={"local_recovery_recorded": recovery_recorded},
    )


def _require_session_admin(environ: Mapping[str, str]) -> None:
    if environ.get(_SESSION_ADMIN_OPT_IN) != "1":
        raise AgentCorePaymentError(
            "payment_session_admin_disabled",
            f"Set {_SESSION_ADMIN_OPT_IN}=1 only for an approved "
            "testnet session create or delete operation.",
        )


def _required_runtime(
    environ: Mapping[str, str],
) -> tuple[str, str, str]:
    manager_arn = environ.get("PAYMENT_MANAGER_ARN", "").strip()
    user_id = environ.get("PAYMENT_USER_ID", "").strip()
    region = _resolve_agentcore_region(environ)
    missing = []
    if not manager_arn:
        missing.append("PAYMENT_MANAGER_ARN")
    if not user_id:
        missing.append("PAYMENT_USER_ID")
    if not region:
        missing.append("AGENTCORE_AWS_REGION")
    if missing:
        raise AgentCorePaymentError(
            "payment_session_configuration_missing",
            "Payment-session configuration is incomplete: " + ", ".join(missing),
        )
    if region not in _SUPPORTED_AGENTCORE_PAYMENT_REGIONS:
        raise AgentCorePaymentError(
            "agentcore_region_unsupported",
            "AgentCore Payments is unavailable in the configured Region.",
        )
    return manager_arn, user_id, region


def create_bounded_session(
    manager: PaymentSessionManager,
    *,
    environ: Mapping[str, str],
    session_file: Path | None = None,
    budget_usd: Decimal = _MAX_SESSION_BUDGET_USD,
    expiry_minutes: int = 30,
    token_factory: TokenFactory = lambda: str(uuid.uuid4()),
) -> dict[str, object]:
    """Create one short-lived session and keep identifiers in a local file."""

    _require_session_admin(environ)
    _, user_id, region = _required_runtime(environ)
    if (
        not budget_usd.is_finite()
        or budget_usd <= 0
        or budget_usd > _MAX_SESSION_BUDGET_USD
    ):
        raise AgentCorePaymentError(
            "payment_session_budget_invalid",
            "The session budget must be greater than 0 and no greater than 0.01 USD.",
        )
    if not _MIN_SESSION_MINUTES <= expiry_minutes <= _MAX_SESSION_MINUTES:
        raise AgentCorePaymentError(
            "payment_session_expiry_invalid",
            "The session expiry must be between 15 and 60 minutes.",
        )

    path = _session_file(environ, session_file)
    with _session_lock(path):
        state = _read_session_state(path)
        if state.get("PAYMENT_SESSION_ID"):
            raise AgentCorePaymentError(
                "payment_session_already_recorded",
                "Delete the recorded payment session before creating another.",
            )
        client_token = state.get("PAYMENT_SESSION_CLIENT_TOKEN") or token_factory()
        if len(client_token) < 8:
            raise AgentCorePaymentError(
                "payment_session_client_token_invalid",
                "The payment-session client token must contain at least eight characters.",
            )
        _write_session_state(
            path,
            {"PAYMENT_SESSION_CLIENT_TOKEN": client_token},
        )

        try:
            session = manager.create_payment_session(
                user_id=user_id,
                limits={
                    "maxSpendAmount": {
                        "value": format(budget_usd, "f"),
                        "currency": "USD",
                    }
                },
                expiry_time_in_minutes=expiry_minutes,
                client_token=client_token,
            )
        except Exception:  # noqa: BLE001
            raise AgentCorePaymentError(
                "payment_session_create_failed",
                "AgentCore did not create the bounded payment session. The "
                "local client token was retained for a safe retry.",
            ) from None

        session_id = str(session.get("paymentSessionId", "")).strip()
        if not session_id:
            raise AgentCorePaymentError(
                "payment_session_response_invalid",
                "AgentCore returned no payment session identifier.",
            )
        try:
            _write_session_state(
                path,
                {
                    "PAYMENT_SESSION_CLIENT_TOKEN": client_token,
                    "PAYMENT_SESSION_ID": session_id,
                },
            )
        except AgentCorePaymentError:
            _delete_unpersisted_session(
                manager,
                session_id=session_id,
                user_id=user_id,
                path=path,
                client_token=client_token,
            )
            raise
        return {
            "result": "CREATED",
            "budget_usd": format(budget_usd, "f"),
            "expiry_minutes": expiry_minutes,
            "agentcore_region": region,
            "session_file": str(path),
            "session_id_logged": False,
            "client_token_logged": False,
            "value_transferred": False,
        }


def delete_recorded_session(
    manager: PaymentSessionManager,
    *,
    environ: Mapping[str, str],
    session_file: Path | None = None,
) -> dict[str, object]:
    """Delete the recorded session and remove its local identifier file."""

    _require_session_admin(environ)
    _, user_id, region = _required_runtime(environ)
    path = _session_file(environ, session_file)
    with _session_lock(path):
        state = _read_session_state(path)
        session_id = state.get("PAYMENT_SESSION_ID", "").strip()
        if not session_id:
            raise AgentCorePaymentError(
                "payment_session_not_recorded",
                "No payment session is recorded in the local state file.",
            )
        try:
            deletion = manager.delete_payment_session(
                payment_session_id=session_id,
                user_id=user_id,
            )
        except Exception:  # noqa: BLE001
            raise AgentCorePaymentError(
                "payment_session_delete_failed",
                "AgentCore did not delete the recorded payment session. The "
                "local state file was retained.",
            ) from None
        if str(deletion.get("status", "")).upper() != "DELETED":
            raise AgentCorePaymentError(
                "payment_session_delete_unconfirmed",
                "AgentCore did not confirm payment-session deletion. The "
                "local state file was retained.",
            )
        path.unlink()
    return {
        "result": "DELETED",
        "agentcore_region": region,
        "session_file_removed": True,
        "session_id_logged": False,
        "client_token_logged": False,
        "value_transferred": False,
    }


def runtime_environment_from_recorded_session(
    environ: Mapping[str, str],
    *,
    session_file: Path | None = None,
) -> dict[str, str]:
    """Return a private runtime copy containing the recorded session ID."""

    path = _session_file(environ, session_file)
    with _session_lock(path):
        state = _read_session_state(path)
        session_id = state.get("PAYMENT_SESSION_ID", "").strip()
        if not session_id:
            raise AgentCorePaymentError(
                "payment_session_not_recorded",
                "No payment session is recorded in the local state file.",
            )
    runtime_environment = dict(environ)
    runtime_environment["PAYMENT_SESSION_ID"] = session_id
    return runtime_environment


def _manager(environ: Mapping[str, str]) -> PaymentSessionManager:
    from bedrock_agentcore.payments import PaymentManager

    manager_arn, _, region = _required_runtime(environ)
    _disable_agentcore_sdk_logging()
    boto3_session = None
    profile = environ.get("AGENTCORE_SESSION_AWS_PROFILE", "").strip()
    if profile:
        import boto3

        boto3_session = boto3.Session(
            profile_name=profile,
            region_name=region,
        )
    return PaymentManager(
        payment_manager_arn=manager_arn,
        region_name=region,
        boto3_session=boto3_session,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create or delete one bounded AgentCore testnet session."
    )
    parser.add_argument(
        "--session-file",
        type=Path,
        help="Local state file for the session ID and client token.",
    )
    subparsers = parser.add_subparsers(dest="operation", required=True)
    create = subparsers.add_parser("create")
    create.add_argument("--budget", type=parse_budget, default=Decimal("0.01"))
    create.add_argument("--expiry-minutes", type=int, default=30)
    subparsers.add_parser("delete")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    try:
        _require_session_admin(os.environ)
        manager = _manager(os.environ)
        if args.operation == "create":
            report = create_bounded_session(
                manager,
                environ=os.environ,
                session_file=args.session_file,
                budget_usd=args.budget,
                expiry_minutes=args.expiry_minutes,
            )
        else:
            report = delete_recorded_session(
                manager,
                environ=os.environ,
                session_file=args.session_file,
            )
    except AgentCorePaymentError as exc:
        print(
            json.dumps(
                {"result": "FAILED", "code": exc.code, "message": str(exc)},
                indent=2,
                sort_keys=True,
            )
        )
        raise SystemExit(1) from None
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
