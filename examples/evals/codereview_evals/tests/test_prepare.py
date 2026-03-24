from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from codereview_evals.github_cache import cache_dir_for, save_pull_request_snapshot, write_manifest
from codereview_evals.prepare import prepare_dataset


def _snapshot(number: int = 101) -> dict:
    return {
        "repository": "openai/codex",
        "number": number,
        "title": f"Example PR {number}",
        "url": f"https://example.com/pr/{number}",
        "merged": True,
        "body": "Fix a bug in the request path.",
        "files": [{"path": "app.py", "additions": 10, "deletions": 2}],
        "diff_text": "@@ -1 +1 @@\n-old\n+new\n",
        "issue_comments": [],
        "reviews": [{"id": 1, "author_login": "alice", "body": "Please add a guard.", "submitted_at": "2025-01-01T00:00:00Z", "source": "review"}],
        "inline_review_comments": [],
    }


class PrepareDatasetTests(unittest.TestCase):
    def _write_cache(self, cache_root: Path, cache_key: str, snapshots: list[dict]) -> None:
        cache_dir = cache_dir_for(cache_root, cache_key)
        cache_dir.mkdir(parents=True, exist_ok=True)
        for snapshot in snapshots:
            save_pull_request_snapshot(cache_dir, snapshot)
        write_manifest(
            cache_dir,
            {
                "cache_key": cache_key,
                "pull_request_numbers": [snapshot["number"] for snapshot in snapshots],
            },
        )

    def test_level_1_prepares_raw_benchmark_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            cache_root = root / "cache"
            prepared_root = root / "prepared"
            self._write_cache(cache_root, "openai_codex", [_snapshot()])

            artifacts, summary = prepare_dataset(
                level=1,
                cache_key="openai_codex",
                cache_root=cache_root,
                prepared_root=prepared_root,
            )

            self.assertEqual(summary["record_count"], 1)
            row = json.loads(artifacts.dataset_path.read_text(encoding="utf-8").splitlines()[0])
            item = row["item"]
            self.assertEqual(item["pr_number"], 101)
            self.assertIn("Changed files:", item["review_input_text"])
            self.assertIn("Please add a guard.", item["reference_comments_text"])

    def test_level_1_accepts_opaque_github_comment_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            cache_root = root / "cache"
            prepared_root = root / "prepared"
            snapshot = _snapshot()
            snapshot["reviews"] = [
                {
                    "id": "IC_kwDOOYsS4c71a3Vu",
                    "author_login": "alice",
                    "body": "Please add a guard.",
                    "submitted_at": "2025-01-01T00:00:00Z",
                    "source": "review",
                }
            ]
            self._write_cache(cache_root, "openai_codex", [snapshot])

            artifacts, summary = prepare_dataset(
                level=1,
                cache_key="openai_codex",
                cache_root=cache_root,
                prepared_root=prepared_root,
            )

            self.assertEqual(summary["record_count"], 1)
            row = json.loads(artifacts.dataset_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertIn("Please add a guard.", row["item"]["reference_comments_text"])

    def test_level_2_reuses_cached_pr_brief(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            cache_root = root / "cache"
            prepared_root = root / "prepared"
            self._write_cache(cache_root, "openai_codex", [_snapshot()])
            brief_path = prepared_root / "openai_codex" / "shared" / "pr_briefs" / "101.txt"
            brief_path.parent.mkdir(parents=True, exist_ok=True)
            brief_path.write_text("Stable PR brief\n", encoding="utf-8")

            artifacts, _summary = prepare_dataset(
                level=2,
                cache_key="openai_codex",
                cache_root=cache_root,
                prepared_root=prepared_root,
            )

            row = json.loads(artifacts.dataset_path.read_text(encoding="utf-8").splitlines()[0])
            item = row["item"]
            self.assertEqual(item["pr_brief"], "Stable PR brief")
            self.assertIn("PR brief:", item["normalized_review_input_text"])

    def test_level_3_reuses_cached_brief_and_reviews(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            cache_root = root / "cache"
            prepared_root = root / "prepared"
            self._write_cache(cache_root, "openai_codex", [_snapshot()])

            brief_path = prepared_root / "openai_codex" / "shared" / "pr_briefs" / "101.txt"
            brief_path.parent.mkdir(parents=True, exist_ok=True)
            brief_path.write_text("Stable PR brief\n", encoding="utf-8")

            baseline_path = prepared_root / "openai_codex" / "level_3" / "generated_reviews" / "baseline" / "101.md"
            baseline_path.parent.mkdir(parents=True, exist_ok=True)
            baseline_path.write_text("Baseline review\n", encoding="utf-8")

            candidate_path = prepared_root / "openai_codex" / "level_3" / "generated_reviews" / "candidate" / "101.md"
            candidate_path.parent.mkdir(parents=True, exist_ok=True)
            candidate_path.write_text("Candidate review\n", encoding="utf-8")

            artifacts, _summary = prepare_dataset(
                level=3,
                cache_key="openai_codex",
                cache_root=cache_root,
                prepared_root=prepared_root,
            )

            row = json.loads(artifacts.dataset_path.read_text(encoding="utf-8").splitlines()[0])
            item = row["item"]
            self.assertEqual(item["baseline_review"], "Baseline review\n")
            self.assertEqual(item["candidate_review"], "Candidate review\n")
            self.assertIn("Choose baseline, candidate, or tie.", item["pairwise_input_text"])


if __name__ == "__main__":
    unittest.main()
