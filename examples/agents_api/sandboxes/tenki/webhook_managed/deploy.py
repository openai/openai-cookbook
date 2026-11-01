# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "tenki[async]>=1.4.1",
# ]
# ///

"""Deploy a signature-protected controller in a dedicated Tenki sandbox."""

from __future__ import annotations

import asyncio
import os
import shlex
from pathlib import Path

from tenki import AsyncClient, AsyncSandbox

ROOT = Path(__file__).parent
CONTROLLER_METADATA = {"agents-webhook-controller": "tenki"}
CONTROLLER_NAME = "agents-api-webhook-tenki"
CONTROLLER_PORT = 8000
HOME = "/home/tenki"
APP_DIR = f"{HOME}/controller"
VENV = f"{APP_DIR}/.venv"
PID_FILE = f"{APP_DIR}/controller.pid"
LOG_FILE = f"{APP_DIR}/controller.log"


def home_relative(path: str) -> str:
    # SDK file calls are confined to the sandbox user's home and take relative paths.
    return path.removeprefix(f"{HOME}/")


async def find_controller(client: AsyncClient) -> AsyncSandbox | None:
    for sandbox in await client.list(sticky=True):
        if sandbox.info.metadata.get("agents-webhook-controller") == "tenki":
            return sandbox
    return None


async def main() -> None:
    values = {
        key: os.environ[key]
        for key in [
            "OPENAI_API_KEY",
            "OPENAI_EXECUTOR_API_KEY",
            "OPENAI_AGENT_ID",
            "TENKI_API_KEY",
        ]
    }
    if "TENKI_SNAPSHOT_ID" in os.environ:
        values["TENKI_SNAPSHOT_ID"] = os.environ["TENKI_SNAPSHOT_ID"]
    values["OPENAI_WEBHOOK_SECRET"] = os.environ.get(
        "OPENAI_WEBHOOK_SECRET", "pending-webhook-registration"
    )
    async with AsyncClient() as client:
        sandbox = await find_controller(client)
        if sandbox is None:
            # sticky: the controller runs until terminated, with no lifetime limit.
            sandbox = await client.create(
                name=CONTROLLER_NAME,
                metadata=CONTROLLER_METADATA,
                cpu_cores=1,
                memory_mb=1024,
                sticky=True,
            )
        elif sandbox.state == "PAUSED":
            await sandbox.resume()
            await sandbox.wait_ready()
        await sandbox.fs.mkdir(home_relative(f"{APP_DIR}/webhook_managed"))
        await sandbox.fs.write_text(
            home_relative(f"{APP_DIR}/webhook_managed/handler.py"),
            ROOT.joinpath("handler.py").read_text(),
        )
        await sandbox.fs.write_text(
            home_relative(f"{APP_DIR}/sandbox.py"),
            ROOT.parent.joinpath("sandbox.py").read_text(),
        )
        install = await sandbox.exec(
            "sh",
            "-c",
            f"test -x {VENV}/bin/python || python3 -m venv {VENV}"
            f" && {VENV}/bin/pip install --quiet uv"
            f" && {VENV}/bin/uv pip install --quiet --python {VENV}/bin/python"
            f" -r {APP_DIR}/webhook_managed/handler.py",
            timeout=300,
        )
        if install.exit_code != 0:
            raise RuntimeError(f"Controller dependency installation failed: {install.stderr_text.strip()}")
        serve = shlex.join(
            [
                f"{VENV}/bin/python",
                "-m",
                "uvicorn",
                "handler:app",
                "--host",
                "0.0.0.0",
                "--port",
                str(CONTROLLER_PORT),
            ]
        )
        # Secrets travel in this command's environment only; a restart needs a redeploy.
        await sandbox.exec(
            "sh",
            "-c",
            f'if [ -f {PID_FILE} ] && kill -0 "$(cat {PID_FILE})" 2>/dev/null; then kill "$(cat {PID_FILE})" && sleep 1; fi;'
            f" cd {APP_DIR}/webhook_managed && setsid sh -c 'echo $$ > {PID_FILE} && exec \"$@\"' sh"
            f" {serve} >> {LOG_FILE} 2>&1 </dev/null &",
            env=values,
        )
        check = await sandbox.exec(
            "sh",
            "-c",
            f'sleep 2; kill -0 "$(cat {PID_FILE})" 2>/dev/null || {{ tail -n 5 {LOG_FILE}; exit 1; }}',
        )
        if check.exit_code != 0:
            raise RuntimeError(f"Controller exited after launch: {check.stdout_text.strip()}")
        exposed = next(
            (p for p in await sandbox.list_exposed_ports() if p.port == CONTROLLER_PORT),
            None,
        ) or await sandbox.expose_port(CONTROLLER_PORT)
        print(f"Webhook: {exposed.url}/webhook")
        print(f"Controller: {sandbox.id} (runs until terminated; redeploy to update)")


if __name__ == "__main__":
    asyncio.run(main())
