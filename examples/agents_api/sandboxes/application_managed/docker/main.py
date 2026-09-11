# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "openai>=3.13.0",
# ]
# ///

from __future__ import annotations

"""Self-hosted Agents API example using a local Docker container."""

import asyncio
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import uuid
from contextlib import suppress
from contextvars import ContextVar
from pathlib import Path

from openai import AsyncOpenAI
from openai.types.beta import AgentSession, AgentSessionEvent

WORKSPACE = "/workspace"
REPORT_PATH = f"{WORKSPACE}/sample_report.txt"
DEFAULT_DOCKER_IMAGE = "agent-api-sandbox:latest"
EXAMPLE_DIR = Path(__file__).resolve().parent
EXECUTOR_HEALTHCHECK_INTERVAL_SECONDS = 5.0
STREAM_NO_PROGRESS_TIMEOUT_SECONDS = 60.0
STREAM_EXECUTION_TIMEOUT_SECONDS = 300.0
OVERALL_EXECUTION_TIMEOUT_SECONDS = 360.0
SESSION_CREATE_TIMEOUT_SECONDS = 30.0
SESSION_DELETE_TIMEOUT_SECONDS = 15.0
CLEANUP_RESERVED_SECONDS = 25.0
DOCKER_IMAGE_BUILD_TIMEOUT_SECONDS = 240.0
DOCKER_EXECUTOR_START_TIMEOUT_SECONDS = 30.0
DOCKER_PROVISION_TIMEOUT_SECONDS = (
    DOCKER_IMAGE_BUILD_TIMEOUT_SECONDS + DOCKER_EXECUTOR_START_TIMEOUT_SECONDS
)
DOCKER_HEALTHCHECK_TIMEOUT_SECONDS = 5.0
DOCKER_CLEANUP_TIMEOUT_SECONDS = 10.0
_EXECUTION_DEADLINE: ContextVar[float | None] = ContextVar(
    "docker_example_execution_deadline", default=None
)


class _DockerProvisioning:
    def __init__(self, container_name: str) -> None:
        self.container_name = container_name
        self.container_started = False
        self.aborted = False


_DOCKER_PROVISIONING: ContextVar[_DockerProvisioning | None] = ContextVar(
    "docker_example_provisioning", default=None
)


