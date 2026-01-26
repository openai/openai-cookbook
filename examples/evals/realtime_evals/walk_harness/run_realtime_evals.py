"""Realtime eval walk harness runner.

Replay saved G.711 mu-law WAV audio deterministically with fixed chunking and
manual turn commits (VAD off) to keep runs comparable.

How to run:
1) Generate audio (one-time): python walk_harness/generate_audio.py
2) Run evals: python walk_harness/run_realtime_evals.py
3) Quick check: python walk_harness/run_realtime_evals.py --max-examples 2
"""

import argparse
import asyncio
import json
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, cast

import pandas as pd
from openai import AsyncOpenAI
from openai.types.realtime import (
    RealtimeResponseCreateParamsParam,
    RealtimeSessionCreateRequestParam,
)
from tqdm import tqdm

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shared.graders import compute_tool_call_grade
from shared.metrics_utils import add_numeric_summaries, order_columns
from shared.realtime_harness_utils import (
    audio_format_config,
    collect_realtime_response,
    ensure_dir,
    stream_audio_to_connection,
    write_pcm16_wav,
)

SHARED_DIR = ROOT_DIR / "shared"
DEFAULT_DATA_CSV = ROOT_DIR / "walk_harness" / "data" / "customer_service_synthetic.csv"
DEFAULT_RESULTS_DIR = ROOT_DIR / "walk_harness" / "results"
DEFAULT_SYSTEM_PROMPT_PATH = SHARED_DIR / "system_prompt.txt"
DEFAULT_TOOLS_PATH = SHARED_DIR / "tools.json"

DEFAULT_MODEL = "gpt-realtime"
DEFAULT_VOICE = "marin"
DEFAULT_CHUNK_MS = 20
DEFAULT_SAMPLE_RATE_HZ = 8000
DEFAULT_INPUT_AUDIO_FORMAT = "g711_ulaw"
DEFAULT_OUTPUT_AUDIO_FORMAT = "pcm16"
DEFAULT_OUTPUT_SAMPLE_RATE_HZ = 24000
DEFAULT_MAX_OUTPUT_TOKENS = 512


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run realtime walk evals with saved-audio replay."
    )
    parser.add_argument("--data-csv", type=Path, default=DEFAULT_DATA_CSV)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--run-name", type=str, default="")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL)
    parser.add_argument(
        "--system-prompt-file", type=Path, default=DEFAULT_SYSTEM_PROMPT_PATH
    )
    parser.add_argument("--tools-file", type=Path, default=DEFAULT_TOOLS_PATH)
    parser.add_argument("--voice", type=str, default=DEFAULT_VOICE)
    parser.add_argument("--chunk-ms", type=int, default=DEFAULT_CHUNK_MS)
    parser.add_argument("--sample-rate-hz", type=int, default=DEFAULT_SAMPLE_RATE_HZ)
    parser.add_argument(
        "--input-audio-format", type=str, default=DEFAULT_INPUT_AUDIO_FORMAT
    )
    parser.add_argument(
        "--output-audio-format", type=str, default=DEFAULT_OUTPUT_AUDIO_FORMAT
    )
    parser.add_argument(
        "--output-sample-rate-hz", type=int, default=DEFAULT_OUTPUT_SAMPLE_RATE_HZ
    )
    parser.add_argument(
        "--max-output-tokens", type=int, default=DEFAULT_MAX_OUTPUT_TOKENS
    )
    parser.add_argument(
        "--real-time", action="store_true", help="Send audio at real-time cadence."
    )
    parser.add_argument(
        "--max-examples",
        type=int,
        default=0,
        help="Limit number of examples for quick checks.",
    )
    return parser.parse_args()


