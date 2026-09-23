import sys
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("streamlit")

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from results_viewer.app import (
    RUN_VIEWER_SELECTED_COLUMN,
    build_run_viewer_table,
    build_summary_table,
    clean_path_value,
    coerce_float,
    display_run_label,
    input_audio_path_for_row,
    run_viewer_table_height,
    run_viewer_table_key,
)


def test_coerce_float_treats_blank_and_non_numeric_strings_as_missing() -> None:
    assert coerce_float("") is None
    assert coerce_float("   ") is None
    assert coerce_float("n/a") is None
    assert coerce_float("1.25") == 1.25


def test_clean_path_value_resolves_paths_within_run_directory(
    tmp_path: Path,
) -> None:
    run_directory = tmp_path / "results" / "demo_run"
    run_directory.mkdir(parents=True)

    assert clean_path_value(run_directory, "events/example.jsonl") == (
        run_directory / "events" / "example.jsonl"
    )


def test_clean_path_value_rejects_absolute_and_escaping_paths(
    tmp_path: Path,
) -> None:
    run_directory = tmp_path / "results" / "demo_run"
    run_directory.mkdir(parents=True)

    assert clean_path_value(run_directory, str(tmp_path / "outside.jsonl")) is None
    assert clean_path_value(run_directory, "../outside.jsonl") is None


def test_input_audio_path_for_row_rejects_example_ids_that_escape_run_directory(
    tmp_path: Path,
) -> None:
    run_directory = tmp_path / "results" / "demo_run"
    run_directory.mkdir(parents=True)
    escaped_audio_path = tmp_path / "results" / "escaped" / "input.wav"
    escaped_audio_path.parent.mkdir(parents=True)
    escaped_audio_path.write_bytes(b"RIFF")

    row = pd.Series({"example_id": "../../escaped"})

    assert input_audio_path_for_row(run_directory, row) is None


def test_run_viewer_table_key_uses_full_relative_path() -> None:
    first = ROOT_DIR / "crawl_harness" / "results" / "batch_a" / "shared_name"
    second = ROOT_DIR / "crawl_harness" / "results" / "batch_b" / "shared_name"

    assert run_viewer_table_key("crawl", first) != run_viewer_table_key("crawl", second)


def test_build_run_viewer_table_marks_active_row_with_checkbox() -> None:
    results = pd.DataFrame({"example_id": ["ex_1", "ex_2"], "grade": [1.0, 0.0]})

    display_results = build_run_viewer_table(results, 1)

    assert display_results.columns.tolist() == [
        RUN_VIEWER_SELECTED_COLUMN,
        "example_id",
        "grade",
    ]
    assert display_results[RUN_VIEWER_SELECTED_COLUMN].tolist() == [False, True]
    assert display_results.drop(columns=[RUN_VIEWER_SELECTED_COLUMN]).equals(results)


def test_run_viewer_table_height_caps_visible_rows_at_200() -> None:
    assert run_viewer_table_height(3) == 149
    assert run_viewer_table_height(100) == 3544
    assert run_viewer_table_height(200) == 7044
    assert run_viewer_table_height(250) == 7044


def test_display_run_label_uses_leaf_name() -> None:
    assert display_run_label("crawl_harness/results/batch_01/demo_run") == "demo_run"


def test_build_summary_table_uses_short_run_label_for_display() -> None:
    summary_table = build_summary_table(
        summaries=[
            {
                "run_label": "crawl_harness/results/batch_01/demo_run",
                "run_display_label": "demo_run",
                "run_name": "demo",
                "model": "gpt-4o-realtime-preview",
            }
        ],
        selected_score_keys=[],
        latency_metric_config={},
        token_metric_config={},
    )

    assert summary_table.loc[0, "run_label"] == "demo_run"
