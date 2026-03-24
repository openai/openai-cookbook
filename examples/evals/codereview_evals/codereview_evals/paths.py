from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = PROJECT_ROOT / "data"
PREPARED_ROOT = DATA_ROOT / "prepared"

HARNESS_DIRS = {
    1: PROJECT_ROOT / "1_basic_benchmark_harness",
    2: PROJECT_ROOT / "2_normalized_benchmark_harness",
    3: PROJECT_ROOT / "3_pairwise_harness",
}


def harness_dir_for_level(level: int) -> Path:
    try:
        return HARNESS_DIRS[level]
    except KeyError as exc:
        raise ValueError(f"Unsupported level: {level}") from exc
