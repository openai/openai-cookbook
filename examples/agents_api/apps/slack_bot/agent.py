"""Run and reuse one Agents API sandbox per Slack thread."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Awaitable, Callable

import docker
from docker.models.containers import Container
from openai import AsyncOpenAI
from openai.types.beta import AgentSessionEvent
from openai.types.beta.agents.session_create_params import Agent
from slack_sdk.web.async_client import AsyncWebClient

from .connections import Connections
from .tools import slack_handlers

INSTRUCTIONS = """\
You are a capable Slack teammate.
Search the current Slack conversation and connected Notion, Google Drive, and GitHub sources.
Cite the records behind your answer.
Use your workspace to analyze data, inspect repositories, and prepare changes.
Only modify external systems or create pull requests when the user explicitly asks.
Never reveal private information in a shared channel.
Delegate complex investigations when helpful.
"""
ProgressCallback = Callable[[str], Awaitable[None]]


def start_executor(environment_id: str, remote_url: str) -> Container:
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
        environment={"CODEX_API_KEY": os.environ["OPENAI_API_KEY"]},
        detach=True,
        auto_remove=True,
        init=True,
    )


class SlackBot:
    """Keep one self-hosted Agents API session and sandbox per Slack thread."""

    def __init__(self, client: AsyncOpenAI, slack: AsyncWebClient) -> None:
        self.client = client
        self.slack = slack
        self.sessions: dict[str, str] = {}
        self.sandboxes: dict[str, Container] = {}
        self.connections = Connections(client)
        self.model = os.environ.get("OPENAI_MODEL", "gpt-5.6-sol")
        self.active: set[str] = set()
        self.seen_messages: set[str] = set()
        self.thread_locks: dict[str, asyncio.Lock] = {}

    async def answer(
        self,
        question: str,
        *,
        thread_id: str,
        team_id: str,
        channel_id: str,
        on_progress: ProgressCallback | None = None,
    ) -> str:
        async with self.thread_locks.setdefault(thread_id, asyncio.Lock()):
            return await self._answer(
                question, thread_id, team_id, channel_id, on_progress
            )

    async def _answer(
        self,
        question: str,
        thread_id: str,
        team_id: str,
        channel_id: str,
        on_progress: ProgressCallback | None,
    ) -> str:
        if thread_id in self.sessions:
            session = await self.client.beta.agents.sessions.retrieve(
                self.sessions[thread_id]
            )
        else:
            vault_id, tools = await self.connections.get(team_id)
            agent: Agent = {
                "model": self.model,
                "instructions": INSTRUCTIONS,
                "reasoning": {"effort": "medium"},
                "multi_agent": {"enabled": True, "max_concurrent_subagents": 3},
                "tools": tools,
            }
            session = await self.client.beta.agents.sessions.create(
                agent=agent,
                environment={
                    "type": "self_hosted",
                    "workspace_directory": "/workspace",
                },
                vault_ids=[vault_id] if vault_id is not None else None,
            )

            try:
                environment = session.environment
                if environment.type != "self_hosted":
                    raise RuntimeError("Expected a self-hosted execution environment.")
                sandbox = await asyncio.to_thread(
                    start_executor, environment.id, environment.remote_url
                )
            except BaseException:
                await self.client.beta.agents.sessions.delete(session.id)
                raise

            self.sessions[thread_id] = session.id
            self.sandboxes[thread_id] = sandbox

        async with self.client.beta.agents.sessions.stream(
            session.id,
            input=question,
            tool_handlers=slack_handlers(self.slack, channel_id),
        ) as events:
            return await self._collect_reply(events, thread_id, on_progress)

    async def _collect_reply(
        self,
        events: AsyncIterator[AgentSessionEvent],
        thread_id: str,
        on_progress: ProgressCallback | None,
    ) -> str:
        parts: list[str] = []
        last_progress = ""
        self.active.add(thread_id)

        try:
            async for event in events:
                if (
                    event.type == "agent.session.turn.item.added"
                    and event.item is not None
                ):
                    item = event.item.to_dict()
                    label = str(item.get("server_label") or item.get("name", ""))
                    progress = {
                        "search_slack_messages": "Searching Slack conversations...",
                        "read_slack_channel": "Reading the Slack channel...",
                        "find_teammate": "Looking up a teammate...",
                        "list_slack_files": "Checking shared files...",
                        "notion": "Checking Notion...",
                        "google_drive": "Searching Google Drive...",
                        "github": "Checking GitHub...",
                    }.get(label, "Working on your request...")
                    if on_progress is not None and progress != last_progress:
                        await on_progress(progress)
                        last_progress = progress
                elif (
                    event.type == "agent.session.subagent.created"
                    and on_progress is not None
                ):
                    await on_progress("A specialist is investigating...")

                if event.type == "agent.session.turn.output_text.delta":
                    parts.append(event.delta)
                elif event.type == "agent.session.turn.output_text.done" and not parts:
                    parts.append(event.text)
                elif event.type in {
                    "agent.session.failed",
                    "agent.session.turn.failed",
                    "error",
                }:
                    raise RuntimeError(f"Agent session failed: {event.to_dict()}")
                elif event.type == "agent.session.turn.cancelled":
                    return "Request cancelled."
        finally:
            self.active.discard(thread_id)

        return "".join(parts)

    async def steer(self, thread_id: str, instructions: str) -> None:
        await self.client.beta.agents.sessions.events.create(
            self.sessions[thread_id],
            events=[
                {
                    "type": "agent.session.input.message",
                    "input": [
                        {
                            "role": "user",
                            "content": [{"type": "input_text", "text": instructions}],
                        }
                    ],
                }
            ],
        )

    async def cancel(self, thread_id: str) -> None:
        await self.client.beta.agents.sessions.events.create(
            self.sessions[thread_id], events=[{"type": "agent.session.input.cancel"}]
        )

    async def close(self) -> None:
        errors: list[Exception] = []
        for thread_id, session_id in self.sessions.items():
            try:
                await self.client.beta.agents.sessions.delete(session_id)
            except Exception as error:
                errors.append(error)
            sandbox = self.sandboxes.get(thread_id)
            if sandbox is not None:
                try:
                    await asyncio.to_thread(sandbox.stop)
                except Exception as error:
                    errors.append(error)
        if errors:
            raise ExceptionGroup("Could not close all Slack runtimes", errors)
