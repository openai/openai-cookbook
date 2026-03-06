import sys
from pathlib import Path

import pandas as pd


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from results_viewer import app


def test_harness_results_roots_include_bootstrap_eval_results(
    tmp_path: Path, monkeypatch
) -> None:
    built_in_results = tmp_path / "crawl_harness" / "results"
    built_in_results.mkdir(parents=True)

    scaffolded_eval_dir = tmp_path / "billing_realtime_eval"
    (scaffolded_eval_dir / "results").mkdir(parents=True)
    (scaffolded_eval_dir / "bootstrap_manifest.json").write_text(
        '{"harness":"crawl"}\n',
        encoding="utf-8",
    )

    other_eval_dir = tmp_path / "other_realtime_eval"
    (other_eval_dir / "results").mkdir(parents=True)
    (other_eval_dir / "bootstrap_manifest.json").write_text(
        '{"harness":"walk"}\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(app, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(
        app,
        "HARNESS_RESULTS_DIRS",
        {
            "crawl": built_in_results,
            "walk": tmp_path / "walk_harness" / "results",
            "run": tmp_path / "run_harness" / "results",
        },
    )

    results_roots = app.harness_results_roots("crawl")

    assert results_roots == [
        built_in_results,
        scaffolded_eval_dir / "results",
    ]


def test_discover_result_directories_uses_root_relative_labels(
    tmp_path: Path, monkeypatch
) -> None:
    built_in_results = tmp_path / "crawl_harness" / "results"
    run_a = built_in_results / "run_a"
    run_a.mkdir(parents=True)
    (run_a / "results.csv").write_text("example_id\nex_001\n", encoding="utf-8")

    scaffolded_results = tmp_path / "billing_realtime_eval" / "results"
    run_b = scaffolded_results / "smoke"
    run_b.mkdir(parents=True)
    (run_b / "summary.json").write_text("{}\n", encoding="utf-8")

    monkeypatch.setattr(app, "ROOT_DIR", tmp_path)

    paths = app.discover_result_directories([built_in_results, scaffolded_results])
    labels = sorted(app.relative_directory_labels(paths))

    assert labels == [
        "billing_realtime_eval/results/smoke",
        "crawl_harness/results/run_a",
    ]


def test_row_text_value_returns_first_non_empty_candidate() -> None:
    row = pd.Series(
        {
            "assistant_text": "",
            "response_text": "Fallback assistant response",
        }
    )

    assert (
        app.row_text_value(row, ("assistant_text", "response_text"))
        == "Fallback assistant response"
    )


def test_resolve_active_row_index_prefers_navigation_state_until_selection_changes() -> None:
    assert app.resolve_active_row_index(
        table_selected_index=3,
        previous_table_selected_index=1,
        stored_active_index=2,
        total_rows=5,
    ) == 3

    assert app.resolve_active_row_index(
        table_selected_index=1,
        previous_table_selected_index=1,
        stored_active_index=2,
        total_rows=5,
    ) == 2

    assert app.resolve_active_row_index(
        table_selected_index=None,
        previous_table_selected_index=None,
        stored_active_index=None,
        total_rows=4,
    ) == 0


def test_run_viewer_table_widget_key_changes_when_selection_is_reset() -> None:
    selected_path = ROOT_DIR / "crawl_harness" / "results" / "batch_a" / "shared_name"

    assert app.normalize_table_revision(None) == 0
    assert app.normalize_table_revision(3) == 3
    assert app.run_viewer_table_widget_key(
        "crawl",
        selected_path,
        table_revision=0,
    ) != app.run_viewer_table_widget_key(
        "crawl",
        selected_path,
        table_revision=1,
    )


def test_resolve_run_viewer_table_selected_index_prefers_latest_checked_row() -> None:
    table_data = pd.DataFrame(
        {
            app.RUN_VIEWER_SELECTED_COLUMN: [True, True, False],
            "example_id": ["ex_1", "ex_2", "ex_3"],
        }
    )
    editing_state = {
        "edited_rows": {
            1: {app.RUN_VIEWER_SELECTED_COLUMN: True},
        }
    }

    assert (
        app.resolve_run_viewer_table_selected_index(
            table_data,
            editing_state,
            current_active_index=0,
        )
        == 1
    )


def test_run_viewer_table_matches_active_row_requires_single_checked_row() -> None:
    table_data = pd.DataFrame(
        {
            app.RUN_VIEWER_SELECTED_COLUMN: [False, True, False],
            "example_id": ["ex_1", "ex_2", "ex_3"],
        }
    )

    assert app.run_viewer_table_matches_active_row(table_data, 1) is True

    table_data.loc[0, app.RUN_VIEWER_SELECTED_COLUMN] = True

    assert app.run_viewer_table_matches_active_row(table_data, 1) is False
