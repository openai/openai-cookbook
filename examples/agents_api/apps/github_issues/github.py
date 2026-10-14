"""Verify GitHub deliveries, clone repositories, and post findings."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import subprocess
from pathlib import Path
from typing import Any

import httpx


def verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    expected = (
        "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    )
    return hmac.compare_digest(signature, expected)


def clone_repository(url: str, workspace: Path) -> None:
    environment = os.environ.copy()
    if token := environment.get("GITHUB_TOKEN"):
        credentials = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        environment.update(
            {
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
                "GIT_CONFIG_VALUE_0": f"Authorization: Basic {credentials}",
            }
        )

    subprocess.run(
        ["git", "clone", "--depth", "1", url, str(workspace)],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )


async def post_findings(issue: dict[str, Any], findings: str) -> None:
    token = os.environ.get("GITHUB_TOKEN")
    comments_url = str(issue.get("comments_url", ""))
    if token and comments_url.startswith("https://api.github.com/"):
        async with httpx.AsyncClient() as http:
            response = await http.post(
                comments_url,
                json={"body": findings},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                },
            )
            response.raise_for_status()
    else:
        print(findings)
