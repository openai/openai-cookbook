"""Data types for the guardrail feedback loop tuner."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TuningDirection(Enum):
    """Direction to adjust threshold."""
    INCREASE = "increase"  # Raise threshold (improve precision)
    DECREASE = "decrease"  # Lower threshold (improve recall)
    STABLE = "stable"      # No change needed


@dataclass
class TuningTarget:
    """Target metrics for tuning."""
    precision_target: float = 0.90
    recall_target: float = 0.90
    priority: str = "f1"  # "precision", "recall", or "f1"
    tolerance: float = 0.02  # Tolerance for considering metric achieved


@dataclass
class GuardrailMetrics:
    """Metrics for a single guardrail from eval results."""
    precision: float
    recall: float
    f1_score: float
    true_positives: int
    false_positives: int
    false_negatives: int
    true_negatives: int
    total_samples: int


@dataclass
class ThresholdAdjustment:
    """Record of a threshold adjustment."""
    guardrail_name: str
    stage: str
    old_threshold: float
    new_threshold: float
    direction: TuningDirection
    reason: str
    iteration: int


@dataclass
class TuningState:
    """State for a guardrail being tuned."""
    guardrail_name: str
    stage: str
    current_threshold: float
    initial_threshold: float
    threshold_history: list[float] = field(default_factory=list)
    metrics_history: list[GuardrailMetrics] = field(default_factory=list)
    adjustments: list[ThresholdAdjustment] = field(default_factory=list)
    oscillation_count: int = 0
    last_direction: Optional[TuningDirection] = None
    converged: bool = False
    stop_reason: Optional[str] = None


@dataclass
class TuningResult:
    """Final result of the tuning process for a guardrail."""
    guardrail_name: str
    stage: str
    initial_threshold: float
    final_threshold: float
    initial_metrics: Optional[GuardrailMetrics]
    final_metrics: Optional[GuardrailMetrics]
    adjustments: list[ThresholdAdjustment]
    converged: bool
    reason: str
    iterations: int


@dataclass
class FeedbackLoopConfig:
    """Configuration for the feedback loop."""
    max_iterations: int = 10
    step_size: float = 0.05
    min_step_size: float = 0.01
    min_threshold: float = 0.1
    max_threshold: float = 0.95
    oscillation_limit: int = 3
    targets: TuningTarget = field(default_factory=TuningTarget)
