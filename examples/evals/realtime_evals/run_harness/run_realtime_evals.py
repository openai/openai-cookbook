"""Realtime eval run harness runner.

Model-simulated multi-turn harness that uses a realtime model as the user
(simulator) and another realtime model as the assistant under test. It streams
simulator audio into the assistant with fixed chunking, mocks tools
deterministically, and records full traces.

Results:
  run_harness/results/<run_id>/results.csv
  run_harness/results/<run_id>/summary.json
  run_harness/results/<run_id>/events/<simulation_id>.jsonl
"""

import argparse
import asyncio
import concurrent.futures
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, cast

import pandas as pd
from openai import AsyncOpenAI, BadRequestError, OpenAI
from openai.types.realtime import RealtimeSessionCreateRequestParam
from tqdm import tqdm

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shared.graders import compute_tool_call_grade
from shared.metrics_utils import add_grade_means, add_numeric_summaries, order_columns
from shared.realtime_harness_utils import (
    audio_format_config,
    collect_realtime_response,
    ensure_dir,
    stream_audio_to_connection,
    write_pcm16_wav,
)

DEFAULT_DATA_CSV = ROOT_DIR / "run_harness" / "data" / "simulations.csv"
DEFAULT_RESULTS_DIR = ROOT_DIR / "run_harness" / "results"
DEFAULT_ASSISTANT_MODEL = "gpt-realtime"
DEFAULT_SIMULATOR_MODEL = "gpt-realtime"
DEFAULT_JUDGE_MODEL = "gpt-5.1"
DEFAULT_CHUNK_MS = 20
DEFAULT_SAMPLE_RATE_HZ = 24000
DEFAULT_INPUT_AUDIO_FORMAT = "pcm16"
DEFAULT_OUTPUT_AUDIO_FORMAT = "pcm16"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run realtime multi-turn evals with a user simulator."
    )
    parser.add_argument("--data-csv", type=Path, default=DEFAULT_DATA_CSV)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--run-name", type=str, default="")
    parser.add_argument("--model", type=str, default="")
    parser.add_argument("--assistant-model", type=str, default="")
    parser.add_argument("--simulator-model", type=str, default="")
    parser.add_argument("--system-prompt-file", type=Path, default=None)
    parser.add_argument("--tools-file", type=Path, default=None)
    parser.add_argument("--assistant-system-prompt-file", type=Path, default=None)
    parser.add_argument("--assistant-tools-file", type=Path, default=None)
    parser.add_argument("--simulator-system-prompt", type=str, default="")
    parser.add_argument("--chunk-ms", type=int, default=DEFAULT_CHUNK_MS)
    parser.add_argument("--sample-rate-hz", type=int, default=DEFAULT_SAMPLE_RATE_HZ)
    parser.add_argument(
        "--input-audio-format", type=str, default=DEFAULT_INPUT_AUDIO_FORMAT
    )
    parser.add_argument(
        "--output-audio-format", type=str, default=DEFAULT_OUTPUT_AUDIO_FORMAT
    )
    parser.add_argument(
        "--real-time", action="store_true", help="Send audio at real-time cadence."
    )
    parser.add_argument("--max-turns", type=int, default=0)
    parser.add_argument("--max-examples", type=int, default=0)
    parser.add_argument("--judge-model", type=str, default=DEFAULT_JUDGE_MODEL)
    return parser.parse_args()


def resolve_path(path_value: str, base_dir: Path) -> Path:
    if not path_value:
        raise ValueError("Path value is empty")
    candidate = Path(path_value)
    if not candidate.is_absolute():
        candidate = base_dir / candidate
    return candidate


