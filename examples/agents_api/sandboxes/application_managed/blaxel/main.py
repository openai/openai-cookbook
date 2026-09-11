# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "openai>=3.13.0",
#     "blaxel>=0.4.3",
# ]
# ///

"""Run an Agents API task in a Blaxel sandbox and clean up both resources."""

import asyncio
import os
import shlex

from blaxel.core.sandbox import SandboxInstance
from openai import AsyncOpenAI

WORKSPACE = "/workspace"
BRIEF = "Migrate a synchronous Python service to async without changing its API.\n"


async def main() -> None:
    executor_key = os.environ["OPENAI_EXECUTOR_API_KEY"]
    async with AsyncOpenAI(timeout=360) as client:
        session = await client.beta.agents.sessions.create(
            agent={"model": "gpt-5.6-sol"},
            environment={"type": "self_hosted", "workspace_directory": WORKSPACE},
        )
        sandbox = None
        print(f"Session: {session.id}", flush=True)
        try:
            assert session.environment.type == "self_hosted"
            executor_args = [
                "exec-server",
                "--remote",
                session.environment.remote_url,
                "--environment-id",
                session.environment.id,
            ]
            async with asyncio.timeout(360):
                sandbox = await SandboxInstance.create(
                    {
                        "name": f"agents-api-{session.id[-12:]}",
                        "image": "blaxel/node:latest",
                        "region": os.environ.get("BL_REGION", "us-pdx-1"),
                        "ttl": "10m",
                    }
                )
                print(f"Sandbox: {sandbox.metadata.name}", flush=True)
                setup = await sandbox.process.exec(
                    {
                        "command": "mkdir -p /workspace && npm install -g @openai/codex@alpha",
                        "wait_for_completion": True,
                        "timeout": 180,
                    }
                )
                if setup.exit_code != 0:
                    raise RuntimeError("Executor installation failed")
                await sandbox.fs.write(f"{WORKSPACE}/brief.txt", BRIEF)
                await sandbox.process.exec(
                    {
                        "command": shlex.join(["codex", *executor_args]),
                        "working_dir": WORKSPACE,
                        "env": {"CODEX_API_KEY": executor_key},
                        "wait_for_completion": False,
                        "keep_alive": True,
                        "timeout": 600,
                    }
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

                plan = await sandbox.fs.read(f"{WORKSPACE}/plan.md")
                if not plan.strip():
                    raise RuntimeError("The agent did not write a migration plan")
                print(f"\n\nplan.md:\n{plan}")
        finally:
            try:
                if sandbox is not None:
                    async with asyncio.timeout(30):
                        await SandboxInstance.delete(sandbox.metadata.name)
            finally:
                async with asyncio.timeout(30):
                    await client.beta.agents.sessions.delete(session.id)


if __name__ == "__main__":
    asyncio.run(main())
