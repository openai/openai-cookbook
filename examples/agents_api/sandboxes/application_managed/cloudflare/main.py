# /// script
# requires-python = ">=3.11"
# dependencies = ["openai>=3.13.0", "httpx>=0.27"]
# ///

"""Provision a Cloudflare sandbox through your Worker, without webhooks."""

import asyncio
import os

import httpx
from openai import AsyncOpenAI


async def main() -> None:
    async with (
        AsyncOpenAI(timeout=360) as client,
        httpx.AsyncClient(
            base_url=os.environ["CLOUDFLARE_SANDBOX_WORKER_URL"],
            headers={"Authorization": f"Bearer {os.environ['SANDBOX_CONTROL_TOKEN']}"},
            timeout=180,
        ) as worker,
    ):
        session = await client.beta.agents.sessions.create(
            agent={"model": "gpt-5.6-sol"},
            environment={"type": "self_hosted", "workspace_directory": "/workspace"},
        )
        print(f"Session: {session.id}", flush=True)
        path = f"/sandboxes/{session.id}"
        try:
            assert session.environment.type == "self_hosted"
            async with asyncio.timeout(360):
                response = await worker.post(
                    path,
                    json={
                        "environment_id": session.environment.id,
                        "remote_url": session.environment.remote_url,
                    },
                )
                response.raise_for_status()
                print(f"Sandbox: {session.id}", flush=True)

                async with client.beta.agents.sessions.stream(
                    session.id,
                    input="Read brief.txt and write a five-step migration plan to plan.md.",
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

                response = await worker.get(f"{path}/plan")
                response.raise_for_status()
                plan = response.text
                if not plan.strip():
                    raise RuntimeError("The agent did not write a migration plan")
                print(f"\n\nplan.md:\n{plan}")
        finally:
            try:
                async with asyncio.timeout(30):
                    response = await worker.delete(path)
                    response.raise_for_status()
            finally:
                async with asyncio.timeout(30):
                    await client.beta.agents.sessions.delete(session.id)


if __name__ == "__main__":
    asyncio.run(main())
