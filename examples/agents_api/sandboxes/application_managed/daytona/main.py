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
import shlex

from daytona import AsyncDaytona, CreateSandboxFromSnapshotParams, SessionExecuteRequest
from openai import AsyncOpenAI

WORKSPACE = "/workspace"
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
            executor_args = [
                "exec-server",
                "--remote",
                session.environment.remote_url,
                "--environment-id",
                session.environment.id,
            ]
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
                setup = await sandbox.process.exec(
                    "sudo install -d -o daytona -g daytona /workspace && "
                    "npm install -g --prefix /home/daytona/.local @openai/codex@alpha",
                    timeout=180,
                )
                if setup.exit_code != 0:
                    raise RuntimeError("Executor installation failed")
                await sandbox.fs.upload_file(BRIEF.encode(), f"{WORKSPACE}/brief.txt")
                await sandbox.process.create_session("executor")
                command = shlex.join(["/home/daytona/.local/bin/codex", *executor_args])
                await sandbox.process.execute_session_command(
                    "executor",
                    SessionExecuteRequest(
                        command=f"cd {WORKSPACE} && exec {command}",
                        run_async=True,
                    ),
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
