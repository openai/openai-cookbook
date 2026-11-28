import asyncio
import json
import logging
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch

process = runpy.run_path(str(Path(__file__).parents[1] / "api_request_parallel_processor.py"))[
    "process_api_requests_from_file"
]


class DiagnosticsTest(unittest.TestCase):
    def exercise(self, data):
        processed = []
        async def process_locally(request, **kwargs):
            processed.append(request.task_id)
            kwargs["status_tracker"].num_tasks_in_progress -= 1

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.jsonl"
            path.write_text(data, encoding="utf-8")
            with patch.dict(process.__globals__, num_tokens_consumed_from_request=lambda *args: 1), \
                 patch.object(process.__globals__["APIRequest"], "call_api", process_locally):
                asyncio.run(process(str(path), str(path.with_suffix(".out")),
                                    "https://api.openai.com/v1/embeddings", "unused",
                                    1000, 1000, "fixture", 1, logging.CRITICAL))
        return processed

    def test_bad_fourth_record(self):
        with self.assertRaisesRegex(json.JSONDecodeError, r"JSONL line 4, column 2") as raised:
            self.exercise('{}\n' * 3 + '{private-record}')
        self.assertNotIn("private-record", str(raised.exception))
        self.assertIsInstance(raised.exception.__cause__, json.JSONDecodeError)

    def test_blank_second_record(self):
        with self.assertRaisesRegex(json.JSONDecodeError, "JSONL line 2"):
            self.exercise('{}\n\n')

    def test_valid_file_without_final_newline(self):
        self.assertEqual(self.exercise('{}\n{}'), [0, 1])
