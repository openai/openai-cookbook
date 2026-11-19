"""Tests for API request parallel processor input validation.

Run with:
    python -m pytest examples/tests/test_api_request_parallel_processor.py
"""

import asyncio
import sys
from pathlib import Path

import pytest

EXAMPLES_DIRECTORY = str(Path(__file__).resolve().parents[1])
if EXAMPLES_DIRECTORY not in sys.path:
    sys.path.insert(0, EXAMPLES_DIRECTORY)

from api_request_parallel_processor import process_api_requests_from_file  # noqa: E402


def run_processor(**overrides):
    arguments = {
        "requests_filepath": "unused-requests.jsonl",
        "save_filepath": "unused-results.jsonl",
        "request_url": "https://api.openai.com/v1/embeddings",
        "api_key": "test-key",
        "max_requests_per_minute": 10.0,
        "max_tokens_per_minute": 1000.0,
        "token_encoding_name": "cl100k_base",
        "max_attempts": 3,
        "logging_level": 20,
    }
    arguments.update(overrides)
    asyncio.run(process_api_requests_from_file(**arguments))


@pytest.mark.parametrize(
    ("argument", "value"),
    [
        ("max_requests_per_minute", 0),
        ("max_requests_per_minute", -1),
        ("max_requests_per_minute", float("nan")),
        ("max_requests_per_minute", float("inf")),
        ("max_requests_per_minute", float("-inf")),
        ("max_tokens_per_minute", 0),
        ("max_tokens_per_minute", -1),
        ("max_tokens_per_minute", float("nan")),
        ("max_tokens_per_minute", float("inf")),
        ("max_tokens_per_minute", float("-inf")),
    ],
)
def test_rejects_non_positive_or_non_finite_rate_limits(argument, value):
    with pytest.raises(ValueError, match=argument):
        run_processor(**{argument: value})


@pytest.mark.parametrize("max_attempts", [0, -1])
def test_rejects_retry_counts_below_one(max_attempts):
    with pytest.raises(ValueError, match="max_attempts"):
        run_processor(max_attempts=max_attempts)
