from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from codereview_evals.reporting import render_report_for_run, write_results


class ReportingTests(unittest.TestCase):
    def test_write_results_and_render_report(self) -> None:
        results = [
            {
                "status": "ok",
                "pr_number": 1,
                "pr_title": "Fix bug",
                "pr_url": "https://example.com/pr/1",
                "merged": True,
                "reviewer_summary": "Found one important issue.",
                "reviewer_comments": [
                    {
                        "path": "app.py",
                        "line": 12,
                        "severity": "high",
                        "category": "correctness",
                        "claim": "Nil value can crash here.",
                        "suggestion": "Guard the access.",
                        "confidence": 0.9,
                    }
                ],
                "grader_correctness": 1,
                "grader_usefulness": 1,
                "grader_noise": 1,
                "grader_overall_pass": 1,
                "grader_reason": "Grounded and useful.",
                "error_message": "",
            },
            {
                "status": "failed",
                "pr_number": 2,
                "pr_title": "Add feature",
                "pr_url": "https://example.com/pr/2",
                "merged": False,
                "reviewer_summary": "",
                "reviewer_comments": [],
                "grader_correctness": 0,
                "grader_usefulness": 0,
                "grader_noise": 0,
                "grader_overall_pass": 0,
                "grader_reason": "",
                "error_message": "boom",
            },
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            run_dir = Path(tmp_dir) / "run"
            artifacts, summary = write_results(
                run_dir=run_dir,
                results=results,
                report_title="Test Report",
            )

            self.assertEqual(summary["total_examples"], 2)
            self.assertEqual(summary["successful_examples"], 1)
            self.assertAlmostEqual(summary["pass_rate"], 1.0)
            self.assertTrue(artifacts.report_html.exists())

            report_path = render_report_for_run(run_dir=run_dir, report_title="Test Report")
            self.assertEqual(report_path, artifacts.report_html)
            html = report_path.read_text(encoding="utf-8")
            self.assertIn("Fix bug", html)
            self.assertIn("Grounded and useful.", html)

            parsed_results = json.loads(artifacts.results_json.read_text(encoding="utf-8"))
            self.assertEqual(len(parsed_results), 2)


if __name__ == "__main__":
    unittest.main()
