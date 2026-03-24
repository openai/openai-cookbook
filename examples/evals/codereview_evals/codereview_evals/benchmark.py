from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
import json
import os
from pathlib import Path
from typing import Any, Callable

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
    max_prs: int | None,
    run_name: str = "",
    cache_root: Path = DEFAULT_CACHE_ROOT,
    harness_dir: Path = DEFAULT_HARNESS_DIR,
    progress_callback: Callable[[str], None] | None = None,
    reviewer_model_override: str | None = None,
    grader_model_override: str | None = None,
    reviewer_reasoning_effort_override: str | None = None,
    grader_reasoning_effort_override: str | None = None,
    reviewer_max_output_tokens_override: int | None = None,
    grader_max_output_tokens_override: int | None = None,
    max_concurrency_override: int | None = None,
) -> tuple[RunArtifacts, JSONDict]:
    config, agents_md, reviewer_prompt, grader_prompt, review_schema, grader_schema = load_harness_bundle(
        harness_dir
    )
    config = _resolve_harness_config(
        config,
        reviewer_model_override=reviewer_model_override,
        grader_model_override=grader_model_override,
        reviewer_reasoning_effort_override=reviewer_reasoning_effort_override,
        grader_reasoning_effort_override=grader_reasoning_effort_override,
        reviewer_max_output_tokens_override=reviewer_max_output_tokens_override,
        grader_max_output_tokens_override=grader_max_output_tokens_override,
        max_concurrency_override=max_concurrency_override,
    )
    snapshots = load_cached_pull_requests(cache_root, cache_key=cache_key)
    if max_prs and max_prs > 0:
        snapshots = snapshots[:max_prs]

    client = _build_openai_client()
    total_snapshots = len(snapshots)
    if config.max_concurrency <= 1 or total_snapshots <= 1:
        results = _run_benchmark_serial(
            snapshots=snapshots,
            config=config,
            client=client,
            agents_md=agents_md,
            reviewer_prompt=reviewer_prompt,
            grader_prompt=grader_prompt,
            review_schema=review_schema,
            grader_schema=grader_schema,
            progress_callback=progress_callback,
        )
    else:
        results = _run_benchmark_parallel(
            snapshots=snapshots,
            config=config,
            client=client,
            agents_md=agents_md,
            reviewer_prompt=reviewer_prompt,
            grader_prompt=grader_prompt,
            review_schema=review_schema,
            grader_schema=grader_schema,
            progress_callback=progress_callback,
        )

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
        reviewer_reasoning_effort=_normalize_optional_string(config_data.get("reviewer_reasoning_effort")),
        grader_reasoning_effort=_normalize_optional_string(config_data.get("grader_reasoning_effort")),
        reviewer_max_output_tokens=_normalize_optional_int(config_data.get("reviewer_max_output_tokens")),
        grader_max_output_tokens=_normalize_optional_int(config_data.get("grader_max_output_tokens")),
        max_concurrency=max(1, int(config_data.get("max_concurrency", 1))),
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
    reasoning_effort: str | None = None,
    max_output_tokens: int | None = None,
) -> JSONDict:
    request: JSONDict = {
        "model": model,
        "input": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "schema": schema,
                "strict": True,
            }
        },
    }
    if reasoning_effort:
        request["reasoning"] = {"effort": reasoning_effort}
    if max_output_tokens is not None:
        request["max_output_tokens"] = max_output_tokens
    response = client.responses.create(**request)
    return json.loads(response.output_text)


def _run_benchmark_serial(
    *,
    snapshots: list[JSONDict],
    config: HarnessConfig,
    client: Any,
    agents_md: str,
    reviewer_prompt: str,
    grader_prompt: str,
    review_schema: JSONDict,
    grader_schema: JSONDict,
    progress_callback: Callable[[str], None] | None,
) -> list[JSONDict]:
    results: list[JSONDict] = []
    total_snapshots = len(snapshots)
    for index, snapshot in enumerate(snapshots, start=1):
        pr_number = snapshot.get("number")
        pr_title = str(snapshot.get("title", "")).strip()
        _emit_progress(
            progress_callback,
            f"[{index}/{total_snapshots}] Processing PR #{pr_number} {pr_title}".rstrip(),
        )
        result = _run_benchmark_snapshot(
            snapshot=snapshot,
            config=config,
            client=client,
            agents_md=agents_md,
            reviewer_prompt=reviewer_prompt,
            grader_prompt=grader_prompt,
            review_schema=review_schema,
            grader_schema=grader_schema,
        )
        results.append(result)
        if result.get("status") == "ok":
            _emit_progress(
                progress_callback,
                f"[{index}/{total_snapshots}] Completed PR #{pr_number} ({len(results)} processed)",
            )
        else:
            _emit_progress(
                progress_callback,
                f"[{index}/{total_snapshots}] Failed PR #{pr_number} ({len(results)} processed): {result.get('error_message', '')}",
            )
    return results


