"""Human-governed synthetic fleet control plane; external writes are not implemented."""
from __future__ import annotations

import fnmatch
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Iterable, Mapping

from .evidence import AuditLog, EvidenceError, EvidenceSealer, FindingRegistry
from .inventory import Repository, classify, load_inventory, stable_digest
from .scanner import RETRY_REASON_CODES, ScanFailure, SyntheticScanner
from .threats import ThreatAssignment, ThreatCatalogue


class PipelineError(RuntimeError):
    """Trusted authority, approval, policy, or campaign control failed closed."""


_GATE_ROLES = {
    "scope": "scope_authorizer",
    "threat_model": "model_reviewer",
    "finding_disposition": "security_reviewer",
    "patch": "patch_reviewer",
    "merge": "merge_owner",
    "deploy": "deploy_owner",
    "exception": "exception_owner",
    "policy_change": "policy_owner",
}


@dataclass(frozen=True)
class FleetPolicy:
    max_concurrent: int = 4
    max_attempts: int = 2
    max_scans_per_run: int = 20
    max_campaign_units: int = 500
    estimated_scan_units: int = 5
    max_inflight_overshoot_units: int = 2
    scanner_version: str = "synthetic-security-adapter/1.0"
    policy_version: str = "synthetic-policy-v1"
    allow_draft_pr: bool = False
    provider_write_authorised: bool = False
    allow_untrusted_network: bool = False
    require_human_merge: bool = True
    require_human_deploy: bool = True

    def __post_init__(self) -> None:
        bounds = {
            "max_concurrent": (1, 32),
            "max_attempts": (1, 5),
            "max_scans_per_run": (1, 20_000),
            "max_campaign_units": (1, 1_000_000),
            "estimated_scan_units": (1, 100_000),
            "max_inflight_overshoot_units": (0, 100_000),
        }
        for name, (minimum, maximum) in bounds.items():
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
                raise PipelineError(f"fleet policy {name} is outside its trusted bounds")
        if not self.policy_version or not self.scanner_version:
            raise PipelineError("fleet policy and scanner versions must be pinned")
        if not self.require_human_merge or not self.require_human_deploy:
            raise PipelineError("human acceptance, merge and deployment cannot be disabled")
        if self.allow_untrusted_network:
            raise PipelineError("network access for untrusted repository execution is prohibited")
        if self.provider_write_authorised and not self.allow_draft_pr:
            raise PipelineError("provider write authorisation requires an explicit draft-PR policy")

    @property
    def worst_case_reservation(self) -> int:
        return self.max_attempts * (self.estimated_scan_units + self.max_inflight_overshoot_units)


class ApprovalLedger:
    """Trusted host approvals; scanner output and repository contents cannot grant authority."""

    def __init__(
        self, authorised_owners: Mapping[str, frozenset[str] | set[str] | tuple[str, ...]],
        *, clock: callable | None = None,
    ) -> None:
        self._owners = {role: frozenset(names) for role, names in authorised_owners.items()}
        self._grants: dict[tuple[str, str, str], tuple[str, int | None]] = {}
        self._exceptions: dict[tuple[str, str], tuple[str, int]] = {}
        self._lock = threading.Lock()
        self._clock = clock or (lambda: int(time.time()))
        if any(not role or any(not isinstance(name, str) or not name for name in names)
               for role, names in self._owners.items()):
            raise PipelineError("trusted owner/RACI policy is invalid")

    def approve(
        self, gate: str, repo_id: str, target: str, actor: str,
        *, expires_at: int | None = None,
    ) -> None:
        role = _GATE_ROLES.get(gate)
        if role is None or actor not in self._owners.get(role, frozenset()):
            raise PipelineError(f"named owner is not authorised for the {gate} human gate")
        if not repo_id or not target:
            raise PipelineError("human approval must identify its repository and exact target")
        if expires_at is not None and (
            isinstance(expires_at, bool) or not isinstance(expires_at, int) or expires_at <= self._clock()
        ):
            raise PipelineError("human approval expiration must be a future whole-second deadline")
        with self._lock:
            self._grants[(gate, repo_id, target)] = (actor, expires_at)

    def actor(self, gate: str, repo_id: str, target: str) -> str | None:
        with self._lock:
            grant = self._grants.get((gate, repo_id, target))
        if grant is None:
            return None
        actor, expires_at = grant
        return None if expires_at is not None and self._clock() >= expires_at else actor

    def authorised_actor(self, gate: str, actor: str) -> bool:
        role = _GATE_ROLES.get(gate)
        return role is not None and actor in self._owners.get(role, frozenset())

    def require(self, gate: str, repo_id: str, target: str) -> str:
        actor = self.actor(gate, repo_id, target)
        if actor is None:
            raise PipelineError(f"{gate} requires explicit named-human approval before proceeding")
        return actor

    def approve_exception(self, repo_id: str, finding_id: str, actor: str, *, expires_at: int) -> None:
        if not isinstance(expires_at, int) or expires_at <= 0:
            raise PipelineError("finding exception requires a finite explicit expiration")
        self.approve("exception", repo_id, finding_id, actor)
        with self._lock:
            self._exceptions[(repo_id, finding_id)] = (actor, expires_at)

    def active_exception(self, repo_id: str, finding_id: str, *, now: int) -> str | None:
        with self._lock:
            exception = self._exceptions.get((repo_id, finding_id))
        if exception is None or now >= exception[1]:
            return None
        return exception[0]


