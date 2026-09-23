"""Generate styled plots for an existing realtime eval run."""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shared.plotting_utils import build_realtime_eval_plots


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render styled plots for an existing realtime eval run."
    )
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--harness-label", type=str, default="")
    parser.add_argument("--run-label", type=str, default="")
    return parser.parse_args()


def infer_harness_label(run_dir: Path) -> str:
    parent_name = run_dir.parent.name.strip()
    if parent_name == "results" and run_dir.parent.parent.name:
        name = run_dir.parent.parent.name.replace("_", " ").strip()
    else:
        name = parent_name.replace("_", " ").strip()
    if name.endswith("harness"):
        return name
    return "realtime eval"


def main() -> None:
    args = parse_args()
    run_dir = args.run_dir.resolve()
    results_csv_path = run_dir / "results.csv"
    summary_json_path = run_dir / "summary.json"
    output_dir = (args.output_dir or (run_dir / "plots")).resolve()

    results = pd.read_csv(results_csv_path)
    summary = json.loads(summary_json_path.read_text(encoding="utf-8"))
    harness_label = args.harness_label or infer_harness_label(run_dir)
    run_label = args.run_label or run_dir.name

    plot_paths = build_realtime_eval_plots(
        results=results,
        summary=summary,
        output_dir=output_dir,
        harness_label=harness_label,
        run_name=run_label,
    )

    print(f"Wrote {len(plot_paths)} plot(s) to {output_dir}")
    for plot_path in plot_paths:
        print(f"- {plot_path}")


if __name__ == "__main__":
    main()