async def main() -> int:
    api_key = os.environ["OPENAI_API_KEY"]
    executor_api_key = os.environ["OPENAI_EXECUTOR_API_KEY"]
    container_name: str | None = None
    provisioner: asyncio.Task[str] | None = None
    session: AgentSession | None = None
    started_at = time.monotonic()
    overall_deadline = started_at + OVERALL_EXECUTION_TIMEOUT_SECONDS
    cleanup_reserve = min(
        CLEANUP_RESERVED_SECONDS, OVERALL_EXECUTION_TIMEOUT_SECONDS / 4
    )
    execution_deadline = overall_deadline - cleanup_reserve
    deadline_token = _EXECUTION_DEADLINE.set(execution_deadline)
    provisioning = _DockerProvisioning(f"agent-api-{uuid.uuid4().hex[:12]}")
    provisioning_token = _DOCKER_PROVISIONING.set(provisioning)

    try:
        async with AsyncOpenAI(api_key=api_key) as client:
            try:
                try:
                    async with asyncio.timeout_at(execution_deadline):
                        try:
                            async with asyncio.timeout(
                                min(
                                    SESSION_CREATE_TIMEOUT_SECONDS,
                                    _remaining(execution_deadline),
                                )
                            ):
                                session = await client.beta.agents.sessions.create(
                                    agent={
                                        "model": "gpt-5.6-sol",
                                        "instructions": (
                                            "Create the requested report using files available in "
                                            "/workspace. Inspect the source file directly, then "
                                            "cite concrete details and caveats."
                                        ),
                                    },
                                    environment={
                                        "type": "self_hosted",
                                        "workspace_directory": WORKSPACE,
                                    },
                                )
                        except TimeoutError as error:
                            provisioning.aborted = True
                            raise RuntimeError(
                                "agent session creation exceeded "
                                f"{SESSION_CREATE_TIMEOUT_SECONDS:g}-second timeout"
                            ) from error

                        environment = session.environment
                        if environment.type != "self_hosted":
                            raise RuntimeError(
                                f"expected self-hosted environment, got {environment.type}"
                            )
                        environment_id = environment.id
                        print(f"created session {session.id}")
                        print(f"environment id: {environment_id}")

                        try:
                            async with asyncio.timeout(
                                min(
                                    DOCKER_PROVISION_TIMEOUT_SECONDS,
                                    _remaining(execution_deadline),
                                )
                            ):
                                provisioner = asyncio.create_task(
                                    asyncio.to_thread(
                                        start_docker_sandbox,
                                        executor_api_key,
                                        environment_id,
                                        environment.remote_url,
                                    )
                                )
                                container_name = await asyncio.shield(provisioner)
                        except TimeoutError as error:
                            provisioning.aborted = True
                            raise RuntimeError(
                                "Docker sandbox provisioning exceeded "
                                f"{DOCKER_PROVISION_TIMEOUT_SECONDS:g}-second timeout"
                            ) from error

                        prompt = (
                            f"Create a short report from {REPORT_PATH}. Summarize the main ideas, "
                            "mention caveats, and include the sandbox path you inspected."
                        )

                        print("\nagent output:\n")
                        await stream_agent_output(
                            client, session, container_name, prompt
                        )

                        final_session = await client.beta.agents.sessions.retrieve(
                            session.id
                        )
                        print(f"\nfinal status: {final_session.status}")
                        return 0 if final_session.status == "idle" else 2
                except TimeoutError as error:
                    raise RuntimeError(
                        "agent session exceeded "
                        f"{OVERALL_EXECUTION_TIMEOUT_SECONDS:g}-second overall execution timeout"
                    ) from error
            finally:
                original_error = sys.exc_info()[1]
                cleanup_errors: list[BaseException] = []
                if provisioner is not None and not provisioner.done():
                    provisioning.aborted = True
                    try:
                        async with asyncio.timeout(
                            min(
                                DOCKER_CLEANUP_TIMEOUT_SECONDS,
                                _remaining(overall_deadline),
                            )
                        ):
                            container_name = await provisioner
                    except TimeoutError as error:
                        cleanup_errors.append(
                            RuntimeError(
                                "Docker provisioning did not stop before cleanup."
                            ).with_traceback(error.__traceback__)
                        )
                    except Exception as error:
                        if original_error is None:
                            cleanup_errors.append(error)
                        else:
                            original_error.add_note(
                                f"Docker provisioning also failed: {error}"
                            )

                if container_name is None and provisioning.container_started:
                    container_name = provisioning.container_name
                if container_name is not None:
                    try:
                        async with asyncio.timeout(
                            min(
                                DOCKER_CLEANUP_TIMEOUT_SECONDS,
                                _remaining(overall_deadline),
                            )
                        ):
                            await asyncio.to_thread(remove_container, container_name)
                    except TimeoutError as error:
                        cleanup_errors.append(
                            RuntimeError(
                                "Docker container cleanup exceeded "
                                f"{DOCKER_CLEANUP_TIMEOUT_SECONDS:g}-second timeout"
                            ).with_traceback(error.__traceback__)
                        )
                    except Exception as error:
                        cleanup_errors.append(error)

                if session is not None:
                    try:
                        async with asyncio.timeout(
                            min(
                                SESSION_DELETE_TIMEOUT_SECONDS,
                                _remaining(overall_deadline),
                            )
                        ):
                            await client.beta.agents.sessions.delete(session.id)
                    except TimeoutError as error:
                        cleanup_errors.append(
                            RuntimeError(
                                "agent session deletion exceeded "
                                f"{SESSION_DELETE_TIMEOUT_SECONDS:g}-second timeout"
                            ).with_traceback(error.__traceback__)
                        )
                    except Exception as error:
                        cleanup_errors.append(error)

                if cleanup_errors:
                    if original_error is not None:
                        for cleanup_error in cleanup_errors:
                            original_error.add_note(
                                f"Cleanup also failed: {cleanup_error}"
                            )
                    elif len(cleanup_errors) == 1:
                        raise cleanup_errors[0]
                    else:
                        raise BaseExceptionGroup(
                            "self-hosted cleanup failed", cleanup_errors
                        )
    finally:
        _DOCKER_PROVISIONING.reset(provisioning_token)
        _EXECUTION_DEADLINE.reset(deadline_token)


