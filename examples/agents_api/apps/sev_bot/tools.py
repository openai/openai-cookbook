"""Configure incident tools and read service evidence."""

from __future__ import annotations

import os
from typing import Any, cast

from openai.types.beta import AgentToolParam
from openai.types.beta.agent_tool_param import (
    AgentToolConfigParamFunction,
    AgentToolConfigParamMcp,
)


def define_tool(
    name: str, description: str, *fields: str
) -> AgentToolConfigParamFunction:
    return {
        "type": "function",
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": {field: {"type": "string"} for field in fields},
            "required": list(fields),
            "additionalProperties": False,
        },
    }


TOOLS: list[AgentToolParam] = [
    define_tool(
        "get_service_evidence",
        "Inspect service metrics, recent error logs, deployments, and bundled AWS evidence.",
        "service",
    ),
    define_tool(
        "recall_incidents",
        "Find related past incidents, root causes, and mitigations.",
        "service",
        "query",
    ),
    define_tool(
        "propose_rollback",
        "Request human approval to roll back to a known healthy deployment. Never executes it.",
        "service",
        "version",
        "reason",
    ),
    {"type": "programmatic_tool_calling", "enabled": True},
]
PROGRESS = {
    "get_service_evidence": "Checking service metrics, logs, and recent deployments.",
    "recall_incidents": "Retrieving related incident history.",
    "propose_rollback": "Preparing a rollback proposal for review.",
}


def configured_tools() -> list[AgentToolParam]:
    tools = [*TOOLS]
    github_token = os.environ.get("GITHUB_TOKEN")
    if github_token:
        github_tool: AgentToolConfigParamMcp = {
            "type": "mcp",
            "server_label": "github",
            "connection_origin": "service",
            "required": True,
            "allowed_tools": [
                "list_commits",
                "get_commit",
                "list_pull_requests",
                "pull_request_read",
                "get_file_contents",
            ],
            "transport": {
                "type": "http",
                "server_url": "https://api.githubcopilot.com/mcp/readonly",
                "authorization": f"Bearer {github_token}",
            },
        }
        tools.append(github_tool)
    token = os.environ.get("DEVOPS_AGENT_TOKEN")
    if token:
        region = os.environ.get("DEVOPS_AGENT_REGION", "us-east-1")
        aws_tool: AgentToolConfigParamMcp = {
            "type": "mcp",
            "server_label": "aws_devops",
            "connection_origin": "service",
            "transport": {
                "type": "http",
                "server_url": f"https://connect.aidevops.{region}.api.aws/mcp",
                "authorization": f"Bearer {token}",
            },
        }
        tools.append(aws_tool)
    return tools


def get_service(operations: dict[str, Any], name: str) -> dict[str, Any]:
    record = operations.get(name)
    if not isinstance(record, dict):
        raise ValueError(f"Unknown service: {name}")
    return cast(dict[str, Any], record)


def get_service_evidence(
    operations: dict[str, Any], arguments: dict[str, Any]
) -> dict[str, Any]:
    name = str(arguments["service"])
    service = get_service(operations, name)
    evidence: dict[str, Any] = {
        "source": "bundled_sample",
        "service": name,
        "team": str(service["team"]),
        "metrics": service["metrics"],
        "logs": service["logs"][-20:],
        "deployments": service["deployments"],
    }
    if not os.environ.get("DEVOPS_AGENT_TOKEN"):
        evidence["aws"] = service["aws"]
    evidence["repository"] = str(service["repository"])
    if os.environ.get("GITHUB_TOKEN"):
        evidence["repository"] = os.environ.get(
            "GITHUB_REPOSITORY", str(service["repository"])
        )
    else:
        evidence["pull_requests"] = service["pull_requests"]
        evidence["commits"] = service["commits"]
    return evidence