def load_system_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def load_tools(path: Path) -> List[Dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_simulation_index(path: Path) -> pd.DataFrame:
    data = pd.read_csv(path)
    required_columns = {"simulation_id", "simulation_path"}
    missing = required_columns.difference(data.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")
    return data


def load_simulation(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def extract_json_object(text: str) -> Dict[str, Any]:
    if not text:
        return {}
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {}
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {}


def compute_tool_outputs(
    tool_calls: List[Dict[str, Any]], tool_mocks: Dict[str, Dict[str, Any]]
) -> List[Dict[str, Any]]:
    outputs = []
    for call in tool_calls:
        tool_name = call.get("name", "")
        output = tool_mocks.get(tool_name, {"status": "Unsupported tool"})
        outputs.append(
            {
                "call_id": call.get("call_id", ""),
                "name": tool_name,
                "arguments": call.get("arguments", {}),
                "output": output,
            }
        )
    return outputs


def build_tool_output_by_call_id(
    tool_outputs: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    outputs_by_call_id: Dict[str, Dict[str, Any]] = {}
    for output in tool_outputs:
        call_id = output.get("call_id", "")
        if not call_id:
            continue
        outputs_by_call_id[call_id] = output
    return outputs_by_call_id


def transcript_lines_for_assistant_turn(
    turn_index: int,
    response_segments: List[Dict[str, Any]],
    tool_outputs_by_call_id: Dict[str, Dict[str, Any]],
) -> List[str]:
    lines: List[str] = []
    for segment in response_segments:
        assistant_text = str(segment.get("assistant_text", "")).strip()
        if assistant_text:
            lines.append(f"TURN {turn_index} ASSISTANT: {assistant_text}")
        for tool_call in segment.get("tool_calls", []):
            lines.append(f"TURN {turn_index} TOOL_CALL: {json.dumps(tool_call)}")
            call_id = str(tool_call.get("call_id", "")).strip()
            if call_id and call_id in tool_outputs_by_call_id:
                lines.append(
                    f"TURN {turn_index} TOOL_OUTPUT: "
                    f"{json.dumps(tool_outputs_by_call_id[call_id])}"
                )
    return lines


def build_simulator_prompt_text(
    history: List[Dict[str, str]], fixed_first_turn: str, turn_index: int
) -> str:
    if turn_index == 1:
        return f"Repeat exactly the following user utterance:\n{fixed_first_turn}"

    lines = ["Conversation so far:"]
    for message in history:
        role = message["role"].capitalize()
        lines.append(f"{role}: {message['text']}")
    lines.append("Next user response:")
    return "\n".join(lines)


def build_turn_context(
    simulation_id: str,
    scenario: str,
    turn_index: int,
    user_text: str,
    assistant_text: str,
    tool_calls: List[Dict[str, Any]],
    tool_outputs: List[Dict[str, Any]],
) -> str:
    return (
        f"Simulation: {simulation_id}\n"
        f"Scenario: {scenario}\n"
        f"Turn: {turn_index}\n"
        f"User: {user_text}\n"
        f"Assistant: {assistant_text}\n"
        f"Tool Calls: {json.dumps(tool_calls)}\n"
        f"Tool Outputs: {json.dumps(tool_outputs)}\n"
    )


def build_trace_context(
    simulation_id: str,
    scenario: str,
    transcript_lines: List[str],
    tool_summaries: List[str],
) -> str:
    transcript_text = "\n".join(transcript_lines)
    tool_text = "\n".join(tool_summaries)
    return (
        f"Simulation: {simulation_id}\n"
        f"Scenario: {scenario}\n"
        "Conversation:\n"
        f"{transcript_text}\n"
        "Tools:\n"
        f"{tool_text}\n"
    )


def run_llm_grade(
    client: OpenAI,
    model: str,
    criteria: str,
    context_text: str,
) -> Dict[str, Any]:
    instructions = (
        "You are a strict evaluator. Return JSON only with keys "
        "grade (0 or 1) and rationale (short)."
    )
    response_input = f"Criteria:\n{criteria}\n\nContext:\n{context_text}"
    # A strict schema makes grading deterministic and easy to parse downstream.
    grade_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "grade": {"type": "integer", "enum": [0, 1]},
            "rationale": {"type": "string"},
        },
        "required": ["grade", "rationale"],
    }
    try:
        # Structured outputs keeps grading deterministic and easier to parse.
        response = client.responses.create(
            model=model,
            instructions=instructions,
            input=response_input,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "grade_result",
                    "strict": True,
                    "schema": grade_schema,
                }
            },
        )
    except BadRequestError:
        # Some judge models may not support json_schema yet; keep a tight fallback.
        response = client.responses.create(
            model=model,
            instructions=instructions,
            input=response_input,
        )

    output_text = response.output_text.strip()
    try:
        parsed = json.loads(output_text)
    except json.JSONDecodeError:
        # This should be rare with structured outputs, but handle it defensively.
        parsed = extract_json_object(output_text)
    grade_value = parsed.get("grade")
    normalized_grade = 1 if grade_value in (1, True) else 0
    return {
        "grade": normalized_grade,
        "rationale": parsed.get("rationale", ""),
        "raw_output": output_text,
    }


