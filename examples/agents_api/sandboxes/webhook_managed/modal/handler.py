# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "openai>=3.13.0",
#     "modal>=1.5.4,<2",
#     "fastapi[standard]",
# ]
# ///

"""Deploy with: uv run examples/agents_api/sandboxes/webhook_managed/modal/handler.py."""

from __future__ import annotations

import json
import os

import modal
from fastapi import Request
from fastapi.responses import JSONResponse
from openai import APIStatusError, AsyncOpenAI, InvalidWebhookSignatureError, OpenAI

APP_NAME = "agents-api-webhook-modal"
WORKSPACE = "/workspace"
app = modal.App(APP_NAME)
executor_image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("nodejs", "npm", "git", "ripgrep")
    .run_commands("npm install -g @openai/codex@alpha", f"mkdir -p {WORKSPACE}")
    .workdir(WORKSPACE)
)
controller_image = executor_image.pip_install("fastapi[standard]", "openai>=3.13.0")


@app.function(
    image=controller_image,
    secrets=[modal.Secret.from_name(f"{APP_NAME}-controller")],
    max_containers=1,
    timeout=180,
    retries=2,
)
async def reconcile(session_id: str) -> None:
    # One worker serializes this small example. The sandbox name survives retries.
    async with AsyncOpenAI(timeout=30) as client:
        try:
            session = await client.beta.agents.sessions.retrieve(session_id)
        except APIStatusError as error:
            if error.status_code == 404:
                return
            raise
    info = session
    environment = info.environment
    if (
        environment.type != "self_hosted"
        or info.agent.id != os.environ["OPENAI_AGENT_ID"]
    ):
        return
    try:
        sandbox = await modal.Sandbox.from_name.aio(APP_NAME, session_id)
    except modal.exception.NotFoundError:
        sandbox = None
    if info.status == "failed":
        if sandbox is not None:
            await sandbox.terminate.aio()
        return
    if not any(
        action.type == "environment_connection" for action in info.required_actions
    ):
        return
    if sandbox is not None:
        return  # Already starting or connected; never create a duplicate.
    sandbox = await modal.Sandbox.create.aio(
        "codex",
        "exec-server",
        "--remote",
        environment.remote_url,
        "--environment-id",
        environment.id,
        app=app,
        name=session_id,
        image=executor_image,
        secrets=[modal.Secret.from_name(f"{APP_NAME}-executor")],
        workdir=WORKSPACE,
        timeout=30 * 60,
    )
    await sandbox.detach.aio()
    print(
        json.dumps(
            {
                "session_id": session_id,
                "sandbox_id": sandbox.object_id,
                "action": "started",
            }
        )
    )


@app.function(
    image=controller_image,
    secrets=[modal.Secret.from_name(f"{APP_NAME}-signing")],
)
@modal.fastapi_endpoint(method="POST")
async def webhook(request: Request) -> JSONResponse:
    secret = os.environ.get("OPENAI_WEBHOOK_SECRET")
    if not secret or secret == "pending-webhook-registration":
        return JSONResponse({"error": "Webhook not configured"}, status_code=503)
    payload = (await request.body()).decode()
    with OpenAI(api_key="unused", webhook_secret=secret) as verifier:
        try:
            verifier.webhooks.verify_signature(payload=payload, headers=request.headers)
        except (InvalidWebhookSignatureError, ValueError):
            return JSONResponse({"error": "Invalid signature"}, status_code=400)
    event = json.loads(payload)
    if event["type"] == "agent.session.failed" or (
        event["type"] == "agent.session.action_required"
        and event["data"]["required_action"]["type"] == "environment_connection"
    ):
        await reconcile.spawn.aio(event["data"]["id"])
    return JSONResponse({"ok": True})


if __name__ == "__main__":
    with modal.enable_output():
        app.deploy()
