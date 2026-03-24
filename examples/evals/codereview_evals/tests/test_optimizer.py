from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from codereview_evals import optimizer


def _snapshot(number: int = 101, title: str = "Example PR") -> dict:
    return {
        "number": number,
        "title": title,
        "url": f"https://example.com/pr/{number}",
        "merged": True,
        "body": "Fix a bug",
        "diff_text": "@@ -1 +1 @@\n-old\n+new\n",
        "files": [{"path": "app.py", "additions": 1, "deletions": 1}],
        "issue_comments": [],
        "reviews": [],
        "inline_review_comments": [],
    }


def _benchmark_row(status: str = "ok") -> dict:
    return {
        "status": status,
        "pr_number": 101,
        "pr_title": "Example PR",
        "pr_url": "https://example.com/pr/101",
        "merged": True,
        "file_count": 1,
        "reference_comment_count": 0,
        "reviewer_model": "gpt-reviewer",
        "grader_model": "gpt-grader",
        "reviewer_summary": "summary" if status == "ok" else "",
        "reviewer_comments": [],
        "reviewer_comment_count": 0,
        "grader_correctness": 1 if status == "ok" else 0,
        "grader_usefulness": 1 if status == "ok" else 0,
        "grader_noise": 1 if status == "ok" else 0,
        "grader_overall_pass": 1 if status == "ok" else 0,
        "grader_reason": "good" if status == "ok" else "",
        "error_message": "" if status == "ok" else "boom",
    }


