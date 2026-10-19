"""Investigate a GitHub issue in an isolated Agents API sandbox."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any

import docker
from docker.models.containers import Container
from openai import AsyncOpenAI, NotFoundError

INSTRUCTIONS = """\
Investigate GitHub issues by inspecting the repository and reproducing problems when practical.
Identify the likely cause and recommend the smallest fix.
Write your findings to /workspace/investigation.md.
Do not edit source files or contact external services.
"""


def start_executor(workspace: Path, environment_id: str, remote_url: str) -> Container:
    return docker.from_env().containers.run(
        os.environ.get("AGENTS_SANDBOX_IMAGE", "agent-api-sandbox:latest"),
        [
            "codex",
            "exec-server",
            "--remote",
            remote_url,
            "--environment-id",
            environment_id,
        ],
        environment={"CODEX_API_KEY": os.environ["OPENAI_EXECUTOR_API_KEY"]},
        volumes={str(workspace.resolve()): {"bind": "/workspace", "mode": "rw"}},
        detach=True,
        auto_remove=True,
    )


async def investigate_issue(issue: dict[str, Any], workspace: Path) -> dict[str, Any]:
    container: Container | None = None
    async with AsyncOpenAI() as client:
        session = await client.beta.agents.sessions.create(
            agent={
                "model": os.environ.get("OPENAI_MODEL", "gpt-5.6-sol"),
                "instructions": INSTRUCTIONS,
                "reasoning": {"effort": "high"},
            },
            environment={"type": "self_hosted", "workspace_directory": "/workspace"},
        )

        try:
            environment = session.environment
            if environment.type != "self_hosted":
                raise RuntimeError("Expected a self-hosted execution environment.")
            container = await asyncio.to_thread(
                start_executor, workspace, environment.id, environment.remote_url
            )
            prompt = f"""\
Investigate GitHub issue #{issue.get("number", "?")}: {issue["title"]}

{issue.get("body", "")}

Inspect /workspace, run relevant tests, identify the root cause, and write
/workspace/investigation.md with your findings and a proposed fix.
"""
            parts: list[str] = []
            async with client.beta.agents.sessions.stream(
                session.id, input=prompt
            ) as events:
                async for event in events:
                    if event.type == "agent.session.turn.output_text.delta":
                        parts.append(event.delta)
                    elif (
                        event.type == "agent.session.turn.output_text.done"
                        and not parts
                    ):
                        parts.append(event.text)
                    if event.type in {
                        "agent.session.failed",
                        "agent.session.turn.failed",
                        "error",
                    }:
                        raise RuntimeError(
                            f"Issue investigation failed: {event.to_dict()}"
                        )
                    if event.type == "agent.session.turn.cancelled":
                        raise RuntimeError("Issue investigation was cancelled.")

            report = workspace / "investigation.md"
            if not report.exists():
                raise RuntimeError(
                    "The agent did not create /workspace/investigation.md."
                )
            return {
                "issue_number": issue.get("number"),
                "session_id": session.id,
                "summary": "".join(parts),
                "findings": report.read_text(),
            }
        finally:
            original_error = sys.exception()
            cleanup_errors: list[Exception] = []
            try:
                if container is not None:
                    await asyncio.to_thread(container.remove, force=True)
            except docker.errors.NotFound:
                pass
            except Exception as error:
                cleanup_errors.append(error)
            try:
                await client.beta.agents.sessions.delete(session.id)
            except NotFoundError:
                pass
            except Exception as error:
                cleanup_errors.append(error)
            if original_error is not None:
                for error in cleanup_errors:
                    original_error.add_note(
                        f"Cleanup for session {session.id}: {error}"
                    )
            elif cleanup_errors:
                raise ExceptionGroup(
                    f"Could not clean up session {session.id} and its sandbox",
                    cleanup_errors,
                )
