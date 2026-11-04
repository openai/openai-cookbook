"""Errors raised by GPT Live assistant lifecycle and delegated tools."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shared.grading.scoring import EvalResult


class LiveResponseError(RuntimeError):
    """A transport, lifecycle, or delegated response failed."""

    def __init__(self, message: str, *, failure_stage: str) -> None:
        super().__init__(message)
        self.failure_stage = failure_stage
        self.partial_result: EvalResult | None = None
