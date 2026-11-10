"""Offline checks: python -m unittest discover -s examples/gpt-5/prompt-optimization-cookbook/tests."""

import contextlib
import csv
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "topk_eval.py"
SPEC = importlib.util.spec_from_file_location("topk_eval", MODULE_PATH)
topk_eval = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(topk_eval)

COUNT_TOKENS = """\
from collections import Counter
counts = Counter(text.split())
pairs = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))[:k]
"""


class TopKEvaluationTests(unittest.TestCase):
    def evaluate_submission(self, source):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / "run.py").write_text(source, encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                summary = topk_eval.evaluate_folder(directory, k=5, scale_tokens=1)
            csv_path = Path(summary["csv"])
            with csv_path.open(newline="") as handle:
                rows = list(csv.DictReader(handle))
            saved_summary = json.loads(
                csv_path.with_name(csv_path.stem + "_summary.json").read_text()
            )
        self.assertEqual(summary, saved_summary)
        self.assertEqual(summary["total_runs"], 1)
        self.assertEqual(summary["successes"], 1)
        self.assertEqual(summary["violations"], 0)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Compiled"], "True")
        return summary, rows[0]

    def test_fractional_namespace_counts_are_not_exact(self):
        summary, row = self.evaluate_submission(
            COUNT_TOKENS + "top_k = [(token, count + 0.5) for token, count in pairs]\n"
        )
        self.assertEqual(summary["exact_matches"], 0)
        self.assertEqual(row["Exact Match"], "False")
        self.assertIn("5000.5", row["Reported Top-K (first 5)"])

    def test_fractional_stdout_counts_are_not_exact(self):
        summary, row = self.evaluate_submission(
            COUNT_TOKENS + "print([(token, count + 0.5) for token, count in pairs])\n"
        )
        self.assertEqual(summary["exact_matches"], 0)
        self.assertEqual(row["Exact Match"], "False")
        self.assertIn("5000.5", row["Reported Top-K (first 5)"])

    def test_integer_namespace_counts_remain_exact(self):
        summary, row = self.evaluate_submission(COUNT_TOKENS + "top_k = pairs\n")
        self.assertEqual(summary["exact_matches"], 1)
        self.assertEqual(row["Exact Match"], "True")
        self.assertEqual(row["Sorted Correctly"], "True")
        self.assertEqual(row["Precision@K"], "1.000")

    def test_integral_float_stdout_counts_remain_exact(self):
        summary, row = self.evaluate_submission(
            COUNT_TOKENS + "print([(token, float(count)) for token, count in pairs])\n"
        )
        self.assertEqual(summary["exact_matches"], 1)
        self.assertEqual(row["Exact Match"], "True")

    def test_wrong_integer_counts_remain_inexact(self):
        summary, row = self.evaluate_submission(
            COUNT_TOKENS + "top_k = [(token, count + 1) for token, count in pairs]\n"
        )
        self.assertEqual(summary["exact_matches"], 0)
        self.assertEqual(row["Exact Match"], "False")

    def test_malformed_result_remains_inexact(self):
        summary, row = self.evaluate_submission("top_k = [('w0001', '5000')]\n")
        self.assertEqual(summary["exact_matches"], 0)
        self.assertEqual(row["Exact Match"], "False")


if __name__ == "__main__":
    unittest.main()
