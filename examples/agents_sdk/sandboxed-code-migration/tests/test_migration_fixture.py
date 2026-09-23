from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from src.run_migration_agent import DEFAULT_MIGRATION_TASKS, build_manifest


EXAMPLE_ROOT = Path(__file__).resolve().parents[1]


def run_in_fixture(repo_path: Path, command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=repo_path,
        check=False,
        text=True,
        capture_output=True,
    )


def test_repo_fixtures_start_with_passing_legacy_tests() -> None:
    for task in DEFAULT_MIGRATION_TASKS:
        result = run_in_fixture(
            task.repo_path,
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."],
        )

        assert result.returncode == 0, result.stdout + result.stderr


def test_repo_fixtures_pass_compile_check() -> None:
    for task in DEFAULT_MIGRATION_TASKS:
        result = run_in_fixture(
            task.repo_path,
            [sys.executable, "-m", "compileall", "-q", "."],
        )

        assert result.returncode == 0, result.stdout + result.stderr


def test_migration_manifest_mounts_repo_and_agent_instructions() -> None:
    manifest = build_manifest(DEFAULT_MIGRATION_TASKS[0])

    assert manifest.root == "/workspace"
    assert "repo" in manifest.entries
    assert "migration_agent/AGENTS.md" in manifest.entries
