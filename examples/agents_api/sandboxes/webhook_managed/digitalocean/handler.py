# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "openai>=3.13.0",
#     "pydo[aio]>=0.40.0b7,!=0.40.0",
#     "fastapi[standard]",
# ]
# ///

"""A single-process OpenAI webhook controller for DigitalOcean MARS sandboxes.

DigitalOcean's Managed Agents Runtime Service boots a Firecracker microVM from
a published image that already contains the Codex CLI and starts the executor
itself, so provisioning is a single API call and there is no `codex exec-server`
command anywhere below. The manifest's `agent: codex-agentapi` selects the image
that runs it.

The sandbox is named after the OpenAI session ID so reconnects can find it.
Reconciliation is serialized within this process; run only one controller
worker. Multiple replicas require distributed coordination or provider-side
idempotency. Idle sandboxes are paused automatically and resumed on reconnect.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from openai import APIStatusError, AsyncOpenAI, InvalidWebhookSignatureError, OpenAI
from pydo.aio import Client as DOClient

# `${ENV_ID}` and `${OPENAI_API_KEY}` are substituted from `variables` below.
# Credentials belong under `secrets:`, not `env:` — the create API rejects a
# credential-shaped `env` value. `config` is passed through to OpenAI verbatim
# and is required even when attaching to an existing session.
MANIFEST = """
name: {name}
agent: codex-agentapi
config:
  agent:
    model: gpt-5.6-sol
  environment:
    type: self_hosted
    workspace_directory: /workspace
secrets:
  CODEX_API_KEY: ${{OPENAI_API_KEY}}
env:
  CODEX_ENVIRONMENT_ID: ${{ENV_ID}}
egress:
  - api.openai.com
  - codex-cloud-environments.chatgpt.com
"""

# A session in one of these is gone for good; a new one must be created.
TERMINAL_STATUSES = {
    "SESSION_STATUS_DESTROYED",
    "SESSION_STATUS_FAILED",
    "SESSION_STATUS_UNSPECIFIED",
}


def do_session_name(openai_session_id: str) -> str:
    """Derive the DO session name that identifies this OpenAI session."""
    return f"mars-{openai_session_id}"


async def find_do_session(do: Any, name: str) -> dict[str, Any] | None:
    """Return the newest non-terminal DO session with *name*, if any."""
    sessions: list[dict[str, Any]] = []
    page_token = None
    while True:
        response = await do.agents.sessions.list(name=name, page_token=page_token)
        sessions.extend((response or {}).get("sessions") or [])
        page_token = (response or {}).get("next_page_token")
        if not page_token:
            break
    live = [s for s in sessions if s.get("status") not in TERMINAL_STATUSES]
    if not live:
        return None
    return max(live, key=lambda s: s.get("created_at") or "")


async def reconcile(openai_session_id: str) -> None:
    async with AsyncOpenAI(timeout=30) as client:
        try:
            session = await client.beta.agents.sessions.retrieve(openai_session_id)
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

    name = do_session_name(openai_session_id)
    do = DOClient(token=os.environ["DIGITALOCEAN_TOKEN"])
    async with do:
        assert do.agents is not None, "Install a pydo release with Agents support"
        existing = await find_do_session(do, name)

        if info.status == "failed":
            if existing is not None:
                await do.agents.destroy_session(session_id=existing["session_id"])
                _log(openai_session_id, name, "destroyed")
            return

        if not any(a.type == "environment_connection" for a in info.required_actions):
            return

        if existing is not None:
            # Already provisioned. Resume it if DigitalOcean paused it while
            # idle; otherwise it is starting or already connected, and creating
            # a second sandbox for one session would be the real failure.
            if existing.get("status") == "SESSION_STATUS_PAUSED":
                await do.agents.sessions.resume(existing["session_id"])
                _log(openai_session_id, name, "resumed")
            return

        # `create_session` is the flat-manifest path: it substitutes
        # `variables` and posts the manifest as written. (`agents.start()`
        # expects the legacy `spec.runtime.adapter` envelope instead.)
        response = await do.agents.create_session(
            params={"openai_session_id": openai_session_id},
            body={
                "manifest": MANIFEST.format(name=name),
                "variables": {
                    "ENV_ID": environment.id,
                    "OPENAI_API_KEY": os.environ["OPENAI_EXECUTOR_API_KEY"],
                },
            },
        )
        _log(
            openai_session_id,
            name,
            "started",
            (response or {}).get("session", {}).get("session_id"),
        )


def _log(
    openai_session_id: str, name: str, action: str, do_session_id: str | None = None
) -> None:
    payload = {
        "openai_session_id": openai_session_id,
        "do_name": name,
        "action": action,
    }
    if do_session_id:
        payload["do_session_id"] = do_session_id
    print(json.dumps(payload), flush=True)


app = FastAPI()
reconcile_lock = asyncio.Lock()


@app.get("/health")
async def health() -> dict[str, bool]:
    return {"ok": True}


@app.post("/webhook")
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
        # Hold the lock across the state read, lookup, and provision/cleanup.
        async with reconcile_lock:
            await reconcile(event["data"]["id"])
    return JSONResponse({"ok": True})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
