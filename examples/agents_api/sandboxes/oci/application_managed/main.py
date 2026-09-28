# /// script
# requires-python = ">=3.11"
# dependencies = ["openai>=3.13.0"]
# ///

"""Run an Agents API task in an application-managed OCI GenAI Sandbox."""

from __future__ import annotations

import asyncio
import io
import os
import shlex
import time
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

WORKSPACE = "/workspace"
CODEX = f"{WORKSPACE}/.local/bin/codex"
DEFAULT_PROFILE = "Sandbox"
DEFAULT_REGION = "us-chicago-1"
SANDBOX_STARTUP_TIMEOUT_SECONDS = 120
SANDBOX_STOP_TIMEOUT_SECONDS = 60


def build_sandbox_client() -> Any:
    """Build the OCI client with the security-token profile from OCI config."""
    try:
        import oci
        from oci.generative_ai_sandbox import GenerativeAiSandboxClient
    except (ImportError, AttributeError) as error:
        raise RuntimeError(
            "The OCI GenAI Sandboxes preview SDK is not installed. "
            "Follow this example's README to install it from Oracle's beta SDK package."
        ) from error

    profile = os.environ.get("OCI_SANDBOX_PROFILE", DEFAULT_PROFILE)
    region = os.environ.get("OCI_SANDBOX_REGION", DEFAULT_REGION)
    endpoint = os.environ.get(
        "OCI_SANDBOX_ENDPOINT",
        f"https://inference.generativeai.{region}.oci.oraclecloud.com",
    )
    config = oci.config.from_file(profile_name=profile)

    try:
        private_key = oci.signer.load_private_key_from_file(config["key_file"])
        token_path = Path(config["security_token_file"]).expanduser()
    except KeyError as error:
        raise RuntimeError(
            f"OCI profile {profile!r} has no security token. Run: "
            f"oci session authenticate --profile-name {profile} --region {region}"
        ) from error

    signer = oci.auth.signers.SecurityTokenSigner(
        token_path.read_text(encoding="utf-8"), private_key
    )
    client = GenerativeAiSandboxClient(
        config=config,
        service_endpoint=endpoint,
        signer=signer,
        timeout=(10, 60),
    )
    return client


