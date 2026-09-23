from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd
import streamlit as st

if TYPE_CHECKING:
    from results_viewer.config import (
        DEFAULT_LATENCY_SERIES,
        DEFAULT_SCORE_KEYS,
        DEFAULT_TOKEN_SERIES,
        LATENCY_CHART_KEYS,
        PERCENTILE_LABELS,
        SCORE_KEY_LABELS,
        SUMMARY_TABLE_BASE_COLUMNS,
        TOKEN_CHART_KEYS,
    )
    from results_viewer.ui import load_css
else:
    try:
        from .config import (
            DEFAULT_LATENCY_SERIES,
            DEFAULT_SCORE_KEYS,
            DEFAULT_TOKEN_SERIES,
            LATENCY_CHART_KEYS,
            PERCENTILE_LABELS,
            SCORE_KEY_LABELS,
            SUMMARY_TABLE_BASE_COLUMNS,
            TOKEN_CHART_KEYS,
        )
        from .ui import load_css
    except ImportError:
        from config import (
            DEFAULT_LATENCY_SERIES,
            DEFAULT_SCORE_KEYS,
            DEFAULT_TOKEN_SERIES,
            LATENCY_CHART_KEYS,
            PERCENTILE_LABELS,
            SCORE_KEY_LABELS,
            SUMMARY_TABLE_BASE_COLUMNS,
            TOKEN_CHART_KEYS,
        )
        from ui import load_css

ROOT_DIR = Path(__file__).resolve().parents[1]
HARNESS_RESULTS_DIRS = {
    "crawl": ROOT_DIR / "crawl_harness" / "results",
    "walk": ROOT_DIR / "walk_harness" / "results",
    "run": ROOT_DIR / "run_harness" / "results",
}
CHART_RUN_PALETTE = [
    "#b9cfdb",
    "#c7d3bf",
    "#ddc2be",
    "#cbc3da",
    "#ddd0b7",
    "#bfd4cc",
]
CHART_TEXT_COLOR = "#151515"
CHART_MUTED_TEXT_COLOR = "#5f5f5a"
CHART_DOMAIN_COLOR = "#cecec7"
CHART_GRID_COLOR = "#dfdfd8"
CHART_CONTENT_HEIGHT = 280
CHART_LABEL_MAX_CHARS = 10
CHART_LABEL_SUFFIX = "...."
RUN_VIEWER_SELECTED_COLUMN = "__selected__"
RUN_VIEWER_TABLE_VISIBLE_ROWS = 200
RUN_VIEWER_TABLE_ROW_HEIGHT = 35
RUN_VIEWER_TABLE_HEADER_HEIGHT = 38
RUN_VIEWER_TABLE_FRAME_PADDING = 6


def chart_theme_config() -> dict[str, object]:
    return {
        "view": {"stroke": None},
        "background": "transparent",
        "axis": {
            "labelColor": CHART_MUTED_TEXT_COLOR,
            "titleColor": CHART_TEXT_COLOR,
            "domainColor": CHART_DOMAIN_COLOR,
            "gridColor": CHART_GRID_COLOR,
            "tickColor": CHART_DOMAIN_COLOR,
        },
        "legend": {
            "labelColor": CHART_MUTED_TEXT_COLOR,
            "titleColor": CHART_TEXT_COLOR,
        },
    }


def result_directory_label(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT_DIR))
    except ValueError:
        return str(path)


def display_run_label(value: str | Path) -> str:
    raw_value = str(value)
    display_label = Path(raw_value).name
    return display_label or raw_value


def path_state_key_fragment(path: Path) -> str:
    return result_directory_label(path).replace("/", "__")


def harness_results_roots(harness: str) -> list[Path]:
    roots = [HARNESS_RESULTS_DIRS[harness]]
    for manifest_path in sorted(ROOT_DIR.glob("*/bootstrap_manifest.json")):
        try:
            manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if manifest_payload.get("harness") != harness:
            continue
        results_root = manifest_path.parent / "results"
        if results_root not in roots:
            roots.append(results_root)
    return roots


def discover_result_directories(results_roots: Path | list[Path]) -> list[Path]:
    if isinstance(results_roots, Path):
        candidate_roots = [results_roots]
    else:
        candidate_roots = results_roots

    run_directories = {
        path.parent
        for results_root in candidate_roots
        if results_root.exists()
        for path in results_root.rglob("*")
        if path.is_file() and path.name in {"results.csv", "summary.json"}
    }
    return sorted(run_directories)


def relative_directory_labels(paths: list[Path], root: Path | None = None) -> list[str]:
    label_root = ROOT_DIR if root is None else root
    labels: list[str] = []
    for path in paths:
        try:
            labels.append(str(path.relative_to(label_root)))
        except ValueError:
            labels.append(str(path))
    return labels


def summary_path_for_run(run_directory: Path) -> Path:
    return run_directory / "summary.json"


def results_csv_path_for_run(run_directory: Path) -> Path:
    return run_directory / "results.csv"


def coerce_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return float(stripped)
        except (TypeError, ValueError):
            return None
    return None


