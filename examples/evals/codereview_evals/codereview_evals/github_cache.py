from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .types import JSONDict

DEFAULT_CACHE_ROOT = Path(__file__).resolve().parents[1] / "data" / "cache" / "github"
_BENCHMARK_POLICY_VERSION = 1
_KNOWN_AUTOMATED_LOGINS = {"chatgpt-codex-connector"}
_LOW_RISK_PATH_PARTS = (
    "docs/",
    "vendor/",
    "generated/",
    "snapshots/",
    "__snapshots__/",
)
_LOW_RISK_FILENAMES = {
    "cargo.lock",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "bun.lockb",
    "poetry.lock",
    "pipfile.lock",
    "uv.lock",
    "go.sum",
    "composer.lock",
}
_LOW_RISK_SUFFIXES = (".md", ".mdx", ".rst", ".txt", ".snap")
_TRIGGER_COMMENT_PATTERNS = (
    re.compile(r"^@codex\b(?:\s+\w+.*)?$", re.IGNORECASE),
    re.compile(r"^@chatgpt\b(?:\s+\w+.*)?$", re.IGNORECASE),
)
_APPROVAL_COMMENT_PATTERNS = (
    re.compile(r"^(lgtm|sgtm|ship it|approved?)\.?$", re.IGNORECASE),
    re.compile(r"^(looks good(?: to me)?|nice work|nice change)\.?$", re.IGNORECASE),
    re.compile(r"^(no(?:\s+\w+){0,3}\s+issues(?:\s+found)?|no blocking issues.*?)\.?$", re.IGNORECASE),
)
_TEMPLATE_COMMENT_SNIPPETS = (
    "About Codex in GitHub",
    "Your team has set up Codex to review pull requests in this repo",
)


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

    fetched = 0
    reused = 0
    scanned = 0
    excluded_reasons: dict[str, int] = {}
    numbers: list[int] = []
    seen_numbers: set[int] = set()
    list_limit = max(limit, min(max(limit * 3, limit + 25), 500))

    if progress_callback:
        progress_callback(
            f"Scanning closed pull requests for {limit} benchmark-eligible PRs from {repo}."
        )

    while len(numbers) < limit:
        listing = _run_gh_json(
            [
                "pr",
                "list",
                "-R",
                repo,
                "--state",
                "closed",
                "--limit",
                str(list_limit),
                "--json",
                "number,title,url",
            ]
        )
        pull_requests = listing if isinstance(listing, list) else []
        candidates = [
            item for item in pull_requests if int(item.get("number") or 0) not in seen_numbers
        ]
        if not candidates:
            break

        total = len(candidates)
        for index, item in enumerate(candidates, start=1):
            number = int(item["number"])
            seen_numbers.add(number)
            scanned += 1
            snapshot_path = prs_dir / f"{number}.json"
            if snapshot_path.exists() and not refresh:
                snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
                reused += 1
                action = "Reusing"
            else:
                if progress_callback:
                    progress_callback(f"[{index}/{total}] Fetching PR #{number}...")
                snapshot = _fetch_single_pull_request(repo=repo, number=number, cache_key=key)
                fetched += 1
                action = "Saved"

            benchmark = _benchmark_metadata(snapshot)
            if snapshot.get("benchmark") != benchmark:
                snapshot["benchmark"] = benchmark
                save_pull_request_snapshot(cache_dir, snapshot)
                if action == "Saved" and progress_callback:
                    progress_callback(f"[{index}/{total}] Saved PR #{number}.")
                elif action == "Reusing" and progress_callback:
                    progress_callback(f"[{index}/{total}] Reusing cached PR #{number}.")
            elif action == "Reusing" and progress_callback:
                progress_callback(f"[{index}/{total}] Reusing cached PR #{number}.")
            elif action == "Saved" and progress_callback:
                progress_callback(f"[{index}/{total}] Saved PR #{number}.")

            if benchmark.get("eligible"):
                numbers.append(number)
                if progress_callback:
                    progress_callback(
                        f"[{index}/{total}] Accepted PR #{number} ({len(numbers)}/{limit})."
                    )
                if len(numbers) >= limit:
                    break
            else:
                for reason in benchmark.get("exclusion_reasons") or ["unknown"]:
                    excluded_reasons[reason] = excluded_reasons.get(reason, 0) + 1
                if progress_callback:
                    reason_text = ", ".join(benchmark.get("exclusion_reasons") or ["unknown"])
                    progress_callback(
                        f"[{index}/{total}] Skipping PR #{number}: {reason_text}."
                    )

        if len(numbers) >= limit or len(pull_requests) < list_limit:
            break
        list_limit = min(list_limit * 2, 500)

    manifest: JSONDict = {
        "cache_key": key,
        "repository": repo,
        "limit": limit,
        "target_limit": limit,
        "pull_request_numbers": numbers,
        "pull_request_count": len(numbers),
        "fetched_count": fetched,
        "reused_count": reused,
        "scanned_count": scanned,
        "excluded_count": sum(excluded_reasons.values()),
        "excluded_reasons": excluded_reasons,
        "satisfied_limit": len(numbers) == limit,
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
    return (
        lowered.endswith("[bot]")
        or lowered.endswith("-bot")
        or lowered == "github-actions"
        or lowered in _KNOWN_AUTOMATED_LOGINS
    )


def benchmark_metadata(snapshot: JSONDict) -> JSONDict:
    return _benchmark_metadata(snapshot)


def iter_substantive_human_comments(snapshot: JSONDict) -> list[JSONDict]:
    comments: list[JSONDict] = []
    for source_key in ("issue_comments", "reviews", "inline_review_comments"):
        for comment in snapshot.get(source_key) or []:
            if _is_substantive_comment(comment):
                comments.append(comment)
    return comments


def _benchmark_metadata(snapshot: JSONDict) -> JSONDict:
    pr_class = _classify_pull_request(snapshot)
    eligible = pr_class == "substantive"
    exclusion_reasons = [] if eligible else [pr_class]
    return {
        "policy_version": _BENCHMARK_POLICY_VERSION,
        "eligible": eligible,
        "pr_class": pr_class,
        "exclusion_reasons": exclusion_reasons,
        "substantive_comment_count": len(iter_substantive_human_comments(snapshot)),
    }


def _classify_pull_request(snapshot: JSONDict) -> str:
    files = snapshot.get("files") or []
    if not files:
        return "substantive"
    paths = [str(file_info.get("path") or "") for file_info in files]
    if paths and all(_is_low_risk_path(path) for path in paths):
        return "trivial_low_risk"
    return "substantive"


def _is_low_risk_path(path: str) -> bool:
    lowered = path.strip().lower()
    if not lowered:
        return False
    if lowered.endswith(_LOW_RISK_SUFFIXES):
        return True
    if any(part in lowered for part in _LOW_RISK_PATH_PARTS):
        return True
    name = lowered.rsplit("/", 1)[-1]
    if name in _LOW_RISK_FILENAMES:
        return True
    if name.startswith("readme"):
        return True
    return False


def _is_substantive_comment(comment: JSONDict) -> bool:
    if comment.get("is_bot"):
        return False
    body = (comment.get("body") or "").strip()
    if not body:
        return False
    if any(pattern.match(body) for pattern in _TRIGGER_COMMENT_PATTERNS):
        return False
    if any(snippet.lower() in body.lower() for snippet in _TEMPLATE_COMMENT_SNIPPETS):
        return False
    if any(pattern.match(body) for pattern in _APPROVAL_COMMENT_PATTERNS):
        return False
    if comment.get("source") == "inline_review_comment":
        return True
    token_count = len(re.findall(r"[A-Za-z0-9_]+", body))
    return token_count >= 4


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
