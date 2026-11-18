"""Offline checks: pytest -q examples/utils/tests/test_embeddings_utils.py.

Requires pytest-asyncio and the dependencies imported by embeddings_utils.py.
The real SDK sends all requests to an in-process HTTP server.
"""

import asyncio
import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import pytest_asyncio
from openai import AsyncOpenAI, BadRequestError, OpenAI


@pytest_asyncio.fixture
async def embedding_helpers(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    path = Path(__file__).parents[1] / "embeddings_utils.py"
    spec = importlib.util.spec_from_file_location("embedding_helpers", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.client.close()
    if hasattr(module, "async_client"):
        await module.async_client.close()
    requests = []
    active = 0
    peak_active = 0
    lock = threading.Lock()
    overlap = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            nonlocal active, peak_active
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            with lock:
                requests.append(body)
                active += 1
                peak_active = max(peak_active, active)
                if active == 2:
                    overlap.set()
            if body.get("user") == "concurrent-test":
                overlap.wait(timeout=1)
            if body.get("model") == "invalid-test-model":
                status = 400
                response = {
                    "error": {
                        "message": "invalid test model",
                        "type": "invalid_request_error",
                    }
                }
            else:
                status = 200
                response = {
                    "object": "list",
                    "model": body["model"],
                    "data": [
                        {
                            "object": "embedding",
                            "index": i,
                            "embedding": [float(i), 0.5],
                        }
                        for i, _ in enumerate(body["input"])
                    ],
                    "usage": {"prompt_tokens": 2, "total_tokens": 2},
                }
            encoded = json.dumps(response).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
            with lock:
                active -= 1

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}/v1"
    with OpenAI(api_key="test-key", base_url=base_url, max_retries=0) as sync_client:
        async with AsyncOpenAI(
            api_key="test-key", base_url=base_url, max_retries=0
        ) as async_client:
            monkeypatch.setattr(module, "client", sync_client)
            monkeypatch.setattr(module, "async_client", async_client, raising=False)
            try:
                yield module, requests, lambda: peak_active
            finally:
                overlap.set()
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)


@pytest.mark.asyncio
@pytest.mark.parametrize("batched", [False, True])
async def test_async_embeddings_use_typed_sdk_responses(embedding_helpers, batched):
    helpers, requests, _ = embedding_helpers
    options = {
        "model": "test-embedding-model",
        "dimensions": 2,
        "encoding_format": "float",
    }
    if batched:
        actual = await helpers.aget_embeddings(["first\nline", "second"], **options)
        assert actual == [[0.0, 0.5], [1.0, 0.5]]
        expected_input = ["first line", "second"]
    else:
        actual = await helpers.aget_embedding("first\nline", **options)
        assert actual == [0.0, 0.5]
        expected_input = ["first line"]
    assert requests == [{"input": expected_input, **options}]


@pytest.mark.asyncio
async def test_async_embedding_requests_can_overlap(embedding_helpers):
    helpers, requests, peak_active = embedding_helpers
    await asyncio.gather(
        helpers.aget_embedding("first", user="concurrent-test"),
        helpers.aget_embedding("second", user="concurrent-test"),
    )
    assert len(requests) == 2
    assert peak_active() == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("batched", [False, True])
async def test_async_embeddings_preserve_sdk_errors(embedding_helpers, batched):
    helpers, requests, _ = embedding_helpers
    with pytest.raises(BadRequestError, match="invalid test model"):
        if batched:
            await helpers.aget_embeddings(["text"], model="invalid-test-model")
        else:
            await helpers.aget_embedding("text", model="invalid-test-model")
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_embedding_batch_limit_is_checked_before_requests(embedding_helpers):
    helpers, requests, _ = embedding_helpers
    with pytest.raises(AssertionError, match="batch size"):
        await helpers.aget_embeddings(["text"] * 2049)
    assert requests == []


@pytest.mark.asyncio
async def test_sync_embedding_helpers_are_unchanged(embedding_helpers):
    helpers, requests, _ = embedding_helpers
    assert helpers.get_embedding("one\nline") == [0.0, 0.5]
    assert helpers.get_embeddings(["one", "two\nlines"]) == [[0.0, 0.5], [1.0, 0.5]]
    assert [request["input"] for request in requests] == [
        ["one line"],
        ["one", "two lines"],
    ]
