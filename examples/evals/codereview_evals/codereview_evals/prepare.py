from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from openai import OpenAI

from .github_cache import DEFAULT_CACHE_ROOT, load_cached_pull_requests
from .paths import PREPARED_ROOT, harness_dir_for_level
from .types import JSONDict, PreparedDatasetArtifacts

ProgressCallback = Callable[[str], None] | None

DEFAULT_DIFF_CHAR_LIMIT = 12_000
DEFAULT_BODY_CHAR_LIMIT = 2_000
DEFAULT_COMMENT_CHAR_LIMIT = 800
DEFAULT_REFERENCE_COMMENT_LIMIT = 12


def default_dataset_path(*, cache_key: str, level: int, prepared_root: Path = PREPARED_ROOT) -> Path:
    filename = "pairwise.jsonl" if level == 3 else "benchmark.jsonl"
    return prepared_root / cache_key / f"level_{level}" / filename


def prepare_dataset(
    *,
    level: int,
    cache_key: str,
    cache_root: Path = DEFAULT_CACHE_ROOT,
    prepared_root: Path = PREPARED_ROOT,
    max_prs: int | None = None,
    refresh_derived: bool = False,
    progress_callback: ProgressCallback = None,
    client: OpenAI | None = None,
) -> tuple[PreparedDatasetArtifacts, JSONDict]:
    snapshots = load_cached_pull_requests(cache_root, cache_key=cache_key)
    if max_prs is not None:
        snapshots = snapshots[:max_prs]

    prepared_dir = default_dataset_path(
        cache_key=cache_key,
        level=level,
        prepared_root=prepared_root,
    ).parent
    prepared_dir.mkdir(parents=True, exist_ok=True)
    dataset_path = default_dataset_path(
        cache_key=cache_key,
        level=level,
        prepared_root=prepared_root,
    )

    records: list[JSONDict] = []
    total = len(snapshots)
    for index, snapshot in enumerate(snapshots, start=1):
        pr_number = int(snapshot.get("number") or 0)
        if progress_callback:
            progress_callback(
                f"[{index}/{total}] Preparing PR #{pr_number} for level {level}."
            )

        record = _build_basic_record(snapshot)
        if level >= 2:
            brief = _load_or_generate_pr_brief(
                cache_key=cache_key,
                prepared_root=prepared_root,
                snapshot=snapshot,
                refresh=refresh_derived,
                client=client,
            )
            record = _build_normalized_record(record, pr_brief=brief)
        if level == 3:
            record = _build_pairwise_record(
                cache_key=cache_key,
                prepared_root=prepared_root,
                base_record=record,
                refresh=refresh_derived,
                client=client,
            )
        records.append(record)

    _write_jsonl(dataset_path, records)
    summary: JSONDict = {
        "cache_key": cache_key,
        "level": level,
        "record_count": len(records),
        "dataset_path": str(dataset_path),
    }
    return (
        PreparedDatasetArtifacts(
            cache_key=cache_key,
            level=level,
            dataset_path=dataset_path,
            prepared_dir=prepared_dir,
            record_count=len(records),
        ),
        summary,
    )


def _build_basic_record(snapshot: JSONDict) -> JSONDict:
    merged = bool(snapshot.get("merged"))
    record: JSONDict = {
        "repository": snapshot.get("repository", ""),
        "pr_number": int(snapshot.get("number") or 0),
        "pr_title": snapshot.get("title", ""),
        "pr_url": snapshot.get("url", ""),
        "merged": merged,
        "pr_body": _truncate_text(snapshot.get("body") or "", DEFAULT_BODY_CHAR_LIMIT),
        "changed_files_text": _format_changed_files(snapshot.get("files") or []),
        "diff_text": _truncate_text(snapshot.get("diff_text") or "", DEFAULT_DIFF_CHAR_LIMIT),
        "reference_comments_text": _format_reference_comments(snapshot),
    }
    record["review_input_text"] = _format_review_input(record, normalized=False)
    return record


def _build_normalized_record(base_record: JSONDict, *, pr_brief: str) -> JSONDict:
    record = dict(base_record)
    record["pr_brief"] = pr_brief.strip()
    record["normalized_review_input_text"] = _format_review_input(record, normalized=True)
    return record


