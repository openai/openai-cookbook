# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "daytona>=0.207.0",
#     "fastapi>=0.115,<1",
#     "uvicorn>=0.30,<1",
#     "httpx>=0.27,<1",
#     "openai>=3.13.0",
# ]
# ///

"""A single-process OpenAI webhook controller hosted in a Daytona sandbox."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sqlite3
import sys
import time
import traceback
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from daytona import (
    AsyncDaytona,
    CreateSandboxFromSnapshotParams,
    DaytonaNotFoundError,
)
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from openai import AsyncOpenAI, InvalidWebhookSignatureError, NotFoundError, OpenAI

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sandbox import install_executor, start_executor

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
    action = next(
        (a for a in session.required_actions if a.type == "environment_connection"),
        None,
    )
    if session.status != "failed" and action is None:
        return
    async with AsyncDaytona() as daytona:
        try:
            sandbox = await daytona.get(sandbox_name(session_id))
        except DaytonaNotFoundError:
            sandbox = None
        if session.status == "failed":
            if sandbox is not None:
                await daytona.delete(sandbox, wait=True)
            return
        assert action is not None
        if sandbox is None:
            sandbox = await daytona.create(
                CreateSandboxFromSnapshotParams(
                    name=sandbox_name(session_id),
                    language="javascript",
                    labels={"agents-session-id": session_id},
                    env_vars={"CODEX_API_KEY": os.environ["OPENAI_EXECUTOR_API_KEY"]},
                    auto_stop_interval=0,
                    ttl_minutes=30,
                ),
                timeout=90,
            )
        elif sandbox.state != "started":
            await sandbox.start(timeout=90)
        await install_executor(sandbox, reconnect=True)
        await start_executor(
            sandbox,
            session.environment.remote_url,
            session.environment.id,
            reconnect=True,
        )
        print(
            json.dumps(
                {
                    "session_id": session_id,
                    "sandbox_id": sandbox.id,
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
