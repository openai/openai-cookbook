# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "openai>=3.13.0",
#     "vercel>=0.10.0",
# ]
# ///

"""Run an Agents API task in a Vercel sandbox and clean up both resources."""

import asyncio
import os
import shlex

from openai import AsyncOpenAI
from vercel.sandbox import create_sandbox

WORKSPACE = "/vercel/sandbox/workspace"
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
                sandbox = await create_sandbox(
                    name=f"agents-api-{session.id[-12:]}",
                    execution_time_limit=600,
                    persistent=False,
                )
                print(f"Sandbox: {sandbox.name}", flush=True)
                setup = await sandbox.run_process(
                    "bash",
                    [
                        "-lc",
                        f"mkdir -p {WORKSPACE} && npm install --prefix /vercel/sandbox/.codex-runtime @openai/codex@alpha",
                    ],
                    kill_after=180,
                    capture_output=True,
                )
                if setup.returncode != 0:
                    raise RuntimeError("Executor installation failed")
                await sandbox.fs.write_text(f"{WORKSPACE}/brief.txt", BRIEF)
                command = shlex.join(
                    [
                        "/vercel/sandbox/.codex-runtime/node_modules/.bin/codex",
                        *executor_args,
                    ]
                )
                await sandbox.create_process(
                    "bash",
                    ["-lc", f"cd {WORKSPACE} && exec {command}"],
                    env={"CODEX_API_KEY": executor_key},
                    kill_after=600,
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

                plan = await sandbox.fs.read_text(f"{WORKSPACE}/plan.md")
                if not plan.strip():
                    raise RuntimeError("The agent did not write a migration plan")
                print(f"\n\nplan.md:\n{plan}")
        finally:
            try:
                if sandbox is not None:
                    async with asyncio.timeout(30):
                        await sandbox.destroy()
            finally:
                async with asyncio.timeout(30):
                    await client.beta.agents.sessions.delete(session.id)


if __name__ == "__main__":
    asyncio.run(main())
