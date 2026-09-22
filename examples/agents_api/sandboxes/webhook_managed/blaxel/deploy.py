# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "blaxel",
# ]
# ///

"""Deploy the webhook controller. Keep all credentials in environment variables."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from blaxel.core.sandbox import SandboxInstance

NAME = "agents-api-webhook-controller"


async def main() -> None:
    required = [
        "OPENAI_API_KEY",
        "OPENAI_EXECUTOR_API_KEY",
        "OPENAI_AGENT_ID",
        "BL_API_KEY",
        "BL_WORKSPACE",
    ]
    values = {key: os.environ[key] for key in required}
    values["BL_REGION"] = os.environ.get("BL_REGION", "us-pdx-1")
    values["OPENAI_WEBHOOK_SECRET"] = os.environ.get(
        "OPENAI_WEBHOOK_SECRET", "pending-webhook-registration"
    )
    sandbox = await SandboxInstance.create_if_not_exists(
        {
            "name": NAME,
            "image": "blaxel/node:latest",
            "region": values["BL_REGION"],
            "memory": 2048,
            "ttl": "2h",
            "ports": [
                {"name": "sandbox-api", "target": 8080, "protocol": "HTTP"},
                {"name": "webhook", "target": 8000, "protocol": "HTTP"},
            ],
        }
    )
    setup = await sandbox.process.exec(
        {
            "command": "apk add --no-cache python3 py3-pip && python3 -m venv /opt/controller && /opt/controller/bin/pip install uv && mkdir -p /app",
            "wait_for_completion": True,
            "timeout": 180,
        }
    )
    if setup.exit_code != 0:
        raise RuntimeError("Controller dependency installation failed")
    await sandbox.fs.write(
        "/app/handler.py", Path(__file__).with_name("handler.py").read_text()
    )
    install = await sandbox.process.exec(
        {
            "command": "/opt/controller/bin/uv pip install --python /opt/controller/bin/python -r /app/handler.py",
            "wait_for_completion": True,
            "timeout": 180,
        }
    )
    if install.exit_code != 0:
        raise RuntimeError("Controller dependency installation failed")
    # A redeploy replaces only this controller process, retaining the disk-backed queue.
    for process in await sandbox.process.list():
        if process.name == "webhook-controller":
            await sandbox.process.kill(process.name)
    await sandbox.process.exec(
        {
            "name": "webhook-controller",
            "command": "/opt/controller/bin/uvicorn handler:app --host 0.0.0.0 --port 8000",
            "working_dir": "/app",
            "env": values,
            "wait_for_completion": False,
            "keep_alive": True,
            "timeout": 7200,
        }
    )
    preview = await sandbox.previews.create_if_not_exists(
        {
            "metadata": {"name": "webhook"},
            "spec": {"port": 8000, "public": True},
        }
    )
    if preview.spec is None or not preview.spec.url:
        raise RuntimeError("Controller preview URL is unavailable")
    print(f"Webhook: {preview.spec.url}/webhook")
    print(f"Controller: {NAME} (expires after two hours)")


if __name__ == "__main__":
    asyncio.run(main())
