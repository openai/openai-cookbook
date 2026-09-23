"""Shared wholly synthetic fleet-security test helpers."""
from __future__ import annotations

import hashlib
import sys
from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = str(ROOT / "src")
if SOURCE not in sys.path:
    sys.path.insert(0, SOURCE)

from fleet_security import ApprovalLedger, FleetPipeline, FleetPolicy, Repository, SyntheticScanner, ThreatCatalogue


OWNERS = {
    "scope_authorizer": {"scope-owner"},
    "model_reviewer": {"threat-owner"},
    "security_reviewer": {"security-owner"},
    "patch_reviewer": {"patch-owner"},
    "merge_owner": {"merge-owner"},
    "deploy_owner": {"deploy-owner"},
    "exception_owner": {"exception-owner"},
    "policy_owner": {"policy-owner"},
}


def repository(index: int = 1, *, fixture: str = "safe_service", **changes: object) -> Repository:
    base = Repository(
        repo_id=f"synthetic/repo-{index:04d}",
        commit_sha=hashlib.sha1(f"synthetic-test-{index}".encode()).hexdigest(),
        owner="named-owner",
        language="python",
        framework="fastapi",
        topology="container",
        data_class="internal",
        exposure="private",
        authentication="service_identity",
        dependencies=("library-a",),
        criticality="medium",
        controls=("audit_logging",),
        changed_paths=("src/service.py",),
        fixture=fixture,
    )
    return replace(base, **changes)


def ledger(*, now: list[int] | None = None) -> ApprovalLedger:
    return ApprovalLedger(OWNERS, clock=(lambda: now[0]) if now is not None else None)


def pipeline(
    *, approvals: ApprovalLedger | None = None,
    policy: FleetPolicy | None = None,
    scanner: SyntheticScanner | None = None,
    clock: callable | None = None,
) -> FleetPipeline:
    return FleetPipeline(
        policy=policy or FleetPolicy(),
        approvals=approvals or ledger(),
        catalogue=ThreatCatalogue(),
        scanner=scanner,
        clock=clock,
    )


def approve_scope(flow: FleetPipeline, record: Repository) -> None:
    flow.approvals.approve("scope", record.repo_id, flow.scope_target(record), "scope-owner")


def approve_model(flow: FleetPipeline, record: Repository) -> None:
    assignment = flow.catalogue.assign(record)
    flow.approvals.approve("threat_model", record.repo_id, assignment.effective_model_hash, "threat-owner")
