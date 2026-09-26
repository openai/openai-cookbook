"""Executor setup and launch shared by the two Blaxel examples."""

import shlex

from blaxel.core.sandbox import SandboxInstance

WORKSPACE = "/workspace"


async def install_executor(
    sandbox: SandboxInstance, *, reconnect: bool = False
) -> None:
    command = "mkdir -p /workspace && npm install -g @openai/codex@alpha"
    if reconnect:
        command = (
            "mkdir -p /workspace && "
            "(command -v codex || npm install -g @openai/codex@alpha) && "
            "(command -v rg || apk add --no-cache ripgrep util-linux)"
        )
    result = await sandbox.process.exec(
        {
            "command": command,
            "wait_for_completion": True,
            "timeout": 120 if reconnect else 180,
        }
    )
    if result.exit_code != 0:
        raise RuntimeError("Executor installation failed")


async def start_executor(
    sandbox: SandboxInstance,
    remote_url: str,
    environment_id: str,
    executor_key: str,
    *,
    reconnect: bool = False,
) -> None:
    args = [
        "codex",
        "exec-server",
        "--remote",
        remote_url,
        "--environment-id",
        environment_id,
    ]
    if reconnect:
        # The controller serializes jobs; flock also prevents duplicate executors.
        args = ["flock", "-n", "/tmp/codex-executor.lock", *args]
    await sandbox.process.exec(
        {
            "command": shlex.join(args),
            "working_dir": WORKSPACE,
            "env": {"CODEX_API_KEY": executor_key},
            "wait_for_completion": False,
            "keep_alive": True,
            "timeout": 1800 if reconnect else 600,
        }
    )
