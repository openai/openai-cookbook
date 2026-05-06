from __future__ import annotations

import json
import tempfile
import threading
from pathlib import Path
from typing import Any

from .models import Deployment, Project


class Store:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _read(self) -> dict[str, Any]:
        with self._lock:
            return self._read_unlocked()

    def _read_unlocked(self) -> dict[str, Any]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            return {"projects": {}, "deployments": {}}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict[str, Any]) -> None:
        with self._lock:
            self._write_unlocked(data)

    def _write_unlocked(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(data, indent=2) + "\n"
        with tempfile.NamedTemporaryFile(
            "w",
            delete=False,
            dir=self.path.parent,
            encoding="utf-8",
        ) as tmp_file:
            tmp_file.write(payload)
            tmp_path = Path(tmp_file.name)
        tmp_path.replace(self.path)

    def list_projects(self) -> list[Project]:
        data = self._read()
        return [Project.model_validate(value) for value in data["projects"].values()]

    def get_project(self, project_id: str) -> Project | None:
        data = self._read()
        value = data["projects"].get(project_id)
        return Project.model_validate(value) if value else None

    def upsert_project(self, project: Project) -> Project:
        with self._lock:
            data = self._read_unlocked()
            data["projects"][project.id] = project.model_dump()
            self._write_unlocked(data)
        return project

    def list_deployments(self) -> list[Deployment]:
        data = self._read()
        return [
            Deployment.model_validate(value)
            for value in data["deployments"].values()
        ]

    def get_deployment(self, deployment_id: str) -> Deployment | None:
        data = self._read()
        value = data["deployments"].get(deployment_id)
        return Deployment.model_validate(value) if value else None

    def upsert_deployment(self, deployment: Deployment) -> Deployment:
        with self._lock:
            data = self._read_unlocked()
            data["deployments"][deployment.id] = deployment.model_dump()
            self._write_unlocked(data)
        return deployment

    def update_deployment(self, deployment: Deployment) -> Deployment | None:
        with self._lock:
            data = self._read_unlocked()
            if deployment.id not in data["deployments"]:
                return None
            data["deployments"][deployment.id] = deployment.model_dump()
            self._write_unlocked(data)
        return deployment

    def delete_deployment(self, deployment_id: str) -> bool:
        with self._lock:
            data = self._read_unlocked()
            if deployment_id not in data["deployments"]:
                return False
            del data["deployments"][deployment_id]
            self._write_unlocked(data)
        return True
