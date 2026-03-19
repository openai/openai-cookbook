from __future__ import annotations

import tempfile
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from codereview_evals import cli


class CliTests(unittest.TestCase):
    @mock.patch("codereview_evals.cli.fetch_pull_requests")
    def test_fetch_prs_command(self, mock_fetch: mock.Mock) -> None:
        mock_fetch.return_value = (Path("/tmp/cache"), {"pull_request_count": 2})
        result = cli.main(["fetch-prs", "--repo", "openai/codex", "--limit", "2"])
        self.assertEqual(result, 0)
        mock_fetch.assert_called_once()

    @mock.patch("codereview_evals.cli.reset_app_state")
    def test_reset_command(self, mock_reset: mock.Mock) -> None:
        mock_reset.return_value = {"cache_removed": True, "removed_run_artifacts": ["run-1"]}
        result = cli.main(["reset", "--repo", "openai/codex"])
        self.assertEqual(result, 0)
        mock_reset.assert_called_once()

    @mock.patch("codereview_evals.cli.run_benchmark")
    def test_benchmark_run_command(self, mock_run: mock.Mock) -> None:
        artifacts = mock.Mock()
        artifacts.run_dir = Path("/tmp/run")
        artifacts.report_html = Path("/tmp/run/report.html")
        mock_run.return_value = (artifacts, {"total_examples": 1})
        result = cli.main(["benchmark", "run", "--cache-key", "openai_codex", "--max-prs", "2"])
        self.assertEqual(result, 0)
        mock_run.assert_called_once()

    @mock.patch("codereview_evals.cli.render_benchmark_report")
    def test_benchmark_report_command(self, mock_report: mock.Mock) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            run_dir = Path(tmp_dir)
            mock_report.return_value = run_dir / "report.html"
            result = cli.main(["benchmark", "report", "--run-dir", str(run_dir)])
            self.assertEqual(result, 0)
            mock_report.assert_called_once_with(run_dir=run_dir)


if __name__ == "__main__":
    unittest.main()
