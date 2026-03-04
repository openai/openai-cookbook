import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from run_harness.run_realtime_evals import (
    apply_turn_level_tool_grades,
    trace_grade_row_indices,
)
from shared.result_types import (
    CrawlEvalResult,
    EvalErrorInfo,
    ExpectedToolCall,
    OutputTokenUsage,
    ResultArtifactPaths,
    ResultLatencies,
    RunTurnArtifactPaths,
    RunTurnResult,
    ToolCallGrade,
    ToolCallRecord,
    WalkEvalResult,
)
from walk_harness.run_realtime_evals import parse_args as parse_walk_args


def test_crawl_result_csv_row_omits_tool_arg_columns_when_disabled() -> None:
    result = CrawlEvalResult(
        example_id="ex_1",
        user_text="hello",
        expected_tool_call=ExpectedToolCall(
            name="refund_order", arguments_json='{"order_id":"ORD-1"}'
        ),
        assistant_text="I can help with that.",
        tool_calls=[ToolCallRecord(name="refund_order", arguments={"order_id": "ORD-1"})],
        tool_call_grade=ToolCallGrade(
            pred_tool_call="refund_order",
            pred_tool_call_arg='{"order_id":"ORD-1"}',
            tool_call_correctness=1,
            tool_call_arg_correctness=1,
        ),
        artifact_paths=ResultArtifactPaths(
            input_audio_path=ROOT_DIR / "crawl_harness" / "results" / "input.wav",
            event_log_path=ROOT_DIR / "crawl_harness" / "results" / "event.jsonl",
        ),
        latencies=ResultLatencies(),
        output_tokens=OutputTokenUsage(),
        error_info=EvalErrorInfo(),
    )

    csv_row = result.to_csv_row(
        include_tool_call_columns=True,
        include_tool_call_arg_columns=False,
    )

    assert "gt_tool_call" in csv_row
    assert "tool_call_correctness" in csv_row
    assert "gt_tool_call_arg" not in csv_row
    assert "tool_call_arg_correctness" not in csv_row
    assert "grade" not in csv_row


def test_walk_result_csv_row_omits_all_tool_columns_when_disabled() -> None:
    result = WalkEvalResult(
        example_id="ex_2",
        user_text="hello",
        expected_tool_call=ExpectedToolCall(
            name="refund_order", arguments_json='{"order_id":"ORD-1"}'
        ),
        assistant_text="Done.",
        tool_calls=[],
        tool_call_grade=ToolCallGrade(),
        audio_path=ROOT_DIR / "walk_harness" / "data" / "audio.wav",
        event_log_path=ROOT_DIR / "walk_harness" / "results" / "event.jsonl",
        output_audio_path=None,
        latencies=ResultLatencies(),
        output_tokens=OutputTokenUsage(),
        error_info=EvalErrorInfo(),
    )

    csv_row = result.to_csv_row(
        include_tool_call_columns=False,
        include_tool_call_arg_columns=False,
    )

    assert "gt_tool_call" not in csv_row
    assert "pred_tool_call" not in csv_row
    assert "gt_tool_call_arg" not in csv_row
    assert "pred_tool_call_arg" not in csv_row
    assert "grade" not in csv_row


def test_run_result_csv_row_uses_enabled_grader_union() -> None:
    row = RunTurnResult(
        simulation_id="sim_1",
        assistant_model="assistant",
        simulator_model="simulator",
        turn_index=1,
        user_text="hello",
        assistant_text="done",
        expected_tool_call=ExpectedToolCall(
            name="lookup_order", arguments_json='{"order_id":"ORD-1"}'
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
            user_audio_path=ROOT_DIR / "run_harness" / "results" / "user.wav",
            assistant_audio_path=ROOT_DIR / "run_harness" / "results" / "assistant.wav",
            event_log_path=ROOT_DIR / "run_harness" / "results" / "event.jsonl",
        ),
        latencies=ResultLatencies(),
        output_tokens=OutputTokenUsage(),
        error_info=EvalErrorInfo(),
    )
    row.set_grader_result("instruction_following", 1, "All rules followed.")

    csv_row = row.to_csv_row(
        include_tool_call_columns=False,
        include_tool_call_arg_columns=False,
    )

    assert "gt_tool_call" not in csv_row
    assert "tool_call_correctness" not in csv_row
    assert "instruction_following_grade" in csv_row
    assert csv_row["instruction_following_rationale"] == "All rules followed."


def test_apply_turn_level_tool_grades_keeps_results_row_local() -> None:
    row = RunTurnResult(
        simulation_id="sim_1",
        assistant_model="assistant",
        simulator_model="simulator",
        turn_index=2,
        user_text="hello",
        assistant_text="done",
        expected_tool_call=ExpectedToolCall(
            name="lookup_order", arguments_json='{"order_id":"ORD-1"}'
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
            user_audio_path=ROOT_DIR / "run_harness" / "results" / "user.wav",
            assistant_audio_path=ROOT_DIR / "run_harness" / "results" / "assistant.wav",
            event_log_path=ROOT_DIR / "run_harness" / "results" / "event.jsonl",
        ),
        latencies=ResultLatencies(),
        output_tokens=OutputTokenUsage(),
        error_info=EvalErrorInfo(),
    )

    apply_turn_level_tool_grades(
        row,
        ["order_status_tool_call"],
        ["order_status_tool_call_args"],
    )

    csv_row = row.to_csv_row(
        include_tool_call_columns=True,
        include_tool_call_arg_columns=True,
    )
    assert csv_row["order_status_tool_call_grade"] == 1
    assert csv_row["order_status_tool_call_args_grade"] == 1


def test_trace_grade_row_indices_targets_last_row_only() -> None:
    assert trace_grade_row_indices([]) == []
    assert trace_grade_row_indices([4, 5, 6]) == [6]


def test_walk_parse_args_does_not_expose_max_output_tokens() -> None:
    original_argv = sys.argv
    try:
        sys.argv = ["walk_harness/run_realtime_evals.py"]
        args = parse_walk_args()
    finally:
        sys.argv = original_argv

    assert not hasattr(args, "max_output_tokens")
