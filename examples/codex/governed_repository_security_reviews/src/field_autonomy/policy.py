"""Fail-closed host policy; model content is never authorisation."""
from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

from .models import Issue, Policy


class PolicyViolation(Exception):
    """A hard safety boundary was violated; the workflow must safely abstain."""


UNTRUSTED_PATTERNS = (
    (r"ignore\s+(?:all\s+)?(?:previous|prior|system|developer)\s+instructions", "instruction override"),
    (r"(?:print|read|dump|send|upload|exfiltrate)\s+.{0,50}(?:secret|token|api[_ -]?key|credential|\.env)", "credential access"),
    (r"\b(?:curl|wget|scp|ssh|nc|netcat)\b", "network-capable command"),
    (r"\bgit\s+(?:push|merge|rebase|remote)\b", "repository publication or merge"),
    (r"\b(?:deploy|terraform\s+apply|kubectl\s+apply)\b", "deployment request"),
    (r"\brm\s+-[a-z]*r[a-z]*f\b", "destructive command"),
    (r"(?:^|\s)(?:sudo|chmod|chown)\b", "privileged operation"),
)


def validate_issue(issue: Issue, policy: Policy) -> None:
    content = "\n".join((issue.title, issue.description, *issue.acceptance_criteria))
    if len(content) > policy.max_issue_characters:
        raise PolicyViolation("issue exceeds the configured size budget")
    if not issue.issue_id or issue.issue_id not in policy.approved_issue_ids:
        raise PolicyViolation("issue lacks approval in the trusted host-owned policy ledger")
    if not issue.repository_id:
        raise PolicyViolation("issue does not identify its approved repository")
    if not issue.acceptance_criteria or any(not value.strip() for value in issue.acceptance_criteria):
        raise PolicyViolation("issue does not define testable acceptance criteria")
    if not issue.human_acceptor or issue.human_acceptor not in policy.approved_human_acceptors:
        raise PolicyViolation("issue does not name an approved independent human acceptor")
    if issue.risk_class not in policy.allowed_risk_classes:
        raise PolicyViolation("issue risk class is not approved")
    if not issue.plan_approved:
        raise PolicyViolation("issue lacks trusted pre-mutation plan approval")
    if not re.fullmatch(r"[a-f0-9]{40}", issue.base_sha):
        raise PolicyViolation("issue does not specify a valid pinned Git base SHA")
    if not issue.allowed_paths:
        raise PolicyViolation("issue does not declare an approved file scope")
    if not policy.require_human_merge:
        raise PolicyViolation("human merge approval cannot be disabled")
    if policy.allow_network:
        raise PolicyViolation("network-enabled execution is not implemented or approved")
    for pattern, description in UNTRUSTED_PATTERNS:
        if re.search(pattern, content, flags=re.IGNORECASE | re.MULTILINE):
            raise PolicyViolation(f"untrusted issue contains {description}")
    for path in issue.allowed_paths:
        validate_relative_path(path, policy)


def validate_relative_path(candidate: str, policy: Policy) -> str:
    if not isinstance(candidate, str) or not candidate or "\x00" in candidate:
        raise PolicyViolation("patch path is missing or invalid")
    if "\\" in candidate:
        raise PolicyViolation(f"backslash paths are not permitted: {candidate!r}")
    path = PurePosixPath(candidate)
    if path.is_absolute() or ".." in path.parts or candidate.startswith("~"):
        raise PolicyViolation(f"path escapes the approved workspace: {candidate!r}")
    normalised = path.as_posix()
    if normalised != candidate or any(part in ("", ".") for part in candidate.split("/")):
        raise PolicyViolation(f"path is not in canonical relative form: {candidate!r}")
    if any(normalised == prefix or normalised.startswith(prefix + "/") for prefix in policy.protected_prefixes):
        raise PolicyViolation(f"protected path is not writable: {normalised!r}")
    if normalised not in policy.allowed_paths:
        raise PolicyViolation(f"path is outside the approved allowlist: {normalised!r}")
    return normalised


def resolve_writable_path(root: Path, relative_path: str, policy: Policy) -> Path:
    normalised = validate_relative_path(relative_path, policy)
    root_resolved = root.resolve(strict=True)
    candidate = root / normalised
    for parent in (candidate, *candidate.parents):
        if parent == root:
            break
        if parent.is_symlink():
            raise PolicyViolation(f"symlink writes are not permitted: {relative_path!r}")
    resolved = candidate.resolve(strict=False)
    if not resolved.is_relative_to(root_resolved):
        raise PolicyViolation(f"resolved path escapes the worktree: {relative_path!r}")
    return resolved


def validate_diff(diff: str, changed_paths: tuple[str, ...], policy: Policy) -> None:
    if not diff.strip():
        raise PolicyViolation("implementation produced no reviewable changes")
    if len(changed_paths) > policy.max_changed_files:
        raise PolicyViolation("change exceeds the approved file-count budget")
    if len(diff.splitlines()) > policy.max_diff_lines:
        raise PolicyViolation("change exceeds the approved diff-size budget")
    for path in changed_paths:
        validate_relative_path(path, policy)
