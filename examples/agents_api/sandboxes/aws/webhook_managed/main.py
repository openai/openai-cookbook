# /// script
# requires-python = ">=3.11"
# dependencies = ["openai>=3.19.0", "boto3>=1.43.34", "httpx[socks]>=0.27"]
# ///
"""Run an Agents API task in a MicroVM started by a webhook."""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import boto3
from openai import AsyncOpenAI

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
from common import (
    GREETING,
    OUTPUT_PATH,
    RESUME_PROMPT,
    delete_session,
    download_file,
    run_turn,
    suspend_environment,
    terminate_microvm,
    verify_output,
    wait_for_microvm,
)


async def main(args):
    async with AsyncOpenAI(timeout=60) as client:
        if args.create_agent:
            agent = await client.beta.agents.create(model="gpt-5.6-sol", name=args.create_agent)
            print(f"Agent: {agent.id}")
            return
        state = json.loads(args.state.read_text())
        aws = boto3.Session(
            profile_name=args.profile or state.get("profile"), region_name=state["region"]
        )
        microvms = aws.client("lambda-microvms")
        session = await client.beta.agents.sessions.create(
            agent_id=state["agent_id"],
            environment={"type": "self_hosted", "workspace_directory": "/workspace"},
            metadata={"aws_suspend_resume": "true"} if args.suspend_resume else {},
        )
        print(f"Session: {session.id}", flush=True)
        vm_id = None
        try:
            await run_turn(client, session.id)
            session = await client.beta.agents.sessions.retrieve(session.id)
            vm_id = session.metadata["aws_microvm_id"]
            print(f"MicroVM: {vm_id}", flush=True)
            await download_file(microvms, vm_id, OUTPUT_PATH, args.output)
            verify_output(args.output, GREETING)
            if args.suspend_resume:
                await suspend_environment(client, microvms, session.id, vm_id)
                await run_turn(client, session.id, RESUME_PROMPT)
                session = await client.beta.agents.sessions.retrieve(session.id)
                if session.metadata["aws_microvm_id"] != vm_id:
                    raise RuntimeError("The webhook replaced the VM instead of resuming it")
                wait_for_microvm(microvms, vm_id, "RUNNING")
                await download_file(microvms, vm_id, OUTPUT_PATH, args.output)
                verify_output(args.output, GREETING)
        finally:
            try:
                # The handler may still be saving the VM ID after a client timeout.
                for _ in range(30):
                    session = await client.beta.agents.sessions.retrieve(session.id)
                    vm_id = vm_id or (session.metadata or {}).get("aws_microvm_id")
                    if vm_id:
                        terminate_microvm(microvms, vm_id)
                        break
                    await asyncio.sleep(1)
                else:
                    raise RuntimeError(
                        "No VM ID recorded; check launcher logs for pending launches"
                    )
            finally:
                await delete_session(client, session.id)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--create-agent", metavar="NAME")
    parser.add_argument("--state", type=Path, default=ROOT / ".local/deployment.json")
    parser.add_argument("--profile", default=os.environ.get("AWS_PROFILE"))
    parser.add_argument("--output", type=Path, default=ROOT / ".local/hello.txt")
    parser.add_argument(
        "--suspend-resume", action="store_true", help="Run a second turn after suspending the VM"
    )
    asyncio.run(main(parser.parse_args()))
