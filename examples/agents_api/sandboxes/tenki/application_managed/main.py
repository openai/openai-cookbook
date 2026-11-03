# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "openai>=3.13.0",
#     "tenki[async]>=1.4.1",
# ]
# ///

"""Run two Agents API turns in a Tenki worker, pausing it between them, then clean up."""

import asyncio
import os
import sys
from pathlib import Path

from openai import AsyncOpenAI
from tenki import AsyncClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sandbox import (
    WORKSPACE,
    create_worker,
    ensure_executor_installed,
    start_executor,
    stop_executor,
)

BRIEF = "Migrate a synchronous Python service to async without changing its API.\n"
FAILURE_EVENTS = {
    "error",
    "agent.session.environment.failed",
    "agent.session.failed",
    "agent.session.turn.failed",
    "agent.session.turn.cancelled",
}


async def run_turn(client: AsyncOpenAI, session_id: str, text: str) -> None:
    async with client.beta.agents.sessions.stream(session_id, input=text) as events:
        async for event in events:
            if event.type in FAILURE_EVENTS:
                raise RuntimeError(f"Agent failed: {event.type}")
            if event.type == "agent.session.turn.output_text.delta":
                print(event.delta, end="", flush=True)
    print(flush=True)


async def main() -> None:
    executor_key = os.environ["OPENAI_EXECUTOR_API_KEY"]
    async with AsyncOpenAI(timeout=360) as client, AsyncClient() as tenki:
        session = await client.beta.agents.sessions.create(
            agent={"model": "gpt-5.6-sol"},
            environment={"type": "self_hosted", "workspace_directory": WORKSPACE},
        )
        sandbox = None
        print(f"Session: {session.id}", flush=True)
        try:
            assert session.environment.type == "self_hosted"
            async with asyncio.timeout(600):
                sandbox = await create_worker(
                    tenki, session.id, max_duration=900, pause_retention=3600
                )
                print(f"Sandbox: {sandbox.id}", flush=True)
                await ensure_executor_installed(sandbox)
                await sandbox.exec("sh", "-c", f"cat > {WORKSPACE}/brief.txt", input=BRIEF)
                remote_url = session.environment.remote_url
                environment_id = session.environment.id
                await start_executor(sandbox, remote_url, environment_id, executor_key)

                await run_turn(
                    client,
                    session.id,
                    "Read brief.txt and write a five-step migration plan to plan.md.",
                )

                # Between turns the worker costs nothing: pause it, keeping memory
                # and disk. Resume restores the same sandbox, with plan.md in place.
                await stop_executor(sandbox)
                await sandbox.pause()
                await sandbox.wait_paused()
                print(f"Paused: {sandbox.id} ({sandbox.state})", flush=True)
                await sandbox.resume()
                await sandbox.wait_ready()
                print(f"Resumed: {sandbox.id} ({sandbox.state})", flush=True)
                await start_executor(sandbox, remote_url, environment_id, executor_key)

                await run_turn(
                    client,
                    session.id,
                    "Add a one-line risk under each step in plan.md.",
                )

                plan = await sandbox.exec("cat", f"{WORKSPACE}/plan.md")
                if plan.exit_code != 0 or not plan.stdout_text.strip():
                    raise RuntimeError("The agent did not write a migration plan")
                print(f"\nplan.md:\n{plan.stdout_text}")
        finally:
            try:
                if sandbox is not None:
                    async with asyncio.timeout(30):
                        await sandbox.terminate()
            finally:
                async with asyncio.timeout(30):
                    await client.beta.agents.sessions.delete(session.id)


if __name__ == "__main__":
    asyncio.run(main())
