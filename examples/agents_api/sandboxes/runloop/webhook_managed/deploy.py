# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "runloop-api-client>=1.31.0",
# ]
# ///

"""Deploy a signature-protected controller in a dedicated Runloop devbox."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path

from runloop_api_client import AsyncRunloopSDK, NotFoundError
from runloop_api_client.sdk.async_devbox import AsyncDevbox

ROOT = Path(__file__).parent
STATE = ROOT / ".controller.json"
CONTROLLER_NAME = "agents-api-webhook-runloop"
OPENAI_GATEWAY_NAME = "agents-api-webhook-openai-controller"
OPENAI_SECRET_NAME = "agents_api_webhook_openai_api_key"
OPENAI_EXECUTOR_SECRET_NAME = "agents_api_webhook_openai_executor_api_key"
RUNLOOP_SECRET_NAME = "agents_api_webhook_runloop_api_key"
WEBHOOK_SECRET_NAME = "agents_api_webhook_openai_webhook_secret"


async def ensure_gateway(runloop: AsyncRunloopSDK) -> str:
    async for info in await runloop.api.gateway_configs.list(
        name=OPENAI_GATEWAY_NAME,
        include_total_count=False,
    ):
        if info.name == OPENAI_GATEWAY_NAME:
            return info.id
    return (
        await runloop.gateway_config.create(
            name=OPENAI_GATEWAY_NAME,
            endpoint="https://api.openai.com",
            auth_mechanism={"type": "bearer"},
        )
    ).id


async def wait_for_controller(controller: AsyncDevbox) -> None:
    for _ in range(30):
        info = await controller.get_info()
        if info.status == "failure":
            raise RuntimeError("Controller entrypoint failed; inspect the devbox logs")
        try:
            health = await controller.cmd.exec("curl -fsS http://127.0.0.1:8000/health")
        except Exception:  # noqa: BLE001 - Retry while the devbox is starting.
            health = None
        if health is not None and health.exit_code == 0:
            return
        await asyncio.sleep(2)
    raise TimeoutError("Controller did not become healthy before the retry limit")


async def reuse_saved_controller(
    runloop: AsyncRunloopSDK,
    state: dict[str, str] | None,
    fingerprint: str,
) -> AsyncDevbox | None:
    if state is None:
        return None
    controller = runloop.devbox.from_id(state["devbox_id"])
    try:
        info = await controller.get_info()
    except NotFoundError:
        return None
    if info.status in {"failure", "shutdown"}:
        return None
    if state.get("fingerprint") != fingerprint:
        await controller.shutdown()
        return None
    if info.status == "suspended":
        await controller.resume()
    elif info.status == "suspending":
        await controller.await_suspended()
        await controller.resume()
    elif info.status != "running":
        await controller.await_running()
    return controller


async def main() -> None:
    handler = ROOT.joinpath("handler.py").read_text()
    sandbox = ROOT.parent.joinpath("sandbox.py").read_text()
    agent_id = os.environ["OPENAI_AGENT_ID"]
    values = {
        OPENAI_SECRET_NAME: os.environ["OPENAI_API_KEY"],
        OPENAI_EXECUTOR_SECRET_NAME: os.environ["OPENAI_EXECUTOR_API_KEY"],
        RUNLOOP_SECRET_NAME: os.environ["RUNLOOP_API_KEY"],
        WEBHOOK_SECRET_NAME: os.environ.get(
            "OPENAI_WEBHOOK_SECRET", "pending-webhook-registration"
        ),
    }
    async with AsyncRunloopSDK() as runloop:
        for name, value in values.items():
            try:
                await runloop.secret.update(name, value)
            except NotFoundError:
                await runloop.secret.create(name, value)
        gateway_id = await ensure_gateway(runloop)
        # These values are fixed at creation; replace the controller when they change.
        fingerprint = hashlib.sha256(
            "\0".join(
                [
                    values[RUNLOOP_SECRET_NAME],
                    values[WEBHOOK_SECRET_NAME],
                    agent_id,
                    handler,
                    sandbox,
                    gateway_id,
                ]
            ).encode()
        ).hexdigest()
        state = json.loads(STATE.read_text()) if STATE.exists() else None
        controller = await reuse_saved_controller(runloop, state, fingerprint)
        if controller is None:
            controller = await runloop.devbox.create(
                name=CONTROLLER_NAME,
                environment_variables={"OPENAI_AGENT_ID": agent_id},
                secrets={
                    "RUNLOOP_API_KEY": RUNLOOP_SECRET_NAME,
                    "OPENAI_WEBHOOK_SECRET": WEBHOOK_SECRET_NAME,
                },
                gateways={
                    "OPENAI_GATEWAY": {
                        "gateway": gateway_id,
                        "secret": OPENAI_SECRET_NAME,
                    }
                },
                file_mounts={
                    "/home/user/controller/webhook_managed/handler.py": handler,
                    "/home/user/controller/sandbox.py": sandbox,
                },
                entrypoint=(
                    "cd /home/user/controller/webhook_managed && exec uv run handler.py"
                ),
                tunnel={"auth_mode": "open"},
                launch_parameters={
                    "launch_commands": [
                        (
                            "dpkg -s libsqlite3-0 >/dev/null 2>&1 || "
                            "(sudo apt-get update && sudo apt-get install -y libsqlite3-0)"
                        ),
                        "command -v uv || python -m pip install uv",
                    ],
                    "lifecycle": {
                        "after_idle": {
                            "idle_time_seconds": 600,
                            "on_idle": "suspend",
                        },
                        "resume_triggers": {"http": True},
                    },
                },
            )
            STATE.write_text(
                json.dumps({"devbox_id": controller.id, "fingerprint": fingerprint})
                + "\n"
            )
        await wait_for_controller(controller)
        webhook_url = await controller.get_tunnel_url(8000)
        if webhook_url is None:
            raise RuntimeError("Controller tunnel was not provisioned")
        print(f"Webhook: {webhook_url}/webhook")
        print(f"Controller: {controller.id} (suspends after ten idle minutes)")


if __name__ == "__main__":
    asyncio.run(main())