def _remaining(deadline: float) -> float:
    return max(deadline - time.monotonic(), 0.001)


def start_docker_sandbox(api_key: str, environment_id: str, remote_url: str) -> str:
    if shutil.which("docker") is None:
        raise RuntimeError("Docker CLI is not installed or not on PATH")

    build_docker_image()

    provisioning = _DOCKER_PROVISIONING.get()
    if provisioning is not None and provisioning.aborted:
        raise RuntimeError(
            "Docker sandbox provisioning was cancelled before container startup"
        )
    container_name = (
        provisioning.container_name
        if provisioning is not None
        else f"agent-api-{uuid.uuid4().hex[:12]}"
    )
    command = [
        "docker",
        "run",
        "--detach",
        "--rm",
        "--name",
        container_name,
        "--init",
        "-e",
        "CODEX_API_KEY",
        DEFAULT_DOCKER_IMAGE,
        "codex",
        "exec-server",
        "--remote",
        remote_url,
        "--environment-id",
        environment_id,
    ]

    print("starting exec server:")
    print(f"  {shlex.join(command)}")

    env = os.environ.copy()
    env["CODEX_API_KEY"] = api_key
    if provisioning is not None and provisioning.aborted:
        raise RuntimeError(
            "Docker sandbox provisioning was cancelled before container startup"
        )
    if provisioning is not None:
        provisioning.container_started = True
    try:
        container_id = run_command(
            command, env=env, timeout=DOCKER_EXECUTOR_START_TIMEOUT_SECONDS
        )
        if provisioning is not None and provisioning.aborted:
            raise RuntimeError(
                "Docker sandbox provisioning was cancelled after container startup"
            )
    except Exception as error:
        try:
            remove_container(container_name)
        except Exception as cleanup_error:
            error.add_note(f"Partial Docker container cleanup failed: {cleanup_error}")
        raise
    print(f"started Docker container {container_id[:12]}")
    return container_name


def build_docker_image() -> None:
    command = [
        "docker",
        "build",
        "--tag",
        DEFAULT_DOCKER_IMAGE,
        str(EXAMPLE_DIR),
    ]

    print("building Docker image:")
    print(f"  {shlex.join(command)}")
    run_command(command, echo=True, timeout=DOCKER_IMAGE_BUILD_TIMEOUT_SECONDS)


