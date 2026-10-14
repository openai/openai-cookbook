# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "openai>=3.13.0",
#     "aiohttp",
#     "docker",
#     "python-dotenv",
#     "slack-bolt",
# ]
# ///

"""Start the Slack bot with Socket Mode."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import AsyncOpenAI

# Support direct execution from any working directory.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))


from examples.agents_api.apps.slack_bot.agent import SlackBot

EXAMPLE_DIR = Path(__file__).resolve().parent


async def run_slack() -> None:
    from slack_bolt.adapter.socket_mode.aiohttp import AsyncSocketModeHandler
    from slack_bolt.async_app import AsyncApp
    from slack_bolt.context.async_context import AsyncBoltContext
    from slack_bolt.context.say.async_say import AsyncSay

    app = AsyncApp(token=os.environ["SLACK_BOT_TOKEN"])

    async with AsyncOpenAI() as client:
        bot = SlackBot(client, app.client)

        async def handle_message(
            event: dict[str, Any], context: AsyncBoltContext, say: AsyncSay
        ) -> None:
            if event.get("bot_id"):
                return

            question = (
                str(event.get("text", ""))
                .replace(f"<@{context.bot_user_id}>", "")
                .strip()
            )
            if not question:
                return

            channel = str(event["channel"])
            thread_ts = str(event.get("thread_ts") or event["ts"])
            team_id = str(context.team_id or event.get("team", ""))
            thread_id = f"{team_id}:{channel}:{thread_ts}"
            message_id = f"{team_id}:{channel}:{event['ts']}"
            if message_id in bot.seen_messages:
                return
            bot.seen_messages.add(message_id)

            if thread_id in bot.active:
                if question.lower() in {"stop", "cancel", "stop this", "cancel this"}:
                    await bot.cancel(thread_id)
                    await say(text="Stopping your request.", thread_ts=thread_ts)
                else:
                    await bot.steer(thread_id, question)
                    await say(
                        text="Got it. Updating your request.", thread_ts=thread_ts
                    )
                return

            status = await say(text="Checking your request...", thread_ts=thread_ts)
            status_ts = str(status["ts"])

            async def update_progress(message: str) -> None:
                await context.client.chat_update(
                    channel=channel, ts=status_ts, text=message
                )

            try:
                reply = await bot.answer(
                    question,
                    thread_id=thread_id,
                    team_id=team_id,
                    channel_id=channel,
                    on_progress=update_progress,
                )
            except Exception:
                logging.exception("Slack request failed for thread %s", thread_id)
                await context.client.chat_update(
                    channel=channel,
                    ts=status_ts,
                    text="I could not complete that request. Check the bot's logs and try again.",
                )
                return

            await context.client.chat_update(channel=channel, ts=status_ts, text=reply)

        @app.event("app_mention")
        async def reply_to_mention(
            event: dict[str, Any], context: AsyncBoltContext, say: AsyncSay
        ) -> None:
            await handle_message(event, context, say)

        @app.event("message")
        async def reply_to_message(
            event: dict[str, Any], context: AsyncBoltContext, say: AsyncSay
        ) -> None:
            if event.get("channel_type") != "im":
                thread_ts = event.get("thread_ts")
                if thread_ts is None:
                    return
                thread_id = f"{context.team_id}:{event['channel']}:{thread_ts}"
                if thread_id not in bot.sessions:
                    return
            await handle_message(event, context, say)

        try:
            await AsyncSocketModeHandler(
                app, os.environ["SLACK_APP_TOKEN"]
            ).start_async()
        finally:
            await bot.close()


def main() -> None:
    load_dotenv(EXAMPLE_DIR / ".env")
    asyncio.run(run_slack())


if __name__ == "__main__":
    main()
