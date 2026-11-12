"""Offline checks for the parallel processor's command-line output path."""

import asyncio
import runpy
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "api_request_parallel_processor.py"


class DefaultResultsPathTests(unittest.TestCase):
    def results_path(self, input_path, explicit_path=None):
        argv = [str(SCRIPT), "--requests_filepath", input_path]
        if explicit_path is not None:
            argv.extend(["--save_filepath", explicit_path])
        captured = {}

        def capture_request(coroutine):
            try:
                captured.update(coroutine.cr_frame.f_locals)
            finally:
                coroutine.close()

        aiohttp_stub = types.ModuleType("aiohttp")
        setattr(aiohttp_stub, "ClientSession", object)
        tiktoken_stub = types.ModuleType("tiktoken")
        with (
            mock.patch.dict(
                sys.modules, {"aiohttp": aiohttp_stub, "tiktoken": tiktoken_stub}
            ),
            mock.patch.object(sys, "argv", argv),
            mock.patch.object(asyncio, "run", capture_request),
        ):
            runpy.run_path(str(SCRIPT), run_name="__main__")
        return captured["save_filepath"]

    def test_default_results_path(self):
        for input_path, expected in (
            ("requests.jsonl", "requests_results.jsonl"),
            ("requests.ndjson", "requests_results.jsonl"),
            ("requests", "requests_results.jsonl"),
            ("dir.jsonl/input.jsonl", "dir.jsonl/input_results.jsonl"),
        ):
            with self.subTest(input_path=input_path):
                actual = self.results_path(input_path)
                self.assertEqual(actual, expected)
                self.assertNotEqual(actual, input_path)

    def test_explicit_results_path_is_unchanged(self):
        self.assertEqual(
            self.results_path("requests.ndjson", "custom/output.txt"),
            "custom/output.txt",
        )


if __name__ == "__main__":
    unittest.main()
