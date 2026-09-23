"""Main feedback loop for automated guardrail threshold tuning."""

import asyncio
import copy
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from guardrails.evals.guardrail_evals import GuardrailEval

from .types import (
    FeedbackLoopConfig,
    TuningResult,
    TuningTarget,
    GuardrailMetrics,
    TuningDirection,
)
from .threshold_adjuster import ThresholdAdjuster

logger = logging.getLogger(__name__)


class GuardrailFeedbackLoop:
    """Automated feedback loop for tuning guardrail confidence thresholds.

    This class runs guardrail evaluations, analyzes precision/recall metrics,
    and automatically adjusts confidence_threshold values to meet target metrics.

    Example:
        loop = GuardrailFeedbackLoop(
            config_path=Path("eval_config.json"),
            dataset_path=Path("test_data.jsonl"),
            output_dir=Path("tuning_results"),
            precision_target=0.90,
            recall_target=0.90,
        )
        results = await loop.run()
    """

    def __init__(
        self,
        config_path: Path,
        dataset_path: Path,
        output_dir: Path,
        precision_target: float = 0.90,
        recall_target: float = 0.90,
        priority: str = "f1",
        max_iterations: int = 10,
        step_size: float = 0.05,
        loop_config: Optional[FeedbackLoopConfig] = None,
    ):
        """Initialize the feedback loop.

        Args:
            config_path: Path to the guardrail configuration JSON file.
            dataset_path: Path to the evaluation dataset (JSONL format).
            output_dir: Directory for output files (tuned config, reports).
            precision_target: Target precision to achieve (default 0.90).
            recall_target: Target recall to achieve (default 0.90).
            priority: Which metric to prioritize when both are below target.
                     Options: "precision", "recall", "f1" (default).
            max_iterations: Maximum tuning iterations (default 10).
            step_size: Initial threshold adjustment step (default 0.05).
            loop_config: Optional FeedbackLoopConfig for advanced configuration.
        """
        self.config_path = Path(config_path)
        self.dataset_path = Path(dataset_path)
        self.output_dir = Path(output_dir)

        # Build config from parameters or use provided config
        if loop_config:
            self.loop_config = loop_config
        else:
            self.loop_config = FeedbackLoopConfig(
                max_iterations=max_iterations,
                step_size=step_size,
                targets=TuningTarget(
                    precision_target=precision_target,
                    recall_target=recall_target,
                    priority=priority,
                ),
            )

        self.adjuster = ThresholdAdjuster(self.loop_config)

        # Config state
        self._original_config: Optional[dict] = None
        self._current_config: Optional[dict] = None

        # Results
        self.results: list[TuningResult] = []

    def _load_config(self) -> dict:
        """Load guardrail configuration from file."""
        with open(self.config_path) as f:
            self._original_config = json.load(f)
            self._current_config = copy.deepcopy(self._original_config)
        return self._current_config

    def _get_tunable_guardrails(self) -> list[dict]:
        """Find guardrails that have confidence_threshold configured."""
        guardrails = []
        for stage in ["input", "output", "pre_flight"]:
            stage_config = self._current_config.get(stage, {})
            for gr in stage_config.get("guardrails", []):
                config = gr.get("config", {})
                if "confidence_threshold" in config:
                    guardrails.append({
                        "stage": stage,
                        "name": gr["name"],
                        "config": config,
                        "threshold": config["confidence_threshold"],
                    })
        return guardrails

    def _update_threshold(
        self, stage: str, guardrail_name: str, new_threshold: float
    ) -> None:
        """Update threshold for a specific guardrail in current config."""
        stage_config = self._current_config.get(stage, {})
        for gr in stage_config.get("guardrails", []):
            if gr["name"] == guardrail_name:
                gr["config"]["confidence_threshold"] = round(new_threshold, 3)
                return
        raise ValueError(f"Guardrail {guardrail_name} not found in {stage}")

    def _save_config(self, path: Path) -> None:
        """Save current config to file."""
        with open(path, "w") as f:
            json.dump(self._current_config, f, indent=2)

    def _parse_metrics(self, metrics_path: Path) -> dict[str, dict[str, GuardrailMetrics]]:
        """Parse eval_metrics.json into GuardrailMetrics objects."""
        with open(metrics_path) as f:
            raw_metrics = json.load(f)

        result = {}
        for stage, guardrails in raw_metrics.items():
            if not isinstance(guardrails, dict):
                continue
            result[stage] = {}
            for name, m in guardrails.items():
                if not isinstance(m, dict):
                    continue
                result[stage][name] = GuardrailMetrics(
                    precision=m.get("precision", 0.0),
                    recall=m.get("recall", 0.0),
                    f1_score=m.get("f1_score", 0.0),
                    true_positives=m.get("true_positives", 0),
                    false_positives=m.get("false_positives", 0),
                    false_negatives=m.get("false_negatives", 0),
                    true_negatives=m.get("true_negatives", 0),
                    total_samples=m.get("total_samples", 0),
                )
        return result

    async def _run_eval(
        self, run_name: str, config_path: Optional[Path] = None
    ) -> dict[str, dict[str, GuardrailMetrics]]:
        """Run evaluation and return metrics."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        eval_output = self.output_dir / f"eval_{run_name}_{timestamp}"
        eval_output.mkdir(parents=True, exist_ok=True)

        evaluator = GuardrailEval(
            config_path=config_path or self.config_path,
            dataset_path=self.dataset_path,
            output_dir=eval_output,
        )

        await evaluator.run()

        # Find metrics file
        metrics_file = eval_output / "eval_metrics.json"
        if not metrics_file.exists():
            # Check subdirectories (eval sometimes creates nested dirs)
            for subdir in eval_output.iterdir():
                if subdir.is_dir():
                    possible = subdir / "eval_metrics.json"
                    if possible.exists():
                        metrics_file = possible
                        break

        if not metrics_file.exists():
            raise FileNotFoundError(f"eval_metrics.json not found in {eval_output}")

        return self._parse_metrics(metrics_file)

    def _generate_report(self) -> Path:
        """Generate markdown tuning report."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = self.output_dir / f"tuning_report_{timestamp}.md"

        lines = [
            "# Guardrail Tuning Report",
            f"\nGenerated: {datetime.now().isoformat()}",
            f"\nTargets: precision={self.loop_config.targets.precision_target}, "
            f"recall={self.loop_config.targets.recall_target}, "
            f"priority={self.loop_config.targets.priority}",
            "\n## Results\n",
        ]

        for result in self.results:
            status = "CONVERGED" if result.converged else "STOPPED"

            # Calculate improvement
            improvement = ""
            if result.initial_metrics and result.final_metrics:
                delta = result.final_metrics.f1_score - result.initial_metrics.f1_score
                if delta > 0:
                    improvement = f" (+{delta:.3f} F1)"
                elif delta < 0:
                    improvement = f" ({delta:.3f} F1)"

            lines.append(f"### {result.guardrail_name} ({result.stage})")
            lines.append(f"- **Status**: {status} - {result.reason}")
            lines.append(
                f"- **Threshold**: {result.initial_threshold:.3f} -> "
                f"{result.final_threshold:.3f}"
            )

            if result.initial_metrics and result.final_metrics:
                lines.append(
                    f"- **Precision**: {result.initial_metrics.precision:.3f} -> "
                    f"{result.final_metrics.precision:.3f}"
                )
                lines.append(
                    f"- **Recall**: {result.initial_metrics.recall:.3f} -> "
                    f"{result.final_metrics.recall:.3f}"
                )
                lines.append(
                    f"- **F1 Score**: {result.initial_metrics.f1_score:.3f} -> "
                    f"{result.final_metrics.f1_score:.3f}{improvement}"
                )

            lines.append(f"- **Iterations**: {result.iterations}")
            lines.append("")

        with open(report_path, "w") as f:
            f.write("\n".join(lines))

        return report_path

    async def run(self) -> list[TuningResult]:
        """Execute the feedback loop.

        Returns:
            List of TuningResult objects, one per tunable guardrail.
        """
        logger.info("Starting guardrail feedback loop")

        # Setup output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Load config and identify tunable guardrails
        self._load_config()
        tunable = self._get_tunable_guardrails()

        if not tunable:
            logger.warning("No guardrails with confidence_threshold found")
            return []

        logger.info(
            f"Found {len(tunable)} tunable guardrails: "
            f"{[g['name'] for g in tunable]}"
        )

        # Save backup of original config
        backup_dir = self.output_dir / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = backup_dir / f"config_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(backup_path, "w") as f:
            json.dump(self._original_config, f, indent=2)
        logger.info(f"Saved config backup to {backup_path}")

        # Initialize states for all tunable guardrails
        for g in tunable:
            self.adjuster.get_or_create_state(g["stage"], g["name"], g["threshold"])

        # Run initial evaluation
        logger.info("Running initial evaluation")
        current_metrics = await self._run_eval("initial")

        # Store initial metrics
        for g in tunable:
            stage_metrics = current_metrics.get(g["stage"], {})
            if g["name"] in stage_metrics:
                self.adjuster.update_metrics(
                    g["stage"], g["name"], stage_metrics[g["name"]]
                )

        # Iteration loop
        for iteration in range(1, self.loop_config.max_iterations + 1):
            logger.info(f"=== Iteration {iteration}/{self.loop_config.max_iterations} ===")

            any_adjustments = False

            for gr in tunable:
                name = gr["name"]
                stage = gr["stage"]

                if not self.adjuster.should_continue_tuning(stage, name):
                    state = self.adjuster.get_state(stage, name)
                    logger.info(f"  {name}: Skipping ({state.stop_reason})")
                    continue

                state = self.adjuster.get_state(stage, name)
                stage_metrics = current_metrics.get(stage, {})
                metrics = stage_metrics.get(name)

                if not metrics:
                    logger.warning(f"  {name}: No metrics found, skipping")
                    continue

                # Log current state
                gaps = self.adjuster.analyzer.calculate_gaps(metrics)
                logger.info(
                    f"  {name}: P={metrics.precision:.3f} R={metrics.recall:.3f} "
                    f"F1={metrics.f1_score:.3f} "
                    f"(gaps: P={gaps['precision_gap']:.3f}, R={gaps['recall_gap']:.3f})"
                )

                # Calculate adjustment
                adjustment = self.adjuster.calculate_adjustment(state, metrics, iteration)

                if adjustment and adjustment.direction != TuningDirection.STABLE:
                    logger.info(
                        f"  {name}: {adjustment.old_threshold:.3f} -> "
                        f"{adjustment.new_threshold:.3f} ({adjustment.reason})"
                    )
                    self._update_threshold(stage, name, adjustment.new_threshold)
                    any_adjustments = True
                elif adjustment:
                    logger.info(f"  {name}: {adjustment.reason}")

            if not any_adjustments:
                logger.info("No adjustments needed, stopping loop")
                break

            # Save updated config and re-run eval
            temp_config = self.output_dir / f"config_iter_{iteration}.json"
            self._save_config(temp_config)

            logger.info("Re-running evaluation with updated thresholds")
            current_metrics = await self._run_eval(f"iter_{iteration}", config_path=temp_config)

            # Update metrics in states
            for gr in tunable:
                stage_metrics = current_metrics.get(gr["stage"], {})
                if gr["name"] in stage_metrics:
                    self.adjuster.update_metrics(
                        gr["stage"], gr["name"], stage_metrics[gr["name"]]
                    )

        # Generate results
        self.results = []
        for gr in tunable:
            state = self.adjuster.get_state(gr["stage"], gr["name"])
            if not state:
                continue

            initial_metrics = state.metrics_history[0] if state.metrics_history else None
            final_metrics = state.metrics_history[-1] if state.metrics_history else None

            self.results.append(
                TuningResult(
                    guardrail_name=gr["name"],
                    stage=gr["stage"],
                    initial_threshold=state.initial_threshold,
                    final_threshold=state.current_threshold,
                    initial_metrics=initial_metrics,
                    final_metrics=final_metrics,
                    adjustments=state.adjustments,
                    converged=state.converged,
                    reason=state.stop_reason or "Max iterations reached",
                    iterations=len(state.adjustments),
                )
            )

        # Save final tuned config
        final_config_path = self.output_dir / "eval_config_tuned.json"
        self._save_config(final_config_path)
        logger.info(f"Saved tuned config to {final_config_path}")

        # Generate report
        report_path = self._generate_report()
        logger.info(f"Generated report at {report_path}")

        return self.results
