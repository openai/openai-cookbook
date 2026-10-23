from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from notebook_helpers import evaluation_environment


@pytest.mark.parametrize("tracing_mode", [None, "aws", "dual"])
def test_notebook_evaluation_preserves_tracing_mode_and_limits_environment(
    tracing_mode: str | None,
) -> None:
    allowed_environment = {
        "PATH": "/usr/bin",
        "AWS_REGION": "us-west-2",
        "AWS_PROFILE": "cookbook-test",
        "OPENAI_API_KEY": "bedrock-model-key",
        "OPENAI_BASE_URL": "https://bedrock-mantle.us-west-2.api.aws/v1",
        "OPENAI_TRACE_API_KEY": "separate-openai-trace-key",
        "OPENAI_PROJECT_ID": "trace-project",
        "LOCAL_AGENT_LOG_GROUP": "test-spans",
        "PROMPTFOO_AGENT_EVALUATION_CASE_IDS": "upcoming-status",
    }
    if tracing_mode is not None:
        allowed_environment["COOKBOOK_TRACING_MODE"] = tracing_mode
    environment = {
        **allowed_environment,
        "AWS_UNRELATED_SECRET": "not-for-this-evaluation",
        "GITHUB_TOKEN": "not-for-this-evaluation",
        "OPENAI_ADMIN_KEY": "not-for-this-evaluation",
        "UNRELATED_PROJECT_TOKEN": "not-for-this-evaluation",
        "UV_INDEX_URL": "https://user:password@packages.example/simple",
    }
    original_environment = environment.copy()

    with patch.dict(os.environ, environment, clear=True):
        selected = evaluation_environment()
        assert dict(os.environ) == original_environment

    # The checked-in runner normalizes an absent mode to aws and removes the
    # OpenAI trace credentials in that mode; dual must reach it unchanged.
    assert selected == {
        **allowed_environment,
        "RUN_PROMPTFOO_AGENT_EVALUATION": "1",
    }
    assert environment == original_environment