def wait_for_sandbox_state(
    client: Any,
    sandbox_id: str,
    target_state: str,
    timeout_seconds: float,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_state = "unknown"
    while time.monotonic() < deadline:
        last_state = str(client.get_sandbox(sandbox_id).data.lifecycle_state).upper()
        if last_state == target_state:
            return
        time.sleep(1)
    raise TimeoutError(
        f"OCI sandbox {sandbox_id} did not reach {target_state}; last state was {last_state}"
    )


def create_sandbox(client: Any, project_id: str) -> str:
    from oci.generative_ai_sandbox.models import CreateSandboxDetails

    response = client.create_sandbox(
        project_id,
        CreateSandboxDetails(
            display_name=f"agents-api-{int(time.time())}",
            runtime=os.environ.get("OCI_SANDBOX_RUNTIME", "python-3.11"),
            shape=os.environ.get("OCI_SANDBOX_SHAPE", "SMALL"),
            expiration_duration=os.environ.get("OCI_SANDBOX_EXPIRATION", "PT30M"),
        ),
    )
    return str(response.data.id)


def install_executor(client: Any, sandbox_id: str) -> None:
    from oci.generative_ai_sandbox.models import RunSandboxCommandDetails

    command = (
        "command -v npm >/dev/null || "
        "{ echo 'This OCI sandbox runtime needs Node.js and npm.' >&2; exit 127; }; "
        f"mkdir -p {WORKSPACE}/.local && "
        f"npm install --global --prefix {WORKSPACE}/.local @openai/codex@alpha"
    )
    output = client.run_sandbox_command_and_wait(
        sandbox_id,
        RunSandboxCommandDetails(command=command, timeout="PT10M"),
    ).data.output
    if output.exit_code != 0:
        detail = output.stderr or output.stdout or "no command output"
        raise RuntimeError(f"Codex installation failed: {detail}")


def write_brief(client: Any, sandbox_id: str) -> None:
    content = (
        b"Migrate a synchronous Python service to async without changing its API.\n"
    )
    client.write_sandbox_file(
        sandbox_id,
        f"{WORKSPACE}/brief.txt",
        io.BytesIO(content),
    )


def start_executor(
    client: Any,
    sandbox_id: str,
    environment_id: str,
    executor_key: str,
    remote_url: str,
) -> str:
    from oci.generative_ai_sandbox.models import (
        EnvironmentVariable,
        RunSandboxCommandDetails,
    )

    inner_command = "cd /workspace && exec " + shlex.join(
        [
            CODEX,
            "exec-server",
            "--remote",
            remote_url,
            "--environment-id",
            environment_id,
        ]
    )
    response = client.run_sandbox_command(
        sandbox_id,
        RunSandboxCommandDetails(
            command=f"sh -lc {shlex.quote(inner_command)}",
            environment_variables=[
                EnvironmentVariable(name="CODEX_API_KEY", value=executor_key),
            ],
            timeout="PT30M",
        ),
    )
    return str(response.data.id)


def read_text_file(client: Any, sandbox_id: str, path: str) -> str:
    content = client.read_sandbox_file(sandbox_id, path).data.content
    if isinstance(content, bytes):
        return content.decode("utf-8")
    return str(content)


def stop_and_delete_sandbox(client: Any, sandbox_id: str) -> None:
    from oci.generative_ai_sandbox.models import StopSandboxDetails

    try:
        state = str(client.get_sandbox(sandbox_id).data.lifecycle_state).upper()
        if state not in {"STOPPED", "STOPPING"}:
            client.stop_sandbox(sandbox_id, StopSandboxDetails(is_force=False))
        if state != "STOPPED":
            wait_for_sandbox_state(
                client,
                sandbox_id,
                "STOPPED",
                SANDBOX_STOP_TIMEOUT_SECONDS,
            )
        client.delete_sandbox(sandbox_id)
    except Exception as error:
        if getattr(error, "status", None) != 404:
            raise


async def main() -> None:
    project_id = os.environ["OCI_SANDBOX_PROJECT_ID"]
    application_key = os.environ["OPENAI_API_KEY"]
    executor_key = os.environ["OPENAI_EXECUTOR_API_KEY"]
    sandbox_client = build_sandbox_client()

    async with AsyncOpenAI(api_key=application_key, timeout=360) as client:
        session = await client.beta.agents.sessions.create(
            agent={"model": "gpt-5.6-sol"},
            environment={"type": "self_hosted", "workspace_directory": WORKSPACE},
        )
        sandbox_id: str | None = None
        print(f"Session: {session.id}", flush=True)
        try:
            environment = session.environment
            if environment.type != "self_hosted":
                raise RuntimeError(
                    f"Expected a self-hosted environment, got {environment.type}"
                )

            sandbox_id = await asyncio.to_thread(
                create_sandbox, sandbox_client, project_id
            )
            print(f"OCI sandbox: {sandbox_id}", flush=True)
            await asyncio.to_thread(
                wait_for_sandbox_state,
                sandbox_client,
                sandbox_id,
                "RUNNING",
                SANDBOX_STARTUP_TIMEOUT_SECONDS,
            )
            await asyncio.to_thread(install_executor, sandbox_client, sandbox_id)
            await asyncio.to_thread(write_brief, sandbox_client, sandbox_id)
            command_id = await asyncio.to_thread(
                start_executor,
                sandbox_client,
                sandbox_id,
                environment.id,
                executor_key,
                environment.remote_url,
            )
            print(f"Executor command: {command_id}", flush=True)

            async with (
                asyncio.timeout(360),
                client.beta.agents.sessions.stream(
                    session.id,
                    input="Read brief.txt and write a five-step migration plan to plan.md.",
                ) as events,
            ):
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

            plan = await asyncio.to_thread(
                read_text_file, sandbox_client, sandbox_id, f"{WORKSPACE}/plan.md"
            )
            if not plan.strip():
                raise RuntimeError("The agent did not write a migration plan")
            print(f"\n\nplan.md:\n{plan}")
        finally:
            try:
                if sandbox_id is not None:
                    await asyncio.to_thread(
                        stop_and_delete_sandbox, sandbox_client, sandbox_id
                    )
            finally:
                await client.beta.agents.sessions.delete(session.id)


if __name__ == "__main__":
    asyncio.run(main())
