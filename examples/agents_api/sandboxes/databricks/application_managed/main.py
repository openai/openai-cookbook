# /// script
# requires-python = ">=3.11"
# dependencies = ["openai>=3.19.0", "databricks-sdk>=0.153.0"]
# ///
"""Run an OpenAI Agents API task in a Databricks sandbox (application-managed).

The application owns the whole lifecycle: it creates a self-hosted session, provisions
the sandbox and launches codex exec-server itself (all outbound calls), runs one turn,
verifies the agent's file write, then tears everything down. No inbound endpoint or
webhook is involved.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from databricks.sdk import WorkspaceClient
from openai import AsyncOpenAI

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
from common import (  # noqa: E402  (local import after sys.path setup)
    GREETING,
    PROMPT,
    WORK_DIR,
    confirm_executor,
    delete_sandbox,
    delete_session,
    prepare_workspace,
    provision_sandbox,
    run_turn,
    start_executor,
    stop_executor,
    verify_output,
)


async def main(args):
    executor_key = args.executor_api_key
    if not executor_key:
        raise SystemExit(
            "set OPENAI_EXECUTOR_API_KEY to an environment key created on the OpenAI "
            "Agents tab (every other permission None); a general API key is rejected with "
            "'missing required scope api.agents.environments.connect'"
        )

    workspace_client = WorkspaceClient(profile=args.profile)
    name = None
    pid = None
    session = None
    async with AsyncOpenAI(timeout=60) as client:
        try:
            session = await client.beta.agents.sessions.create(
                agent={"model": args.model},
                environment={"type": "self_hosted", "workspace_directory": WORK_DIR},
            )
            print(f"Session: {session.id}", flush=True)

            name = provision_sandbox(
                workspace_client, args.sandbox_id, inactivity_timeout_s=args.inactivity_timeout
            )
            print(f"Sandbox: {name}", flush=True)
            prepare_workspace(workspace_client, name)

            pid = start_executor(
                workspace_client,
                name,
                environment_id=session.environment.id,
                remote_url=session.environment.remote_url,
                executor_api_key=executor_key,
            )
            confirm_executor(workspace_client, name, pid)

            await run_turn(client, session.id, PROMPT)
            verify_output(workspace_client, name, GREETING)
            print("\nVerified the agent's file write.", flush=True)
        finally:
            # Nested finally so a failure in one teardown step still attempts the rest.
            try:
                if pid is not None:
                    stop_executor(workspace_client, name, pid)
            finally:
                try:
                    if session is not None:
                        await delete_session(client, session.id)
                finally:
                    if name is not None and not args.keep_sandbox:
                        delete_sandbox(workspace_client, name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default=os.environ.get("DATABRICKS_CONFIG_PROFILE"))
    parser.add_argument("--sandbox-id", default="openai-agent-sandbox")
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--inactivity-timeout", type=int, default=900)
    parser.add_argument(
        "--executor-api-key",
        default=os.environ.get("OPENAI_EXECUTOR_API_KEY"),
        help="OpenAI environment key passed to codex as CODEX_API_KEY. Required. "
        "Defaults to the OPENAI_EXECUTOR_API_KEY env var.",
    )
    parser.add_argument("--keep-sandbox", action="store_true", help="Do not delete the sandbox on exit")
    asyncio.run(main(parser.parse_args()))
