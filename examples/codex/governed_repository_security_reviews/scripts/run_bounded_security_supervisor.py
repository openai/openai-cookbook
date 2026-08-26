#!/usr/bin/env python3
"""Bounded customer-owned synthetic reconciliation with no live product adapter.

The trusted host can request separately restricted Docker workers with
``--docker``. A hardened, daemon-free service container can instead execute the
offline synthetic adapter within its own independently verified outer isolation
boundary. These modes are deliberately different and are never substituted.
Real customer repository access, real product scans, provider writes, merge and
deployment remain unimplemented and require separate named-human authorisation.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import signal
import socket
import stat
import sys
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


sys.dont_write_bytecode = True
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from field_autonomy.sandbox import ContainerRuntime
from fleet_security.evidence import EvidenceError
from fleet_security.pipeline import PipelineError
from fleet_security.recipe import RecurringSecurityRecipe
from fleet_security.schema_validation import official_schema_directory


EVENT_TYPES = frozenset({"repository_changed", "approval_changed", "reconcile_requested"})
EVENT_KEYS = frozenset({"event_id", "repository_id", "revision", "event_type"})
EVENT_ID = re.compile(r"[A-Za-z0-9_.:-]{1,128}\Z")
MAX_EVENT_LINE_BYTES = 8192
FORBIDDEN_CREDENTIALS = (
    "OPENAI_API_KEY", "CODEX_API_KEY", "GH_TOKEN", "GITHUB_TOKEN",
    "AWS_SECRET_ACCESS_KEY", "OPENAI_WEBHOOK_SECRET",
)


class SupervisorSafetyError(RuntimeError):
    """A trusted input, queue bound, checkpoint or isolation guarantee failed."""


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _private_file(path: Path, *, label: str) -> Path:
    absolute = path.expanduser().absolute()
    if absolute.is_symlink() or not absolute.is_file():
        raise SupervisorSafetyError(f"{label} must be a real trusted regular file")
    if stat.S_IMODE(absolute.stat().st_mode) != 0o600:
        raise SupervisorSafetyError(f"{label} must have exact owner-private mode 0600")
    return absolute


def _external_state(path: Path) -> Path:
    absolute = path.expanduser().absolute()
    if absolute.is_relative_to(ROOT) or absolute.resolve().is_relative_to(ROOT.resolve()):
        raise SupervisorSafetyError("supervisor durable state must remain outside the repository checkout")
    if absolute.exists():
        if absolute.is_symlink() or not absolute.is_dir():
            raise SupervisorSafetyError("supervisor durable state must be a real owner-private directory")
        if stat.S_IMODE(absolute.stat().st_mode) != 0o700:
            raise SupervisorSafetyError("supervisor durable state must have exact owner-private mode 0700")
    return absolute


def _finite_int(value: str, *, minimum: int, maximum: int, name: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise argparse.ArgumentTypeError(f"{name} must be an integer") from error
    if not minimum <= parsed <= maximum:
        raise argparse.ArgumentTypeError(f"{name} must be between {minimum} and {maximum}")
    return parsed


def _bounded_interval(value: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as error:
        raise argparse.ArgumentTypeError("interval must be a finite number") from error
    if parsed != parsed or parsed in {float("inf"), float("-inf")} or not 0 <= parsed <= 60:
        raise argparse.ArgumentTypeError("interval must be between zero and 60 seconds")
    return parsed


def _network_denied() -> bool:
    try:
        with socket.create_connection(("203.0.113.1", 443), timeout=0.35):
            return False
    except OSError:
        return True


def _mount_options(path: Path) -> set[str]:
    destination = str(path.absolute())
    for line in Path("/proc/self/mountinfo").read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if len(fields) > 5 and fields[4] == destination:
            return set(fields[5].split(","))
    raise SupervisorSafetyError(f"expected dedicated container bind mount is absent: {destination}")


def _verify_outer_container(*, inputs: tuple[Path, ...], state: Path) -> dict[str, Any]:
    if not Path("/proc/self/status").is_file():
        raise SupervisorSafetyError("required restricted service-container boundary is unavailable")
    rows = dict(
        line.split(":", 1)
        for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines()
        if ":" in line
    )
    root_read_only = False
    try:
        Path("/governed-supervisor-read-only-proof").write_text("synthetic", encoding="utf-8")
    except OSError:
        root_read_only = True
    else:
        Path("/governed-supervisor-read-only-proof").unlink(missing_ok=True)

    approved_mounts = {
        name: _mount_options(ROOT / name)
        for name in ("src", "scripts", "fixtures", "contracts")
    }
    forbidden_source_entries = [
        path.relative_to(ROOT).as_posix()
        for directory in (ROOT / name for name in approved_mounts)
        for path in directory.rglob("*")
        if path.is_symlink()
        or path.name.startswith(".env")
        or path.name in {".git", ".ssh", ".aws", ".local-state-key", "credentials.json"}
    ]
    hidden_checkout_material = {
        ".git": (ROOT / ".git").exists(),
        "dotenv": any(ROOT.glob(".env*")),
    }
    input_parents = {path.parent for path in inputs}
    input_options = {str(parent): sorted(_mount_options(parent)) for parent in input_parents}
    state_options = _mount_options(state)
    receipt = {
        "uid": os.getuid(),
        "gid": os.getgid(),
        "network_blocked": _network_denied(),
        "root_read_only": root_read_only,
        "checkout_read_only": all("ro" in options for options in approved_mounts.values()),
        "approved_source_mounts": {name: sorted(options) for name, options in approved_mounts.items()},
        "hidden_checkout_material_present": hidden_checkout_material,
        "forbidden_source_entry_count": len(forbidden_source_entries),
        "input_mounts_read_only": all("ro" in options for options in input_options.values()),
        "state_mount_writable": "rw" in state_options,
        "effective_capabilities": rows.get("CapEff", "").strip(),
        "no_new_privileges": rows.get("NoNewPrivs", "").strip(),
        "docker_socket_present": Path("/var/run/docker.sock").exists(),
        "credentials_present": {name: name in os.environ for name in FORBIDDEN_CREDENTIALS},
    }
    try:
        capabilities = int(receipt["effective_capabilities"], 16)
    except ValueError as error:
        raise SupervisorSafetyError("restricted service effective capabilities are unrecognised") from error
    if (
        receipt["uid"] == 0
        or not receipt["network_blocked"]
        or not receipt["root_read_only"]
        or not receipt["checkout_read_only"]
        or any(receipt["hidden_checkout_material_present"].values())
        or receipt["forbidden_source_entry_count"]
        or not receipt["input_mounts_read_only"]
        or not receipt["state_mount_writable"]
        or capabilities != 0
        or receipt["no_new_privileges"] != "1"
        or receipt["docker_socket_present"]
        or any(receipt["credentials_present"].values())
    ):
        raise SupervisorSafetyError("restricted service-container isolation failed; downgrade is prohibited")
    return receipt


@dataclass
class QueueBatch:
    offset: int
    lines_consumed: int
    unique: int
    duplicates: int
    rejected: int
    backpressure: int
    max_pending: int


def _read_cursor(recipe: RecurringSecurityRecipe, events: Path) -> int:
    path = recipe.store.root / "supervisor-cursor.json"
    if not path.exists():
        return 0
    _private_file(path, label="signed supervisor event cursor")
    try:
        envelope = json.loads(path.read_text(encoding="utf-8"))
        payload = envelope["payload"]
        signature = envelope["signature"]
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise SupervisorSafetyError("signed supervisor event cursor is malformed") from error
    if not isinstance(payload, dict) or not isinstance(signature, str):
        raise SupervisorSafetyError("signed supervisor event cursor is malformed")
    key = _private_file(recipe.store.root / ".local-state-key", label="supervisor signing key").read_bytes()
    expected = hmac.new(key, _canonical(payload), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise SupervisorSafetyError("signed supervisor event cursor failed integrity verification")
    offset = payload.get("offset")
    if (
        payload.get("format") != "governed-supervisor-cursor/v1"
        or payload.get("event_file_name") != events.name
        or isinstance(offset, bool)
        or not isinstance(offset, int)
        or offset < 0
    ):
        raise SupervisorSafetyError("signed supervisor event cursor does not match its trusted event stream")
    with events.open("rb") as source:
        prefix = source.read(offset)
    if len(prefix) != offset or hashlib.sha256(prefix).hexdigest() != payload.get("prefix_sha256"):
        raise SupervisorSafetyError("trusted event stream changed before its authenticated cursor")
    return offset


def _write_cursor(recipe: RecurringSecurityRecipe, events: Path, offset: int) -> None:
    with events.open("rb") as source:
        prefix = source.read(offset)
    if len(prefix) != offset:
        raise SupervisorSafetyError("trusted event stream changed during bounded reconciliation")
    payload = {
        "format": "governed-supervisor-cursor/v1",
        "event_file_name": events.name,
        "offset": offset,
        "prefix_sha256": hashlib.sha256(prefix).hexdigest(),
    }
    key = _private_file(recipe.store.root / ".local-state-key", label="supervisor signing key").read_bytes()
    signature = hmac.new(key, _canonical(payload), hashlib.sha256).hexdigest()
    recipe.store.write_json(recipe.store.root / "supervisor-cursor.json", {"payload": payload, "signature": signature})


def _read_events(
    *, recipe: RecurringSecurityRecipe, events: Path, max_per_cycle: int,
    max_pending: int, max_file_bytes: int,
) -> QueueBatch:
    _private_file(events, label="trusted local event stream")
    if events.stat().st_size > max_file_bytes:
        raise SupervisorSafetyError("trusted event stream exceeds its explicit bounded byte budget")
    records = {record.repo_id: record for record in recipe.inventory}
    offset = _read_cursor(recipe, events)
    pending: OrderedDict[tuple[str, str], str] = OrderedDict()
    lines = duplicates = rejected = pressure = peak = 0
    with events.open("rb") as source:
        source.seek(offset)
        while lines < max_per_cycle:
            before = source.tell()
            line = source.readline(MAX_EVENT_LINE_BYTES + 1)
            if not line:
                break
            if len(line) > MAX_EVENT_LINE_BYTES and not line.endswith(b"\n"):
                raise SupervisorSafetyError("trusted event line exceeds its bounded inspection budget")
            try:
                entry = json.loads(line.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError):
                rejected += 1
                lines += 1
                offset = source.tell()
                continue
            valid = isinstance(entry, dict) and set(entry) == EVENT_KEYS
            if valid:
                identifier = entry.get("event_id")
                repo_id = entry.get("repository_id")
                revision = entry.get("revision")
                valid = (
                    isinstance(identifier, str)
                    and EVENT_ID.fullmatch(identifier) is not None
                    and isinstance(repo_id, str)
                    and repo_id.startswith("synthetic/")
                    and repo_id in records
                    and revision == records[repo_id].commit_sha
                    and entry.get("event_type") in EVENT_TYPES
                )
            if not valid:
                rejected += 1
                lines += 1
                offset = source.tell()
                continue
            key = (entry["repository_id"], entry["revision"])
            if key in pending:
                duplicates += 1
                lines += 1
                offset = source.tell()
                continue
            if len(pending) >= max_pending:
                pressure += 1
                source.seek(before)
                break
            pending[key] = entry["event_id"]
            peak = max(peak, len(pending))
            lines += 1
            offset = source.tell()
        if lines >= max_per_cycle and source.read(1):
            pressure += 1
    return QueueBatch(offset, lines, len(pending), duplicates, rejected, pressure, peak)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--approvals", required=True, type=Path)
    parser.add_argument("--state-dir", required=True, type=Path)
    parser.add_argument("--events", type=Path)
    parser.add_argument("--max-cycles", default=2, type=lambda value: _finite_int(value, minimum=1, maximum=1000, name="max cycles"))
    parser.add_argument("--interval-seconds", default=0.0, type=_bounded_interval)
    parser.add_argument("--max-events-per-cycle", default=128, type=lambda value: _finite_int(value, minimum=1, maximum=10000, name="events per cycle"))
    parser.add_argument("--max-pending-events", default=32, type=lambda value: _finite_int(value, minimum=1, maximum=10000, name="pending events"))
    parser.add_argument("--max-event-file-bytes", default=1048576, type=lambda value: _finite_int(value, minimum=1, maximum=10485760, name="event file bytes"))
    parser.add_argument("--docker", action="store_true", help="Use separately restricted Docker workers from the trusted host only.")
    parser.add_argument("--runtime-label", choices=("trusted_host", "restricted_service_container"), default="trusted_host")
    parser.add_argument("--require-container-isolation", action="store_true", help="Require observed daemon-free, network-denied service-container isolation.")
    return parser


def run(options: argparse.Namespace) -> dict[str, Any]:
    configuration = _private_file(options.config, label="trusted supervisor configuration")
    inventory = _private_file(options.inventory, label="trusted supervisor inventory")
    approvals = _private_file(options.approvals, label="trusted named-human supervisor approvals")
    events = _private_file(options.events, label="trusted local event stream") if options.events else None
    state = _external_state(options.state_dir)

    bundled = ROOT / "contracts" / "codex-security-schemas"
    schemas = official_schema_directory(plugin_cache=Path("/nonexistent-private-plugin"), bundled_root=bundled)
    os.environ["CODEX_SECURITY_SCHEMA_ROOT"] = str(schemas)

    if options.require_container_isolation and options.runtime_label != "restricted_service_container":
        raise SupervisorSafetyError("container isolation verification requires the explicit restricted service runtime")
    if options.runtime_label == "restricted_service_container" and not options.require_container_isolation:
        raise SupervisorSafetyError("restricted service runtime must verify its actual outer isolation boundary")
    if options.docker and options.runtime_label == "restricted_service_container":
        raise SupervisorSafetyError("Docker-in-Docker and service-container daemon sockets are prohibited")

    container_receipt: dict[str, Any] | None = None
    if options.require_container_isolation:
        selected_inputs = (configuration, inventory, approvals) + ((events,) if events else ())
        container_receipt = _verify_outer_container(inputs=selected_inputs, state=state)
        boundary = "outer_service_container_isolated"
    elif options.docker:
        ContainerRuntime()._validate_daemon_and_image()
        boundary = "trusted_host_with_restricted_workers"
    else:
        boundary = "trusted_host_offline_not_sandboxed"

    stop = threading.Event()
    reason = {"value": "max_cycles_reached"}
    original_handlers: dict[int, Any] = {}

    def request_stop(signum: int, _frame: Any) -> None:
        reason["value"] = f"signal:{signal.Signals(signum).name}"
        stop.set()

    for name in ("SIGTERM", "SIGINT"):
        selected = getattr(signal, name, None)
        if selected is not None:
            original_handlers[selected] = signal.getsignal(selected)
            signal.signal(selected, request_stop)

    started = time.monotonic()
    cycles: list[dict[str, Any]] = []
    lines = unique = duplicates = rejected = pressure = peak = 0
    try:
        while len(cycles) < options.max_cycles and not stop.is_set():
            cycle_started = time.monotonic()
            _private_file(configuration, label="trusted supervisor configuration")
            _private_file(inventory, label="trusted supervisor inventory")
            _private_file(approvals, label="trusted named-human supervisor approvals")
            recipe = RecurringSecurityRecipe.from_files(
                configuration_path=configuration,
                inventory_path=inventory,
                approvals_path=approvals,
                state_directory=state,
                docker=options.docker,
            )
            batch = (
                _read_events(
                    recipe=recipe,
                    events=events,
                    max_per_cycle=options.max_events_per_cycle,
                    max_pending=options.max_pending_events,
                    max_file_bytes=options.max_event_file_bytes,
                )
                if events is not None else QueueBatch(0, 0, 0, 0, 0, 0, 0)
            )
            receipt = recipe.cycle()
            if options.docker:
                successful_scans = sum(
                    row.get("attempts", 0) > 0 and row.get("status") != "failed_safe_abstention"
                    for row in receipt["records"].values()
                )
                if receipt["scanner_invocations"] and successful_scans and receipt["restricted_docker_receipts"] == 0:
                    raise SupervisorSafetyError("trusted host requested isolated workers but received no genuine restricted Docker evidence")
            if events is not None:
                _write_cursor(recipe, events, batch.offset)
            cycle = {
                "supervisor_cycle": len(cycles) + 1,
                "recipe_run_number": receipt["run_number"],
                "configuration_reread": True,
                "inventory_reread": True,
                "approvals_reread": True,
                "scanner_invocations": receipt["scanner_invocations"],
                "admitted_jobs": receipt["admitted_jobs"],
                "attempted_repositories": receipt["attempted_repositories"],
                "scanner_attempts_by_repository": receipt["scanner_attempts_by_repository"],
                "retry_attempts": receipt["retry_attempts"],
                "transient_retry_events": receipt["transient_retry_events"],
                "restricted_docker_receipts": receipt["restricted_docker_receipts"],
                "recipe_execution_mode": receipt["execution_mode"],
                "decision_states": receipt["decision_states"],
                "audit_valid": receipt["audit_valid"],
                "durable_audit_valid": receipt.get("durable_audit_valid"),
                "durable_audit_event_count": receipt.get("durable_audit_event_count"),
                "durable_audit_cumulative_event_count": receipt.get("durable_audit_cumulative_event_count"),
                "durable_audit_tail_digest": receipt.get("durable_audit_tail_digest"),
                "queue_event_lines_consumed": batch.lines_consumed,
                "queue_unique_events": batch.unique,
                "queue_duplicates_coalesced": batch.duplicates,
                "queue_rejected_events": batch.rejected,
                "queue_backpressure_events": batch.backpressure,
                "elapsed_ms": round((time.monotonic() - cycle_started) * 1000, 3),
                "paid_api_calls": 0,
                "external_writes": 0,
                "live_product_execution": False,
            }
            recipe.store.write_json(
                recipe.store.root / "supervisor-runs" /
                f"supervisor-{receipt['run_number']:06d}-{time.time_ns()}.json",
                cycle,
            )
            cycles.append(cycle)
            lines += batch.lines_consumed
            unique += batch.unique
            duplicates += batch.duplicates
            rejected += batch.rejected
            pressure += batch.backpressure
            peak = max(peak, batch.max_pending)
            if len(cycles) < options.max_cycles and options.interval_seconds:
                stop.wait(options.interval_seconds)
    finally:
        for signum, previous in original_handlers.items():
            signal.signal(signum, previous)

    return {
        "supervisor": "bounded-owner-governed-synthetic-security-reconciliation",
        "runtime_label": options.runtime_label,
        "execution_boundary": boundary,
        "outer_service_container_isolation": container_receipt,
        "state_directory": str(state),
        "owner_private_state_mode": "0700",
        "pinned_public_schema_root": str(schemas),
        "max_cycles": options.max_cycles,
        "cycles_completed": len(cycles),
        "interval_seconds": options.interval_seconds,
        "max_events_per_cycle": options.max_events_per_cycle,
        "max_pending_events": options.max_pending_events,
        "event_lines_consumed": lines,
        "events_processed": unique,
        "duplicate_events_coalesced": duplicates,
        "rejected_events": rejected,
        "backpressure_events": pressure,
        "max_pending_observed": peak,
        "scanner_invocations_per_cycle": [row["scanner_invocations"] for row in cycles],
        "attempted_repositories_per_cycle": [row["attempted_repositories"] for row in cycles],
        "retry_attempts_per_cycle": [row["retry_attempts"] for row in cycles],
        "restricted_docker_receipts_per_cycle": [row["restricted_docker_receipts"] for row in cycles],
        "scan_attempts_total": sum(row["scanner_invocations"] for row in cycles),
        "isolated_worker_receipts_total": sum(row["restricted_docker_receipts"] for row in cycles),
        "durable_audit_all_cycles_valid": bool(cycles) and all(
            row["durable_audit_valid"] is True for row in cycles
        ),
        "cycle_metrics": cycles,
        "graceful_shutdown": True,
        "shutdown_reason": reason["value"],
        "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
        "real_customer_repository_access": 0,
        "hosted_model_calls": 0,
        "paid_api_calls": 0,
        "live_product_execution": False,
        "external_writes": 0,
        "automatic_pr_merge_or_deploy": False,
    }


def main(argv: list[str] | None = None) -> int:
    options = build_parser().parse_args(argv)
    try:
        receipt = run(options)
    except (EvidenceError, PipelineError, SupervisorSafetyError, OSError) as error:
        print(json.dumps({
            "supervisor": "bounded-owner-governed-synthetic-security-reconciliation",
            "status": "failed_closed",
            "error_type": type(error).__name__,
            "error": str(error),
            "paid_api_calls": 0,
            "external_writes": 0,
        }, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
