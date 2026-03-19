from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from codereview_evals import benchmark
from codereview_evals.types import HarnessConfig


class BenchmarkTests(unittest.TestCase):
    @mock.patch("codereview_evals.benchmark.write_results")
    @mock.patch("codereview_evals.benchmark._run_json_schema_completion")
    @mock.patch("codereview_evals.benchmark._build_openai_client")
    @mock.patch("codereview_evals.benchmark.load_cached_pull_requests")
    @mock.patch("codereview_evals.benchmark.load_harness_bundle")
    def test_run_benchmark_reports_progress(
        self,
        mock_load_harness_bundle: mock.Mock,
        mock_load_cached_pull_requests: mock.Mock,
        mock_build_openai_client: mock.Mock,
        mock_run_completion: mock.Mock,
        mock_write_results: mock.Mock,
    ) -> None:
        mock_load_harness_bundle.return_value = (
            HarnessConfig(model="gpt-reviewer", grader_model="gpt-grader"),
            "agents",
            "reviewer",
            "grader",
            {},
            {},
        )
        mock_load_cached_pull_requests.return_value = [
            {"number": 11, "title": "First PR", "files": []},
            {"number": 22, "title": "Second PR", "files": []},
        ]
        mock_build_openai_client.return_value = object()
        mock_run_completion.side_effect = [
            {"summary": "ok", "comments": []},
            {"correctness": 1, "usefulness": 1, "noise": 1, "overall_pass": 1, "reason": "ok"},
            {"summary": "ok", "comments": []},
            {"correctness": 1, "usefulness": 1, "noise": 1, "overall_pass": 1, "reason": "ok"},
        ]
        mock_write_results.return_value = (mock.Mock(), {"total_examples": 2})
        progress_messages: list[str] = []

        with tempfile.TemporaryDirectory() as tmp_dir:
            benchmark.run_benchmark(
                cache_key="openai_codex",
                max_prs=2,
                harness_dir=Path(tmp_dir),
                progress_callback=progress_messages.append,
            )

        self.assertEqual(
            progress_messages,
            [
                "[1/2] Processing PR #11 First PR",
                "[1/2] Completed PR #11 (1 processed)",
                "[2/2] Processing PR #22 Second PR",
                "[2/2] Completed PR #22 (2 processed)",
            ],
        )


if __name__ == "__main__":
    unittest.main()