def _set_results_selection(
    selection_key: str, select_all_key: str, available_labels: list[str]
) -> None:
    if st.session_state.get(select_all_key):
        st.session_state[selection_key] = available_labels
        return

    current_selection = st.session_state.get(selection_key, [])
    st.session_state[selection_key] = [
        label for label in current_selection if label in available_labels
    ]


def _sync_select_all_toggle(
    selection_key: str, select_all_key: str, available_labels: list[str]
) -> None:
    selected_labels = st.session_state.get(selection_key, [])
    st.session_state[select_all_key] = bool(available_labels) and len(
        selected_labels
    ) == len(available_labels)


def selected_runs_status_markup(selected_run_count: int) -> str:
    run_label = "run" if selected_run_count == 1 else "runs"
    return (
        '<p class="comparison-selection-status">'
        '<span class="comparison-selection-status__count">'
        f"{selected_run_count}"
        "</span> "
        f"{run_label} selected"
        "</p>"
    )


def selected_result_directories(harness: str) -> list[Path]:
    results_roots = harness_results_roots(harness)
    available_paths = discover_result_directories(results_roots)
    available_labels = relative_directory_labels(available_paths)

    selection_key = f"selected_results_{harness}"
    select_all_key = f"selected_results_all_{harness}"

    current_selection = st.session_state.get(selection_key, [])
    valid_defaults = [label for label in current_selection if label in available_labels]
    all_selected = bool(available_labels) and len(valid_defaults) == len(
        available_labels
    )

    if selection_key not in st.session_state:
        st.session_state[selection_key] = valid_defaults
    if select_all_key not in st.session_state:
        st.session_state[select_all_key] = all_selected

    if (
        st.session_state.get(select_all_key)
        and st.session_state.get(selection_key) != available_labels
    ):
        st.session_state[selection_key] = available_labels
    elif (
        not st.session_state.get(select_all_key)
        and st.session_state.get(selection_key) != valid_defaults
    ):
        st.session_state[selection_key] = valid_defaults

    with st.popover("Results browser"):
        st.caption(f"Browsing saved `{harness}_harness` runs")
        if len(results_roots) > 1:
            st.caption(
                "Includes scaffolded eval folders created by the bootstrap skill."
            )
        if not available_labels:
            st.info("No result directories found for this harness yet.")
            return []

        st.checkbox(
            "Select all",
            key=select_all_key,
            on_change=_set_results_selection,
            args=(selection_key, select_all_key, available_labels),
        )
        st.multiselect(
            "Select one or more result directories",
            options=available_labels,
            key=selection_key,
            placeholder="Choose saved runs",
            format_func=display_run_label,
            on_change=_sync_select_all_toggle,
            args=(selection_key, select_all_key, available_labels),
        )

    selected_set = set(st.session_state.get(selection_key, []))
    return [
        path
        for path, label in zip(available_paths, available_labels, strict=False)
        if label in selected_set
    ]


def selected_run_directory(harness: str) -> Path | None:
    results_roots = harness_results_roots(harness)
    available_paths = discover_result_directories(results_roots)
    available_labels = relative_directory_labels(available_paths)

    if not available_paths:
        st.info("No result directories found for this harness yet.")
        return None

    current_selection = st.session_state.get(f"selected_run_{harness}")
    default_index = 0
    if current_selection in available_labels:
        default_index = available_labels.index(current_selection)

    selected_label = st.selectbox(
        "Run",
        options=available_labels,
        index=default_index,
        key=f"selected_run_{harness}",
        format_func=display_run_label,
    )
    if not selected_label:
        return None

    return available_paths[available_labels.index(selected_label)]


def load_selected_summaries(
    selected_paths: list[Path],
) -> tuple[list[dict[str, object]], list[str]]:
    loaded_summaries: list[dict[str, object]] = []
    load_errors: list[str] = []

    for run_directory in selected_paths:
        summary_path = summary_path_for_run(run_directory)
        run_label = result_directory_label(run_directory)
        run_display_label = display_run_label(run_label)
        if not summary_path.exists():
            load_errors.append(f"`{run_display_label}` is missing `summary.json`.")
            continue

        try:
            summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            load_errors.append(f"`{run_display_label}` has an invalid `summary.json`.")
            continue

        if not isinstance(summary_payload, dict):
            load_errors.append(
                f"`{run_display_label}` has a non-object `summary.json`."
            )
            continue

        loaded_summaries.append(
            {
                "run_label": run_label,
                "run_display_label": run_display_label,
                "run_directory": str(run_directory),
                "summary_path": str(summary_path),
                **summary_payload,
            }
        )

    return loaded_summaries, load_errors


def load_results_frame(run_directory: Path) -> tuple[pd.DataFrame | None, str | None]:
    results_csv_path = results_csv_path_for_run(run_directory)
    if not results_csv_path.exists():
        return None, "This run is missing `results.csv`."

    try:
        results = pd.read_csv(results_csv_path, keep_default_na=False)
    except Exception as exc:
        return None, f"Could not load `results.csv`: {exc}"

    return results, None