@dataclass
class ScanState:
    repository_id: str
    idempotency_key: str
    boundary_hash: str
    status: str
    reviewed_revision: str
    attempts: int = 0
    reason: str = ""
    evidence: dict[str, Any] | None = None
    current_findings: tuple[dict[str, Any], ...] = ()
    fresh_findings: tuple[dict[str, Any], ...] = ()
    duplicates: int = 0
    route: str = "review_packet"
    named_reviewers: dict[str, str] = field(default_factory=dict)

    def receipt(self) -> dict[str, Any]:
        return {
            "repository_id": self.repository_id,
            "idempotency_key": self.idempotency_key,
            "boundary_hash": self.boundary_hash,
            "status": self.status,
            "reviewed_revision": self.reviewed_revision,
            "attempts": self.attempts,
            "reason": self.reason,
            "fresh_findings": len(self.fresh_findings),
            "current_findings": len(self.current_findings),
            "duplicates": self.duplicates,
            "route": self.route,
            "named_reviewers": deepcopy(self.named_reviewers),
            "external_pr_created": False,
            "merge_performed": False,
            "deployment_performed": False,
        }


class FleetPipeline:
    """Scope gates run before scanner invocation; all consequential outcomes stop at humans."""

    def __init__(
        self, *, policy: FleetPolicy, approvals: ApprovalLedger,
        catalogue: ThreatCatalogue | None = None,
        scanner: SyntheticScanner | None = None,
        sealer: EvidenceSealer | None = None,
        audit: AuditLog | None = None,
        clock: callable | None = None,
    ) -> None:
        self.policy = policy
        self.approvals = approvals
        self.catalogue = catalogue or ThreatCatalogue()
        self.scanner = scanner or SyntheticScanner()
        self.sealer = sealer or EvidenceSealer()
        self.audit = audit or AuditLog()
        self.registry = FindingRegistry()
        self._clock = clock or (lambda: 1_787_140_800)
        self.states: dict[str, ScanState] = {}
        self._cancelled: set[str] = set()
        self._budget_lock = threading.Lock()
        self.reserved_units = 0
        self.consumed_units = 0
        self.max_observed_reserved_units = 0

    def cancel(self, repository_id: str, *, actor: str) -> None:
        if not actor or not repository_id:
            raise PipelineError("cancellation requires a named human owner and repository")
        if not self.approvals.authorised_actor("scope", actor):
            raise PipelineError("cancellation requires a trusted named scope owner")
        self._cancelled.add(repository_id)
        self.audit.append("cancelled", repository_id, actor=actor)

    def apply_policy(self, updated: FleetPolicy, *, actor: str) -> None:
        target = stable_digest(asdict(updated))
        approved = self.approvals.require("policy_change", "fleet", target)
        if actor != approved:
            raise PipelineError("policy change actor differs from its named trusted approver")
        self.policy = updated
        self.audit.append("policy_changed", "fleet", actor=actor, policy_version=updated.policy_version)

    def run(self, repositories: Iterable[Repository]) -> dict[str, Any]:
        inventory = load_inventory(repositories)
        audit_start = len(self.audit.events)
        results: dict[str, dict[str, Any]] = {}
        candidates: list[tuple[Repository, ThreatAssignment, str]] = []
        for repository in inventory:
            assignment = self.catalogue.assign(repository)
            key = self._idempotency_key(repository, assignment)
            previous = self.states.get(repository.repo_id)
            if repository.repo_id in self._cancelled:
                results[repository.repo_id] = self._stop(repository, key, "cancelled", "owner cancelled campaign")
                continue
            if self.approvals.actor("scope", repository.repo_id, self.scope_target(repository)) is None:
                results[repository.repo_id] = self._stop(repository, key, "awaiting_scope_approval", "scope gate was not approved")
                continue
            if assignment.requires_human_acceptance and (
                self.approvals.actor("threat_model", repository.repo_id, assignment.effective_model_hash) is None
            ):
                results[repository.repo_id] = self._stop(repository, key, "awaiting_threat_model_approval", "high-risk threat model was not accepted")
                continue
            if previous and previous.idempotency_key == key and previous.evidence:
                self.sealer.verify(previous.evidence)
                self._resolve_review(repository, previous)
                results[repository.repo_id] = previous.receipt()
                self.audit.append("cached_evidence_reused", repository.repo_id, evidence_digest=key)
                continue
            if previous and previous.evidence and previous.boundary_hash == repository.boundary_hash and repository.changed_paths and (
                not any(self._security_relevant(path) for path in repository.changed_paths)
            ) and previous.idempotency_key == self._idempotency_key(
                replace(repository, commit_sha=previous.reviewed_revision), assignment,
            ):
                # Only the revision may differ. A docs-only path list cannot
                # override changed context, scanner/policy versions, failed
                # predecessor work or unauthenticated evidence.
                self.sealer.verify(previous.evidence)
                review = deepcopy(previous)
                review.named_reviewers = {
                    "scope": self.approvals.require("scope", repository.repo_id, self.scope_target(repository)),
                }
                if assignment.requires_human_acceptance:
                    review.named_reviewers["threat_model"] = self.approvals.require(
                        "threat_model", repository.repo_id, assignment.effective_model_hash,
                    )
                review.fresh_findings = ()
                review.duplicates = 0
                self._resolve_review(repository, review)
                receipt = review.receipt()
                receipt.update({
                    "status": "skipped_unchanged_security_scope",
                    "scheduling_status": "skipped_unchanged_security_scope",
                    "review_status": review.status,
                    "review_reason": review.reason,
                    "reason": "only non-security documentation changed; known findings still require current review",
                    "reviewed_revision": previous.reviewed_revision,
                    "requested_revision": repository.commit_sha,
                    "requested_idempotency_key": key,
                    "reused_evidence_idempotency_key": previous.idempotency_key,
                    "new_scan_performed": False,
                })
                self.audit.append(
                    "skipped_unchanged_security_scope", repository.repo_id,
                    reviewed_revision=previous.reviewed_revision,
                    requested_revision=repository.commit_sha,
                    finding_count=len(review.current_findings), review_status=review.status,
                )
                results[repository.repo_id] = receipt
                continue
            candidates.append((repository, assignment, key))

        admitted: list[tuple[Repository, ThreatAssignment, str]] = []
        for repository, assignment, key in candidates:
            if len(admitted) >= self.policy.max_scans_per_run:
                results[repository.repo_id] = self._stop(repository, key, "deferred_rate_limit", "host campaign rate budget reached")
                continue
            if not self._reserve():
                results[repository.repo_id] = self._stop(repository, key, "deferred_budget", "host hard admission budget would be exceeded")
                continue
            admitted.append((repository, assignment, key))

        with ThreadPoolExecutor(max_workers=self.policy.max_concurrent, thread_name_prefix="synthetic-fleet") as pool:
            futures = {
                pool.submit(self._execute, repository, assignment, key): repository
                for repository, assignment, key in admitted
            }
            for future in as_completed(futures):
                repository = futures[future]
                try:
                    state = future.result()
                finally:
                    self._release_unused()
                self.states[repository.repo_id] = state
                results[repository.repo_id] = state.receipt()

        # Count this run's host-authorised calls, not restored ScanState.attempts
        # or the scanner's lifetime counter. A scheduled retry may be cancelled
        # before the next call; only a started call counts as an actual retry.
        current_events = self.audit.events[audit_start:]
        attempted = Counter(
            event["repositoryId"] for event in current_events
            if event["event"] == "scan_attempt_started"
        )
        retry_events = sorted((
            {
                "repository_id": event["repositoryId"],
                "failed_attempt": event["metadata"]["attempt"],
                "reason_code": event["metadata"]["reason_code"],
            }
            for event in current_events if event["event"] == "transient_retry"
        ), key=lambda event: (event["repository_id"], event["failed_attempt"]))
        return {
            "records": {key: results[key] for key in sorted(results)},
            "inventory_count": len(inventory),
            "admitted": len(admitted),
            "admitted_jobs": len(admitted),
            "attempted_repositories": len(attempted),
            "scanner_attempts_by_repository": dict(sorted(attempted.items())),
            "retry_attempts": sum(count - 1 for count in attempted.values()),
            "transient_retry_events": retry_events,
            "consumed_units": self.consumed_units,
            "reserved_units": self.reserved_units,
            "max_observed_reserved_units": self.max_observed_reserved_units,
            "scanner_invocations": sum(self.scanner.invocations.values()),
            "max_active_workers": self.scanner.max_active_workers,
            "audit_valid": self.audit.verify(),
            "product_execution": False,
            "external_writes": 0,
        }

    def _reserve(self) -> bool:
        with self._budget_lock:
            requested = self.policy.worst_case_reservation
            if self.consumed_units + self.reserved_units + requested > self.policy.max_campaign_units:
                return False
            self.reserved_units += requested
            self.max_observed_reserved_units = max(self.max_observed_reserved_units, self.reserved_units)
            return True

    def _release_unused(self) -> None:
        with self._budget_lock:
            self.reserved_units -= self.policy.worst_case_reservation
            if self.reserved_units < 0:
                raise PipelineError("host admission reservation ledger underflow")

    def _charge(self) -> None:
        with self._budget_lock:
            self.consumed_units += self.policy.estimated_scan_units
            # Reserved includes this job's worst-case retry + in-flight overhead.
            if self.consumed_units > self.policy.max_campaign_units:
                raise PipelineError("host hard admission budget was exceeded")

    @staticmethod
    def _security_relevant(path: str) -> bool:
        basename = path.rsplit("/", 1)[-1].casefold()
        if basename in {"readme.md", "agents.md", "claude.md", "dockerfile", "makefile"}:
            return True
        if ("security" in path.casefold().split("/") or any(
            word in basename for word in ("security", "threat", "auth", "deploy", "dependency", "architecture")
        )):
            return True
        if path.startswith("docs/") and basename.endswith((".md", ".txt", ".rst")):
            return False
        if fnmatch.fnmatch(path, "*.md") and basename not in {"readme.md", "agents.md"}:
            return False
        return True

    def _idempotency_key(self, repository: Repository, assignment: ThreatAssignment) -> str:
        return stable_digest({
            "repository_id": repository.repo_id,
            "commit_sha": repository.commit_sha,
            "effective_threat_model_hash": assignment.effective_model_hash,
            "scanner_version": self.policy.scanner_version,
            "policy_version": self.policy.policy_version,
        })

    @staticmethod
    def scope_target(repository: Repository) -> str:
        """Human scope binds exact repository, immutable revision, and current trusted owner."""

        return stable_digest({
            "repository_id": repository.repo_id,
            "commit_sha": repository.commit_sha,
            "owner": repository.owner,
        })

    def finding_target(self, repository: Repository, finding_id: str) -> str:
        """Bind every disposition, exception and patch to revision and effective policy/context."""

        assignment = self.catalogue.assign(repository)
        return stable_digest({
            "repository_id": repository.repo_id,
            "commit_sha": repository.commit_sha,
            "idempotency_key": self._idempotency_key(repository, assignment),
            "finding_id": finding_id,
        })

    def _execute(self, repository: Repository, assignment: ThreatAssignment, key: str) -> ScanState:
        state = ScanState(
            repository_id=repository.repo_id,
            idempotency_key=key,
            boundary_hash=repository.boundary_hash,
            status="running",
            reviewed_revision=repository.commit_sha,
            named_reviewers={
                "scope": self.approvals.require("scope", repository.repo_id, self.scope_target(repository)),
            },
        )
        if assignment.requires_human_acceptance:
            state.named_reviewers["threat_model"] = self.approvals.require(
                "threat_model", repository.repo_id, assignment.effective_model_hash,
            )
        self.audit.append("scan_admitted", repository.repo_id, context_hash=assignment.effective_model_hash)
        while state.attempts < self.policy.max_attempts:
            if repository.repo_id in self._cancelled:
                state.status, state.reason = "cancelled", "owner cancelled campaign"
                self.audit.append("scan_cancelled", repository.repo_id)
                return state
            state.attempts += 1
            self._charge()
            try:
                self.audit.append("scan_attempt_started", repository.repo_id, attempt=state.attempts)
                artifacts = self.scanner.scan(repository, assignment)
                manifest = self.sealer.seal(
                    repository_id=repository.repo_id,
                    commit_sha=repository.commit_sha,
                    scan_id=artifacts["scan_id"],
                    scanner_version=self.policy.scanner_version,
                    report=artifacts["report.md"],
                    findings=artifacts["findings.json"],
                    coverage=artifacts["coverage.json"],
                )
                evidence = {
                    "report.md": artifacts["report.md"],
                    "findings.json": artifacts["findings.json"],
                    "coverage.json": artifacts["coverage.json"],
                    "scan-manifest.json": manifest,
                }
                self.sealer.verify(evidence)
                if artifacts["coverage.json"]["completeness"] != "complete":
                    raise ScanFailure("scanner returned incomplete coverage", coverage="partial")
                state.evidence = evidence
                state.current_findings = tuple(deepcopy(artifacts["findings.json"]["findings"]))
                state.fresh_findings, state.duplicates = self.registry.admit(
                    artifacts["findings.json"]["findings"],
                )
                self._resolve_review(repository, state)
                self.audit.append(
                    "scan_completed", repository.repo_id,
                    finding_count=len(state.fresh_findings), duplicates=state.duplicates,
                    evidence_digest=next(
                        item["sha256"] for item in manifest["scan"]["artifacts"]
                        if item["path"] == "findings.json"
                    ),
                )
                return state
            except (ScanFailure, EvidenceError) as error:
                coverage = getattr(error, "coverage", None)
                retryable = getattr(error, "retryable", False)
                if coverage in {"partial", "unknown"}:
                    state.status = "awaiting_coverage_review"
                    state.reason = f"scanner returned incomplete {coverage} coverage; do not retry automatically"
                    self.audit.append("coverage_escalated", repository.repo_id, coverage=coverage)
                    return state
                if retryable and state.attempts < self.policy.max_attempts:
                    reason_code = getattr(error, "reason_code", "retryable_scan_failure")
                    if not isinstance(reason_code, str) or reason_code not in RETRY_REASON_CODES:
                        reason_code = "retryable_scan_failure"
                    self.audit.append(
                        "transient_retry", repository.repo_id,
                        attempt=state.attempts, reason_code=reason_code,
                    )
                    continue
                state.status = "failed_safe_abstention"
                state.reason = str(error)
                self.audit.append("safe_abstention", repository.repo_id, error_type=type(error).__name__)
                return state
            except Exception as error:
                # Untrusted adapters must not abort sibling reviews, strand a
                # reserved campaign slot, or copy sensitive exception text into
                # durable owner-visible evidence. Human approvals established
                # above remain attached to this safely stopped repository.
                state.status = "failed_safe_abstention"
                state.reason = "unexpected synthetic worker failure; stopped safely"
                self.audit.append("safe_abstention", repository.repo_id, error_type=type(error).__name__)
                return state
        raise PipelineError("scan retry state exhausted without a terminal decision")

    def _resolve_review(self, repository: Repository, state: ScanState) -> None:
        now = self._clock()
        for finding in state.current_findings:
            identity = str(finding["findingId"])
            target = self.finding_target(repository, identity)
            reviewer = self.approvals.actor("finding_disposition", repository.repo_id, target)
            exception_owner = self.approvals.active_exception(repository.repo_id, target, now=now)
            if reviewer is None and exception_owner is None:
                state.status = "awaiting_finding_disposition"
                state.reason = "named security owner must disposition each consequential finding"
                state.route = "review_packet"
                return
            state.named_reviewers["security"] = reviewer or str(exception_owner)
            if exception_owner:
                state.named_reviewers["exception"] = exception_owner
        if self.policy.allow_draft_pr and self.policy.provider_write_authorised and state.current_findings:
            for finding in state.current_findings:
                identity = str(finding["findingId"])
                target = self.finding_target(repository, identity)
                patch_reviewer = self.approvals.actor("patch", repository.repo_id, target)
                if patch_reviewer is None:
                    state.status = "awaiting_patch_approval"
                    state.reason = "named patch owner must approve the exact finding before draft routing"
                    state.route = "review_packet"
                    return
                state.named_reviewers["patch"] = patch_reviewer
            state.status = "awaiting_human_merge"
            state.reason = "local draft-PR artifact only; no provider call, merge, or deployment"
            state.route = "draft_pr_artifact_only"
            return
        state.status = "review_packet_ready"
        state.reason = "named human retains disposition, acceptance, merge and deployment authority"
        state.route = "review_packet"

    def _stop(self, repository: Repository, key: str, status: str, reason: str) -> dict[str, Any]:
        state = ScanState(
            repository_id=repository.repo_id,
            idempotency_key=key,
            boundary_hash=repository.boundary_hash,
            status=status,
            reviewed_revision=repository.commit_sha,
            reason=reason,
        )
        self.audit.append(status, repository.repo_id)
        return state.receipt()
