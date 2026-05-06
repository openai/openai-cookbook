from __future__ import annotations

from pathlib import Path

from .models import Project


DOCKERIGNORE_TEXT = """.venv
node_modules
__pycache__
.ruff_cache
.DS_Store
.env
data
uploads
.run
"""


def dockerfile_text(project: Project) -> str:
    entrypoint = project.orchestrator_entrypoint or "main.py"
    return f"""FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

RUN pip install --no-cache-dir uv

COPY . .
RUN uv sync --no-dev

ENV HOST=0.0.0.0
CMD ["uv", "run", "python", "{entrypoint}"]
"""


def ensure_dockerfile(project: Project) -> Path:
    project_path = Path(project.path)
    dockerfile_path = project_path / "Dockerfile"
    if not dockerfile_path.exists():
        dockerfile_path.write_text(dockerfile_text(project), encoding="utf-8")

    dockerignore_path = project_path / ".dockerignore"
    if not dockerignore_path.exists():
        dockerignore_path.write_text(DOCKERIGNORE_TEXT, encoding="utf-8")

    return dockerfile_path