def chart_run_label(summary: dict[str, object]) -> str:
    run_display_label = summary.get("run_display_label")
    if isinstance(run_display_label, str) and run_display_label:
        return run_display_label
    return display_run_label(str(summary["run_label"]))


def build_score_chart_frame(
    summaries: list[dict[str, object]], metric_keys: list[str]
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for summary in summaries:
        run_label = chart_run_label(summary)
        for metric_key in metric_keys:
            metric_value = coerce_float(summary.get(metric_key))
            if metric_value is None:
                continue
            rows.append(
                {
                    "run_label": run_label,
                    "metric_key": metric_key,
                    "metric_label": score_key_label(metric_key),
                    "value": metric_value,
                }
            )
    return pd.DataFrame(rows)


def score_key_label(metric_key: str) -> str:
    if metric_key in SCORE_KEY_LABELS:
        return SCORE_KEY_LABELS[metric_key]
    if metric_key.endswith("_grade_mean"):
        metric_key = metric_key[: -len("_grade_mean")]
    return metric_key.replace("_", " ").strip().title()


def available_score_keys(summaries: list[dict[str, object]]) -> list[str]:
    default_keys = [
        metric_key
        for metric_key in DEFAULT_SCORE_KEYS
        if any(coerce_float(summary.get(metric_key)) is not None for summary in summaries)
    ]
    dynamic_grade_keys = sorted(
        {
            metric_key
            for summary in summaries
            for metric_key, metric_value in summary.items()
            if metric_key.endswith("_grade_mean")
            and metric_key not in DEFAULT_SCORE_KEYS
            and coerce_float(metric_value) is not None
        }
    )
    return default_keys + dynamic_grade_keys


def available_series_labels(
    summaries: list[dict[str, object]], metric_config: dict[str, list[str]]
) -> list[str]:
    available_labels: list[str] = []
    for series_label, metric_keys in metric_config.items():
        if any(
            summary.get(metric_key) is not None
            for summary in summaries
            for metric_key in metric_keys
        ):
            available_labels.append(series_label)
    return available_labels


def build_percentile_chart_frame(
    summaries: list[dict[str, object]], metric_config: dict[str, list[str]]
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for summary in summaries:
        run_label = chart_run_label(summary)
        for series_label, metric_keys in metric_config.items():
            for percentile_order, metric_key in enumerate(metric_keys):
                metric_value = coerce_float(summary.get(metric_key))
                if metric_value is None:
                    continue
                percentile_suffix = metric_key.rsplit("_", 1)[-1]
                rows.append(
                    {
                        "run_label": run_label,
                        "series_label": series_label,
                        "metric_key": metric_key,
                        "percentile_label": PERCENTILE_LABELS.get(
                            percentile_suffix, percentile_suffix
                        ),
                        "percentile_order": percentile_order,
                        "value": metric_value,
                    }
                )
    return pd.DataFrame(rows)


def selected_metric_controls(
    harness: str,
    summaries: list[dict[str, object]],
) -> tuple[list[str], dict[str, list[str]], dict[str, list[str]]]:
    score_options = available_score_keys(summaries)
    latency_options = available_series_labels(summaries, LATENCY_CHART_KEYS)
    token_options = available_series_labels(summaries, TOKEN_CHART_KEYS)

    score_defaults = [key for key in DEFAULT_SCORE_KEYS if key in score_options]
    latency_defaults = [
        label for label in DEFAULT_LATENCY_SERIES if label in latency_options
    ]
    token_defaults = [label for label in DEFAULT_TOKEN_SERIES if label in token_options]

    with st.popover("Chart metrics"):
        st.caption("Toggle which metrics and metric families are visible.")
        selected_score_keys = st.multiselect(
            "Overall score metrics",
            options=score_options,
            default=score_defaults,
            format_func=score_key_label,
            key=f"selected_score_keys_{harness}",
        )
        selected_latency_labels = st.multiselect(
            "Latency families",
            options=latency_options,
            default=latency_defaults,
            key=f"selected_latency_series_{harness}",
        )
        selected_token_labels = st.multiselect(
            "Token families",
            options=token_options,
            default=token_defaults,
            key=f"selected_token_series_{harness}",
        )

    selected_latency_config = {
        label: LATENCY_CHART_KEYS[label] for label in selected_latency_labels
    }
    selected_token_config = {
        label: TOKEN_CHART_KEYS[label] for label in selected_token_labels
    }
    return selected_score_keys, selected_latency_config, selected_token_config


def build_summary_table(
    summaries: list[dict[str, object]],
    selected_score_keys: list[str],
    latency_metric_config: dict[str, list[str]],
    token_metric_config: dict[str, list[str]],
) -> pd.DataFrame:
    table_columns = list(SUMMARY_TABLE_BASE_COLUMNS)
    table_columns.extend(selected_score_keys)

    for metric_keys in latency_metric_config.values():
        table_columns.extend(metric_keys)
    for metric_keys in token_metric_config.values():
        table_columns.extend(metric_keys)

    ordered_columns: list[str] = []
    seen_columns: set[str] = set()
    for column in table_columns:
        if column in seen_columns:
            continue
        if any(summary.get(column) is not None for summary in summaries):
            ordered_columns.append(column)
            seen_columns.add(column)

    rows: list[dict[str, object]] = []
    for summary in summaries:
        row: dict[str, object] = {}
        for column in ordered_columns:
            if column == "run_label":
                row[column] = chart_run_label(summary)
            else:
                row[column] = summary.get(column)
        rows.append(row)

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows)


def truncated_chart_label_expr() -> str:
    return (
        f"length(datum.label) > {CHART_LABEL_MAX_CHARS} ? "
        f"slice(datum.label, 0, {CHART_LABEL_MAX_CHARS}) + '{CHART_LABEL_SUFFIX}' : "
        "datum.label"
    )


def angled_chart_axis() -> dict[str, object]:
    return {
        "labelAngle": 90,
        "labelExpr": truncated_chart_label_expr(),
    }


def render_grouped_bar_chart(data: pd.DataFrame) -> None:
    if data.empty:
        st.info("No score metrics were found in the selected summaries.")
        return

    st.vega_lite_chart(
        data,
        {
            "config": chart_theme_config(),
            "height": CHART_CONTENT_HEIGHT,
            "layer": [
                {
                    "mark": {
                        "type": "bar",
                        "cornerRadiusTopLeft": 4,
                        "cornerRadiusTopRight": 4,
                    },
                    "encoding": {
                        "x": {
                            "field": "metric_label",
                            "type": "nominal",
                            "title": "Metric",
                            "axis": angled_chart_axis(),
                        },
                        "xOffset": {"field": "run_label"},
                        "y": {
                            "field": "value",
                            "type": "quantitative",
                            "title": "Score",
                        },
                        "color": {
                            "field": "run_label",
                            "type": "nominal",
                            "title": "Run",
                            "scale": {"range": CHART_RUN_PALETTE},
                        },
                        "tooltip": [
                            {
                                "field": "metric_label",
                                "type": "nominal",
                                "title": "Metric",
                            },
                            {"field": "run_label", "type": "nominal", "title": "Run"},
                            {
                                "field": "value",
                                "type": "quantitative",
                                "format": ".3f",
                            },
                        ],
                    },
                },
                {
                    "mark": {
                        "type": "text",
                        "dy": -8,
                        "fontSize": 11,
                    },
                    "encoding": {
                        "x": {
                            "field": "metric_label",
                            "type": "nominal",
                            "title": "Metric",
                            "axis": angled_chart_axis(),
                        },
                        "xOffset": {"field": "run_label"},
                        "y": {
                            "field": "value",
                            "type": "quantitative",
                            "title": "Score",
                        },
                        "text": {
                            "field": "value",
                            "type": "quantitative",
                            "format": ".3f",
                        },
                        "color": {
                            "value": CHART_TEXT_COLOR,
                        },
                    },
                },
            ],
        },
        use_container_width=True,
    )


def render_percentile_ladder_chart(data: pd.DataFrame, y_title: str) -> None:
    if data.empty:
        st.info("No percentile metrics were found in the selected summaries.")
        return

    for series_label in data["series_label"].drop_duplicates().tolist():
        series_data = data[data["series_label"] == series_label]
        st.caption(series_label)
        st.vega_lite_chart(
            series_data,
            {
                "config": chart_theme_config(),
                "height": CHART_CONTENT_HEIGHT,
                "layer": [
                    {
                        "mark": {
                            "type": "bar",
                            "cornerRadiusTopLeft": 4,
                            "cornerRadiusTopRight": 4,
                        },
                        "encoding": {
                            "x": {
                                "field": "percentile_label",
                                "type": "ordinal",
                                "title": "Percentile",
                                "sort": ["avg", "p50", "p95", "p99"],
                                "axis": angled_chart_axis(),
                            },
                            "xOffset": {"field": "run_label"},
                            "y": {
                                "field": "value",
                                "type": "quantitative",
                                "title": y_title,
                            },
                            "color": {
                                "field": "run_label",
                                "type": "nominal",
                                "title": "Run",
                                "scale": {"range": CHART_RUN_PALETTE},
                            },
                            "tooltip": [
                                {
                                    "field": "run_label",
                                    "type": "nominal",
                                    "title": "Run",
                                },
                                {
                                    "field": "series_label",
                                    "type": "nominal",
                                    "title": "Series",
                                },
                                {
                                    "field": "percentile_label",
                                    "type": "ordinal",
                                    "title": "Percentile",
                                },
                                {
                                    "field": "value",
                                    "type": "quantitative",
                                    "format": ".2f",
                                },
                            ],
                        },
                    },
                    {
                        "mark": {
                            "type": "text",
                            "dy": -8,
                            "fontSize": 11,
                        },
                        "encoding": {
                            "x": {
                                "field": "percentile_label",
                                "type": "ordinal",
                                "title": "Percentile",
                                "sort": ["avg", "p50", "p95", "p99"],
                                "axis": angled_chart_axis(),
                            },
                            "xOffset": {"field": "run_label"},
                            "y": {
                                "field": "value",
                                "type": "quantitative",
                                "title": y_title,
                            },
                            "text": {
                                "field": "value",
                                "type": "quantitative",
                                "format": ".2f",
                            },
                            "color": {"value": CHART_TEXT_COLOR},
                        },
                    },
                ],
            },
            use_container_width=True,
        )


def render_comparison_config_bar() -> tuple[str, list[Path]]:
    with st.container():
        harness_column, browser_column, status_column = st.columns(
            [2.9, 1.2, 1],
            gap="small",
            vertical_alignment="bottom",
        )

        with harness_column:
            harness = st.selectbox(
                "Harness",
                options=["crawl", "walk", "run"],
                index=0,
                format_func=lambda value: f"{value}_harness",
                key="comparison_harness",
            )

        with browser_column:
            selected_paths = selected_result_directories(harness)

        with status_column:
            st.markdown(
                selected_runs_status_markup(len(selected_paths)),
                unsafe_allow_html=True,
            )

    return harness, selected_paths


def render_run_viewer_config_bar() -> tuple[str, Path | None]:
    with st.container():
        left, right = st.columns([1.1, 2.2])

        with left:
            harness = st.selectbox(
                "Harness",
                options=["crawl", "walk", "run"],
                index=0,
                format_func=lambda value: f"{value}_harness",
                key="run_viewer_harness",
            )

        with right:
            selected_path = selected_run_directory(harness)

    return harness, selected_path


def read_text_if_present(path: Path | None) -> str | None:
    if path is None or not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def audio_bytes_if_present(path: Path | None) -> bytes | None:
    if path is None or not path.exists():
        return None
    return path.read_bytes()


def resolve_run_relative_path(run_directory: Path, candidate: Path) -> Path | None:
    try:
        resolved_run_directory = run_directory.resolve()
        resolved_root = ROOT_DIR.resolve()
        resolved_candidate = (
            candidate.resolve(strict=False)
            if candidate.is_absolute()
            else (resolved_run_directory / candidate).resolve(strict=False)
        )
    except OSError:
        return None
    if not (
        resolved_candidate.is_relative_to(resolved_run_directory)
        or resolved_candidate.is_relative_to(resolved_root)
    ):
        return None
    return resolved_candidate


def clean_path_value(run_directory: Path, value: object) -> Path | None:
    if not isinstance(value, str):
        return None
    cleaned_value = value.strip()
    if not cleaned_value:
        return None
    return resolve_run_relative_path(run_directory, Path(cleaned_value))


def simulation_id_for_row(row: pd.Series) -> str:
    return str(row.get("simulation_id", "")).strip()


def selected_run_viewer_row_indices(table_data: pd.DataFrame) -> list[int]:
    if RUN_VIEWER_SELECTED_COLUMN not in table_data.columns:
        return []

    selected_rows: list[int] = []
    for row_index, value in enumerate(table_data[RUN_VIEWER_SELECTED_COLUMN].tolist()):
        if pd.isna(value):
            continue
        if bool(value):
            selected_rows.append(row_index)
    return selected_rows


def edited_run_viewer_row_indices(editing_state: object) -> list[int]:
    if not isinstance(editing_state, dict):
        return []

    edited_rows = editing_state.get("edited_rows")
    if not isinstance(edited_rows, dict):
        return []

    selected_rows: list[int] = []
    for row_index, row_changes in edited_rows.items():
        if not isinstance(row_index, int) or not isinstance(row_changes, dict):
            continue
        if row_changes.get(RUN_VIEWER_SELECTED_COLUMN) is True:
            selected_rows.append(row_index)
    return selected_rows


def row_text_value(row: pd.Series, candidate_columns: tuple[str, ...]) -> str | None:
    for column_name in candidate_columns:
        if column_name not in row.index:
            continue
        value = str(row.get(column_name, "")).strip()
        if value:
            return value
    return None


def normalize_row_index(candidate: object, total_rows: int) -> int | None:
    if isinstance(candidate, int) and 0 <= candidate < total_rows:
        return candidate
    return None


def resolve_active_row_index(
    table_selected_index: int | None,
    previous_table_selected_index: int | None,
    stored_active_index: object,
    total_rows: int,
) -> int | None:
    if total_rows <= 0:
        return None
    if (
        table_selected_index is not None
        and table_selected_index != previous_table_selected_index
    ):
        return table_selected_index

    active_row_index = normalize_row_index(stored_active_index, total_rows)
    if active_row_index is not None:
        return active_row_index

    if table_selected_index is not None:
        return table_selected_index

    return 0


def build_run_viewer_table(
    results: pd.DataFrame, active_row_index: int | None
) -> pd.DataFrame:
    display_results = results.copy()
    selected_rows = [False] * len(display_results)
    if active_row_index is not None and 0 <= active_row_index < len(display_results):
        selected_rows[active_row_index] = True
    display_results.insert(0, RUN_VIEWER_SELECTED_COLUMN, selected_rows)
    return display_results


def resolve_run_viewer_table_selected_index(
    table_data: pd.DataFrame,
    editing_state: object,
    current_active_index: int | None,
) -> int | None:
    total_rows = len(table_data)
    for candidate in reversed(edited_run_viewer_row_indices(editing_state)):
        normalized_candidate = normalize_row_index(candidate, total_rows)
        if normalized_candidate is not None:
            return normalized_candidate

    selected_rows = selected_run_viewer_row_indices(table_data)
    if current_active_index is not None and current_active_index in selected_rows:
        return current_active_index
    if selected_rows:
        return selected_rows[0]
    return current_active_index


def run_viewer_table_matches_active_row(
    table_data: pd.DataFrame,
    active_row_index: int | None,
) -> bool:
    normalized_active_index = normalize_row_index(active_row_index, len(table_data))
    expected_rows = [] if normalized_active_index is None else [normalized_active_index]
    return selected_run_viewer_row_indices(table_data) == expected_rows


def run_viewer_table_height(total_rows: int) -> int:
    visible_rows = max(1, min(total_rows, RUN_VIEWER_TABLE_VISIBLE_ROWS))
    return (
        RUN_VIEWER_TABLE_HEADER_HEIGHT
        + (visible_rows * RUN_VIEWER_TABLE_ROW_HEIGHT)
        + RUN_VIEWER_TABLE_FRAME_PADDING
    )


def input_audio_path_for_row(run_directory: Path, row: pd.Series) -> Path | None:
    for column_name in ("input_audio_path", "audio_path"):
        candidate = clean_path_value(run_directory, row.get(column_name, ""))
        if candidate is not None:
            return candidate

    example_id = str(row.get("example_id", "")).strip()
    if not example_id:
        return None
    candidate = resolve_run_relative_path(
        run_directory, Path("audio") / example_id / "input.wav"
    )
    if candidate is not None and candidate.exists():
        return candidate
    return None


def output_audio_path_for_row(run_directory: Path, row: pd.Series) -> Path | None:
    candidate = clean_path_value(run_directory, row.get("output_audio_path", ""))
    if candidate is not None:
        return candidate

    example_id = str(row.get("example_id", "")).strip()
    if not example_id:
        return None
    candidate = resolve_run_relative_path(
        run_directory, Path("audio") / example_id / "output.wav"
    )
    if candidate is not None and candidate.exists():
        return candidate
    return None


def event_log_path_for_row(run_directory: Path, row: pd.Series) -> Path | None:
    candidate = clean_path_value(run_directory, row.get("event_log_path", ""))
    if candidate is not None:
        return candidate

    example_id = str(row.get("example_id", "")).strip()
    if not example_id:
        return None
    candidate = resolve_run_relative_path(
        run_directory, Path("events") / f"{example_id}.jsonl"
    )
    if candidate is not None and candidate.exists():
        return candidate
    return None


def simulation_transcript_path_for_row(
    run_directory: Path, row: pd.Series
) -> Path | None:
    simulation_id = simulation_id_for_row(row)
    if not simulation_id:
        return None

    candidate = resolve_run_relative_path(
        run_directory, Path("conversations") / f"{simulation_id}.txt"
    )
    if candidate is not None and candidate.exists():
        return candidate
    return None


def simulation_event_log_path_for_row(
    run_directory: Path, row: pd.Series
) -> Path | None:
    candidate = clean_path_value(run_directory, row.get("event_log_path", ""))
    if candidate is not None:
        return candidate

    simulation_id = simulation_id_for_row(row)
    if not simulation_id:
        return None

    candidate = resolve_run_relative_path(
        run_directory, Path("events") / f"{simulation_id}.jsonl"
    )
    if candidate is not None and candidate.exists():
        return candidate
    return None


def _audio_sort_key(path: Path) -> tuple[int, int, str]:
    stem_parts = path.stem.split("_")
    turn_index = -1
    role_order = 2

    if len(stem_parts) >= 3 and stem_parts[0] == "turn":
        try:
            turn_index = int(stem_parts[1])
        except ValueError:
            turn_index = -1
        role_order = {"user": 0, "assistant": 1}.get(stem_parts[2], 2)

    return turn_index, role_order, path.name


def simulation_audio_paths_for_row(run_directory: Path, row: pd.Series) -> list[Path]:
    simulation_id = simulation_id_for_row(row)
    if not simulation_id:
        return []

    audio_dir = resolve_run_relative_path(run_directory, Path("audio") / simulation_id)
    if audio_dir is None or not audio_dir.exists():
        return []

    return sorted(audio_dir.glob("*.wav"), key=_audio_sort_key)


def run_viewer_table_key(harness: str, selected_path: Path) -> str:
    return f"run_viewer_table_{harness}_{path_state_key_fragment(selected_path)}"


def normalize_table_revision(candidate: object) -> int:
    if isinstance(candidate, int) and candidate >= 0:
        return candidate
    return 0


def run_viewer_active_row_key(harness: str, selected_path: Path) -> str:
    return f"run_viewer_active_row_{harness}_{path_state_key_fragment(selected_path)}"


def run_viewer_table_selection_key(harness: str, selected_path: Path) -> str:
    return (
        f"run_viewer_table_selection_{harness}_{path_state_key_fragment(selected_path)}"
    )


def run_viewer_table_revision_key(harness: str, selected_path: Path) -> str:
    return (
        f"run_viewer_table_revision_{harness}_{path_state_key_fragment(selected_path)}"
    )


def run_viewer_table_widget_key(
    harness: str, selected_path: Path, table_revision: int
) -> str:
    return f"{run_viewer_table_key(harness, selected_path)}_{table_revision}"


def refresh_run_viewer_table_state(
    harness: str,
    selected_path: Path,
    selected_index: int | None,
) -> None:
    selection_key = run_viewer_table_selection_key(harness, selected_path)
    revision_key = run_viewer_table_revision_key(harness, selected_path)
    st.session_state[selection_key] = selected_index
    # Streamlit data editor edits are sticky, so bump the widget key to rehydrate
    # the controlled checkbox state from the active row.
    st.session_state[revision_key] = (
        normalize_table_revision(st.session_state.get(revision_key)) + 1
    )


def render_row_text_review(row: pd.Series) -> None:
    input_text = row_text_value(row, ("user_text", "input_text"))
    output_text = row_text_value(
        row,
        ("assistant_text", "output_text", "response_text"),
    )

    st.caption("Input text")
    if input_text is None:
        st.info("No input text recorded for this row.")
    else:
        st.code(input_text, language="text")

    st.caption("Output text")
    if output_text is None:
        st.info("No output text recorded for this row.")
    else:
        st.code(output_text, language="text")


def render_example_viewer(run_directory: Path, row: pd.Series) -> None:
    example_id = str(row.get("example_id", "")).strip() or "Unknown example"

    st.subheader(example_id)
    render_row_text_review(row)

    input_audio_path = input_audio_path_for_row(run_directory, row)
    output_audio_path = output_audio_path_for_row(run_directory, row)
    event_log_path = event_log_path_for_row(run_directory, row)

    st.caption("Input audio")
    input_audio_bytes = audio_bytes_if_present(input_audio_path)
    if input_audio_bytes is None:
        st.info("No input audio found for this example.")
    else:
        st.audio(input_audio_bytes, format="audio/wav")
        st.caption(str(input_audio_path))

    st.caption("Output audio")
    output_audio_bytes = audio_bytes_if_present(output_audio_path)
    if output_audio_bytes is None:
        st.info("No output audio found for this example.")
    else:
        st.audio(output_audio_bytes, format="audio/wav")
        st.caption(str(output_audio_path))

    st.caption("Events")
    event_log_text = read_text_if_present(event_log_path)
    if event_log_text is None:
        st.info("No event log found for this example.")
    else:
        st.code(event_log_text, language="json")
        st.caption(str(event_log_path))


def render_simulation_viewer(run_directory: Path, row: pd.Series) -> None:
    simulation_id = simulation_id_for_row(row) or "Unknown simulation"
    turn_index = str(row.get("turn_index", "")).strip()

    st.subheader(simulation_id)
    if turn_index:
        st.caption(f"Selected row turn: {turn_index}")
    render_row_text_review(row)

    transcript_path = simulation_transcript_path_for_row(run_directory, row)
    event_log_path = simulation_event_log_path_for_row(run_directory, row)
    audio_paths = simulation_audio_paths_for_row(run_directory, row)

    transcript_tab, events_tab, audio_tab = st.tabs(
        ["Transcript", "Events", "Audio by turn"]
    )

    with transcript_tab:
        transcript_text = read_text_if_present(transcript_path)
        if transcript_text is None:
            st.info("No transcript found for this simulation.")
        else:
            st.code(transcript_text, language="text")
            st.caption(str(transcript_path))

    with events_tab:
        event_log_text = read_text_if_present(event_log_path)
        if event_log_text is None:
            st.info("No event log found for this simulation.")
        else:
            st.code(event_log_text, language="json")
            st.caption(str(event_log_path))

    with audio_tab:
        if not audio_paths:
            st.info("No turn audio files found for this simulation.")
        else:
            for audio_path in audio_paths:
                st.caption(audio_path.name)
                audio_bytes = audio_bytes_if_present(audio_path)
                if audio_bytes is None:
                    st.info("Could not load this audio file.")
                    continue
                st.audio(audio_bytes, format="audio/wav")
                st.caption(str(audio_path))


def render_comparison_view() -> None:
    st.title("Comparison View")
    st.caption("Compare metrics across one or more saved realtime eval runs.")

    harness, selected_paths = render_comparison_config_bar()

    st.divider()

    if not selected_paths:
        st.info(
            "Choose one or more result directories from the Results browser to continue."
        )
        return

    summaries, load_errors = load_selected_summaries(selected_paths)
    for error_message in load_errors:
        st.warning(error_message)

    if not summaries:
        st.error(
            "No valid `summary.json` files could be loaded from the selected runs."
        )
        return

    st.subheader("Selected Result Directories")
    selected_runs_text = "\n".join(
        f"{index}. {display_run_label(path)}"
        for index, path in enumerate(selected_paths, start=1)
    )
    st.code(selected_runs_text, language="text")

    score_keys, latency_config, token_config = selected_metric_controls(
        harness, summaries
    )

    st.subheader("Summary Table")
    summary_table = build_summary_table(
        summaries,
        selected_score_keys=score_keys,
        latency_metric_config=latency_config,
        token_metric_config=token_config,
    )
    if summary_table.empty:
        st.info("No table columns are currently selected.")
    else:
        st.dataframe(summary_table, use_container_width=True, hide_index=True)

    st.subheader("Overall Scores (higher is better)")
    render_grouped_bar_chart(build_score_chart_frame(summaries, score_keys))

    st.subheader("Latency (lower is better)")
    render_percentile_ladder_chart(
        build_percentile_chart_frame(summaries, latency_config),
        y_title="Latency (ms)",
    )

    st.subheader("Token Consumption (lower is better)")
    render_percentile_ladder_chart(
        build_percentile_chart_frame(summaries, token_config),
        y_title="Tokens",
    )


def render_run_viewer() -> None:
    st.title("Run Viewer")
    st.caption(
        "Inspect one saved run and drill into example- or simulation-level artifacts."
    )

    harness, selected_path = render_run_viewer_config_bar()

    st.divider()

    if selected_path is None:
        st.info("Choose a result directory for the selected harness to continue.")
        return

    results, load_error = load_results_frame(selected_path)
    if load_error is not None:
        st.error(load_error)
        return
    if results is None or results.empty:
        st.info("This run does not contain any rows in `results.csv`.")
        return

    st.caption(f"Viewing `{display_run_label(selected_path)}`")

    active_row_key = run_viewer_active_row_key(harness, selected_path)
    table_selection_key = run_viewer_table_selection_key(harness, selected_path)
    table_revision_key = run_viewer_table_revision_key(harness, selected_path)
    table_revision = normalize_table_revision(
        st.session_state.get(table_revision_key)
    )
    previous_table_selected_index = normalize_row_index(
        st.session_state.get(table_selection_key),
        len(results),
    )
    render_active_row_index = resolve_active_row_index(
        previous_table_selected_index,
        previous_table_selected_index,
        st.session_state.get(active_row_key),
        len(results),
    )

    table_column, detail_column = st.columns([1.45, 1], gap="large")

    with table_column:
        st.subheader("Examples" if harness != "run" else "Simulation rows")
        table_widget_key = run_viewer_table_widget_key(
            harness,
            selected_path,
            table_revision,
        )
        selection = st.data_editor(
            build_run_viewer_table(results, render_active_row_index),
            height=run_viewer_table_height(len(results)),
            use_container_width=True,
            hide_index=True,
            column_config={
                RUN_VIEWER_SELECTED_COLUMN: st.column_config.CheckboxColumn(
                    " ",
                    width="small",
                )
            },
            disabled=list(results.columns),
            row_height=RUN_VIEWER_TABLE_ROW_HEIGHT,
            key=table_widget_key,
        )

    with detail_column:
        st.subheader("Example Viewer" if harness != "run" else "Simulation Viewer")
        table_selected_index = resolve_run_viewer_table_selected_index(
            selection,
            st.session_state.get(table_widget_key),
            render_active_row_index,
        )
        active_row_index = resolve_active_row_index(
            table_selected_index,
            previous_table_selected_index,
            st.session_state.get(active_row_key),
            len(results),
        )
        st.session_state[table_selection_key] = table_selected_index
        st.session_state[active_row_key] = active_row_index
        if active_row_index is None:
            st.info("No datapoints are available to inspect.")
            return
        if not run_viewer_table_matches_active_row(selection, active_row_index):
            refresh_run_viewer_table_state(harness, selected_path, active_row_index)
            st.rerun()

        nav_previous_column, nav_status_column, nav_next_column = st.columns(
            [1, 1.2, 1]
        )
        with nav_previous_column:
            if st.button(
                "Previous",
                key=f"{active_row_key}_previous",
                disabled=active_row_index <= 0,
                use_container_width=True,
            ):
                previous_row_index = active_row_index - 1
                st.session_state[active_row_key] = previous_row_index
                refresh_run_viewer_table_state(
                    harness,
                    selected_path,
                    previous_row_index,
                )
                st.rerun()
        with nav_status_column:
            st.caption(f"Datapoint {active_row_index + 1} of {len(results)}")
        with nav_next_column:
            if st.button(
                "Next",
                key=f"{active_row_key}_next",
                disabled=active_row_index >= len(results) - 1,
                use_container_width=True,
            ):
                next_row_index = active_row_index + 1
                st.session_state[active_row_key] = next_row_index
                refresh_run_viewer_table_state(
                    harness,
                    selected_path,
                    next_row_index,
                )
                st.rerun()

        selected_row = results.iloc[active_row_index]
        if harness == "run":
            render_simulation_viewer(selected_path, selected_row)
        else:
            render_example_viewer(selected_path, selected_row)


def main() -> None:
    st.set_page_config(
        page_title="Realtime Results Viewer",
        page_icon=":bar_chart:",
        layout="wide",
    )
    load_css()

    navigation = st.navigation(
        [
            st.Page(render_comparison_view, title="Comparison View", default=True),
            st.Page(render_run_viewer, title="Run Viewer"),
        ]
    )
    navigation.run()


if __name__ == "__main__":
    main()
