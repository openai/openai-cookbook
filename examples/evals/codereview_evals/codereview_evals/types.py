from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

JSONDict = dict[str, Any]


@dataclass(frozen=True)
class HarnessConfig:
    model: str
    grader_model: str
    reviewer_reasoning_effort: str | None = None
    grader_reasoning_effort: str | None = None
    reviewer_max_output_tokens: int | None = None
    grader_max_output_tokens: int | None = None
    max_concurrency: int = 1


@dataclass(frozen=True)
class RunArtifacts:
    run_dir: Path
    results_json: Path
    results_csv: Path
    summary_json: Path
    report_html: Path
