# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "openai>=3.13.0",
#     "aiohttp",
#     "docker",
#     "fastapi",
#     "python-dotenv",
#     "slack-sdk",
#     "uvicorn",
# ]
# ///

"""Receive incident alerts, Agents API webhooks, and Slack callbacks."""

from __future__ import annotations

import hmac
import json
import logging
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from openai import AsyncOpenAI, InvalidWebhookSignatureError, OpenAI

# Support direct execution from any working directory.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))


from examples.agents_api.apps.sev_bot.agent import IncidentBot
from examples.agents_api.apps.sev_bot.alerts import queue_alerts
from examples.agents_api.apps.sev_bot.slack import verify_slack_request

EXAMPLE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    if not os.environ.get("OPENAI_WEBHOOK_SECRET"):
        raise RuntimeError(
            "Configure the Agents API webhook and set OPENAI_WEBHOOK_SECRET."
        )
    async with AsyncOpenAI() as client:
        app.state.bot = IncidentBot(client)
        try:
            yield
        finally:
            await app.state.bot.close()


app = FastAPI(title="SRE agent for incident response", lifespan=lifespan)


@app.post("/webhooks/alerts")
async def receive_alert(request: Request, tasks: BackgroundTasks) -> dict[str, Any]:
    expected = os.environ.get("ALERT_WEBHOOK_TOKEN")
    authorization = request.headers.get("authorization", "")
    if expected and not hmac.compare_digest(authorization, f"Bearer {expected}"):
        raise HTTPException(status_code=401, detail="Invalid alert webhook token.")

    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=400, detail="Expected an incident webhook payload."
        )
    return queue_alerts(app.state.bot, payload, tasks)


@app.post("/webhooks/openai")
async def openai_webhook(request: Request) -> dict[str, Any]:
    secret = os.environ.get("OPENAI_WEBHOOK_SECRET")
    if not secret:
        raise HTTPException(status_code=500, detail="Set OPENAI_WEBHOOK_SECRET.")
    body = await request.body()
    try:
        with OpenAI(webhook_secret=secret) as verifier:
            verifier.webhooks.verify_signature(payload=body, headers=request.headers)
    except (InvalidWebhookSignatureError, ValueError) as error:
        raise HTTPException(
            status_code=401, detail="Invalid OpenAI webhook signature."
        ) from error
    try:
        event = json.loads(body)
    except ValueError as error:
        raise HTTPException(status_code=400, detail="Invalid webhook JSON.") from error
    if event.get("type") == "agent.session.action_required":
        data = event["data"]
        if data.get("required_action", {}).get("type") == "function_call":
            # Finish before acknowledging so a failed Slack delivery can be retried.
            await app.state.bot.request_approval(data["id"])
    return {"status": "ok"}


@app.post("/slack/events")
async def slack_events(request: Request, tasks: BackgroundTasks) -> dict[str, Any]:
    body = await request.body()
    verify_slack_request(body, request)
    payload = json.loads(body)
    if payload.get("type") == "url_verification":
        return {"challenge": str(payload["challenge"])}

    bot: IncidentBot = app.state.bot
    delivery = str(payload.get("event_id", ""))
    if delivery and delivery in bot.slack_deliveries:
        return {"status": "already_processed"}

    event = payload.get("event", {})
    if not isinstance(event, dict) or event.get("bot_id") or event.get("subtype"):
        return {"status": "ignored"}

    incident_id = bot.slack_threads.get(str(event.get("thread_ts", "")))
    if incident_id is None:
        return {"status": "ignored"}

    if delivery:
        bot.slack_deliveries.add(delivery)
    tasks.add_task(
        bot.investigate, bot.incident(incident_id), str(event.get("text", ""))
    )
    return {"status": "accepted"}


@app.post("/slack/actions")
async def slack_actions(request: Request, tasks: BackgroundTasks) -> dict[str, Any]:
    body = await request.body()
    verify_slack_request(body, request)
    encoded = parse_qs(body.decode()).get("payload", [])
    if not encoded:
        raise HTTPException(status_code=400, detail="Missing Slack action payload.")

    payload = json.loads(encoded[0])
    action = payload["actions"][0]
    bot: IncidentBot = app.state.bot
    incident_id = str(action["value"])
    try:
        if action["action_id"] not in {"approve_rollback", "reject_rollback"}:
            raise ValueError("Unknown Slack approval action.")
        bot.incident(incident_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    tasks.add_task(
        bot.submit_slack_decision,
        incident_id,
        action["action_id"] == "approve_rollback",
    )
    return {"text": "Submitting your decision to the agent."}


def main() -> None:
    import uvicorn

    load_dotenv(EXAMPLE_DIR / ".env")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    uvicorn.run(app, host="127.0.0.1", port=8003)


if __name__ == "__main__":
    main()