def _build_pairwise_record(
    *,
    cache_key: str,
    prepared_root: Path,
    base_record: JSONDict,
    refresh: bool,
    client: OpenAI | None,
) -> JSONDict:
    harness_dir = harness_dir_for_level(3)
    reviewer_system = _read_text(harness_dir / "reviewer_system.txt")
    eval_config = _read_json(harness_dir / "eval_config.json")
    reviewer_model = eval_config.get("reviewer_model") or eval_config.get("model") or "gpt-4.1"
    review_input_text = base_record.get("normalized_review_input_text") or base_record["review_input_text"]

    baseline_review = _load_or_generate_review(
        cache_key=cache_key,
        prepared_root=prepared_root,
        pr_number=int(base_record["pr_number"]),
        policy_name="baseline",
        reviewer_model=reviewer_model,
        reviewer_system=reviewer_system,
        agents_md=_read_text(harness_dir / "baseline_AGENTS.md"),
        review_input_text=review_input_text,
        refresh=refresh,
        client=client,
    )
    candidate_review = _load_or_generate_review(
        cache_key=cache_key,
        prepared_root=prepared_root,
        pr_number=int(base_record["pr_number"]),
        policy_name="candidate",
        reviewer_model=reviewer_model,
        reviewer_system=reviewer_system,
        agents_md=_read_text(harness_dir / "candidate_AGENTS.md"),
        review_input_text=review_input_text,
        refresh=refresh,
        client=client,
    )

    record = dict(base_record)
    record["baseline_review"] = baseline_review
    record["candidate_review"] = candidate_review
    record["pairwise_input_text"] = _format_pairwise_input(record)
    return record


def _load_or_generate_pr_brief(
    *,
    cache_key: str,
    prepared_root: Path,
    snapshot: JSONDict,
    refresh: bool,
    client: OpenAI | None,
) -> str:
    pr_number = int(snapshot.get("number") or 0)
    brief_path = prepared_root / cache_key / "shared" / "pr_briefs" / f"{pr_number}.txt"
    if brief_path.exists() and not refresh:
        return brief_path.read_text(encoding="utf-8")

    if client is None:
        client = OpenAI()

    harness_dir = harness_dir_for_level(2)
    eval_config = _read_json(harness_dir / "eval_config.json")
    brief_model = eval_config.get("brief_model") or eval_config.get("reviewer_model") or "gpt-4.1-mini"
    brief = _generate_text(
        client=client,
        model=brief_model,
        developer_prompt=_read_text(harness_dir / "pr_brief_system.txt"),
        user_prompt=_format_brief_input(snapshot),
    )
    brief_path.parent.mkdir(parents=True, exist_ok=True)
    brief_path.write_text(brief.strip() + "\n", encoding="utf-8")
    return brief


def _load_or_generate_review(
    *,
    cache_key: str,
    prepared_root: Path,
    pr_number: int,
    policy_name: str,
    reviewer_model: str,
    reviewer_system: str,
    agents_md: str,
    review_input_text: str,
    refresh: bool,
    client: OpenAI | None,
) -> str:
    review_path = (
        prepared_root
        / cache_key
        / "level_3"
        / "generated_reviews"
        / policy_name
        / f"{pr_number}.md"
    )
    if review_path.exists() and not refresh:
        return review_path.read_text(encoding="utf-8")

    if client is None:
        client = OpenAI()

    developer_prompt = reviewer_system.strip()
    if agents_md.strip():
        developer_prompt += f"\n\nAGENTS.md guidance:\n{agents_md.strip()}"
    review = _generate_text(
        client=client,
        model=reviewer_model,
        developer_prompt=developer_prompt,
        user_prompt=review_input_text,
    )
    review_path.parent.mkdir(parents=True, exist_ok=True)
    review_path.write_text(review.strip() + "\n", encoding="utf-8")
    return review


