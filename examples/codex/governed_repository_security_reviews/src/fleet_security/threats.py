"""Host-owned, hierarchical threat context; no product-generated models are claimed."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping

from .inventory import Classification, Repository, classify, stable_digest


@dataclass(frozen=True)
class ThreatAssignment:
    strategy: str
    organisation_model_id: str
    archetype_model_id: str | None
    repository_model_id: str | None
    effective_model_hash: str
    boundary_hash: str
    delta: Mapping[str, object]
    requires_human_acceptance: bool
    covered_scenarios: frozenset[str]


@dataclass(frozen=True)
class ThreatCatalogue:
    """Immutable trusted context; repository files never control this configuration."""

    organisation_controls: tuple[str, ...] = (
        "audit_logging", "encryption_at_rest", "identity_governance", "network_segmentation",
    )
    version: str = "synthetic-org-v1"
    archetype_overrides: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.version or any(not item for item in self.organisation_controls):
            raise ValueError("trusted organisation threat baseline is incomplete")
        for key, scenarios in self.archetype_overrides.items():
            if not isinstance(key, str) or not key or not isinstance(scenarios, tuple):
                raise ValueError("trusted archetype override is invalid")

    def assign(self, repository: Repository, *, strategy: str = "hierarchical") -> ThreatAssignment:
        if strategy not in {"hierarchical", "per_repository", "shared"}:
            raise ValueError("threat model strategy is unsupported")
        classification = classify(repository)
        platform = frozenset({"identity_abuse", "dependency_supply_chain", "audit_tampering"})
        archetype_scenarios = self._archetype_scenarios(repository, classification)
        unique_scenarios = self._unique_scenarios(repository)
        bespoke = strategy == "per_repository" or (
            strategy == "hierarchical" and repository.risk_tier == "high"
        )
        if strategy == "shared":
            archetype_model_id = None
            repository_model_id = None
            covered = platform
            delta: dict[str, object] = {}
        elif bespoke:
            archetype_model_id = classification.archetype if strategy == "hierarchical" else None
            repository_model_id = f"repository:{repository.repo_id}"
            delta = self._repository_delta(repository)
            covered = platform | archetype_scenarios | unique_scenarios
        else:
            archetype_model_id = classification.archetype
            repository_model_id = None
            delta = self._repository_delta(repository)
            covered = platform | archetype_scenarios | unique_scenarios
        context = {
            "version": self.version,
            "strategy": strategy,
            "platform_controls": self.organisation_controls,
            "archetype": archetype_model_id,
            "repository_model": repository_model_id,
            "delta": delta,
            "covered_scenarios": sorted(covered),
        }
        return ThreatAssignment(
            strategy=strategy,
            organisation_model_id=self.version,
            archetype_model_id=archetype_model_id,
            repository_model_id=repository_model_id,
            effective_model_hash=stable_digest(context),
            boundary_hash=repository.boundary_hash,
            delta=delta,
            requires_human_acceptance=repository.risk_tier == "high",
            covered_scenarios=covered,
        )

    def _repository_delta(self, repository: Repository) -> dict[str, object]:
        return {
            "data_class": repository.data_class,
            "authentication": repository.authentication,
            "dependencies": repository.dependencies,
            "criticality": repository.criticality,
            "additional_controls": tuple(
                control for control in repository.controls if control not in self.organisation_controls
            ),
            "material_divergence": repository.material_divergence,
        }

    def _archetype_scenarios(self, repository: Repository, classification: Classification) -> frozenset[str]:
        scenarios = set(self.archetype_overrides.get(classification.archetype, ()))
        if repository.exposure == "internet":
            scenarios.update({"remote_input_injection", "authentication_bypass"})
        if repository.topology in {"container", "serverless"}:
            scenarios.add("runtime_identity_escape")
        if repository.topology == "worker":
            scenarios.add("queue_message_tampering")
        if repository.framework in {"django", "fastapi", "express", "spring"}:
            scenarios.add("framework_authorisation_bypass")
        return frozenset(scenarios)

    @staticmethod
    def _unique_scenarios(repository: Repository) -> frozenset[str]:
        scenarios: set[str] = set()
        if repository.data_class in {"confidential", "restricted"}:
            scenarios.add("sensitive_data_exfiltration")
        if repository.data_class == "restricted":
            scenarios.add("regulated_data_boundary")
        if repository.authentication == "none" and repository.exposure == "internet":
            scenarios.add("unauthenticated_public_entrypoint")
        if repository.material_divergence:
            scenarios.add("bespoke_trust_boundary")
        return frozenset(scenarios)


def compare_strategies(
    repositories: Iterable[Repository], catalogue: ThreatCatalogue | None = None,
) -> dict[str, dict[str, int | float]]:
    """Transparent synthetic comparison, not customer telemetry, price, or SLA."""

    records = tuple(repositories)
    if not records:
        raise ValueError("strategy comparison requires at least one synthetic repository")
    trusted = catalogue or ThreatCatalogue()
    results: dict[str, dict[str, int | float]] = {}
    for strategy in ("per_repository", "shared", "hierarchical"):
        assignments = [trusted.assign(record, strategy=strategy) for record in records]
        archetypes = {item.archetype_model_id for item in assignments if item.archetype_model_id}
        bespoke = {item.repository_model_id for item in assignments if item.repository_model_id}
        model_artifacts = 1 + len(archetypes) + len(bespoke)
        possible_scenarios = 0
        covered_scenarios = 0
        high_risk_total = 0
        high_risk_fully_covered = 0
        for repository, assignment in zip(records, assignments, strict=True):
            expected = trusted.assign(repository, strategy="per_repository").covered_scenarios
            possible_scenarios += len(expected)
            covered_scenarios += len(expected & assignment.covered_scenarios)
            if repository.risk_tier == "high":
                high_risk_total += 1
                if expected <= assignment.covered_scenarios:
                    high_risk_fully_covered += 1
        if strategy == "per_repository":
            # Full platform + workload context must be repeated and re-reviewed for each repository.
            context_units = len(records) * 120
            platform_drift_model_updates = len(records)
            reviewer_artifacts = len(records)
        elif strategy == "shared":
            context_units = 120 + len(records) * 4
            platform_drift_model_updates = 1
            reviewer_artifacts = 1
        else:
            context_units = 120 + len(archetypes) * 45 + len(records) * 12 + len(bespoke) * 60
            platform_drift_model_updates = 1
            reviewer_artifacts = 1 + len(archetypes) + len(bespoke)
        results[strategy] = {
            "repositories": len(records),
            "model_artifacts": model_artifacts,
            "reviewer_artifacts": reviewer_artifacts,
            "platform_drift_model_updates": platform_drift_model_updates,
            "synthetic_relative_context_units": context_units,
            "covered_scenarios": covered_scenarios,
            "possible_scenarios": possible_scenarios,
            "coverage_percent": round(100 * covered_scenarios / possible_scenarios, 2),
            "high_risk_repositories": high_risk_total,
            "high_risk_fully_covered": high_risk_fully_covered,
            "bespoke_models": len(bespoke),
            "archetype_models": len(archetypes),
        }
    return results
