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
from codereview_evals.optimizer import OptimizationConfig
from codereview_evals.types import HarnessConfig


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

    def test_benchmark_run_requires_type(self) -> None:
        stderr = io.StringIO()
        with mock.patch("sys.stderr", stderr):
            with self.assertRaises(SystemExit) as raised:
                cli.main(["benchmark", "run", "--cache-key", "openai_codex"])
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("the following arguments are required: --type", stderr.getvalue())

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
    @mock.patch("codereview_evals.cli.run_optimizer")
    @mock.patch("codereview_evals.cli.run_pairwise")
    @mock.patch("codereview_evals.cli.load_cached_pull_requests")
    @mock.patch("codereview_evals.cli.load_optimizer_harness_bundle")
    @mock.patch("codereview_evals.cli.load_pairwise_harness_bundle")
    @mock.patch("codereview_evals.cli.load_harness_bundle")
    def test_benchmark_run_command(
        self,
        mock_load_bundle: mock.Mock,
        mock_load_optimizer_bundle: mock.Mock,
        mock_load_pairwise_bundle: mock.Mock,
        mock_load_pull_requests: mock.Mock,
        mock_run_pairwise: mock.Mock,
        mock_run_optimizer: mock.Mock,
        mock_run: mock.Mock,
        mock_default_run_id: mock.Mock,
        mock_input: mock.Mock,
    ) -> None:
        stdout = io.StringIO()
        config = HarnessConfig(model="gpt-reviewer", grader_model="gpt-grader")
        mock_load_bundle.return_value = (config, "", "", "", {}, {})
        optimizer_config = OptimizationConfig(
            model="gpt-reviewer",
            grader_model="gpt-grader",
            optimizer_model="gpt-optimizer",
            max_steps=3,
            score_threshold=0.7,
            pairwise_weight=0.5,
            benchmark_weight=0.5,
            benchmark_guardrail=0.03,
        )
        mock_load_optimizer_bundle.return_value = (optimizer_config, "", "", "", "", "", "", "", {}, {}, {}, "", {})
        mock_load_pairwise_bundle.return_value = (config, "", "", "", "", "", {}, {})
        mock_load_pull_requests.return_value = [
            {"number": 101, "title": "PR one"},
            {"number": 202, "title": "PR two"},
            {"number": 303, "title": "PR three"},
        ]
        artifacts = mock.Mock()
        artifacts.run_dir = Path("/tmp/run")
        artifacts.report_html = Path("/tmp/run/report.html")
        mock_run.return_value = (artifacts, {"total_examples": 1})
        mock_run_pairwise.return_value = (artifacts, {"total_examples": 1})
        mock_run_optimizer.return_value = (artifacts, {"steps_run": 1})
        with mock.patch("sys.stdout", stdout):
            result = cli.main(
                [
                    "benchmark",
                    "run",
                    "--type",
                    "benchmark",
                    "--cache-key",
                    "openai_codex",
                    "--max-prs",
                    "2",
                ]
            )
        self.assertEqual(result, 0)
        mock_run.assert_called_once()
        mock_input.assert_called_once_with("Press Enter to start, or type 'cancel' to abort: ")
        mock_load_pull_requests.assert_called_once()
        self.assertEqual(mock_run.call_args.kwargs["progress_callback"], print)
        self.assertEqual(mock_run.call_args.kwargs["run_name"], "resolved-run")
        self.assertEqual(mock_run.call_args.kwargs["harness_dir"], cli.DEFAULT_HARNESS_DIR)
        mock_default_run_id.assert_called_once_with("")
        self.assertIn("Harness type: benchmark", stdout.getvalue())
        self.assertIn("Reviewer model: gpt-reviewer", stdout.getvalue())
        self.assertIn("Grader model: gpt-grader", stdout.getvalue())
        self.assertIn("Reviewer reasoning effort: default", stdout.getvalue())
        self.assertIn("Max concurrency: 1", stdout.getvalue())
        self.assertIn("Selected PRs: 2", stdout.getvalue())
        self.assertIn("Run name: resolved-run", stdout.getvalue())
        self.assertIn("Visualizer: evalcr visualize --type benchmark --run-id resolved-run", stdout.getvalue())
        mock_run_pairwise.assert_not_called()
        mock_run_optimizer.assert_not_called()

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
        config = HarnessConfig(model="gpt-reviewer", grader_model="gpt-grader")
        mock_load_bundle.return_value = (config, "", "", "", {}, {})
        mock_load_pull_requests.return_value = [{"number": 101, "title": "PR one"}]
        with mock.patch("sys.stdout", stdout):
            result = cli.main(
                ["benchmark", "run", "--type", "benchmark", "--cache-key", "openai_codex"]
            )
        self.assertEqual(result, 0)
        mock_run.assert_not_called()
        self.assertIn("Cancelled.", stdout.getvalue())
        self.assertIn("Selected PRs: 1", stdout.getvalue())
        self.assertNotIn("Run name:", stdout.getvalue())

    @mock.patch("builtins.input", return_value="")
    @mock.patch("codereview_evals.cli.default_run_id", return_value="pairwise-run")
    @mock.patch("codereview_evals.cli.run_pairwise")
    @mock.patch("codereview_evals.cli.load_cached_pull_requests")
    @mock.patch("codereview_evals.cli.load_pairwise_harness_bundle")
    def test_benchmark_run_pairwise_command(
        self,
        mock_load_pairwise_bundle: mock.Mock,
        mock_load_pull_requests: mock.Mock,
        mock_run_pairwise: mock.Mock,
        _mock_default_run_id: mock.Mock,
        mock_input: mock.Mock,
    ) -> None:
        stdout = io.StringIO()
        config = HarnessConfig(model="gpt-reviewer", grader_model="gpt-grader")
        mock_load_pairwise_bundle.return_value = (config, "", "", "", "", "", {}, {})
        mock_load_pull_requests.return_value = [{"number": 101, "title": "PR one"}]
        artifacts = mock.Mock()
        artifacts.run_dir = Path("/tmp/pairwise-run")
        artifacts.report_html = Path("/tmp/pairwise-run/report.html")
        mock_run_pairwise.return_value = (artifacts, {"candidate_win_rate": 1.0})
        with mock.patch("sys.stdout", stdout):
            result = cli.main(
                ["benchmark", "run", "--type", "pairwise", "--cache-key", "openai_codex"]
            )
        self.assertEqual(result, 0)
        mock_input.assert_called_once_with("Press Enter to start, or type 'cancel' to abort: ")
        self.assertEqual(
            mock_run_pairwise.call_args.kwargs["harness_dir"],
            cli.DEFAULT_PAIRWISE_HARNESS_DIR,
        )
        self.assertIn("Harness type: pairwise", stdout.getvalue())
        self.assertIn("Visualizer: evalcr visualize --type pairwise --run-id pairwise-run", stdout.getvalue())

    @mock.patch("builtins.input", return_value="")
    @mock.patch("codereview_evals.cli.default_run_id", return_value="optimizer-run")
    @mock.patch("codereview_evals.cli.run_optimizer")
    @mock.patch("codereview_evals.cli.load_cached_pull_requests")
    @mock.patch("codereview_evals.cli.load_optimizer_harness_bundle")
    def test_benchmark_run_optimizer_command(
        self,
        mock_load_optimizer_bundle: mock.Mock,
        mock_load_pull_requests: mock.Mock,
        mock_run_optimizer: mock.Mock,
        _mock_default_run_id: mock.Mock,
        mock_input: mock.Mock,
    ) -> None:
        stdout = io.StringIO()
        config = OptimizationConfig(
            model="gpt-reviewer",
            grader_model="gpt-grader",
            optimizer_model="gpt-optimizer",
            max_steps=4,
            score_threshold=0.75,
            pairwise_weight=0.5,
            benchmark_weight=0.5,
            benchmark_guardrail=0.03,
        )
        mock_load_optimizer_bundle.return_value = (config, "", "", "", "", "", "", "", {}, {}, {}, "", {})
        mock_load_pull_requests.return_value = [{"number": 101, "title": "PR one"}]
        artifacts = mock.Mock()
        artifacts.run_dir = Path("/tmp/optimizer-run")
        artifacts.report_html = Path("/tmp/optimizer-run/report.html")
        mock_run_optimizer.return_value = (artifacts, {"steps_run": 2})
        with mock.patch("sys.stdout", stdout):
            result = cli.main(
                [
                    "benchmark",
                    "run",
                    "--type",
                    "optimizer",
                    "--cache-key",
                    "openai_codex",
                    "--max-steps",
                    "5",
                    "--score-threshold",
                    "0.8",
                ]
            )
        self.assertEqual(result, 0)
        mock_input.assert_called_once_with("Press Enter to start, or type 'cancel' to abort: ")
        self.assertEqual(
            mock_run_optimizer.call_args.kwargs["harness_dir"],
            cli.DEFAULT_OPTIMIZER_HARNESS_DIR,
        )
        self.assertEqual(mock_run_optimizer.call_args.kwargs["max_steps"], 5)
        self.assertEqual(mock_run_optimizer.call_args.kwargs["score_threshold"], 0.8)
        self.assertTrue(mock_run_optimizer.call_args.kwargs["enable_benchmark_cache"])
        self.assertIn("Harness type: optimizer", stdout.getvalue())
        self.assertIn("Optimizer model: gpt-optimizer", stdout.getvalue())
        self.assertIn("Benchmark cache: enabled", stdout.getvalue())
        self.assertIn("Max steps: 5", stdout.getvalue())
        self.assertIn("Score threshold: 0.8", stdout.getvalue())
        self.assertIn("Visualizer: evalcr visualize --type optimizer --run-id optimizer-run", stdout.getvalue())

    @mock.patch("codereview_evals.cli.render_benchmark_report")
    def test_benchmark_report_command(self, mock_report: mock.Mock) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            run_dir = Path(tmp_dir)
            mock_report.return_value = run_dir / "report.html"
            result = cli.main(["benchmark", "report", "--run-dir", str(run_dir)])
            self.assertEqual(result, 0)
            mock_report.assert_called_once_with(run_dir=run_dir)

    @mock.patch("codereview_evals.cli._serve_run_visualization")
    def test_visualize_command(self, mock_visualize: mock.Mock) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            harness_dir = Path(tmp_dir) / "1_benchmark_harness"
            run_dir = harness_dir / "results" / "run-123"
            run_dir.mkdir(parents=True)
            (run_dir / "report.html").write_text("<html></html>", encoding="utf-8")
            with mock.patch.object(cli, "DEFAULT_HARNESS_DIR", harness_dir):
                result = cli.main(["visualize", "--run-id", "run-123", "--type", "benchmark"])
        self.assertEqual(result, 0)
        mock_visualize.assert_called_once_with(run_dir=run_dir, port=8000)

    def test_visualize_command_missing_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            harness_dir = Path(tmp_dir) / "1_benchmark_harness"
            harness_dir.mkdir(parents=True)
            with mock.patch.object(cli, "DEFAULT_HARNESS_DIR", harness_dir):
                with self.assertRaises(FileNotFoundError) as raised:
                    cli.main(["visualize", "--run-id", "missing-run"])
        self.assertIn("missing-run", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
