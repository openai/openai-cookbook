# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "openai>=3.13.0",
#     "modal[api-proxy-support]>=1.3.4,<2",
# ]
# ///

from __future__ import annotations

"""Self-hosted Agents API example using a Modal Sandbox."""

import asyncio
import os
import shlex
import sys
import time
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING

from openai import AsyncOpenAI
from openai.types.beta import AgentSession, AgentSessionEvent

if TYPE_CHECKING:
    import modal

WORKSPACE = "/workspace"
REPORT_PATH = f"{WORKSPACE}/sample_report.txt"
DEFAULT_MODAL_APP_NAME = "agents-api-self-hosted-example"
MODAL_SANDBOX_TIMEOUT_SECONDS = 15 * 60
EXAMPLE_DIR = Path(__file__).resolve().parent
EXECUTOR_HEALTHCHECK_INTERVAL_SECONDS = 5.0
STREAM_NO_PROGRESS_TIMEOUT_SECONDS = 60.0
STREAM_EXECUTION_TIMEOUT_SECONDS = 300.0
OVERALL_EXECUTION_TIMEOUT_SECONDS = 360.0
SESSION_CREATE_TIMEOUT_SECONDS = 30.0
SESSION_DELETE_TIMEOUT_SECONDS = 15.0
SANDBOX_CLEANUP_TIMEOUT_SECONDS = 15.0
CLEANUP_RESERVED_SECONDS = 30.0
SANDBOX_STARTUP_TIMEOUT_SECONDS = 120.0


