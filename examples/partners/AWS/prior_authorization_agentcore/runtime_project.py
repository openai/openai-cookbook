"""Load the Runtime project files packaged by the notebook."""

from __future__ import annotations

from pathlib import Path
from typing import Any


_RUNTIME_SOURCE_ROOT = Path(__file__).with_name("runtime_source")
_ALLOWED_RUNTIME_FILES = {
    "main.py",
    "models.py",
    "policy_registry.py.tmpl",
    "pyproject.toml",
    "retrieval.py",
    "workflow.py",
}


def load_runtime_source(filename: str) -> str:
    """Load one reviewed Runtime source file from this package."""
    if filename not in _ALLOWED_RUNTIME_FILES:
        raise ValueError(f"Unsupported Runtime source file: {filename}")
    return (_RUNTIME_SOURCE_ROOT / filename).read_text(encoding="utf-8")


def render_policy_registry_source(
    trusted_policy_definitions: dict[str, Any],
) -> str:
    """Insert application-owned policy definitions into the Runtime module."""
    template = load_runtime_source("policy_registry.py.tmpl")
    return template.replace(
        "__TRUSTED_POLICY_PAYLOADS__",
        repr(trusted_policy_definitions),
    )


def build_runtime_kb_policy(
    *,
    partition: str,
    region: str,
    account_id: str,
    knowledge_base_id: str,
) -> dict[str, object]:
    """Build the Runtime permission for the selected Knowledge Base."""
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "RetrieveMappedPublicPolicy",
                "Effect": "Allow",
                "Action": "bedrock:Retrieve",
                "Resource": (
                    f"arn:{partition}:bedrock:{region}:"
                    f"{account_id}:knowledge-base/{knowledge_base_id}"
                ),
            }
        ],
    }
