"""Shared MicroVM and session operations."""

import asyncio
import json
import time
from urllib.parse import quote

import httpx
from openai import APIStatusError, NotFoundError

GREETING = "Hello from AWS Lambda MicroVMs!\n"
OUTPUT_PATH = "hello.txt"
PROMPT = f"Write {GREETING!r} to /workspace/{OUTPUT_PATH}."
RESUME_PROMPT = f"Read /workspace/{OUTPUT_PATH} and tell me what it says."


def launch_microvm(microvms, environment, image, execution, *, suspend_resume=False):
    region = microvms.meta.region_name
    connector = f"arn:aws:lambda:{region}:aws:network-connector:aws-network-connector"
    return microvms.run_microvm(
        imageIdentifier=image["image_arn"],
        imageVersion=image["image_version"],
        executionRoleArn=execution["role_arn"],
        runHookPayload=json.dumps(
            {
                "environment_id": environment.id,
                "remote_url": environment.remote_url,
                "executor_secret_arn": execution["executor_secret_arn"],
            }
        ),
        maximumDurationInSeconds=900,
        idlePolicy={
            "maxIdleDurationSeconds": 600,
            "suspendedDurationSeconds": 300 if suspend_resume else 0,
            "autoResumeEnabled": False,
        },
        ingressNetworkConnectors=[f"{connector}:ALL_INGRESS"],
        egressNetworkConnectors=[f"{connector}:INTERNET_EGRESS"],
    )


async def run_turn(client, session_id, prompt=PROMPT):
    async with asyncio.timeout(420):
        async with client.beta.agents.sessions.stream(session_id, input=prompt) as events:
            async for event in events:
                if event.type == "agent.session.turn.output_text.delta":
                    print(event.delta, end="", flush=True)
                elif event.type in {
                    "agent.session.turn.completed",
                    "agent.session.turn.failed",
                    "agent.session.turn.cancelled",
                }:
                    if event.turn.subagent_id is not None:
                        continue
                    if event.type != "agent.session.turn.completed":
                        raise RuntimeError(f"Turn failed: {event.type}")
                    print(f"\nCompleted turn: {event.turn.id}", flush=True)
                    return
                elif event.type in {
                    "error",
                    "agent.session.failed",
                    "agent.session.environment.failed",
                }:
                    raise RuntimeError(f"Session failed: {event.type}")
    raise RuntimeError("Stream ended without a completed turn")


def microvm_http(microvms, vm_id):
    vm = microvms.get_microvm(microvmIdentifier=vm_id)
    token = microvms.create_microvm_auth_token(
        microvmIdentifier=vm_id, expirationInMinutes=5, allowedPorts=[{"port": 8080}]
    )
    endpoint = vm["endpoint"]
    if not endpoint.startswith("https://"):
        endpoint = f"https://{endpoint}"
    return endpoint, {
        "X-aws-proxy-auth": token["authToken"]["X-aws-proxy-auth"],
        "X-aws-proxy-port": "8080",
    }


async def upload_file(microvms, vm_id, source, workspace_path):
    endpoint, headers = microvm_http(microvms, vm_id)
    async with httpx.AsyncClient(timeout=60) as http:
        result = await http.put(
            f"{endpoint}/upload/{quote(workspace_path, safe='/')}",
            headers={**headers, "Content-Type": "application/octet-stream"},
            content=source.read_bytes(),
        )
        result.raise_for_status()
    print(f"Uploaded: {source} → /workspace/{workspace_path}", flush=True)


async def download_file(microvms, vm_id, workspace_path, output):
    endpoint, headers = microvm_http(microvms, vm_id)
    async with httpx.AsyncClient(timeout=30) as http:
        result = await http.get(
            f"{endpoint}/download/{quote(workspace_path, safe='/')}",
            headers=headers,
        )
        result.raise_for_status()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(result.content)
    print(f"Downloaded: {output}", flush=True)


def verify_output(output, expected):
    if output.read_text(encoding="utf-8") != expected:
        raise RuntimeError("The sandbox output did not match the expected text")
    print(f"Verified: {output}", flush=True)


def wait_for_microvm(microvms, vm_id, state):
    # Lambda MicroVMs does not yet provide a Boto3 waiter.
    for _ in range(30):
        current = microvms.get_microvm(microvmIdentifier=vm_id)["state"]
        if current == state:
            print(f"MicroVM {state}: {vm_id}", flush=True)
            return
        if current == "TERMINATED":
            raise RuntimeError(f"MicroVM terminated before reaching {state}: {vm_id}")
        time.sleep(2)
    raise TimeoutError(f"MicroVM did not reach {state}: {vm_id}")


async def suspend_environment(client, microvms, session_id, vm_id):
    async with asyncio.timeout(90):
        async with await client.beta.agents.sessions.events.stream(session_id) as events:
            microvms.suspend_microvm(microvmIdentifier=vm_id)
            async for event in events:
                if event.type == "agent.session.environment.disconnected":
                    break
            else:
                raise RuntimeError("Stream ended before the executor disconnected")
        await asyncio.to_thread(wait_for_microvm, microvms, vm_id, "SUSPENDED")


def resume_microvm(microvms, vm_id):
    microvms.resume_microvm(microvmIdentifier=vm_id)
    wait_for_microvm(microvms, vm_id, "RUNNING")


def terminate_microvm(microvms, vm_id):
    microvms.terminate_microvm(microvmIdentifier=vm_id)
    wait_for_microvm(microvms, vm_id, "TERMINATED")


async def delete_session(client, session_id):
    for attempt in range(10):
        try:
            await client.beta.agents.sessions.delete(session_id)
            break
        except APIStatusError as error:
            if error.status_code != 409 or attempt == 9:
                raise
            await client.beta.agents.sessions.cancel(session_id)
            await asyncio.sleep(2)
    try:
        await client.beta.agents.sessions.retrieve(session_id)
    except NotFoundError:
        print(f"Session deleted (404): {session_id}", flush=True)
        return
    raise RuntimeError(f"Session deletion not confirmed: {session_id}")
