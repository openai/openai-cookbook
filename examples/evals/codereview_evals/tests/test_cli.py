from __future__ import annotations

import io
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
    def test_no_args_prints_help(self) -> None:
        stdout = io.StringIO()
        with mock.patch("sys.stdout", stdout):
            result = cli.main([])
        self.assertEqual(result, 0)
        self.assertIn("usage: evalcr", stdout.getvalue())
        self.assertNotIn("error:", stdout.getvalue())

    def test_missing_benchmark_subcommand_prints_help(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with mock.patch("sys.stdout", stdout), mock.patch("sys.stderr", stderr):
            result = cli.main(["benchmark"])
        self.assertEqual(result, 0)
        self.assertIn("usage: evalcr benchmark", stdout.getvalue())
        self.assertIn("{run,report}", stdout.getvalue())
        self.assertNotIn("error:", stdout.getvalue())
        self.assertEqual("", stderr.getvalue())

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

    @mock.patch("builtins.input", return_value="")
    @mock.patch("codereview_evals.cli.default_run_id", return_value="resolved-run")
    @mock.patch("codereview_evals.cli.run_benchmark")
    @mock.patch("codereview_evals.cli.load_cached_pull_requests")
    @mock.patch("codereview_evals.cli.load_harness_bundle")
    def test_benchmark_run_command(
        self,
        mock_load_bundle: mock.Mock,
        mock_load_pull_requests: mock.Mock,
        mock_run: mock.Mock,
        mock_default_run_id: mock.Mock,
        mock_input: mock.Mock,
    ) -> None:
        stdout = io.StringIO()
        config = mock.Mock()
        config.model = "gpt-reviewer"
        config.grader_model = "gpt-grader"
        mock_load_bundle.return_value = (config, "", "", "", {}, {})
        mock_load_pull_requests.return_value = [
            {"number": 101, "title": "PR one"},
            {"number": 202, "title": "PR two"},
            {"number": 303, "title": "PR three"},
        ]
        artifacts = mock.Mock()
        artifacts.run_dir = Path("/tmp/run")
        artifacts.report_html = Path("/tmp/run/report.html")
        mock_run.return_value = (artifacts, {"total_examples": 1})
        with mock.patch("sys.stdout", stdout):
            result = cli.main(["benchmark", "run", "--cache-key", "openai_codex", "--max-prs", "2"])
        self.assertEqual(result, 0)
        mock_run.assert_called_once()
        mock_input.assert_called_once_with("Press Enter to start, or type 'cancel' to abort: ")
        mock_load_pull_requests.assert_called_once()
        self.assertEqual(mock_run.call_args.kwargs["progress_callback"], print)
        self.assertEqual(mock_run.call_args.kwargs["run_name"], "resolved-run")
        mock_default_run_id.assert_called_once_with("")
        self.assertIn("Reviewer model: gpt-reviewer", stdout.getvalue())
        self.assertIn("Grader model: gpt-grader", stdout.getvalue())
        self.assertIn("Selected PRs: 2", stdout.getvalue())
        self.assertIn("Run name: resolved-run", stdout.getvalue())

    @mock.patch("builtins.input", return_value="cancel")
    @mock.patch("codereview_evals.cli.run_benchmark")
    @mock.patch("codereview_evals.cli.load_cached_pull_requests")
    @mock.patch("codereview_evals.cli.load_harness_bundle")
    def test_benchmark_run_cancelled(
        self,
        mock_load_bundle: mock.Mock,
        mock_load_pull_requests: mock.Mock,
        mock_run: mock.Mock,
        _mock_input: mock.Mock,
    ) -> None:
        stdout = io.StringIO()
        config = mock.Mock()
        config.model = "gpt-reviewer"
        config.grader_model = "gpt-grader"
        mock_load_bundle.return_value = (config, "", "", "", {}, {})
        mock_load_pull_requests.return_value = [{"number": 101, "title": "PR one"}]
        with mock.patch("sys.stdout", stdout):
            result = cli.main(["benchmark", "run", "--cache-key", "openai_codex"])
        self.assertEqual(result, 0)
        mock_run.assert_not_called()
        self.assertIn("Cancelled.", stdout.getvalue())
        self.assertIn("Selected PRs: 1", stdout.getvalue())
        self.assertNotIn("Run name:", stdout.getvalue())

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
