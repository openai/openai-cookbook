"""Investigate incidents and coordinate approval, resolution, and cleanup."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import docker
from docker.models.containers import Container
from openai import AsyncOpenAI, NotFoundError
from openai.lib.streaming.agents import AsyncToolHandler
from openai.types.beta import AgentSessionEvent
from openai.types.beta.agents.session_create_params import Agent

from .memory import load_history, recall_incidents, save_history
from .slack import SLACK_CHANNEL, SlackChannel, approval_blocks
from .tools import PROGRESS, configured_tools, get_service, get_service_evidence

EXAMPLE_DIR = Path(__file__).resolve().parent
DOCKER_IMAGE = "agent-api-sev-sandbox:latest"
logger = logging.getLogger(__name__)
INSTRUCTIONS = """\
Investigate the incident using service evidence, GitHub, AWS, and past incidents.
Consult /workspace/runbooks/<service>.md and explain impact, likely cause, and next steps.
Use read-only tools; never install integrations or change infrastructure.
Clearly separate sample data from live findings.
If a rollout caused the incident, call propose_rollback once for the previous healthy version.
Approval records a decision, not an executed rollback.
"""


def start_executor(environment_id: str, remote_url: str) -> Container:
    return docker.from_env().containers.run(
        DOCKER_IMAGE,
        [
            "codex",
            "exec-server",
            "--remote",
            remote_url,
            "--environment-id",
            environment_id,
        ],
        environment={"CODEX_API_KEY": os.environ["OPENAI_EXECUTOR_API_KEY"]},
        volumes={
            str(EXAMPLE_DIR / "runbooks"): {"bind": "/workspace/runbooks", "mode": "ro"}
        },
        working_dir="/workspace",
        detach=True,
    )


@dataclass
class Incident:
    id: str
    fingerprint: str
    service: str
    severity: str
    title: str
    team: str
    channel: str = SLACK_CHANNEL
    status: str = "investigating"
    session_id: str | None = None
    sandbox: Container | None = field(default=None, repr=False)
    slack_thread_ts: str | None = None
    slack_approval_ts: str | None = None
    analysis: str = ""
    action: dict[str, Any] | None = None
    timeline: list[dict[str, Any]] = field(default_factory=list)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    approval_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    def record(self, message: str) -> None:
        self.timeline.append(
            {"time": datetime.now(UTC).strftime("%H:%M:%S UTC"), "message": message}
        )


class IncidentBot:
    """Keep one Agents API session and approval boundary for each incident."""

    def __init__(
        self,
        client: AsyncOpenAI,
        operations: dict[str, Any] | None = None,
        *,
        slack: SlackChannel | None = None,
        history: list[dict[str, Any]] | None = None,
        history_path: Path = EXAMPLE_DIR / "incident_memory.json",
    ) -> None:
        self.client = client
        self.model = os.environ.get("OPENAI_MODEL", "gpt-5.6-sol")
        self.operations = (
            operations
            if operations is not None
            else json.loads((EXAMPLE_DIR / "operations.json").read_text())
        )
        self.slack = slack if slack is not None else SlackChannel()
        self.history_path = history_path
        if history is not None:
            self.history = [*history]
        else:
            self.history = load_history(history_path)
        self.next_incident_number = (
            max(
                [1041]
                + [
                    int(str(record["id"]).removeprefix("INC-"))
                    for record in self.history
                ]
            )
            + 1
        )
        self.incidents: dict[str, Incident] = {}
        self.fingerprints: dict[str, str] = {}
        self.slack_threads: dict[str, str] = {}
        self.slack_deliveries: set[str] = set()
        self.closed_sessions: set[str] = set()

    def service(self, name: str) -> dict[str, Any]:
        return get_service(self.operations, name)

    def start_incident(self, alert: dict[str, Any]) -> Incident:
        labels = alert.get("labels", {})
        annotations = alert.get("annotations", {})
        service = str(labels.get("service", ""))
        fingerprint = str(
            alert.get("fingerprint") or f"{service}:{labels.get('alertname', '')}"
        )
        existing = self.fingerprints.get(fingerprint)
        if existing is not None:
            return self.incidents[existing]

        service_info = self.service(service)
        severity = "SEV-1" if labels.get("severity") == "critical" else "SEV-2"
        incident = Incident(
            id=f"INC-{self.next_incident_number}",
            fingerprint=fingerprint,
            service=service,
            severity=severity,
            title=str(
                annotations.get("summary", labels.get("alertname", "Service alert"))
            ),
            team=str(service_info["team"]),
        )
        self.next_incident_number += 1
        incident.record(f"Received {severity} alert for {service}.")
        self.incidents[incident.id] = incident
        self.fingerprints[fingerprint] = incident.id
        return incident

    def get_service_evidence(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return get_service_evidence(self.operations, arguments)

    def recall_incidents(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return recall_incidents(self.history, arguments)

    def propose_rollback(
        self, incident: Incident, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        service_name = str(arguments["service"])
        version = str(arguments["version"])
        if service_name != incident.service:
            raise ValueError("A rollback can only target the affected service.")

        deployments: list[dict[str, Any]] = self.service(service_name)["deployments"]
        healthy_versions = {
            str(deployment["version"])
            for deployment in deployments
            if deployment.get("status") == "previous_healthy"
        }
        if version not in healthy_versions:
            raise ValueError("A rollback must target a known healthy deployment.")

        if incident.action is None:
            incident.action = {
                "id": f"ACTION-{incident.id.removeprefix('INC-')}",
                "service": service_name,
                "version": version,
                "reason": str(arguments["reason"]),
                "status": "awaiting_approval",
            }
            incident.status = "awaiting_approval"
            incident.record(
                f"Requested approval to roll back {service_name} to {version}."
            )

        return incident.action

    async def publish(
        self,
        incident: Incident,
        text: str,
        *,
        blocks: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        message = await self.slack.post(
            text, thread_ts=incident.slack_thread_ts, blocks=blocks
        )
        if incident.slack_thread_ts is None:
            incident.slack_thread_ts = str(message["ts"])
            self.slack_threads[incident.slack_thread_ts] = incident.id
        return message

    async def investigate(self, incident: Incident, question: str | None = None) -> str:
        async with incident.lock:
            if incident.status in {"resolved", "resolving"}:
                return "This incident is closing or already resolved."
            try:
                return await self._investigate(incident, question)
            except Exception as error:
                incident.status = "failed"
                incident.record(f"Investigation failed: {error}")
                await self.close_runtime(incident)
                raise

    async def _investigate(self, incident: Incident, question: str | None) -> str:
        handlers: dict[str, AsyncToolHandler] = {
            "get_service_evidence": self.get_service_evidence,
            "recall_incidents": self.recall_incidents,
        }
        prompt = (
            question
            or f"""\
