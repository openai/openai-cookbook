# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "fastapi>=0.115,<1",
#     "openai>=3.13.0",
#     "runloop-api-client>=1.31.0",
#     "uvicorn>=0.30,<1",
# ]
# ///

"""A single-process OpenAI webhook controller hosted in a Runloop devbox."""

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
from typing import Literal, TypeAlias
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from openai import AsyncOpenAI, InvalidWebhookSignatureError, NotFoundError, OpenAI
from runloop_api_client import AsyncRunloopSDK
from runloop_api_client.lib.polling import PollingConfig
from runloop_api_client.sdk.async_devbox import AsyncDevbox

DB_PATH = os.environ.get("QUEUE_PATH", "/home/user/pending.sqlite3")
OPENAI_API_ORIGIN = "https://api.openai.com"
OPENAI_EXECUTOR_SECRET_NAME = "agents_api_webhook_openai_executor_api_key"
CODEX = "/home/user/.codex-runtime/node_modules/.bin/codex"
DevboxStatus: TypeAlias = Literal[
    "scheduled",
    "queued",
    "provisioning",
    "initializing",
    "running",
    "suspending",
    "suspended",
    "resuming",
]


async def find_devbox(
    runloop: AsyncRunloopSDK, session_id: str
) -> tuple[AsyncDevbox | None, str | None]:
    statuses: tuple[DevboxStatus, ...] = (
        "scheduled",
        "queued",
        "provisioning",
        "initializing",
        "running",
        "suspending",
        "suspended",
        "resuming",
    )
    for status in statuses:
        async for info in await runloop.api.devboxes.list(
            status=status,
            limit=5000,
            include_total_count=False,
        ):
            if info.metadata and info.metadata.get("agents-session-id") == session_id:
                return runloop.devbox.from_id(info.id), info.status
    return None, None


def remote_path(remote_url: str) -> str:
    parsed = urlsplit(remote_url)
    if not parsed.scheme or not parsed.netloc or not parsed.path.startswith("/"):
        raise ValueError("The Agents API returned an invalid environment remote URL")
    if f"{parsed.scheme}://{parsed.netloc}" != OPENAI_API_ORIGIN:
        raise ValueError(f"The environment remote URL does not use {OPENAI_API_ORIGIN}")
    # Keep the executor on its credential-injecting Runloop gateway origin.
    return parsed.path + (f"?{parsed.query}" if parsed.query else "")


async def reconcile(session_id: str) -> None:
    async with AsyncOpenAI(
        api_key=os.environ["OPENAI_GATEWAY"],
        base_url=f"{os.environ['OPENAI_GATEWAY_URL'].rstrip('/')}/v1",
        timeout=30,
    ) as client:
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
    async with AsyncRunloopSDK() as runloop:
        devbox, status = await find_devbox(runloop, session_id)
        if session.status == "failed":
            if devbox is not None:
                await devbox.shutdown()
            return
        assert action is not None
        if devbox is None:
            devbox = await runloop.devbox.create(
                name=f"agents-webhook-{session_id[-24:]}",
                metadata={"agents-session-id": session_id},
                gateways={
                    "OPENAI_GATEWAY": {
                        "gateway": os.environ["OPENAI_EXECUTOR_GATEWAY_ID"],
                        "secret": OPENAI_EXECUTOR_SECRET_NAME,
                    }
                },
                launch_parameters={"keep_alive_time_seconds": 1800},
            )
        elif status == "suspended":
            await devbox.resume()
        elif status == "suspending":
            await devbox.await_suspended()
            await devbox.resume()
        elif status != "running":
            await devbox.await_running()
        setup = await devbox.cmd.exec(
            "sudo install -d -o user -g user /workspace && "
            "mkdir -p /home/user/.codex-runtime && "
            f"(test -x {CODEX} || "
            "npm install --prefix /home/user/.codex-runtime @openai/codex@alpha) && "
            "command -v flock",
            polling_config=PollingConfig(timeout_seconds=180),
        )
        if setup.exit_code != 0:
            raise RuntimeError("Executor installation failed")
        environment_id = shlex.quote(session.environment.id)
        path = shlex.quote(remote_path(session.environment.remote_url))
        await devbox.cmd.exec_async(
            f"cd /workspace && REMOTE_PATH={path} && "
            'CODEX_API_KEY="$OPENAI_GATEWAY" flock -n /tmp/codex-executor.lock '
            f"{CODEX} exec-server "
            '--remote "${OPENAI_GATEWAY_URL%/}$REMOTE_PATH" '
            f"--environment-id {environment_id} "
            ">> /tmp/codex-executor.log 2>&1"
        )
        print(
            json.dumps(
                {
                    "session_id": session_id,
                    "devbox_id": devbox.id,
                    "action": "started",
                }
            ),
            flush=True,
        )


def initialize_queue(db: sqlite3.Connection) -> None:
    db.execute(
        "CREATE TABLE IF NOT EXISTS jobs ("
        "session_id TEXT PRIMARY KEY, "
        "attempts INTEGER DEFAULT 0, "
        "retry_at REAL DEFAULT 0, "
        "generation INTEGER DEFAULT 0)"
    )
    db.commit()


def enqueue(db: sqlite3.Connection, session_id: str) -> None:
    db.execute(
        "INSERT INTO jobs(session_id) VALUES (?) "
        "ON CONFLICT(session_id) DO UPDATE SET "
        "attempts = 0, retry_at = 0, generation = jobs.generation + 1",
        (session_id,),
    )
    db.commit()


async def process_next_job(db: sqlite3.Connection) -> bool:
    row = db.execute(
        "SELECT session_id, attempts, generation FROM jobs WHERE retry_at <= ? LIMIT 1",
        (time.time(),),
    ).fetchone()
    if row is None:
        return False
    session_id, attempts, generation = row
    try:
        await reconcile(session_id)
    except Exception as error:
        if attempts >= 4:
            db.execute(
                "DELETE FROM jobs WHERE session_id = ? AND generation = ?",
                (session_id, generation),
            )
        else:
            db.execute(
                "UPDATE jobs SET attempts = ?, retry_at = ? "
                "WHERE session_id = ? AND generation = ?",
                (attempts + 1, time.time() + 10, session_id, generation),
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
        db.execute(
            "DELETE FROM jobs WHERE session_id = ? AND generation = ?",
            (session_id, generation),
        )
    db.commit()
    return True


async def drain_queue(db: sqlite3.Connection) -> None:
    while True:
        if not await process_next_job(db):
            await asyncio.sleep(1)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    db = sqlite3.connect(DB_PATH)
    initialize_queue(db)
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
        enqueue(request.app.state.db, event["data"]["id"])
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
