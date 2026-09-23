# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "daytona>=0.207.0",
# ]
# ///

"""Deploy a signature-protected controller in a dedicated Daytona sandbox."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from daytona import (
    AsyncDaytona,
    CreateSandboxFromImageParams,
    DaytonaNotFoundError,
    Image,
    SessionExecuteRequest,
)

NAME = "agents-api-webhook-daytona"
ROOT = Path(__file__).parent


async def main() -> None:
    values = {
        key: os.environ[key]
        for key in [
            "OPENAI_API_KEY",
            "OPENAI_EXECUTOR_API_KEY",
            "OPENAI_AGENT_ID",
            "DAYTONA_API_KEY",
        ]
    }
    for key in ["DAYTONA_API_URL", "DAYTONA_TARGET"]:
        if key in os.environ:
            values[key] = os.environ[key]
    values["OPENAI_WEBHOOK_SECRET"] = os.environ.get(
        "OPENAI_WEBHOOK_SECRET", "pending-webhook-registration"
    )
    async with AsyncDaytona() as daytona:
        try:
            sandbox = await daytona.get(NAME)
        except DaytonaNotFoundError:
            sandbox = await daytona.create(
                CreateSandboxFromImageParams(
                    name=NAME,
                    image=Image.base("python:3.12-slim").run_commands("mkdir -p /app"),
                    os_user="root",
                    public=True,
                    env_vars=values,
                    labels={"agents-webhook-controller": "daytona"},
                    auto_stop_interval=0,
                    ttl_minutes=120,
                ),
                timeout=300,
            )
        else:
            if sandbox.state != "started":
                await sandbox.start(timeout=90)
            await sandbox.update_env(values)
            await sandbox.set_ttl(120)
        await sandbox.fs.upload_file(
            ROOT.joinpath("handler.py").read_bytes(), "/app/handler.py"
        )
        install = await sandbox.process.exec(
            "python -m pip install uv && uv pip install --system -r /app/handler.py",
            timeout=180,
        )
        if install.exit_code != 0:
            raise RuntimeError("Controller dependency installation failed")
        try:
            await sandbox.process.get_session("webhook-controller")
        except DaytonaNotFoundError:
            pass
        else:
            await sandbox.process.delete_session("webhook-controller")
        await sandbox.process.create_session("webhook-controller")
        await sandbox.process.execute_session_command(
            "webhook-controller",
            SessionExecuteRequest(
                command="cd /app && python -m uvicorn handler:app --host 0.0.0.0 --port 8000 >> /app/controller.log 2>&1",
                run_async=True,
            ),
        )
        preview = await sandbox.get_preview_link(8000)
        print(f"Webhook: {preview.url}/webhook")
        print(f"Controller: {sandbox.id} (expires after two hours; redeploy to extend)")


if __name__ == "__main__":
    asyncio.run(main())
