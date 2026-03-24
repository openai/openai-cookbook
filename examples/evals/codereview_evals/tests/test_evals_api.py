from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from codereview_evals.evals_api import run_evals


class _FakeObject:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def model_dump(self, mode: str = "json") -> dict:
        return self._payload


class _FakePage:
    def __init__(self, payloads: list[dict], *, has_more: bool = False) -> None:
        self.data = [_FakeObject(payload) for payload in payloads]
        self.has_more = has_more


class _FakeOutputItems:
    def __init__(self, payloads: list[dict]) -> None:
        self._payloads = payloads

    def list(self, **_kwargs) -> _FakePage:
        return _FakePage(self._payloads)


class _FakeRuns:
    def __init__(self, run_payload: dict, output_items: list[dict]) -> None:
        self._run_payload = run_payload
        self.output_items = _FakeOutputItems(output_items)

    def create(self, _eval_id: str, **_kwargs) -> _FakeObject:
        return _FakeObject({"id": self._run_payload["id"], "status": "queued"})

    def retrieve(self, **_kwargs) -> _FakeObject:
        return _FakeObject(self._run_payload)


class _FakeEvals:
    def __init__(self, eval_payload: dict, run_payload: dict, output_items: list[dict]) -> None:
        self._eval_payload = eval_payload
        self.runs = _FakeRuns(run_payload, output_items)

    def list(self, **_kwargs) -> _FakePage:
        return _FakePage([self._eval_payload])

    def create(self, **_kwargs) -> _FakeObject:
        return _FakeObject(self._eval_payload)


class _FakeFiles:
    def create(self, **_kwargs) -> _FakeObject:
        return _FakeObject({"id": "file_123"})


class _FakeClient:
    def __init__(self, eval_payload: dict, run_payload: dict, output_items: list[dict]) -> None:
        self.files = _FakeFiles()
        self.evals = _FakeEvals(eval_payload, run_payload, output_items)


class EvalsApiTests(unittest.TestCase):
    def test_run_evals_level_1_writes_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            dataset_path = Path(tmp_dir) / "benchmark.jsonl"
            dataset_path.write_text(json.dumps({"item": {"pr_number": 1}}) + "\n", encoding="utf-8")
            client = _FakeClient(
                {"id": "eval_1", "name": "code-review-evals-level-1"},
                {
                    "id": "run_1",
                    "eval_id": "eval_1",
                    "status": "completed",
                    "report_url": "https://example.com/run_1",
                    "result_counts": {"total": 1, "passed": 1, "failed": 0, "errored": 0},
                    "per_testing_criteria_results": [],
                },
                [
                    {
                        "id": "output_1",
                        "status": "pass",
                        "datasource_item": {"merged": True},
                        "results": [
                            {"name": "Correctness", "passed": True},
                            {"name": "Usefulness", "passed": True},
                            {"name": "Noise", "passed": True},
                            {"name": "Overall pass", "passed": True},
                        ],
                        "sample": {"output": [{"content": "Review text"}]},
                    }
                ],
            )

            artifacts, summary = run_evals(
                level=1,
                cache_key="openai_codex",
                dataset_path=dataset_path,
                client=client,
                run_name="test-run-level-1",
                poll_interval_seconds=0,
            )

            self.assertEqual(summary["overall_pass_rate"], 1.0)
            self.assertEqual(summary["merged_pass_rate"], 1.0)
            self.assertTrue(artifacts.summary_json.exists())

    def test_run_evals_level_3_extracts_pairwise_winner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            dataset_path = Path(tmp_dir) / "pairwise.jsonl"
            dataset_path.write_text(json.dumps({"item": {"pr_number": 1}}) + "\n", encoding="utf-8")
            client = _FakeClient(
                {"id": "eval_3", "name": "code-review-evals-level-3"},
                {
                    "id": "run_3",
                    "eval_id": "eval_3",
                    "status": "completed",
                    "report_url": "https://example.com/run_3",
                    "result_counts": {"total": 1, "passed": 1, "failed": 0, "errored": 0},
                    "per_testing_criteria_results": [],
                },
                [
                    {
                        "id": "output_3",
                        "status": "pass",
                        "datasource_item": {"merged": False},
                        "results": [],
                        "sample": {"output": [{"content": "candidate"}]},
                    }
                ],
            )

            _artifacts, summary = run_evals(
                level=3,
                cache_key="openai_codex",
                dataset_path=dataset_path,
                client=client,
                run_name="test-run-level-3",
                poll_interval_seconds=0,
            )

            self.assertEqual(summary["winner_counts"]["candidate"], 1)
            self.assertEqual(summary["candidate_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
