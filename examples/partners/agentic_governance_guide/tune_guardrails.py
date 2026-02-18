#!/usr/bin/env python
"""CLI for automated guardrail threshold tuning.

This script runs the guardrail feedback loop to automatically tune
confidence_threshold values based on evaluation metrics.

Example:
    python tune_guardrails.py \\
        --config eval_data/eval_config.json \\
        --dataset eval_data/guardrail_test_data.jsonl \\
        --precision-target 0.90 \\
        --recall-target 0.90
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from guardrail_tuner import GuardrailFeedbackLoop


def main():
    parser = argparse.ArgumentParser(
        description="Automatically tune guardrail confidence thresholds",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage with default targets (0.90 precision and recall)
  python tune_guardrails.py --config config.json --dataset test_data.jsonl

  # Custom targets prioritizing precision
  python tune_guardrails.py --config config.json --dataset test_data.jsonl \\
      --precision-target 0.95 --recall-target 0.85 --priority precision

  # More iterations with smaller steps
  python tune_guardrails.py --config config.json --dataset test_data.jsonl \\
      --max-iterations 20 --step-size 0.02
        """,
    )

    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Path to guardrail configuration JSON file",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        required=True,
        help="Path to evaluation dataset (JSONL format)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("tuning_results"),
        help="Output directory for results (default: tuning_results)",
    )
    parser.add_argument(
        "--precision-target",
        type=float,
        default=0.90,
        help="Target precision to achieve (default: 0.90)",
    )
    parser.add_argument(
        "--recall-target",
        type=float,
        default=0.90,
        help="Target recall to achieve (default: 0.90)",
    )
    parser.add_argument(
        "--priority",
        choices=["precision", "recall", "f1"],
        default="f1",
        help="Which metric to prioritize when both below target (default: f1)",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=10,
        help="Maximum tuning iterations (default: 10)",
    )
    parser.add_argument(
        "--step-size",
        type=float,
        default=0.05,
        help="Initial threshold adjustment step size (default: 0.05)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    # Validate inputs
    if not args.config.exists():
        print(f"Error: Config file not found: {args.config}", file=sys.stderr)
        sys.exit(1)

    if not args.dataset.exists():
        print(f"Error: Dataset file not found: {args.dataset}", file=sys.stderr)
        sys.exit(1)

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Create and run feedback loop
    loop = GuardrailFeedbackLoop(
        config_path=args.config,
        dataset_path=args.dataset,
        output_dir=args.output,
        precision_target=args.precision_target,
        recall_target=args.recall_target,
        priority=args.priority,
        max_iterations=args.max_iterations,
        step_size=args.step_size,
    )

    results = asyncio.run(loop.run())

    # Print summary
    print(f"\n{'=' * 60}")
    print("TUNING COMPLETE")
    print(f"{'=' * 60}")

    if not results:
        print("\nNo guardrails with confidence_threshold found in config.")
        return

    for r in results:
        status = "CONVERGED" if r.converged else "STOPPED"
        print(f"\n{r.guardrail_name} ({r.stage}):")
        print(f"  Status: {status} - {r.reason}")
        print(f"  Threshold: {r.initial_threshold:.3f} -> {r.final_threshold:.3f}")

        if r.initial_metrics and r.final_metrics:
            print(
                f"  Precision: {r.initial_metrics.precision:.3f} -> "
                f"{r.final_metrics.precision:.3f}"
            )
            print(
                f"  Recall: {r.initial_metrics.recall:.3f} -> "
                f"{r.final_metrics.recall:.3f}"
            )
            print(
                f"  F1: {r.initial_metrics.f1_score:.3f} -> "
                f"{r.final_metrics.f1_score:.3f}"
            )

    print(f"\nTuned config saved to: {args.output / 'eval_config_tuned.json'}")
    print(f"Report saved to: {args.output}")


if __name__ == "__main__":
    main()
