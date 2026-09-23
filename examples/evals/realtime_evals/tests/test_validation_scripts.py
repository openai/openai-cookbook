import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shared.scripts.validate_eval_output import validate_output
from shared.scripts.validate_eval_input import validate_input
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
)


def test_validate_input_accepts_valid_run_bundle(tmp_path: Path) -> None:
    assistant_prompt_path = tmp_path / "assistant_prompt.txt"
    tools_path = tmp_path / "tools.json"
    assistant_prompt_path.write_text("Prompt", encoding="utf-8")
    tools_path.write_text("[]\n", encoding="utf-8")

    simulation_path = tmp_path / "sim_demo.json"
    simulation_path.write_text(
        json.dumps(
            {
                "simulation_id": "sim_demo",
                "scenario": "Check order status",
                "assistant": {
                    "system_prompt_file": str(assistant_prompt_path),
                    "tools_file": str(tools_path),
                },
                "simulator": {"system_prompt": "Act like a customer."},
                "audio": {},
                "turns": {"fixed_first_user_turn": "Where is my package?"},
                "tool_mocks": [{"name": "lookup_order", "output": {"status": "ok"}}],
                "expected_tool_call": {
                    "name": "lookup_order",
                    "arguments": {"order_id": "A123"},
                },
                "graders": {
                    "turn_level": [{"id": "instruction_following", "criteria": "Be correct."}],
                    "trace_level": [{"id": "resolved", "criteria": "Issue is resolved."}],
                },
            }
        ),
        encoding="utf-8",
    )

    simulations_csv_path = tmp_path / "simulations.csv"
    pd.DataFrame(
        [{"simulation_id": "sim_demo", "simulation_path": str(simulation_path)}]
    ).to_csv(simulations_csv_path, index=False)

    validate_input("run", simulations_csv_path)


def test_validate_input_rejects_walk_audio_with_wrong_format(tmp_path: Path) -> None:
    dataset_path = tmp_path / "walk.csv"
    invalid_audio_path = tmp_path / "bad.wav"
    invalid_audio_path.write_text("not-a-wave-file", encoding="utf-8")

    pd.DataFrame(
        [
            {
                "example_id": "ex_1",
                "user_text": "hello",
                "gt_tool_call": "",
                "gt_tool_call_arg": "",
                "audio_path": str(invalid_audio_path),
            }
        ]
    ).to_csv(dataset_path, index=False)

    with pytest.raises(ValueError, match="Expected RIFF/WAVE header|Invalid WAV header"):
        validate_input("walk", dataset_path)


def test_validate_output_accepts_valid_run_output(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_harness" / "results" / "demo_run"
    user_audio_path = run_dir / "audio" / "sim_1" / "turn_01_user.wav"
    assistant_audio_path = run_dir / "audio" / "sim_1" / "turn_01_assistant.wav"
    event_log_path = run_dir / "events" / "sim_1.jsonl"
    user_audio_path.parent.mkdir(parents=True)
    event_log_path.parent.mkdir(parents=True)
    user_audio_path.write_bytes(b"RIFF")
    assistant_audio_path.write_bytes(b"RIFF")
    event_log_path.write_text("{}\n", encoding="utf-8")

    row = RunTurnResult(
        simulation_id="sim_1",
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
        tool_call_grade=ToolCallGrade(),
        artifact_paths=RunTurnArtifactPaths(
            user_audio_path=user_audio_path,
            assistant_audio_path=assistant_audio_path,
            event_log_path=event_log_path,
        ),
        latencies=ResultLatencies(response_done_ms=250.0),
        output_tokens=OutputTokenUsage(output_tokens=10),
        error_info=EvalErrorInfo(),
    )
    row.set_grader_result("instruction_following", 1, "ok")

    pd.DataFrame([row.to_csv_row()]).to_csv(run_dir / "results.csv", index=False)

    summary = RunEvalRunSummary(
        total_rows=1,
        failed_simulations=0,
        grade_means={"instruction_following_grade_mean": 1.0},
        config=RunEvalRunConfig(
            run_name="demo_run",
            assistant_model_default="assistant-model",
            simulator_model_default="simulator-model",
            input_audio_format="pcm16",
            output_audio_format="pcm16",
            chunk_ms=20,
            sample_rate_hz=24000,
            real_time=False,
            data_csv=tmp_path / "run_harness" / "data" / "simulations.csv",
        ),
        latency_response_done_ms=NumericMetricSummary(avg=250.0),
    )
    summary_dict = summary.to_flat_summary()
    (run_dir / "summary.json").write_text(
        json.dumps(summary_dict, indent=2),
        encoding="utf-8",
    )

    validate_output("run", run_dir)


def test_validate_output_rejects_missing_run_grade_mean(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_harness" / "results" / "demo_run"
    run_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "simulation_id": "sim_1",
                "assistant_model": "assistant-model",
                "simulator_model": "simulator-model",
                "turn_index": 1,
                "user_text": "hello",
                "assistant_text": "done",
                "tool_calls": "[]",
                "tool_outputs": "[]",
                "user_audio_path": "",
                "assistant_audio_path": "",
                "event_log_path": "",
                "status": "failed",
                "instruction_following_grade": 1,
            }
        ]
    ).to_csv(run_dir / "results.csv", index=False)
    (run_dir / "summary.json").write_text(
        json.dumps(
            {
                "run_name": "demo_run",
                "assistant_model_default": "assistant-model",
                "simulator_model_default": "simulator-model",
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "chunk_ms": 20,
                "sample_rate_hz": 24000,
                "real_time": False,
                "data_csv": str(tmp_path / "run_harness" / "data" / "simulations.csv"),
                "total_rows": 1,
                "failed_simulations": 1,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="instruction_following_grade_mean"):
        validate_output("run", run_dir)
