"""Validation shared by metric projection and portable result reporting."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from shared.grading.scoring import EvalResult


class ResultValidationError(ValueError):
    """A record is not trustworthy enough to grade as a target-model result."""

    failure_stage = "result_validation"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.partial_result: EvalResult | None = None


def require_task_completed(record: Mapping[str, Any]) -> bool:
    value = record.get("task_completed")
    if type(value) is not bool:
        raise ResultValidationError("task_completed must be an explicitly observed boolean")
    return value


def result_status(record: Mapping[str, Any], *, completed: bool) -> str:
    status = record.get("status", "")
    if not isinstance(status, str) or status not in {
        "",
        "ok",
        "passed",
        "failed",
        "incomplete",
        "error",
        "infrastructure_error",
    }:
        raise ResultValidationError("status must be a supported result status")
    if status in {"infrastructure_error", "error"} or (status == "failed" and record.get("failure_stage")):
        return "infrastructure_error"
    return "passed" if completed else "failed"


def validation_failure_row(record: Mapping[str, Any], error: ResultValidationError) -> dict[str, Any]:
    """Retain the record's evidence links and primary error without grading it."""
    return {
        **record,
        "status": "infrastructure_error",
        "task_completed": False,
        "failure_stage": record.get("failure_stage") or error.failure_stage,
        "error_message": record.get("error_message") or str(error),
        "semantic_dimension_scores": {},
        "semantic_evaluation_status": "not_assessed",
    }
