from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional


@dataclass
class RunSummary:
    run_id: str
    experiment: str
    num_tasks: int
    num_succeeded: int
    average_score: Optional[float]


def iter_results_files(results_dir: Path) -> Iterable[Path]:
    if not results_dir.exists():
        return []
    for path in results_dir.glob("*/results.json"):
        if path.is_file():
            yield path


def load_run_summary(path: Path) -> RunSummary:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    tasks = data.get("tasks", [])
    scores = [task.get("grade", {}).get("score") for task in tasks if task.get("grade")]
    average_score = sum(scores) / len(scores) if scores else None

    summary = data.get("summary", {})

    return RunSummary(
        run_id=data.get("runId", "unknown"),
        experiment=data.get("experimentName", "unknown"),
        num_tasks=summary.get("numTasks", len(tasks)),
        num_succeeded=summary.get("numSucceeded", 0),
        average_score=average_score,
    )


def format_summary_line(summary: RunSummary) -> str:
    score_display = f"{summary.average_score:.2f}" if summary.average_score is not None else "n/a"
    return (
        f"run={summary.run_id} experiment={summary.experiment} "
        f"tasks={summary.num_tasks} succeeded={summary.num_succeeded} avg_score={score_display}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize Codex evaluation runs.")
    parser.add_argument("--results-dir", default="evals_output", help="Directory with run folders")
    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    results_files = list(iter_results_files(results_dir))

    if not results_files:
        print(f"No results.json found under {results_dir}")
        raise SystemExit(1)

    summaries = [load_run_summary(path) for path in results_files]
    print("Run summaries:")
    for summary in summaries:
        print(f"  - {format_summary_line(summary)}")

    total_tasks = sum(s.num_tasks for s in summaries)
    total_succeeded = sum(s.num_succeeded for s in summaries)
    average_scores = [s.average_score for s in summaries if s.average_score is not None]
    overall_avg = sum(average_scores) / len(average_scores) if average_scores else None

    print("\nAggregate:")
    print(f"  runs={len(summaries)}")
    print(f"  tasks={total_tasks}")
    print(f"  succeeded={total_succeeded}")
    if overall_avg is None:
        print("  avg_score=n/a")
    else:
        print(f"  avg_score={overall_avg:.2f}")


if __name__ == "__main__":
    main()