def execute_grade_job(job: Dict[str, Any]) -> Dict[str, Any]:
    client = OpenAI()
    grade_result = run_llm_grade(client, job["model"], job["criteria"], job["context"])
    return {
        "row_indices": job["row_indices"],
        "grader_id": job["grader_id"],
        "grade": grade_result["grade"],
        "rationale": grade_result["rationale"],
    }


def compute_summary(results: pd.DataFrame) -> Dict[str, Any]:
    summary: Dict[str, Any] = {
        "total_rows": int(results.shape[0]),
    }

    add_grade_means(summary, results)
    add_numeric_summaries(
        summary,
        results,
        [
            "latency_first_audio_ms",
            "latency_first_text_ms",
            "latency_response_done_ms",
            "output_tokens",
            "output_audio_tokens",
            "output_text_tokens",
        ],
    )

    return summary


def order_result_columns(results: pd.DataFrame) -> pd.DataFrame:
    preferred = [
        "simulation_id",
        "assistant_model",
        "simulator_model",
        "turn_index",
        "user_text",
        "assistant_text",
        "tool_calls",
        "tool_outputs",
        "pred_tool_call",
        "pred_tool_call_arg",
        "user_audio_path",
        "assistant_audio_path",
        "latency_first_audio_ms",
        "latency_first_text_ms",
        "latency_response_done_ms",
        "output_tokens",
        "output_audio_tokens",
        "output_text_tokens",
    ]
    return order_columns(results, preferred)


