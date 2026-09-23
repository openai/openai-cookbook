from __future__ import annotations

from typing import Any

from .graders import Grader
from .runners import ImageEditRunner, ImageGenerationRunner
from .storage import OutputStore
from .types import ModelRun, Score, TestCase


def _as_score_list(score_or_scores: Score | list[Score]) -> list[Score]:
    if isinstance(score_or_scores, list):
        return score_or_scores
    return [score_or_scores]


def evaluate(
    *,
    cases: list[TestCase],
    model_runs: list[ModelRun],
    graders: list[Grader],
    output_store: OutputStore,
) -> list[dict[str, Any]]:
    gen_runner = ImageGenerationRunner()
    edit_runner = ImageEditRunner()

    results: list[dict[str, Any]] = []

    for case in cases:
        for run_cfg in model_runs:
            if run_cfg.task_type != case.task_type:
                continue

            if case.task_type == "image_generation":
                response = gen_runner.run(case, run_cfg, output_store)
            elif case.task_type == "image_editing":
                response = edit_runner.run(case, run_cfg, output_store)
            else:
                raise ValueError(f"Unknown task_type: {case.task_type}")

            score_map: dict[str, Any] = {}
            reason_map: dict[str, str] = {}

            for grader in graders:
                scored = grader.grade(response, case)
                for score in _as_score_list(scored):
                    score_map[score.key] = score.value
                    reason_map[score.key] = score.reason

            results.append(
                {
                    "test_id": case.id,
                    "model_label": run_cfg.label,
                    "task_type": case.task_type,
                    "artifact_paths": [str(a.path) for a in response.artifacts],
                    "scores": score_map,
                    "reasons": reason_map,
                    "run_params": run_cfg.params,
                }
            )

    return results
