# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "openai>=3.13.0",
#     "daytona>=0.207.0",
# ]
# ///

"""Run an Agents API task in a Daytona sandbox and clean up both resources."""

import asyncio
import os
import sys
from pathlib import Path

from daytona import AsyncDaytona, CreateSandboxFromSnapshotParams
from openai import AsyncOpenAI

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sandbox import WORKSPACE, install_executor, start_executor

BRIEF = "Migrate a synchronous Python service to async without changing its API.\n"


async def main() -> None:
    executor_key = os.environ["OPENAI_EXECUTOR_API_KEY"]
    async with AsyncOpenAI(timeout=360) as client, AsyncDaytona() as daytona:
        session = await client.beta.agents.sessions.create(
            agent={"model": "gpt-5.6-sol"},
            environment={"type": "self_hosted", "workspace_directory": WORKSPACE},
        )
        sandbox = None
        print(f"Session: {session.id}", flush=True)
        try:
            assert session.environment.type == "self_hosted"
            async with asyncio.timeout(360):
                sandbox = await daytona.create(
                    CreateSandboxFromSnapshotParams(
                        name=f"agents-api-{session.id[-12:]}",
                        language="javascript",
                        env_vars={"CODEX_API_KEY": executor_key},
                        auto_stop_interval=0,
                        ttl_minutes=10,
                    ),
                    timeout=90,
                )
                print(f"Sandbox: {sandbox.id}", flush=True)
                await install_executor(sandbox)
                await sandbox.fs.upload_file(BRIEF.encode(), f"{WORKSPACE}/brief.txt")
                await start_executor(
                    sandbox,
                    session.environment.remote_url,
                    session.environment.id,
                )

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

                plan = (await sandbox.fs.download_file(f"{WORKSPACE}/plan.md")).decode(
                    "utf-8"
                )
                if not plan.strip():
                    raise RuntimeError("The agent did not write a migration plan")
                print(f"\n\nplan.md:\n{plan}")
        finally:
            try:
                if sandbox is not None:
                    async with asyncio.timeout(30):
                        await daytona.delete(sandbox, wait=True)
            finally:
                async with asyncio.timeout(30):
                    await client.beta.agents.sessions.delete(session.id)


if __name__ == "__main__":
    asyncio.run(main())
