from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

EXAMPLE_ROOT = Path(__file__).resolve().parent

EXPECTED_PATCH_MARKERS = {
    "support_reply_service": [
        "customer_support_bot/client.py",
        "customer_support_bot/replies.py",
    ],
    "case_summary_service": [
        "case_summary_service/client.py",
        "case_summary_service/summaries.py",
    ],
}


def read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return payload


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError(f"{path}:{line_number} must contain a JSON object.")
        events.append(payload)
    return events


def require_output(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(
            f"Missing {path}. Run the full migration agent before running artifact evals."
        )
    if path.stat().st_size == 0:
        raise ValueError(f"{path} is empty.")


def require_contains(text: str, marker: str, *, artifact: str) -> None:
    if marker not in text:
        raise ValueError(f"Expected {artifact} to contain {marker!r}.")


def require_result_value(result: dict[str, Any], field: str, marker: str) -> None:
    value = result.get(field)
    if not isinstance(value, str) or marker not in value:
        raise ValueError(f"Expected result[{field!r}] to contain {marker!r}.")


def validate_migration_artifacts(output_dir: Path, *, task_name: str | None = None) -> None:
    report_path = output_dir / "migration_report.md"
    patch_path = output_dir / "migration.patch"
    result_path = output_dir / "migration_result.json"
    audit_path = output_dir / "migration_audit.jsonl"

    for path in [report_path, patch_path, result_path, audit_path]:
        require_output(path)

    result = read_json(result_path)
    patch = patch_path.read_text(encoding="utf-8")
    report = report_path.read_text(encoding="utf-8")
    audit_events = read_jsonl(audit_path)

    require_result_value(result, "baseline_test_command", "unittest")
    require_result_value(result, "check_command", "compileall")
    require_result_value(result, "final_test_command", "unittest")

    final_test_result = str(result.get("final_test_result", "")).lower()
    if "pass" not in final_test_result and "ok" not in final_test_result:
        raise ValueError("Expected final_test_result to describe a passing test run.")

    changed_files = result.get("changed_files")
    if not isinstance(changed_files, list) or not changed_files:
        raise ValueError("Expected result['changed_files'] to be a non-empty list.")

    require_contains(patch, "responses.create", artifact=str(patch_path))
    require_contains(patch, "output_text", artifact=str(patch_path))
    for marker in EXPECTED_PATCH_MARKERS.get(task_name or "", []):
        require_contains(patch, marker, artifact=str(patch_path))
    require_contains(patch, "tests/", artifact=str(patch_path))

    require_contains(report.lower(), "responses", artifact=str(report_path))
    require_contains(report.lower(), "test", artifact=str(report_path))

    if not any(event.get("event") == "host_artifacts_written" for event in audit_events):
        raise ValueError("Expected audit log to include a host_artifacts_written event.")


def validate_output_root(output_dir: Path) -> None:
    batch_summary_path = output_dir / "batch_summary.json"
    if not batch_summary_path.exists():
        validate_migration_artifacts(output_dir)
        return

    batch_summary = read_json(batch_summary_path)
    task_summaries = batch_summary.get("task_summaries")
    if not isinstance(task_summaries, list) or not task_summaries:
        raise ValueError("Expected batch_summary.json to include task_summaries.")

    for summary in task_summaries:
        if not isinstance(summary, dict):
            raise ValueError("Each task summary must be a JSON object.")
        task_name = summary.get("task_name")
        task_output_dir = summary.get("output_dir")
        if not isinstance(task_name, str) or not isinstance(task_output_dir, str):
            raise ValueError("Each task summary must include task_name and output_dir.")
        validate_migration_artifacts(Path(task_output_dir), task_name=task_name)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate generated migration-agent artifacts.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=EXAMPLE_ROOT / "outputs",
        help=(
            "Directory containing batch_summary.json or a single task's "
            "migration_report.md, migration.patch, migration_result.json, "
            "and migration_audit.jsonl."
        ),
    )
    args = parser.parse_args()

    try:
        validate_output_root(args.output_dir)
    except Exception as exc:
        raise SystemExit(f"Artifact eval failed: {exc}") from exc

    print(f"Migration artifact evals passed for {args.output_dir}")


if __name__ == "__main__":
    main()
