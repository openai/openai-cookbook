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
import sqlite3
import sys
import time
import traceback
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from openai import AsyncOpenAI, InvalidWebhookSignatureError, NotFoundError, OpenAI
from runloop_api_client import AsyncRunloopSDK
from runloop_api_client.sdk.async_devbox import AsyncDevbox
from runloop_api_client.sdk.async_execution import AsyncExecution

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sandbox import LOCK_BUSY_EXIT_CODE, install_executor, start_executor

DB_PATH = os.environ.get("QUEUE_PATH", "/home/user/pending.sqlite3")
OPENAI_EXECUTOR_SECRET_NAME = "agents_api_webhook_openai_executor_api_key"
EXECUTOR_CONNECT_TIMEOUT = 60


def log(**fields: object) -> None:
    print(json.dumps(fields), flush=True)


async def find_devbox(
    runloop: AsyncRunloopSDK, session_id: str
) -> tuple[AsyncDevbox | None, str | None]:
    async for info in await runloop.api.devboxes.list(include_total_count=False):
        if info.status not in {"failure", "shutdown"} and (
            (info.metadata or {}).get("agents-session-id") == session_id
        ):
            return runloop.devbox.from_id(info.id), info.status
    return None, None


async def wait_for_executor(
    client: AsyncOpenAI, session_id: str, execution: AsyncExecution
) -> None:
    async with asyncio.timeout(EXECUTOR_CONNECT_TIMEOUT):
        while True:
            session = await client.beta.agents.sessions.retrieve(session_id)
            if session.status == "failed":
                raise RuntimeError("Session failed before the executor connected")
            if not any(
                action.type == "environment_connection"
                for action in session.required_actions
            ):
                return
            state = await execution.get_state()
            # A duplicate launch loses the lock; wait for the existing executor.
            if state.status == "completed" and state.exit_status != LOCK_BUSY_EXIT_CODE:
                raise RuntimeError("Executor exited; inspect /tmp/codex-executor.log")
            await asyncio.sleep(2)


async def reconcile(session_id: str) -> None:
    async with (
        AsyncOpenAI(
            api_key=os.environ["OPENAI_GATEWAY"],
            base_url=f"{os.environ['OPENAI_GATEWAY_URL'].rstrip('/')}/v1",
            timeout=30,
        ) as client,
        AsyncRunloopSDK() as runloop,
    ):
        try:
            session = await client.beta.agents.sessions.retrieve(session_id)
        except NotFoundError:
            return
        if (
            session.environment.type != "self_hosted"
            or session.agent.id != os.environ["OPENAI_AGENT_ID"]
        ):
            return
        if session.status != "failed" and not any(
            action.type == "environment_connection"
            for action in session.required_actions
        ):
            return
        devbox, status = await find_devbox(runloop, session_id)
        if session.status == "failed":
            if devbox is not None:
                await devbox.shutdown()
            return
        if devbox is None:
            devbox = await runloop.devbox.create(
                name=f"agents-webhook-{session_id[-24:]}",
                metadata={"agents-session-id": session_id},
                secrets={"CODEX_API_KEY": OPENAI_EXECUTOR_SECRET_NAME},
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
            "sudo install -d -o user -g user /workspace && command -v flock"
        )
        if setup.exit_code != 0:
            raise RuntimeError("Workspace setup failed")
        await install_executor(devbox)
        execution = await start_executor(
            devbox,
            workspace="/workspace",
            remote_url=session.environment.remote_url,
            environment_id=session.environment.id,
            locked=True,
        )
        await wait_for_executor(client, session_id, execution)
        log(session_id=session_id, devbox_id=devbox.id, action="connected")


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
    except Exception as error:  # noqa: BLE001 - Keep failed jobs in the retry queue.
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
        log(
            session_id=session_id,
            error_type=type(error).__name__,
            error_at=[
                f"{frame.name}:{frame.lineno}"
                for frame in traceback.extract_tb(error.__traceback__)
            ],
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
        log(event_id=event["id"], session_id=event["data"]["id"], action="enqueued")
    return JSONResponse({"ok": True})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
