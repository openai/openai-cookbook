"""
Slack DM posting utility.

Posts messages to Slack users via the Slack Web API (chat.postMessage).
Requires SLACK_BOT_TOKEN with chat:write and im:write scopes.

Usage:
  from tools.utils.slack_post import post_slack_dm
  post_slack_dm("U01234567", "Hello!")
"""
import os
from typing import Any

import requests

SLACK_API_URL = "https://slack.com/api/chat.postMessage"
SLACK_MSG_MAX_LEN = 40000  # Slack limit ~40k chars per message


def post_slack_dm(
    user_id: str,
    text: str,
    token: str | None = None,
) -> tuple[bool, str]:
    """
    Post a direct message to a Slack user.

    Args:
        user_id: Slack user ID (e.g. U01234567). Get from Profile > Copy member ID.
        text: Message text. Slack format: *bold* _italic_ <url|link text>
        token: Slack Bot Token (xoxb-...). Defaults to SLACK_BOT_TOKEN env var.

    Returns:
        (success: bool, message: str) — success status and error/success message.
    """
    token = token or os.environ.get("SLACK_BOT_TOKEN", "").strip()
    if not token:
        return False, "SLACK_BOT_TOKEN not set. Add to .env (Bot Token from api.slack.com/apps)."

    user_id = (user_id or "").strip()
    if not user_id or not user_id.startswith("U"):
        return False, f"Invalid Slack user_id: {user_id!r}. Must start with U (e.g. U01234567)."

    if len(text) > SLACK_MSG_MAX_LEN:
        text = text[: SLACK_MSG_MAX_LEN - 50] + "\n\n...(truncated)"

    try:
        resp = requests.post(
            SLACK_API_URL,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"channel": user_id, "text": text},
            timeout=15,
        )
        data = resp.json()
        if not data.get("ok"):
            err = data.get("error", "unknown")
            return False, f"Slack API error: {err}"
        return True, "Message sent."
    except requests.RequestException as e:
        return False, f"Request failed: {e}"
