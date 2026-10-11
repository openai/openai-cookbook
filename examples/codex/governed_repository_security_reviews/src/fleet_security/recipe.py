"""Portable, owner-governed recurring security-review recipe.

This module executes synthetic fixtures only. Supported product commands are
rendered as inspection-only plans; no scanner, provider or remote API is called.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import fcntl
import math
import os
import re
import secrets
import stat
import time
from collections import Counter
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

from .evidence import AuditLog, EvidenceError, EvidenceSealer
from .inventory import Repository, classify, load_inventory, stable_digest
from .pipeline import ApprovalLedger, FleetPipeline, FleetPolicy, PipelineError, ScanState
from .scanner import SyntheticScanner
from .schema_validation import OFFICIAL_SCHEMA_NAMES, official_schema_directory, validate_schema
from .surface import NativeBulkCampaign, group_native_campaigns
from .threats import ThreatCatalogue


_NAME = re.compile(r"[a-z][a-z0-9-]{1,79}\Z")
_EFFORTS = frozenset({"minimal", "low", "medium", "high", "xhigh"})
_ROLES = frozenset({
    "scope_authorizer", "model_reviewer", "security_reviewer", "patch_reviewer",
    "merge_owner", "deploy_owner", "exception_owner", "policy_owner",
})
_CONFIG_KEYS = frozenset({
    "organisation_id", "organisation_model_version", "organisation_controls",
    "owners", "policy", "periodic_revalidation_hours", "model_selection",
})
_POLICY_KEYS = frozenset({
    "max_concurrent", "max_attempts", "max_scans_per_run", "max_campaign_units",
    "estimated_scan_units", "max_inflight_overshoot_units", "scanner_version",
    "policy_version", "allow_draft_pr", "provider_write_authorised",
    "allow_untrusted_network", "require_human_merge", "require_human_deploy",
})
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_APPROVAL_COMMON = frozenset({"gate", "repository_id", "actor"})
_APPROVAL_REQUIRED = {
    "scope": _APPROVAL_COMMON | {"revision", "service_owner"},
    "threat_model": _APPROVAL_COMMON | {"revision", "context_sha256"},
    "finding_disposition": _APPROVAL_COMMON | {"revision", "finding_id", "target_sha256", "expires_at"},
    "patch": _APPROVAL_COMMON | {"revision", "finding_id", "target_sha256", "expires_at"},
    "exception": _APPROVAL_COMMON | {"revision", "finding_id", "target_sha256", "expires_at"},
    "policy_change": _APPROVAL_COMMON | {"configuration_sha256", "expires_at"},
}
_APPROVAL_OPTIONAL = {
    "scope": frozenset({"expires_at"}),
    "threat_model": frozenset({"expires_at"}),
    "finding_disposition": frozenset({"context_sha256"}),
    "patch": frozenset({"context_sha256"}),
    "exception": frozenset({"context_sha256"}),
    "policy_change": frozenset(),
}


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PipelineError("trusted JSON object contains duplicate fields")
        result[key] = value
    return result


def _normalise_owner_policy(owners: Any) -> dict[str, tuple[str, ...]]:
    if not isinstance(owners, dict) or set(owners) != _ROLES:
        raise PipelineError("trusted owner policy must explicitly configure every human gate")
    normalised: dict[str, tuple[str, ...]] = {}
    for role, values in owners.items():
        if (
            not isinstance(values, list) or not values
            or any(not isinstance(actor, str) or not actor.strip() for actor in values)
            or len(set(values)) != len(values)
        ):
            raise PipelineError("trusted role owners must contain unique named human identities")
        normalised[role] = tuple(values)
    return normalised


def _read_json(path: Path, *, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise PipelineError(f"trusted {label} file is missing or is a symbolic link")
    try:
        document = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_json_object)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PipelineError(f"trusted {label} file is malformed") from error
    if not isinstance(document, dict):
        raise PipelineError(f"trusted {label} must contain one JSON object")
    return document


@dataclass(frozen=True)
class RecipeConfiguration:
    organisation_id: str
    organisation_model_version: str
    organisation_controls: tuple[str, ...]
    owners: Mapping[str, tuple[str, ...]]
    policy: FleetPolicy
    periodic_revalidation_hours: int
    selected_model: str
    selected_effort: str
    model_approved: bool
    model_approval_owner: str

    @classmethod
    def from_file(cls, path: Path) -> "RecipeConfiguration":
        document = _read_json(path, label="recipe configuration")
        unknown = set(document) - _CONFIG_KEYS
        if unknown:
            raise PipelineError("recipe configuration contains unsupported authority or fields")
        organisation = document.get("organisation_id")
        if not isinstance(organisation, str) or not _NAME.fullmatch(organisation):
            raise PipelineError("organisation identity must be a customer-neutral lowercase slug")

        controls = document.get("organisation_controls")
        if not isinstance(controls, list) or not controls or any(
            not isinstance(item, str) or not item for item in controls
        ) or len(set(controls)) != len(controls):
            raise PipelineError("trusted organisation controls must be non-empty and unique")

        normalised_owners = _normalise_owner_policy(document.get("owners"))

        settings = document.get("policy")
        if not isinstance(settings, dict) or set(settings) - _POLICY_KEYS:
            raise PipelineError("trusted fleet policy is absent or contains unsupported controls")
        policy = FleetPolicy(**settings)
        if policy.provider_write_authorised or policy.allow_draft_pr:
            raise PipelineError("portable recipe never grants provider writes or draft publication")

        cadence = document.get("periodic_revalidation_hours")
        if isinstance(cadence, bool) or not isinstance(cadence, int) or not 1 <= cadence <= 8_760:
            raise PipelineError("periodic revalidation must be between one hour and one year")
        version = document.get("organisation_model_version")
        if not isinstance(version, str) or not version:
            raise PipelineError("organisation threat-model version must be pinned")

        selection = document.get("model_selection")
        if not isinstance(selection, dict) or set(selection) != {"model", "effort", "approved", "owner"}:
            raise PipelineError("model, reasoning effort, approval owner and approval state must be explicit")
        if not isinstance(selection["model"], str) or not selection["model"].strip():
            raise PipelineError("native campaign model must be selected explicitly")
        if selection["effort"] not in _EFFORTS:
            raise PipelineError("native campaign reasoning effort must be selected explicitly")
        if not isinstance(selection["approved"], bool):
            raise PipelineError("model approval state must be explicitly boolean")
        if not isinstance(selection["owner"], str) or not selection["owner"]:
            raise PipelineError("model and spending selection requires a named human owner")

        return cls(
            organisation_id=organisation,
            organisation_model_version=version,
            organisation_controls=tuple(controls),
            owners=normalised_owners,
            policy=policy,
            periodic_revalidation_hours=cadence,
            selected_model=selection["model"],
            selected_effort=selection["effort"],
            model_approved=selection["approved"],
            model_approval_owner=selection["owner"],
        )

    @property
    def fingerprint(self) -> str:
        return stable_digest({
            "organisation_id": self.organisation_id,
            "organisation_model_version": self.organisation_model_version,
            "organisation_controls": self.organisation_controls,
            "owners": self.owners,
            "policy": asdict(self.policy),
            "periodic_revalidation_hours": self.periodic_revalidation_hours,
            "model_selection": {
                "model": self.selected_model, "effort": self.selected_effort,
                "approved": self.model_approved, "owner": self.model_approval_owner,
            },
        })


def load_recipe_inventory(path: Path) -> tuple[Repository, ...]:
    document = _read_json(path, label="repository inventory")
    if set(document) != {"repositories"} or not isinstance(document["repositories"], list):
        raise PipelineError("trusted repository inventory requires an explicit repositories list")
    rows = []
    for raw in document["repositories"]:
        if not isinstance(raw, dict):
            raise PipelineError("trusted repository inventory row must be an object")
        row = dict(raw)
        if not isinstance(row.get("repo_id"), str) or not row["repo_id"].startswith("synthetic/"):
            raise PipelineError(
                "offline demonstration accepts only explicit synthetic/ repository identities; "
                "real repositories require a separately authorised live source adapter"
            )
        if not isinstance(row.get("fixture"), str) or not row["fixture"]:
            raise PipelineError(
                "offline demonstration requires an explicit synthetic fixture for every repository; "
                "a clean result must never be inferred from an unrelated default fixture"
            )
        for name in ("dependencies", "controls", "changed_paths"):
            if name in row:
                if not isinstance(row[name], list):
                    raise PipelineError(f"trusted repository {name} must be an explicit JSON list")
                row[name] = tuple(row[name])
        rows.append(row)
    if not rows:
        raise PipelineError("trusted repository inventory cannot be empty")
    return load_inventory(rows)


class DurableRecipeStore:
    """Owner-only, MAC-sealed local state for recurring synthetic review cycles."""

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().absolute()
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.root.is_symlink() or not self.root.is_dir():
            raise EvidenceError("recipe state root must be a real owner-private directory")
        root_status = self.root.stat()
        if stat.S_IMODE(root_status.st_mode) != 0o700:
            raise EvidenceError("recipe state root must be owner-private with mode 0700")
        if root_status.st_uid != os.geteuid():
            raise EvidenceError("recipe state root must belong to its current trusted owner")
        self._lock_path = self.root / ".cycle.lock"
        self._key_path = self.root / ".local-state-key"
        self._state_path = self.root / "state.json"
        # First-ever concurrent processes must agree on one completed signing
        # key; the same bounded lock also serialises every full review cycle.
        with self.cycle_lock():
            if self._key_path.exists():
                if self._key_path.is_symlink() or stat.S_IMODE(self._key_path.stat().st_mode) != 0o600:
                    raise EvidenceError("local recipe signing key must be a private regular 0600 file")
                self._key = self._key_path.read_bytes()
                if len(self._key) != 32:
                    raise EvidenceError("local recipe signing key has an invalid size")
            else:
                if self._state_path.exists():
                    raise EvidenceError("existing recipe state cannot be reopened without its original host key")
                self._key = secrets.token_bytes(32)
                self._write_new_private(self._key_path, self._key)

    @contextmanager
    def cycle_lock(self, *, timeout: float = 30.0, poll_interval: float = 0.01):
        """Boundedly serialise cooperating processes without weakening ownership."""
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or not 0 < timeout <= 60
            or isinstance(poll_interval, bool)
            or not isinstance(poll_interval, (int, float))
            or not math.isfinite(poll_interval)
            or not 0 < poll_interval <= 1
        ):
            raise EvidenceError("recipe cycle lock requires a bounded finite timeout and poll interval")
        try:
            parent = self.root.lstat()
        except OSError as error:
            raise EvidenceError("recipe cycle lock parent cannot be verified") from error
        if (
            not stat.S_ISDIR(parent.st_mode)
            or stat.S_IMODE(parent.st_mode) != 0o700
            or parent.st_uid != os.geteuid()
        ):
            raise EvidenceError("recipe cycle lock requires an owner-private 0700 state directory")
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        if self._lock_path.is_symlink():
            raise EvidenceError("recipe cycle lock must not be a symbolic link")
        try:
            descriptor = os.open(self._lock_path, flags, 0o600)
        except OSError as error:
            raise EvidenceError("recipe cycle lock cannot be opened as a trusted regular file") from error
        acquired = False
        try:
            details = os.fstat(descriptor)
            if (
                not stat.S_ISREG(details.st_mode)
                or stat.S_IMODE(details.st_mode) != 0o600
                or details.st_uid != os.geteuid()
                or details.st_nlink != 1
            ):
                raise EvidenceError("recipe cycle lock must be an owner-private regular 0600 file")
            deadline = time.monotonic() + float(timeout)
            while True:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                    break
                except BlockingIOError:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise EvidenceError("recipe cycle lock acquisition timed out; scanner dispatch refused")
                    time.sleep(min(float(poll_interval), remaining))
                except OSError as error:
                    raise EvidenceError("recipe cycle lock could not be acquired safely") from error
            current = self._lock_path.lstat()
            if stat.S_ISLNK(current.st_mode) or (current.st_dev, current.st_ino) != (details.st_dev, details.st_ino):
                raise EvidenceError("recipe cycle lock identity changed during acquisition")
            yield
        finally:
            try:
                if acquired:
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)

    def sealer(self) -> EvidenceSealer:
        return EvidenceSealer(_key=self._key)

    def read(self) -> dict[str, Any] | None:
        if not self._state_path.exists():
            return None
        if self._state_path.is_symlink() or stat.S_IMODE(self._state_path.stat().st_mode) != 0o600:
            raise EvidenceError("saved recipe state must be owner-private and must not be a symbolic link")
        envelope = _read_json(self._state_path, label="signed recipe state")
        if set(envelope) != {"payload", "signature"} or not isinstance(envelope["payload"], dict):
            raise EvidenceError("saved recipe state envelope is incomplete")
        expected = hmac.new(self._key, _canonical_bytes(envelope["payload"]), hashlib.sha256).hexdigest()
        if not isinstance(envelope["signature"], str) or not hmac.compare_digest(expected, envelope["signature"]):
            raise EvidenceError("saved recipe state signature is invalid; refuse all scanner dispatch")
        return envelope["payload"]

    def write(self, payload: Mapping[str, Any]) -> str:
        copied = json.loads(json.dumps(payload, sort_keys=True))
        digest = hmac.new(self._key, _canonical_bytes(copied), hashlib.sha256).hexdigest()
        self.write_json(self._state_path, {"payload": copied, "signature": digest})
        return stable_digest(copied)

    def write_json(self, path: Path, payload: Mapping[str, Any]) -> None:
        if not path.absolute().is_relative_to(self.root):
            raise EvidenceError("private recipe artifact escaped its trusted state root")
        if path.exists() and path.is_symlink():
            raise EvidenceError("private recipe artifact cannot replace a symbolic link")
        parent = path.parent
        self._ensure_private_directory(parent)
        temporary = parent / f".{path.name}.{secrets.token_hex(8)}.tmp"
        encoded = (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
        self._write_new_private(temporary, encoded)
        try:
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def write_text(self, path: Path, text: str) -> None:
        if not path.absolute().is_relative_to(self.root):
            raise EvidenceError("private recipe context escaped its trusted state root")
        self._ensure_private_directory(path.parent)
        if path.is_symlink():
            raise EvidenceError("private recipe context must remain owner-private")
        temporary = path.parent / f".{path.name}.{secrets.token_hex(8)}.tmp"
        self._write_new_private(temporary, text.encode("utf-8"))
        try:
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def _ensure_private_directory(self, directory: Path) -> None:
        """Create every intermediate child with 0700; Path.mkdir only protects the leaf."""
        try:
            pieces = directory.absolute().relative_to(self.root).parts
        except ValueError as error:
            raise EvidenceError("private recipe directory escaped its trusted state root") from error
        current = self.root
        for piece in pieces:
            current = current / piece
            current.mkdir(mode=0o700, exist_ok=True)
            if current.is_symlink() or not current.is_dir():
                raise EvidenceError("private recipe directory must be real and owner-private")
            if stat.S_IMODE(current.stat().st_mode) != 0o700:
                raise EvidenceError("private recipe directory must have exact owner-private mode 0700")

    @staticmethod
    def _write_new_private(path: Path, data: bytes) -> None:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as output:
                output.write(data)
        except BaseException:
            path.unlink(missing_ok=True)
            raise


class RecurringSecurityRecipe:
    """Repeatable customer-neutral sample; all live/product actions stay disabled."""

    def __init__(
        self, *, configuration: RecipeConfiguration, inventory: tuple[Repository, ...],
        approvals_path: Path, state_directory: Path, docker: bool = False,
        clock: Any = None,
        schema_directory: Path | None = None,
    ) -> None:
        self.configuration = configuration
        self.inventory = inventory
        self.approvals_path = approvals_path
        self.schema_directory = schema_directory if schema_directory is not None else official_schema_directory()
        self.store = DurableRecipeStore(state_directory)
        self.docker = docker
        self.clock = clock or (lambda: int(time.time()))

    @classmethod
    def from_files(
        cls, *, configuration_path: Path, inventory_path: Path, approvals_path: Path,
        state_directory: Path, docker: bool = False, clock: Any = None,
    ) -> "RecurringSecurityRecipe":
        configuration = RecipeConfiguration.from_file(configuration_path)
        inventory = load_recipe_inventory(inventory_path)
        # Resolve and validate official contracts before creating a signing key,
        # writing a campaign, or dispatching even one synthetic repository.
        schema_directory = official_schema_directory()
        return cls(
            configuration=configuration,
            inventory=inventory,
            approvals_path=approvals_path,
            state_directory=state_directory,
            docker=docker,
            clock=clock,
            schema_directory=schema_directory,
        )

    def cycle(self) -> dict[str, Any]:
        with self.store.cycle_lock():
            return self._cycle_locked()

    def _cycle_locked(self) -> dict[str, Any]:
        previous = self.store.read()
        if previous is not None and previous.get("organisation_id") != self.configuration.organisation_id:
            raise PipelineError("saved recipe state belongs to a different trusted organisation")
        previous_audit_digest, previous_audit_events = self._verify_durable_audit(previous)

        catalogue = ThreatCatalogue(
            organisation_controls=self.configuration.organisation_controls,
            version=self.configuration.organisation_model_version,
        )
        approvals = ApprovalLedger(self._trusted_approval_owners(previous), clock=self.clock)
        scanner = SyntheticScanner(isolated=self.docker)
        flow = FleetPipeline(
            policy=self.configuration.policy, approvals=approvals, catalogue=catalogue,
            scanner=scanner, sealer=self.store.sealer(), clock=self.clock,
        )
        self._apply_approvals(flow)
        if previous is not None and previous.get("configuration_hash") != self.configuration.fingerprint:
            approved = approvals.actor("policy_change", "fleet", self.configuration.fingerprint)
            if approved is None:
                raise PipelineError("changed trusted recipe policy requires named policy-owner approval")
            flow.audit.append(
                "configuration_change_approved", "fleet", actor=approved,
                previous_configuration_sha256=previous["configuration_hash"],
                configuration_sha256=self.configuration.fingerprint,
            )

        now = self.clock()
        prior_times = self._restore(flow, previous)
        revalidation_due: list[str] = []
        for repo_id, scanned_at in prior_times.items():
            if now - scanned_at >= self.configuration.periodic_revalidation_hours * 3_600:
                flow.states.pop(repo_id, None)
                revalidation_due.append(repo_id)

        quarantined = {
            record.repo_id
            for record in self.inventory
            if (
                (state := flow.states.get(record.repo_id)) is not None
                and state.status == "failed_safe_abstention"
                and state.idempotency_key == flow._idempotency_key(record, catalogue.assign(record))
            )
        }
        eligible = tuple(
            repo for repo in self.inventory
            if repo.repo_id not in quarantined
            and approvals.actor("scope", repo.repo_id, flow.scope_target(repo)) is not None
            and (
                not catalogue.assign(repo).requires_human_acceptance
                or approvals.actor("threat_model", repo.repo_id, catalogue.assign(repo).effective_model_hash)
                is not None
            )
        )
        run_number = int(previous.get("run_number", 0)) + 1 if previous else 1
        campaign_plans = self._write_campaign_plans(eligible, catalogue)
        result = flow.run(tuple(record for record in self.inventory if record.repo_id not in quarantined))
        for repo_id in sorted(quarantined):
            result["records"][repo_id] = flow.states[repo_id].receipt()
            flow.audit.append("unchanged_safe_abstention_quarantined", repo_id)
        result["records"] = {key: result["records"][key] for key in sorted(result["records"])}
        result["inventory_count"] = len(self.inventory)
        result["audit_valid"] = flow.audit.verify()
        schema_count = self._persist_evidence(flow)
        scanned_at = {
            repo_id: (now if scanner.invocations.get(repo_id) else prior_times.get(repo_id, now))
            for repo_id, state in flow.states.items() if state.evidence is not None
        }
        payload = {
            "format": "governed-security-recipe/v1",
            "organisation_id": self.configuration.organisation_id,
            "configuration_hash": self.configuration.fingerprint,
            "trusted_owner_policy": {
                role: list(self.configuration.owners[role]) for role in sorted(_ROLES)
            },
            "run_number": run_number,
            "previous_run_hash": previous.get("last_run_hash", "0" * 64) if previous else "0" * 64,
            "states": [asdict(flow.states[key]) for key in sorted(flow.states)],
            "scanned_at": scanned_at,
        }
        audit_path, audit_digest, current_audit_events = self._persist_durable_audit(
            flow.audit,
            run_number=run_number,
            previous_audit_digest=previous_audit_digest,
        )
        payload["audit_tail_digest"] = audit_digest
        payload["audit_run_count"] = run_number
        payload["audit_event_count"] = previous_audit_events + current_audit_events
        payload["last_run_hash"] = stable_digest(payload)
        try:
            state_digest = self.store.write(payload)
        except BaseException:
            # Remove an uncommitted event file only when the authenticated
            # checkpoint is provably still the prior checkpoint. Ambiguous
            # partial commits are retained and fail closed on the next run.
            try:
                unchanged = self.store.read() == previous
            except (EvidenceError, OSError, PipelineError):
                unchanged = False
            if unchanged:
                audit_path.unlink(missing_ok=True)
            raise
        receipt = {
            "recipe": "customer-neutral governed recurring repository security review",
            "execution_mode": "synthetic_restricted_docker" if self.docker else "synthetic_offline_not_sandboxed",
            "organisation_id": self.configuration.organisation_id,
            "run_number": run_number,
            "inventory_count": len(self.inventory),
            "approved_dispatch_candidates": len(eligible),
            "native_campaign_plans": campaign_plans,
            "decision_states": dict(sorted(Counter(row["status"] for row in result["records"].values()).items())),
            "records": result["records"],
            "scanner_invocations": result["scanner_invocations"],
            "admitted_jobs": result["admitted_jobs"],
            "attempted_repositories": result["attempted_repositories"],
            "scanner_attempts_by_repository": result["scanner_attempts_by_repository"],
            "retry_attempts": result["retry_attempts"],
            "transient_retry_events": result["transient_retry_events"],
            "max_active_workers": result["max_active_workers"],
            "max_concurrent_policy": self.configuration.policy.max_concurrent,
            "consumed_synthetic_units": result["consumed_units"],
            "max_reserved_synthetic_units": result["max_observed_reserved_units"],
            "campaign_budget_synthetic_units": self.configuration.policy.max_campaign_units,
            "revalidation_due": sorted(revalidation_due),
            "quarantined_unchanged": sorted(quarantined),
            "official_schema_validated_synthetic_documents": schema_count,
            "restricted_docker_receipts": len(scanner.isolation_receipts),
            "audit_valid": result["audit_valid"],
            "durable_audit_valid": True,
            "durable_audit_event_count": current_audit_events,
            "durable_audit_cumulative_event_count": payload["audit_event_count"],
            "durable_audit_tail_digest": audit_digest,
            "durable_state_digest": state_digest,
            "previous_run_hash": payload["previous_run_hash"],
            "selected_model": self.configuration.selected_model,
            "selected_effort": self.configuration.selected_effort,
            "customer_model_approval_verified": self.configuration.model_approved,
            "live_product_execution": False,
            "paid_api_calls": 0,
            "external_writes": 0,
            "automatic_pr_merge_or_deploy": False,
        }
        self.store.write_json(self.store.root / "runs" / f"run-{run_number:04d}.json", receipt)
        return receipt

    def _verify_durable_audit(self, previous: dict[str, Any] | None) -> tuple[str, int]:
        """Authenticate every historical event before any scanner is constructed."""
        directory = self.store.root / "audit"
        if previous is None:
            if directory.exists() or directory.is_symlink():
                raise EvidenceError("orphaned durable audit history has no authenticated checkpoint")
            return "0" * 64, 0

        run_count = previous.get("audit_run_count")
        event_count = previous.get("audit_event_count")
        anchor = previous.get("audit_tail_digest")
        if (
            isinstance(run_count, bool)
            or not isinstance(run_count, int)
            or run_count < 1
            or run_count != previous.get("run_number")
            or isinstance(event_count, bool)
            or not isinstance(event_count, int)
            or event_count < run_count
            or not isinstance(anchor, str)
            or re.fullmatch(r"[0-9a-f]{64}", anchor) is None
        ):
            raise EvidenceError("legacy or malformed signed recipe state has no trusted durable audit anchor")

        try:
            details = directory.lstat()
        except OSError as error:
            raise EvidenceError("authenticated durable audit directory is missing") from error
        if (
            not stat.S_ISDIR(details.st_mode)
            or stat.S_IMODE(details.st_mode) != 0o700
            or details.st_uid != os.geteuid()
        ):
            raise EvidenceError("durable audit directory must be owner-private 0700 and must not be a symbolic link")

        expected_names = {f"run-{number:04d}.json" for number in range(1, run_count + 1)}
        try:
            actual_names = {entry.name for entry in directory.iterdir()}
        except OSError as error:
            raise EvidenceError("durable audit history cannot be inspected safely") from error
        if actual_names != expected_names:
            raise EvidenceError("durable audit history is missing, rolled back, or contains uncommitted events")

        prior_digest = "0" * 64
        total_events = 0
        keys = {
            "format", "organisation_id", "run_number", "previous_audit_digest",
            "event_count", "events", "audit_digest",
        }
        forbidden_metadata = {"secret", "token", "api_key", "credential", "source", "prompt"}
        for number in range(1, run_count + 1):
            path = directory / f"run-{number:04d}.json"
            try:
                attributes = path.lstat()
                if (
                    not stat.S_ISREG(attributes.st_mode)
                    or stat.S_IMODE(attributes.st_mode) != 0o600
                    or attributes.st_uid != os.geteuid()
                    or attributes.st_nlink != 1
                ):
                    raise EvidenceError("durable audit event file must be an owner-private regular 0600 file")
                document = json.loads(path.read_text(encoding="utf-8"))
            except EvidenceError:
                raise
            except (OSError, UnicodeError, json.JSONDecodeError) as error:
                raise EvidenceError("durable audit event history is unreadable or malformed") from error
            if not isinstance(document, dict) or set(document) != keys:
                raise EvidenceError("durable audit event envelope is incomplete or contains untrusted fields")
            events = document.get("events")
            if (
                document.get("format") != "governed-security-audit/v1"
                or document.get("organisation_id") != self.configuration.organisation_id
                or document.get("run_number") != number
                or document.get("previous_audit_digest") != prior_digest
                or not isinstance(events, list)
                or not events
                or document.get("event_count") != len(events)
            ):
                raise EvidenceError("durable audit run identity, continuity, or event count is invalid")
            if any(
                not isinstance(event, dict)
                or not isinstance(event.get("metadata"), dict)
                or any(any(marker in key.casefold() for marker in forbidden_metadata)
                       for key in event["metadata"] if isinstance(key, str))
                for event in events
            ):
                raise EvidenceError("durable audit event metadata contains unsafe or malformed fields")
            try:
                valid = AuditLog().verify(tuple(events))
            except (KeyError, TypeError, ValueError) as error:
                raise EvidenceError("durable audit event hash chain is malformed") from error
            if not valid:
                raise EvidenceError("durable audit event hash chain is invalid; refuse scanner dispatch")
            supplied = document["audit_digest"]
            unsigned = {key: value for key, value in document.items() if key != "audit_digest"}
            expected = stable_digest(unsigned)
            if not isinstance(supplied, str) or not hmac.compare_digest(supplied, expected):
                raise EvidenceError("durable audit run digest is invalid; refuse scanner dispatch")
            prior_digest = supplied
            total_events += len(events)

        if not hmac.compare_digest(prior_digest, anchor) or total_events != event_count:
            raise EvidenceError("durable audit history does not match its authenticated signed-state anchor")
        return prior_digest, total_events

    def _persist_durable_audit(
        self,
        audit: AuditLog,
        *,
        run_number: int,
        previous_audit_digest: str,
    ) -> tuple[Path, str, int]:
        events = list(audit.events)
        if not events or not audit.verify(tuple(events)):
            raise EvidenceError("refuse to persist an empty or invalid durable audit event chain")
        document: dict[str, Any] = {
            "format": "governed-security-audit/v1",
            "organisation_id": self.configuration.organisation_id,
            "run_number": run_number,
            "previous_audit_digest": previous_audit_digest,
            "event_count": len(events),
            "events": events,
        }
        digest = stable_digest(document)
        document["audit_digest"] = digest
        path = self.store.root / "audit" / f"run-{run_number:04d}.json"
        if path.exists() or path.is_symlink():
            raise EvidenceError("durable audit run already exists; refuse to replace prior evidence")
        self.store.write_json(path, document)
        return path, digest, len(events)

    def _trusted_approval_owners(self, previous: Mapping[str, Any] | None) -> dict[str, tuple[str, ...]]:
        """Only the prior MAC-sealed policy owners can authorise a configuration transition."""
        owners = dict(self.configuration.owners)
        if previous is None:
            return owners
        prior_hash = previous.get("configuration_hash")
        try:
            prior_owners = _normalise_owner_policy(previous.get("trusted_owner_policy"))
        except PipelineError as error:
            raise EvidenceError(
                "legacy or malformed signed recipe state has no trusted previous owner policy; "
                "explicit migration is required"
            ) from error
        if not isinstance(prior_hash, str) or not _SHA256.fullmatch(prior_hash):
            raise EvidenceError("signed recipe state has no valid prior configuration identity")
        if prior_hash == self.configuration.fingerprint and prior_owners != owners:
            raise EvidenceError("signed recipe owner policy contradicts its configuration identity")
        owners["policy_owner"] = prior_owners["policy_owner"]
        return owners

    def _apply_approvals(self, flow: FleetPipeline) -> None:
        document = _read_json(self.approvals_path, label="named-human approval")
        if set(document) != {"approvals"} or not isinstance(document["approvals"], list):
            raise PipelineError("trusted approval document must contain explicit named-human approvals")
        records = {item.repo_id: item for item in self.inventory}
        seen: set[tuple[str, str, str]] = set()
        for entry in document["approvals"]:
            if not isinstance(entry, dict):
                raise PipelineError("trusted human approval must be a JSON object")
            gate = entry.get("gate")
            actor = entry.get("actor")
            repo_id = entry.get("repository_id")
            if not isinstance(gate, str) or gate not in _APPROVAL_REQUIRED:
                raise PipelineError("human approval gate is unsupported or would grant external authority")
            required = _APPROVAL_REQUIRED[gate]
            if not required.issubset(entry) or set(entry) - required - _APPROVAL_OPTIONAL[gate]:
                raise PipelineError("human approval has missing required fields or unsupported constraints")
            if not isinstance(actor, str) or not actor.strip() or not isinstance(repo_id, str) or not repo_id:
                raise PipelineError("human approval requires named actor and repository identities")
            expires = entry.get("expires_at")
            if "expires_at" in entry and (
                isinstance(expires, bool) or not isinstance(expires, int) or expires <= self.clock()
            ):
                raise PipelineError("human approval expiration must be a future whole-second deadline")
            if gate == "policy_change":
                target = self.configuration.fingerprint
                if repo_id != "fleet" or entry["configuration_sha256"] != target:
                    raise PipelineError("policy approval must bind the exact full trusted configuration digest")
            else:
                record = records.get(repo_id)
                if record is None or entry.get("revision") != record.commit_sha:
                    raise PipelineError("human approval must bind one current repository and immutable revision")
            if gate == "scope":
                if entry.get("service_owner") != record.owner:
                    raise PipelineError("scope approval must bind the currently named repository owner")
                target = flow.scope_target(record)
            elif gate == "threat_model":
                target = flow.catalogue.assign(record).effective_model_hash
                if entry.get("context_sha256") != target:
                    raise PipelineError("threat-model approval must bind the current effective context")
            elif gate in {"finding_disposition", "patch", "exception"}:
                finding = entry.get("finding_id")
                if not isinstance(finding, str) or not finding.startswith("csf_"):
                    raise PipelineError("finding approval requires an exact trusted finding identity")
                target = flow.finding_target(record, finding)
                if entry["target_sha256"] != target:
                    raise PipelineError("finding approval must bind its exact current context, scanner and policy target")
                if "context_sha256" in entry and entry["context_sha256"] != flow.catalogue.assign(record).effective_model_hash:
                    raise PipelineError("finding approval contains a stale or contradictory effective-context constraint")
            identity = (gate, repo_id, target)
            if identity in seen:
                raise PipelineError("human approval document contains duplicate grants for one exact target")
            seen.add(identity)
            if gate == "exception":
                flow.approvals.approve_exception(repo_id, target, actor, expires_at=expires)
                continue
            flow.approvals.approve(gate, repo_id, target, actor, expires_at=expires)

    def _restore(self, flow: FleetPipeline, previous: Mapping[str, Any] | None) -> dict[str, int]:
        if previous is None:
            return {}
        if previous.get("format") != "governed-security-recipe/v1":
            raise EvidenceError("saved recipe state format is unsupported")
        times = previous.get("scanned_at")
        rows = previous.get("states")
        if not isinstance(times, dict) or not isinstance(rows, list):
            raise EvidenceError("saved recipe state inventory is malformed")
        for row in rows:
            if not isinstance(row, dict):
                raise EvidenceError("saved recipe scan state is malformed")
            material = dict(row)
            material["current_findings"] = tuple(material.get("current_findings", ()))
            material["fresh_findings"] = tuple(material.get("fresh_findings", ()))
            try:
                state = ScanState(**material)
            except (TypeError, ValueError) as error:
                raise EvidenceError("saved recipe scan state cannot be safely restored") from error
            if state.evidence is not None:
                self._verify_persisted_evidence(flow, state)
                if any(state.evidence[name].get("synthetic") is not True for name in (
                    "findings.json", "coverage.json", "scan-manifest.json"
                )):
                    raise EvidenceError("saved recipe evidence lacks explicit synthetic provenance")
                flow.registry.admit(state.current_findings)
            flow.states[state.repository_id] = state
        if any(isinstance(value, bool) or not isinstance(value, int) for value in times.values()):
            raise EvidenceError("saved recipe scan freshness timestamps are invalid")
        return dict(times)

    def _verify_persisted_evidence(self, flow: FleetPipeline, state: ScanState) -> None:
        """Bind independently stored evidence files to the authenticated checkpoint."""
        if state.evidence is None or not isinstance(state.reviewed_revision, str):
            raise EvidenceError("saved recipe evidence does not identify a reviewed revision")
        slug = re.sub(r"[^a-z0-9-]+", "-", state.repository_id.casefold()).strip("-")
        directory = self.store.root / "evidence" / slug / state.reviewed_revision[:12]
        if directory.is_symlink() or not directory.is_dir():
            raise EvidenceError("saved recipe evidence directory is missing or is a symbolic link")
        if stat.S_IMODE(directory.stat().st_mode) & 0o077:
            raise EvidenceError("saved recipe evidence directory is not owner-private")

        restored: dict[str, Any] = {}
        for name in (*[f"{item}.json" for item in OFFICIAL_SCHEMA_NAMES], "report.md"):
            path = directory / name
            if path.is_symlink() or not path.is_file():
                raise EvidenceError(f"saved recipe evidence artifact is missing or unsafe: {name}")
            if stat.S_IMODE(path.stat().st_mode) != 0o600:
                raise EvidenceError(f"saved recipe evidence artifact is not owner-private: {name}")
            if name == "report.md":
                try:
                    restored[name] = path.read_text(encoding="utf-8")
                except (OSError, UnicodeError) as error:
                    raise EvidenceError("saved recipe evidence report is unreadable") from error
            else:
                try:
                    restored[name] = _read_json(path, label="persisted scanner evidence")
                except PipelineError as error:
                    raise EvidenceError(f"saved recipe evidence artifact is malformed: {name}") from error
            if restored[name] != state.evidence.get(name):
                raise EvidenceError(f"saved recipe evidence differs from its signed checkpoint: {name}")
        flow.sealer.verify(restored)

    def _write_campaign_plans(
        self, repositories: tuple[Repository, ...], catalogue: ThreatCatalogue,
    ) -> list[dict[str, Any]]:
        if not repositories:
            return []
        org_context = self.store.root / "context" / "organisation.md"
        self.store.write_text(
            org_context,
            "# Trusted organisation security controls\n\n"
            + "\n".join(f"- {control}" for control in self.configuration.organisation_controls)
            + "\n",
        )
        plans: list[dict[str, Any]] = []
        for campaign in group_native_campaigns(
            repositories, catalogue,
            workers=self.configuration.policy.max_concurrent,
            max_attempts=self.configuration.policy.max_attempts,
        ):
            slug = re.sub(r"[^a-z0-9-]+", "-", campaign.archetype.casefold()).strip("-")
            archetype_path = self.store.root / "context" / "archetypes" / f"{slug}.md"
            self.store.write_text(archetype_path, f"# Trusted workload archetype\n\n`{campaign.archetype}`\n")
            local_campaign = NativeBulkCampaign(
                archetype=campaign.archetype,
                rows=campaign.rows,
                knowledge_base_paths=(str(org_context), str(archetype_path)),
                workers=campaign.workers,
                max_attempts=campaign.max_attempts,
            )
            csv_path = self.store.root / "campaigns" / f"{slug}.csv"
            self.store.write_text(csv_path, local_campaign.csv_text())
            output = self.store.root / "planned-product-output" / slug
            command = local_campaign.command(csv_path=str(csv_path), output_dir=str(output)) + (
                "--model", self.configuration.selected_model,
                "--effort", self.configuration.selected_effort,
            )
            plans.append({
                "archetype": campaign.archetype,
                "repository_count": len(campaign.rows),
                "csv_path": str(csv_path),
                "knowledge_base_paths": [str(org_context), str(archetype_path)],
                "command": list(command),
                "command_executed": False,
                "customer_model_approval_verified": self.configuration.model_approved,
                "native_campaign_has_hard_cost_flag": False,
            })
        return plans

    def _persist_evidence(self, flow: FleetPipeline) -> int:
        root = self.schema_directory
        schemas = {
            name: json.loads((root / f"{name}.schema.json").read_text(encoding="utf-8"))
            for name in OFFICIAL_SCHEMA_NAMES
        }
        validated = 0
        for state in flow.states.values():
            if state.evidence is None:
                continue
            slug = re.sub(r"[^a-z0-9-]+", "-", state.repository_id.casefold()).strip("-")
            directory = self.store.root / "evidence" / slug / state.reviewed_revision[:12]
            for name in OFFICIAL_SCHEMA_NAMES:
                document = state.evidence[f"{name}.json"]
                if document.get("synthetic") is not True:
                    raise EvidenceError("portable recipe output lacks explicit synthetic provenance")
                validate_schema(document, schemas[name])
                self.store.write_json(directory / f"{name}.json", document)
                validated += 1
            self.store.write_text(directory / "report.md", str(state.evidence["report.md"]))
        return validated
