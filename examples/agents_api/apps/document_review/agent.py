"""Delegate document reviews and export their reports."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from docker.errors import NotFound as ContainerNotFound
from docker.models.containers import Container
from openai import AsyncOpenAI, NotFoundError

from .sandbox import SKILLS_DIRECTORY, start_executor

logger = logging.getLogger(__name__)
INSTRUCTIONS = """\
You coordinate bulk invoice and contract reviews.
Before inspecting any document, spawn specialist subagents and assign them the files in
/workspace/input. Assign one document to each specialist when possible, or several for
larger batches. Do not review source documents yourself.

Each specialist must discover and apply $expense-review-policy before inspecting its
assigned documents. Follow the skill's arithmetic checks, decision rules, and required
report fields. Each specialist writes only its /workspace/output/<document-stem>.json,
including the extracted line items and calculation for invoices. Specialists must not
write summary.json. Check their arithmetic and document coverage before summarizing.

Wait for every specialist to finish, then write /workspace/output/summary.json with
document_count, reviews, and recommendation. Never approve a payment or sign a contract.
"""


async def review_activity(client: AsyncOpenAI, session_id: str) -> list[dict[str, Any]]:
    """Export sandbox commands available in retained item history."""
    commands: list[dict[str, Any]] = []
    subagent_ids: list[str | None] = [None]
    subagent_ids.extend(
        [
            subagent.id
            async for subagent in client.beta.agents.sessions.subagents.list(session_id)
        ]
    )
    for subagent_id in subagent_ids:
        items = (
            client.beta.agents.sessions.items.list(session_id, limit=100, order="asc")
            if subagent_id is None
            else client.beta.agents.sessions.subagents.items.list(
                subagent_id, session_id=session_id, limit=100, order="asc"
            )
        )
        async for item in items:
            if item.type == "command_execution":
                commands.append(
                    {
                        "item_id": item.id,
                        "turn_id": item.turn_id,
                        "subagent_id": subagent_id,
                        "command": item.command,
                        "status": item.status,
                    }
                )
    return commands


def validate_review(report: dict[str, Any], document: str) -> None:
    """Reject incomplete reports and inconsistent invoice arithmetic."""
    if (
        report.get("document") != document
        or not report.get("policy_id")
        or report.get("document_type") not in {"invoice", "contract"}
        or report.get("decision")
        not in {"needs_info", "escalated", "ready_for_approval"}
    ):
        raise ValueError(f"{document}: incomplete policy review")
    if report["document_type"] != "invoice":
        return
    try:
        calculation = report["calculation"]
        line_items = calculation["line_items"]
        if not line_items:
            raise ValueError("No invoice line items were extracted")
        amounts = [
            Decimal(str(item["quantity"])) * Decimal(str(item["unit_price"]))
            for item in line_items
        ]
        shipping = Decimal(str(calculation["shipping"]))
        stated = Decimal(str(report["amount"]))
        calculated = Decimal(str(calculation["calculated_total"]))
        difference = Decimal(str(calculation["difference"]))
        if not all(
            value.is_finite()
            for value in [*amounts, shipping, stated, calculated, difference]
        ):
            raise ValueError("Invoice amounts must be finite")
        if sum(amounts) + shipping != calculated or stated - calculated != difference:
            raise ValueError("Invoice totals do not match the extracted line items")
    except (KeyError, TypeError, ValueError, InvalidOperation) as error:
        raise ValueError(f"{document}: invalid invoice calculation: {error}") from error


async def review_documents(
    input_directory: Path, output_directory: Path
) -> dict[str, Any]:
    documents = sorted(path for path in input_directory.iterdir() if path.is_file())
    if not documents:
        raise ValueError("The input directory does not contain any documents.")
    if len({document.stem for document in documents}) != len(documents):
        raise ValueError(
            "Document filenames must have unique stems for their JSON reports."
        )
    if any(document.stem == "summary" for document in documents):
        raise ValueError(
            "Rename summary.*; summary.json is reserved for the batch report."
        )
    if any(document.stem == "review-activity" for document in documents):
        raise ValueError(
            "Rename review-activity.*; that name is reserved for command attribution."
        )
    output_directory.mkdir(parents=True, exist_ok=True)
    if any(output_directory.iterdir()):
        raise ValueError(
            "Choose an empty output directory so earlier reports cannot be reused."
        )
    logger.info("Documents: %s", ", ".join(document.name for document in documents))
    logger.info(
        "Input mount: %s -> /workspace/input (read-only)", input_directory.resolve()
    )
    logger.info("Output mount: %s -> /workspace/output", output_directory.resolve())
    logger.info("Skills mount: %s -> /workspace/skills (read-only)", SKILLS_DIRECTORY)

    container: Container | None = None
    async with AsyncOpenAI() as client:
        session = await client.beta.agents.sessions.create(
            agent={
                "model": os.environ.get("OPENAI_MODEL", "gpt-5.6-luna"),
                "instructions": INSTRUCTIONS,
                "reasoning": {"effort": "high"},
                "multi_agent": {
                    "enabled": True,
                    "max_concurrent_subagents": min(len(documents), 8),
                },
            },
            environment={
                "type": "self_hosted",
                "workspace_directory": "/workspace",
                "capability_directories": ["/workspace/skills"],
            },
        )
        logger.info("Session created: %s", session.id)

        try:
            environment = session.environment
            if environment.type != "self_hosted":
                raise RuntimeError("Expected a self-hosted execution environment.")
            logger.info("Environment: %s", environment.id)
            logger.info("Starting document sandbox.")
            container = await asyncio.to_thread(
                start_executor,
                input_directory,
                output_directory,
                environment.id,
                environment.remote_url,
            )
            logger.info("Sandbox started: %s", container.short_id)
            parts: list[str] = []
            subagents: set[str] = set()
            prompt = f"""\
