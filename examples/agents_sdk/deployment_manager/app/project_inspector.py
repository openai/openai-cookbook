from __future__ import annotations

import hashlib
import os
import re
import tomllib
from pathlib import Path

from .models import Project


ENV_PATTERN = re.compile(r"os\.environ\.(?:get|__getitem__)\(\s*[\"']([A-Z0-9_]+)[\"']")
GETENV_PATTERN = re.compile(r"os\.getenv\(\s*[\"']([A-Z0-9_]+)[\"']")
PORT_PATTERN = re.compile(r"os\.environ\.get\(\s*[\"']PORT[\"']\s*,\s*[\"'](\d+)[\"']")


def _project_id(path: Path) -> str:
    digest = hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:10]
    return f"{path.name}-{digest}"


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(errors="ignore")


def _dependencies(pyproject_path: Path | None) -> list[str]:
    if pyproject_path is None or not pyproject_path.exists():
        return []
    payload = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    deps = payload.get("project", {}).get("dependencies", [])
    return [str(dep) for dep in deps]


def _find_env_vars(files: list[Path]) -> tuple[list[str], list[str]]:
    names: set[str] = set()
    for path in files:
        text = _read(path)
        names.update(ENV_PATTERN.findall(text))
        names.update(GETENV_PATTERN.findall(text))
    optional = {"HOST", "PORT", "SANDBOX_BACKEND", "SANDBOX_IMAGE"}
    manager = {
        "AGENTS_SDK_MANAGER",
        "AGENTS_SDK_PROJECT",
        "AGENTS_SDK_PROJECT_ID",
        "AGENTS_SDK_DEPLOYMENT_ID",
        "AGENTS_SDK_DEPLOYMENT_DATA_DIR",
        "AGENTS_SDK_MANAGER_TRACE_ENDPOINT",
    }
    required = sorted(name for name in names if name not in optional | manager)
    optional_found = sorted(name for name in names if name in optional)
    return required, optional_found


def _detect_port(main_path: Path | None) -> int:
    if main_path is None or not main_path.exists():
        return 8421
    match = PORT_PATTERN.search(_read(main_path))
    if not match:
        return 8421
    return int(match.group(1))


def inspect_project(raw_path: str) -> Project:
    project_path = Path(raw_path).expanduser().resolve()
    if not project_path.is_dir():
        raise ValueError(
            f"project path does not exist or is not a directory: {project_path}"
        )

    pyproject_path = project_path / "pyproject.toml"
    pyproject = pyproject_path if pyproject_path.exists() else None
    python_files = sorted(project_path.glob("*.py"))
    main_path = (
        project_path / "main.py" if (project_path / "main.py").exists() else None
    )
    executor_candidates = [
        path
        for path in python_files
        if path.name != "main.py" and "agent" in path.stem.lower()
    ]
    executor_path = executor_candidates[0] if executor_candidates else None
    dependencies = _dependencies(pyproject)
    scanned_files = [
        path for path in [main_path, *executor_candidates] if path is not None
    ]
    if not scanned_files:
        scanned_files = python_files[:5]
    required_env, optional_env = _find_env_vars(scanned_files)
    combined = "\n".join(_read(path) for path in scanned_files)
    uses_sandbox_agent = "SandboxAgent" in combined
    uses_docker_sandbox = (
        "DockerSandboxClient" in combined or "SANDBOX_BACKEND" in combined
    )
    framework = "flask" if "from flask import" in combined else None
    port = _detect_port(main_path)
    run_command = ["uv", "run", "python", "main.py"] if main_path else []

    # OPENAI_API_KEY can be runtime-required even when checked via
    # os.environ.get at call time.
    if "OPENAI_API_KEY" not in required_env and "OPENAI_API_KEY" in combined:
        required_env.append("OPENAI_API_KEY")
        required_env.sort()

    return Project(
        id=_project_id(project_path),
        name=project_path.name,
        path=str(project_path),
        pyproject_path=str(pyproject_path.relative_to(project_path))
        if pyproject
        else None,
        orchestrator_entrypoint=str(main_path.relative_to(project_path))
        if main_path
        else None,
        executor_entrypoint=(
            str(executor_path.relative_to(project_path)) if executor_path else None
        ),
        run_command=run_command,
        app_url=f"http://127.0.0.1:{port}",
        port=port,
        dependencies=dependencies,
        required_env=required_env,
        optional_env=optional_env,
        uses_sandbox_agent=uses_sandbox_agent,
        uses_docker_sandbox=uses_docker_sandbox,
        framework=framework,
        metadata={
            "cwd": os.getcwd(),
            "python_files": [path.name for path in python_files[:20]],
        },
    )
