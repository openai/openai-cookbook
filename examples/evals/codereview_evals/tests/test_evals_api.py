from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import codereview_evals.evals_api as evals_api
from codereview_evals.evals_api import (
    _ensure_eval,
    _eval_spec_fingerprint,
    _versioned_eval_name,
    run_evals,
)


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
        self.create_calls: list[dict] = []

    def create(self, _eval_id: str, **_kwargs) -> _FakeObject:
        self.create_calls.append({"eval_id": _eval_id, **_kwargs})
        return _FakeObject({"id": self._run_payload["id"], "status": "queued"})

    def retrieve(self, **_kwargs) -> _FakeObject:
        return _FakeObject(self._run_payload)


class _FakeEvals:
    def __init__(self, eval_payloads: list[dict], run_payload: dict, output_items: list[dict]) -> None:
        self._eval_payloads = list(eval_payloads)
        self.runs = _FakeRuns(run_payload, output_items)
        self.create_calls: list[dict] = []

    def list(self, **_kwargs) -> _FakePage:
        return _FakePage(self._eval_payloads)

    def create(self, **_kwargs) -> _FakeObject:
        payload = {
            "id": f"created_eval_{len(self.create_calls) + 1}",
            "name": _kwargs["name"],
            "metadata": _kwargs.get("metadata"),
            "data_source_config": _kwargs.get("data_source_config"),
            "testing_criteria": _kwargs.get("testing_criteria"),
        }
        self.create_calls.append(_kwargs)
        self._eval_payloads.insert(0, payload)
        return _FakeObject(payload)


class _FakeFiles:
    def create(self, **_kwargs) -> _FakeObject:
        return _FakeObject({"id": "file_123"})


class _FakeClient:
    def __init__(self, eval_payloads: list[dict], run_payload: dict, output_items: list[dict]) -> None:
        self.files = _FakeFiles()
        self.evals = _FakeEvals(eval_payloads, run_payload, output_items)


class EvalsApiTests(unittest.TestCase):
    def test_run_evals_level_1_writes_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            dataset_path = Path(tmp_dir) / "benchmark.jsonl"
            dataset_path.write_text(json.dumps({"item": {"pr_number": 1}}) + "\n", encoding="utf-8")
            client = _FakeClient(
                [],
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
            self.assertTrue(summary["eval_name"].startswith("code-review-evals-level-1-"))
            self.assertRegex(summary["eval_spec_fingerprint"], r"^[0-9a-f]{12}$")
            self.assertTrue(artifacts.summary_json.exists())

    def test_run_evals_level_3_extracts_pairwise_winner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            dataset_path = Path(tmp_dir) / "pairwise.jsonl"
            dataset_path.write_text(json.dumps({"item": {"pr_number": 1}}) + "\n", encoding="utf-8")
            client = _FakeClient(
                [],
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
            self.assertTrue(summary["eval_name"].startswith("code-review-evals-level-3-"))

    def test_eval_spec_fingerprint_is_stable_for_key_order(self) -> None:
        spec_a = {
            "testing_criteria": [
                {
                    "name": "Correctness",
                    "model": "gpt-5.3-codex",
                    "labels": ["pass", "fail"],
                }
            ],
            "data_source_config": {
                "include_sample_schema": True,
                "type": "custom",
            },
        }
        spec_b = {
            "data_source_config": {
                "type": "custom",
                "include_sample_schema": True,
            },
            "testing_criteria": [
                {
                    "labels": ["pass", "fail"],
                    "model": "gpt-5.3-codex",
                    "name": "Correctness",
                }
            ],
        }

        self.assertEqual(_eval_spec_fingerprint(spec_a), _eval_spec_fingerprint(spec_b))

    def test_ensure_eval_reuses_matching_versioned_eval(self) -> None:
        spec = {
            "data_source_config": {"type": "custom", "include_sample_schema": True},
            "testing_criteria": [{"type": "label_model", "model": "grader-a"}],
        }
        fingerprint = _eval_spec_fingerprint(spec)
        eval_name = _versioned_eval_name(level=1, eval_spec_fingerprint=fingerprint)
        client = _FakeClient(
            [{"id": "eval_existing", "name": eval_name}],
            {"id": "run_unused", "eval_id": "eval_existing", "status": "completed"},
            [],
        )

        with patch.object(evals_api, "_build_eval_spec", return_value=spec):
            eval_obj, resolved_name, resolved_fingerprint = _ensure_eval(level=1, client=client)

        self.assertEqual(eval_obj["id"], "eval_existing")
        self.assertEqual(resolved_name, eval_name)
        self.assertEqual(resolved_fingerprint, fingerprint)
        self.assertEqual(client.evals.create_calls, [])

    def test_level_1_grader_model_change_creates_new_versioned_eval(self) -> None:
        with patch.object(evals_api, "_read_text", return_value="grader prompt"):
            with patch.object(evals_api, "_read_eval_config", return_value={"grader_model": "grader-a"}):
                stale_fingerprint = _eval_spec_fingerprint(evals_api._build_eval_spec(1))
            stale_name = _versioned_eval_name(level=1, eval_spec_fingerprint=stale_fingerprint)
            client = _FakeClient(
                [{"id": "eval_stale", "name": stale_name}],
                {"id": "run_unused", "eval_id": "eval_new", "status": "completed"},
                [],
            )
            with patch.object(evals_api, "_read_eval_config", return_value={"grader_model": "grader-b"}):
                eval_obj, resolved_name, resolved_fingerprint = _ensure_eval(level=1, client=client)

        self.assertEqual(eval_obj["id"], "created_eval_1")
        self.assertNotEqual(resolved_name, stale_name)
        self.assertNotEqual(resolved_fingerprint, stale_fingerprint)
        self.assertEqual(client.evals.create_calls[0]["name"], resolved_name)

    def test_level_3_judge_model_change_creates_new_versioned_eval(self) -> None:
        with patch.object(evals_api, "_read_text", return_value="judge prompt"):
            with patch.object(evals_api, "_read_eval_config", return_value={"judge_model": "judge-a"}):
                stale_fingerprint = _eval_spec_fingerprint(evals_api._build_eval_spec(3))
            stale_name = _versioned_eval_name(level=3, eval_spec_fingerprint=stale_fingerprint)
            client = _FakeClient(
                [{"id": "eval_stale", "name": stale_name}],
                {"id": "run_unused", "eval_id": "eval_new", "status": "completed"},
                [],
            )
            with patch.object(evals_api, "_read_eval_config", return_value={"judge_model": "judge-b"}):
                eval_obj, resolved_name, resolved_fingerprint = _ensure_eval(level=3, client=client)

        self.assertEqual(eval_obj["id"], "created_eval_1")
        self.assertNotEqual(resolved_name, stale_name)
        self.assertNotEqual(resolved_fingerprint, stale_fingerprint)
        self.assertEqual(client.evals.create_calls[0]["name"], resolved_name)

    def test_ensure_eval_ignores_legacy_unsuffixed_eval_name(self) -> None:
        client = _FakeClient(
            [{"id": "eval_legacy", "name": "code-review-evals-level-1"}],
            {"id": "run_unused", "eval_id": "eval_new", "status": "completed"},
            [],
        )

        eval_obj, resolved_name, _resolved_fingerprint = _ensure_eval(level=1, client=client)

        self.assertEqual(eval_obj["id"], "created_eval_1")
        self.assertEqual(client.evals.create_calls[0]["name"], resolved_name)
        self.assertNotEqual(resolved_name, "code-review-evals-level-1")
        self.assertTrue(resolved_name.startswith("code-review-evals-level-1-"))


if __name__ == "__main__":
    unittest.main()
