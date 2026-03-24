from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from codereview_evals.github_cache import (
    benchmark_metadata,
    cache_dir_for,
    fetch_pull_requests,
    load_cached_pull_requests,
    repo_to_cache_key,
    save_pull_request_snapshot,
    write_manifest,
)


class GithubCacheTests(unittest.TestCase):
    def test_repo_to_cache_key(self) -> None:
        self.assertEqual(repo_to_cache_key("openai/codex"), "openai_codex")

    def test_load_cached_pull_requests_from_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cache_root = Path(tmp_dir)
            cache_dir = cache_dir_for(cache_root, "openai_codex")
            cache_dir.mkdir(parents=True, exist_ok=True)

            save_pull_request_snapshot(
                cache_dir,
                {
                    "number": 101,
                    "title": "Cached PR",
                    "url": "https://example.com/pr/101",
                    "files": [],
                },
            )
            write_manifest(
                cache_dir,
                {
                    "cache_key": "openai_codex",
                    "pull_request_numbers": [101],
                },
            )

            snapshots = load_cached_pull_requests(cache_root, cache_key="openai_codex")
            self.assertEqual(len(snapshots), 1)
            self.assertEqual(snapshots[0]["number"], 101)

    def test_fetch_pull_requests_reports_progress(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cache_root = Path(tmp_dir)
            progress_messages: list[str] = []

            from unittest.mock import patch

            def fake_run_gh_json(args: list[str]) -> object:
                if args[:2] == ["pr", "list"]:
                    return [{"number": 101}, {"number": 102}]
                if args[:2] == ["pr", "view"]:
                    number = int(args[2])
                    return {
                        "number": number,
                        "title": f"PR {number}",
                        "url": f"https://example.com/pr/{number}",
                        "state": "MERGED",
                        "files": [],
                        "reviews": [],
                        "comments": [],
                    }
                if args[:2] == ["api", "repos/example/repo/pulls/101/comments"]:
                    return []
                if args[:2] == ["api", "repos/example/repo/pulls/102/comments"]:
                    return []
                raise AssertionError(f"Unexpected JSON args: {args}")

            def fake_run_gh_text(args: list[str]) -> str:
                if args[:3] == ["pr", "diff", "101"] or args[:3] == ["pr", "diff", "102"]:
                    return "diff --git a/file.py b/file.py"
                raise AssertionError(f"Unexpected text args: {args}")

            with patch("codereview_evals.github_cache._run_gh_json", side_effect=fake_run_gh_json):
                with patch(
                    "codereview_evals.github_cache._run_gh_text",
                    side_effect=fake_run_gh_text,
                ):
                    _, manifest = fetch_pull_requests(
                        repo="example/repo",
                        limit=2,
                        cache_key="example_repo",
                        cache_root=cache_root,
                        progress_callback=progress_messages.append,
                    )

            self.assertEqual(manifest["fetched_count"], 2)
            self.assertEqual(
                progress_messages,
                [
                    "Scanning closed pull requests for 2 benchmark-eligible PRs from example/repo.",
                    "[1/2] Fetching PR #101...",
                    "[1/2] Saved PR #101.",
                    "[1/2] Accepted PR #101 (1/2).",
                    "[2/2] Fetching PR #102...",
                    "[2/2] Saved PR #102.",
                    "[2/2] Accepted PR #102 (2/2).",
                ],
            )

    def test_benchmark_metadata_marks_docs_only_pr_as_trivial_low_risk(self) -> None:
        snapshot = {
            "number": 101,
            "files": [{"path": "docs/guide.md", "additions": 5, "deletions": 0}],
            "issue_comments": [],
            "reviews": [],
            "inline_review_comments": [],
        }

        metadata = benchmark_metadata(snapshot)

        self.assertEqual(metadata["pr_class"], "trivial_low_risk")
        self.assertFalse(metadata["eligible"])
        self.assertEqual(metadata["exclusion_reasons"], ["trivial_low_risk"])

    def test_fetch_pull_requests_skips_low_risk_prs_until_limit_is_satisfied(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cache_root = Path(tmp_dir)

            from unittest.mock import patch

            def fake_run_gh_json(args: list[str]) -> object:
                if args[:2] == ["pr", "list"]:
                    return [{"number": 201}, {"number": 202}, {"number": 203}]
                if args[:2] == ["pr", "view"]:
                    number = int(args[2])
                    files = (
                        [{"path": "docs/guide.md", "additions": 5, "deletions": 0}]
                        if number == 202
                        else [{"path": "src/app.py", "additions": 5, "deletions": 1}]
                    )
                    return {
                        "number": number,
                        "title": f"PR {number}",
                        "url": f"https://example.com/pr/{number}",
                        "state": "MERGED",
                        "files": files,
                        "reviews": [],
                        "comments": [],
                    }
                if args[:2] == ["api", "repos/example/repo/pulls/201/comments"]:
                    return []
                if args[:2] == ["api", "repos/example/repo/pulls/202/comments"]:
                    return []
                if args[:2] == ["api", "repos/example/repo/pulls/203/comments"]:
                    return []
                raise AssertionError(f"Unexpected JSON args: {args}")

            def fake_run_gh_text(args: list[str]) -> str:
                if args[:2] == ["pr", "diff"]:
                    return "diff --git a/file.py b/file.py"
                raise AssertionError(f"Unexpected text args: {args}")

            with patch("codereview_evals.github_cache._run_gh_json", side_effect=fake_run_gh_json):
                with patch(
                    "codereview_evals.github_cache._run_gh_text",
                    side_effect=fake_run_gh_text,
                ):
                    _, manifest = fetch_pull_requests(
                        repo="example/repo",
                        limit=2,
                        cache_key="example_repo",
                        cache_root=cache_root,
                    )

            self.assertEqual(manifest["pull_request_numbers"], [201, 203])
            self.assertEqual(manifest["pull_request_count"], 2)
            self.assertEqual(manifest["scanned_count"], 3)
            self.assertEqual(manifest["excluded_reasons"], {"trivial_low_risk": 1})


if __name__ == "__main__":
    unittest.main()
