from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Callable

from openai import OpenAI

from .paths import PREPARED_ROOT, harness_dir_for_level
from .prepare import default_dataset_path
from .types import EvalRunArtifacts, JSONDict

ProgressCallback = Callable[[str], None] | None
DEFAULT_REVIEWER_MODEL = "gpt-5.3-codex"
DEFAULT_EVAL_JUDGE_MODEL = "gpt-4.1"


def run_evals(
    *,
    level: int,
    cache_key: str,
    dataset_path: Path | None = None,
    prepared_root: Path = PREPARED_ROOT,
    run_name: str | None = None,
    poll_interval_seconds: int = 5,
    timeout_seconds: int = 900,
    progress_callback: ProgressCallback = None,
    client: OpenAI | None = None,
) -> tuple[EvalRunArtifacts, JSONDict]:
    if dataset_path is None:
        dataset_path = default_dataset_path(
            cache_key=cache_key,
            level=level,
            prepared_root=prepared_root,
        )
    if not dataset_path.exists():
        raise FileNotFoundError(f"Prepared dataset not found at {dataset_path}")

    if client is None:
        client = OpenAI()

    run_name = run_name or _default_run_name(level)
    if progress_callback:
        progress_callback(f"Uploading {dataset_path.name} for level {level}.")
    with dataset_path.open("rb") as handle:
        uploaded_file = _to_jsonable(client.files.create(file=handle, purpose="evals"))

    eval_obj, eval_name, eval_spec_fingerprint = _ensure_eval(level=level, client=client)
    eval_id = str(eval_obj["id"])
    if progress_callback:
        progress_callback(f"Using eval {eval_id} ({eval_name}).")

    run_request = _build_run_request(level=level, file_id=str(uploaded_file["id"]))
    initial_run = _to_jsonable(
        client.evals.runs.create(eval_id, name=run_name, data_source=run_request)
    )
    run_id = str(initial_run["id"])
    if progress_callback:
        progress_callback(f"Created eval run {run_id}.")

    final_run = _poll_run(
        client=client,
        eval_id=eval_id,
        run_id=run_id,
        poll_interval_seconds=poll_interval_seconds,
        timeout_seconds=timeout_seconds,
        progress_callback=progress_callback,
    )
    output_items = _list_output_items(client=client, eval_id=eval_id, run_id=run_id)
    summary = _build_summary(
        level=level,
        run=final_run,
        output_items=output_items,
        eval_name=eval_name,
        eval_spec_fingerprint=eval_spec_fingerprint,
    )

    run_dir = harness_dir_for_level(level) / "results" / run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    uploaded_file_json = run_dir / "uploaded_file.json"
    eval_json = run_dir / "eval.json"
    run_json = run_dir / "run.json"
    output_items_json = run_dir / "output_items.json"
    summary_json = run_dir / "summary.json"

    _write_json(uploaded_file_json, uploaded_file)
    _write_json(eval_json, eval_obj)
    _write_json(run_json, final_run)
    _write_json(output_items_json, output_items)
    _write_json(summary_json, summary)

    return (
        EvalRunArtifacts(
            cache_key=cache_key,
            level=level,
            run_dir=run_dir,
            uploaded_file_json=uploaded_file_json,
            eval_json=eval_json,
            run_json=run_json,
            output_items_json=output_items_json,
            summary_json=summary_json,
            dataset_path=dataset_path,
        ),
        summary,
    )


def _ensure_eval(*, level: int, client: OpenAI) -> tuple[JSONDict, str, str]:
    eval_spec = _build_eval_spec(level)
    eval_spec_fingerprint = _eval_spec_fingerprint(eval_spec)
    eval_name = _versioned_eval_name(level=level, eval_spec_fingerprint=eval_spec_fingerprint)
    page = client.evals.list(limit=100, order="desc")
    for eval_obj in getattr(page, "data", []):
        eval_dict = _to_jsonable(eval_obj)
        if eval_dict.get("name") == eval_name:
            return eval_dict, eval_name, eval_spec_fingerprint
    created = client.evals.create(
        name=eval_name,
        metadata={
            "example": "code_review_evals",
            "level": str(level),
            "eval_spec_fingerprint": eval_spec_fingerprint,
        },
        **eval_spec,
    )
    return _to_jsonable(created), eval_name, eval_spec_fingerprint


