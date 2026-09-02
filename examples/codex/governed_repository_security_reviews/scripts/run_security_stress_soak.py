#!/usr/bin/env python3
"""Bounded, genuinely isolated synthetic stress/soak; never a customer scan.

Exactly 2,000 generated records are classified as metadata only. A much smaller,
explicitly enumerated set of bundled fictional repositories is actually examined
by already-cached, network-denied, non-root, read-only Docker workers.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import math
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from collections import Counter
from dataclasses import replace
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Iterator
from unittest import mock


sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from field_autonomy.sandbox import ContainerExecutor, ContainerRuntime, scrubbed_environment
from fleet_security.evidence import AuditLog, EvidenceError
from fleet_security.inventory import Repository, classify, generate_inventory
from fleet_security.pipeline import ApprovalLedger, FleetPipeline, FleetPolicy, PipelineError
from fleet_security.recipe import RecipeConfiguration, RecurringSecurityRecipe, load_recipe_inventory
from fleet_security.reproduction import (
    DEMO_ATTEMPTED_REPOSITORIES, DEMO_EXPECTED_STATUSES,
    ReproductionFailure, assert_attempt_accounting, assert_cycle_accounting,
)
from fleet_security.scanner import (
    RETRY_REASON_CODES, ScanFailure, SyntheticScanner,
    parse_restricted_content_refusal, restricted_isolation_verified,
)
from fleet_security.threats import ThreatCatalogue, compare_strategies


EXAMPLES = ROOT / "cookbook" / "security-review-pipeline"
EXPECTED_DECISIONS = {
    "awaiting_finding_disposition": 2,
    "awaiting_scope_approval": 1,
    "awaiting_threat_model_approval": 1,
    "failed_safe_abstention": 1,
    "review_packet_ready": 1,
}


class StressFailure(RuntimeError):
    """An expected owner-governed stress invariant failed closed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise StressFailure(message)


def _private_directory(path: Path) -> Path:
    absolute = path.expanduser().absolute()
    require(
        not absolute.is_relative_to(ROOT)
        and not absolute.resolve().is_relative_to(ROOT.resolve()),
        "owner-private stress state cannot live in or resolve into the checkout",
    )
    if not absolute.exists():
        absolute.mkdir(mode=0o700, parents=True)
        absolute.chmod(0o700)
    require(not absolute.is_symlink() and absolute.is_dir(), "stress state must be a real directory")
    metadata = absolute.stat()
    require(metadata.st_uid == os.geteuid(), "stress state must be owned by the current user")
    require(stat.S_IMODE(metadata.st_mode) == 0o700, "stress state must have mode 0700")
    return absolute


