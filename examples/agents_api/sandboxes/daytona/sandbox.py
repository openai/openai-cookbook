"""Executor setup and launch shared by the two Daytona examples."""

import shlex

from daytona import AsyncSandbox, DaytonaNotFoundError, SessionExecuteRequest

WORKSPACE = "/workspace"
CODEX = "/home/daytona/.local/bin/codex"


async def install_executor(sandbox: AsyncSandbox, *, reconnect: bool = False) -> None:
    install = "npm install -g --prefix /home/daytona/.local @openai/codex@alpha"
    if reconnect:
        install = f"(test -x {CODEX} || {install}) && command -v flock"
    result = await sandbox.process.exec(
        f"sudo install -d -o daytona -g daytona {WORKSPACE} && {install}",
        timeout=180,
    )
    if result.exit_code != 0:
        raise RuntimeError("Executor installation failed")


async def start_executor(
    sandbox: AsyncSandbox,
    remote_url: str,
    environment_id: str,
    *,
    reconnect: bool = False,
) -> None:
    if reconnect:
        try:
            await sandbox.process.get_session("executor")
        except DaytonaNotFoundError:
            await sandbox.process.create_session("executor")
    else:
        await sandbox.process.create_session("executor")
    args = [
        CODEX,
        "exec-server",
        "--remote",
        remote_url,
        "--environment-id",
        environment_id,
    ]
    if reconnect:
        # flock makes retries safe while an executor is already running.
        args = ["flock", "-n", "/tmp/codex-executor.lock", *args]
        command = f"{shlex.join(args)} >> /tmp/codex-executor.log 2>&1"
    else:
        command = f"exec {shlex.join(args)}"
    await sandbox.process.execute_session_command(
        "executor",
        SessionExecuteRequest(command=f"cd {WORKSPACE} && {command}", run_async=True),
    )