def _build_eval_spec(level: int) -> JSONDict:
    if level in {1, 2}:
        return {
            "data_source_config": {
                "type": "custom",
                "item_schema": _item_schema(level),
                "include_sample_schema": True,
            },
            "testing_criteria": _build_benchmark_testing_criteria(level),
        }
    eval_config = _read_eval_config(level)
    grader_model = (
        eval_config.get("judge_model")
        or eval_config.get("grader_model")
        or DEFAULT_EVAL_JUDGE_MODEL
    )
    return {
        "data_source_config": {
            "type": "custom",
            "item_schema": _item_schema(level),
            "include_sample_schema": True,
        },
        "testing_criteria": [
            {
                "type": "label_model",
                "name": "Pairwise winner label",
                "model": grader_model,
                "input": [
                    {
                        "role": "developer",
                        "content": _read_text(harness_dir_for_level(level) / "pairwise_judge_system.txt"),
                    },
                    {
                        "role": "user",
                        "content": _pairwise_template(),
                    },
                ],
                "labels": ["baseline", "candidate", "tie"],
                "passing_labels": ["baseline", "candidate", "tie"],
            }
        ],
    }


def _eval_spec_fingerprint(eval_spec: JSONDict) -> str:
    fingerprint_input = {
        "data_source_config": eval_spec["data_source_config"],
        "testing_criteria": eval_spec["testing_criteria"],
    }
    payload = json.dumps(fingerprint_input, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def _versioned_eval_name(*, level: int, eval_spec_fingerprint: str) -> str:
    return f"code-review-evals-level-{level}-{eval_spec_fingerprint}"


def _build_run_request(*, level: int, file_id: str) -> JSONDict:
    if level in {1, 2}:
        eval_config = _read_eval_config(level)
        model = eval_config.get("reviewer_model") or eval_config.get("model") or DEFAULT_REVIEWER_MODEL
        reviewer_system = _read_text(harness_dir_for_level(level) / "reviewer_system.txt")
        agents_md = _read_text(harness_dir_for_level(level) / "AGENTS.md")
        developer_prompt = reviewer_system.strip()
        if agents_md.strip():
            developer_prompt += f"\n\nAGENTS.md guidance:\n{agents_md.strip()}"
        template_field = "normalized_review_input_text" if level == 2 else "review_input_text"
        return {
            "type": "responses",
            "model": model,
            "input_messages": {
                "type": "template",
                "template": [
                    {"role": "developer", "content": developer_prompt},
                    {"role": "user", "content": f"{{{{ item.{template_field} }}}}"},
                ],
            },
            "source": {"type": "file_id", "id": file_id},
        }

    judge_model = (
        _read_eval_config(level).get("judge_model")
        or _read_eval_config(level).get("grader_model")
        or DEFAULT_EVAL_JUDGE_MODEL
    )
    return {
        "type": "responses",
        "model": judge_model,
        "input_messages": {
            "type": "template",
            "template": [
                {
                    "role": "developer",
                    "content": _read_text(harness_dir_for_level(level) / "pairwise_judge_system.txt"),
                },
                {"role": "user", "content": _pairwise_template()},
            ],
        },
        "source": {"type": "file_id", "id": file_id},
    }


def _poll_run(
    *,
    client: OpenAI,
    eval_id: str,
    run_id: str,
    poll_interval_seconds: int,
    timeout_seconds: int,
    progress_callback: ProgressCallback,
) -> JSONDict:
    deadline = time.time() + timeout_seconds
    while True:
        run = _to_jsonable(client.evals.runs.retrieve(run_id=run_id, eval_id=eval_id))
        status = run.get("status")
        if progress_callback:
            progress_callback(f"Run {run_id} status: {status}.")
        if status in {"completed", "failed", "canceled"}:
            return run
        if time.time() >= deadline:
            raise TimeoutError(f"Timed out waiting for eval run {run_id}.")
        time.sleep(poll_interval_seconds)


def _list_output_items(*, client: OpenAI, eval_id: str, run_id: str) -> list[JSONDict]:
    items: list[JSONDict] = []
    after: str | None = None
    while True:
        kwargs: JSONDict = {
            "run_id": run_id,
            "eval_id": eval_id,
            "limit": 100,
            "order": "asc",
        }
        if after:
            kwargs["after"] = after
        page = client.evals.runs.output_items.list(**kwargs)
        page_items = [_to_jsonable(item) for item in getattr(page, "data", [])]
        items.extend(page_items)
        if not getattr(page, "has_more", False) or not page_items:
            return items
        after = page_items[-1]["id"]


def _build_summary(
    *,
    level: int,
    run: JSONDict,
    output_items: list[JSONDict],
    eval_name: str,
    eval_spec_fingerprint: str,
) -> JSONDict:
    summary: JSONDict = {
        "eval_id": run.get("eval_id"),
        "eval_name": eval_name,
        "eval_spec_fingerprint": eval_spec_fingerprint,
        "run_id": run.get("id"),
        "status": run.get("status"),
        "report_url": run.get("report_url"),
        "result_counts": run.get("result_counts") or {},
        "per_testing_criteria_results": run.get("per_testing_criteria_results") or [],
        "output_item_count": len(output_items),
    }
    if level in {1, 2}:
        summary.update(_benchmark_summary(output_items))
    else:
        summary.update(_pairwise_summary(output_items))
    return summary


def _benchmark_summary(output_items: list[JSONDict]) -> JSONDict:
    criteria = {
        "correctness": {"passed": 0, "total": 0},
        "usefulness": {"passed": 0, "total": 0},
        "noise": {"passed": 0, "total": 0},
        "overall_pass": {"passed": 0, "total": 0},
    }
    subgroups = {
        "merged": {"passed": 0, "total": 0},
        "unmerged": {"passed": 0, "total": 0},
    }
    for item in output_items:
        result_map: dict[str, bool] = {}
        for result in item.get("results", []):
            key = _criterion_key(result.get("name", ""))
            if not key:
                continue
            passed = bool(result.get("passed"))
            criteria[key]["total"] += 1
            criteria[key]["passed"] += int(passed)
            result_map[key] = passed
        datasource_item = item.get("datasource_item") or {}
        subgroup = "merged" if datasource_item.get("merged") else "unmerged"
        subgroups[subgroup]["total"] += 1
        overall_pass = result_map.get("overall_pass", item.get("status") == "pass")
        subgroups[subgroup]["passed"] += int(overall_pass)
    return {
        "correctness_rate": _safe_rate(criteria["correctness"]["passed"], criteria["correctness"]["total"]),
        "usefulness_rate": _safe_rate(criteria["usefulness"]["passed"], criteria["usefulness"]["total"]),
        "noise_rate": _safe_rate(criteria["noise"]["passed"], criteria["noise"]["total"]),
        "overall_pass_rate": _safe_rate(criteria["overall_pass"]["passed"], criteria["overall_pass"]["total"]),
        "merged_pass_rate": _safe_rate(subgroups["merged"]["passed"], subgroups["merged"]["total"]),
        "unmerged_pass_rate": _safe_rate(subgroups["unmerged"]["passed"], subgroups["unmerged"]["total"]),
        "subgroups": subgroups,
    }


def _pairwise_summary(output_items: list[JSONDict]) -> JSONDict:
    counts = {"baseline": 0, "candidate": 0, "tie": 0, "unknown": 0}
    for item in output_items:
        winner = _extract_winner(item)
        counts[winner] = counts.get(winner, 0) + 1
    total = sum(counts.values())
    return {
        "winner_counts": counts,
        "baseline_rate": _safe_rate(counts["baseline"], total),
        "candidate_rate": _safe_rate(counts["candidate"], total),
        "tie_rate": _safe_rate(counts["tie"], total),
    }


def _extract_winner(item: JSONDict) -> str:
    for result in item.get("results", []):
        for key in ("label", "value", "selected_label", "output_text"):
            winner = _normalize_winner(result.get(key))
            if winner:
                return winner
    sample_text = _sample_output_text(item.get("sample") or {})
    return _normalize_winner(sample_text) or "unknown"


def _sample_output_text(sample: JSONDict) -> str:
    parts: list[str] = []
    for message in sample.get("output") or []:
        content = message.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("text"):
                    parts.append(str(part["text"]))
    return "\n".join(parts).strip()


def _normalize_winner(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    lowered = value.strip().lower()
    for winner in ("baseline", "candidate", "tie"):
        if lowered == winner or winner in lowered:
            return winner
    return None


def _criterion_key(name: str) -> str | None:
    lowered = name.lower()
    if "correctness" in lowered:
        return "correctness"
    if "usefulness" in lowered:
        return "usefulness"
    if "noise" in lowered:
        return "noise"
    if "overall" in lowered:
        return "overall_pass"
    return None


def _build_benchmark_testing_criteria(level: int) -> list[JSONDict]:
    grader_model = _read_eval_config(level).get("grader_model") or DEFAULT_EVAL_JUDGE_MODEL
    grader_system = _read_text(harness_dir_for_level(level) / "grader_system.txt")
    label_instruction = "Return exactly one label: pass or fail. Do not output any other text."
    criteria: list[JSONDict] = []
    for name, extra_instruction in (
        (
            "Correctness",
            "Label pass only if the generated review is grounded in the diff and changed-file summary, and does not invent nonexistent risks. A no-issue review only passes if it gives concrete diff-grounded reasoning.",
        ),
        (
            "Usefulness",
            "Label pass only if the generated review either identifies a concrete issue or omission, or gives a justified no-issue assessment tied to the diff. Generic approval or PR restatement should fail.",
        ),
        (
            "Noise",
            "Label pass only if the generated review stays focused on high-signal issues and avoids trivial, redundant, or boilerplate approval language.",
        ),
        (
            "Overall pass",
            "Label pass only if the generated review is successful overall because it finds a concrete issue or provides a justified no-issue assessment. Generic positive signoff should fail.",
        ),
    ):
        criteria.append(
            {
                "type": "label_model",
                "name": name,
                "model": grader_model,
                "input": [
                    {
                        "role": "developer",
                        "content": f"{grader_system}\n\n{extra_instruction}\n\n{label_instruction}",
                    },
                    {
                        "role": "user",
                        "content": _benchmark_template(level),
                    },
                ],
                "labels": ["pass", "fail"],
                "passing_labels": ["pass"],
            }
        )
    return criteria


def _benchmark_template(level: int) -> str:
    lines = [
        "Pull request:",
        "#{{ item.pr_number }} {{ item.pr_title }}",
        "Merged: {{ item.merged }}",
    ]
    if level == 2:
        lines.extend(["", "PR brief:", "{{ item.pr_brief }}"])
    lines.extend(
        [
            "",
            "Changed files:",
            "{{ item.changed_files_text }}",
            "",
            "Diff excerpt:",
            "{{ item.diff_text }}",
            "",
            "Historical comments:",
            "{{ item.reference_comments_text }}",
            "",
            "Generated review:",
            "{{ sample.output_text }}",
        ]
    )
    return "\n".join(lines)


def _pairwise_template() -> str:
    return "\n".join(
        [
            "Pull request:",
            "#{{ item.pr_number }} {{ item.pr_title }}",
            "Merged: {{ item.merged }}",
            "",
            "PR brief:",
            "{{ item.pr_brief }}",
            "",
            "Changed files:",
            "{{ item.changed_files_text }}",
            "",
            "Diff excerpt:",
            "{{ item.diff_text }}",
            "",
            "Historical comments:",
            "{{ item.reference_comments_text }}",
            "",
            "Baseline review:",
            "{{ item.baseline_review }}",
            "",
            "Candidate review:",
            "{{ item.candidate_review }}",
        ]
    )


def _item_schema(level: int) -> JSONDict:
    properties: JSONDict = {
        "repository": {"type": "string"},
        "pr_number": {"type": "integer"},
        "pr_title": {"type": "string"},
        "pr_url": {"type": "string"},
        "merged": {"type": "boolean"},
        "pr_body": {"type": "string"},
        "changed_files_text": {"type": "string"},
        "diff_text": {"type": "string"},
        "reference_comments_text": {"type": "string"},
        "review_input_text": {"type": "string"},
    }
    required = [
        "repository",
        "pr_number",
        "pr_title",
        "pr_url",
        "merged",
        "changed_files_text",
        "diff_text",
        "reference_comments_text",
        "review_input_text",
    ]
    if level >= 2:
        properties["pr_brief"] = {"type": "string"}
        properties["normalized_review_input_text"] = {"type": "string"}
        required.extend(["pr_brief", "normalized_review_input_text"])
    if level == 3:
        properties["baseline_review"] = {"type": "string"}
        properties["candidate_review"] = {"type": "string"}
        properties["pairwise_input_text"] = {"type": "string"}
        required.extend(["baseline_review", "candidate_review", "pairwise_input_text"])
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def _default_run_name(level: int) -> str:
    return f"level-{level}-{time.strftime('%Y%m%d-%H%M%S')}"


def _safe_rate(passed: int, total: int) -> float | None:
    if total == 0:
        return None
    return passed / total


def _read_eval_config(level: int) -> JSONDict:
    return json.loads((harness_dir_for_level(level) / "eval_config.json").read_text(encoding="utf-8"))


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _to_jsonable(value: object) -> JSONDict:
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(mode="json")
        if isinstance(dumped, dict):
            return dumped
    if isinstance(value, dict):
        return value
    raise TypeError(f"Unsupported OpenAI SDK object: {type(value)!r}")
