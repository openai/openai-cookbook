from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from contextlib import AsyncExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import BaseModel, Field

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents import ModelSettings, Runner
from agents.mcp import MCPServer, MCPServerStreamableHttp
from agents.run import RunConfig
from agents.sandbox import Manifest, SandboxAgent, SandboxRunConfig
from agents.sandbox.capabilities import ApplyPatch, Shell
from agents.sandbox.entries import LocalDir, LocalFile
from agents.sandbox.sandboxes.docker import DockerSandboxClient, DockerSandboxClientOptions
from docker import from_env as docker_from_env


EXAMPLE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = "gpt-5.4"
DEFAULT_DOCKER_IMAGE = "python:3.14-slim"
DEFAULT_PROMPT = (
    "Migrate the mounted repo from Chat Completions to the Responses API. "
    "Follow migration_agent/AGENTS.md and repo/MIGRATION.md. "
    "Run the required baseline tests, patch the app and tests, run the check command, "
    "run the final tests, produce a diff, "
    "and return the structured migration result."
)
OPENAI_RESPONSES_MIGRATION_DOC_URL = (
    "https://developers.openai.com/api/docs/guides/migrate-to-responses"
)
AGENT_INSTRUCTIONS = (
    "You are a careful code-migration agent. Work only inside the mounted repo. "
    "If the openai_docs MCP server is available, fetch "
    f"{OPENAI_RESPONSES_MIGRATION_DOC_URL} before patching code. Do not use docs search. "
    "Read the migration brief, run tests before and after editing, make the smallest "
    "useful patch, and return a structured migration result."
)
DEVELOPER_INSTRUCTIONS = (
    "Follow migration_agent/AGENTS.md exactly. Use shell commands from the workspace. "
    "Do not use network access or real API credentials. Keep tests offline."
)

SandboxBackend = Literal["cloudflare", "docker", "e2b"]


@dataclass(frozen=True)
class MigrationTask:
    name: str
    repo_path: Path

    @property
    def migration_brief_path(self) -> Path:
        return self.repo_path / "MIGRATION.md"


class MigrationResult(BaseModel):
    baseline_test_command: str = Field(description="Baseline test command run from repo/.")
    baseline_test_result: str = Field(description="Short pass/fail summary before edits.")
    check_command: str = Field(description="Static check or formatting command run from repo/.")
    check_result: str = Field(description="Short pass/fail summary for the check command.")
    final_test_command: str = Field(description="Final test command run from repo/.")
    final_test_result: str = Field(description="Short pass/fail summary after edits.")
    changed_files: list[str] = Field(description="Workspace-relative paths changed by the agent.")
    migration_report: str = Field(description="Markdown summary of the migration.")
    migration_patch: str = Field(description="Patch text for the migration.")


class MigrationTaskSummary(BaseModel):
    task_name: str
    output_dir: str
    report_path: str
    patch_path: str
    changed_files: list[str]
    final_test_result: str


class MigrationCampaignResult(BaseModel):
    task_summaries: list[MigrationTaskSummary]


DEFAULT_MIGRATION_TASKS = (
    MigrationTask(
        name="support_reply_service",
        repo_path=EXAMPLE_ROOT / "repo_fixtures" / "support_reply_service",
    ),
    MigrationTask(
        name="case_summary_service",
        repo_path=EXAMPLE_ROOT / "repo_fixtures" / "case_summary_service",
    ),
)


def get_migration_task(task_name: str) -> MigrationTask:
    for task in DEFAULT_MIGRATION_TASKS:
        if task.name == task_name:
            return task
    supported = ", ".join(task.name for task in DEFAULT_MIGRATION_TASKS)
    raise ValueError(f"Unknown migration task {task_name!r}. Supported tasks: {supported}.")


def select_migration_tasks(task_names: list[str] | None = None) -> list[MigrationTask]:
    if not task_names:
        return list(DEFAULT_MIGRATION_TASKS)
    return [get_migration_task(task_name) for task_name in task_names]


def build_manifest(task: MigrationTask | None = None) -> Manifest:
    task = task or DEFAULT_MIGRATION_TASKS[0]
    return Manifest(
        root="/workspace",
        entries={
            "migration_agent/AGENTS.md": LocalFile(
                src=EXAMPLE_ROOT / "migration_agent" / "AGENTS.md"
            ),
            "repo": LocalDir(src=task.repo_path),
        },
    )


def build_openai_docs_mcp_server(url: str) -> MCPServerStreamableHttp:
    return MCPServerStreamableHttp(
        params={"url": url},
        name="openai_docs",
        cache_tools_list=True,
        client_session_timeout_seconds=30,
        require_approval="never",
    )


