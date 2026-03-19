from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .types import JSONDict

DEFAULT_CACHE_ROOT = Path(__file__).resolve().parents[1] / "data" / "cache" / "github"


def repo_to_cache_key(repo: str) -> str:
    return repo.replace("/", "_").replace("-", "_")


def cache_dir_for(cache_root: Path, cache_key: str) -> Path:
    return cache_root / cache_key


def write_manifest(cache_dir: Path, manifest: JSONDict) -> Path:
    manifest_path = cache_dir / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def save_pull_request_snapshot(cache_dir: Path, snapshot: JSONDict) -> Path:
    prs_dir = cache_dir / "prs"
    prs_dir.mkdir(parents=True, exist_ok=True)
    path = prs_dir / f"{snapshot['number']}.json"
    path.write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def load_cached_pull_requests(
    cache_root: Path = DEFAULT_CACHE_ROOT,
    *,
    cache_key: str,
) -> list[JSONDict]:
    cache_dir = cache_dir_for(cache_root, cache_key)
    manifest_path = cache_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"No cache manifest found for {cache_key!r} at {manifest_path}."
        )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    snapshots: list[JSONDict] = []
    for number in manifest.get("pull_request_numbers", []):
        pr_path = cache_dir / "prs" / f"{number}.json"
        if pr_path.exists():
            snapshots.append(json.loads(pr_path.read_text(encoding="utf-8")))
    return snapshots


def fetch_pull_requests(
    *,
    repo: str,
    limit: int,
    cache_key: str | None = None,
    refresh: bool = False,
    cache_root: Path = DEFAULT_CACHE_ROOT,
    progress_callback: Callable[[str], None] | None = None,
) -> tuple[Path, JSONDict]:
    key = cache_key or repo_to_cache_key(repo)
    cache_dir = cache_dir_for(cache_root, key)
    prs_dir = cache_dir / "prs"
    prs_dir.mkdir(parents=True, exist_ok=True)

    listing = _run_gh_json(
        [
            "pr",
            "list",
            "-R",
            repo,
            "--state",
            "closed",
            "--limit",
            str(limit),
            "--json",
            "number,title,url",
        ]
    )
    pull_requests = listing if isinstance(listing, list) else []
    if progress_callback:
        progress_callback(
            f"Found {len(pull_requests)} pull requests to process for {repo}."
        )

    fetched = 0
    reused = 0
    numbers: list[int] = []
    total = len(pull_requests)
    for index, item in enumerate(pull_requests, start=1):
        number = int(item["number"])
        numbers.append(number)
        snapshot_path = prs_dir / f"{number}.json"
        if snapshot_path.exists() and not refresh:
            reused += 1
            if progress_callback:
                progress_callback(
                    f"[{index}/{total}] Reusing cached PR #{number}."
                )
            continue

        if progress_callback:
            progress_callback(f"[{index}/{total}] Fetching PR #{number}...")
        snapshot = _fetch_single_pull_request(repo=repo, number=number, cache_key=key)
        save_pull_request_snapshot(cache_dir, snapshot)
        fetched += 1
        if progress_callback:
            progress_callback(f"[{index}/{total}] Saved PR #{number}.")

    manifest: JSONDict = {
        "cache_key": key,
        "repository": repo,
        "limit": limit,
        "pull_request_numbers": numbers,
        "pull_request_count": len(numbers),
        "fetched_count": fetched,
        "reused_count": reused,
        "refreshed": refresh,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    write_manifest(cache_dir, manifest)
    return cache_dir, manifest


def _fetch_single_pull_request(*, repo: str, number: int, cache_key: str) -> JSONDict:
    view = _run_gh_json(
        [
            "pr",
            "view",
            str(number),
            "-R",
            repo,
            "--json",
            ",".join(
                [
                    "number",
                    "title",
                    "url",
                    "state",
                    "body",
                    "baseRefName",
                    "headRefName",
                    "mergedAt",
                    "closedAt",
                    "reviewDecision",
                    "files",
                    "reviews",
                    "comments",
                ]
            ),
        ]
    )
    inline_comments = _run_gh_json([ "api", f"repos/{repo}/pulls/{number}/comments" ])
    diff_text = _run_gh_text(["pr", "diff", str(number), "-R", repo, "--patch"])

    return {
        "cache_key": cache_key,
        "repository": repo,
        "number": number,
        "title": view.get("title", ""),
        "url": view.get("url", ""),
        "state": view.get("state", ""),
        "merged": bool(view.get("mergedAt")),
        "merged_at": view.get("mergedAt"),
        "closed_at": view.get("closedAt"),
        "body": view.get("body") or "",
        "base_ref_name": view.get("baseRefName", ""),
        "head_ref_name": view.get("headRefName", ""),
        "review_decision": view.get("reviewDecision") or "",
        "files": [
            {
                "path": file_info.get("path", ""),
                "additions": int(file_info.get("additions") or 0),
                "deletions": int(file_info.get("deletions") or 0),
            }
            for file_info in view.get("files", [])
        ],
        "diff_text": diff_text,
        "issue_comments": [_normalize_issue_comment(comment) for comment in view.get("comments", [])],
        "reviews": [_normalize_review(review) for review in view.get("reviews", [])],
        "inline_review_comments": [
            _normalize_inline_comment(comment) for comment in inline_comments or []
        ],
    }


def _normalize_issue_comment(comment: JSONDict) -> JSONDict:
    author = comment.get("author") or {}
    login = author.get("login", "")
    return {
        "id": comment.get("id"),
        "author_login": login,
        "author_association": comment.get("authorAssociation", ""),
        "body": comment.get("body") or "",
        "created_at": comment.get("createdAt"),
        "url": comment.get("url", ""),
        "is_bot": _is_probably_bot(login),
        "source": "issue_comment",
    }


def _normalize_review(review: JSONDict) -> JSONDict:
    author = review.get("author") or {}
    login = author.get("login", "")
    return {
        "id": review.get("id"),
        "author_login": login,
        "author_association": review.get("authorAssociation", ""),
        "body": review.get("body") or "",
        "state": review.get("state", ""),
        "submitted_at": review.get("submittedAt"),
        "is_bot": _is_probably_bot(login),
        "source": "review",
    }


def _normalize_inline_comment(comment: JSONDict) -> JSONDict:
    user = comment.get("user") or {}
    login = user.get("login", "")
    return {
        "id": comment.get("id"),
        "author_login": login,
        "author_association": comment.get("author_association", ""),
        "body": comment.get("body") or "",
        "path": comment.get("path", ""),
        "line": comment.get("line"),
        "start_line": comment.get("start_line"),
        "created_at": comment.get("created_at"),
        "url": comment.get("html_url", ""),
        "diff_hunk": comment.get("diff_hunk", ""),
        "is_bot": _is_probably_bot(login),
        "source": "inline_review_comment",
    }


def _is_probably_bot(login: str) -> bool:
    lowered = login.lower()
    return lowered.endswith("[bot]") or lowered.endswith("-bot") or lowered == "github-actions"


def _run_gh_json(args: list[str]) -> Any:
    output = _run_gh_text(args)
    if not output.strip():
        return None
    return json.loads(output)


def _run_gh_text(args: list[str]) -> str:
    command = ["gh", *args]
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        raise RuntimeError(f"`{' '.join(command)}` failed: {stderr or 'unknown error'}")
    return completed.stdout
