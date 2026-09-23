import json
import sys
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shared.plotting_utils import build_realtime_eval_plots


def test_build_realtime_eval_plots_writes_expected_files(tmp_path: Path) -> None:
    results = pd.DataFrame(
        {
            "status": ["ok", "ok", "failed", "ok"],
            "failure_stage": ["", "", "response_timeout", ""],
            "grade": [1, 1, 0, 1],
            "turn_index": [1, 2, 1, 2],
            "latency_first_audio_ms": [180, 210, 260, 220],
            "latency_first_text_ms": [220, 255, 320, 280],
            "latency_response_done_ms": [480, 540, 760, 610],
            "output_tokens": [48, 57, 72, 60],
            "output_audio_tokens": [30, 35, 44, 38],
            "output_text_tokens": [18, 22, 28, 22],
        }
    )
    summary = {
        "total_rows": 4,
        "failed_simulations": 1,
        "grade_mean": 0.75,
        "latency_first_audio_ms_p50": 215.0,
        "latency_first_audio_ms_p95": 254.0,
        "latency_first_audio_ms_p99": 258.8,
        "latency_first_text_ms_p50": 267.5,
        "latency_first_text_ms_p95": 314.0,
        "latency_first_text_ms_p99": 318.8,
        "latency_response_done_ms_p50": 575.0,
        "latency_response_done_ms_p95": 737.5,
        "latency_response_done_ms_p99": 755.5,
        "output_tokens_avg": 59.25,
        "output_tokens_p50": 58.5,
        "output_tokens_p95": 70.2,
        "output_audio_tokens_avg": 36.75,
        "output_audio_tokens_p50": 36.5,
        "output_audio_tokens_p95": 43.1,
        "output_text_tokens_avg": 22.5,
        "output_text_tokens_p50": 22.0,
        "output_text_tokens_p95": 27.1,
    }

    plot_paths = build_realtime_eval_plots(
        results=results,
        summary=summary,
        output_dir=tmp_path,
        harness_label="run harness",
        run_name="smoke-run",
    )

    assert {path.name for path in plot_paths} == {
        "scorecard.png",
        "detail_panels.png",
        "turn_trends.png",
    }
    for plot_path in plot_paths:
        assert plot_path.exists()
        assert plot_path.stat().st_size > 0


def test_plot_eval_results_cli_infers_labels(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_harness" / "results" / "demo_run"
    run_dir.mkdir(parents=True)

    pd.DataFrame(
        {
            "status": ["ok"],
            "grade": [1],
            "latency_response_done_ms": [400],
            "output_tokens": [50],
        }
    ).to_csv(run_dir / "results.csv", index=False)
    (run_dir / "summary.json").write_text(
        json.dumps(
            {
                "total_rows": 1,
                "failed_simulations": 0,
                "grade_mean": 1.0,
                "latency_response_done_ms_p50": 400.0,
                "latency_response_done_ms_p95": 400.0,
                "latency_response_done_ms_p99": 400.0,
                "output_tokens_avg": 50.0,
                "output_tokens_p50": 50.0,
                "output_tokens_p95": 50.0,
            }
        ),
        encoding="utf-8",
    )

    from plot_eval_results import infer_harness_label

    assert infer_harness_label(run_dir) == "run harness"
