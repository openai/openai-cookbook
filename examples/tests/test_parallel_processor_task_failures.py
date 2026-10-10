"""Run with pytest examples/tests/test_parallel_processor_task_failures.py."""

import asyncio
import importlib.util
import json
import logging
import sys
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "parallel_processor_task_failures",
    Path(__file__).resolve().parents[1] / "api_request_parallel_processor.py",
)
processor = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = processor
SPEC.loader.exec_module(processor)


class Response:
    def __init__(self, payload, state):
        self.payload = payload
        self.state = state

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def json(self):
        if self.state.get("block"):
            self.state["started"] = True
            try:
                await asyncio.Future()
            finally:
                self.state["cancelled"] = True
        return self.payload


@pytest.fixture
def harness(monkeypatch):
    state = {"calls": 0, "closed": False}

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            state["closed"] = True
            state["cancelled_before_close"] = state.get("cancelled", False)

        def post(self, **kwargs):
            state["calls"] += 1
            return Response(state.get("payload", {"data": []}), state)

    monkeypatch.setattr(processor.aiohttp, "ClientSession", Session)
    # Token counting is unrelated to task ownership and is deterministic here.
    monkeypatch.setattr(processor, "num_tokens_consumed_from_request", lambda *args: 1)
    return state


def run_processor(source, destination, attempts=1):
    return processor.process_api_requests_from_file(
        str(source),
        str(destination),
        "https://api.openai.com/v1/embeddings",
        "synthetic-key",
        1000,
        1000,
        "cl100k_base",
        attempts,
        logging.ERROR,
    )


@pytest.mark.parametrize("provider_error", [False, True])
def test_output_write_failure_reaches_the_caller(tmp_path, harness, provider_error):
    source = tmp_path / "requests.jsonl"
    source.write_text('{"input":"sample"}\n')
    if provider_error:
        harness["payload"] = {"error": {"message": "Synthetic provider failure"}}

    async def check():
        with pytest.raises(FileNotFoundError):
            await asyncio.wait_for(
                run_processor(source, tmp_path / "missing" / "results.jsonl"), 1
            )

    asyncio.run(check())
    assert harness["calls"] == 1
    assert harness["closed"]


@pytest.mark.parametrize("provider_error", [False, True])
def test_success_and_exhausted_retries_still_save_results(
    tmp_path, harness, provider_error
):
    source = tmp_path / "requests.jsonl"
    destination = tmp_path / "results.jsonl"
    source.write_text('{"input":"sample","metadata":{"row":1}}\n')
    if provider_error:
        harness["payload"] = {"error": {"message": "Synthetic provider failure"}}
    asyncio.run(asyncio.wait_for(run_processor(source, destination, attempts=2), 1))
    records = [json.loads(line) for line in destination.read_text().splitlines()]
    assert len(records) == 1
    assert records[0][0] == {"input": "sample"}
    assert records[0][2] == {"row": 1}
    assert harness["calls"] == (2 if provider_error else 1)
    assert harness["closed"]


def test_input_failure_cancels_inflight_requests_before_session_close(
    tmp_path, harness
):
    source = tmp_path / "requests.jsonl"
    source.write_text('{"input":"sample"}\n{invalid}\n')
    harness["block"] = True

    async def check():
        with pytest.raises(json.JSONDecodeError):
            await run_processor(source, tmp_path / "results.jsonl")
        assert harness["started"]
        assert harness["cancelled_before_close"]

    asyncio.run(check())
