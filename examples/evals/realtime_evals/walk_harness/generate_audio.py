"""Generate walk-harness audio assets from the crawl CSV.

Requires ffmpeg: `brew install ffmpeg`
"""

import argparse
import subprocess
from pathlib import Path

import pandas as pd
from openai import OpenAI

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_CSV = (
    ROOT_DIR / "crawl_harness" / "data" / "customer_service_synthetic.csv"
)
DEFAULT_OUTPUT_DIR = ROOT_DIR / "walk_harness" / "data" / "audio"
DEFAULT_OUTPUT_CSV = (
    ROOT_DIR / "walk_harness" / "data" / "customer_service_synthetic.csv"
)

DEFAULT_TTS_MODEL = "gpt-4o-mini-tts"
DEFAULT_VOICE = "alloy"
DEFAULT_TTS_SAMPLE_RATE_HZ = 24000
DEFAULT_TARGET_SAMPLE_RATE_HZ = 8000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate G.711 mu-law WAV files for the walk harness. Requires ffmpeg: `brew install ffmpeg`.",
    )
    parser.add_argument("--source-csv", type=Path, default=DEFAULT_SOURCE_CSV)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_OUTPUT_CSV)
    parser.add_argument("--tts-model", type=str, default=DEFAULT_TTS_MODEL)
    parser.add_argument("--voice", type=str, default=DEFAULT_VOICE)
    parser.add_argument(
        "--tts-sample-rate-hz", type=int, default=DEFAULT_TTS_SAMPLE_RATE_HZ
    )
    parser.add_argument(
        "--target-sample-rate-hz", type=int, default=DEFAULT_TARGET_SAMPLE_RATE_HZ
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Regenerate audio even if output exists.",
    )
    return parser.parse_args()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def load_dataset(path: Path) -> pd.DataFrame:
    dataset = pd.read_csv(path)
    required_columns = {"example_id", "user_text", "gt_tool_call", "gt_tool_call_arg"}
    missing = required_columns.difference(dataset.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")
    return dataset


def tts_to_pcm_file(
    client: OpenAI, text: str, output_path: Path, model: str, voice: str
) -> None:
    ensure_dir(output_path.parent)
    with client.audio.speech.with_streaming_response.create(
        model=model,
        voice=voice,
        input=text,
        response_format="pcm",
    ) as response:
        response.stream_to_file(output_path)


def encode_pcm_to_ulaw_wav(
    input_pcm_path: Path,
    output_wav_path: Path,
    input_sample_rate_hz: int,
    target_sample_rate_hz: int,
) -> None:
    ensure_dir(output_wav_path.parent)
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "s16le",
        "-ar",
        str(input_sample_rate_hz),
        "-ac",
        "1",
        "-i",
        str(input_pcm_path),
        "-ar",
        str(target_sample_rate_hz),
        "-ac",
        "1",
        "-c:a",
        "pcm_mulaw",
        str(output_wav_path),
    ]
    subprocess.run(command, check=True)


def main() -> None:
    args = parse_args()
    dataset = load_dataset(args.source_csv)

    ensure_dir(args.output_dir)
    ensure_dir(args.output_csv.parent)

    client = OpenAI()

    audio_paths: list[str] = []
    for _, row in dataset.iterrows():
        example_id = str(row["example_id"]).strip()
        user_text = str(row["user_text"]).strip()
        if not example_id:
            raise ValueError("example_id is empty")

        output_wav_path = args.output_dir / f"{example_id}.wav"
        audio_paths.append(str(output_wav_path.relative_to(args.output_csv.parent)))

        if output_wav_path.exists() and not args.overwrite:
            continue

        temp_pcm_path = args.output_dir / f"{example_id}.pcm"
        tts_to_pcm_file(client, user_text, temp_pcm_path, args.tts_model, args.voice)

        encode_pcm_to_ulaw_wav(
            temp_pcm_path,
            output_wav_path,
            input_sample_rate_hz=args.tts_sample_rate_hz,
            target_sample_rate_hz=args.target_sample_rate_hz,
        )

        temp_pcm_path.unlink(missing_ok=True)

    output_dataset = dataset.copy()
    if "expected_keywords" in output_dataset.columns:
        output_dataset = output_dataset.drop(columns=["expected_keywords"])
    output_dataset["audio_path"] = audio_paths
    output_dataset.to_csv(args.output_csv, index=False)


if __name__ == "__main__":
    main()
