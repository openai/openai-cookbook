"""Immutable task contracts and serialisable execution evidence."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class RunStatus(str, Enum):
    READY_FOR_HUMAN_REVIEW = "ready_for_human_review"
    ABSTAIN = "abstain"


@dataclass(frozen=True)
class Issue:
    issue_id: str
    title: str
    description: str
    acceptance_criteria: tuple[str, ...]
    allowed_paths: tuple[str, ...]
    base_sha: str
    human_acceptor: str
    repository_id: str = "synthetic-repository"
    risk_class: str = "low"
    plan_approved: bool = True

    @property
    def identifier(self) -> str:
        return self.issue_id

    @property
    def requested_paths(self) -> tuple[str, ...]:
        return self.allowed_paths

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Issue:
        values = dict(data)
        if "identifier" in values and "issue_id" not in values:
            values["issue_id"] = values.pop("identifier")
        if "requested_paths" in values and "allowed_paths" not in values:
            values["allowed_paths"] = values.pop("requested_paths")
        for name in ("acceptance_criteria", "allowed_paths"):
            if name in values:
                values[name] = tuple(values[name])
        return cls(**values)


@dataclass(frozen=True)
class Policy:
    allowed_paths: tuple[str, ...] = ("src/text_tools.py",)
    approved_issue_ids: tuple[str, ...] = ("SYNTH-101",)
    approved_human_acceptors: tuple[str, ...] = ("synthetic-maintainer",)
    allowed_risk_classes: tuple[str, ...] = ("low",)
    protected_prefixes: tuple[str, ...] = (
        ".git", ".github", ".env", "tests", "evals", "secrets", "infra", "deploy"
    )
    allowed_imports: tuple[str, ...] = ("re", "unicodedata")
    max_model_turns: int = 6
    max_patch_calls: int = 4
    max_shell_calls: int = 2
    max_remediation_attempts: int = 1
    max_changed_files: int = 2
    max_diff_lines: int = 120
    max_issue_characters: int = 8000
    max_wall_seconds: float = 60.0
    max_test_seconds: float = 15.0
    max_input_tokens: int = 32000
    max_output_tokens: int = 4000
    allow_network: bool = False
    allow_shell: bool = False
    require_human_merge: bool = True
    allow_create: bool = False
    allow_delete: bool = False

    @property
    def preapproved_issue_ids(self) -> tuple[str, ...]:
        return self.approved_issue_ids

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Policy:
        values = dict(data)
        if "preapproved_issue_ids" in values and "approved_issue_ids" not in values:
            values["approved_issue_ids"] = values.pop("preapproved_issue_ids")
        for name in (
            "allowed_paths", "approved_issue_ids", "approved_human_acceptors",
            "allowed_risk_classes", "protected_prefixes", "allowed_imports",
        ):
            if name in values:
                values[name] = tuple(values[name])
        return cls(**values)

    @classmethod
    def for_issue(cls, issue: Issue, **overrides: Any) -> Policy:
        # Never derive trusted approval identities, owners, scope, or risk from issue data.
        # Explicit caller-supplied overrides remain the caller's trusted policy decision.
        policy = cls(**overrides)
        from .policy import validate_issue
        validate_issue(issue, policy)
        return policy


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunResult:
    status: RunStatus
    issue_id: str
    reason: str
    review_packet: dict[str, Any] | None = None
    audit: list[dict[str, Any]] = field(default_factory=list)
    turns: int = 0
    patch_calls: int = 0
    remediation_attempts: int = 0

    @property
    def decision(self) -> RunStatus:
        return self.status

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        data["decision"] = self.status.value
        return data
