"""Base image and executor command shared by the two Modal examples."""

import modal

WORKSPACE = "/workspace"


def executor_image(python_version: str = "3.12") -> modal.Image:
    return (
        modal.Image.debian_slim(python_version=python_version)
        .apt_install("nodejs", "npm", "git", "ripgrep")
        .run_commands("npm install -g @openai/codex@alpha", f"mkdir -p {WORKSPACE}")
        .workdir(WORKSPACE)
    )


def exec_server_command(environment_id: str, remote_url: str) -> list[str]:
    return [
        "codex",
        "exec-server",
        "--remote",
        remote_url,
        "--environment-id",
        environment_id,
    ]
