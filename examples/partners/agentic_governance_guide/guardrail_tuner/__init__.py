"""Automated guardrail feedback loop for threshold tuning.

This package provides tools to automatically tune guardrail confidence_threshold
values based on evaluation metrics.

Example:
    from guardrail_tuner import GuardrailFeedbackLoop

    loop = GuardrailFeedbackLoop(
        config_path=Path("eval_config.json"),
        dataset_path=Path("test_data.jsonl"),
        output_dir=Path("tuning_results"),
        precision_target=0.90,
        recall_target=0.90,
    )
    results = await loop.run()
"""

from .feedback_loop import GuardrailFeedbackLoop
from .types import (
    FeedbackLoopConfig,
    TuningTarget,
    TuningResult,
    GuardrailMetrics,
    TuningDirection,
)

__all__ = [
    "GuardrailFeedbackLoop",
    "FeedbackLoopConfig",
    "TuningTarget",
    "TuningResult",
    "GuardrailMetrics",
    "TuningDirection",
]
