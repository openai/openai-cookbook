from __future__ import annotations

import os
import shutil
import signal
import socket
import subprocess
import time
from pathlib import Path

from .dockerfile_writer import ensure_dockerfile
from .models import Deployment, Project, now_iso

RESERVED_CONTAINER_ENV = {
    "HOST",
    "PORT",
    "SANDBOX_BACKEND",
    "AGENTS_SDK_MANAGER",
    "AGENTS_SDK_PROJECT",
    "AGENTS_SDK_PROJECT_ID",
    "AGENTS_SDK_DEPLOYMENT_ID",
    "AGENTS_SDK_DEPLOYMENT_DATA_DIR",
    "AGENTS_SDK_MANAGER_TRACE_ENDPOINT",
    "PYTHONPATH",
}
TRACE_CAPTURE_RUNTIME = (
    Path(__file__).resolve().parents[1] / "runtime" / "trace_capture"
)


def _is_running(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _port_is_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.25):
            return True
    except OSError:
        return False


def _run_dir(state_root: Path, deployment: Deployment) -> Path:
    run_dir = state_root / "deployments" / deployment.id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _data_dir(state_root: Path, deployment: Deployment) -> Path:
    data_dir = _run_dir(state_root, deployment) / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def _seed_data_dir(project: Project, data_dir: Path) -> None:
    source = Path(project.path) / "data"
    if not source.is_dir() or any(data_dir.iterdir()):
        return
    for item in source.iterdir():
        target = data_dir / item.name
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)


def _pythonpath_with_trace_capture(existing: str | None, runtime_path: str) -> str:
    if existing:
        return f"{runtime_path}{os.pathsep}{existing}"
    return runtime_path


def _manager_trace_endpoint(target: str) -> str:
    port = os.environ.get("PORT", "8732")
    host = "host.docker.internal" if target == "local-docker" else "127.0.0.1"
    return f"http://{host}:{port}/api/traces/ingest"


def _slug(value: str) -> str:
    slug = "".join(char.lower() if char.isalnum() else "-" for char in value).strip("-")
    return "-".join(part for part in slug.split("-") if part)


def _container_name(project: Project, deployment: Deployment) -> str:
    display_name = (
        project.name if deployment.name == f"{project.name} local" else deployment.name
    )
    return _slug(display_name)


def _image_tag(project: Project, deployment: Deployment) -> str:
    safe_name = "".join(
        char if char.isalnum() else "-" for char in project.name.lower()
    ).strip("-")
    return deployment.image_tag or f"agents-sdk/{safe_name}:{deployment.id}"