def _private_write(path: Path, payload: str | bytes) -> None:
    encoded = payload.encode("utf-8") if isinstance(payload, str) else payload
    _private_directory(path.parent)
    descriptor = os.open(
        path,
        os.O_CREAT | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        metadata = os.fstat(descriptor)
        require(stat.S_ISREG(metadata.st_mode), "private stress output must be a regular file")
        require(metadata.st_uid == os.geteuid(), "private stress output must be owner-owned")
        require(metadata.st_nlink == 1, "private stress output must not have hard links")
        require(stat.S_IMODE(metadata.st_mode) == 0o600, "private stress output must have mode 0600")
        os.ftruncate(descriptor, 0)
        with os.fdopen(descriptor, "wb") as destination:
            descriptor = -1
            destination.write(encoded)
    finally:
        if descriptor != -1:
            os.close(descriptor)


def _save_json(path: Path, document: object) -> None:
    _private_write(path, json.dumps(document, sort_keys=True, indent=2) + "\n")


def _read_json(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(document, dict), "trusted synthetic input must be a JSON object")
    return document


@contextlib.contextmanager
def _temporarily_edit(path: Path, mutate: Callable[[dict[str, Any]], None]) -> Iterator[None]:
    original = path.read_bytes()
    document = _read_json(path)
    mutate(document)
    _save_json(path, document)
    try:
        yield
    finally:
        _private_write(path, original)


def _docker_prerequisites() -> dict[str, str]:
    require(shutil.which("docker") is not None, "Docker is unavailable; unrestricted fallback is prohibited")
    commands = (
        (["docker", "info", "--format", "{{.ServerVersion}}"], "daemon_version"),
        (["docker", "image", "inspect", "python:3.12-alpine", "--format", "{{.Id}}"], "cached_image_id"),
    )
    result: dict[str, str] = {}
    for command, key in commands:
        try:
            completed = subprocess.run(
                command, capture_output=True, text=True, timeout=10,
                check=False, shell=False, env=scrubbed_environment(),
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise StressFailure("restricted Docker could not be checked; image pulls are prohibited") from error
        require(completed.returncode == 0 and bool(completed.stdout.strip()),
                "Docker daemon or already-cached approved image is unavailable; fail closed")
        result[key] = completed.stdout.strip()
    return result


class RuntimeInstrumentation:
    """Separate executor calls, evidenced worker starts and unresolved attempts."""

    def __init__(self) -> None:
        self.containers: list[dict[str, Any]] = []
        self.scans: list[dict[str, Any]] = []
        self._local = threading.local()
        self._lock = threading.Lock()
        self._active_containers = 0
        self._active_scanners = 0
        self._start_observations: dict[str, str] = {}
        self.peak_containers = 0
        self.peak_scanners = 0

    @staticmethod
    def launch_metrics(receipts: list[dict[str, Any]]) -> dict[str, int]:
        return {
            "executor_run_invocations": len(receipts),
            "actual_container_starts": sum(row["container_started"] for row in receipts),
            "rejected_container_launches": sum(row["status"] == "launch_rejected" for row in receipts),
            "unresolved_container_starts": sum(
                not row["container_started"] and row["status"] != "launch_rejected"
                for row in receipts
            ),
        }

    @staticmethod
    def _verify_isolation(payload: dict[str, Any]) -> None:
        require(restricted_isolation_verified(payload),
                "restricted worker omitted or violated mandatory isolation evidence")

    @contextlib.contextmanager
    def install(self) -> Iterator["RuntimeInstrumentation"]:
        original_run = ContainerExecutor.run
        original_remove = ContainerExecutor._remove
        original_scan = SyntheticScanner.scan

        @wraps(original_remove)
        def observed_remove(executor: ContainerExecutor, name: str) -> None:
            # A CLI timeout alone does not prove a worker started. Observe only
            # this executor's own container before mandatory forced cleanup.
            try:
                inspected = executor._inspect(name)
                if inspected.returncode == 0 and inspected.stdout.strip() in {
                    "running", "paused", "restarting",
                }:
                    with self._lock:
                        self._start_observations[name] = "daemon_running_before_forced_cleanup"
            except (OSError, subprocess.TimeoutExpired):
                pass
            finally:
                # Observation must never prevent the existing cleanup or its
                # independent absence check from running and failing closed.
                original_remove(executor, name)

        @wraps(original_run)
        def observed_run(executor: ContainerExecutor, arguments: list[str], *, timeout: float) -> Any:
            started = time.monotonic()
            repository = getattr(self._local, "repository", "explicit-timeout-probe")
            fixture = getattr(self._local, "fixture", "safe_service")
            with self._lock:
                self._active_containers += 1
                self.peak_containers = max(self.peak_containers, self._active_containers)
            status = "unknown"
            returncode: int | None = None
            isolation_verified = False
            start_evidence: str | None = None
            refusal_reason: str | None = None
            try:
                completed = original_run(executor, arguments, timeout=timeout)
                returncode = completed.returncode
                status = "unresolved_worker_failure"
                if completed.returncode == 0:
                    start_evidence = "successful_worker_exit"
                    status = "completed_unverified_receipt"
                    try:
                        payload = json.loads(completed.stdout)
                    except (TypeError, json.JSONDecodeError):
                        payload = None
                    if isinstance(payload, dict):
                        self._verify_isolation(payload)
                        isolation_verified = True
                        start_evidence = "validated_isolation_receipt"
                        status = "completed"
                else:
                    refusal_reason = parse_restricted_content_refusal(
                        completed.returncode, completed.stdout,
                    )
                    if refusal_reason is not None:
                        start_evidence = (
                            "trusted_instruction_refusal_protocol"
                            if refusal_reason == "repository_instruction"
                            else "trusted_content_refusal_protocol"
                        )
                        status = "hostile_or_failed_exit"
                    elif completed.returncode == 125:
                        status = "launch_rejected"
                return completed
            except subprocess.TimeoutExpired:
                status = "timeout_forced_cleanup"
                raise
            except BaseException:
                status = "launch_or_policy_failure"
                raise
            finally:
                name = executor.container_names[-1] if executor.container_names else None
                if start_evidence is None and name is not None:
                    with self._lock:
                        start_evidence = self._start_observations.get(name)
                if status == "timeout_forced_cleanup" and start_evidence is None:
                    status = "timeout_unresolved_start_cleanup_verified"
                receipt = {
                    "repository_id": repository,
                    "fixture": fixture,
                    "container_name": name,
                    "status": status,
                    "container_started": start_evidence is not None,
                    "start_evidence": start_evidence,
                    "refusal_reason_code": refusal_reason,
                    "returncode": returncode,
                    "timeout_seconds": timeout,
                    "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
                    "isolation_verified": isolation_verified,
                }
                with self._lock:
                    self.containers.append(receipt)
                    self._active_containers -= 1

        @wraps(original_scan)
        def observed_scan(scanner: SyntheticScanner, repository: Repository, assignment: Any) -> Any:
            previous_repository = getattr(self._local, "repository", None)
            previous_fixture = getattr(self._local, "fixture", None)
            self._local.repository = repository.repo_id
            self._local.fixture = repository.fixture
            started = time.monotonic()
            status = "unknown"
            failure_reason_code: str | None = None
            with self._lock:
                self._active_scanners += 1
                self.peak_scanners = max(self.peak_scanners, self._active_scanners)
            try:
                result = original_scan(scanner, repository, assignment)
                status = "completed"
                return result
            except ScanFailure as error:
                status = "retryable_failure" if error.retryable else "safe_failure"
                if error.reason_code in RETRY_REASON_CODES:
                    failure_reason_code = error.reason_code
                raise
            except Exception:
                status = "unexpected_worker_exception"
                raise
            finally:
                with self._lock:
                    self.scans.append({
                        "repository_id": repository.repo_id,
                        "fixture": repository.fixture,
                        "isolated": scanner.isolated,
                        "status": status,
                        "failure_reason_code": failure_reason_code,
                        "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
                    })
                    self._active_scanners -= 1
                if previous_repository is None:
                    del self._local.repository
                else:
                    self._local.repository = previous_repository
                if previous_fixture is None:
                    del self._local.fixture
                else:
                    self._local.fixture = previous_fixture

        with mock.patch.object(ContainerExecutor, "_remove", observed_remove):
            with mock.patch.object(ContainerExecutor, "run", observed_run):
                with mock.patch.object(SyntheticScanner, "scan", observed_scan):
                    yield self


class StressSoak:
    def __init__(self, *, state_root: Path, cycles: int, supervisor: Path | None) -> None:
        self.started = time.monotonic()
        self.root = _private_directory(state_root)
        self.run_root = _private_directory(
            self.root / ("run-" + time.strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8])
        )
        self.inputs = _private_directory(self.run_root / "inputs")
        self.state = self.run_root / "recipe-state"
        self.cycles = cycles
        self.supervisor = supervisor
        self.instrumentation = RuntimeInstrumentation()
        self.scenarios: list[dict[str, Any]] = []
        self.recipe_receipts: list[dict[str, Any]] = []
        self.clock = [int(time.time())]
        self.config = self.inputs / "configuration.json"
        self.inventory = self.inputs / "inventory.json"
        self.approvals = self.inputs / "approvals.json"
        for source, destination in (
            (EXAMPLES / "config.example.json", self.config),
            (EXAMPLES / "inventory.example.json", self.inventory),
            (EXAMPLES / "approvals.example.json", self.approvals),
        ):
            _private_write(destination, source.read_bytes())
        self.configuration = RecipeConfiguration.from_file(self.config)

    def _record(self, name: str, **values: Any) -> None:
        self.scenarios.append({"scenario": name, "status": "PASS", **values})

    def _cycle(self, label: str) -> dict[str, Any]:
        before = len(self.instrumentation.containers)
        before_scans = len(self.instrumentation.scans)
        started = time.monotonic()
        receipt = RecurringSecurityRecipe.from_files(
            configuration_path=self.config,
            inventory_path=self.inventory,
            approvals_path=self.approvals,
            state_directory=self.state,
            docker=True,
            clock=lambda: self.clock[0],
        ).cycle()
        require(receipt["execution_mode"] == "synthetic_restricted_docker", "recipe downgraded its worker isolation")
        require(receipt["audit_valid"], "synthetic recipe audit chain was invalid")
        require(receipt["paid_api_calls"] == receipt["external_writes"] == 0,
                "synthetic recipe attempted an external operation")
        measured_attempts = self.instrumentation.scans[before_scans:]
        require(len(measured_attempts) == receipt["scanner_invocations"]
                and dict(Counter(row["repository_id"] for row in measured_attempts))
                == receipt["scanner_attempts_by_repository"],
                "recipe attempt ledger differs from independently observed scanner calls")
        require(len(self.instrumentation.containers) - before <= len(measured_attempts),
                "recipe started a container without an accounted scanner attempt")
        self.recipe_receipts.append({
            "label": label,
            "run_number": receipt["run_number"],
            "admitted_jobs": receipt["admitted_jobs"],
            "attempted_repositories": receipt["attempted_repositories"],
            "scanner_attempts": receipt["scanner_invocations"],
            "scanner_attempts_by_repository": receipt["scanner_attempts_by_repository"],
            "retry_attempts": receipt["retry_attempts"],
            "transient_retry_events": receipt["transient_retry_events"],
            "successful_isolation_receipts": receipt["restricted_docker_receipts"],
            **self.instrumentation.launch_metrics(self.instrumentation.containers[before:]),
            "decision_states": receipt["decision_states"],
            "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
        })
        return receipt

    def metadata_scale(self) -> dict[str, Any]:
        before_scans = len(self.instrumentation.scans)
        before_containers = len(self.instrumentation.containers)
        started = time.monotonic()
        fleet = generate_inventory(2_000)
        classifications = [classify(repository) for repository in fleet]
        archetypes = Counter(row.archetype for row in classifications)
        high_risk = sum(row.risk_tier == "high" for row in classifications)
        comparison = compare_strategies(fleet)
        require(len(fleet) == 2_000, "metadata inventory was not exactly 2,000 synthetic records")
        require(len(archetypes) == 10, "metadata inventory did not contain ten workload archetypes")
        require(high_risk == 57, "metadata inventory did not contain 57 high-risk exceptions")
        require(all(repository.fixture is None for repository in fleet),
                "metadata-only records unexpectedly contained executable fixtures")
        require(len(self.instrumentation.scans) == before_scans, "metadata classification invoked a scanner")
        require(len(self.instrumentation.containers) == before_containers,
                "metadata classification started a restricted worker")
        self._record("two_thousand_records_metadata_only", records=2_000, archetypes=10,
                     high_risk=high_risk, scanner_invocations=0, docker_starts=0)
        return {
            "classification_mode": "synthetic_metadata_only_not_scanned",
            "records_classified": len(fleet),
            "executable_repository_scans": 0,
            "docker_container_starts": 0,
            "archetype_count": len(archetypes),
            "archetypes": dict(sorted(archetypes.items())),
            "high_risk_exception_count": high_risk,
            "hierarchical_reviewer_artefacts": comparison["hierarchical"]["reviewer_artifacts"],
            "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
        }

    def recurring_and_idempotency(self) -> None:
        first = self._cycle("initial_authorised_reconciliation")
        assert_cycle_accounting(
            first, expected_attempted_repositories=DEMO_ATTEMPTED_REPOSITORIES,
            expected_statuses=DEMO_EXPECTED_STATUSES, policy=self.configuration.policy,
            expected_isolation_receipts=3, context="first_cycle",
        )
        require(first["decision_states"] == EXPECTED_DECISIONS,
                "initial cycle did not preserve its named-human holds and hostile refusal")
        hostile = first["records"]["synthetic/adversarial-docs"]
        require(hostile["status"] == "failed_safe_abstention"
                and "untrusted repository content" in hostile["reason"],
                "hostile fixture did not refuse its untrusted repository content")
        self._record("initial_reconciliation_and_prompt_injection_refusal",
                     attempted_repositories=first["attempted_repositories"],
                     scan_attempts=first["scanner_invocations"], retry_attempts=first["retry_attempts"],
                     successful_isolation_receipts=first["restricted_docker_receipts"],
                     actual_container_starts=self.recipe_receipts[-1]["actual_container_starts"],
                     hostile_repository="synthetic/adversarial-docs", decision_states=first["decision_states"])

        unchanged: list[int] = []
        for index in range(self.cycles):
            receipt = self._cycle(f"unchanged_restart_{index + 1}")
            assert_cycle_accounting(
                receipt, expected_attempted_repositories=(),
                expected_statuses=DEMO_EXPECTED_STATUSES, policy=self.configuration.policy,
                expected_isolation_receipts=0, context="restart_cycle",
            )
            unchanged.append(receipt["scanner_invocations"])
            require(receipt["quarantined_unchanged"] == ["synthetic/adversarial-docs"],
                    "hostile fixture lost its authenticated quarantine on restart")
        require(unchanged == [0] * self.cycles, "unchanged reconciliation restarted a fixture worker")
        self._record("durable_restart_and_unchanged_soak", restart_cycles=self.cycles,
                     scanner_invocations_per_cycle=unchanged,
                     quarantined_repository="synthetic/adversarial-docs")

    def _expect_pre_dispatch_refusal(self, name: str, operation: Callable[[], Any]) -> str:
        before_scans = len(self.instrumentation.scans)
        before_containers = len(self.instrumentation.containers)
        try:
            operation()
        except (PipelineError, EvidenceError) as error:
            message = str(error)
        else:
            raise StressFailure(f"{name} unexpectedly executed instead of refusing safely")
        require(len(self.instrumentation.scans) == before_scans,
                f"{name} invoked a scanner before refusing")
        require(len(self.instrumentation.containers) == before_containers,
                f"{name} started Docker before refusing")
        self._record(name, refusal=message, scanner_invocations=0, docker_starts=0)
        return message

    @staticmethod
    def _repository(document: dict[str, Any], name: str) -> dict[str, Any]:
        return next(row for row in document["repositories"] if row["repo_id"] == name)

    @staticmethod
    def _approval(document: dict[str, Any], name: str, gate: str = "scope") -> dict[str, Any]:
        return next(row for row in document["approvals"]
                    if row["repository_id"] == name and row["gate"] == gate)

    def authority_invalidation(self) -> None:
        catalog = "synthetic/catalog-service"
        edge = "synthetic/edge-auth"

        with _temporarily_edit(self.inventory, lambda document:
                               self._repository(document, catalog).__setitem__("owner", "reassigned-service-owner")):
            self._expect_pre_dispatch_refusal("changed_service_owner_invalidates_exact_scope_approval",
                                              lambda: self._cycle("unsafe_changed_owner"))

        with _temporarily_edit(self.approvals, lambda document:
                               self._approval(document, catalog).__setitem__("actor", "untrusted-actor")):
            self._expect_pre_dispatch_refusal("unauthorised_named_scope_actor_is_refused",
                                              lambda: self._cycle("unsafe_scope_actor"))

        with _temporarily_edit(self.approvals, lambda document:
                               self._approval(document, edge, "threat_model").__setitem__(
                                   "context_sha256", "0" * 64)):
            self._expect_pre_dispatch_refusal("stale_high_risk_threat_acceptance_is_refused",
                                              lambda: self._cycle("unsafe_threat_context"))

        with _temporarily_edit(self.approvals, lambda document: document.__setitem__(
            "approvals", [row for row in document["approvals"]
                          if not (row["repository_id"] == catalog and row["gate"] == "scope")],
        )):
            hold = self._cycle("revoked_scope_hold")
            require(hold["records"][catalog]["status"] == "awaiting_scope_approval"
                    and hold["scanner_invocations"] == 0,
                    "revoked repository scope reused evidence or started a scan")
            self._record("revoked_scope_prevents_cached_evidence_reuse", scanner_invocations=0,
                         decision="awaiting_scope_approval")

        with _temporarily_edit(self.approvals, lambda document: document.__setitem__(
            "approvals", [row for row in document["approvals"]
                          if not (row["repository_id"] == edge and row["gate"] == "threat_model")],
        )):
            hold = self._cycle("revoked_high_risk_threat_hold")
            require(hold["records"][edge]["status"] == "awaiting_threat_model_approval"
                    and hold["scanner_invocations"] == 0,
                    "revoked high-risk threat acceptance permitted a scan")
            self._record("revoked_high_risk_threat_acceptance_holds_execution", scanner_invocations=0,
                         decision="awaiting_threat_model_approval")

        real_format = self.inputs / "rejected-real-format.json"
        document = _read_json(self.inventory)
        document["repositories"][0]["repo_id"] = "fictional-enterprise/production-api"
        _save_json(real_format, document)
        self._expect_pre_dispatch_refusal("real_format_repository_identity_never_uses_synthetic_fixture",
                                          lambda: load_recipe_inventory(real_format))

        missing_fixture = self.inputs / "rejected-missing-fixture.json"
        document = _read_json(self.inventory)
        document["repositories"][0]["fixture"] = ""
        _save_json(missing_fixture, document)
        self._expect_pre_dispatch_refusal("missing_fixture_never_substitutes_a_clean_repository",
                                          lambda: load_recipe_inventory(missing_fixture))

    def selective_reconciliation(self) -> None:
        catalog = "synthetic/catalog-service"
        inventory = _read_json(self.inventory)
        row = self._repository(inventory, catalog)
        original_revision = str(row["commit_sha"])
        approved_revision = "b" * 40
        row["commit_sha"] = approved_revision
        _save_json(self.inventory, inventory)

        self._expect_pre_dispatch_refusal("changed_revision_without_exact_human_scope_is_refused",
                                          lambda: self._cycle("stale_revision_scope"))

        approvals = _read_json(self.approvals)
        self._approval(approvals, catalog)["revision"] = approved_revision
        _save_json(self.approvals, approvals)
        changed = self._cycle("approved_selective_revision_change")
        assert_cycle_accounting(
            changed, expected_attempted_repositories=(catalog,),
            expected_statuses=DEMO_EXPECTED_STATUSES, policy=self.configuration.policy,
            expected_isolation_receipts=1, context="changed_revision",
        )
        require(changed["records"][catalog]["reviewed_revision"] == approved_revision,
                "selective rescan did not bind the approved immutable revision")
        self._record("approved_changed_revision_rescans_only_affected_repository",
                     prior_revision=original_revision, approved_revision=approved_revision,
                     attempted_repositories=changed["attempted_repositories"],
                     scanner_invocations=changed["scanner_invocations"],
                     retry_attempts=changed["retry_attempts"],
                     docker_starts=self.recipe_receipts[-1]["actual_container_starts"])

        inventory = _read_json(self.inventory)
        self._repository(inventory, catalog)["exposure"] = "internet"
        _save_json(self.inventory, inventory)
        boundary = self._cycle("approved_selective_boundary_change")
        assert_cycle_accounting(
            boundary, expected_attempted_repositories=(catalog,),
            expected_statuses=DEMO_EXPECTED_STATUSES, policy=self.configuration.policy,
            expected_isolation_receipts=1, context="changed_boundary",
        )
        self._record("material_threat_boundary_rescans_only_affected_repository",
                     attempted_repositories=boundary["attempted_repositories"],
                     scanner_invocations=boundary["scanner_invocations"],
                     retry_attempts=boundary["retry_attempts"],
                     docker_starts=self.recipe_receipts[-1]["actual_container_starts"],
                     changed_boundary="exposure:private_to_internet")

        inventory = _read_json(self.inventory)
        row = self._repository(inventory, catalog)
        row["commit_sha"] = "c" * 40
        row["changed_paths"] = ["docs/operator-notes.md"]
        _save_json(self.inventory, inventory)
        approvals = _read_json(self.approvals)
        self._approval(approvals, catalog)["revision"] = "c" * 40
        _save_json(self.approvals, approvals)
        documentation = self._cycle("approved_documentation_only_change")
        require(documentation["scanner_invocations"] == 0
                and documentation["records"][catalog]["status"] == "skipped_unchanged_security_scope",
                "documentation-only revision launched a restricted scanner")
        self._record("documentation_only_change_avoids_unnecessary_rescan",
                     scanner_invocations=0, decision="skipped_unchanged_security_scope")

        # Restore the already reviewed, already owner-approved b... revision.
        inventory = _read_json(self.inventory)
        row = self._repository(inventory, catalog)
        row["commit_sha"] = approved_revision
        row["changed_paths"] = ["src/service.py"]
        _save_json(self.inventory, inventory)
        approvals = _read_json(self.approvals)
        self._approval(approvals, catalog)["revision"] = approved_revision
        _save_json(self.approvals, approvals)
        restored = self._cycle("restored_reviewed_revision")
        require(restored["scanner_invocations"] == 0,
                "restoring the already reviewed exact revision relaunched a worker")

    def evidence_tamper_and_recovery(self) -> None:
        checkpoint = self.state / "state.json"
        original = checkpoint.read_bytes()
        forged = _read_json(checkpoint)
        forged["payload"]["run_number"] += 1000
        _save_json(checkpoint, forged)
        try:
            self._expect_pre_dispatch_refusal("tampered_signed_checkpoint_fails_before_worker_dispatch",
                                              lambda: self._cycle("tampered_checkpoint"))
        finally:
            _private_write(checkpoint, original)
        recovered = self._cycle("restored_authenticated_checkpoint")
        require(recovered["scanner_invocations"] == 0, "restoring a signed checkpoint caused an unsafe rescan")
        self._record("authenticated_checkpoint_recovery_is_idempotent", scanner_invocations=0)

        finding = next((self.state / "evidence" / "synthetic-payments-api").rglob("findings.json"))
        original_finding = finding.read_bytes()
        document = _read_json(finding)
        document["findings"][0]["title"] = "forged synthetic finding"
        _save_json(finding, document)
        try:
            self._expect_pre_dispatch_refusal("tampered_signed_finding_fails_before_worker_dispatch",
                                              lambda: self._cycle("tampered_finding"))
        finally:
            _private_write(finding, original_finding)
        recovered = self._cycle("restored_authenticated_finding")
        require(recovered["scanner_invocations"] == 0,
                "restoring an authenticated finding caused an unnecessary rescan")
        self._record("authenticated_evidence_recovery_is_idempotent", scanner_invocations=0)

    def multiprocess_serialisation_and_lock_timeout(self) -> dict[str, Any]:
        """Use eight genuine OS processes, then prove bounded hostile contention."""
        worker = ROOT / "stress-tests" / "concurrent_recipe_worker.py"
        require(worker.is_file(), "independent multiprocess reconciliation worker is missing")
        ready = _private_directory(self.run_root / "multiprocess-ready")
        release = self.run_root / "multiprocess-release.signal"
        before_state = _read_json(self.state / "state.json")["payload"]
        first_number = int(before_state["run_number"])
        before_scans = len(self.instrumentation.scans)
        before_containers = len(self.instrumentation.containers)
        environment = scrubbed_environment()
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["PYTHONPATH"] = str(ROOT / "src")
        processes: list[subprocess.Popen[str]] = []
        results: list[dict[str, Any]] = []
        try:
            for index in range(8):
                command = [
                    sys.executable, "-B", str(worker),
                    "--checkout", str(ROOT), "--config", str(self.config),
                    "--inventory", str(self.inventory), "--approvals", str(self.approvals),
                    "--state", str(self.state), "--ready", str(ready),
                    "--start", str(release), "--worker", str(index),
                ]
                processes.append(subprocess.Popen(
                    command, cwd=ROOT, env=environment, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, text=True, shell=False,
                ))
            deadline = time.monotonic() + 20
            while len(list(ready.glob("*.ready"))) != 8:
                require(time.monotonic() < deadline,
                        "eight real synthetic reconciliation processes missed their bounded start barrier")
                require(all(process.poll() is None for process in processes),
                        "a synthetic reconciliation process failed before its start barrier")
                time.sleep(0.01)
            _private_write(release, "owner-approved bounded synthetic reconciliation\n")
            for process in processes:
                stdout, _ = process.communicate(timeout=45)
                require(process.returncode == 0 and bool(stdout.strip()),
                        "an independent synthetic reconciliation process failed")
                document = json.loads(stdout)
                require(isinstance(document, dict) and document.get("status") == "PASS",
                        "an independent synthetic reconciliation process returned unsafe evidence")
                results.append(document)
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.communicate(timeout=5)

        expected_numbers = list(range(first_number + 1, first_number + 9))
        numbers = sorted(row["run_number"] for row in results)
        final_state = _read_json(self.state / "state.json")["payload"]
        require(len({row["pid"] for row in results}) == 8,
                "synthetic reconciliation did not use eight distinct operating-system processes")
        require(numbers == expected_numbers and final_state["run_number"] == expected_numbers[-1],
                "concurrent reconciliation lost, duplicated, or silently rolled back signed state updates")
        require(all(row["scanner_invocations"] == 0 and row["audit_valid"] is True
                    and row["external_writes"] == 0 for row in results),
                "concurrent unchanged reconciliation rescanned, lost integrity, or wrote externally")
        require(final_state["audit_run_count"] == expected_numbers[-1],
                "concurrent reconciliation lost its signed cross-run audit anchor")
        require(len(self.instrumentation.scans) == before_scans
                and len(self.instrumentation.containers) == before_containers,
                "concurrent unchanged reconciliation unexpectedly dispatched a scanner")

        lock = self.state / ".cycle.lock"
        require(lock.is_file() and not lock.is_symlink()
                and stat.S_IMODE(lock.stat().st_mode) == 0o600
                and lock.stat().st_uid == os.geteuid(),
                "cross-process reconciliation lock is not an owner-private regular 0600 file")
        blocked = RecurringSecurityRecipe.from_files(
            configuration_path=self.config,
            inventory_path=self.inventory,
            approvals_path=self.approvals,
            state_directory=self.state,
            docker=True,
            clock=lambda: self.clock[0],
        )
        holder_ready = self.run_root / "independent-lock-holder.ready"
        holder_release = self.run_root / "independent-lock-holder.release"
        holder_source = (
            "import fcntl, os, sys, time\n"
            "fd = os.open(sys.argv[1], os.O_RDWR)\n"
            "fcntl.flock(fd, fcntl.LOCK_EX)\n"
            "ready = os.open(sys.argv[2], os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)\n"
            "os.close(ready)\n"
            "deadline = time.monotonic() + 10\n"
            "while not os.path.exists(sys.argv[3]):\n"
            "    if time.monotonic() >= deadline:\n"
            "        raise TimeoutError('bounded synthetic lock holder expired')\n"
            "    time.sleep(0.005)\n"
            "fcntl.flock(fd, fcntl.LOCK_UN)\n"
            "os.close(fd)\n"
        )
        holder = subprocess.Popen(
            [sys.executable, "-I", "-c", holder_source, str(lock), str(holder_ready), str(holder_release)],
            cwd=ROOT, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, shell=False,
        )
        refusal = ""
        try:
            deadline = time.monotonic() + 5
            while not holder_ready.exists():
                require(time.monotonic() < deadline and holder.poll() is None,
                        "independent cross-process lock holder failed to initialise")
                time.sleep(0.005)
            started = time.monotonic()
            try:
                with blocked.store.cycle_lock(timeout=0.15, poll_interval=0.01):
                    raise StressFailure("contended interprocess lock unexpectedly granted execution")
            except EvidenceError as error:
                refusal = str(error)
            elapsed = time.monotonic() - started
            require("timed out" in refusal and 0.10 <= elapsed < 1.5,
                    "independent cross-process contention did not fail within its bounded deadline")
            require(_read_json(self.state / "state.json")["payload"]["run_number"] == expected_numbers[-1],
                    "a timed-out interprocess lock modified signed state")
            require(len(self.instrumentation.scans) == before_scans
                    and len(self.instrumentation.containers) == before_containers,
                    "a timed-out interprocess lock dispatched a restricted scanner")
        finally:
            _private_write(holder_release, "release\n")
            if holder.poll() is None:
                try:
                    holder.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    holder.kill()
                    holder.communicate(timeout=5)
        require(holder.returncode == 0, "independent cross-process lock holder failed to release cleanly")
        result = {
            "distinct_os_processes": 8,
            "reported_run_numbers": numbers,
            "persisted_final_run_number": final_state["run_number"],
            "worker_scanner_invocations": [row["scanner_invocations"] for row in results],
            "lock_mode": "0600",
            "lock_owner_uid_verified": True,
            "independent_lock_holder_pid": holder.pid,
            "bounded_contention_refused_before_dispatch": True,
            "contention_refusal": refusal,
            "contention_elapsed_ms": round(elapsed * 1000, 3),
            "scanner_invocations_during_contention": 0,
            "docker_starts_during_contention": 0,
        }
        self._record("eight_process_signed_state_serialisation_and_bounded_lock_refusal", **result)
        return result

    def durable_audit_history_tamper_and_recovery(self) -> dict[str, Any]:
        """Tamper a historical signed event and require zero pre-refusal dispatch."""
        checkpoint = _read_json(self.state / "state.json")["payload"]
        directory = self.state / "audit"
        documents = sorted(directory.glob("run-*.json"))
        require(len(documents) == checkpoint["audit_run_count"] == checkpoint["run_number"],
                "persisted audit history omits one or more signed recurring review runs")
        previous = "0" * 64
        total = 0
        for index, path in enumerate(documents, start=1):
            document = _read_json(path)
            require(document["run_number"] == index
                    and document["previous_audit_digest"] == previous,
                    "persisted recurring audit events have a broken cross-run continuity link")
            require(AuditLog().verify(tuple(document["events"]))
                    and document["event_count"] == len(document["events"]),
                    "persisted recurring audit contains an invalid per-run event hash chain")
            require(path.stat().st_uid == os.geteuid()
                    and stat.S_IMODE(path.stat().st_mode) == 0o600,
                    "persisted recurring audit event file is not owner-private")
            previous = document["audit_digest"]
            total += len(document["events"])
        require(previous == checkpoint["audit_tail_digest"]
                and total == checkpoint["audit_event_count"],
                "persisted recurring audit history does not match the signed checkpoint anchor")
        require(stat.S_IMODE(directory.stat().st_mode) == 0o700,
                "persisted recurring audit directory is not owner-private")

        original = documents[0].read_bytes()
        forged = _read_json(documents[0])
        forged["events"][0]["event"] = "hostile_forged_named_human_approval"
        _save_json(documents[0], forged)
        before_scans = len(self.instrumentation.scans)
        before_containers = len(self.instrumentation.containers)
        try:
            try:
                self._cycle("tampered_historical_durable_audit")
            except EvidenceError as error:
                refusal = str(error)
            else:
                raise StressFailure("tampered historical durable audit event was accepted")
            require("audit" in refusal.casefold(),
                    "historical durable audit tampering was not identified as an audit refusal")
            require(len(self.instrumentation.scans) == before_scans
                    and len(self.instrumentation.containers) == before_containers,
                    "historical audit tampering dispatched a scanner before being rejected")
        finally:
            _private_write(documents[0], original)
        recovered = self._cycle("restored_authenticated_durable_audit")
        require(recovered["run_number"] == checkpoint["run_number"] + 1
                and recovered["scanner_invocations"] == 0
                and recovered["durable_audit_valid"] is True,
                "authenticated historical audit recovery did not resume idempotently")
        result = {
            "historical_runs_verified": len(documents),
            "historical_events_verified": total,
            "signed_tail_digest": checkpoint["audit_tail_digest"],
            "tampered_run_number": 1,
            "tampered_prior_event_refused_before_dispatch": True,
            "scanner_invocations_during_refusal": 0,
            "docker_starts_during_refusal": 0,
            "authenticated_recovered_run_number": recovered["run_number"],
            "recovery_scanner_invocations": 0,
            "audit_directory_mode": "0700",
            "audit_file_mode": "0600",
            "crash_durability_fsync_claimed": False,
        }
        self._record("durable_signed_cross_run_audit_tamper_refusal_and_recovery", **result)
        return result

    def _sample_record(self, index: int, fixture: str) -> Repository:
        base = next(record for record in load_recipe_inventory(self.inventory)
                    if record.repo_id == "synthetic/catalog-service")
        return replace(
            base,
            repo_id=f"synthetic/stress-{index:04d}",
            commit_sha=hashlib.sha1(f"synthetic-stress-revision-{index}".encode("ascii")).hexdigest(),
            owner=f"stress-service-owner-{index:02d}",
            exposure="private",
            changed_paths=("src/service.py",),
            fixture=fixture,
        )

    def _pipeline(self, *, policy: FleetPolicy, scanner: SyntheticScanner) -> FleetPipeline:
        return FleetPipeline(
            policy=policy,
            approvals=ApprovalLedger(self.configuration.owners, clock=lambda: self.clock[0]),
            catalogue=ThreatCatalogue(
                organisation_controls=self.configuration.organisation_controls,
                version=self.configuration.organisation_model_version,
            ),
            scanner=scanner,
            clock=lambda: self.clock[0],
        )

    @staticmethod
    def _approve(flow: FleetPipeline, repository: Repository) -> None:
        flow.approvals.approve(
            "scope", repository.repo_id, flow.scope_target(repository), "security-owner"
        )
        assignment = flow.catalogue.assign(repository)
        if assignment.requires_human_acceptance:
            flow.approvals.approve(
                "threat_model", repository.repo_id, assignment.effective_model_hash, "threat-owner"
            )

    @staticmethod
    def _assert_pipeline_accounting(
        receipt: dict[str, Any], *, policy: FleetPolicy,
        expected_attempted_repositories: tuple[str, ...],
        expected_statuses: dict[str, str], scanner_invocations_before: int = 0,
    ) -> None:
        # Pipeline counters are cumulative when an object is reused. Validate
        # the current run's exact job/attempt ledger without inventing the
        # durable-audit or isolation fields supplied by a full recipe receipt.
        assert_attempt_accounting(
            receipt, expected_attempted_repositories=expected_attempted_repositories,
            policy=policy, scanner_invocations_before=scanner_invocations_before,
        )
        require(set(receipt["records"]) == set(expected_statuses)
                and all(receipt["records"][name]["status"] == expected
                        for name, expected in expected_statuses.items()),
                "pipeline changed an exact repository decision or named-human hold")
        require(receipt["consumed_units"]
                == receipt["scanner_invocations"] * policy.estimated_scan_units
                and receipt["consumed_units"] <= policy.max_campaign_units
                and receipt["max_observed_reserved_units"] <= policy.max_campaign_units
                and receipt["reserved_units"] == 0,
                "pipeline measured attempts violated or leaked its hard capacity budget")
        require(receipt["max_active_workers"] <= policy.max_concurrent,
                "pipeline exceeded its approved worker concurrency ceiling")
        require(receipt["audit_valid"] is True and receipt["product_execution"] is False
                and receipt["external_writes"] == 0,
                "pipeline lost authenticated evidence or crossed the synthetic execution boundary")

    def batching_and_capacity(self) -> None:
        fixtures = ("config_service", "inventory_service", "slug_service", "safe_service")
        records = tuple(self._sample_record(100 + index, fixture)
                        for index, fixture in enumerate(fixtures))
        scanner = SyntheticScanner(isolated=True)
        policy = FleetPolicy(max_concurrent=2, max_scans_per_run=2, max_campaign_units=200)
        flow = self._pipeline(policy=policy, scanner=scanner)
        for repository in records:
            self._approve(flow, repository)
        starts = len(self.instrumentation.containers)
        first = flow.run(records)
        first_states = {
            row.repo_id: "review_packet_ready" if index < 2 else "deferred_rate_limit"
            for index, row in enumerate(records)
        }
        self._assert_pipeline_accounting(
            first, policy=policy,
            expected_attempted_repositories=tuple(row.repo_id for row in records[:2]),
            expected_statuses=first_states,
        )
        require(first["admitted"] == 2, "first bounded batch admitted an unsafe number of fixtures")
        require(sum(row["status"] == "deferred_rate_limit"
                    for row in first["records"].values()) == 2,
                "excess approved fixture records did not receive rate-limit backpressure")
        second = flow.run(records)
        completed_states = {row.repo_id: "review_packet_ready" for row in records}
        self._assert_pipeline_accounting(
            second, policy=policy,
            expected_attempted_repositories=tuple(row.repo_id for row in records[2:]),
            expected_statuses=completed_states,
            scanner_invocations_before=first["scanner_invocations"],
        )
        require(second["admitted"] == 2, "second bounded batch did not drain its deferred fixtures")
        third = flow.run(records)
        self._assert_pipeline_accounting(
            third, policy=policy, expected_attempted_repositories=(),
            expected_statuses=completed_states,
            scanner_invocations_before=second["scanner_invocations"],
        )
        require(third["admitted"] == 0
                and sum(scanner.invocations.values()) == second["scanner_invocations"],
                "unchanged batch replay duplicated an already completed fixture")
        require(scanner.max_active_workers <= policy.max_concurrent,
                "restricted worker concurrency exceeded its approved ceiling")
        launch_metrics = self.instrumentation.launch_metrics(self.instrumentation.containers[starts:])
        measured_starts = launch_metrics["actual_container_starts"]
        require(len(scanner.isolation_receipts) == len(records)
                and len(records) <= measured_starts <= launch_metrics["executor_run_invocations"]
                <= second["scanner_invocations"],
                "bounded batch launches did not reconcile with exact successful jobs and measured attempts")
        require(first["reserved_units"] == second["reserved_units"] == third["reserved_units"] == 0,
                "bounded admission leaked a reserved worker budget")
        self._record("bounded_batching_backpressure_and_worker_concurrency", fixture_records=4,
                     admitted_per_cycle=[2, 2, 0], first_cycle_rate_limited=2,
                     max_allowed_workers=2, peak_observed_workers=scanner.max_active_workers,
                     scanner_attempts_per_cycle=[
                         sum(row["scanner_attempts_by_repository"].values())
                         for row in (first, second, third)
                     ],
                     retry_attempts_per_cycle=[row["retry_attempts"] for row in (first, second, third)],
                     successful_isolation_receipts=len(scanner.isolation_receipts),
                     **launch_metrics, fixture_types=list(fixtures))

        capacity_scanner = SyntheticScanner(isolated=True)
        denied = self._pipeline(
            policy=FleetPolicy(max_campaign_units=13, max_attempts=2,
                               estimated_scan_units=5, max_inflight_overshoot_units=2),
            scanner=capacity_scanner,
        )
        for record in records[:2]:
            self._approve(denied, record)
        before = len(self.instrumentation.containers)
        exhausted = denied.run(records[:2])
        require(exhausted["scanner_invocations"] == 0
                and all(row["status"] == "deferred_budget"
                        for row in exhausted["records"].values()),
                "exhausted admission capacity dispatched a fixture worker")
        require(len(self.instrumentation.containers) == before,
                "insufficient hard budget started a restricted container")
        self._record("hard_capacity_exhaustion_fails_before_dispatch", deferred_repositories=2,
                     budget_units=13, minimum_reserved_units=14,
                     scanner_invocations=0, actual_container_starts=0)

    def retry_failure_and_cancellation(self) -> None:
        retry, logical_timeout, permanent, healthy, cancelled, hostile = (
            self._sample_record(200, "safe_service"),
            self._sample_record(201, "safe_service"),
            self._sample_record(202, "safe_service"),
            self._sample_record(203, "inventory_service"),
            self._sample_record(204, "safe_service"),
            self._sample_record(205, "adversarial_service"),
        )
        scanner = SyntheticScanner(isolated=True, behaviour={
            retry.repo_id: ("transient", "success"),
            logical_timeout.repo_id: ("timeout", "timeout"),
            permanent.repo_id: ("permanent",),
        })
        policy = FleetPolicy(max_concurrent=3, max_attempts=2, max_scans_per_run=10,
                             max_campaign_units=250)
        flow = self._pipeline(policy=policy, scanner=scanner)
        records = (retry, logical_timeout, permanent, healthy, cancelled, hostile)
        for repository in records:
            self._approve(flow, repository)
        flow.cancel(cancelled.repo_id, actor="security-owner")
        before = len(self.instrumentation.containers)
        outcome = flow.run(records)
        self._assert_pipeline_accounting(
            outcome, policy=policy,
            expected_attempted_repositories=tuple(row.repo_id for row in records if row != cancelled),
            expected_statuses={
                retry.repo_id: "review_packet_ready",
                logical_timeout.repo_id: "failed_safe_abstention",
                permanent.repo_id: "failed_safe_abstention",
                healthy.repo_id: "review_packet_ready",
                cancelled.repo_id: "cancelled",
                hostile.repo_id: "failed_safe_abstention",
            },
        )
        rows = outcome["records"]
        require(rows[retry.repo_id]["status"] == "review_packet_ready"
                and rows[retry.repo_id]["attempts"] == 2,
                "bounded transient scanner failure did not recover on exactly one retry")
        require(rows[logical_timeout.repo_id]["status"] == "failed_safe_abstention"
                and rows[logical_timeout.repo_id]["attempts"] == 2,
                "synthetic scanner timeout exceeded its hard two-attempt ceiling")
        require(rows[permanent.repo_id]["status"] == "failed_safe_abstention"
                and rows[permanent.repo_id]["attempts"] == 1,
                "permanent scanner refusal was retried")
        require(rows[healthy.repo_id]["status"] == "review_packet_ready",
                "one failed fixture blocked an independently approved healthy fixture")
        require(rows[cancelled.repo_id]["status"] == "cancelled"
                and scanner.invocations[cancelled.repo_id] == 0,
                "named-owner cancellation still dispatched a fixture")
        require(rows[hostile.repo_id]["status"] == "failed_safe_abstention"
                and "untrusted repository content" in rows[hostile.repo_id]["reason"],
                "hostile fixture escaped prompt-injection quarantine")
        launch_metrics = self.instrumentation.launch_metrics(self.instrumentation.containers[before:])
        measured_starts = launch_metrics["actual_container_starts"]
        # Four injected failures happen before container creation: one
        # transient, two logical deadlines and one permanent refusal.
        injected_pre_container_failures = 4
        require(len(scanner.isolation_receipts) == 2
                and 3 <= measured_starts <= launch_metrics["executor_run_invocations"]
                <= outcome["scanner_invocations"] - injected_pre_container_failures,
                "failure-isolation launches did not match bounded attempts and exact successful jobs")
        self._record("transient_retry_hard_timeout_failure_isolation_and_owner_cancellation",
                     transient_attempts=2, logical_timeout_attempts=2,
                     permanent_failure_attempts=1, healthy_sibling="review_packet_ready",
                     cancelled_scan_attempts=0, hostile_fixture="failed_safe_abstention",
                     injected_pre_container_failures=injected_pre_container_failures,
                     measured_retry_attempts=outcome["retry_attempts"],
                     transient_retry_events=outcome["transient_retry_events"],
                     successful_isolation_receipts=len(scanner.isolation_receipts),
                     **launch_metrics,
                     scanner_invocations_by_repository=dict(sorted(scanner.invocations.items())))

    def genuine_container_timeout_cleanup(self) -> None:
        before = len(self.instrumentation.containers)
        runtime = ContainerRuntime()
        fixture = ROOT / "fixtures" / "safe_service"
        with runtime.open(fixture, "synthetic-soak-timeout") as workspace:
            executor = workspace.executor
            require(executor is not None, "actual timeout scenario did not obtain a restricted executor")
            try:
                executor.run(["python3", "-I", "-c", "import time; time.sleep(5)"], timeout=0.4)
            except subprocess.TimeoutExpired:
                pass
            else:
                raise StressFailure("real restricted Docker timeout unexpectedly completed")
            require(bool(executor.container_names), "timed-out restricted Docker worker had no identity")
            name = executor.container_names[-1]
            require(executor._inspect(name).returncode != 0,
                    "timed-out restricted Docker worker survived its forced cleanup")
        require(len(self.instrumentation.containers) - before == 1,
                "actual restricted timeout did not produce exactly one executor invocation")
        timeout_receipt = self.instrumentation.containers[-1]
        require(timeout_receipt["status"] == "timeout_forced_cleanup"
                and timeout_receipt["container_started"] is True,
                "Docker CLI timed out without evidence of a running worker before verified cleanup")
        self._record("genuine_restricted_docker_timeout_forces_verified_cleanup",
                     actual_container_starts=1, container_removed=True,
                     start_evidence=timeout_receipt["start_evidence"],
                     worker_status="timeout_forced_cleanup")

    def unexpected_worker_interruption_isolated(self) -> None:
        interrupted = self._sample_record(300, "safe_service")
        healthy = self._sample_record(301, "config_service")
        sentinel = "SYNTHETIC_PRIVATE_FAILURE_DETAIL_MUST_NOT_APPEAR"

        class InterruptedFixtureScanner(SyntheticScanner):
            def _isolated_matches(self, fixture: Path, repository: Repository) -> Any:
                if repository.repo_id == interrupted.repo_id:
                    raise OSError(sentinel)
                return super()._isolated_matches(fixture, repository)

        scanner = InterruptedFixtureScanner(isolated=True)
        policy = FleetPolicy(max_concurrent=2, max_attempts=2,
                             max_scans_per_run=4, max_campaign_units=100)
        flow = self._pipeline(policy=policy, scanner=scanner)
        for repository in (interrupted, healthy):
            self._approve(flow, repository)
        before = len(self.instrumentation.containers)
        result = flow.run((interrupted, healthy))
        self._assert_pipeline_accounting(
            result, policy=policy,
            expected_attempted_repositories=(interrupted.repo_id, healthy.repo_id),
            expected_statuses={
                interrupted.repo_id: "failed_safe_abstention",
                healthy.repo_id: "review_packet_ready",
            },
        )
        failed = result["records"][interrupted.repo_id]
        sibling = result["records"][healthy.repo_id]
        require(failed["status"] == "failed_safe_abstention",
                "unexpected worker interruption did not become a safe per-repository refusal")
        require(failed["attempts"] == 1,
                "unexpected worker interruption was retried without trusted recovery authority")
        require(sentinel not in json.dumps(result, sort_keys=True),
                "unexpected worker failure leaked sensitive exception text into its receipt")
        require(sentinel not in json.dumps(flow.audit.events, sort_keys=True),
                "unexpected worker failure leaked sensitive exception text into the audit log")
        require(sibling["status"] == "review_packet_ready",
                "unexpected worker interruption cancelled an independently approved healthy sibling")
        require(result["reserved_units"] == 0,
                "unexpected worker interruption leaked a hard-capacity reservation")
        require(result["audit_valid"],
                "unexpected worker interruption damaged its authenticated audit chain")
        require(scanner.invocations[interrupted.repo_id] == 1
                and scanner.invocations[healthy.repo_id]
                == result["scanner_attempts_by_repository"][healthy.repo_id],
                "unexpected worker interruption did not preserve exact independent scan accounting")
        observed_containers = self.instrumentation.containers[before:]
        launch_metrics = self.instrumentation.launch_metrics(observed_containers)
        require(len(scanner.isolation_receipts) == 1
                and 1 <= launch_metrics["actual_container_starts"]
                <= len(observed_containers) <= scanner.invocations[healthy.repo_id]
                and all(row["repository_id"] == healthy.repo_id for row in observed_containers),
                "only the approved healthy sibling should start a genuine restricted worker")
        self._record("unexpected_worker_oserror_isolated_from_healthy_sibling", interrupted_status=failed["status"],
                     interrupted_attempts=failed["attempts"], healthy_status=sibling["status"],
                     healthy_scan_attempts=scanner.invocations[healthy.repo_id],
                     measured_retry_attempts=result["retry_attempts"],
                     healthy_isolated_container_starts=launch_metrics["actual_container_starts"],
                     **launch_metrics,
                     reserved_units_after_completion=0,
                     sensitive_error_detail_redacted=True)

    def duplicate_burst_supervisor(self) -> dict[str, Any]:
        selected = self.supervisor or (ROOT / "scripts" / "run_bounded_security_supervisor.py")
        require(selected.is_file(), "bounded reconciliation supervisor is unavailable for duplicate-burst stress")
        inventory = _read_json(self.inventory)
        catalog = self._repository(inventory, "synthetic/catalog-service")
        payments = self._repository(inventory, "synthetic/payments-api")
        edge = self._repository(inventory, "synthetic/edge-auth")
        hostile = self._repository(inventory, "synthetic/adversarial-docs")

        entries: list[dict[str, str]] = [
            {"event_id": "bad-owner-1", "repository_id": "actual-customer/private-repo",
             "revision": "0" * 40, "event_type": "repository_changed"},
            {"event_id": "bad-revision-1", "repository_id": payments["repo_id"],
             "revision": "0" * 40, "event_type": "repository_changed"},
            {"event_id": "bad-type-1", "repository_id": payments["repo_id"],
             "revision": payments["commit_sha"], "event_type": "grant_approval"},
        ]
        event_number = 0
        for record, repeats in ((payments, 5), (catalog, 4), (edge, 3), (hostile, 3)):
            for _ in range(repeats):
                event_number += 1
                entries.append({
                    "event_id": f"synthetic-event-{event_number:03d}",
                    "repository_id": record["repo_id"],
                    "revision": record["commit_sha"],
                    "event_type": "repository_changed",
                })
        events = self.inputs / "synthetic-events.jsonl"
        _private_write(events, "".join(json.dumps(row, sort_keys=True) + "\n" for row in entries))
        supervisor_state = self.run_root / "supervisor-state"
        specification = importlib.util.spec_from_file_location(
            "independently_instrumented_bounded_supervisor", selected,
        )
        require(specification is not None and specification.loader is not None,
                "bounded reconciliation supervisor could not be imported")
        module = importlib.util.module_from_spec(specification)
        sys.modules[specification.name] = module
        specification.loader.exec_module(module)

        arguments = [
            "--config", str(self.config),
            "--inventory", str(self.inventory),
            "--approvals", str(self.approvals),
            "--state-dir", str(supervisor_state),
            "--events", str(events),
            "--max-cycles", str(max(6, self.cycles)),
            "--interval-seconds", "0",
            "--max-events-per-cycle", "6",
            "--max-pending-events", "2",
            "--docker",
        ]
        before = len(self.instrumentation.containers)
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            code = module.main(arguments)
        require(code == 0, "bounded reconciliation supervisor failed during duplicate-event stress")
        receipt = json.loads(captured.getvalue())
        require(receipt["cycles_completed"] == max(6, self.cycles),
                "bounded reconciliation supervisor did not honour its maximum cycle count")
        scans = receipt["scanner_invocations_per_cycle"]
        measured_attempts = []
        for index, cycle in enumerate(receipt["cycle_metrics"]):
            run_number = cycle["recipe_run_number"]
            full = _read_json(supervisor_state / "runs" / f"run-{run_number:04d}.json")
            assert_cycle_accounting(
                full,
                expected_attempted_repositories=DEMO_ATTEMPTED_REPOSITORIES if index == 0 else (),
                expected_statuses=DEMO_EXPECTED_STATUSES, policy=self.configuration.policy,
                expected_isolation_receipts=3 if index == 0 else 0,
                context="supervisor_cycle",
            )
            require(cycle["scanner_invocations"] == full["scanner_invocations"]
                    and cycle["restricted_docker_receipts"] == full["restricted_docker_receipts"]
                    and cycle["decision_states"] == full["decision_states"],
                    "supervisor summary differs from its persisted full recipe receipt")
            measured_attempts.append(full["scanner_invocations"])
        require(scans == measured_attempts and all(value == 0 for value in scans[1:]),
                "duplicate event delivery launched repeated fixture scans")
        require(receipt["duplicate_events_coalesced"] > 0,
                "duplicate delivery burst was not independently coalesced")
        require(receipt["rejected_events"] >= 3,
                "hostile identity, stale revision or unauthorised event did not fail closed")
        require(receipt["backpressure_events"] > 0,
                "bounded event queue failed to exert observable backpressure")
        require(receipt["max_pending_observed"] <= 2,
                "bounded event queue exceeded its approved pending capacity")
        launch_metrics = self.instrumentation.launch_metrics(self.instrumentation.containers[before:])
        measured_starts = launch_metrics["actual_container_starts"]
        require(len(DEMO_ATTEMPTED_REPOSITORIES) <= measured_starts
                <= launch_metrics["executor_run_invocations"] <= sum(measured_attempts)
                and receipt["scan_attempts_total"] == sum(measured_attempts),
                "bounded supervisor launches did not match exact jobs and bounded measured attempts")
        require(receipt["isolated_worker_receipts_total"] == 3,
                "bounded supervisor did not distinguish three successful isolation receipts")
        require(receipt["paid_api_calls"] == receipt["external_writes"] == 0,
                "bounded supervisor attempted an external operation")
        self._record("automatic_duplicate_event_burst_backpressure_and_hostile_event_refusal",
                     supervisor_cycles=receipt["cycles_completed"],
                     scanner_invocations_per_cycle=scans,
                     duplicate_events_coalesced=receipt["duplicate_events_coalesced"],
                     rejected_events=receipt["rejected_events"],
                     backpressure_events=receipt["backpressure_events"],
                     max_pending_observed=receipt["max_pending_observed"],
                     **launch_metrics,
                     successful_isolation_receipts=receipt["isolated_worker_receipts_total"],
                     graceful_shutdown=receipt["graceful_shutdown"])
        return receipt

    def verify_cleanup_and_permissions(self) -> dict[str, Any]:
        names = {
            entry["container_name"] for entry in self.instrumentation.containers
            if isinstance(entry.get("container_name"), str)
        }
        completed = subprocess.run(
            ["docker", "ps", "--all", "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=10, check=False,
            shell=False, env=scrubbed_environment(),
        )
        require(completed.returncode == 0, "restricted worker cleanup could not be independently verified")
        survivors = sorted(names & set(completed.stdout.splitlines()))
        require(not survivors, "one or more stress-owned restricted Docker containers survived cleanup")
        directories = [self.run_root, *[path for path in self.run_root.rglob("*") if path.is_dir()]]
        files = [path for path in self.run_root.rglob("*") if path.is_file()]
        require(all(stat.S_IMODE(path.stat().st_mode) == 0o700 for path in directories),
                "stress state contains a directory without owner-only 0700 permissions")
        require(all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in files),
                "stress state contains a file without owner-only 0600 permissions")
        self._record("all_owned_restricted_workers_cleaned_and_state_owner_private",
                     owned_container_names=len(names), surviving_owned_containers=0,
                     private_directories=len(directories), private_files=len(files))
        return {
            "owned_container_names_verified_absent": len(names),
            "surviving_owned_containers": survivors,
            "owner_private_directories": len(directories),
            "owner_private_files": len(files),
            "directory_mode": "0700",
            "file_mode": "0600",
        }

    @staticmethod
    def _latency_summary(values: list[float]) -> dict[str, float | int]:
        require(bool(values), "stress run produced no measured restricted worker latencies")
        ordered = sorted(values)

        def percentile(value: float) -> float:
            rank = max(0, min(len(ordered) - 1, math.ceil(value * len(ordered)) - 1))
            return round(ordered[rank], 3)

        return {
            "observations": len(values),
            "minimum_ms": round(ordered[0], 3),
            "median_ms": percentile(0.5),
            "p95_ms": percentile(0.95),
            "maximum_ms": round(ordered[-1], 3),
        }

    def run(self) -> dict[str, Any]:
        docker = _docker_prerequisites()
        with self.instrumentation.install():
            metadata = self.metadata_scale()
            self.recurring_and_idempotency()
            self.authority_invalidation()
            self.selective_reconciliation()
            self.evidence_tamper_and_recovery()
            multiprocess = self.multiprocess_serialisation_and_lock_timeout()
            durable_audit = self.durable_audit_history_tamper_and_recovery()
            self.batching_and_capacity()
            self.retry_failure_and_cancellation()
            self.unexpected_worker_interruption_isolated()
            self.genuine_container_timeout_cleanup()
            supervisor = self.duplicate_burst_supervisor()
            cleanup = self.verify_cleanup_and_permissions()

        containers = self.instrumentation.containers
        scans = self.instrumentation.scans
        launch_metrics = self.instrumentation.launch_metrics(containers)
        successes = sum(entry["isolation_verified"] for entry in containers)
        hostile_failures = sum(entry["status"] == "hostile_or_failed_exit" for entry in containers)
        timeouts = sum(entry["status"] == "timeout_forced_cleanup" for entry in containers)
        unverified = sum(entry["status"] == "completed_unverified_receipt" for entry in containers)
        require(launch_metrics["actual_container_starts"]
                == successes + hostile_failures + timeouts + unverified
                and launch_metrics["executor_run_invocations"]
                == launch_metrics["actual_container_starts"]
                + launch_metrics["rejected_container_launches"]
                + launch_metrics["unresolved_container_starts"],
                "executor calls, evidenced worker starts and unresolved launches did not reconcile")
        require(Counter(row["repository_id"] for row in containers
                        if row["status"] == "completed_unverified_receipt")
                == Counter(row["repository_id"] for row in scans
                           if row["status"] == "retryable_failure"
                           and row["failure_reason_code"] == "restricted_receipt_invalid"),
                "an unverified worker receipt lacks its typed scanner failure record")
        require(all(row["status"] == "timeout_unresolved_start_cleanup_verified"
                    for row in containers
                    if not row["container_started"] and row["status"] != "launch_rejected"),
                "an executor failure has no explained launch or mandatory-cleanup outcome")
        require(Counter(row["repository_id"] for row in containers if row["status"] in {
                    "timeout_forced_cleanup", "timeout_unresolved_start_cleanup_verified",
                }) == Counter(row["repository_id"] for row in scans
                              if row["status"] == "retryable_failure"
                              and row["failure_reason_code"] == "restricted_worker_timeout")
                + Counter({"explicit-timeout-probe": 1}),
                "a container timeout lacks its typed retry failure or explicit timeout-probe receipt")
        require(all(entry["isolated"] for entry in scans),
                "a fixture scanner silently downgraded to unrestricted host execution")
        fixture_types = sorted({str(row["fixture"]) for row in scans if row.get("fixture")})
        available = sorted(path.name for path in (ROOT / "fixtures").iterdir()
                           if path.is_dir() and (path / "src").is_dir())
        require(len(available) == 7, "approved synthetic fixture corpus no longer contains seven repositories")
        require(set(fixture_types) == set(available),
                "stress fixture corpus did not explicitly exercise all seven synthetic fixtures")
        elapsed = time.monotonic() - self.started
        require(elapsed < 300, "bounded local stress/soak exceeded its five-minute ceiling")
        revision_cycle = next(row for row in self.recipe_receipts
                              if row["label"] == "approved_selective_revision_change")
        boundary_cycle = next(row for row in self.recipe_receipts
                              if row["label"] == "approved_selective_boundary_change")

        return {
            "status": "PASS",
            "execution": "bounded_synthetic_restricted_docker_stress_soak",
            "state_directory": str(self.run_root),
            "state_directory_outside_checkout": not self.run_root.is_relative_to(ROOT),
            "docker": docker,
            "metadata_only_scale": metadata,
            "actual_fixture_execution": {
                "available_synthetic_fixture_corpus_size": len(available),
                "available_synthetic_fixtures": available,
                "fixture_types_actually_attempted": fixture_types,
                "unique_synthetic_repository_identities_attempted": len({row["repository_id"] for row in scans}),
                "scanner_attempts_including_retries_without_container": len(scans),
                "executor_run_invocations": launch_metrics["executor_run_invocations"],
                "actual_restricted_docker_container_starts": launch_metrics["actual_container_starts"],
                "rejected_container_launches": launch_metrics["rejected_container_launches"],
                "unresolved_container_starts": launch_metrics["unresolved_container_starts"],
                "successful_verified_container_isolation_receipts": successes,
                "hostile_or_failed_container_exits": hostile_failures,
                "actual_container_timeouts_with_verified_cleanup": timeouts,
                "completed_workers_with_unverified_receipts": unverified,
                "peak_concurrent_executor_run_invocations": self.instrumentation.peak_containers,
                "peak_concurrent_restricted_containers_upper_bound": self.instrumentation.peak_containers,
                "peak_concurrent_synthetic_scanner_workers": self.instrumentation.peak_scanners,
                "executor_run_latency": self._latency_summary([entry["elapsed_ms"] for entry in containers]),
                "observed_local_fixture_scans_per_second": round(successes / max(elapsed, 0.001), 4),
                "throughput_scope": "observed approved local synthetic fixture runs only; not product or customer throughput",
            },
            "reconciliation": {
                "recipe_cycles_completed": len(self.recipe_receipts),
                "recipe_cycle_receipts": self.recipe_receipts,
                "initial_cycle_scans": self.recipe_receipts[0]["scanner_attempts"],
                "unchanged_restart_cycles": self.cycles,
                "unchanged_restart_rescans": 0,
                "selective_changed_revision_repositories": revision_cycle["attempted_repositories"],
                "selective_changed_revision_rescans": revision_cycle["scanner_attempts"],
                "selective_changed_revision_container_starts": revision_cycle["actual_container_starts"],
                "selective_changed_boundary_repositories": boundary_cycle["attempted_repositories"],
                "selective_changed_boundary_rescans": boundary_cycle["scanner_attempts"],
                "selective_changed_boundary_container_starts": boundary_cycle["actual_container_starts"],
                "supervisor_cycles_completed": supervisor["cycles_completed"],
                "supervisor_scanner_invocations_per_cycle": supervisor["scanner_invocations_per_cycle"],
                "duplicate_events_coalesced": supervisor["duplicate_events_coalesced"],
                "rejected_hostile_or_stale_events": supervisor["rejected_events"],
                "queue_backpressure_events": supervisor["backpressure_events"],
            },
            "multiprocess_reconciliation": multiprocess,
            "durable_audit_continuity": durable_audit,
            "scenarios": self.scenarios,
            "scenario_count": len(self.scenarios),
            "all_scenarios_passed": all(row["status"] == "PASS" for row in self.scenarios),
            "container_launch_receipts": containers,
            "scanner_attempt_receipts": scans,
            "cleanup": cleanup,
            "elapsed_seconds": round(elapsed, 3),
            "paid_api_calls": 0,
            "hosted_model_calls": 0,
            "real_customer_repository_access": 0,
            "live_product_security_scans": 0,
            "image_pulls": 0,
            "external_writes": 0,
            "provider_pull_requests_created": 0,
            "automatic_merges_or_deployments": 0,
            "limitations": [
                "The 2,000-record fleet exercises metadata classification only; no generated record is inspected or scanned.",
                "Only the seven bundled, explicitly fictional fixture types are examined in real restricted Docker workers.",
                "Recorded scanner-timeout retries are synthetic failure injections; a separate actual timed-out Docker worker proves forced cleanup.",
                "Executor invocations are not assumed to be started containers: successful exits, validated isolation or refusal receipts, and pre-cleanup running-state observations supply start evidence; unresolved attempts remain separate.",
                "Malformed worker receipts are counted separately and never prove isolation; a cycle passes only after existing bounded typed retries produce its exact required final decisions and valid isolation receipts.",
                "Observed local fixture throughput and latency are not product throughput, customer-scale performance, precision, recall or operating cost.",
                "The owner-private signed audit chain proves tamper detection and process coordination; filesystem fsync crash durability and adversarial same-user writers are not proven.",
                "No real customer repository, hosted model, Codex Security product scanner, provider integration or production deployment is exercised.",
            ],
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--state-dir", type=Path,
        default=None,
        help=("Owner-private retained stress evidence outside the checkout; "
              "defaults to a newly created 0700 operating-system temporary directory."),
    )
    parser.add_argument("--cycles", type=int, default=8,
                        help="Unchanged durable recipe restart cycles; must be between 1 and 30.")
    parser.add_argument("--output", type=Path, default=None,
                        help="Optional owner-private JSON receipt outside the disposable checkout.")
    parser.add_argument("--supervisor", type=Path, default=None,
                        help="Optional reviewed bounded reconciliation supervisor script.")
    return parser


def main(argv: list[str] | None = None) -> int:
    options = build_parser().parse_args(argv)
    require(not isinstance(options.cycles, bool) and 1 <= options.cycles <= 30,
            "unchanged soak cycles must be between one and thirty")
    os.environ.update({
        "RUN_LIVE_MODEL": "0",
        "APPROVE_PAID_OPENAI_REQUEST": "0",
        "OPENAI_API_KEY": "",
        "CODEX_API_KEY": "",
        "OPENAI_WEBHOOK_SECRET": "",
    })
    os.environ.pop("CODEX_SECURITY_SCHEMA_ROOT", None)
    state_directory = options.state_dir or Path(
        tempfile.mkdtemp(prefix="governed-security-soak-")
    )
    receipt = StressSoak(state_root=state_directory, cycles=options.cycles,
                         supervisor=options.supervisor).run()
    output = options.output or (Path(receipt["state_directory"]) / "stress-soak-receipt.json")
    output = output.expanduser().absolute()
    require(not output.is_relative_to(ROOT), "stress JSON receipt must remain outside the disposable checkout")
    _private_directory(output.parent)
    _save_json(output, receipt)
    receipt["receipt_path"] = str(output)
    _save_json(output, receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ReproductionFailure as error:
        print(json.dumps({
            "status": "FAIL", "error_type": type(error).__name__,
            "diagnostic": error.diagnostic, "paid_api_calls": 0, "external_writes": 0,
        }, sort_keys=True), file=sys.stderr)
        raise SystemExit(2)
    except (StressFailure, PipelineError, EvidenceError, OSError,
            subprocess.SubprocessError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "FAIL", "error_type": type(error).__name__,
                          "error": str(error), "paid_api_calls": 0,
                          "external_writes": 0}, sort_keys=True), file=sys.stderr)
        raise SystemExit(2)