async def run_simulation(
    async_client: AsyncOpenAI,
    simulation_row: pd.Series,
    args: argparse.Namespace,
    run_dir: Path,
) -> Dict[str, Any]:
    simulation_path = resolve_path(
        str(simulation_row["simulation_path"]), args.data_csv.parent
    )
    simulation = load_simulation(simulation_path)

    simulation_id = simulation.get(
        "simulation_id", str(simulation_row["simulation_id"])
    )
    scenario = simulation.get("scenario", "")

    assistant_config = simulation.get("assistant", {})
    simulator_config = simulation.get("simulator", {})
    audio_config = simulation.get("audio", {})
    turns_config = simulation.get("turns", {})

    assistant_model = (
        args.assistant_model
        or args.model
        or assistant_config.get("model", DEFAULT_ASSISTANT_MODEL)
    )
    simulator_model = args.simulator_model or simulator_config.get(
        "model", DEFAULT_SIMULATOR_MODEL
    )

    assistant_prompt_path = args.assistant_system_prompt_file or args.system_prompt_file
    if assistant_prompt_path is None:
        assistant_prompt_path = resolve_path(
            assistant_config.get("system_prompt_file", ""), ROOT_DIR
        )

    assistant_tools_path = args.assistant_tools_file or args.tools_file
    if assistant_tools_path is None:
        assistant_tools_path = resolve_path(
            assistant_config.get("tools_file", ""), ROOT_DIR
        )

    simulator_prompt = args.simulator_system_prompt or simulator_config.get(
        "system_prompt", ""
    )

    if not simulator_prompt:
        raise ValueError(f"Missing simulator system_prompt in {simulation_path}")

    system_prompt = load_system_prompt(assistant_prompt_path)
    tools = load_tools(assistant_tools_path)

    input_audio_format = audio_config.get("input_format", args.input_audio_format)
    output_audio_format = audio_config.get("output_format", args.output_audio_format)
    sample_rate_hz = int(audio_config.get("sample_rate_hz", args.sample_rate_hz))
    chunk_ms = int(audio_config.get("chunk_ms", args.chunk_ms))
    real_time = bool(audio_config.get("real_time", args.real_time))

    max_turns = int(turns_config.get("max_turns", 0))
    max_turns_override = simulation_row.get("max_turns_override")
    if max_turns_override is not None and not pd.isna(max_turns_override):
        override_value = int(max_turns_override)
        if override_value > 0:
            max_turns = override_value
    if args.max_turns > 0:
        max_turns = args.max_turns
    if max_turns <= 0:
        max_turns = 1

    fixed_first_turn = turns_config.get("fixed_first_user_turn", "")
    tool_mocks_list = simulation.get("tool_mocks", [])
    tool_mocks = {
        entry.get("name", ""): entry.get("output", {}) for entry in tool_mocks_list
    }
    expected_tool_call = simulation.get("expected_tool_call", {})
    expected_tool_name = str(expected_tool_call.get("name", "")).strip()
    expected_tool_args = expected_tool_call.get("arguments", {})
    expected_tool_args_text = (
        json.dumps(expected_tool_args) if expected_tool_args else ""
    )

    graders = simulation.get("graders", {})
    turn_level_graders = graders.get("turn_level", [])
    trace_level_graders = graders.get("trace_level", [])
    tool_call_grader_ids = [
        grader.get("id", "tool_call")
        for grader in turn_level_graders
        if grader.get("type") == "tool_call"
    ]
    tool_call_args_grader_ids = [
        grader.get("id", "tool_call_args")
        for grader in turn_level_graders
        if grader.get("type") == "tool_call_args"
    ]

    run_audio_dir = run_dir / "audio" / simulation_id
    run_events_dir = run_dir / "events"
    run_conv_dir = run_dir / "conversations"
    ensure_dir(run_audio_dir)
    ensure_dir(run_events_dir)
    ensure_dir(run_conv_dir)

    trace_path = run_events_dir / f"{simulation_id}.jsonl"
    transcript_path = run_conv_dir / f"{simulation_id}.txt"

    conversation_history: List[Dict[str, str]] = []
    transcript_lines: List[str] = []
    tool_summaries: List[str] = []

    results_rows: List[Dict[str, Any]] = []
    turn_grade_requests: List[Dict[str, Any]] = []
    trace_grade_requests: List[Dict[str, Any]] = []
    any_tool_call_correctness = 0
    any_tool_call_arg_correctness = 0
    tool_call_correctness_flags: List[int] = []

    assistant_voice = assistant_config.get("voice", "")
    simulator_voice = simulator_config.get("voice", "")

    # Disable turn detection (VAD) for both connections so this harness controls turn
    # boundaries explicitly via `input_audio_buffer.commit()` (important for comparability).
    assistant_session: Dict[str, Any] = {
        "type": "realtime",
        "instructions": system_prompt,
        "tools": tools,
        "tool_choice": "auto",
        "audio": {
            "input": {
                "format": audio_format_config(input_audio_format, sample_rate_hz),
                "turn_detection": None,
            },
            "output": {
                "format": audio_format_config(output_audio_format, sample_rate_hz)
            },
        },
    }
    if assistant_voice:
        assistant_session["audio"]["output"]["voice"] = assistant_voice

    simulator_session: Dict[str, Any] = {
        "type": "realtime",
        "instructions": simulator_prompt,
        "tools": [],
        "tool_choice": "none",
        "audio": {
            "input": {
                "format": audio_format_config(input_audio_format, sample_rate_hz),
                "turn_detection": None,
            },
            "output": {
                "format": audio_format_config(output_audio_format, sample_rate_hz)
            },
        },
    }
    if simulator_voice:
        simulator_session["audio"]["output"]["voice"] = simulator_voice

    event_index_state = {"value": 0}

    # Keep both sessions open across turns; rely on server-side conversation state.
    async with async_client.realtime.connect(
        model=simulator_model
    ) as simulator_connection, async_client.realtime.connect(
        model=assistant_model
    ) as assistant_connection:
        await simulator_connection.session.update(
            session=cast(RealtimeSessionCreateRequestParam, simulator_session)
        )
        await assistant_connection.session.update(
            session=cast(RealtimeSessionCreateRequestParam, assistant_session)
        )

        with trace_path.open("w", encoding="utf-8") as trace_file:
            for turn_index in range(1, max_turns + 1):
                if turn_index == 1 and not fixed_first_turn:
                    raise ValueError(
                        f"Missing fixed_first_user_turn for {simulation_id}"
                    )

                simulator_prompt_text = build_simulator_prompt_text(
                    conversation_history, fixed_first_turn, turn_index
                )

                simulator_payload: Dict[str, Any] = {}
                if turn_index == 1:
                    simulator_payload["instructions"] = (
                        "Output exactly this user utterance and nothing else: "
                        f"{fixed_first_turn}"
                    )
                simulator_payload["input"] = [
                    {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": simulator_prompt_text}
                        ],
                    }
                ]
                # Keep simulator turns out of the assistant's conversation state.
                simulator_payload["conversation"] = "none"

                # Collect the simulator's audio/text output and log the full event stream.
                simulator_result = await collect_realtime_response(
                    simulator_connection,
                    simulator_payload,
                    log_file=trace_file,
                    event_index_state=event_index_state,
                    source="simulator",
                    turn_index=turn_index,
                )

                user_text = simulator_result["assistant_text"] or fixed_first_turn
                user_audio_bytes = simulator_result["output_audio_bytes"]

                user_audio_path = run_audio_dir / f"turn_{turn_index:02d}_user.wav"
                if user_audio_bytes:
                    write_pcm16_wav(user_audio_path, user_audio_bytes, sample_rate_hz)

                transcript_lines.append(f"TURN {turn_index} USER: {user_text}")
                if "END_CALL" in user_text.upper():
                    break
                conversation_history.append({"role": "user", "text": user_text})

                await stream_audio_to_connection(
                    assistant_connection,
                    user_audio_bytes,
                    chunk_ms,
                    sample_rate_hz,
                    input_audio_format,
                    real_time,
                    # Pad very short utterances so the assistant reliably responds.
                    minimum_duration_seconds=0.1,
                )

                assistant_payload: Dict[str, Any] = {}

                assistant_result = await collect_realtime_response(
                    assistant_connection,
                    assistant_payload,
                    log_file=trace_file,
                    event_index_state=event_index_state,
                    source="assistant",
                    turn_index=turn_index,
                    tool_mocks=tool_mocks,
                )

                assistant_text = assistant_result["assistant_text"]
                assistant_segments = assistant_result.get("response_segments", [])
                assistant_audio_bytes = assistant_result["output_audio_bytes"]
                tool_calls = assistant_result["tool_calls"]
                tool_outputs = compute_tool_outputs(tool_calls, tool_mocks)
                tool_outputs_by_call_id = build_tool_output_by_call_id(tool_outputs)
                tool_call_grade_data = compute_tool_call_grade(
                    expected_tool_name,
                    expected_tool_args_text,
                    tool_calls,
                )
                # Track whether any turn matched the expected tool behavior.
                tool_call_correctness_flags.append(
                    tool_call_grade_data.get("tool_call_correctness", 0)
                )
                if tool_call_grade_data.get("tool_call_correctness") == 1:
                    any_tool_call_correctness = 1
                if tool_call_grade_data.get("tool_call_arg_correctness") == 1:
                    any_tool_call_arg_correctness = 1

                assistant_audio_path = (
                    run_audio_dir / f"turn_{turn_index:02d}_assistant.wav"
                )
                if assistant_audio_bytes:
                    write_pcm16_wav(
                        assistant_audio_path, assistant_audio_bytes, sample_rate_hz
                    )

                transcript_lines.extend(
                    transcript_lines_for_assistant_turn(
                        turn_index, assistant_segments, tool_outputs_by_call_id
                    )
                )
                if not assistant_segments and assistant_text:
                    # Keep backwards-compatible transcript output if no segment metadata is available.
                    transcript_lines.append(
                        f"TURN {turn_index} ASSISTANT: {assistant_text}"
                    )
                conversation_history.append(
                    {"role": "assistant", "text": assistant_text}
                )

                if tool_calls:
                    for tool_call in tool_calls:
                        tool_summaries.append(
                            f"TURN {turn_index} TOOL_CALL: {json.dumps(tool_call)}"
                        )
                        call_id = str(tool_call.get("call_id", "")).strip()
                        if call_id and call_id in tool_outputs_by_call_id:
                            tool_summaries.append(
                                f"TURN {turn_index} TOOL_OUTPUT: "
                                f"{json.dumps(tool_outputs_by_call_id[call_id])}"
                            )

                turn_context = build_turn_context(
                    simulation_id,
                    scenario,
                    turn_index,
                    user_text,
                    assistant_text,
                    tool_calls,
                    tool_outputs,
                )

                usage_data = assistant_result.get("usage", {})
                output_tokens = usage_data.get("output_tokens")
                output_audio_tokens = None
                output_text_tokens = None
                if "output_token_details" in usage_data:
                    output_details = usage_data["output_token_details"]
                    output_audio_tokens = output_details.get("audio_tokens")
                    output_text_tokens = output_details.get("text_tokens")

                row_data = {
                    "simulation_id": simulation_id,
                    "assistant_model": assistant_model,
                    "simulator_model": simulator_model,
                    "turn_index": turn_index,
                    "user_text": user_text,
                    "assistant_text": assistant_text,
                    "tool_calls": json.dumps(tool_calls),
                    "tool_outputs": json.dumps(tool_outputs),
                    "pred_tool_call": tool_call_grade_data.get("pred_tool_call", ""),
                    "pred_tool_call_arg": tool_call_grade_data.get(
                        "pred_tool_call_arg", ""
                    ),
                    "user_audio_path": str(user_audio_path),
                    "assistant_audio_path": str(assistant_audio_path),
                    "event_log_path": str(trace_path),
                    "latency_first_audio_ms": assistant_result["first_audio_time_ms"],
                    "latency_first_text_ms": assistant_result["first_text_time_ms"],
                    "latency_response_done_ms": assistant_result[
                        "response_done_time_ms"
                    ],
                    "output_tokens": output_tokens,
                    "output_audio_tokens": output_audio_tokens,
                    "output_text_tokens": output_text_tokens,
                }
                results_rows.append(row_data)
                for grader in turn_level_graders:
                    if grader.get("type") != "llm_as_judge":
                        continue
                    turn_grade_requests.append(
                        {
                            "simulation_id": simulation_id,
                            "turn_index": turn_index,
                            "grader_id": grader.get("id", "turn_grader"),
                            "criteria": grader.get("criteria", ""),
                            "model": grader.get("model", args.judge_model),
                            "context": turn_context,
                        }
                    )

    trace_context = build_trace_context(
        simulation_id, scenario, transcript_lines, tool_summaries
    )

    transcript_path.write_text("\n".join(transcript_lines), encoding="utf-8")
    if not expected_tool_name and tool_call_correctness_flags:
        if all(flag == 1 for flag in tool_call_correctness_flags):
            any_tool_call_correctness = 1
            any_tool_call_arg_correctness = 1
        else:
            any_tool_call_correctness = 0
            any_tool_call_arg_correctness = 0

    if tool_call_grader_ids or tool_call_args_grader_ids:
        for row_data in results_rows:
            for grader_id in tool_call_grader_ids:
                row_data[f"{grader_id}_grade"] = any_tool_call_correctness
                row_data[f"{grader_id}_rationale"] = ""
            for grader_id in tool_call_args_grader_ids:
                row_data[f"{grader_id}_grade"] = any_tool_call_arg_correctness
                row_data[f"{grader_id}_rationale"] = ""

    for grader in trace_level_graders:
        if grader.get("type") != "llm_as_judge":
            continue
        trace_grade_requests.append(
            {
                "simulation_id": simulation_id,
                "grader_id": grader.get("id", "trace_grader"),
                "criteria": grader.get("criteria", ""),
                "model": grader.get("model", args.judge_model),
                "context": trace_context,
            }
        )

    return {
        "rows": results_rows,
        "turn_grade_requests": turn_grade_requests,
        "trace_grade_requests": trace_grade_requests,
        "simulation_id": simulation_id,
    }


