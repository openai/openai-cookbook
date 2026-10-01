# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "openai>=3.13.0",
#     "docker",
#     "fastapi",
#     "python-dotenv",
#     "uvicorn",
# ]
# ///

"""Receive GitHub issue webhooks or investigate the included issue."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request

# Support direct execution from any working directory.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))


from examples.agents_api.apps.github_issues.agent import investigate_issue
from examples.agents_api.apps.github_issues.github import (
    clone_repository,
    post_findings,
    verify_signature,
)

EXAMPLE_DIR = Path(__file__).resolve().parent
DELIVERIES: set[str] = set()


async def handle_github_event(event: dict[str, Any]) -> None:
    issue = event["issue"]
    clone_url = event["repository"]["clone_url"]
    with tempfile.TemporaryDirectory(
        prefix=".agent-github-", dir=EXAMPLE_DIR
    ) as directory:
        workspace = Path(directory) / "repository"
        await asyncio.to_thread(clone_repository, clone_url, workspace)
        result = await investigate_issue(issue, workspace)

    await post_findings(issue, result["findings"])


app = FastAPI(title="GitHub issue investigator")


@app.post("/webhooks/github")
async def github_webhook(request: Request, tasks: BackgroundTasks) -> dict[str, str]:
    body = await request.body()
    secret = os.environ.get("GITHUB_WEBHOOK_SECRET", "")
    signature = request.headers.get("x-hub-signature-256", "")
    if not secret or not verify_signature(body, signature, secret):
        raise HTTPException(status_code=401, detail="Invalid webhook signature.")

    delivery = request.headers.get("x-github-delivery", "")
    if delivery and delivery in DELIVERIES:
        return {"status": "already_processed"}

    event = json.loads(body)
    event_name = request.headers.get("x-github-event", "")
    if event_name != "issues" or event.get("action") not in {
        "opened",
        "edited",
        "reopened",
    }:
        return {"status": "ignored"}

    if delivery:
        DELIVERIES.add(delivery)
    tasks.add_task(handle_github_event, event)
    return {"status": "accepted"}


async def investigate_sample_issue() -> None:
    event = json.loads((EXAMPLE_DIR / "sample_event.json").read_text())
    with tempfile.TemporaryDirectory(
        prefix=".agent-github-", dir=EXAMPLE_DIR
    ) as directory:
        workspace = Path(directory) / "repository"
        shutil.copytree(
            EXAMPLE_DIR / "sample_repository",
            workspace,
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        result = await investigate_issue(event["issue"], workspace)
        print(result["findings"])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Investigate new GitHub issues with Agents API."
    )
    parser.add_argument(
        "--issue", action="store_true", help="Investigate the included issue."
    )
    args = parser.parse_args()
    load_dotenv(EXAMPLE_DIR / ".env")
    if args.issue:
        asyncio.run(investigate_sample_issue())
        return

    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8002)


if __name__ == "__main__":
    main()
