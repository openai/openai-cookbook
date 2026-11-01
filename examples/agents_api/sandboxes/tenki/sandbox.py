"""Worker lifecycle and executor launch shared by the two Tenki examples."""

from __future__ import annotations

import os
import shlex

from tenki import AsyncClient, AsyncSandbox

WORKSPACE = "/workspace"
SESSION_METADATA_KEY = "agents-session-id"
WORKER_CORES = 2
WORKER_MEMORY_MB = 2048
EXECUTOR_PID_FILE = "/tmp/codex-executor.pid"
EXECUTOR_LOG = "/tmp/codex-executor.log"

# Runs once on the snapshot builder, or once on a worker when no snapshot is
# configured. Tenki's base image ships a Codex CLI at /usr/local/bin/codex; the
# --prefix replaces it with the alpha channel these examples require, and the
# stamp file records the installed version so later launches skip the install.
INSTALL_STAMP = "/home/tenki/.codex-executor-version"
INSTALL_EXECUTOR = (
    f"sudo install -d -o tenki -g tenki {WORKSPACE}"
    " && sudo npm install -g --prefix /usr/local @openai/codex@alpha"
    f" && codex --version > {INSTALL_STAMP}"
)

# Ends an executor started by START_EXECUTOR, if one is still running.
STOP_EXECUTOR = (
    f'if [ -f {EXECUTOR_PID_FILE} ] && kill -0 "$(cat {EXECUTOR_PID_FILE})" 2>/dev/null;'
    f' then kill "$(cat {EXECUTOR_PID_FILE})" && sleep 1; fi'
)

# The inner shell records its own PID, then becomes the executor, so the PID
# file names the executor whether or not setsid forks. The executor is
# detached from this command and from the SDK connection that launched it.
START_EXECUTOR = (
    f"cd {WORKSPACE} && setsid sh -c 'echo $$ > {EXECUTOR_PID_FILE} && exec \"$@\"' sh"
    f" {{args}} >> {EXECUTOR_LOG} 2>&1 </dev/null &"
)

# Fails when the executor exited right after launch, for example on a bad key.
CHECK_EXECUTOR = (
    f'sleep 2; if kill -0 "$(cat {EXECUTOR_PID_FILE})" 2>/dev/null; then exit 0; fi;'
    f" tail -n 5 {EXECUTOR_LOG}; exit 1"
)


def configured_snapshot_id() -> str | None:
    """The golden image built by build_snapshot.py, when one is configured."""
    return os.environ.get("TENKI_SNAPSHOT_ID") or None


async def create_worker(
    client: AsyncClient,
    session_id: str,
    *,
    max_duration: int,
    pause_retention: int,
) -> AsyncSandbox:
    """Create a worker for one Agents API session.

    With TENKI_SNAPSHOT_ID set, the worker restores from the golden image and
    has the Codex CLI the moment it is RUNNING. Inbound traffic is disabled;
    the executor only needs outbound access to OpenAI.
    """
    return await client.create(
        snapshot_id=configured_snapshot_id(),
        name=f"agents-api-{session_id[-12:]}",
        metadata={SESSION_METADATA_KEY: session_id},
        cpu_cores=WORKER_CORES,
        memory_mb=WORKER_MEMORY_MB,
        allow_inbound=False,
        max_duration=max_duration,
        pause_retention=pause_retention,
    )


async def find_worker(client: AsyncClient, session_id: str) -> AsyncSandbox | None:
    """Find the running or paused worker tagged with this session ID."""
    for sandbox in await client.list():
        if (
            sandbox.info.metadata.get(SESSION_METADATA_KEY) == session_id
            and sandbox.state not in {"TERMINATING", "TERMINATED"}
        ):
            return sandbox
    return None


async def ensure_executor_installed(sandbox: AsyncSandbox) -> None:
    """Install the Codex alpha unless this worker already has it (snapshot restores do)."""
    result = await sandbox.exec(
        "sh", "-c", f"test -s {INSTALL_STAMP} || ({INSTALL_EXECUTOR})", timeout=180
    )
    if result.exit_code != 0:
        raise RuntimeError("Executor installation failed")


async def start_executor(
    sandbox: AsyncSandbox,
    remote_url: str,
    environment_id: str,
    executor_key: str,
) -> None:
    """Replace any earlier executor with a fresh one and confirm it stays up.

    The key is passed in the launch command's environment only. It is not part
    of the sandbox definition, so it is not stored with the sandbox or its
    snapshots as configuration.
    """
    args = [
        "codex",
        "exec-server",
        "--remote",
        remote_url,
        "--environment-id",
        environment_id,
    ]
    command = f"{STOP_EXECUTOR}; {START_EXECUTOR.format(args=shlex.join(args))}"
    await sandbox.exec("sh", "-c", command, env={"CODEX_API_KEY": executor_key})
    check = await sandbox.exec("sh", "-c", CHECK_EXECUTOR)
    if check.exit_code != 0:
        raise RuntimeError(f"Executor exited after launch: {check.stdout_text.strip()}")


async def stop_executor(sandbox: AsyncSandbox) -> None:
    """End the executor before pausing, so the resumed worker starts a fresh one."""
    await sandbox.exec("sh", "-c", STOP_EXECUTOR)
