from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

JSONDict = dict[str, Any]


@dataclass(frozen=True)
class PreparedDatasetArtifacts:
    cache_key: str
    level: int
    dataset_path: Path
    prepared_dir: Path
    record_count: int


@dataclass(frozen=True)
class EvalRunArtifacts:
    cache_key: str
    level: int
    run_dir: Path
    uploaded_file_json: Path
    eval_json: Path
    run_json: Path
    output_items_json: Path | None
    summary_json: Path
    dataset_path: Path
