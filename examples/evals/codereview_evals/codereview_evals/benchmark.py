from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .github_cache import DEFAULT_CACHE_ROOT, load_cached_pull_requests
from .reporting import default_run_id, render_report_for_run, write_results
from .types import HarnessConfig, JSONDict, RunArtifacts

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HARNESS_DIR = PROJECT_ROOT / "1_benchmark_harness"

MAX_DIFF_CHARS = 16_000
MAX_REFERENCE_COMMENTS = 12


def run_benchmark(
    *,
    cache_key: str,
    max_prs: int,
    run_name: str = "",
    cache_root: Path = DEFAULT_CACHE_ROOT,
    harness_dir: Path = DEFAULT_HARNESS_DIR,
) -> tuple[RunArtifacts, JSONDict]:
    config, agents_md, reviewer_prompt, grader_prompt, review_schema, grader_schema = load_harness_bundle(
        harness_dir
    )
    snapshots = load_cached_pull_requests(cache_root, cache_key=cache_key)
    if max_prs > 0:
        snapshots = snapshots[:max_prs]

    client = _build_openai_client()
    results: list[JSONDict] = []
    for snapshot in snapshots:
        try:
            review_output = _run_json_schema_completion(
                client=client,
                model=config.model,
                system_prompt=reviewer_prompt,
                user_content=build_reviewer_input(snapshot, agents_md),
                schema_name="code_review_output",
                schema=review_schema,
            )
            grade_output = _run_json_schema_completion(
                client=client,
                model=config.grader_model,
                system_prompt=grader_prompt,
                user_content=build_grader_input(snapshot, agents_md, review_output),
                schema_name="code_review_grade",
                schema=grader_schema,
            )
            results.append(
                build_result_row(
                    snapshot=snapshot,
                    review_output=review_output,
                    grade_output=grade_output,
                    config=config,
                )
            )
        except Exception as exc:  # pragma: no cover - exercised through CLI smoke paths
            results.append(build_failure_row(snapshot=snapshot, error_message=str(exc), config=config))

    run_dir = harness_dir / "results" / default_run_id(run_name)
    return write_results(
        run_dir=run_dir,
        results=results,
        report_title="Level 1 Benchmark Harness Report",
    )


def render_benchmark_report(*, run_dir: Path) -> Path:
    return render_report_for_run(
        run_dir=run_dir,
        report_title="Level 1 Benchmark Harness Report",
    )


def load_harness_bundle(
    harness_dir: Path = DEFAULT_HARNESS_DIR,
) -> tuple[HarnessConfig, str, str, str, JSONDict, JSONDict]:
    config_data = json.loads((harness_dir / "eval_config.json").read_text(encoding="utf-8"))
    config = HarnessConfig(
        model=str(config_data["model"]),
        grader_model=str(config_data["grader_model"]),
    )
    agents_md = (harness_dir / "AGENTS.md").read_text(encoding="utf-8").strip()
    reviewer_prompt = (harness_dir / "reviewer_system.txt").read_text(encoding="utf-8").strip()
    grader_prompt = (harness_dir / "grader_system.txt").read_text(encoding="utf-8").strip()
    review_schema = json.loads((harness_dir / "review_output_schema.json").read_text(encoding="utf-8"))
    grader_schema = json.loads((harness_dir / "grader_output_schema.json").read_text(encoding="utf-8"))
    return config, agents_md, reviewer_prompt, grader_prompt, review_schema, grader_schema


def collect_reference_comments(snapshot: JSONDict) -> list[JSONDict]:
    comments: list[JSONDict] = []
    for key in ("issue_comments", "reviews", "inline_review_comments"):
        for item in snapshot.get(key, []):
            body = str(item.get("body") or "").strip()
            if not body or item.get("is_bot"):
                continue
            comments.append(item)
    comments.sort(key=lambda item: str(item.get("created_at") or item.get("submitted_at") or ""))
    return comments[:MAX_REFERENCE_COMMENTS]


def build_reviewer_input(snapshot: JSONDict, agents_md: str) -> str:
    files_block = "\n".join(
        f"- {file_info.get('path', '')} (+{file_info.get('additions', 0)}/-{file_info.get('deletions', 0)})"
        for file_info in snapshot.get("files", [])
    )
    diff_text = _truncate_text(str(snapshot.get("diff_text") or ""), MAX_DIFF_CHARS)
    return "\n\n".join(
        [
            f"Pull request: #{snapshot.get('number')} {snapshot.get('title', '')}",
            f"URL: {snapshot.get('url', '')}",
            f"Merged: {snapshot.get('merged', False)}",
            "AGENTS.md guidance:\n" + (agents_md or "(empty)"),
            "PR description:\n" + (str(snapshot.get("body") or "").strip() or "(empty)"),
            "Changed files:\n" + (files_block or "(none)"),
            "Unified diff:\n" + (diff_text or "(empty)"),
        ]
    )


