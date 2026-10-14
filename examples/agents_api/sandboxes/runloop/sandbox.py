"""Executor installation and launch shared by the Runloop examples."""

import shlex

from runloop_api_client.lib.polling import PollingConfig
from runloop_api_client.sdk.async_devbox import AsyncDevbox
from runloop_api_client.sdk.async_execution import AsyncExecution

CODEX = "/home/user/.codex-runtime/node_modules/.bin/codex"
LOCK_BUSY_EXIT_CODE = 75


async def install_executor(devbox: AsyncDevbox) -> None:
    setup = await devbox.cmd.exec(
        "mkdir -p /home/user/.codex-runtime && "
        f"(test -x {CODEX} || "
        "npm install --prefix /home/user/.codex-runtime @openai/codex@alpha)",
        polling_config=PollingConfig(timeout_seconds=180),
    )
    if setup.exit_code != 0:
        raise RuntimeError("Executor installation failed")


async def start_executor(
    devbox: AsyncDevbox,
    *,
    workspace: str,
    remote_url: str,
    environment_id: str,
    locked: bool = False,
) -> AsyncExecution:
    command = shlex.join(
        [
            CODEX,
            "exec-server",
            "--remote",
            remote_url,
            "--environment-id",
            environment_id,
        ]
    )
    if locked:
        command = (
            f"flock -n -E {LOCK_BUSY_EXIT_CODE} /tmp/codex-executor.lock {command} "
            ">> /tmp/codex-executor.log 2>&1"
        )
    else:
        command = f"exec {command}"
    return await devbox.cmd.exec_async(f"cd {shlex.quote(workspace)} && {command}")