async def stream_agent_output(
    client: AsyncOpenAI,
    session: AgentSession,
    container_name: str,
    prompt: str,
) -> None:
    saw_text_delta = False
    loop = asyncio.get_running_loop()
    async with client.beta.agents.sessions.stream(session.id, input=prompt) as events:
        next_event = asyncio.create_task(anext(events))
        try:
            async with asyncio.timeout(STREAM_EXECUTION_TIMEOUT_SECONDS):
                last_progress = loop.time()
                while True:
                    completed, _ = await asyncio.wait(
                        {next_event}, timeout=EXECUTOR_HEALTHCHECK_INTERVAL_SECONDS
                    )
                    if not completed:
                        await asyncio.to_thread(
                            ensure_container_running, container_name
                        )
                        if (
                            loop.time() - last_progress
                            >= STREAM_NO_PROGRESS_TIMEOUT_SECONDS
                        ):
                            raise RuntimeError(
                                "agent session made no progress for "
                                f"{STREAM_NO_PROGRESS_TIMEOUT_SECONDS:g} seconds"
                            )
                        continue
                    try:
                        event = next_event.result()
                    except StopAsyncIteration:
                        break
                    last_progress = loop.time()
                    await asyncio.to_thread(ensure_container_running, container_name)
                    if event.type == "agent.session.environment.connected":
                        print("environment connected")
                    if event.type == "agent.session.environment.failed":
                        raise RuntimeError(
                            f"environment failed: {event.environment.error}"
                        )
                    if event.type == "agent.session.turn.failed":
                        error = (
                            event.turn.error.message
                            if event.turn.error is not None
                            else "unknown error"
                        )
                        raise RuntimeError(f"session turn failed: {error}")
                    if event.type == "agent.session.turn.cancelled":
                        raise RuntimeError("session turn was cancelled")
                    saw_text_delta = print_event(event, saw_text_delta)
                    if event.type == "agent.session.failed":
                        raise RuntimeError(f"session failed: {event.to_dict()}")
                    if event.type == "error":
                        raise RuntimeError(event.error.message)
                    next_event = asyncio.create_task(anext(events))
        except TimeoutError as error:
            raise RuntimeError(
                "agent session exceeded "
                f"{STREAM_EXECUTION_TIMEOUT_SECONDS:g}-second execution timeout"
            ) from error
        finally:
            next_event.cancel()
            with suppress(asyncio.CancelledError, StopAsyncIteration):
                await next_event
    print()


def print_event(event: AgentSessionEvent, saw_text_delta: bool) -> bool:
    if event.type == "agent.session.turn.output_text.delta":
        print(event.delta, end="", flush=True)
        return True
    if event.type == "agent.session.turn.output_text.done" and not saw_text_delta:
        print(event.text)
    return saw_text_delta


def ensure_container_running(container_name: str) -> None:
    result = subprocess.run(
        ["docker", "inspect", "--format", "{{.State.Running}}", container_name],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        timeout=DOCKER_HEALTHCHECK_TIMEOUT_SECONDS,
    )
    if result.returncode == 0 and result.stdout.strip() == "true":
        return

    logs = subprocess.run(
        ["docker", "logs", "--tail", "80", container_name],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=DOCKER_HEALTHCHECK_TIMEOUT_SECONDS,
    ).stdout
    raise RuntimeError(f"Docker sandbox {container_name} is not running:\n{logs}")


def remove_container(container_name: str) -> None:
    try:
        result = subprocess.run(
            ["docker", "rm", "-f", container_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=DOCKER_CLEANUP_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(
            f"Docker sandbox {container_name} removal exceeded "
            f"{DOCKER_CLEANUP_TIMEOUT_SECONDS:g}-second timeout"
        ) from error

    if result.returncode == 0:
        return

    detail = (result.stderr or result.stdout or "").strip()
    if re.fullmatch(
        r"(?:error response from daemon:\s*|error:\s*)?"
        r"no such (?:container|object):\s*['\"]?"
        + re.escape(container_name)
        + r"['\"]?",
        detail,
        flags=re.IGNORECASE,
    ):
        return

    reason = detail or "Docker returned no diagnostic output."
    raise RuntimeError(
        f"Could not remove Docker sandbox {container_name} "
        f"(exit status {result.returncode}): {reason}"
    )


def run_command(
    command: list[str],
    env: dict[str, str] | None = None,
    echo: bool = False,
    timeout: float = DOCKER_EXECUTOR_START_TIMEOUT_SECONDS,
) -> str:
    deadline = _EXECUTION_DEADLINE.get()
    if deadline is not None:
        timeout = min(timeout, _remaining(deadline))
    try:
        result = subprocess.run(
            command,
            check=False,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(
            f"Command exceeded its {timeout:g}-second timeout: {shlex.join(command)}"
        ) from error
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {shlex.join(command)}\n{result.stdout}")
    if echo and result.stdout:
        print(result.stdout, end="")
    return result.stdout.strip()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
