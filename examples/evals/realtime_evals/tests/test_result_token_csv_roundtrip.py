"""Reload mixed-success CSV output without losing optional integer counts."""

import csv
import io
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shared.result_types import CrawlEvalResult


def row(value):
    return {
        "example_id": "synthetic",
        "user_text": "Synthetic request.",
        "assistant_text": "Synthetic response.",
        "input_audio_path": "synthetic-input.wav",
        "event_log_path": "synthetic-events.jsonl",
        "output_tokens": value,
        "output_audio_tokens": value,
        "output_text_tokens": value,
        "tool_call_correctness": 0,
        "tool_call_arg_correctness": 0,
    }


@pytest.mark.parametrize("reader", ["stdlib", "pandas"])
@pytest.mark.parametrize("count", [0, 1, 42, 1000000])
def test_optional_counts_survive_mixed_success_csv(reader, count):
    success = CrawlEvalResult.from_csv_row(row(count))
    missing = CrawlEvalResult.from_csv_row(
        {**row(None), "example_id": "failed", "status": "failed"}
    )
    stream = io.StringIO()
    pd.DataFrame([success.to_csv_row(), missing.to_csv_row()]).to_csv(
        stream, index=False
    )
    assert f"{count}.0" in stream.getvalue()
    stream.seek(0)
    records = (
        list(csv.DictReader(stream))
        if reader == "stdlib"
        else pd.read_csv(stream, keep_default_na=False).to_dict("records")
    )
    restored = [CrawlEvalResult.from_csv_row(record) for record in records]
    assert restored[0].output_tokens == success.output_tokens
    assert restored[1].output_tokens == missing.output_tokens
    assert restored[1].error_info.status == "failed"
    assert restored[0].artifact_paths == success.artifact_paths


@pytest.mark.parametrize(
    "text,expected",
    [
        ("0", 0),
        ("42", 42),
        ("42.0", 42),
        ("4.2e1", 42),
        ("9007199254740993.0", 9007199254740993),
        ("-2.0", -2),
        ("", None),
        (None, None),
    ],
)
def test_integer_text_avoids_binary_float_rounding(text, expected):
    result = CrawlEvalResult.from_csv_row(row(text))
    assert result.output_tokens.output_tokens == expected
    assert result.output_tokens.output_audio_tokens == expected
    assert result.output_tokens.output_text_tokens == expected


@pytest.mark.parametrize(
    "text", ["1.5", "NaN", "Infinity", "-Infinity", "not a number"]
)
def test_invalid_or_fractional_token_count_text_is_rejected(text):
    with pytest.raises(ValueError):
        CrawlEvalResult.from_csv_row(row(text))
