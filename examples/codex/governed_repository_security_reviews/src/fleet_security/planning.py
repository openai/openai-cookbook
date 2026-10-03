"""Validate trusted real-repository metadata without accessing or scanning code.

This adapter is deliberately planning-only. It never fetches a repository,
starts a scanner, writes a campaign, connects to a provider, or claims findings.
"""
from __future__ import annotations

import ipaddress
import re
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from .inventory import Repository, classify, load_inventory
from .pipeline import ApprovalLedger, FleetPipeline, PipelineError
from .recipe import RecipeConfiguration, _read_json
from .surface import NativeBulkCampaign, group_native_campaigns
from .threats import ThreatCatalogue


_CONTROL_CHARACTER = re.compile(r"[\x00-\x20\x7f]")


def _repository_url(value: object, repository_id: str) -> str:
    if not isinstance(value, str) or not value or _CONTROL_CHARACTER.search(value):
        raise PipelineError("repository URL must be one explicit, whitespace-free HTTPS address")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise PipelineError("repository URL is malformed") from error
    if (
        parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
        or parsed.password is not None or parsed.query or parsed.fragment or port is not None
    ):
        raise PipelineError(
            "repository URL must use HTTPS without embedded credentials, ports, query, or fragment"
        )
    hostname = parsed.hostname.rstrip(".").casefold()
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise PipelineError("repository URL cannot target localhost or an internal address")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise PipelineError("repository URL cannot target localhost or an internal address")
    if unquote(parsed.path) != parsed.path or "//" in parsed.path:
        raise PipelineError("repository URL path cannot hide encoded or ambiguous segments")
    repository_path = parsed.path.removesuffix(".git").strip("/")
    if repository_path != repository_id:
        raise PipelineError("repository URL must bind the exact trusted repository identity")
    return value


def _load_metadata(path: Path) -> tuple[tuple[Repository, ...], dict[str, str]]:
    document = _read_json(path, label="planning-only repository metadata")
    if set(document) != {"repositories"} or not isinstance(document["repositories"], list):
        raise PipelineError("trusted planning inventory requires one explicit repositories list")
    if not document["repositories"]:
        raise PipelineError("trusted planning inventory cannot be empty")
    rows: list[dict[str, Any]] = []
    urls: dict[str, str] = {}
    for entry in document["repositories"]:
        if not isinstance(entry, dict):
            raise PipelineError("trusted planning inventory row must be one JSON object")
        row = dict(entry)
        if "fixture" in row:
            raise PipelineError("real repository metadata cannot be attached to a synthetic fixture")
        repository_id = row.get("repo_id")
        if not isinstance(repository_id, str) or repository_id.startswith("synthetic/"):
            raise PipelineError("planning-only metadata requires an explicit non-synthetic repository")
        url = _repository_url(row.pop("repository_url", None), repository_id)
        previous_url = urls.get(repository_id)
        if previous_url is not None and previous_url != url:
            raise PipelineError("trusted repository identity has contradictory provider URLs")
        urls[repository_id] = url
        for field in ("dependencies", "controls", "changed_paths"):
            if field in row:
                if not isinstance(row[field], list):
                    raise PipelineError(f"trusted repository {field} must be an explicit JSON list")
                row[field] = tuple(row[field])
        rows.append(row)
    return load_inventory(rows), urls


def _apply_planning_approvals(
    *, path: Path, repositories: tuple[Repository, ...], catalogue: ThreatCatalogue,
    ledger: ApprovalLedger,
) -> None:
    document = _read_json(path, label="planning-only named-human approval")
    if set(document) != {"approvals"} or not isinstance(document["approvals"], list):
        raise PipelineError("trusted planning approvals require one explicit approvals list")
    records = {repository.repo_id: repository for repository in repositories}
    admitted: set[tuple[str, str]] = set()
    for entry in document["approvals"]:
        if not isinstance(entry, dict):
            raise PipelineError("trusted planning approval must be one JSON object")
        gate = entry.get("gate")
        if gate not in {"scope", "threat_model"}:
            raise PipelineError("planning-only approval cannot grant scanning or provider-write authority")
        required = {"gate", "repository_id", "revision", "actor"}
        required.add("service_owner" if gate == "scope" else "context_sha256")
        if not required <= set(entry) or set(entry) - required - {"expires_at"}:
            raise PipelineError("planning approval contains missing or unsupported authority fields")
        repository = records.get(entry["repository_id"])
        if repository is None or entry["revision"] != repository.commit_sha:
            raise PipelineError("planning approval must bind the current exact repository revision")
        identity = (gate, repository.repo_id)
        if identity in admitted:
            raise PipelineError("planning approval contains duplicate or contradictory human decisions")
        admitted.add(identity)
        if gate == "scope":
            if entry["service_owner"] != repository.owner:
                raise PipelineError("planning scope approval must bind its current named service owner")
            target = FleetPipeline.scope_target(repository)
        else:
            target = catalogue.assign(repository).effective_model_hash
            if entry["context_sha256"] != target:
                raise PipelineError("planning threat approval must bind the exact effective context")
        ledger.approve(
            gate, repository.repo_id, target, entry["actor"],
            expires_at=entry.get("expires_at"),
        )


