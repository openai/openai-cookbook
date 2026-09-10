# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "openai>=3.13.0",
#     "pydo[aio]>=0.40.0b7",
# ]
# pydo = { url = "https://github.com/digitalocean/pydo/releases/download/v0.40.0-beta.7/pydo-0.40.0b7-py3-none-any.whl" }
# ///

"""Run an Agents API task in a DigitalOcean sandbox and clean up both resources."""

import asyncio
import os
from pathlib import Path

from openai import AsyncOpenAI
from pydo.aio import Client

WORKSPACE = "/workspace"
MANIFEST = Path(__file__).with_name("agents.yaml")


async def main() -> None:
    executor_key = os.environ["OPENAI_EXECUTOR_API_KEY"]
    async with (
        AsyncOpenAI(timeout=360) as client,
        Client(token=os.environ["DIGITALOCEAN_TOKEN"]) as digitalocean,
    ):
        session = await client.beta.agents.sessions.create(
            agent={"model": "gpt-5.6-sol"},
            environment={"type": "self_hosted", "workspace_directory": WORKSPACE},
        )
        sandbox_id = None
        print(f"Session: {session.id}", flush=True)
        try:
            assert session.environment.type == "self_hosted"
            async with asyncio.timeout(600):
                response = await digitalocean.agents.create_session(
                    params={"openai_session_id": session.id},
                    body={
                        "manifest": MANIFEST.read_text().replace(
                            "{name}", f"agents-api-{session.id[-12:]}"
                        ),
                        "variables": {
                            "ENVIRONMENT_ID": session.environment.id,
                            "EXECUTOR_API_KEY": executor_key,
                        },
                    },
                    timeout=180,
                )
                sandbox_id = response["session"]["session_id"]
                print(f"Sandbox: {sandbox_id}", flush=True)

                async with client.beta.agents.sessions.stream(
                    session.id,
                    input="Write a five-step plan to migrate a synchronous Python service "
                    "to async without changing its API. Save it to /workspace/plan.md.",
                ) as events:
                    async for event in events:
                        if event.type in {
                            "error",
                            "agent.session.environment.failed",
                            "agent.session.failed",
                            "agent.session.turn.failed",
                            "agent.session.turn.cancelled",
                        }:
                            raise RuntimeError(f"Agent failed: {event.type}")
                        if event.type == "agent.session.turn.output_text.delta":
                            print(event.delta, end="", flush=True)
                        if (
                            event.type == "agent.session.turn.completed"
                            and event.turn.subagent_id is None
                        ):
                            break
                    else:
                        raise RuntimeError("Stream ended without a completed turn")

                download = await digitalocean.agents.sessions.workspace_download(
                    sandbox_id, path="plan.md", timeout=60
                )
                plan = (await download.read()).decode("utf-8")
                if not plan.strip():
                    raise RuntimeError("The agent did not write a migration plan")
                print(f"\n\nplan.md:\n{plan}")
        finally:
            try:
                if sandbox_id is not None:
                    async with asyncio.timeout(30):
                        await digitalocean.agents.destroy_session(session_id=sandbox_id)
            finally:
                async with asyncio.timeout(30):
                    await client.beta.agents.sessions.delete(session.id)


if __name__ == "__main__":
    asyncio.run(main())