async def run_evals() -> None:
    args = parse_args()

    dataset = load_simulation_index(args.data_csv)

    if "enabled" in dataset.columns:
        dataset = dataset[dataset["enabled"].astype(str).str.lower() == "true"]

    if args.max_examples > 0:
        dataset = dataset.head(args.max_examples)

    run_timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_name = args.run_name or run_timestamp
    run_dir = args.results_dir / run_name
    ensure_dir(run_dir)

    async_client = AsyncOpenAI()

    all_rows: List[Dict[str, Any]] = []
    turn_grade_requests: List[Dict[str, Any]] = []
    trace_grade_requests: List[Dict[str, Any]] = []
    simulation_row_indices: Dict[str, List[int]] = {}

    total_simulations = int(dataset.shape[0])
    print(f"Running run harness: {total_simulations} simulations -> {run_dir}")
    for _, row in tqdm(dataset.iterrows(), total=total_simulations, desc="Run evals"):
        simulation_result = await run_simulation(async_client, row, args, run_dir)
        rows = simulation_result["rows"]
        simulation_id = simulation_result["simulation_id"]
        offset = len(all_rows)
        all_rows.extend(rows)
        simulation_row_indices[simulation_id] = list(range(offset, offset + len(rows)))

        for request in simulation_result["turn_grade_requests"]:
            row_index = offset + request["turn_index"] - 1
            turn_grade_requests.append(
                {
                    "row_indices": [row_index],
                    "grader_id": request["grader_id"],
                    "criteria": request["criteria"],
                    "model": request["model"],
                    "context": request["context"],
                }
            )

        for request in simulation_result["trace_grade_requests"]:
            row_indices = simulation_row_indices.get(request["simulation_id"], [])
            trace_grade_requests.append(
                {
                    "row_indices": row_indices,
                    "grader_id": request["grader_id"],
                    "criteria": request["criteria"],
                    "model": request["model"],
                    "context": request["context"],
                }
            )

    grade_jobs = turn_grade_requests + trace_grade_requests
    if grade_jobs:
        max_workers = min(8, len(grade_jobs))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            for result in executor.map(execute_grade_job, grade_jobs):
                for row_index in result["row_indices"]:
                    all_rows[row_index][f"{result['grader_id']}_grade"] = result[
                        "grade"
                    ]
                    all_rows[row_index][f"{result['grader_id']}_rationale"] = result[
                        "rationale"
                    ]

    results_df = pd.DataFrame(all_rows)
    results_df = order_result_columns(results_df)
    results_csv_path = run_dir / "results.csv"
    results_df.to_csv(results_csv_path, index=False)

    summary = compute_summary(results_df)
    summary.update(
        {
            "run_name": run_name,
            "assistant_model_default": args.assistant_model or args.model or "",
            "simulator_model_default": args.simulator_model or "",
            "input_audio_format": args.input_audio_format,
            "output_audio_format": args.output_audio_format,
            "chunk_ms": args.chunk_ms,
            "sample_rate_hz": args.sample_rate_hz,
            "real_time": args.real_time,
            "data_csv": str(args.data_csv),
        }
    )

    summary_path = run_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    grade_keys = sorted(key for key in summary.keys() if key.endswith("_grade_mean"))
    grade_notes = " ".join(f"{key}={summary.get(key, 0):.3f}" for key in grade_keys)
    print(
        "Summary:"
        f" total_rows={summary.get('total_rows', 0)}"
        f"{(' ' + grade_notes) if grade_notes else ''}"
    )
    print(f"Wrote results to {run_dir}")


def main() -> None:
    asyncio.run(run_evals())


if __name__ == "__main__":
    main()
