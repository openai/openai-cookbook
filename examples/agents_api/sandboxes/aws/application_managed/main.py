# /// script
# requires-python = ">=3.11"
# dependencies = ["openai>=3.19.0", "boto3>=1.43.34", "httpx[socks]>=0.27"]
# ///
"""Run an Agents API task in an AWS Lambda MicroVM."""

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
    launch_microvm,
    resume_microvm,
    run_turn,
    suspend_environment,
    terminate_microvm,
    verify_output,
)


async def main(args):
    image = json.loads(args.image_state.read_text())
    execution = json.loads(args.execution_state.read_text())
    aws = boto3.Session(profile_name=args.profile, region_name=image["region"])
    microvms = aws.client("lambda-microvms")
    microvms.get_microvm_image(imageIdentifier=image["image_arn"])
    async with AsyncOpenAI(timeout=60) as client:
        session = await client.beta.agents.sessions.create(
            agent={"model": "gpt-5.6-sol"},
            environment={"type": "self_hosted", "workspace_directory": "/workspace"},
        )
        print(f"Session: {session.id}", flush=True)
        vm_id = None
        try:
            vm = launch_microvm(
                microvms, session.environment, image, execution, suspend_resume=args.suspend_resume
            )
            vm_id = vm["microvmId"]
            print(f"MicroVM: {vm_id}", flush=True)
            await run_turn(client, session.id)
            await download_file(microvms, vm_id, OUTPUT_PATH, args.output)
            verify_output(args.output, GREETING)
            if args.suspend_resume:
                await suspend_environment(client, microvms, session.id, vm_id)
                resume_microvm(microvms, vm_id)
                await run_turn(client, session.id, RESUME_PROMPT)
                await download_file(microvms, vm_id, OUTPUT_PATH, args.output)
                verify_output(args.output, GREETING)
        finally:
            try:
                if vm_id:
                    terminate_microvm(microvms, vm_id)
            finally:
                await delete_session(client, session.id)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default=os.environ.get("AWS_PROFILE"))
    parser.add_argument("--image-state", type=Path, default=ROOT / ".local/image.json")
    parser.add_argument("--execution-state", type=Path, default=ROOT / ".local/execution-role.json")
    parser.add_argument("--output", type=Path, default=ROOT / ".local/hello.txt")
    parser.add_argument(
        "--suspend-resume", action="store_true", help="Run a second turn after suspending the VM"
    )
    asyncio.run(main(parser.parse_args()))
