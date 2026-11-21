import asyncio
import json
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from examples import api_request_parallel_processor as processor


@pytest.mark.parametrize("include_valid_request", [False, True])
def test_oversized_request_does_not_block_batch(
    tmp_path, monkeypatch, include_valid_request
):
    oversized = {"model": "text-embedding-3-small", "input": "one two three"}
    valid = {"model": "text-embedding-3-small", "input": "one two"}
    metadata = {"row_id": 0}
    requests = [{**oversized, "metadata": metadata}]
    if include_valid_request:
        requests.append(valid)
    request_file = tmp_path / "requests.jsonl"
    request_file.write_text("\n".join(map(json.dumps, requests)), encoding="utf-8")
    result_file = tmp_path / "results.jsonl"

    monkeypatch.setattr(
        processor,
        "num_tokens_consumed_from_request",
        lambda request, *_: len(request["input"].split()),
    )
    response = {"data": [{"embedding": [0.5]}]}
    session_factory = MagicMock()
    session = session_factory.return_value.__aenter__.return_value
    session.post = MagicMock()
    session.post.return_value.__aenter__.return_value.json = AsyncMock(
        return_value=response
    )
    monkeypatch.setattr(processor.aiohttp, "ClientSession", session_factory)

    async def run():
        await asyncio.wait_for(
            processor.process_api_requests_from_file(
                requests_filepath=request_file,
                save_filepath=result_file,
                request_url="https://api.openai.com/v1/embeddings",
                api_key="unused",
                max_requests_per_minute=60,
                max_tokens_per_minute=2,
                token_encoding_name="cl100k_base",
                max_attempts=2,
                logging_level=logging.INFO,
            ),
            timeout=1,
        )

    asyncio.run(run())

    results = [
        json.loads(line)
        for line in result_file.read_text(encoding="utf-8").splitlines()
    ]
    request, errors, result_metadata = results[0]
    assert request == oversized
    assert len(errors) == 1
    assert "requires 3 tokens" in errors[0]
    assert "max_tokens_per_minute (2)" in errors[0]
    assert result_metadata == metadata
    if include_valid_request:
        assert results[1:] == [[valid, response]]
        assert session.post.call_count == 1
        assert session.post.call_args.kwargs["json"] == valid
    else:
        assert len(results) == 1
        session.post.assert_not_called()
