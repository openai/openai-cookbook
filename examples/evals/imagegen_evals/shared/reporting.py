from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def default_run_id(run_name: str) -> str:
    if run_name:
        return run_name
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def summarize_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "total_examples": len(results),
    }
    score_keys = sorted({key for item in results for key in item.get("scores", {}).keys()})

    for key in score_keys:
        values = [
            item["scores"][key]
            for item in results
            if key in item.get("scores", {})
        ]
        bool_values = [value for value in values if isinstance(value, bool)]
        numeric_values = [
            value
            for value in values
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        ]
        string_values = [value for value in values if isinstance(value, str)]

        if bool_values:
            summary[f"{key}_pass_rate"] = sum(bool_values) / len(bool_values)
        if numeric_values:
            summary[f"{key}_avg"] = sum(numeric_values) / len(numeric_values)
        if string_values:
            summary[f"{key}_counts"] = dict(Counter(string_values))

    return summary


def save_results(run_dir: Path, results: list[dict[str, Any]]) -> dict[str, Any]:
    ensure_dir(run_dir)
    (run_dir / "results.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    pd.DataFrame(results).to_csv(run_dir / "results.csv", index=False)

    summary = summarize_results(results)
    (run_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return summary