def _run_benchmark_parallel(
    *,
    snapshots: list[JSONDict],
    config: HarnessConfig,
    client: Any,
    agents_md: str,
    reviewer_prompt: str,
    grader_prompt: str,
    review_schema: JSONDict,
    grader_schema: JSONDict,
    progress_callback: Callable[[str], None] | None,
) -> list[JSONDict]:
    total_snapshots = len(snapshots)
    results_by_index: dict[int, JSONDict] = {}
    completed = 0

    with ThreadPoolExecutor(max_workers=min(config.max_concurrency, total_snapshots)) as executor:
        future_map = {}
        for index, snapshot in enumerate(snapshots, start=1):
            pr_number = snapshot.get("number")
            pr_title = str(snapshot.get("title", "")).strip()
            _emit_progress(
                progress_callback,
                f"[{index}/{total_snapshots}] Processing PR #{pr_number} {pr_title}".rstrip(),
            )
            future = executor.submit(
                _run_benchmark_snapshot,
                snapshot=snapshot,
                config=config,
                client=client,
                agents_md=agents_md,
                reviewer_prompt=reviewer_prompt,
                grader_prompt=grader_prompt,
                review_schema=review_schema,
                grader_schema=grader_schema,
            )
            future_map[future] = (index, pr_number)

        for future in as_completed(future_map):
            index, pr_number = future_map[future]
            result = future.result()
            results_by_index[index] = result
            completed += 1
            if result.get("status") == "ok":
                _emit_progress(
                    progress_callback,
                    f"[{index}/{total_snapshots}] Completed PR #{pr_number} ({completed} processed)",
                )
            else:
                _emit_progress(
                    progress_callback,
                    f"[{index}/{total_snapshots}] Failed PR #{pr_number} ({completed} processed): {result.get('error_message', '')}",
                )

    return [results_by_index[index] for index in range(1, total_snapshots + 1)]


def _run_benchmark_snapshot(
    *,
    snapshot: JSONDict,
    config: HarnessConfig,
    client: Any,
    agents_md: str,
    reviewer_prompt: str,
    grader_prompt: str,
    review_schema: JSONDict,
    grader_schema: JSONDict,
) -> JSONDict:
    try:
        review_output = _run_json_schema_completion(
            client=client,
            model=config.model,
            system_prompt=reviewer_prompt,
            user_content=build_reviewer_input(snapshot, agents_md),
            schema_name="code_review_output",
            schema=review_schema,
            reasoning_effort=config.reviewer_reasoning_effort,
            max_output_tokens=config.reviewer_max_output_tokens,
        )
        grade_output = _run_json_schema_completion(
            client=client,
            model=config.grader_model,
            system_prompt=grader_prompt,
            user_content=build_grader_input(snapshot, agents_md, review_output),
            schema_name="code_review_grade",
            schema=grader_schema,
            reasoning_effort=config.grader_reasoning_effort,
            max_output_tokens=config.grader_max_output_tokens,
        )
        return build_result_row(
            snapshot=snapshot,
            review_output=review_output,
            grade_output=grade_output,
            config=config,
        )
    except Exception as exc:  # pragma: no cover - exercised through CLI smoke paths
        return build_failure_row(snapshot=snapshot, error_message=str(exc), config=config)


def _resolve_harness_config(
    config: HarnessConfig,
    *,
    reviewer_model_override: str | None = None,
    grader_model_override: str | None = None,
    reviewer_reasoning_effort_override: str | None = None,
    grader_reasoning_effort_override: str | None = None,
    reviewer_max_output_tokens_override: int | None = None,
    grader_max_output_tokens_override: int | None = None,
    max_concurrency_override: int | None = None,
) -> HarnessConfig:
    return replace(
        config,
        model=reviewer_model_override or config.model,
        grader_model=grader_model_override or config.grader_model,
        reviewer_reasoning_effort=_normalize_override(
            reviewer_reasoning_effort_override, config.reviewer_reasoning_effort
        ),
        grader_reasoning_effort=_normalize_override(
            grader_reasoning_effort_override, config.grader_reasoning_effort
        ),
        reviewer_max_output_tokens=(
            reviewer_max_output_tokens_override
            if reviewer_max_output_tokens_override is not None
            else config.reviewer_max_output_tokens
        ),
        grader_max_output_tokens=(
            grader_max_output_tokens_override
            if grader_max_output_tokens_override is not None
            else config.grader_max_output_tokens
        ),
        max_concurrency=max_concurrency_override or config.max_concurrency,
    )


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


def _emit_progress(progress_callback: Callable[[str], None] | None, message: str) -> None:
    if progress_callback is not None:
        progress_callback(message)


def _normalize_optional_string(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _normalize_optional_int(value: object) -> int | None:
    if value is None:
        return None
    return int(value)


def _normalize_override(override: str | None, fallback: str | None) -> str | None:
    if override is None:
        return fallback
    normalized = override.strip()
    if normalized.lower() in {"", "default"}:
        return None
    return normalized


def _truncate_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n\n[truncated]"
