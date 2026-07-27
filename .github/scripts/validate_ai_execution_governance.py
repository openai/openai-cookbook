#!/usr/bin/env python3
"""Validate repository-level AI execution governance without dependencies."""

from __future__ import annotations

import argparse
import pathlib
import re
import shutil
import tempfile


REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[2]
REQUIRED_FILES = {
    "AGENTS.md": (
        "one execution has one narrowly scoped objective",
        "one task produces one pull request",
        "inspect the targeted existing work",
        "do not rescan the whole repository",
        "scope, evidence, tests, stop condition, and recovery point",
        "stop when the requested artifact is produced",
        "secrets or private operational values",
        "gmail, beds24, monitoring, deployment, access, payments, legal",
        "reduces the context required by the next execution",
    ),
    "docs/AI_EXECUTION_POLICY.md": (
        "one execution must have one narrowly scoped objective",
        "one task must produce one pull request",
        "inspect targeted existing work before creating new work",
        "do not rescan the whole repository",
        "| scope |",
        "| evidence |",
        "| tests |",
        "| stop condition |",
        "| recovery point |",
        "secrets and private operational values",
        "without explicit, task-specific authorization",
        "stop after the requested artifact is produced",
        "reduce the context required by the next task",
    ),
    "docs/CHECKPOINT_PROTOCOL.md": (
        "objective",
        "scope",
        "evidence",
        "tests",
        "stop condition",
        "recovery point",
        "reuse any recoverable branch, commit, pull request, or checkpoint",
        "whole-repository rescan",
        "stop immediately when the stop condition is met",
        "reduce the context the next task must reconstruct",
    ),
    ".github/pull_request_template.md": (
        "## execution contract",
        "**scope:**",
        "**evidence:**",
        "**tests:**",
        "**stop condition:**",
        "**recovery point:**",
        "one narrowly scoped objective",
        "did not rescan the whole repository",
        "no secrets or private operational values",
        "gmail, beds24, monitoring, deployment, access, payments, legal, tax",
        "reduces context required by the next task",
    ),
}

SECRET_PATTERNS = (
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    re.compile(r"\b(?:sk|ghp|github_pat)_[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{12,}\b", re.IGNORECASE),
)


class GovernanceValidationError(ValueError):
    """Raised when a governance artifact is missing or incomplete."""


def validate(root: pathlib.Path = REPOSITORY_ROOT) -> None:
    """Validate required files, policy clauses, links, and secret hygiene."""
    root = pathlib.Path(root)

    for relative_path, required_phrases in REQUIRED_FILES.items():
        path = root / relative_path
        if not path.is_file():
            raise GovernanceValidationError(f"missing required file: {relative_path}")

        content = path.read_text(encoding="utf-8")
        normalized = " ".join(content.lower().split())
        missing = [phrase for phrase in required_phrases if phrase not in normalized]
        if missing:
            raise GovernanceValidationError(
                f"{relative_path}: missing governance clause: {missing[0]}"
            )

        for pattern in SECRET_PATTERNS:
            if pattern.search(content):
                raise GovernanceValidationError(
                    f"{relative_path}: possible secret or private value"
                )

    agents = (root / "AGENTS.md").read_text(encoding="utf-8")
    for policy_path in ("docs/AI_EXECUTION_POLICY.md", "docs/CHECKPOINT_PROTOCOL.md"):
        if policy_path not in agents:
            raise GovernanceValidationError(f"AGENTS.md: missing link to {policy_path}")


def _copy_governance_files(source: pathlib.Path, destination: pathlib.Path) -> None:
    for relative_path in REQUIRED_FILES:
        target = destination / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / relative_path, target)


def self_test(root: pathlib.Path = REPOSITORY_ROOT) -> None:
    """Run positive and negative checks against isolated fixtures."""
    validate(root)

    with tempfile.TemporaryDirectory() as temp_dir:
        fixture = pathlib.Path(temp_dir)
        _copy_governance_files(root, fixture)

        missing_file = fixture / "docs/CHECKPOINT_PROTOCOL.md"
        missing_file.unlink()
        try:
            validate(fixture)
        except GovernanceValidationError as exc:
            if "missing required file" not in str(exc):
                raise
        else:
            raise GovernanceValidationError("self-test accepted a missing file")

    with tempfile.TemporaryDirectory() as temp_dir:
        fixture = pathlib.Path(temp_dir)
        _copy_governance_files(root, fixture)

        policy = fixture / "docs/AI_EXECUTION_POLICY.md"
        policy.write_text(
            policy.read_text(encoding="utf-8").replace(
                "Stop after the requested artifact is produced",
                "Continue with adjacent work",
            ),
            encoding="utf-8",
        )
        try:
            validate(fixture)
        except GovernanceValidationError as exc:
            if "missing governance clause" not in str(exc):
                raise
        else:
            raise GovernanceValidationError("self-test accepted a missing clause")

    with tempfile.TemporaryDirectory() as temp_dir:
        fixture = pathlib.Path(temp_dir)
        _copy_governance_files(root, fixture)

        template = fixture / ".github/pull_request_template.md"
        test_secret = "gh" + "p_" + ("x" * 20)
        template.write_text(
            template.read_text(encoding="utf-8") + f"\n{test_secret}\n",
            encoding="utf-8",
        )
        try:
            validate(fixture)
        except GovernanceValidationError as exc:
            if "possible secret" not in str(exc):
                raise
        else:
            raise GovernanceValidationError("self-test accepted a secret pattern")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=pathlib.Path,
        default=REPOSITORY_ROOT,
        help="repository root",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run positive validation and isolated negative tests",
    )
    args = parser.parse_args()

    if args.self_test:
        self_test(args.root)
        print("AI execution governance validation passed; 3 self-tests passed.")
    else:
        validate(args.root)
        print(
            "AI execution governance validation passed: "
            f"{len(REQUIRED_FILES)} files checked."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
