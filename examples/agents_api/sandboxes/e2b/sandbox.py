"""Executor setup and launch shared by the two E2B examples."""

import shlex

from e2b import AsyncSandbox

WORKSPACE = "/workspace"


async def install_executor(sandbox: AsyncSandbox, *, reconnect: bool = False) -> None:
    install = "npm install -g @openai/codex@alpha"
    if reconnect:
        install = f"(command -v codex || {install}) && command -v flock"
    await sandbox.commands.run(
        f"mkdir -p {WORKSPACE} && {install}", user="root", timeout=180
    )


async def start_executor(
    sandbox: AsyncSandbox,
    remote_url: str,
    environment_id: str,
    *,
    executor_key: str | None = None,
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
        args = ["flock", "-n", "/tmp/codex-executor.lock", *args]
    command = shlex.join(args)
    if reconnect:
        command += " >> /tmp/codex-executor.log 2>&1"
    # Webhook workers inherit the restricted key from sandbox creation.
    envs = {"CODEX_API_KEY": executor_key} if executor_key is not None else None
    await sandbox.commands.run(
        command,
        envs=envs,
        user="root",
        cwd=WORKSPACE,
        background=True,
        timeout=0,
    )
