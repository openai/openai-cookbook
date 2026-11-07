"""Offline token-accounting tests for the parallel request processor."""

import asyncio
import copy
import importlib.util
import json
import logging
from pathlib import Path
import sys

import pytest
import tiktoken

SPEC = importlib.util.spec_from_file_location(
    "parallel_embedding_inputs",
    Path(__file__).parents[1] / "api_request_parallel_processor.py",
)
processor = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = processor
SPEC.loader.exec_module(processor)


@pytest.fixture(autouse=True)
def synthetic_encoding(monkeypatch):
    encoding = tiktoken.Encoding(
        name="synthetic-byte-encoding",
        pat_str=r"(?s:.)",
        mergeable_ranks={bytes([value]): value for value in range(256)},
        special_tokens={},
    )
    monkeypatch.setattr(processor.tiktoken, "get_encoding", lambda _: encoding)
    return encoding


@pytest.mark.parametrize(
    "value,count",
    [
        ([10, 20, 30], 3),
        ([[10], [20, 30]], 3),
        ([0], 1),
        ([], 0),
        ([[], [1, 2], []], 2),
        ([[], []], 0),
    ],
)
def test_token_id_inputs_are_counted_without_encoding(value, count):
    original = copy.deepcopy(value)
    assert (
        processor.num_tokens_consumed_from_request(
            {"input": value}, "embeddings", "fixture"
        )
        == count
    )
    assert value == original


@pytest.mark.parametrize("value", ["hello", ["hello", "café"], "", ["", "東"]])
def test_existing_text_paths_are_preserved(value, synthetic_encoding):
    texts = [value] if isinstance(value, str) else value
    expected = sum(len(synthetic_encoding.encode(text)) for text in texts)
    assert (
        processor.num_tokens_consumed_from_request(
            {"input": value}, "embeddings", "fixture"
        )
        == expected
    )


@pytest.mark.parametrize(
    "value",
    [
        True,
        10,
        None,
        {},
        [True],
        [[False]],
        [1, "text"],
        ["text", [1]],
        [[1], 2],
        [1.5],
        [[1.5]],
    ],
)
def test_heterogeneous_and_boolean_inputs_are_rejected(value):
    with pytest.raises(TypeError):
        processor.num_tokens_consumed_from_request(
            {"input": value}, "embeddings", "fixture"
        )


@pytest.mark.parametrize("value", [[10, 20, 30], [[10], [20, 30]], "text", ["a", "b"]])
def test_processor_submits_original_inputs_and_saves_results(
    tmp_path, monkeypatch, value
):
    submitted = []

    class Response:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def json(self):
            return {"data": []}

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def post(self, **kwargs):
            submitted.append(copy.deepcopy(kwargs["json"]))
            return Response()

    monkeypatch.setattr(processor.aiohttp, "ClientSession", Session)
    source, destination = tmp_path / "input.jsonl", tmp_path / "output.jsonl"
    request = {"input": value, "model": "synthetic-model"}
    source.write_text(json.dumps(request) + "\n")
    asyncio.run(
        asyncio.wait_for(
            processor.process_api_requests_from_file(
                str(source),
                str(destination),
                "https://api.openai.com/v1/embeddings",
                "synthetic-key",
                1000,
                1000,
                "fixture",
                1,
                logging.ERROR,
            ),
            2,
        )
    )
    assert submitted == [request]
    assert json.loads(destination.read_text()) == [request, {"data": []}]


def test_completion_token_accounting_is_unchanged(synthetic_encoding):
    request = {"prompt": "abc", "n": 2, "max_tokens": 5}
    assert (
        processor.num_tokens_consumed_from_request(request, "completions", "fixture")
        == 13
    )