def _docker_output(
    args: list[str], *, timeout: int = 10
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


def _container_is_running(container_id: str | None) -> bool:
    if not container_id:
        return False
    try:
        completed = _docker_output(
            ["inspect", "-f", "{{.State.Running}}", container_id]
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0 and completed.stdout.strip() == "true"


def _remove_managed_container(container: str | None, deployment_id: str) -> None:
    if not container:
        return
    try:
        completed = _docker_output(
            [
                "inspect",
                "-f",
                "{{ index .Config.Labels \"agents-sdk.manager\" }} {{ index .Config.Labels \"agents-sdk.deployment-id\" }}",
                container,
            ]
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return
    if completed.returncode != 0:
        return
    if completed.stdout.strip() != f"true {deployment_id}":
        return
    try:
        _docker_output(["rm", "-f", container], timeout=20)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass


def refresh_status(deployment: Deployment) -> Deployment:
    if deployment.target == "local-docker" and deployment.status == "running":
        if not _container_is_running(
            deployment.container_id or deployment.container_name
        ):
            deployment.status = "stopped"
            deployment.stopped_at = deployment.stopped_at or now_iso()
        return deployment
    if deployment.process_pid and deployment.status == "running":
        if not _is_running(deployment.process_pid):
            deployment.status = "stopped"
            deployment.stopped_at = deployment.stopped_at or now_iso()
    return deployment


def start_local_process(
    state_root: Path,
    project: Project,
    deployment: Deployment,
) -> Deployment:
    deployment = refresh_status(deployment)
    if deployment.status == "running" and _is_running(deployment.process_pid):
        return deployment
    if not project.run_command:
        raise RuntimeError("project does not have a runnable command")
    if _port_is_open(deployment.port):
        raise RuntimeError(f"port {deployment.port} is already in use")

    run_dir = _run_dir(state_root, deployment)
    data_dir = _data_dir(state_root, deployment)
    _seed_data_dir(project, data_dir)
    log_path = run_dir / "orchestrator.log"
    env = os.environ.copy()
    env.update(
        {
            "HOST": "127.0.0.1",
            "PORT": str(deployment.port),
            "SANDBOX_BACKEND": deployment.sandbox_backend,
            "AGENTS_SDK_MANAGER": "true",
            "AGENTS_SDK_PROJECT": project.name,
            "AGENTS_SDK_PROJECT_ID": project.id,
            "AGENTS_SDK_DEPLOYMENT_ID": deployment.id,
            "AGENTS_SDK_DEPLOYMENT_DATA_DIR": str(data_dir),
            "AGENTS_SDK_MANAGER_TRACE_ENDPOINT": _manager_trace_endpoint(
                "local-process"
            ),
            "PYTHONPATH": _pythonpath_with_trace_capture(
                env.get("PYTHONPATH"), str(TRACE_CAPTURE_RUNTIME)
            ),
        }
    )
    handle = log_path.open("ab")
    process = subprocess.Popen(
        project.run_command,
        cwd=project.path,
        env=env,
        stdout=handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    deployment.status = "running"
    deployment.process_pid = process.pid
    deployment.log_path = str(log_path)
    deployment.data_path = str(data_dir)
    deployment.app_url = f"http://127.0.0.1:{deployment.port}"
    deployment.started_at = now_iso()
    deployment.stopped_at = None
    deployment.error = None

    for _ in range(20):
        if _port_is_open(deployment.port):
            return deployment
        if process.poll() is not None:
            raise RuntimeError(
                read_log(str(log_path), limit=12000)
                or "process exited before listening"
            )
        time.sleep(0.25)
    return deployment


def start_local_docker(
    state_root: Path,
    project: Project,
    deployment: Deployment,
) -> Deployment:
    deployment = refresh_status(deployment)
    if deployment.status == "running" and _container_is_running(
        deployment.container_id or deployment.container_name
    ):
        return deployment
    if _port_is_open(deployment.port):
        raise RuntimeError(f"port {deployment.port} is already in use")

    run_dir = _run_dir(state_root, deployment)
    data_dir = _data_dir(state_root, deployment)
    _seed_data_dir(project, data_dir)
    uploads_dir = data_dir / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / "orchestrator.log"
    dockerfile_path = ensure_dockerfile(project)
    image_tag = _image_tag(project, deployment)
    container_name = _container_name(project, deployment)

    build = _docker_output(
        ["build", "-t", image_tag, "-f", str(dockerfile_path), str(project.path)],
        timeout=180,
    )
    log_path.write_text((build.stdout or "") + (build.stderr or ""), encoding="utf-8")
    if build.returncode != 0:
        raise RuntimeError(
            read_log(str(log_path), limit=12000) or "docker build failed"
        )

    _remove_managed_container(container_name, deployment.id)

    env_args = [
        "-e",
        "HOST=0.0.0.0",
        "-e",
        f"PORT={deployment.port}",
        "-e",
        f"SANDBOX_BACKEND={deployment.sandbox_backend}",
        "-e",
        "AGENTS_SDK_MANAGER=true",
        "-e",
        f"AGENTS_SDK_PROJECT={project.name}",
        "-e",
        f"AGENTS_SDK_PROJECT_ID={project.id}",
        "-e",
        f"AGENTS_SDK_DEPLOYMENT_ID={deployment.id}",
        "-e",
        "AGENTS_SDK_DEPLOYMENT_DATA_DIR=/app/.agents-deployment-data",
        "-e",
        f"AGENTS_SDK_MANAGER_TRACE_ENDPOINT={_manager_trace_endpoint('local-docker')}",
        "-e",
        "PYTHONPATH=/app/.agents-manager-pythonpath",
    ]
    for name in sorted(
        set(
            project.required_env
            + project.optional_env
            + ["OPENAI_API_KEY", "SANDBOX_IMAGE"]
        )
    ):
        if name in RESERVED_CONTAINER_ENV:
            continue
        value = os.environ.get(name)
        if value:
            env_args.extend(["-e", f"{name}={value}"])

    volume_args = [
        "-v",
        f"{TRACE_CAPTURE_RUNTIME}:/app/.agents-manager-pythonpath:ro",
        "-v",
        f"{data_dir}:/app/.agents-deployment-data",
        "-v",
        f"{data_dir}:/app/data",
        "-v",
        f"{uploads_dir}:/app/uploads",
    ]
    if deployment.requires_docker_socket:
        volume_args.extend(["-v", "/var/run/docker.sock:/var/run/docker.sock"])

    run = _docker_output(
        [
            "run",
            "-d",
            "--name",
            container_name,
            "--label",
            "agents-sdk.manager=true",
            "--label",
            f"agents-sdk.project={project.name}",
            "--label",
            f"agents-sdk.deployment-id={deployment.id}",
            "--label",
            "agents-sdk.role=orchestrator",
            "-p",
            f"127.0.0.1:{deployment.port}:{deployment.port}",
            *env_args,
            *volume_args,
            image_tag,
        ],
        timeout=30,
    )
    if run.returncode != 0:
        log_path.write_text(
            read_log(str(log_path)) + "\n" + (run.stdout or "") + (run.stderr or ""),
            encoding="utf-8",
        )
        raise RuntimeError(read_log(str(log_path), limit=12000) or "docker run failed")

    deployment.status = "running"
    deployment.container_id = run.stdout.strip()
    deployment.container_name = container_name
    deployment.image_tag = image_tag
    deployment.dockerfile_path = str(dockerfile_path)
    deployment.process_pid = None
    deployment.log_path = str(log_path)
    deployment.data_path = str(data_dir)
    deployment.app_url = f"http://127.0.0.1:{deployment.port}"
    deployment.started_at = now_iso()
    deployment.stopped_at = None
    deployment.error = None

    for _ in range(40):
        if _port_is_open(deployment.port):
            return deployment
        if not _container_is_running(deployment.container_id):
            raise RuntimeError(
                read_deployment_log(deployment, limit=12000)
                or "container exited before listening"
            )
        time.sleep(0.25)
    return deployment


def stop_local_process(deployment: Deployment) -> Deployment:
    if deployment.process_pid and _is_running(deployment.process_pid):
        try:
            os.killpg(deployment.process_pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deployment.status = "stopped"
    deployment.stopped_at = now_iso()
    return deployment


def stop_local_docker(deployment: Deployment) -> Deployment:
    _remove_managed_container(
        deployment.container_id or deployment.container_name,
        deployment.id,
    )
    deployment.status = "stopped"
    deployment.stopped_at = now_iso()
    return deployment


def read_log(path: str | None, *, limit: int = 60000) -> str:
    if not path:
        return ""
    log_path = Path(path)
    if not log_path.exists():
        return ""
    data = log_path.read_bytes()
    return data[-limit:].decode("utf-8", errors="replace")


def read_deployment_log(deployment: Deployment, *, limit: int = 60000) -> str:
    if deployment.target == "local-docker" and (
        deployment.container_id or deployment.container_name
    ):
        try:
            completed = _docker_output(
                [
                    "logs",
                    "--tail",
                    str(max(1, limit // 120)),
                    deployment.container_id or deployment.container_name or "",
                ],
                timeout=5,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return read_log(deployment.log_path, limit=limit)
        output = (completed.stdout or "") + (completed.stderr or "")
        if output:
            return output[-limit:]
    return read_log(deployment.log_path, limit=limit)
