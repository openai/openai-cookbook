import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from crawl_harness.run_realtime_evals import build_failed_result as build_crawl_failed_result
from run_harness.run_realtime_evals import build_failed_simulation_result
from shared.result_types import EvalErrorInfo
from walk_harness.run_realtime_evals import build_failed_result as build_walk_failed_result


def test_crawl_failure_row_serializes_error_info() -> None:
    row = pd.Series(
        {
            "example_id": "ex_1",
            "user_text": "hello",
            "gt_tool_call": "refund_order",
            "gt_tool_call_arg": '{"order_id":"ORD-1"}',
        }
    )

    result = build_crawl_failed_result(
        row,
        ROOT_DIR / "crawl_harness" / "results" / "run_1" / "audio",
        ROOT_DIR / "crawl_harness" / "results" / "run_1" / "events",
        EvalErrorInfo(
            status="failed",
            failure_stage="example_execution",
            error_type="RuntimeError",
            error_message="boom",
        ),
    )

    csv_row = result.to_csv_row()
    assert csv_row["status"] == "failed"
    assert csv_row["failure_stage"] == "example_execution"
    assert csv_row["error_message"] == "boom"
    assert csv_row["grade"] == 0


def test_walk_failure_row_handles_missing_audio_path() -> None:
    row = pd.Series(
        {
            "example_id": "ex_2",
            "user_text": "hello",
            "gt_tool_call": "",
            "gt_tool_call_arg": "",
            "audio_path": "",
        }
    )

    result = build_walk_failed_result(
        row,
        ROOT_DIR / "walk_harness" / "data" / "customer_service_synthetic.csv",
        ROOT_DIR / "walk_harness" / "results" / "run_1" / "events",
        EvalErrorInfo(status="failed", error_type="ValueError", error_message="bad row"),
    )

    csv_row = result.to_csv_row()
    assert csv_row["status"] == "failed"
    assert csv_row["audio_path"].endswith("missing_audio.wav")


def test_run_failure_row_uses_turn_zero() -> None:
    row = pd.Series({"simulation_id": "sim_1"})
    args = argparse.Namespace(
        assistant_model="assistant-model",
        model="",
        simulator_model="sim-model",
    )

    result = build_failed_simulation_result(
        row,
        args,
        ROOT_DIR / "run_harness" / "results" / "run_1",
        EvalErrorInfo(
            status="failed",
            failure_stage="simulation_execution",
            error_type="RuntimeError",
            error_message="failure",
        ),
    )

    csv_row = result.rows[0].to_csv_row()
    assert csv_row["simulation_id"] == "sim_1"
    assert csv_row["turn_index"] == 0
    assert csv_row["status"] == "failed"