Investigate {incident.severity}: {incident.title}
Affected service: {incident.service}

Inspect service health, production logs, recent deployments, GitHub pull requests and commits,
AWS infrastructure, related past incidents, and /workspace/runbooks/{incident.service}.md.
Correlate timestamps, quantify customer impact, and cite the responsible code.
If a rollout caused the incident, propose a rollback to the previous healthy version.
"""
        )

        if incident.session_id is not None:
            session = await self.client.beta.agents.sessions.retrieve(
                incident.session_id
            )
            incident.record("Received a follow-up question.")
        else:
            await self.publish(
                incident,
                f"*{incident.severity} {incident.id}* {incident.title}\n"
                f"Investigating `{incident.service}`.",
            )
            incident.record(f"Opened an incident thread in {incident.channel}.")
            agent: Agent = {
                "model": self.model,
                "instructions": INSTRUCTIONS,
                "reasoning": {"effort": "high"},
                "multi_agent": {"enabled": True, "max_concurrent_subagents": 3},
                "tools": configured_tools(),
            }
            session = await self.client.beta.agents.sessions.create(
                agent=agent,
                environment={
                    "type": "self_hosted",
                    "workspace_directory": "/workspace",
                },
            )
            incident.session_id = session.id
            if incident.status == "resolving":
                return ""
            environment = session.environment
            if environment.type != "self_hosted":
                raise RuntimeError("Expected a self-hosted execution environment.")
            incident.sandbox = await asyncio.to_thread(
                start_executor, environment.id, environment.remote_url
            )
            incident.record("Started an incident sandbox with AWS skills.")
            logger.info(
                "%s: sandbox %s, session %s",
                incident.id,
                incident.sandbox.short_id,
                session.id,
            )

        # The webhook handles propose_rollback; do not auto-complete its tool call.
        if incident.status == "resolving":
            return ""
        async with self.client.beta.agents.sessions.stream(
            session.id, input=prompt, tool_handlers=handlers
        ) as events:
            answer = await self.collect(events, incident)
        if incident.status == "resolving":
            return answer
        if question is not None and incident.analysis:
            incident.analysis += f"\n\nFollow-up: {question}\n{answer}"
        else:
            incident.analysis = answer
        if incident.status in {"investigating", "failed"}:
            incident.status = "investigated"
        await self.publish(incident, f"*Incident update*\n{answer}")
        incident.record(f"Posted investigation results to {incident.channel}.")
        return answer

    async def collect(
        self, events: AsyncIterator[AgentSessionEvent], incident: Incident
    ) -> str:
        output: list[str] = []
        reported: set[str] = set()
        async for event in events:
            if incident.status == "resolving":
                return "".join(output)
            if event.type == "agent.session.environment.connected":
                incident.record("Connected the incident sandbox.")
            elif (
                event.type == "agent.session.turn.item.done" and event.item is not None
            ):
                if event.item.type == "command_execution":
                    logger.info(
                        "%s: sandbox command %s", incident.id, event.item.status
                    )
            elif (
                event.type == "agent.session.turn.item.added"
                and event.item.type == "function_call"
            ):
                tool_name = event.item.name
                if tool_name in PROGRESS and tool_name not in reported:
                    incident.record(PROGRESS[tool_name])
                    reported.add(tool_name)
            elif (
                event.type == "agent.session.subagent.created"
                and "specialist" not in reported
            ):
                incident.record("Delegated part of the investigation to a specialist.")
                reported.add("specialist")
            elif event.type == "agent.session.turn.output_text.delta":
                output.append(event.delta)
            elif event.type == "agent.session.turn.output_text.done" and not output:
                output.append(event.text)
            elif event.type in {
                "agent.session.failed",
                "agent.session.turn.failed",
                "error",
                "agent.session.environment.failed",
            }:
                raise RuntimeError(f"Incident investigation failed: {event.to_dict()}")
            elif event.type == "agent.session.turn.cancelled":
                if incident.status == "resolving":
                    return "".join(output)
                raise RuntimeError("Incident investigation was cancelled.")

        return "".join(output)

    async def request_approval(self, session_id: str) -> None:
        incident = next(
            (item for item in self.incidents.values() if item.session_id == session_id),
            None,
        )
        if incident is None:
            return
        # Independent of the stream's lock: the turn waits here for the Slack decision.
        async with incident.approval_lock:
            if incident.status in {"resolved", "resolving", "failed"}:
                return
            session = await self.client.beta.agents.sessions.retrieve(session_id)
            for action in session.required_actions:
                if action.type != "function_call" or action.name != "propose_rollback":
                    continue
                if (
                    incident.action is not None
                    and incident.action.get("call_id") == action.call_id
                    and incident.action.get("turn_id") == action.turn_id
                ):
                    if incident.slack_approval_ts is not None:
                        continue
                else:
                    try:
                        if incident.action is not None:
                            raise ValueError(
                                "A rollback has already been proposed for this incident."
                            )
                        arguments = action.arguments
                        if isinstance(arguments, str):
                            arguments = json.loads(arguments)
                        if not isinstance(arguments, dict):
                            raise ValueError("Rollback arguments must be an object.")
                        incident.action = self.propose_rollback(incident, arguments)
                    except (KeyError, ValueError):
                        await self.client.beta.agents.sessions.events.create(
                            session.id,
                            events=[
                                {
                                    "type": "agent.session.input.tool_result",
                                    "turn_id": action.turn_id,
                                    "call_id": action.call_id,
                                    "success": False,
                                    "error": "Invalid or duplicate rollback proposal.",
                                }
                            ],
                        )
                        continue
                    incident.action.update(
                        turn_id=action.turn_id, call_id=action.call_id
                    )
                approval = await self.publish(
                    incident,
                    f"Approval required: {incident.action['reason']}\n"
                    f"Roll back {incident.action['service']} to {incident.action['version']}?",
                    blocks=approval_blocks(incident),
                )
                incident.slack_approval_ts = str(approval["ts"])

    async def decide_rollback(self, incident_id: str, approved: bool) -> dict[str, Any]:
        incident = self.incident(incident_id)
        async with incident.approval_lock:
            if incident.status in {"resolved", "resolving", "failed"}:
                raise ValueError("This incident is no longer awaiting a decision.")
            action = incident.action
            if action is None or incident.session_id is None:
                raise ValueError("No rollback is awaiting approval.")
            decision = "approved" if approved else "rejected"
            if action["status"] == decision:
                return action
            if action["status"] != "awaiting_approval":
                raise ValueError("This rollback request is no longer pending.")
            session = await self.client.beta.agents.sessions.retrieve(
                incident.session_id
            )
            if not any(
                pending.type == "function_call"
                and pending.call_id == action["call_id"]
                and pending.turn_id == action["turn_id"]
                for pending in session.required_actions
            ):
                raise ValueError("This rollback request is no longer pending.")
            await self.client.beta.agents.sessions.events.create(
                session.id,
                events=[
                    {
                        "type": "agent.session.input.tool_result",
                        "turn_id": str(action["turn_id"]),
                        "call_id": str(action["call_id"]),
                        "success": True,
                        "output": json.dumps(
                            {
                                "decision": decision,
                                "executed": False,
                                "service": action["service"],
                                "version": action["version"],
                            }
                        ),
                    }
                ],
            )
            action["status"] = decision
            incident.status = decision if approved else "investigated"
            incident.record(f"Rollback {decision}; returned the decision to the agent.")
            return action

    async def submit_slack_decision(self, incident_id: str, approved: bool) -> None:
        incident = self.incident(incident_id)
        try:
            decision = await self.decide_rollback(incident_id, approved)
        except Exception:
            logger.exception(
                "Could not submit the rollback decision for %s", incident_id
            )
            await self.publish(
                incident, "Could not submit the decision. Check the logs and retry."
            )
            return
        await self.publish(
            incident,
            f"Rollback {decision['status']}. The agent received the decision; no deployment ran.",
        )

    def incident(self, incident_id: str) -> Incident:
        incident = self.incidents.get(incident_id)
        if incident is None:
            raise ValueError(f"Unknown incident: {incident_id}")
        return incident

    async def resolve(self, incident_id: str) -> None:
        incident = self.incident(incident_id)
        async with incident.approval_lock:
            if incident.status == "resolved":
                return
            active = incident.lock.locked() or incident.status == "awaiting_approval"
            incident.status = "resolving"
            if active and incident.session_id is not None:
                await self.client.beta.agents.sessions.events.create(
                    incident.session_id, events=[{"type": "agent.session.input.cancel"}]
                )
        async with incident.lock:
            await self._resolve(incident)

    async def _resolve(self, incident: Incident) -> None:
        if incident.status == "resolved":
            return
        history: list[dict[str, Any]] = [
            *self.history,
            {
                "id": incident.id,
                "service": incident.service,
                "summary": incident.title,
                "root_cause": incident.analysis[:1200],
                "resolution": (
                    f"Rollback to {incident.action['version']} was approved; "
                    "execution was not recorded."
                    if incident.action is not None
                    and incident.action["status"] == "approved"
                    else "Resolved without a recorded rollback."
                ),
            },
        ]
        try:
            save_history(self.history_path, history)
            self.history = history
            incident.status = "resolved"
            if (
                incident.action is not None
                and incident.action["status"] == "awaiting_approval"
            ):
                incident.action["status"] = "expired"
            if incident.slack_thread_ts is not None:
                await self.publish(
                    incident, f"Resolved {incident.id}; saved the incident findings."
                )
        except OSError:
            if incident.status != "resolved":
                incident.status = "failed"
            raise
        finally:
            if incident.status == "resolved":
                if incident.slack_thread_ts is not None:
                    self.slack_threads.pop(incident.slack_thread_ts, None)
                self.fingerprints.pop(incident.fingerprint, None)
            await self.close_runtime(incident)
            incident.record("Closed the incident session and sandbox.")

    async def close_runtime(self, incident: Incident) -> None:
        original_error = sys.exception()
        session_id = incident.session_id
        errors: list[Exception] = []
        if session_id is not None and session_id not in self.closed_sessions:
            try:
                await self.client.beta.agents.sessions.delete(session_id)
            except NotFoundError:
                self.closed_sessions.add(session_id)
                incident.session_id = None
            except Exception as error:
                errors.append(error)
            else:
                self.closed_sessions.add(session_id)
                incident.session_id = None
        if incident.sandbox is not None:
            try:
                await asyncio.to_thread(incident.sandbox.remove, force=True)
            except docker.errors.NotFound:
                incident.sandbox = None
            except Exception as error:
                errors.append(error)
            else:
                logger.info(
                    "%s: removed sandbox %s", incident.id, incident.sandbox.short_id
                )
                incident.sandbox = None
        if original_error is not None:
            for error in errors:
                original_error.add_note(f"Cleanup for session {session_id}: {error}")
        elif errors:
            raise ExceptionGroup(
                f"Could not clean up session {session_id} and its sandbox", errors
            )

    async def close(self) -> None:
        errors: list[Exception] = []
        for incident in self.incidents.values():
            try:
                await self.close_runtime(incident)
            except Exception as error:
                errors.append(error)
        if errors:
            raise ExceptionGroup("Could not close all incident runtimes", errors)
