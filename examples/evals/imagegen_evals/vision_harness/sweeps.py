from __future__ import annotations

from itertools import product
from typing import Any

from .types import ModelRun, TaskType


def grid_sweep(
    *,
    base_label: str,
    task_type: TaskType,
    fixed: dict[str, Any],
    grid: dict[str, list[Any]],
) -> list[ModelRun]:
    keys = list(grid.keys())
    runs: list[ModelRun] = []

    for values in product(*[grid[k] for k in keys]):
        params = dict(fixed)
        label_parts = [base_label]
        for k, v in zip(keys, values):
            params[k] = v
            label_parts.append(f"{k}={v}")
        runs.append(ModelRun(label=",".join(label_parts), task_type=task_type, params=params))

    return runs
