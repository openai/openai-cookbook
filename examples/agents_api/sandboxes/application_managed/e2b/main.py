# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "openai>=3.13.0",
#     "e2b>=2.45.1",
# ]
# ///

"""Run an Agents API task in an E2B sandbox and clean up both resources."""

import asyncio
import os
import shlex

from e2b import AsyncSandbox
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
                sandbox = await AsyncSandbox.create(
                    timeout=600,
                    metadata={"agents-session-id": session.id},
                    network={"allow_public_traffic": False},
                )
                print(f"Sandbox: {sandbox.sandbox_id}", flush=True)
                await sandbox.commands.run(
                    "mkdir -p /workspace && npm install -g @openai/codex@alpha",
                    user="root",
                    timeout=180,
                )
                await sandbox.files.write(f"{WORKSPACE}/brief.txt", BRIEF, user="root")
                await sandbox.commands.run(
                    shlex.join(["codex", *executor_args]),
                    envs={"CODEX_API_KEY": executor_key},
                    user="root",
                    cwd=WORKSPACE,
                    background=True,
                    timeout=0,
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

                plan = await sandbox.files.read(f"{WORKSPACE}/plan.md", user="root")
                if not plan.strip():
                    raise RuntimeError("The agent did not write a migration plan")
                print(f"\n\nplan.md:\n{plan}")
        finally:
            try:
                if sandbox is not None:
                    async with asyncio.timeout(30):
                        await sandbox.kill()
            finally:
                async with asyncio.timeout(30):
                    await client.beta.agents.sessions.delete(session.id)


if __name__ == "__main__":
    asyncio.run(main())