def _generate_text(
    *,
    client: OpenAI,
    model: str,
    developer_prompt: str,
    user_prompt: str,
) -> str:
    response = client.responses.create(
        model=model,
        input=[
            {"role": "developer", "content": developer_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    output_text = getattr(response, "output_text", None)
    if output_text:
        return output_text.strip()
    payload = _to_jsonable(response)
    text = payload.get("output_text") or ""
    if text:
        return text.strip()
    for item in payload.get("output", []):
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, dict) and part.get("text"):
                    parts.append(str(part["text"]))
            if parts:
                return "\n".join(parts).strip()
    raise RuntimeError("Could not extract output_text from preparation response.")


def _format_review_input(record: JSONDict, *, normalized: bool) -> str:
    lines = [
        f"Repository: {record.get('repository', '')}",
        f"Pull request: #{record['pr_number']} {record['pr_title']}",
        f"URL: {record['pr_url']}",
        f"Merged: {'yes' if record['merged'] else 'no'}",
    ]
    if record.get("pr_body"):
        lines.extend(["", "PR description:", record["pr_body"]])
    if normalized and record.get("pr_brief"):
        lines.extend(["", "PR brief:", record["pr_brief"]])
    lines.extend(
        [
            "",
            "Changed files:",
            record["changed_files_text"],
            "",
            "Diff excerpt:",
            record["diff_text"] or "No diff available.",
            "",
            "Historical review comments:",
            record["reference_comments_text"],
            "",
            "Return a concise review that focuses on the most important issues introduced by this pull request.",
        ]
    )
    return "\n".join(lines).strip()


def _format_pairwise_input(record: JSONDict) -> str:
    return "\n".join(
        [
            record["normalized_review_input_text"],
            "",
            "Baseline review:",
            record["baseline_review"],
            "",
            "Candidate review:",
            record["candidate_review"],
            "",
            "Choose baseline, candidate, or tie.",
        ]
    ).strip()


def _format_brief_input(snapshot: JSONDict) -> str:
    return "\n".join(
        [
            f"Repository: {snapshot.get('repository', '')}",
            f"Pull request: #{snapshot.get('number')} {snapshot.get('title', '')}",
            f"Merged: {'yes' if snapshot.get('merged') else 'no'}",
            "",
            "PR description:",
            _truncate_text(snapshot.get("body") or "", DEFAULT_BODY_CHAR_LIMIT) or "None.",
            "",
            "Changed files:",
            _format_changed_files(snapshot.get("files") or []),
            "",
            "Diff excerpt:",
            _truncate_text(snapshot.get("diff_text") or "", 8_000) or "No diff available.",
        ]
    ).strip()


def _format_changed_files(files: list[JSONDict]) -> str:
    if not files:
        return "No changed files captured."
    lines = []
    for file_info in sorted(files, key=lambda item: item.get("path", "")):
        path = file_info.get("path", "")
        additions = int(file_info.get("additions") or 0)
        deletions = int(file_info.get("deletions") or 0)
        lines.append(f"- {path} (+{additions}/-{deletions})")
    return "\n".join(lines)


def _format_reference_comments(snapshot: JSONDict) -> str:
    comments: list[JSONDict] = []
    for source_key in ("issue_comments", "reviews", "inline_review_comments"):
        for comment in snapshot.get(source_key) or []:
            if comment.get("is_bot"):
                continue
            body = (comment.get("body") or "").strip()
            if not body:
                continue
            comments.append(comment)

    if not comments:
        return "No historical comments captured."

    def sort_key(comment: JSONDict) -> tuple[str, str, int]:
        timestamp = comment.get("created_at") or comment.get("submitted_at") or ""
        return (timestamp, comment.get("source", ""), int(comment.get("id") or 0))

    lines = []
    for comment in sorted(comments, key=sort_key)[:DEFAULT_REFERENCE_COMMENT_LIMIT]:
        location = comment.get("path") or ""
        if comment.get("line"):
            location = f"{location}:{comment['line']}" if location else f"line {comment['line']}"
        prefix = f"- [{comment.get('source', 'comment')}] {comment.get('author_login', 'unknown')}"
        if location:
            prefix += f" on {location}"
        body = _truncate_text((comment.get("body") or "").strip(), DEFAULT_COMMENT_CHAR_LIMIT)
        lines.append(f"{prefix}: {body}")
    return "\n".join(lines)


def _truncate_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 17].rstrip() + "\n...[truncated]"


def _write_jsonl(path: Path, records: list[JSONDict]) -> None:
    lines = [json.dumps({"item": record}, ensure_ascii=False) for record in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _read_json(path: Path) -> JSONDict:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def _to_jsonable(value: object) -> JSONDict:
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(mode="json")
        if isinstance(dumped, dict):
            return dumped
    if isinstance(value, dict):
        return value
    raise TypeError(f"Unsupported OpenAI SDK object: {type(value)!r}")