class OptimizerTests(unittest.TestCase):
    def test_pointwise_benchmark_fingerprint_changes_for_relevant_inputs(self) -> None:
        snapshots = [_snapshot()]
        base_kwargs = {
            "cache_key": "openai_codex",
            "snapshots": snapshots,
            "reviewer_model": "gpt-reviewer",
            "grader_model": "gpt-grader",
            "reviewer_reasoning_effort": "minimal",
            "grader_reasoning_effort": "minimal",
            "reviewer_max_output_tokens": 1000,
            "grader_max_output_tokens": 200,
            "reviewer_system": "reviewer system",
            "agents_md": "agents",
            "grader_system": "grader system",
            "review_schema": {"type": "object"},
            "benchmark_schema": {"type": "object"},
        }
        baseline = optimizer._build_pointwise_benchmark_fingerprint(**base_kwargs)
        self.assertEqual(baseline, optimizer._build_pointwise_benchmark_fingerprint(**base_kwargs))

        variants = [
            dict(base_kwargs, agents_md="agents changed"),
            dict(base_kwargs, reviewer_system="reviewer system changed"),
            dict(base_kwargs, grader_system="grader system changed"),
            dict(base_kwargs, reviewer_model="gpt-reviewer-2"),
            dict(base_kwargs, grader_model="gpt-grader-2"),
            dict(base_kwargs, reviewer_reasoning_effort="low"),
            dict(base_kwargs, grader_reasoning_effort="low"),
            dict(base_kwargs, reviewer_max_output_tokens=900),
            dict(base_kwargs, grader_max_output_tokens=150),
            dict(base_kwargs, snapshots=[_snapshot(number=202, title="Different PR")]),
        ]
        for variant in variants:
            self.assertNotEqual(baseline, optimizer._build_pointwise_benchmark_fingerprint(**variant))

    @mock.patch("codereview_evals.optimizer._run_optimizer_benchmark_snapshot")
    def test_pointwise_benchmark_cache_hit_bypasses_model_calls(self, mock_snapshot_run: mock.Mock) -> None:
        mock_snapshot_run.return_value = _benchmark_row()
        config = optimizer.OptimizationConfig(
            model="gpt-reviewer",
            grader_model="gpt-grader",
            optimizer_model="gpt-optimizer",
            max_steps=1,
            score_threshold=0.8,
            pairwise_weight=0.5,
            benchmark_weight=0.5,
            benchmark_guardrail=0.03,
        )
        snapshots = [_snapshot()]
        with tempfile.TemporaryDirectory() as tmp_dir:
            cache_root = Path(tmp_dir) / "data" / "cache" / "github"
            first = optimizer._run_pointwise_benchmark(
                snapshots=snapshots,
                cache_key="openai_codex",
                cache_root=cache_root,
                client=object(),
                reviewer_model="gpt-reviewer",
                grader_model="gpt-grader",
                reviewer_system="reviewer system",
                agents_md="agents",
                grader_system="grader system",
                review_schema={"type": "object"},
                benchmark_schema={"type": "object"},
                progress_callback=None,
                progress_prefix="[benchmark]",
                config=config,
                enable_cache=True,
            )
            self.assertFalse(first.cache_hit)
            self.assertEqual(mock_snapshot_run.call_count, 1)

            mock_snapshot_run.reset_mock()
            second = optimizer._run_pointwise_benchmark(
                snapshots=snapshots,
                cache_key="openai_codex",
                cache_root=cache_root,
                client=object(),
                reviewer_model="gpt-reviewer",
                grader_model="gpt-grader",
                reviewer_system="reviewer system",
                agents_md="agents",
                grader_system="grader system",
                review_schema={"type": "object"},
                benchmark_schema={"type": "object"},
                progress_callback=None,
                progress_prefix="[benchmark]",
                config=config,
                enable_cache=True,
            )
            self.assertTrue(second.cache_hit)
            self.assertEqual(mock_snapshot_run.call_count, 0)
            self.assertEqual(first.results, second.results)
            self.assertEqual(first.summary, second.summary)
            self.assertEqual(first.fingerprint, second.fingerprint)

    @mock.patch("codereview_evals.optimizer._run_optimizer_benchmark_snapshot")
    def test_failed_pointwise_benchmark_does_not_populate_cache(self, mock_snapshot_run: mock.Mock) -> None:
        mock_snapshot_run.return_value = _benchmark_row(status="failed")
        config = optimizer.OptimizationConfig(
            model="gpt-reviewer",
            grader_model="gpt-grader",
            optimizer_model="gpt-optimizer",
            max_steps=1,
            score_threshold=0.8,
            pairwise_weight=0.5,
            benchmark_weight=0.5,
            benchmark_guardrail=0.03,
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            cache_root = Path(tmp_dir) / "data" / "cache" / "github"
            first = optimizer._run_pointwise_benchmark(
                snapshots=[_snapshot()],
                cache_key="openai_codex",
                cache_root=cache_root,
                client=object(),
                reviewer_model="gpt-reviewer",
                grader_model="gpt-grader",
                reviewer_system="reviewer system",
                agents_md="agents",
                grader_system="grader system",
                review_schema={"type": "object"},
                benchmark_schema={"type": "object"},
                progress_callback=None,
                progress_prefix="[benchmark]",
                config=config,
                enable_cache=True,
            )
            self.assertFalse(first.cache_hit)

            second = optimizer._run_pointwise_benchmark(
                snapshots=[_snapshot()],
                cache_key="openai_codex",
                cache_root=cache_root,
                client=object(),
                reviewer_model="gpt-reviewer",
                grader_model="gpt-grader",
                reviewer_system="reviewer system",
                agents_md="agents",
                grader_system="grader system",
                review_schema={"type": "object"},
                benchmark_schema={"type": "object"},
                progress_callback=None,
                progress_prefix="[benchmark]",
                config=config,
                enable_cache=True,
            )
            self.assertFalse(second.cache_hit)
            self.assertEqual(mock_snapshot_run.call_count, 2)

    @mock.patch("codereview_evals.optimizer._run_optimizer_benchmark_snapshot")
    def test_disable_pointwise_benchmark_cache_forces_recompute(self, mock_snapshot_run: mock.Mock) -> None:
        mock_snapshot_run.return_value = _benchmark_row()
        config = optimizer.OptimizationConfig(
            model="gpt-reviewer",
            grader_model="gpt-grader",
            optimizer_model="gpt-optimizer",
            max_steps=1,
            score_threshold=0.8,
            pairwise_weight=0.5,
            benchmark_weight=0.5,
            benchmark_guardrail=0.03,
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            cache_root = Path(tmp_dir) / "data" / "cache" / "github"
            optimizer._run_pointwise_benchmark(
                snapshots=[_snapshot()],
                cache_key="openai_codex",
                cache_root=cache_root,
                client=object(),
                reviewer_model="gpt-reviewer",
                grader_model="gpt-grader",
                reviewer_system="reviewer system",
                agents_md="agents",
                grader_system="grader system",
                review_schema={"type": "object"},
                benchmark_schema={"type": "object"},
                progress_callback=None,
                progress_prefix="[benchmark]",
                config=config,
                enable_cache=True,
            )

            mock_snapshot_run.reset_mock()
            second = optimizer._run_pointwise_benchmark(
                snapshots=[_snapshot()],
                cache_key="openai_codex",
                cache_root=cache_root,
                client=object(),
                reviewer_model="gpt-reviewer",
                grader_model="gpt-grader",
                reviewer_system="reviewer system",
                agents_md="agents",
                grader_system="grader system",
                review_schema={"type": "object"},
                benchmark_schema={"type": "object"},
                progress_callback=None,
                progress_prefix="[benchmark]",
                config=config,
                enable_cache=False,
            )
            self.assertFalse(second.cache_hit)
            self.assertEqual(mock_snapshot_run.call_count, 1)

    @mock.patch("codereview_evals.optimizer._run_optimizer_pairwise_snapshot")
    @mock.patch("codereview_evals.optimizer._run_optimizer_benchmark_snapshot")
    @mock.patch("codereview_evals.optimizer.load_cached_pull_requests")
    @mock.patch("codereview_evals.optimizer._build_openai_client")
    def test_run_optimizer_cache_hit_still_writes_step_artifacts(
        self,
        mock_build_client: mock.Mock,
        mock_load_cached_pull_requests: mock.Mock,
        mock_benchmark_snapshot: mock.Mock,
        mock_pairwise_snapshot: mock.Mock,
    ) -> None:
        mock_build_client.return_value = object()
        mock_load_cached_pull_requests.return_value = [_snapshot()]
        mock_benchmark_snapshot.return_value = _benchmark_row()
        mock_pairwise_snapshot.return_value = {
            "status": "ok",
            "pr_number": 101,
            "pr_title": "Example PR",
            "pr_url": "https://example.com/pr/101",
            "merged": True,
            "reviewer_model": "gpt-reviewer",
            "grader_model": "gpt-grader",
            "baseline_summary": "baseline",
            "baseline_comments": [],
            "baseline_comment_count": 0,
            "candidate_summary": "candidate",
            "candidate_comments": [],
            "candidate_comment_count": 0,
            "winner": "candidate",
            "judge_confidence": 0.9,
            "judge_reason": "candidate better",
            "error_message": "",
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            harness_src = ROOT_DIR / "3_optimization_harness"
            harness_dir = root / "3_optimization_harness"
            shutil.copytree(harness_src, harness_dir)
            cache_root = root / "data" / "cache" / "github"

            optimizer.run_optimizer(
                cache_key="openai_codex",
                max_prs=1,
                run_name="first-run",
                cache_root=cache_root,
                harness_dir=harness_dir,
                max_steps=1,
                score_threshold=0.8,
                enable_benchmark_cache=True,
            )
            first_benchmark_calls = mock_benchmark_snapshot.call_count
            self.assertGreater(first_benchmark_calls, 0)

            mock_benchmark_snapshot.reset_mock()
            artifacts, summary = optimizer.run_optimizer(
                cache_key="openai_codex",
                max_prs=1,
                run_name="second-run",
                cache_root=cache_root,
                harness_dir=harness_dir,
                max_steps=1,
                score_threshold=0.8,
                enable_benchmark_cache=True,
            )

            self.assertEqual(mock_benchmark_snapshot.call_count, 0)
            self.assertTrue(summary["baseline_benchmark_cache_hit"])
            step_dir = artifacts.run_dir / "steps" / "step_01"
            self.assertTrue((step_dir / "benchmark_results.json").exists())
            self.assertTrue((step_dir / "benchmark_summary.json").exists())
            self.assertTrue((step_dir / "benchmark_report.html").exists())


if __name__ == "__main__":
    unittest.main()
