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

from runloop_api_client import AsyncRunloopSDK
from runloop_api_client.sdk.async_devbox import AsyncDevbox

ROOT = Path(__file__).parent
STATE = ROOT / ".controller.json"
CONTROLLER_NAME = "agents-api-webhook-runloop"
OPENAI_GATEWAY_NAME = "agents-api-webhook-openai-controller"
OPENAI_EXECUTOR_GATEWAY_NAME = "agents-api-webhook-openai-executor"
OPENAI_API_ORIGIN = "https://api.openai.com"
OPENAI_SECRET_NAME = "agents_api_webhook_openai_api_key"
OPENAI_EXECUTOR_SECRET_NAME = "agents_api_webhook_openai_executor_api_key"
RUNLOOP_SECRET_NAME = "agents_api_webhook_runloop_api_key"
WEBHOOK_SECRET_NAME = "agents_api_webhook_openai_webhook_secret"


async def upsert_secret(
    runloop: AsyncRunloopSDK, names: set[str], name: str, value: str
) -> None:
    if name in names:
        await runloop.secret.update(name, value)
    else:
        await runloop.secret.create(name, value)


async def ensure_gateway(runloop: AsyncRunloopSDK, name: str, description: str) -> str:
    for gateway in await runloop.gateway_config.list():
        info = await gateway.get_info()
        if info.name == name:
            await gateway.update(
                endpoint=OPENAI_API_ORIGIN,
                auth_mechanism={"type": "bearer"},
            )
            return gateway.id
    return (
        await runloop.gateway_config.create(
            name=name,
            endpoint=OPENAI_API_ORIGIN,
            auth_mechanism={"type": "bearer"},
            description=description,
        )
    ).id


async def wait_for_controller(controller: AsyncDevbox) -> None:
    for _ in range(30):
        info = await controller.get_info()
        if info.status == "failure":
            raise RuntimeError("Controller entrypoint failed; inspect the devbox logs")
        try:
            health = await controller.cmd.exec("curl -fsS http://127.0.0.1:8000/health")
        except Exception:
            health = None
        if health is not None and health.exit_code == 0:
            return
        await asyncio.sleep(2)
    raise TimeoutError("Controller did not become healthy within 60 seconds")


async def main() -> None:
    values = {
        "OPENAI_API_KEY": os.environ["OPENAI_API_KEY"],
        "OPENAI_EXECUTOR_API_KEY": os.environ["OPENAI_EXECUTOR_API_KEY"],
        "RUNLOOP_API_KEY": os.environ["RUNLOOP_API_KEY"],
        "OPENAI_WEBHOOK_SECRET": os.environ.get(
            "OPENAI_WEBHOOK_SECRET", "pending-webhook-registration"
        ),
    }
    fingerprint = hashlib.sha256(
        "\0".join(
            [
                values["RUNLOOP_API_KEY"],
                values["OPENAI_WEBHOOK_SECRET"],
                os.environ["OPENAI_AGENT_ID"],
                ROOT.joinpath("handler.py").read_text(),
            ]
        ).encode()
    ).hexdigest()
    async with AsyncRunloopSDK() as runloop:
        secret_names = {secret.name for secret in await runloop.secret.list()}
        await asyncio.gather(
            upsert_secret(
                runloop,
                secret_names,
                OPENAI_SECRET_NAME,
                values["OPENAI_API_KEY"],
            ),
            upsert_secret(
                runloop,
                secret_names,
                OPENAI_EXECUTOR_SECRET_NAME,
                values["OPENAI_EXECUTOR_API_KEY"],
            ),
            upsert_secret(
                runloop,
                secret_names,
                RUNLOOP_SECRET_NAME,
                values["RUNLOOP_API_KEY"],
            ),
            upsert_secret(
                runloop,
                secret_names,
                WEBHOOK_SECRET_NAME,
                values["OPENAI_WEBHOOK_SECRET"],
            ),
        )
        gateway_id, executor_gateway_id = await asyncio.gather(
            ensure_gateway(
                runloop,
                OPENAI_GATEWAY_NAME,
                "OpenAI controller access for the Agents API webhook example",
            ),
            ensure_gateway(
                runloop,
                OPENAI_EXECUTOR_GATEWAY_NAME,
                "Restricted OpenAI executor access for the Agents API webhook example",
            ),
        )
        fingerprint = hashlib.sha256(
            f"{fingerprint}\0{gateway_id}\0{executor_gateway_id}".encode()
        ).hexdigest()
        state = json.loads(STATE.read_text()) if STATE.exists() else None
        controller = None
        if state is not None and state.get("fingerprint") == fingerprint:
            controller = runloop.devbox.from_id(state["devbox_id"])
            info = await controller.get_info()
            if info.status == "suspended":
                await controller.resume()
            elif info.status == "suspending":
                await controller.await_suspended()
                await controller.resume()
            elif info.status in {"failure", "shutdown"}:
                controller = None
            elif info.status != "running":
                await controller.await_running()
        elif state is not None:
            previous = runloop.devbox.from_id(state["devbox_id"])
            previous_info = await previous.get_info()
            if previous_info.status not in {"failure", "shutdown"}:
                await previous.shutdown()
        if controller is None:
            controller = await runloop.devbox.create(
                name=CONTROLLER_NAME,
                environment_variables={
                    "OPENAI_AGENT_ID": os.environ["OPENAI_AGENT_ID"],
                    "OPENAI_EXECUTOR_GATEWAY_ID": executor_gateway_id,
                },
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
                    "/home/user/controller/handler.py": ROOT.joinpath(
                        "handler.py"
                    ).read_text()
                },
                entrypoint="cd /home/user/controller && exec uv run handler.py",
                tunnel={"auth_mode": "open"},
                launch_parameters={
                    "launch_commands": [
                        "dpkg -s libsqlite3-0 >/dev/null 2>&1 || "
                        "(sudo apt-get update && sudo apt-get install -y libsqlite3-0)",
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
