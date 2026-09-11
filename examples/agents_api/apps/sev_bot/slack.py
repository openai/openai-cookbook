"""Publish incident messages and verify Slack callbacks."""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException, Request
from slack_sdk.web.async_client import AsyncWebClient

if TYPE_CHECKING:
    from .agent import Incident

SLACK_CHANNEL = "#oncall"


class SlackChannel:
    """Post incident updates and approval buttons to a Slack thread."""

    def __init__(self, token: str | None = None, channel: str = SLACK_CHANNEL) -> None:
        self.channel = channel
        self.client = AsyncWebClient(token=token or os.environ["SLACK_BOT_TOKEN"])

    async def post(
        self,
        text: str,
        *,
        thread_ts: str | None = None,
        blocks: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"channel": self.channel, "text": text}
        if thread_ts is not None:
            payload["thread_ts"] = thread_ts
        if blocks is not None:
            payload["blocks"] = blocks
        response = await self.client.chat_postMessage(**payload)
        return {"channel": str(response["channel"]), "ts": str(response["ts"])}


def approval_blocks(incident: Incident) -> list[dict[str, Any]]:
    if incident.action is None:
        raise ValueError("No rollback has been proposed.")
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "*Rollback approval required*\n"
                    f"`{incident.action['service']}` to `{incident.action['version']}`\n"
                    f"{incident.action['reason']}\n"
                    "Approval records a decision; it does not execute a deployment."
                ),
            },
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Approve proposal"},
                    "style": "primary",
                    "action_id": "approve_rollback",
                    "value": incident.id,
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Reject"},
                    "action_id": "reject_rollback",
                    "value": incident.id,
                },
            ],
        },
    ]


def verify_slack_request(body: bytes, request: Request) -> None:
    secret = os.environ.get("SLACK_SIGNING_SECRET")
    if not secret:
        raise HTTPException(status_code=500, detail="Set SLACK_SIGNING_SECRET.")

    timestamp = request.headers.get("x-slack-request-timestamp", "")
    signature = request.headers.get("x-slack-signature", "")
    try:
        if abs(time.time() - int(timestamp)) > 300:
            raise ValueError("Expired request.")
    except ValueError as error:
        raise HTTPException(
            status_code=401, detail="Invalid Slack request timestamp."
        ) from error

    digest = hmac.new(
        secret.encode(), b"v0:" + timestamp.encode() + b":" + body, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(signature, f"v0={digest}"):
        raise HTTPException(status_code=401, detail="Invalid Slack request signature.")
