"""Offline regressions for the JSONL parallel request processor."""

import asyncio
import builtins
import json
import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from examples import api_request_parallel_processor as processor


class FakeResponse:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def json(self):
        return {"ok": True}


class FakeSession:
    def __init__(self):
        self.requests = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def post(self, *, url, headers, json):
        self.requests.append(json.copy())
        return FakeResponse()


class ParallelProcessorInputEncodingTests(unittest.IsolatedAsyncioTestCase):
    async def process_under_cp1252_default(self, request):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "requests.jsonl"
            output_path = Path(directory) / "results.jsonl"
            input_path.write_text(
                json.dumps(request, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            real_open = builtins.open

            def locale_open(file, mode="r", *args, **kwargs):
                if Path(file) == input_path and "r" in mode and "encoding" not in kwargs:
                    kwargs["encoding"] = "cp1252"
                return real_open(file, mode, *args, **kwargs)

            session = FakeSession()
            with (
                patch("builtins.open", side_effect=locale_open),
                patch.object(processor.aiohttp, "ClientSession", return_value=session),
                patch.object(processor, "num_tokens_consumed_from_request", return_value=1),
            ):
                await asyncio.wait_for(
                    processor.process_api_requests_from_file(
                        str(input_path),
                        str(output_path),
                        "https://api.openai.com/v1/embeddings",
                        "unused-test-key",
                        100,
                        100,
                        "unused-test-encoding",
                        1,
                        logging.ERROR,
                    ),
                    timeout=1,
                )
            return session.requests, json.loads(output_path.read_text(encoding="utf-8"))

    async def test_raw_unicode_jsonl_survives_non_utf8_locale(self):
        request = {
            "model": "test-model",
            "input": "東京で Türkçe arama",
            "metadata": {"label": "日本語 ve Türkçe"},
        }
        sent, saved = await self.process_under_cp1252_default(request)
        expected_request = {"model": request["model"], "input": request["input"]}
        self.assertEqual(sent, [expected_request])
        self.assertEqual(saved, [expected_request, {"ok": True}, request["metadata"]])

    async def test_ascii_jsonl_still_processes(self):
        request = {"model": "test-model", "input": "hello"}
        sent, saved = await self.process_under_cp1252_default(request)
        self.assertEqual(sent, [request])
        self.assertEqual(saved, [request, {"ok": True}])


if __name__ == "__main__":
    unittest.main()
