"""Disposable deterministic Git worktrees and explicit, honest runtime isolation."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Protocol

from .policy import PolicyViolation


def scrubbed_environment() -> dict[str, str]:
    result = {
        name: value
        for name in ("PATH", "SYSTEMROOT", "TMPDIR", "LANG", "LC_ALL")
        if (value := os.environ.get(name))
    }
    result.update({
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_AUTHOR_NAME": "Synthetic Autonomy Harness",
        "GIT_AUTHOR_EMAIL": "synthetic@example.invalid",
        "GIT_COMMITTER_NAME": "Synthetic Autonomy Harness",
        "GIT_COMMITTER_EMAIL": "synthetic@example.invalid",
        "GIT_AUTHOR_DATE": "2026-01-01T00:00:00+0000",
        "GIT_COMMITTER_DATE": "2026-01-01T00:00:00+0000",
        "GIT_TERMINAL_PROMPT": "0",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    return result


def git(cwd: Path, *arguments: str, timeout: float = 15.0) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", "-c", f"core.hooksPath={os.devnull}", *arguments],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
            env=scrubbed_environment(),
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as error:
        raise PolicyViolation(f"isolated Git operation failed: {type(error).__name__}") from error


def _git(cwd: Path, *arguments: str, timeout: float = 15.0) -> subprocess.CompletedProcess[str]:
    """Late-bound alias keeps both public and internal Git seams independently auditable."""
    return git(cwd, *arguments, timeout=timeout)


def _initialise_repository(fixture: Path, destination: Path) -> str:
    if not fixture.is_dir():
        raise PolicyViolation(f"fixture repository does not exist: {fixture.name}")
    shutil.copytree(
        fixture,
        destination,
        symlinks=True,
        ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", "*.pyc"),
    )
    _git(destination, "init", "--quiet", "--initial-branch=main")
    _git(destination, "add", "--all")
    _git(destination, "commit", "--quiet", "-m", "Synthetic fixture baseline")
    return _git(destination, "rev-parse", "HEAD").stdout.strip()


def compute_base_sha(fixture: Path) -> str:
    """Return the deterministic SHA that LocalWorktreeRuntime will pin for a plain fixture."""
    with tempfile.TemporaryDirectory(prefix="field-autonomy-base-") as temporary:
        return _initialise_repository(Path(fixture), Path(temporary) / "repository")


@dataclass(frozen=True)
class Workspace:
    repository: Path
    worktree: Path
    base_sha: str
    branch: str
    isolation: str
    executor: ContainerExecutor | None = None


class SandboxRuntime(Protocol):
    isolation: str
    def open(self, fixture: Path, issue_id: str) -> Iterator[Workspace]: ...


class LocalWorktreeRuntime:
    """Disposable checkout isolation only; this is not an OS/network security sandbox."""

    isolation = "local_git_worktree_not_os_sandbox"

    @contextmanager
    def open(self, fixture: Path, issue_id: str) -> Iterator[Workspace]:
        with tempfile.TemporaryDirectory(prefix="field-autonomy-") as temporary:
            temporary_root = Path(temporary)
            repository = temporary_root / "repository"
            worktree = temporary_root / "worktree"
            base_sha = _initialise_repository(Path(fixture), repository)
            safe_issue = "".join(value for value in issue_id.lower() if value.isalnum() or value == "-")
            branch = f"agent/{safe_issue or 'issue'}-{uuid.uuid4().hex[:8]}"
            _git(repository, "worktree", "add", "--quiet", "-b", branch, str(worktree), base_sha)
            try:
                yield Workspace(repository, worktree, base_sha, branch, self.isolation)
            finally:
                if worktree.exists():
                    _git(repository, "worktree", "remove", "--force", str(worktree))


class ContainerRuntime:
    """Host-owned Git/patch control and genuinely isolated candidate execution."""

    isolation = "docker_isolated_no_network_read_only_non_root"

    def __init__(self, configuration: ContainerConfiguration | None = None) -> None:
        self.configuration = configuration or ContainerConfiguration()

    def _validate_daemon_and_image(self) -> None:
        if not shutil.which("docker"):
            raise PolicyViolation("container runtime is unavailable; local worktree fallback is prohibited")
        commands = (
            (["docker", "info", "--format", "{{.ServerVersion}}"], "container daemon is not running"),
            (
                ["docker", "image", "inspect", self.configuration.image, "--format", "{{.Id}}"],
                "approved container image is not cached locally; automatic image pulls are prohibited",
            ),
        )
        for command, failure in commands:
            try:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=8,
                    check=False,
                    shell=False,
                    env=scrubbed_environment(),
                )
            except (OSError, subprocess.TimeoutExpired) as error:
                raise PolicyViolation("container runtime cannot be validated; no fallback is allowed") from error
            if result.returncode != 0 or not result.stdout.strip():
                raise PolicyViolation(f"{failure}; no worktree fallback is allowed")

    @contextmanager
    def open(self, fixture: Path, issue_id: str) -> Iterator[Workspace]:
        self._validate_daemon_and_image()
        trusted_fixture = Path(fixture).resolve()
        trusted_tests = trusted_fixture / "tests"
        if trusted_tests.is_symlink() or not trusted_tests.is_dir():
            raise PolicyViolation("protected acceptance fixture is unavailable or is a symbolic link")
        with LocalWorktreeRuntime().open(trusted_fixture, issue_id) as local:
            source = local.worktree / "src"
            if source.is_symlink() or not source.is_dir():
                raise PolicyViolation("candidate source mount is unavailable or is a symbolic link")
            scratch = local.repository.parent / "execution-scratch"
            scratch.mkdir(mode=0o777)
            scratch.chmod(0o777)
            executor = ContainerExecutor(source, trusted_tests, scratch, self.configuration)
            workspace = Workspace(
                local.repository,
                local.worktree,
                local.base_sha,
                local.branch,
                self.isolation,
                executor,
            )
            try:
                yield workspace
            finally:
                executor.close()


@dataclass(frozen=True)
class ContainerConfiguration:
    """Small, inspectable host policy; image pulls and privilege relaxation are absent."""

    image: str = "python:3.12-alpine"
    uid: int = 65532
    gid: int = 65532
    pids_limit: int = 64
    memory_bytes: int = 256 * 1024 * 1024
    cpus: str = "0.50"
    temporary_bytes: int = 32 * 1024 * 1024
    max_output_bytes: int = 64 * 1024

    def __post_init__(self) -> None:
        if self.image != "python:3.12-alpine":
            raise PolicyViolation("only the explicitly approved cached Python Alpine image is permitted")
        if self.uid == 0 or self.gid == 0 or self.uid < 0 or self.gid < 0:
            raise PolicyViolation("container execution must use a non-root user and group")
        if not 1 <= self.pids_limit <= 128:
            raise PolicyViolation("container process limit must remain between 1 and 128")
        if not 16 * 1024 * 1024 <= self.memory_bytes <= 512 * 1024 * 1024:
            raise PolicyViolation("container memory limit must remain between 16 MiB and 512 MiB")
        try:
            cpu_limit = float(self.cpus)
        except (TypeError, ValueError) as error:
            raise PolicyViolation("container CPU limit is invalid") from error
        if not 0 < cpu_limit <= 1:
            raise PolicyViolation("container CPU limit must remain above zero and at most one core")
        if not 1 <= self.temporary_bytes <= 64 * 1024 * 1024:
            raise PolicyViolation("container temporary-filesystem limit is invalid")


@dataclass
class ContainerExecutor:
    """Run only host-selected argv inside one short-lived, restricted Docker container."""

    source: Path
    protected_tests: Path
    scratch: Path
    configuration: ContainerConfiguration
    container_names: list[str] = field(default_factory=list)

    @staticmethod
    def _bind(source: Path, target: str, *, readonly: bool) -> str:
        resolved = source.resolve(strict=True)
        if "," in str(resolved):
            raise PolicyViolation("container mount source contains an unsupported separator")
        options = f"type=bind,source={resolved},target={target}"
        return options + (",readonly" if readonly else "")

    def command(self, arguments: list[str], name: str) -> list[str]:
        if not arguments or not all(isinstance(value, str) and value for value in arguments):
            raise PolicyViolation("container execution requires a non-empty, host-selected argument vector")
        config = self.configuration
        return [
            "docker", "run", "--rm", "--pull", "never", "--name", name,
            "--network", "none", "--read-only", "--user", f"{config.uid}:{config.gid}",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--pids-limit", str(config.pids_limit),
            "--memory", str(config.memory_bytes), "--memory-swap", str(config.memory_bytes),
            "--cpus", config.cpus,
            "--ulimit", "nofile=128:128", "--ulimit", "fsize=1048576:1048576",
            "--tmpfs", f"/tmp:rw,noexec,nosuid,nodev,size={config.temporary_bytes},mode=1777",
            "--mount", self._bind(self.source, "/workspace/src", readonly=True),
            "--mount", self._bind(self.protected_tests, "/workspace/tests", readonly=True),
            "--mount", self._bind(self.scratch, "/workspace/.scratch", readonly=False),
            "--workdir", "/workspace",
            "--env", "PYTHONDONTWRITEBYTECODE=1", "--env", "PYTHONIOENCODING=utf-8",
            config.image, *arguments,
        ]

    def _inspect(self, name: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["docker", "container", "inspect", name, "--format", "{{.State.Status}}"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
            shell=False,
            env=scrubbed_environment(),
        )

    def _remove(self, name: str) -> None:
        try:
            subprocess.run(
                ["docker", "container", "rm", "--force", name],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
                shell=False,
                env=scrubbed_environment(),
            )
            inspection = self._inspect(name)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise PolicyViolation("restricted container cleanup could not be verified") from error
        if inspection.returncode == 0:
            raise PolicyViolation("restricted container remained present after forced cleanup")

    def run(self, arguments: list[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        if not isinstance(timeout, (int, float)) or timeout <= 0 or timeout > 60:
            raise PolicyViolation("restricted container timeout must be greater than zero and at most 60 seconds")
        name = "field-autonomy-" + uuid.uuid4().hex
        self.container_names.append(name)
        command = self.command(arguments, name)
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                shell=False,
                env=scrubbed_environment(),
            )
        except subprocess.TimeoutExpired:
            self._remove(name)
            raise
        except OSError as error:
            self._remove(name)
            raise PolicyViolation("restricted container could not be started") from error
        if len(result.stdout.encode("utf-8")) + len(result.stderr.encode("utf-8")) > self.configuration.max_output_bytes:
            raise PolicyViolation("restricted container output exceeded its configured evidence ceiling")
        return result

    def close(self) -> None:
        for name in self.container_names:
            try:
                inspection = self._inspect(name)
            except (OSError, subprocess.TimeoutExpired) as error:
                raise PolicyViolation("restricted container cleanup could not be verified") from error
            if inspection.returncode == 0:
                self._remove(name)
                raise PolicyViolation("restricted container required unexpected forced cleanup")


def read_diff(worktree: Path) -> tuple[str, tuple[str, ...]]:
    untracked = _git(worktree, "ls-files", "--others", "--exclude-standard", "--", ".").stdout.splitlines()
    if untracked:
        for path in untracked:
            _git(worktree, "add", "--intent-to-add", "--", path)
    tracked_diff = _git(worktree, "diff", "--", ".").stdout
    tracked = _git(worktree, "diff", "--name-only", "--", ".").stdout.splitlines()
    return tracked_diff, tuple(path for path in tracked if path)
