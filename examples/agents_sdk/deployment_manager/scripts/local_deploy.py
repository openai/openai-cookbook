#!/usr/bin/env python3
from __future__ import annotations

import argparse
import http.client
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_MANAGER_PORT = 8732


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Deploy a local Agents SDK project through the Deployment Manager."
    )
    parser.add_argument("project_path", nargs="?", default=os.getcwd())
    parser.add_argument("--manager-port", type=int, default=DEFAULT_MANAGER_PORT)
    parser.add_argument("--app-port", type=int)
    parser.add_argument("--name")
    parser.add_argument("--sandbox-backend", default="docker")
    parser.add_argument("--target", default="local-docker", choices=["local-process", "local-docker"])
    parser.add_argument("--no-start", action="store_true")
    args = parser.parse_args()

    project_path = Path(args.project_path).expanduser().resolve()
    manager_root = find_manager_root()
    manager_url = f"http://127.0.0.1:{args.manager_port}"

    if not project_path.exists():
        raise SystemExit(f"Project path does not exist: {project_path}")
    if not manager_root.exists():
        raise SystemExit(f"Deployment Manager not found: {manager_root}")

    layout = inspect_layout(project_path)
    print_layout(project_path, layout)

    if not api_ok(manager_url):
        start_manager(manager_root, args.manager_port)
        wait_for_manager(manager_url)

    project = post_json(manager_url, "/api/projects/import", {"path": str(project_path)})["project"]
    deployment = ensure_deployment(
        manager_url=manager_url,
        project=project,
        target=args.target,
        sandbox_backend=args.sandbox_backend,
        app_port=args.app_port,
        deployment_name=args.name,
    )
    if not args.no_start:
        deployment = post_json(manager_url, f"/api/deployments/{deployment['id']}/start", {})[
            "deployment"
        ]
        if deployment.get("status") == "failed":
            raise SystemExit(deployment.get("error") or "deployment failed")
        wait_for_app(str(deployment.get("app_url") or ""))

    result = {
        "manager_url": manager_url,
        "project": project,
        "deployment": deployment,
        "app_url": deployment.get("app_url"),
    }
    print("\nDeployment ready:")
    print(f"- Manager: {manager_url}")
    print(f"- Deployment: {deployment['id']} ({deployment['status']})")
    if deployment.get("app_url"):
        print(f"- App: {deployment['app_url']}")
    print("\nJSON:")
    print(json.dumps(result, indent=2))
    return 0


def find_manager_root() -> Path:
    env_root = os.environ.get("DEPLOYMENT_MANAGER_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()

    cwd = Path.cwd().resolve()
    if (cwd / "deployment_manager").is_dir():
        return cwd / "deployment_manager"
    if cwd.name == "deployment_manager" and (cwd / "app").is_dir():
        return cwd

    return Path(__file__).resolve().parents[1]


def inspect_layout(project_path: Path) -> dict[str, Any]:
    pyproject_path = project_path / "pyproject.toml"
    main_path = project_path / "main.py"
    agent_paths = [
        path
        for path in sorted(project_path.glob("*.py"))
        if path.name != "main.py" and "agent" in path.stem.lower()
    ]
    pyproject_text = (
        pyproject_path.read_text(encoding="utf-8", errors="replace")
        if pyproject_path.exists()
        else ""
    )
    agent_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace") for path in agent_paths
    )
    return {
        "pyproject": pyproject_path.exists(),
        "main": main_path.exists(),
        "agent_files": [path.name for path in agent_paths],
        "sandbox_agent": "SandboxAgent" in agent_text,
        "openai_agents": "openai-agents" in pyproject_text,
        "uses_uv": pyproject_path.exists(),
    }


def print_layout(project_path: Path, layout: dict[str, Any]) -> None:
    print(f"Project: {project_path}")
    print("Layout:")
    for key, value in layout.items():
        print(f"- {key}: {value}")
    missing = [key for key in ("pyproject", "main", "openai_agents") if not layout[key]]
    if missing:
        print(f"Warning: missing expected Agents SDK layout signals: {', '.join(missing)}")


def start_manager(manager_root: Path, port: int) -> None:
    subprocess.run(
        ["make", "start", f"PORT={port}"],
        cwd=manager_root,
        check=True,
    )


def ensure_deployment(
    *,
    manager_url: str,
    project: dict[str, Any],
    target: str,
    sandbox_backend: str,
    app_port: int | None,
    deployment_name: str | None,
) -> dict[str, Any]:
    deployments = get_json(manager_url, "/api/deployments")["deployments"]
    port = app_port or int(project.get("port") or 8421)
    for deployment in reversed(deployments):
        if (
            deployment.get("project_id") == project["id"]
            and deployment.get("target") == target
            and deployment.get("sandbox_backend") == sandbox_backend
            and int(deployment.get("port") or 0) == port
            and (deployment_name is None or deployment.get("name") == deployment_name)
        ):
            return deployment
    payload: dict[str, Any] = {
        "project_id": project["id"],
        "target": target,
        "sandbox_backend": sandbox_backend,
        "port": port,
    }
    if deployment_name:
        payload["name"] = deployment_name
    return post_json(manager_url, "/api/deployments", payload)["deployment"]


def wait_for_manager(manager_url: str) -> None:
    for _ in range(40):
        if api_ok(manager_url):
            return
        time.sleep(0.5)
    raise SystemExit(f"Deployment Manager did not become healthy: {manager_url}")


def wait_for_app(app_url: str) -> None:
    if not app_url:
        return
    health_url = f"{app_url.rstrip('/')}/health"
    for _ in range(40):
        try:
            request(health_url, timeout=1)
            return
        except (urllib.error.URLError, TimeoutError, http.client.HTTPException, OSError):
            pass
        time.sleep(0.5)
    raise SystemExit(f"App did not become healthy: {health_url}")


def api_ok(manager_url: str) -> bool:
    try:
        payload = get_json(manager_url, "/api/health")
    except urllib.error.URLError:
        return False
    return payload.get("ok") == "true"


def get_json(base_url: str, path: str) -> dict[str, Any]:
    return json.loads(request(f"{base_url}{path}").decode("utf-8"))


def post_json(base_url: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    return json.loads(request(f"{base_url}{path}", data=body, headers=headers).decode("utf-8"))


def request(
    url: str,
    *,
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 10,
) -> bytes:
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.HTTPError as exc:
        sys.stderr.write(exc.read().decode("utf-8", errors="replace") + "\n")
        raise SystemExit(exc.code)
