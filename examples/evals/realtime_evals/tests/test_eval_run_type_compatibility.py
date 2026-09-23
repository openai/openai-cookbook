import sys
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("streamlit")

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from results_viewer import app as viewer_app
from shared.result_types import (
    EvalErrorInfo,
    ExpectedToolCall,
    NumericMetricSummary,
    OutputTokenUsage,
    ResultLatencies,
    RunEvalRunConfig,
    RunEvalRunSummary,
    RunTurnArtifactPaths,
    RunTurnResult,
    ToolCallGrade,
    ToolCallRecord,
    WalkEvalResult,
)


def test_run_eval_run_summary_coerces_types_and_feeds_results_viewer() -> None:
    config = RunEvalRunConfig(
        run_name="demo",
        assistant_model_default="assistant-model",
        simulator_model_default="simulator-model",
        input_audio_format="pcm16",
        output_audio_format="pcm16",
        chunk_ms=20,
        sample_rate_hz=24000,
        real_time=True,
        data_csv=ROOT_DIR / "run_harness" / "data" / "simulations.csv",
    )

    summary = RunEvalRunSummary.from_flat_summary(
        {
            "total_rows": "5",
            "failed_simulations": "1",
            "grade_mean": "0.75",
            "instruction_following_grade_mean": "0.5",
            "latency_response_done_ms_avg": "410.0",
        },
        config,
    )

    assert isinstance(summary.total_rows, int)
    assert isinstance(summary.failed_simulations, int)
    assert summary.grade_means == {
        "grade_mean": 0.75,
        "instruction_following_grade_mean": 0.5,
    }
    assert summary.latency_response_done_ms == NumericMetricSummary(avg=410.0)

    flat_summary = {
        "run_label": "run_harness/results/demo_run",
        "run_display_label": "demo_run",
        **summary.to_flat_summary(),
    }

    assert viewer_app.available_score_keys([flat_summary]) == [
        "grade_mean",
        "instruction_following_grade_mean",
    ]

    summary_table = viewer_app.build_summary_table(
        summaries=[flat_summary],
        selected_score_keys=viewer_app.available_score_keys([flat_summary]),
        latency_metric_config={
            "Response done latency (ms)": ["latency_response_done_ms_avg"]
        },
        token_metric_config={},
    )

    assert summary_table.loc[0, "run_label"] == "demo_run"
    assert summary_table.loc[0, "assistant_model_default"] == "assistant-model"
    assert summary_table.loc[0, "instruction_following_grade_mean"] == 0.5
    assert summary_table.loc[0, "latency_response_done_ms_avg"] == 410.0

    score_chart = viewer_app.build_score_chart_frame(
        [flat_summary],
        viewer_app.available_score_keys([flat_summary]),
    )
    assert set(score_chart["metric_key"]) == {
        "grade_mean",
        "instruction_following_grade_mean",
    }
    assert "Instruction Following" in set(score_chart["metric_label"])


def test_walk_eval_result_csv_row_uses_repo_absolute_paths_in_results_viewer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(viewer_app, "ROOT_DIR", tmp_path)

    run_directory = tmp_path / "walk_harness" / "results" / "demo_run"
    input_audio_path = tmp_path / "walk_harness" / "data" / "audio" / "cs_001.wav"
    output_audio_path = run_directory / "audio" / "cs_001" / "output.wav"
    event_log_path = run_directory / "events" / "cs_001.jsonl"

    input_audio_path.parent.mkdir(parents=True)
    output_audio_path.parent.mkdir(parents=True)
    event_log_path.parent.mkdir(parents=True)

    input_audio_path.write_bytes(b"RIFF")
    output_audio_path.write_bytes(b"RIFF")
    event_log_path.write_text("{}\n", encoding="utf-8")

    result = WalkEvalResult(
        example_id="cs_001",
        user_text="hello",
        expected_tool_call=ExpectedToolCall(
            name="refund_order",
            arguments_json='{"order_id":"ORD-1"}',
        ),
        assistant_text="Done.",
        tool_calls=[ToolCallRecord(name="refund_order", arguments={"order_id": "ORD-1"})],
        tool_call_grade=ToolCallGrade(
            pred_tool_call="refund_order",
            pred_tool_call_arg='{"order_id":"ORD-1"}',
            tool_call_correctness=1,
            tool_call_arg_correctness=1,
        ),
        audio_path=input_audio_path,
        event_log_path=event_log_path,
        output_audio_path=output_audio_path,
        latencies=ResultLatencies(),
        output_tokens=OutputTokenUsage(),
        error_info=EvalErrorInfo(),
    )

    pd.DataFrame([result.to_csv_row()]).to_csv(run_directory / "results.csv", index=False)

    results, error = viewer_app.load_results_frame(run_directory)

    assert error is None
    assert results is not None

    row = results.iloc[0]
    assert viewer_app.input_audio_path_for_row(run_directory, row) == input_audio_path
    assert viewer_app.output_audio_path_for_row(run_directory, row) == output_audio_path
    assert viewer_app.event_log_path_for_row(run_directory, row) == event_log_path


def test_run_turn_result_csv_row_is_compatible_with_run_viewer_helpers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(viewer_app, "ROOT_DIR", tmp_path)

    run_directory = tmp_path / "run_harness" / "results" / "demo_run"
    audio_dir = run_directory / "audio" / "sim_001"
    user_audio_path = audio_dir / "turn_01_user.wav"
    assistant_audio_path = audio_dir / "turn_01_assistant.wav"
    event_log_path = run_directory / "events" / "sim_001.jsonl"

    user_audio_path.parent.mkdir(parents=True)
    event_log_path.parent.mkdir(parents=True)
    user_audio_path.write_bytes(b"RIFF")
    assistant_audio_path.write_bytes(b"RIFF")
    event_log_path.write_text("{}\n", encoding="utf-8")

    row = RunTurnResult(
        simulation_id="sim_001",
        assistant_model="assistant-model",
        simulator_model="simulator-model",
        turn_index=1,
        user_text="hello",
        assistant_text="done",
        expected_tool_call=ExpectedToolCall(
            name="lookup_order",
            arguments_json='{"order_id":"ORD-1"}',
        ),
        tool_calls=[ToolCallRecord(name="lookup_order", arguments={"order_id": "ORD-1"})],
        tool_outputs=[],
        tool_call_grade=ToolCallGrade(
            pred_tool_call="lookup_order",
            pred_tool_call_arg='{"order_id":"ORD-1"}',
            tool_call_correctness=1,
            tool_call_arg_correctness=1,
        ),
        artifact_paths=RunTurnArtifactPaths(
            user_audio_path=user_audio_path,
            assistant_audio_path=assistant_audio_path,
            event_log_path=event_log_path,
        ),
        latencies=ResultLatencies(),
        output_tokens=OutputTokenUsage(),
        error_info=EvalErrorInfo(),
    )

    pd.DataFrame([row.to_csv_row()]).to_csv(run_directory / "results.csv", index=False)

    results, error = viewer_app.load_results_frame(run_directory)

    assert error is None
    assert results is not None

    loaded_row = results.iloc[0]
    assert (
        viewer_app.simulation_event_log_path_for_row(run_directory, loaded_row)
        == event_log_path
    )
    assert viewer_app.simulation_audio_paths_for_row(run_directory, loaded_row) == [
        user_audio_path,
        assistant_audio_path,
    ]
