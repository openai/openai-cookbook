"""Mount the input documents, output artifacts, and policy skill."""

from __future__ import annotations

import os
from pathlib import Path

import docker
from docker.models.containers import Container

EXAMPLE_DIR = Path(__file__).resolve().parent
SKILLS_DIRECTORY = EXAMPLE_DIR / "skills"


def start_executor(
    input_directory: Path, output_directory: Path, environment_id: str, remote_url: str
) -> Container:
    return docker.from_env().containers.run(
        os.environ.get("AGENTS_SANDBOX_IMAGE", "agent-api-sandbox:latest"),
        [
            "codex",
            "exec-server",
            "--remote",
            remote_url,
            "--environment-id",
            environment_id,
        ],
        environment={"CODEX_API_KEY": os.environ["OPENAI_EXECUTOR_API_KEY"]},
        volumes={
            str(input_directory.resolve()): {"bind": "/workspace/input", "mode": "ro"},
            str(output_directory.resolve()): {
                "bind": "/workspace/output",
                "mode": "rw",
            },
            str(SKILLS_DIRECTORY): {"bind": "/workspace/skills", "mode": "ro"},
        },
        detach=True,
        auto_remove=True,
    )
