"""Threshold adjustment logic with oscillation prevention."""

import logging
from typing import Optional

from .types import (
    TuningDirection,
    TuningState,
    ThresholdAdjustment,
    FeedbackLoopConfig,
    GuardrailMetrics,
    TuningTarget,
)

logger = logging.getLogger(__name__)


class MetricsAnalyzer:
    """Analyzes evaluation metrics and determines tuning actions."""

    def __init__(self, targets: TuningTarget):
        self.targets = targets

    def calculate_gaps(self, metrics: GuardrailMetrics) -> dict:
        """Calculate gap between current and target metrics."""
        precision_gap = self.targets.precision_target - metrics.precision
        recall_gap = self.targets.recall_target - metrics.recall

        return {
            "precision_gap": precision_gap,
            "recall_gap": recall_gap,
            "precision_achieved": metrics.precision >= (self.targets.precision_target - self.targets.tolerance),
            "recall_achieved": metrics.recall >= (self.targets.recall_target - self.targets.tolerance),
        }

    def determine_direction(self, metrics: GuardrailMetrics) -> TuningDirection:
        """Determine which direction to adjust threshold."""
        gaps = self.calculate_gaps(metrics)

        # Both targets achieved
        if gaps["precision_achieved"] and gaps["recall_achieved"]:
            return TuningDirection.STABLE

        precision_gap = gaps["precision_gap"]
        recall_gap = gaps["recall_gap"]

        # Precision too low, recall acceptable -> increase threshold
        if precision_gap > self.targets.tolerance and recall_gap <= self.targets.tolerance:
            return TuningDirection.INCREASE

        # Recall too low, precision acceptable -> decrease threshold
        if recall_gap > self.targets.tolerance and precision_gap <= self.targets.tolerance:
            return TuningDirection.DECREASE

        # Both below target -> use priority or larger gap
        if self.targets.priority == "precision":
            return TuningDirection.INCREASE
        elif self.targets.priority == "recall":
            return TuningDirection.DECREASE
        else:  # F1 priority - choose direction with larger gap
            return TuningDirection.INCREASE if precision_gap > recall_gap else TuningDirection.DECREASE

    def metrics_improved(self, old: GuardrailMetrics, new: GuardrailMetrics) -> bool:
        """Check if metrics improved based on priority."""
        if self.targets.priority == "precision":
            return new.precision >= old.precision
        elif self.targets.priority == "recall":
            return new.recall >= old.recall
        else:
            return new.f1_score >= old.f1_score


class ThresholdAdjuster:
    """Adjusts thresholds with oscillation prevention."""

    def __init__(self, config: FeedbackLoopConfig):
        self.config = config
        self.states: dict[str, TuningState] = {}
        self.analyzer = MetricsAnalyzer(config.targets)

    def _state_key(self, stage: str, guardrail_name: str) -> str:
        """Generate unique key for guardrail state."""
        return f"{stage}:{guardrail_name}"

    def get_or_create_state(
        self, stage: str, guardrail_name: str, current_threshold: float
    ) -> TuningState:
        """Get existing state or create new one."""
        key = self._state_key(stage, guardrail_name)
        if key not in self.states:
            self.states[key] = TuningState(
                guardrail_name=guardrail_name,
                stage=stage,
                current_threshold=current_threshold,
                initial_threshold=current_threshold,
            )
        return self.states[key]

    def get_state(self, stage: str, guardrail_name: str) -> Optional[TuningState]:
        """Get state for a guardrail if it exists."""
        key = self._state_key(stage, guardrail_name)
        return self.states.get(key)

    def calculate_adjustment(
        self,
        state: TuningState,
        metrics: GuardrailMetrics,
        iteration: int,
    ) -> Optional[ThresholdAdjustment]:
        """Calculate threshold adjustment with oscillation detection."""
        direction = self.analyzer.determine_direction(metrics)

        if direction == TuningDirection.STABLE:
            state.converged = True
            state.stop_reason = "Targets achieved"
            return None

        # Detect oscillation (direction changed from last time)
        if state.last_direction is not None and state.last_direction != direction:
            state.oscillation_count += 1
            logger.info(
                f"  {state.guardrail_name}: Oscillation detected "
                f"({state.last_direction.value} -> {direction.value}), "
                f"count={state.oscillation_count}"
            )

            if state.oscillation_count >= self.config.oscillation_limit:
                state.converged = True
                state.stop_reason = f"Oscillation limit reached ({self.config.oscillation_limit})"
                return ThresholdAdjustment(
                    guardrail_name=state.guardrail_name,
                    stage=state.stage,
                    old_threshold=state.current_threshold,
                    new_threshold=state.current_threshold,
                    direction=TuningDirection.STABLE,
                    reason=state.stop_reason,
                    iteration=iteration,
                )

        # Calculate step size (reduce on oscillation)
        step = self.config.step_size
        if state.oscillation_count > 0:
            step = max(
                self.config.min_step_size,
                step / (2**state.oscillation_count),
            )

        # Calculate new threshold
        if direction == TuningDirection.INCREASE:
            new_threshold = min(
                self.config.max_threshold,
                state.current_threshold + step,
            )
            reason = f"Precision below target, increasing threshold by {step:.3f}"
        else:
            new_threshold = max(
                self.config.min_threshold,
                state.current_threshold - step,
            )
            reason = f"Recall below target, decreasing threshold by {step:.3f}"

        # Round to 3 decimal places
        new_threshold = round(new_threshold, 3)

        # Check if we hit bounds
        if new_threshold == state.current_threshold:
            state.converged = True
            state.stop_reason = "Threshold at bounds limit"
            return ThresholdAdjustment(
                guardrail_name=state.guardrail_name,
                stage=state.stage,
                old_threshold=state.current_threshold,
                new_threshold=new_threshold,
                direction=TuningDirection.STABLE,
                reason=state.stop_reason,
                iteration=iteration,
            )

        adjustment = ThresholdAdjustment(
            guardrail_name=state.guardrail_name,
            stage=state.stage,
            old_threshold=state.current_threshold,
            new_threshold=new_threshold,
            direction=direction,
            reason=reason,
            iteration=iteration,
        )

        # Update state
        state.threshold_history.append(state.current_threshold)
        state.metrics_history.append(metrics)
        state.adjustments.append(adjustment)
        state.current_threshold = new_threshold
        state.last_direction = direction

        return adjustment

    def should_continue_tuning(self, stage: str, guardrail_name: str) -> bool:
        """Check if guardrail should continue tuning."""
        state = self.get_state(stage, guardrail_name)
        if not state:
            return True
        return not state.converged

    def update_metrics(
        self, stage: str, guardrail_name: str, metrics: GuardrailMetrics
    ) -> None:
        """Update the latest metrics for a guardrail."""
        state = self.get_state(stage, guardrail_name)
        if state:
            state.metrics_history.append(metrics)