async def main() -> int:
    api_key = os.environ["OPENAI_API_KEY"]
    executor_api_key = os.environ.get("OPENAI_EXECUTOR_API_KEY", api_key)
    sandbox: modal.Sandbox | None = None
    session: AgentSession | None = None
    overall_deadline = time.monotonic() + OVERALL_EXECUTION_TIMEOUT_SECONDS
    cleanup_reserve = min(
        CLEANUP_RESERVED_SECONDS, OVERALL_EXECUTION_TIMEOUT_SECONDS / 4
    )
    execution_deadline = overall_deadline - cleanup_reserve

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
                                SANDBOX_STARTUP_TIMEOUT_SECONDS,
                                _remaining(execution_deadline),
                            )
                        ):
                            sandbox = await start_modal_sandbox(
                                executor_api_key, environment_id, environment.remote_url
                            )
                    except TimeoutError as error:
                        raise RuntimeError(
                            "Modal sandbox startup exceeded "
                            f"{SANDBOX_STARTUP_TIMEOUT_SECONDS:g}-second timeout"
                        ) from error
                    prompt = (
                        f"Create a short report from {REPORT_PATH}. Summarize the main ideas, "
                        "mention caveats, and include the sandbox path you inspected."
                    )

                    print("\nagent output:\n")
                    await stream_agent_output(client, session, sandbox, prompt)

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
            if sandbox is not None:
                try:
                    async with asyncio.timeout(
                        min(
                            SANDBOX_CLEANUP_TIMEOUT_SECONDS,
                            _remaining(overall_deadline),
                        )
                    ):
                        await stop_modal_sandbox(sandbox)
                except TimeoutError as error:
                    failure = RuntimeError(
                        "Modal sandbox cleanup exceeded "
                        f"{SANDBOX_CLEANUP_TIMEOUT_SECONDS:g}-second timeout"
                    )
                    for detail in getattr(error, "__notes__", ()):
                        failure.add_note(detail)
                    cleanup_errors.append(failure.with_traceback(error.__traceback__))
                except Exception as error:
                    cleanup_errors.append(error)

            if session is not None:
                try:
                    async with asyncio.timeout(
                        min(
                            SESSION_DELETE_TIMEOUT_SECONDS, _remaining(overall_deadline)
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
                        original_error.add_note(f"Cleanup also failed: {cleanup_error}")
                        for detail in getattr(cleanup_error, "__notes__", ()):
                            original_error.add_note(f"Cleanup detail: {detail}")
                elif len(cleanup_errors) == 1:
                    raise cleanup_errors[0]
                else:
                    raise BaseExceptionGroup(
                        "self-hosted cleanup failed", cleanup_errors
                    )


def _remaining(deadline: float) -> float:
    return max(deadline - time.monotonic(), 0.001)


async def start_modal_sandbox(
    api_key: str, environment_id: str, remote_url: str
) -> modal.Sandbox:
    try:
        import modal
    except ImportError as exc:
        raise RuntimeError(
            "The Modal example dependency is not installed. "
            "Run: uv run examples/agents_api/sandboxes/application_managed/modal/main.py"
        ) from exc

    app = await modal.App.lookup.aio(DEFAULT_MODAL_APP_NAME, create_if_missing=True)
    image = (
        modal.Image.debian_slim(python_version="3.14")
        .apt_install(
            "ca-certificates",
            "curl",
            "file",
            "git",
            "nodejs",
            "npm",
            "poppler-utils",
            "ripgrep",
        )
        .run_commands(
            "mkdir -p /workspace /codex-home",
            "npm install --global @openai/codex@alpha",
        )
        .env({"CODEX_HOME": "/codex-home"})
        .workdir(WORKSPACE)
        .add_local_file(EXAMPLE_DIR / "sample_report.txt", REPORT_PATH, copy=True)
    )
    command = exec_server_command(environment_id, remote_url)

    print("starting exec server in Modal:")
    print(f"  {shlex.join(command)}")

    with modal.enable_output():
        sandbox = await modal.Sandbox.create.aio(
            *command,
            app=app,
            image=image,
            # The environment ID selects the target; exec-server separately
            # authenticates its registration request with CODEX_API_KEY.
            secrets=[modal.Secret.from_dict({"CODEX_API_KEY": api_key})],
            timeout=MODAL_SANDBOX_TIMEOUT_SECONDS,
            workdir=WORKSPACE,
        )
    print(f"started Modal sandbox {sandbox.object_id}")
    return sandbox


def exec_server_command(environment_id: str, remote_url: str) -> list[str]:
    return [
        "codex",
        "exec-server",
        "--remote",
        remote_url,
        "--environment-id",
        environment_id,
    ]


async def stream_agent_output(
    client: AsyncOpenAI,
    session: AgentSession,
    sandbox: modal.Sandbox,
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
                        await ensure_modal_sandbox_running(sandbox)
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
                    await ensure_modal_sandbox_running(sandbox)
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


async def ensure_modal_sandbox_running(sandbox: modal.Sandbox) -> None:
    exit_code = await sandbox.poll.aio()
    if exit_code is None:
        return

    stdout, stderr = await asyncio.gather(
        sandbox.stdout.read.aio(),
        sandbox.stderr.read.aio(),
    )
    logs = "\n".join(part.strip() for part in (stdout, stderr) if part.strip())
    if not logs:
        logs = "(no sandbox logs)"
    raise RuntimeError(
        f"Modal sandbox {sandbox.object_id} exited with code {exit_code}:\n{logs}"
    )


async def stop_modal_sandbox(sandbox: modal.Sandbox) -> None:
    termination_error: BaseException | None = None
    try:
        async with asyncio.timeout(SANDBOX_CLEANUP_TIMEOUT_SECONDS / 2):
            await sandbox.terminate.aio(wait=True)
    except BaseException as error:
        termination_error = error
    finally:
        try:
            async with asyncio.timeout(SANDBOX_CLEANUP_TIMEOUT_SECONDS / 2):
                await sandbox.detach.aio()
        except BaseException as detach_error:
            if termination_error is None:
                raise
            detail = str(detach_error) or type(detach_error).__name__
            termination_error.add_note(f"Modal sandbox detach also failed: {detail}")

    if termination_error is not None:
        raise termination_error


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
