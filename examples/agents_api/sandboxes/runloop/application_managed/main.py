# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "openai>=3.13.0",
#     "runloop-api-client>=1.31.0",
# ]
# ///

"""Run an Agents API task in a Runloop devbox and clean up both resources."""

import asyncio
import os
import sys
from pathlib import Path

from openai import AsyncOpenAI
from runloop_api_client import AsyncRunloopSDK

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sandbox import install_executor, start_executor

WORKSPACE = "/home/user/workspace"


async def main() -> None:
    executor_key = os.environ["OPENAI_EXECUTOR_API_KEY"]
    async with AsyncOpenAI(timeout=360) as client, AsyncRunloopSDK() as runloop:
        session = await client.beta.agents.sessions.create(
            agent={"model": "gpt-5.6-sol"},
            environment={"type": "self_hosted", "workspace_directory": WORKSPACE},
        )
        devbox = None
        print(f"Session: {session.id}", flush=True)
        try:
            assert session.environment.type == "self_hosted"
            async with asyncio.timeout(300):
                devbox = await runloop.devbox.create(
                    name=f"agents-api-{session.id[-12:]}",
                    environment_variables={"CODEX_API_KEY": executor_key},
                    launch_parameters={"keep_alive_time_seconds": 600},
                )
                print(f"Devbox: {devbox.id}", flush=True)
                setup = await devbox.cmd.exec(f"mkdir -p {WORKSPACE}")
                if setup.exit_code != 0:
                    raise RuntimeError("Workspace setup failed")
                await install_executor(devbox)
                await devbox.file.write(
                    file_path=f"{WORKSPACE}/brief.txt",
                    contents="Migrate a synchronous Python service to async without changing its API.\n",
                )
                await start_executor(
                    devbox,
                    workspace=WORKSPACE,
                    remote_url=session.environment.remote_url,
                    environment_id=session.environment.id,
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

                plan = await devbox.file.read(file_path=f"{WORKSPACE}/plan.md")
                if not plan.strip():
                    raise RuntimeError("The agent did not write a migration plan")
                print(f"\n\nplan.md:\n{plan}")
        finally:
            try:
                if devbox is not None:
                    async with asyncio.timeout(30):
                        await devbox.shutdown()
            finally:
                async with asyncio.timeout(30):
                    await client.beta.agents.sessions.delete(session.id)


if __name__ == "__main__":
    asyncio.run(main())