Review all {len(documents)} documents in /workspace/input.
First spawn specialist subagents and assign the documents to them.
Each specialist must apply $expense-review-policy and include its policy_id and decision.
Wait for every review, write one JSON report per document and /workspace/output/summary.json,
and summarize the most important findings for the human approver.
"""
            async with client.beta.agents.sessions.stream(
                session.id, input=prompt
            ) as events:
                async for event in events:
                    if (
                        event.type == "agent.session.subagent.created"
                        and event.subagent.id not in subagents
                    ):
                        subagents.add(event.subagent.id)
                        logger.info(
                            "Specialist started: %s/%s", len(subagents), len(documents)
                        )
                    elif (
                        event.type == "agent.session.turn.item.done"
                        and event.item is not None
                    ):
                        item_type = event.item.type
                        if item_type not in {"reasoning", "message"}:
                            logger.info("Sandbox item: %s", item_type)
                    elif event.type == "agent.session.turn.output_text.delta":
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
                        raise RuntimeError(f"Document review failed: {event.to_dict()}")
                    if event.type == "agent.session.turn.cancelled":
                        raise RuntimeError(
                            "Document review was cancelled; reports may be incomplete."
                        )

            if len(documents) > 1 and not subagents:
                raise RuntimeError(
                    "The document batch was not delegated to specialist subagents."
                )

            report_path = output_directory / "summary.json"
            if not report_path.exists():
                response = "".join(parts).strip()
                raise RuntimeError(
                    "The agent did not create /workspace/output/summary.json."
                    + (f" Agent response: {response}" if response else "")
                )

            reviews = []
            for document in documents:
                document_report = output_directory / f"{document.stem}.json"
                if not document_report.exists():
                    raise RuntimeError(
                        f"The agent did not create {document_report.name}."
                    )
                report = json.loads(document_report.read_text())
                validate_review(report, document.name)
                reviews.append(
                    {
                        "document": document.name,
                        "report": report,
                        "status": "awaiting_approval",
                    }
                )
                logger.info("Artifact created: %s", document_report)

            activity = await review_activity(client, session.id)
            activity_path = output_directory / "review-activity.json"
            activity_path.write_text(json.dumps(activity, indent=2) + "\n")
            logger.info(
                "Command attribution saved: %s (%s commands)",
                activity_path,
                len(activity),
            )

            return {
                "summary": "".join(parts),
                "report": json.loads(report_path.read_text()),
                "reviews": reviews,
                "status": "awaiting_approval",
                "session_id": session.id,
                "subagents": len(subagents),
                "activity": activity,
                "output_directory": str(output_directory),
            }
        finally:
            original_error = sys.exception()
            cleanup_errors: list[Exception] = []
            try:
                if container is not None:
                    await asyncio.to_thread(container.remove, force=True)
                    logger.info("Sandbox removed: %s", container.short_id)
            except ContainerNotFound:
                pass
            except Exception as error:
                cleanup_errors.append(error)
            try:
                await client.beta.agents.sessions.delete(session.id)
                logger.info("Session deleted: %s", session.id)
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