def prepare_repository_review(
    *, configuration_path: Path, inventory_path: Path, approvals_path: Path,
) -> dict[str, Any]:
    """Return inert owner-authorised campaign plans without inspecting repositories."""

    configuration = RecipeConfiguration.from_file(configuration_path)
    repositories, urls = _load_metadata(inventory_path)
    catalogue = ThreatCatalogue(
        organisation_controls=configuration.organisation_controls,
        version=configuration.organisation_model_version,
    )
    ledger = ApprovalLedger(configuration.owners)
    _apply_planning_approvals(
        path=approvals_path, repositories=repositories,
        catalogue=catalogue, ledger=ledger,
    )

    available = min(
        configuration.policy.max_scans_per_run,
        configuration.policy.max_campaign_units // configuration.policy.worst_case_reservation,
    )
    admitted: list[Repository] = []
    decisions: list[dict[str, Any]] = []
    for repository in repositories:
        assignment = catalogue.assign(repository)
        scope_actor = ledger.actor("scope", repository.repo_id, FleetPipeline.scope_target(repository))
        threat_actor = ledger.actor("threat_model", repository.repo_id, assignment.effective_model_hash)
        if scope_actor is None:
            status, reason = "awaiting_scope_approval", "exact repository scope has not been approved"
        elif assignment.requires_human_acceptance and threat_actor is None:
            status, reason = (
                "awaiting_threat_model_acceptance",
                "high-risk effective threat context requires named human acceptance",
            )
        elif len(admitted) >= available:
            status, reason = "awaiting_campaign_capacity", "campaign concurrency or budget admission is full"
        else:
            status, reason = "planned_not_executed", "metadata-only plan; no repository was inspected"
            admitted.append(repository)
        reviewers = {"scope": scope_actor}
        if threat_actor is not None:
            reviewers["threat_model"] = threat_actor
        decisions.append({
            "repository_id": repository.repo_id,
            "repository_url": urls[repository.repo_id],
            "revision": repository.commit_sha,
            "service_owner": repository.owner,
            "risk_tier": repository.risk_tier,
            "archetype": classify(repository).archetype,
            "effective_context_sha256": assignment.effective_model_hash,
            "requires_human_acceptance": assignment.requires_human_acceptance,
            "named_human_reviewers": reviewers,
            "status": status,
            "reason": reason,
            "code_inspected": False,
            "finding_count": None,
            "review_packet_ready": False,
        })

    campaigns: list[dict[str, Any]] = []
    for campaign in group_native_campaigns(
        tuple(admitted), catalogue,
        workers=configuration.policy.max_concurrent,
        max_attempts=configuration.policy.max_attempts,
    ):
        rows = tuple({**row, "repository": urls[row["repository"]]} for row in campaign.rows)
        provider_campaign = NativeBulkCampaign(
            archetype=campaign.archetype,
            rows=rows,
            knowledge_base_paths=campaign.knowledge_base_paths,
            workers=campaign.workers,
            max_attempts=campaign.max_attempts,
        )
        slug = re.sub(r"[^a-z0-9-]+", "-", campaign.archetype.casefold()).strip("-")
        command = provider_campaign.command(
            csv_path=f"/owner-private/planned-campaigns/{slug}.csv",
            output_dir=f"/owner-private/planned-output/{slug}",
        ) + ("--model", configuration.selected_model, "--effort", configuration.selected_effort)
        campaigns.append({
            "archetype": campaign.archetype,
            "repository_count": len(rows),
            "rows": list(rows),
            "knowledge_base_paths": list(provider_campaign.knowledge_base_paths),
            "command": list(command),
            "command_executed": False,
            "campaign_files_written": False,
            "native_campaign_has_hard_cost_flag": False,
        })

    blockers = ["live_repository_adapter_not_authorised", "native_product_execution_not_authorised"]
    if not configuration.model_approved:
        blockers.append("named_model_and_spending_owner_approval_required")
    return {
        "mode": "planning_only",
        "organisation_id": configuration.organisation_id,
        "repository_metadata_only": True,
        "repositories": decisions,
        "decision_states": dict(sorted(Counter(row["status"] for row in decisions).items())),
        "campaigns": campaigns,
        "campaign_admission_capacity": available,
        "model_execution_approved": configuration.model_approved,
        "model_approval_owner": configuration.model_approval_owner,
        "execution_blockers": blockers,
        "scanned_repositories": 0,
        "scan_receipts": 0,
        "finding_count": None,
        "review_packets_created": 0,
        "customer_repository_accessed": False,
        "product_scan_executed": False,
        "paid_api_calls": 0,
        "external_writes": 0,
        "provider_pr_created": False,
        "merge_performed": False,
        "deployment_performed": False,
    }
