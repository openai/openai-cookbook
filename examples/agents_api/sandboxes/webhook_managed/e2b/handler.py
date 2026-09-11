# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "e2b>=2.45.1",
#     "fastapi>=0.115,<1",
#     "uvicorn>=0.30,<1",
#     "httpx>=0.27,<1",
#     "openai>=3.13.0",
# ]
# ///

"""A single-process OpenAI webhook controller hosted in an E2B sandbox."""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import sqlite3
import time
import traceback
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from e2b import AsyncSandbox, SandboxQuery, SandboxState
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from openai import AsyncOpenAI, InvalidWebhookSignatureError, NotFoundError, OpenAI

DB_PATH = os.environ.get("QUEUE_PATH", "/app/pending.sqlite3")


async def find_sandbox(session_id: str) -> str | None:
    items = await AsyncSandbox.list(
        query=SandboxQuery(
            metadata={"agents-session-id": session_id},
            state=[SandboxState.RUNNING, SandboxState.PAUSED],
        ),
        limit=1,
    ).next_items()
    return items[0].sandbox_id if items else None


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
    action = next(
        (a for a in session.required_actions if a.type == "environment_connection"),
        None,
    )
    if session.status != "failed" and action is None:
        return
    sandbox_id = await find_sandbox(session_id)
    if session.status == "failed":
        if sandbox_id is not None:
            await AsyncSandbox.kill(sandbox_id)
        return
    assert action is not None
    if sandbox_id is None:
        sandbox = await AsyncSandbox.create(
            timeout=1800,
            metadata={"agents-session-id": session_id},
            envs={"CODEX_API_KEY": os.environ["OPENAI_EXECUTOR_API_KEY"]},
            network={"allow_public_traffic": False},
        )
    else:
        sandbox = await AsyncSandbox.connect(sandbox_id, timeout=1800)
    await sandbox.commands.run(
        "mkdir -p /workspace && (command -v codex || npm install -g @openai/codex@alpha) && command -v flock",
        user="root",
        timeout=180,
    )
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
    await sandbox.commands.run(
        f"{command} >> /tmp/codex-executor.log 2>&1",
        user="root",
        cwd="/workspace",
        background=True,
        timeout=0,
    )
    print(
        json.dumps(
            {
                "session_id": session_id,
                "sandbox_id": sandbox.sandbox_id,
                "action": "started",
            }
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
                    {
                        "session_id": session_id,
                        "error_type": type(error).__name__,
                        "error_at": [
                            f"{frame.name}:{frame.lineno}"
                            for frame in traceback.extract_tb(error.__traceback__)
                        ],
                    }
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
        print(
            json.dumps(
                {
                    "event_id": event["id"],
                    "session_id": event["data"]["id"],
                    "action": "enqueued",
                }
            ),
            flush=True,
        )
    return JSONResponse({"ok": True})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