def build_agent(
    *,
    model: str,
    manifest: Manifest,
    mcp_servers: list[MCPServer] | None = None,
) -> SandboxAgent:
    return SandboxAgent(
        name="Code Migration Agent",
        model=model,
        instructions=AGENT_INSTRUCTIONS,
        developer_instructions=DEVELOPER_INSTRUCTIONS,
        default_manifest=manifest,
        capabilities=[Shell(), ApplyPatch()],
        mcp_servers=list(mcp_servers or []),
        model_settings=ModelSettings(tool_choice="required"),
        output_type=MigrationResult,
    )


async def create_sandbox(
    backend: SandboxBackend,
    manifest: Manifest,
    *,
    docker_image: str,
):
    if backend == "cloudflare":
        try:
            from agents.extensions.sandbox import (  # type: ignore[attr-defined]
                CloudflareSandboxClient,
                CloudflareSandboxClientOptions,
            )
        except Exception as exc:
            raise SystemExit(
                "Cloudflare sandbox support is not installed in this environment. "
                "Install the SDK Cloudflare extra, or run with --backend docker."
            ) from exc

        worker_url = os.environ.get("CLOUDFLARE_SANDBOX_WORKER_URL")
        if not worker_url:
            raise SystemExit(
                "CLOUDFLARE_SANDBOX_WORKER_URL is required for --backend cloudflare. "
                "Run with --backend docker for a local sandbox."
            )
        api_key = os.environ.get("CLOUDFLARE_SANDBOX_API_KEY")
        client = CloudflareSandboxClient()
        session = await client.create(
            manifest=manifest,
            options=CloudflareSandboxClientOptions(worker_url=worker_url, api_key=api_key),
        )
        return client, session

    if backend == "e2b":
        try:
            from agents.extensions.sandbox import (  # type: ignore[attr-defined]
                E2BSandboxClient,
                E2BSandboxClientOptions,
                E2BSandboxType,
            )
        except Exception as exc:
            raise SystemExit(
                "E2B sandbox support is not installed in this environment. "
                "Install the SDK E2B extra, or run with --backend docker."
            ) from exc

        if not os.environ.get("E2B_API_KEY"):
            raise SystemExit(
                "E2B_API_KEY is required for --backend e2b. "
                "Run with --backend docker for a local sandbox."
            )

        client = E2BSandboxClient()
        session = await client.create(
            manifest=manifest,
            options=E2BSandboxClientOptions(sandbox_type=E2BSandboxType.E2B),
        )
        return client, session

    client = DockerSandboxClient(docker_from_env())
    session = await client.create(
        manifest=manifest,
        options=DockerSandboxClientOptions(image=docker_image),
    )
    return client, session


def write_host_artifacts(output_dir: Path, result: MigrationResult) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "migration_report.md").write_text(
        result.migration_report.strip() + "\n",
        encoding="utf-8",
    )
    (output_dir / "migration.patch").write_text(
        result.migration_patch.strip() + "\n",
        encoding="utf-8",
    )
    (output_dir / "migration_result.json").write_text(
        result.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )


def append_audit_event(audit_log_path: Path, payload: dict[str, Any]) -> None:
    audit_log_path.parent.mkdir(parents=True, exist_ok=True)
    with audit_log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, default=str) + "\n")


async def configure_host_mcp_servers(
    stack: AsyncExitStack,
) -> tuple[list[MCPServer], list[dict[str, Any]]]:
    mcp_servers: list[MCPServer] = []
    host_audit_events: list[dict[str, Any]] = []

    openai_docs_mcp_url = os.environ.get("OPENAI_DOCS_MCP_URL")
    if openai_docs_mcp_url:
        openai_docs = build_openai_docs_mcp_server(openai_docs_mcp_url)
        await stack.enter_async_context(openai_docs)
        mcp_servers.append(openai_docs)
        host_audit_events.append(
            {
                "event": "host_mcp_connected",
                "mcp_server": "openai_docs",
                "url": openai_docs_mcp_url,
            }
        )

    return mcp_servers, host_audit_events


def summarize_task_result(
    *,
    task: MigrationTask,
    output_dir: Path,
    result: MigrationResult,
) -> MigrationTaskSummary:
    return MigrationTaskSummary(
        task_name=task.name,
        output_dir=str(output_dir),
        report_path=str(output_dir / "migration_report.md"),
        patch_path=str(output_dir / "migration.patch"),
        changed_files=result.changed_files,
        final_test_result=result.final_test_result,
    )


def write_campaign_summary(output_root: Path, result: MigrationCampaignResult) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "batch_summary.json").write_text(
        result.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )


async def run_migration_task(
    *,
    task: MigrationTask,
    backend: SandboxBackend,
    model: str,
    prompt: str,
    docker_image: str,
    output_dir: Path,
    enable_hosted_tracing: bool,
    mcp_servers: list[MCPServer] | None = None,
    host_audit_events: list[dict[str, Any]] | None = None,
) -> MigrationResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    audit_log_path = output_dir / "migration_audit.jsonl"
    audit_log_path.unlink(missing_ok=True)

    for event in host_audit_events or []:
        append_audit_event(audit_log_path, event)

    manifest = build_manifest(task)
    client = None
    session = None

    agent = build_agent(model=model, manifest=manifest, mcp_servers=mcp_servers)
    client, session = await create_sandbox(backend, manifest, docker_image=docker_image)

    try:
        async with session:
            result = Runner.run_streamed(
                agent,
                [{"role": "user", "content": f"Task name: {task.name}\n\n{prompt}"}],
                max_turns=30,
                run_config=RunConfig(
                    sandbox=SandboxRunConfig(session=session),
                    workflow_name=f"Sandboxed code migration: {task.name} ({backend})",
                    tracing_disabled=not enable_hosted_tracing,
                ),
            )
            async for event in result.stream_events():
                if event.type != "run_item_stream_event":
                    continue
                if event.name in {"tool_called", "tool_output"}:
                    raw_item = getattr(event.item, "raw_item", None)
                    append_audit_event(
                        audit_log_path,
                        {
                            "event": event.name,
                            "item_type": getattr(event.item, "type", None),
                            "raw_item": str(raw_item)[:4000],
                        },
                    )

            if result.final_output is None:
                raise RuntimeError("Migration agent returned no structured output.")
            migration = cast(MigrationResult, result.final_output)
    finally:
        if client is not None and session is not None:
            await client.delete(session)

    write_host_artifacts(output_dir, migration)
    append_audit_event(
        audit_log_path,
        {
            "event": "host_artifacts_written",
            "paths": [
                str(output_dir / "migration_report.md"),
                str(output_dir / "migration.patch"),
                str(output_dir / "migration_result.json"),
            ],
        },
    )
    return migration


async def run_migration_campaign(
    *,
    tasks: list[MigrationTask],
    backend: SandboxBackend,
    model: str,
    prompt: str,
    docker_image: str,
    output_root: Path,
    enable_hosted_tracing: bool,
) -> MigrationCampaignResult:
    task_summaries: list[MigrationTaskSummary] = []

    async with AsyncExitStack() as stack:
        mcp_servers, host_audit_events = await configure_host_mcp_servers(stack)

        for task in tasks:
            output_dir = output_root / task.name
            migration = await run_migration_task(
                task=task,
                backend=backend,
                model=model,
                prompt=prompt,
                docker_image=docker_image,
                output_dir=output_dir,
                enable_hosted_tracing=enable_hosted_tracing,
                mcp_servers=mcp_servers,
                host_audit_events=host_audit_events,
            )
            task_summaries.append(
                summarize_task_result(task=task, output_dir=output_dir, result=migration)
            )

    campaign = MigrationCampaignResult(task_summaries=task_summaries)
    write_campaign_summary(output_root, campaign)
    return campaign


async def run(
    *,
    backend: SandboxBackend,
    model: str,
    prompt: str,
    docker_image: str,
    output_dir: Path,
    enable_hosted_tracing: bool,
    task: MigrationTask | None = None,
) -> MigrationResult:
    async with AsyncExitStack() as stack:
        mcp_servers, host_audit_events = await configure_host_mcp_servers(stack)
        return await run_migration_task(
            task=task or DEFAULT_MIGRATION_TASKS[0],
            backend=backend,
            model=model,
            prompt=prompt,
            docker_image=docker_image,
            output_dir=output_dir,
            enable_hosted_tracing=enable_hosted_tracing,
            mcp_servers=mcp_servers,
            host_audit_events=host_audit_events,
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=["cloudflare", "docker", "e2b"], default="docker")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--docker-image", default=DEFAULT_DOCKER_IMAGE)
    parser.add_argument("--output-dir", type=Path, default=EXAMPLE_ROOT / "outputs")
    parser.add_argument(
        "--task",
        action="append",
        choices=[task.name for task in DEFAULT_MIGRATION_TASKS],
        help="Migration task to run. Repeat to run multiple tasks; omit to run all tasks.",
    )
    parser.add_argument("--enable-hosted-tracing", action="store_true")
    args = parser.parse_args()

    tasks = select_migration_tasks(args.task)
    campaign = asyncio.run(
        run_migration_campaign(
            tasks=tasks,
            backend=cast(SandboxBackend, args.backend),
            model=args.model,
            prompt=args.prompt,
            docker_image=args.docker_image,
            output_root=args.output_dir,
            enable_hosted_tracing=args.enable_hosted_tracing,
        )
    )
    for task_summary in campaign.task_summaries:
        print(
            f"{task_summary.task_name}: wrote {task_summary.patch_path} "
            f"and {task_summary.report_path}"
        )
    print(f"\nwrote batch summary to {args.output_dir / 'batch_summary.json'}")


if __name__ == "__main__":
    main()
