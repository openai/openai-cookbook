"""Offline checks: python -m unittest discover -s examples/tests -p '*http_status.py' -v.

Requires the example's aiohttp and tiktoken dependencies; no API key is needed.
"""

import asyncio
import importlib.util
import json
import logging
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "parallel_processor_http_status",
    Path(__file__).resolve().parents[1] / "api_request_parallel_processor.py",
)
processor = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = processor
SPEC.loader.exec_module(processor)


class Response:
    def __init__(self, status, payload):
        self.status = status
        self.payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class Session:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def post(self, **kwargs):
        self.calls.append(kwargs)
        return next(self.responses)


class HTTPStatusTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.output = Path(directory.name) / "results.jsonl"
        self.request = processor.APIRequest(0, {"input": "sample"}, 1, 0, {"row": 1})
        self.tracker = processor.StatusTracker(
            num_tasks_started=1, num_tasks_in_progress=1
        )
        self.queue = asyncio.Queue()

    async def call(self, status, payload):
        await self.request.call_api(
            Session([Response(status, payload)]),
            "https://example.invalid/v1/embeddings",
            {},
            self.queue,
            str(self.output),
            self.tracker,
        )

    def record(self):
        records = [json.loads(line) for line in self.output.read_text().splitlines()]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0][0], self.request.request_json)
        self.assertEqual(records[0][2], {"row": 1})
        return records[0][1]

    async def test_success_keeps_response_and_metadata(self):
        payload = {"data": [{"embedding": [0.1]}]}
        await self.call(200, payload)
        self.assertEqual(self.record(), payload)
        self.assertEqual(self.tracker.num_tasks_succeeded, 1)
        self.assertEqual(self.tracker.num_tasks_in_progress, 0)
        self.assertEqual(self.tracker.num_api_errors, 0)
        self.assertTrue(self.queue.empty())

    async def test_nonstandard_503_is_saved_as_failure(self):
        await self.call(503, {"message": "Service temporarily unavailable"})
        self.assertEqual(self.tracker.num_tasks_failed, 1)
        self.assertEqual(self.tracker.num_tasks_in_progress, 0)
        self.assertTrue(self.queue.empty())
        self.assertEqual(self.tracker.num_tasks_succeeded, 0)
        self.assertEqual(self.tracker.num_api_errors, 1)
        self.assertEqual(self.tracker.num_other_errors, 0)
        self.assertIn("503", self.record()[0])
        self.assertIn("Service temporarily unavailable", self.record()[0])

    async def test_non_2xx_statuses_reject_empty_and_non_object_json(self):
        for status, payload in [(199, {}), (300, []), (400, None), (500, ""), (503, 0)]:
            with self.subTest(status=status, payload=payload):
                self.request.attempts_left = 1
                await self.call(status, payload)
                self.assertFalse(self.queue.empty())
                self.assertIs(self.queue.get_nowait(), self.request)
        self.assertEqual(self.tracker.num_api_errors, 5)
        self.assertEqual(self.tracker.num_other_errors, 0)
        self.assertEqual(self.tracker.num_tasks_succeeded, 0)
        self.assertFalse(self.output.exists())

    async def test_success_without_metadata_keeps_two_element_record(self):
        self.request.metadata = None
        await self.call(200, {"data": []})
        self.assertEqual(
            json.loads(self.output.read_text()),
            [self.request.request_json, {"data": []}],
        )

    async def test_non_json_error_still_uses_exception_retry_path(self):
        self.request.attempts_left = 1
        await self.call(503, ValueError("Synthetic non-JSON body"))
        self.assertIs(self.queue.get_nowait(), self.request)
        self.assertEqual(self.tracker.num_other_errors, 1)
        self.assertEqual(self.tracker.num_tasks_succeeded, 0)
        self.assertFalse(self.output.exists())

    async def test_upper_2xx_boundary_is_success(self):
        payload = {"data": []}
        await self.call(299, payload)
        self.assertEqual(self.record(), payload)
        self.assertEqual(self.tracker.num_tasks_succeeded, 1)

    async def test_standard_error_body_is_preserved(self):
        payload = {"error": {"message": "Synthetic invalid request"}}
        await self.call(400, payload)
        self.assertEqual(self.record(), [str(payload)])
        self.assertEqual(self.tracker.num_api_errors, 1)
        self.assertEqual(self.tracker.num_tasks_failed, 1)

    async def test_2xx_error_body_still_fails(self):
        await self.call(200, {"error": {"message": "Synthetic API error"}})
        self.assertEqual(self.tracker.num_tasks_failed, 1)
        self.assertEqual(self.tracker.num_api_errors, 1)

    async def test_rate_limits_use_existing_cooldown_counters(self):
        cases = [
            (429, {"message": "Too many requests"}),
            (429, {}),
            (429, {"error": {"message": "Too many requests"}}),
            (429, {"error": {"message": "Rate limit reached"}}),
            (200, {"error": {"message": "Rate limit reached"}}),
        ]
        self.request.attempts_left = 1
        for status, payload in cases:
            with self.subTest(status=status, payload=payload):
                with patch.object(processor.time, "time", return_value=12345):
                    await self.call(status, payload)
                self.assertFalse(self.queue.empty())
                self.assertIs(self.queue.get_nowait(), self.request)
                self.assertEqual(self.tracker.time_of_last_rate_limit_error, 12345)
        self.assertEqual(self.tracker.num_rate_limit_errors, len(cases))
        self.assertEqual(self.tracker.num_api_errors, 0)
        self.assertEqual(self.tracker.num_other_errors, 0)
        self.assertEqual(self.tracker.num_tasks_in_progress, 1)
        self.assertFalse(self.output.exists())

    async def run_file(self, responses, attempts):
        source = self.output.with_name("requests.jsonl")
        source.write_text('{"input":"sample","metadata":{"row":1}}\n')
        session = Session(responses)
        with (
            patch.object(processor.aiohttp, "ClientSession", return_value=session),
            patch.object(processor, "num_tokens_consumed_from_request", return_value=1),
        ):
            await asyncio.wait_for(
                processor.process_api_requests_from_file(
                    str(source),
                    str(self.output),
                    "https://example.invalid/v1/embeddings",
                    "synthetic-key",
                    1000,
                    1000,
                    "cl100k_base",
                    attempts,
                    logging.ERROR,
                ),
                timeout=2,
            )
        return session

    async def test_retry_then_success_saves_only_success(self):
        payload = {"data": []}
        session = await self.run_file(
            [
                Response(503, {"message": "Service temporarily unavailable"}),
                Response(200, payload),
            ],
            attempts=3,
        )
        self.assertEqual(len(session.calls), 2)
        self.assertEqual(self.record(), payload)

    async def test_exhaustion_keeps_configured_attempt_count(self):
        session = await self.run_file(
            [
                Response(503, {"message": "Service temporarily unavailable"})
                for _ in range(3)
            ],
            attempts=3,
        )
        self.assertEqual(len(session.calls), 3)
        self.assertEqual(len(self.record()), 3)
        self.assertTrue(all("503" in error for error in self.record()))


if __name__ == "__main__":
    unittest.main()