def build_grader_input(
    snapshot: JSONDict,
    agents_md: str,
    review_output: JSONDict,
) -> str:
    reference_comments = collect_reference_comments(snapshot)
    reference_block = "\n\n".join(_format_reference_comment(comment) for comment in reference_comments) or "(none)"
    review_json = json.dumps(review_output, indent=2, ensure_ascii=False)
    diff_text = _truncate_text(str(snapshot.get("diff_text") or ""), MAX_DIFF_CHARS)
    return "\n\n".join(
        [
            f"Pull request: #{snapshot.get('number')} {snapshot.get('title', '')}",
            f"URL: {snapshot.get('url', '')}",
            "AGENTS.md guidance:\n" + (agents_md or "(empty)"),
            "Unified diff:\n" + (diff_text or "(empty)"),
            "Historical human reference comments:\n" + reference_block,
            "Generated review JSON:\n" + review_json,
        ]
    )


def build_result_row(
    *,
    snapshot: JSONDict,
    review_output: JSONDict,
    grade_output: JSONDict,
    config: HarnessConfig,
) -> JSONDict:
    comments = list(review_output.get("comments") or [])
    return {
        "status": "ok",
        "pr_number": snapshot.get("number"),
        "pr_title": snapshot.get("title", ""),
        "pr_url": snapshot.get("url", ""),
        "merged": bool(snapshot.get("merged")),
        "file_count": len(snapshot.get("files", [])),
        "reference_comment_count": len(collect_reference_comments(snapshot)),
        "reviewer_model": config.model,
        "grader_model": config.grader_model,
        "reviewer_summary": str(review_output.get("summary") or "").strip(),
        "reviewer_comments": comments,
        "reviewer_comment_count": len(comments),
        "grader_correctness": int(grade_output.get("correctness", 0) or 0),
        "grader_usefulness": int(grade_output.get("usefulness", 0) or 0),
        "grader_noise": int(grade_output.get("noise", 0) or 0),
        "grader_overall_pass": int(grade_output.get("overall_pass", 0) or 0),
        "grader_reason": str(grade_output.get("reason") or "").strip(),
        "error_message": "",
    }


def build_failure_row(
    *,
    snapshot: JSONDict,
    error_message: str,
    config: HarnessConfig,
) -> JSONDict:
    return {
        "status": "failed",
        "pr_number": snapshot.get("number"),
        "pr_title": snapshot.get("title", ""),
        "pr_url": snapshot.get("url", ""),
        "merged": bool(snapshot.get("merged")),
        "file_count": len(snapshot.get("files", [])),
        "reference_comment_count": len(collect_reference_comments(snapshot)),
        "reviewer_model": config.model,
        "grader_model": config.grader_model,
        "reviewer_summary": "",
        "reviewer_comments": [],
        "reviewer_comment_count": 0,
        "grader_correctness": 0,
        "grader_usefulness": 0,
        "grader_noise": 0,
        "grader_overall_pass": 0,
        "grader_reason": "",
        "error_message": error_message,
    }


def _build_openai_client() -> Any:
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is required to run benchmark evals.")
    try:
        from openai import OpenAI
    except ModuleNotFoundError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "The OpenAI SDK is not installed. Run `pip install -e .` from this folder first."
        ) from exc
    return OpenAI()


def _run_json_schema_completion(
    *,
    client: Any,
    model: str,
    system_prompt: str,
    user_content: str,
    schema_name: str,
    schema: JSONDict,
) -> JSONDict:
    response = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "schema": schema,
                "strict": True,
            }
        },
    )
    return json.loads(response.output_text)


def _format_reference_comment(comment: JSONDict) -> str:
    location = ""
    if comment.get("path"):
        location = f"{comment.get('path')}:{comment.get('line') or ''}".rstrip(":")
    metadata = ", ".join(
        part
        for part in [
            str(comment.get("source", "")),
            str(comment.get("author_login", "")),
            location,
        ]
        if part
    )
    return f"- [{metadata}]\n{str(comment.get('body') or '').strip()}"


def _truncate_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n\n[truncated]"