def load_system_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def load_tools(path: Path) -> List[Dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_dataset(path: Path) -> pd.DataFrame:
    data = pd.read_csv(path)
    required_columns = {
        "example_id",
        "user_text",
        "gt_tool_call",
        "gt_tool_call_arg",
        "audio_path",
    }
    missing = required_columns.difference(data.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")
    return data


def read_ulaw_wav(audio_path: Path, expected_sample_rate_hz: int) -> bytes:
    data = audio_path.read_bytes()
    if len(data) < 12:
        raise ValueError(f"Invalid WAV header in {audio_path}")

    riff_id = data[0:4]
    wave_id = data[8:12]
    if riff_id != b"RIFF" or wave_id != b"WAVE":
        raise ValueError(f"Expected RIFF/WAVE header in {audio_path}")

    offset = 12
    fmt_info: Dict[str, int] = {}
    data_bytes = None

    while offset + 8 <= len(data):
        chunk_id = data[offset : offset + 4]
        chunk_size = struct.unpack_from("<I", data, offset + 4)[0]
        chunk_start = offset + 8
        chunk_end = chunk_start + chunk_size
        if chunk_end > len(data):
            raise ValueError(f"Invalid chunk size in {audio_path}")

        if chunk_id == b"fmt ":
            if chunk_size < 16:
                raise ValueError(f"Invalid fmt chunk in {audio_path}")
            (
                audio_format,
                num_channels,
                sample_rate_hz,
                byte_rate,
                block_align,
                bits_per_sample,
            ) = struct.unpack_from("<HHIIHH", data, chunk_start)
            fmt_info = {
                "audio_format": audio_format,
                "num_channels": num_channels,
                "sample_rate_hz": sample_rate_hz,
                "byte_rate": byte_rate,
                "block_align": block_align,
                "bits_per_sample": bits_per_sample,
            }
        elif chunk_id == b"data":
            data_bytes = data[chunk_start:chunk_end]

        offset = chunk_end if chunk_size % 2 == 0 else chunk_end + 1

    if not fmt_info:
        raise ValueError(f"Missing fmt chunk in {audio_path}")
    if data_bytes is None:
        raise ValueError(f"Missing data chunk in {audio_path}")

    if fmt_info["audio_format"] != 7:
        raise ValueError(f"Expected mu-law WAV format tag 7 in {audio_path}")
    if fmt_info["num_channels"] != 1:
        raise ValueError(f"Expected mono audio in {audio_path}")
    if fmt_info["bits_per_sample"] != 8:
        raise ValueError(f"Expected 8-bit mu-law audio in {audio_path}")
    if fmt_info["sample_rate_hz"] != expected_sample_rate_hz:
        raise ValueError(
            f"Expected sample rate {expected_sample_rate_hz} Hz but got {fmt_info['sample_rate_hz']} in {audio_path}"
        )

    return data_bytes


def resolve_audio_path(audio_path_value: str, dataset_path: Path) -> Path:
    if not audio_path_value:
        raise ValueError("audio_path is empty")
    audio_path = Path(audio_path_value)
    if not audio_path.is_absolute():
        audio_path = dataset_path.parent / audio_path
    return audio_path


async def run_single_eval(
    async_client: AsyncOpenAI,
    row: pd.Series,
    system_prompt: str,
    tools: List[Dict[str, Any]],
    run_audio_dir: Path,
    events_dir: Path,
    config: Dict[str, Any],
    dataset_path: Path,
) -> Dict[str, Any]:
    example_id = str(row["example_id"])
    user_text = str(row["user_text"])
    expected_tool_call = (
        "" if bool(pd.isna(row["gt_tool_call"])) else str(row["gt_tool_call"])
    )
    expected_tool_call_arg = (
        "" if bool(pd.isna(row["gt_tool_call_arg"])) else str(row["gt_tool_call_arg"])
    )

    audio_path = resolve_audio_path(str(row["audio_path"]), dataset_path)

    if config["input_audio_format"] != "g711_ulaw":
        raise ValueError("This walk harness expects g711_ulaw input audio.")

    input_audio_bytes = read_ulaw_wav(audio_path, config["sample_rate_hz"])

    event_log_path = events_dir / f"{example_id}.jsonl"

    async with async_client.realtime.connect(model=config["model"]) as connection:
        # Disable VAD/turn detection so turn boundaries are controlled explicitly via
        # `input_audio_buffer.commit()` (keeps replay runs comparable).
        session = {
            "type": "realtime",
            "instructions": system_prompt,
            "tools": tools,
            "tool_choice": "auto",
            "output_modalities": ["audio"],
            "audio": {
                "input": {
                    "format": audio_format_config(
                        config["input_audio_format"], config["sample_rate_hz"]
                    ),
                    "turn_detection": None,
                },
                "output": {
                    "format": audio_format_config(
                        config["output_audio_format"],
                        config["output_sample_rate_hz"],
                    ),
                    "voice": config["voice"],
                },
            },
            "max_output_tokens": config["max_output_tokens"],
        }
        await connection.session.update(
            session=cast(RealtimeSessionCreateRequestParam, session)
        )

        await stream_audio_to_connection(
            connection,
            input_audio_bytes,
            config["chunk_ms"],
            config["sample_rate_hz"],
            config["input_audio_format"],
            config["real_time"],
        )

        response_payload: RealtimeResponseCreateParamsParam = {}
        with event_log_path.open("w", encoding="utf-8") as log_file:
            # Persist the full event stream so latency/tool-call issues are traceable.
            response_result = await collect_realtime_response(
                connection, response_payload, log_file=log_file
            )

    assistant_text = response_result["assistant_text"]
    tool_calls = response_result["tool_calls"]
    output_audio_bytes = response_result["output_audio_bytes"]
    tool_call_grade_data = compute_tool_call_grade(
        expected_tool_call, expected_tool_call_arg, tool_calls
    )
    tool_call_correctness = tool_call_grade_data["tool_call_correctness"]
    tool_call_arg_correctness = tool_call_grade_data["tool_call_arg_correctness"]
    grade = 1 if tool_call_correctness == 1 and tool_call_arg_correctness == 1 else 0

    output_audio_path = ""
    if output_audio_bytes:
        example_audio_dir = run_audio_dir / example_id
        ensure_dir(example_audio_dir)
        output_audio_path = str(example_audio_dir / "output.wav")
        write_pcm16_wav(
            Path(output_audio_path),
            bytes(output_audio_bytes),
            config["output_sample_rate_hz"],
        )

    usage_data = response_result["usage"]
    usage_output_tokens = usage_data.get("output_tokens", None)
    usage_output_audio_tokens = None
    usage_output_text_tokens = None
    if "output_token_details" in usage_data:
        output_details = usage_data["output_token_details"]
        usage_output_audio_tokens = output_details.get("audio_tokens")
        usage_output_text_tokens = output_details.get("text_tokens")

    return {
        "example_id": example_id,
        "user_text": user_text,
        "gt_tool_call": expected_tool_call,
        "gt_tool_call_arg": expected_tool_call_arg,
        "audio_path": str(audio_path),
        "assistant_text": assistant_text,
        "output_audio_path": output_audio_path,
        "event_log_path": str(event_log_path),
        "tool_calls": json.dumps(tool_calls),
        "pred_tool_call": tool_call_grade_data["pred_tool_call"],
        "pred_tool_call_arg": tool_call_grade_data["pred_tool_call_arg"],
        "tool_call_correctness": tool_call_correctness,
        "tool_call_arg_correctness": tool_call_arg_correctness,
        "grade": grade,
        "latency_first_audio_ms": response_result["first_audio_time_ms"],
        "latency_first_text_ms": response_result["first_text_time_ms"],
        "latency_response_done_ms": response_result["response_done_time_ms"],
        "output_tokens": usage_output_tokens,
        "output_audio_tokens": usage_output_audio_tokens,
        "output_text_tokens": usage_output_text_tokens,
    }


def compute_summary(results: pd.DataFrame) -> Dict[str, Any]:
    summary: Dict[str, Any] = {
        "total_examples": int(results.shape[0]),
        "grade_mean": float(results["grade"].mean()) if not results.empty else 0.0,
    }
    if "tool_call_correctness" in results.columns and not results.empty:
        summary["tool_call_correctness_mean"] = float(
            results["tool_call_correctness"].mean()
        )
    if "tool_call_arg_correctness" in results.columns and not results.empty:
        summary["tool_call_arg_correctness_mean"] = float(
            results["tool_call_arg_correctness"].mean()
        )

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
        "example_id",
        "user_text",
        "gt_tool_call",
        "pred_tool_call",
        "gt_tool_call_arg",
        "pred_tool_call_arg",
        "tool_call_correctness",
        "tool_call_arg_correctness",
        "grade",
        "assistant_text",
        "tool_calls",
        "event_log_path",
        "audio_path",
        "output_audio_path",
        "latency_first_audio_ms",
        "latency_first_text_ms",
        "latency_response_done_ms",
        "output_tokens",
        "output_audio_tokens",
        "output_text_tokens",
    ]
    return order_columns(results, preferred)


async def run_evals() -> None:
    args = parse_args()

    system_prompt = load_system_prompt(args.system_prompt_file)
    tools = load_tools(args.tools_file)
    dataset = load_dataset(args.data_csv)

    if args.max_examples > 0:
        dataset = dataset.head(args.max_examples)

    run_timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_name = args.run_name or run_timestamp
    run_dir = args.results_dir / run_name
    run_audio_dir = run_dir / "audio"
    run_events_dir = run_dir / "events"
    ensure_dir(run_audio_dir)
    ensure_dir(run_events_dir)

    config = {
        "model": args.model,
        "chunk_ms": args.chunk_ms,
        "sample_rate_hz": args.sample_rate_hz,
        "input_audio_format": args.input_audio_format,
        "output_audio_format": args.output_audio_format,
        "output_sample_rate_hz": args.output_sample_rate_hz,
        "max_output_tokens": args.max_output_tokens,
        "real_time": args.real_time,
        "voice": args.voice,
    }

    async_client = AsyncOpenAI()

    results: List[Dict[str, Any]] = []
    total_examples = int(dataset.shape[0])
    print(f"Running walk evals: {total_examples} examples -> {run_dir}")
    for _, row in tqdm(dataset.iterrows(), total=total_examples, desc="Walk evals"):
        result = await run_single_eval(
            async_client,
            row,
            system_prompt,
            tools,
            run_audio_dir,
            run_events_dir,
            config,
            args.data_csv,
        )
        results.append(result)

    results_df = pd.DataFrame(results)
    results_df = order_result_columns(results_df)
    results_csv_path = run_dir / "results.csv"
    results_df.to_csv(results_csv_path, index=False)

    summary = compute_summary(results_df)
    summary.update(
        {
            "run_name": run_name,
            "model": args.model,
            "chunk_ms": args.chunk_ms,
            "sample_rate_hz": args.sample_rate_hz,
            "input_audio_format": args.input_audio_format,
            "output_audio_format": args.output_audio_format,
            "output_sample_rate_hz": args.output_sample_rate_hz,
            "max_output_tokens": args.max_output_tokens,
            "real_time": args.real_time,
            "voice": args.voice,
            "data_csv": str(args.data_csv),
            "system_prompt_file": str(args.system_prompt_file),
            "tools_file": str(args.tools_file),
        }
    )

    summary_path = run_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(
        "Summary:"
        f" grade_mean={summary.get('grade_mean', 0):.3f}"
        f" tool_call_correctness_mean={summary.get('tool_call_correctness_mean', 0):.3f}"
        f" tool_call_arg_correctness_mean={summary.get('tool_call_arg_correctness_mean', 0):.3f}"
    )
    print(f"Wrote results to {run_dir}")


def main() -> None:
    asyncio.run(run_evals())


if __name__ == "__main__":
    main()
