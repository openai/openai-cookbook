from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


class ImportProjectRequest(BaseModel):
    path: str


class CreateDeploymentRequest(BaseModel):
    project_id: str
    name: str | None = None
    target: Literal["local-process", "local-docker"] = "local-docker"
    port: int | None = None
    sandbox_backend: str = "docker"


class Project(BaseModel):
    id: str
    name: str
    path: str
    pyproject_path: str | None = None
    orchestrator_entrypoint: str | None = None
    executor_entrypoint: str | None = None
    run_command: list[str] = Field(default_factory=list)
    app_url: str | None = None
    port: int = 8421
    package_manager: str = "uv"
    dependencies: list[str] = Field(default_factory=list)
    required_env: list[str] = Field(default_factory=list)
    optional_env: list[str] = Field(default_factory=list)
    uses_sandbox_agent: bool = False
    uses_docker_sandbox: bool = False
    framework: str | None = None
    created_at: str = Field(default_factory=now_iso)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Deployment(BaseModel):
    id: str
    project_id: str
    name: str
    target: Literal["local-process", "local-docker"]
    status: Literal["draft", "starting", "running", "stopped", "failed"] = "draft"
    port: int = 8421
    sandbox_backend: str = "docker"
    requires_docker_socket: bool = False
    process_pid: int | None = None
    container_id: str | None = None
    container_name: str | None = None
    image_tag: str | None = None
    log_path: str | None = None
    dockerfile_path: str | None = None
    data_path: str | None = None
    app_url: str | None = None
    error: str | None = None
    created_at: str = Field(default_factory=now_iso)
    started_at: str | None = None
    stopped_at: str | None = None


class TimelineEvent(BaseModel):
    id: str
    timestamp: str
    source: str
    type: str
    message: str
    level: str = "info"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContainerInfo(BaseModel):
    id: str
    name: str
    image: str
    status: str
    created_at: str | None = None
    role: str = "observed"
    labels: dict[str, str] = Field(default_factory=dict)


class SessionInfo(BaseModel):
    id: str
    deployment_id: str
    project_id: str
    deployment_name: str | None = None
    project_name: str | None = None
    expense_id: str
    status: str
    event_count: int
    trace_id: str | None = None
    trace_url: str | None = None
    started_at: str | None = None
    updated_at: str | None = None
