# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "e2b>=2.45.1",
# ]
# ///

"""Deploy a signature-protected controller in a dedicated E2B sandbox."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from e2b import AsyncSandbox

ROOT = Path(__file__).parent
STATE = ROOT / ".controller.json"


async def main() -> None:
    values = {
        key: os.environ[key]
        for key in [
            "OPENAI_API_KEY",
            "OPENAI_EXECUTOR_API_KEY",
            "OPENAI_AGENT_ID",
            "E2B_API_KEY",
        ]
    }
    values["OPENAI_WEBHOOK_SECRET"] = os.environ.get(
        "OPENAI_WEBHOOK_SECRET", "pending-webhook-registration"
    )
    if STATE.exists():
        sandbox = await AsyncSandbox.connect(
            json.loads(STATE.read_text())["sandbox_id"], timeout=3600
        )
    else:
        sandbox = await AsyncSandbox.create(
            timeout=3600,
            metadata={"agents-webhook-controller": "e2b"},
            network={"allow_public_traffic": True},
        )
        STATE.write_text(json.dumps({"sandbox_id": sandbox.sandbox_id}) + "\n")
    await sandbox.commands.run("mkdir -p /app", user="root")
    await sandbox.files.write(
        "/app/handler.py", ROOT.joinpath("handler.py").read_text(), user="root"
    )
    await sandbox.commands.run(
        "python -m venv /opt/controller && /opt/controller/bin/pip install uv && /opt/controller/bin/uv pip install --python /opt/controller/bin/python -r /app/handler.py",
        user="root",
        timeout=180,
    )
    await sandbox.commands.run(
        "pkill -f '^/opt/controller/bin/python -m uvicorn handler:app' || true",
        user="root",
    )
    await sandbox.commands.run(
        "exec /opt/controller/bin/python -m uvicorn handler:app --host 0.0.0.0 --port 8000 >> /app/controller.log 2>&1",
        cwd="/app",
        user="root",
        envs=values,
        background=True,
        timeout=0,
    )
    print(f"Webhook: https://{sandbox.get_host(8000)}/webhook")
    print(
        f"Controller: {sandbox.sandbox_id} (expires after one hour; redeploy to extend)"
    )


if __name__ == "__main__":
    asyncio.run(main())
