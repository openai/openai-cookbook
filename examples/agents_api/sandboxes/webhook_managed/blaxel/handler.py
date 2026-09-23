# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "blaxel",
#     "fastapi[standard]",
#     "httpx",
#     "openai>=3.13.0",
#     "uvicorn",
# ]
# ///

"""A small, single-process webhook controller running in a Blaxel sandbox."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shlex
import sqlite3
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from blaxel.core.sandbox import SandboxInstance
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from openai import AsyncOpenAI, InvalidWebhookSignatureError, NotFoundError, OpenAI

DB_PATH = os.environ.get("QUEUE_PATH", "/app/pending.sqlite3")


def sandbox_name(session_id: str) -> str:
    return f"agents-webhook-{hashlib.sha256(session_id.encode()).hexdigest()[:24]}"


async def reconcile(session_id: str) -> None:
    async with AsyncOpenAI(timeout=30) as client:
        try:
            session = await client.beta.agents.sessions.retrieve(session_id)
        except NotFoundError:
            return
    if (
        session.environment.type != "self_hosted"
        or session.agent.id != os.environ["OPENAI_AGENT_ID"]
    ):
        return
    name = sandbox_name(session_id)
    if session.status == "failed":
        try:
            await SandboxInstance.delete(name)
        except Exception as error:
            if getattr(error, "status_code", None) != 404:
                raise
        return
    action = next(
        (a for a in session.required_actions if a.type == "environment_connection"),
        None,
    )
    if action is None:
        return
    sandbox = await SandboxInstance.create_if_not_exists(
        {
            "name": name,
            "image": "blaxel/node:latest",
            "region": os.environ.get("BL_REGION", "us-pdx-1"),
            "ttl": "30m",
            "labels": {"agents-session-id": session_id},
        }
    )
    setup = await sandbox.process.exec(
        {
            "command": "mkdir -p /workspace && (command -v codex || npm install -g @openai/codex@alpha) && (command -v rg || apk add --no-cache ripgrep util-linux)",
            "wait_for_completion": True,
            "timeout": 120,
        }
    )
    if setup.exit_code != 0:
        raise RuntimeError("Executor setup failed")
    # The controller serializes jobs; flock also prevents duplicate executors.
    command = shlex.join(
        [
            "flock",
            "-n",
            "/tmp/codex-executor.lock",
            "codex",
            "exec-server",
            "--remote",
            session.environment.remote_url,
            "--environment-id",
            session.environment.id,
        ]
    )
    await sandbox.process.exec(
        {
            "command": command,
            "working_dir": "/workspace",
            "wait_for_completion": False,
            "keep_alive": True,
            "timeout": 1800,
            "env": {"CODEX_API_KEY": os.environ["OPENAI_EXECUTOR_API_KEY"]},
        }
    )
    print(
        json.dumps(
            {"session_id": session_id, "sandbox_name": name, "action": "started"}
        ),
        flush=True,
    )


async def drain_queue(db: sqlite3.Connection) -> None:
    while True:
        row = db.execute(
            "SELECT session_id, attempts FROM jobs WHERE retry_at <= ? LIMIT 1",
            (time.time(),),
        ).fetchone()
        if row is None:
            await asyncio.sleep(1)
            continue
        session_id, attempts = row
        try:
            await reconcile(session_id)
        except Exception as error:
            # Persist retries across controller process restarts; never log secrets.
            if attempts >= 4:
                db.execute("DELETE FROM jobs WHERE session_id = ?", (session_id,))
            else:
                db.execute(
                    "UPDATE jobs SET attempts = ?, retry_at = ? WHERE session_id = ?",
                    (attempts + 1, time.time() + 10, session_id),
                )
            print(
                json.dumps(
                    {"session_id": session_id, "error_type": type(error).__name__}
                ),
                flush=True,
            )
        else:
            db.execute("DELETE FROM jobs WHERE session_id = ?", (session_id,))
        db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    db = sqlite3.connect(DB_PATH)
    db.execute(
        "CREATE TABLE IF NOT EXISTS jobs (session_id TEXT PRIMARY KEY, attempts INTEGER DEFAULT 0, retry_at REAL DEFAULT 0)"
    )
    app.state.db = db
    task = asyncio.create_task(drain_queue(db))
    try:
        yield
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        db.close()


app = FastAPI(lifespan=lifespan)


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
        request.app.state.db.execute(
            "INSERT OR IGNORE INTO jobs(session_id) VALUES (?)", (event["data"]["id"],)
        )
        request.app.state.db.commit()
    return JSONResponse({"ok": True})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
