from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from codereview_evals import cli


class CliTests(unittest.TestCase):
    def test_no_args_prints_help(self) -> None:
        stdout = io.StringIO()
        with mock.patch("sys.stdout", stdout):
            result = cli.main([])
        self.assertEqual(result, 0)
        self.assertIn("usage: evalcr", stdout.getvalue())

    @mock.patch("codereview_evals.cli.fetch_pull_requests")
    def test_fetch_prs_command(self, mock_fetch: mock.Mock) -> None:
        mock_fetch.return_value = (Path("/tmp/cache"), {"pull_request_count": 2})
        result = cli.main(["fetch-prs", "--repo", "openai/codex", "--limit", "2"])
        self.assertEqual(result, 0)
        mock_fetch.assert_called_once()

    @mock.patch("codereview_evals.cli.prepare_dataset")
    def test_prepare_dataset_command(self, mock_prepare: mock.Mock) -> None:
        artifacts = mock.Mock()
        artifacts.dataset_path = Path("/tmp/benchmark.jsonl")
        mock_prepare.return_value = (artifacts, {"record_count": 3})
        result = cli.main(["prepare-dataset", "--level", "2", "--cache-key", "openai_codex"])
        self.assertEqual(result, 0)
        self.assertEqual(mock_prepare.call_args.kwargs["level"], 2)

    @mock.patch("codereview_evals.cli.run_evals")
    def test_run_evals_command(self, mock_run_evals: mock.Mock) -> None:
        artifacts = mock.Mock()
        artifacts.run_dir = Path("/tmp/run")
        artifacts.dataset_path = Path("/tmp/benchmark.jsonl")
        mock_run_evals.return_value = (artifacts, {"report_url": "https://example.com"})
        result = cli.main(["run-evals", "--level", "1", "--cache-key", "openai_codex"])
        self.assertEqual(result, 0)
        self.assertEqual(mock_run_evals.call_args.kwargs["level"], 1)

    @mock.patch("codereview_evals.cli.reset_app_state")
    def test_reset_command(self, mock_reset: mock.Mock) -> None:
        mock_reset.return_value = {"cache_removed": True}
        result = cli.main(["reset", "--cache-key", "openai_codex"])
        self.assertEqual(result, 0)
        mock_reset.assert_called_once()


if __name__ == "__main__":
    unittest.main()
