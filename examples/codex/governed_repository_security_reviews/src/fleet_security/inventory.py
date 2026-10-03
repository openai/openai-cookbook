"""Trusted synthetic repository inventory and deterministic classification."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Iterable, Mapping


class InventoryError(ValueError):
    """Inventory input was incomplete, contradictory, or unsafe."""


_IDENTITY = re.compile(r"[a-z][a-z0-9]*(?:[-_/][a-z0-9]+)*\Z")
_FIXTURE = re.compile(r"[a-z][a-z0-9_-]{0,127}\Z")
_OWNER = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{1,79}\Z")
_SHA = re.compile(r"(?:[a-f0-9]{40}|[a-f0-9]{64})\Z")
_VALUES = {
    "language": frozenset({"python", "typescript", "go", "java"}),
    "framework": frozenset({"django", "fastapi", "express", "spring", "stdlib"}),
    "topology": frozenset({"container", "serverless", "worker", "library"}),
    "data_class": frozenset({"public", "internal", "confidential", "restricted"}),
    "exposure": frozenset({"internet", "private", "offline"}),
    "authentication": frozenset({"oidc", "mtls", "service_identity", "none"}),
    "criticality": frozenset({"low", "medium", "high", "critical"}),
}


def stable_digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("ascii")).hexdigest()


@dataclass(frozen=True)
class Repository:
    """One owner-authorised inventory row; identifiers contain no customer data."""

    repo_id: str
    commit_sha: str
    owner: str
    language: str
    framework: str
    topology: str
    data_class: str
    exposure: str
    authentication: str
    dependencies: tuple[str, ...] = ()
    criticality: str = "medium"
    controls: tuple[str, ...] = ()
    changed_paths: tuple[str, ...] = ()
    material_divergence: bool = False
    fixture: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.repo_id, str) or not _IDENTITY.fullmatch(self.repo_id):
            raise InventoryError("repository identity is missing or unsafe")
        if not isinstance(self.commit_sha, str) or not _SHA.fullmatch(self.commit_sha):
            raise InventoryError("repository revision must be a pinned 40- or 64-character lowercase SHA")
        if not isinstance(self.owner, str) or not _OWNER.fullmatch(self.owner):
            raise InventoryError("repository requires a named trusted human owner")
        for name, allowed in _VALUES.items():
            if getattr(self, name) not in allowed:
                raise InventoryError(f"repository {name} is absent or unsupported")
        for name in ("dependencies", "controls", "changed_paths"):
            values = getattr(self, name)
            if not isinstance(values, tuple) or any(not isinstance(v, str) or not v for v in values):
                raise InventoryError(f"repository {name} must contain non-empty strings")
            if name != "changed_paths" and tuple(sorted(set(values))) != values:
                raise InventoryError(f"repository {name} must be sorted and deduplicated")
        for path in self.changed_paths:
            if path.startswith(("/", "~")) or "\\" in path or ".." in path.split("/"):
                raise InventoryError("changed path escaped its repository boundary")
        if not isinstance(self.material_divergence, bool):
            raise InventoryError("material divergence must be explicitly boolean")
        if self.fixture is not None and (
            not isinstance(self.fixture, str) or not _FIXTURE.fullmatch(self.fixture)
        ):
            raise InventoryError("fixture identity is unsafe")

    def as_dict(self) -> dict[str, object]:
        return asdict(self)

    @property
    def risk_tier(self) -> str:
        if self.material_divergence or self.criticality == "critical":
            return "high"
        if self.data_class == "restricted" and self.exposure == "internet":
            return "high"
        if self.authentication == "none" and self.exposure == "internet":
            return "high"
        return "standard"

    @property
    def boundary_hash(self) -> str:
        return stable_digest({
            "language": self.language, "framework": self.framework,
            "topology": self.topology, "data_class": self.data_class,
            "exposure": self.exposure, "authentication": self.authentication,
            "dependencies": self.dependencies, "criticality": self.criticality,
            "controls": self.controls, "material_divergence": self.material_divergence,
        })


@dataclass(frozen=True)
class Classification:
    archetype: str
    risk_tier: str
    attributes: Mapping[str, str] = field(default_factory=dict)


def classify(repository: Repository) -> Classification:
    return Classification(
        archetype=f"{repository.language}:{repository.framework}:{repository.topology}:{repository.exposure}",
        risk_tier=repository.risk_tier,
        attributes={
            "owner": repository.owner, "data_class": repository.data_class,
            "authentication": repository.authentication,
            "criticality": repository.criticality,
            "dependency_count": str(len(repository.dependencies)),
        },
    )


def load_inventory(rows: Iterable[Repository | Mapping[str, object]]) -> tuple[Repository, ...]:
    observed: dict[str, Repository] = {}
    for row in rows:
        try:
            repository = row if isinstance(row, Repository) else Repository(**dict(row))
        except (TypeError, ValueError) as error:
            raise InventoryError(f"invalid trusted inventory row: {error}") from error
        previous = observed.get(repository.repo_id)
        if previous is not None and previous != repository:
            raise InventoryError(f"contradictory repository inventory identity: {repository.repo_id}")
        observed[repository.repo_id] = repository
    return tuple(observed[key] for key in sorted(observed))


def generate_inventory(count: int = 2_000) -> tuple[Repository, ...]:
    if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= 20_000:
        raise InventoryError("synthetic fleet size must be between 1 and 20,000")
    profiles = (
        ("python", "django", "container", "internet"),
        ("python", "fastapi", "container", "private"),
        ("python", "stdlib", "worker", "private"),
        ("typescript", "express", "container", "internet"),
        ("typescript", "express", "serverless", "private"),
        ("go", "stdlib", "container", "internet"),
        ("go", "stdlib", "worker", "private"),
        ("java", "spring", "container", "private"),
        ("java", "spring", "container", "internet"),
        ("python", "stdlib", "library", "offline"),
    )
    rows: list[Repository] = []
    for index in range(count):
        language, framework, topology, exposure = profiles[index % len(profiles)]
        high_risk = index % 50 == 0
        data_class = "restricted" if high_risk else ("confidential" if index % 7 == 0 else "internal")
        rows.append(Repository(
            repo_id=f"synthetic/repo-{index:04d}",
            commit_sha=hashlib.sha1(f"synthetic-revision-{index}".encode("ascii")).hexdigest(),
            owner=f"owner-{index % 25:02d}",
            language=language,
            framework=framework,
            topology=topology,
            data_class=data_class,
            exposure=exposure,
            authentication="oidc" if exposure == "internet" else "service_identity",
            dependencies=tuple(sorted({f"package-{index % 13}", f"shared-{index % 4}"})),
            criticality="critical" if high_risk else ("high" if index % 11 == 0 else "medium"),
            controls=tuple(sorted({"audit_logging", "encryption_at_rest", f"team_control_{index % 3}"})),
            changed_paths=("src/service.py",),
            material_divergence=index % 113 == 0,
        ))
    return load_inventory(rows)
