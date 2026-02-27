from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd
import streamlit as st

if TYPE_CHECKING:
    from results_viewer.config import (
        DEFAULT_SCORE_KEYS,
        DEFAULT_LATENCY_SERIES,
        DEFAULT_TOKEN_SERIES,
        LATENCY_CHART_KEYS,
        PERCENTILE_LABELS,
        SCORE_KEY_LABELS,
        SUMMARY_TABLE_BASE_COLUMNS,
        TOKEN_CHART_KEYS,
    )
else:
    try:
        from .config import (
            DEFAULT_SCORE_KEYS,
            DEFAULT_LATENCY_SERIES,
            DEFAULT_TOKEN_SERIES,
            LATENCY_CHART_KEYS,
            PERCENTILE_LABELS,
            SCORE_KEY_LABELS,
            SUMMARY_TABLE_BASE_COLUMNS,
            TOKEN_CHART_KEYS,
        )
    except ImportError:
        from config import (
            DEFAULT_SCORE_KEYS,
            DEFAULT_LATENCY_SERIES,
            DEFAULT_TOKEN_SERIES,
            LATENCY_CHART_KEYS,
            PERCENTILE_LABELS,
            SCORE_KEY_LABELS,
            SUMMARY_TABLE_BASE_COLUMNS,
            TOKEN_CHART_KEYS,
        )

ROOT_DIR = Path(__file__).resolve().parents[1]
HARNESS_RESULTS_DIRS = {
    "crawl": ROOT_DIR / "crawl_harness" / "results",
    "walk": ROOT_DIR / "walk_harness" / "results",
    "run": ROOT_DIR / "run_harness" / "results",
}


def discover_result_directories(results_root: Path) -> list[Path]:
    if not results_root.exists():
        return []

    run_directories = {
        path.parent
        for path in results_root.rglob("*")
        if path.is_file() and path.name in {"results.csv", "summary.json"}
    }
    return sorted(run_directories)


def relative_directory_labels(paths: list[Path], root: Path) -> list[str]:
    return [str(path.relative_to(root)) for path in paths]


def summary_path_for_run(run_directory: Path) -> Path:
    return run_directory / "summary.json"


def coerce_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float, str)):
        return float(value)
    return None


def selected_result_directories(harness: str) -> list[Path]:
    results_root = HARNESS_RESULTS_DIRS[harness]
    available_paths = discover_result_directories(results_root)
    available_labels = relative_directory_labels(available_paths, results_root)

    current_selection = st.session_state.get(f"selected_results_{harness}", [])
    valid_defaults = [label for label in current_selection if label in available_labels]

    with st.popover("Results browser"):
        st.caption(f"Browsing `{results_root.relative_to(ROOT_DIR)}`")
        if not available_labels:
            st.info("No result directories found for this harness yet.")
            return []

        st.multiselect(
            "Select one or more result directories",
            options=available_labels,
            default=valid_defaults,
            key=f"selected_results_{harness}",
            placeholder="Choose saved runs",
        )

    selected_set = set(st.session_state.get(f"selected_results_{harness}", []))
    return [
        path
        for path, label in zip(available_paths, available_labels, strict=False)
        if label in selected_set
    ]


def load_selected_summaries(
    selected_paths: list[Path], results_root: Path
) -> tuple[list[dict[str, object]], list[str]]:
    loaded_summaries: list[dict[str, object]] = []
    load_errors: list[str] = []

    for run_directory in selected_paths:
        summary_path = summary_path_for_run(run_directory)
        run_label = str(run_directory.relative_to(results_root))
        if not summary_path.exists():
            load_errors.append(f"`{run_label}` is missing `summary.json`.")
            continue

        try:
            summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            load_errors.append(f"`{run_label}` has an invalid `summary.json`.")
            continue

        if not isinstance(summary_payload, dict):
            load_errors.append(f"`{run_label}` has a non-object `summary.json`.")
            continue

        loaded_summaries.append(
            {
                "run_label": run_label,
                "run_directory": str(run_directory),
                "summary_path": str(summary_path),
                **summary_payload,
            }
        )

    return loaded_summaries, load_errors


def build_score_chart_frame(
    summaries: list[dict[str, object]], metric_keys: list[str]
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for summary in summaries:
        run_label = str(summary["run_label"])
        for metric_key in metric_keys:
            metric_value = coerce_float(summary.get(metric_key))
            if metric_value is None:
                continue
            rows.append(
                {
                    "run_label": run_label,
                    "metric_key": metric_key,
                    "metric_label": SCORE_KEY_LABELS.get(metric_key, metric_key),
                    "value": metric_value,
                }
            )
    return pd.DataFrame(rows)


def available_score_keys(summaries: list[dict[str, object]]) -> list[str]:
    return [
        metric_key
        for metric_key in DEFAULT_SCORE_KEYS
        if any(summary.get(metric_key) is not None for summary in summaries)
    ]


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
        run_label = str(summary["run_label"])
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
            format_func=lambda key: SCORE_KEY_LABELS.get(key, key),
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
        rows.append({column: summary.get(column) for column in ordered_columns})

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows)


def render_grouped_bar_chart(data: pd.DataFrame) -> None:
    if data.empty:
        st.info("No score metrics were found in the selected summaries.")
        return

    st.vega_lite_chart(
        data,
        {
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
                            "value": "#1f2937",
                        },
                    },
                },
            ]
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
                            },
                            "tooltip": [
                                {"field": "run_label", "type": "nominal", "title": "Run"},
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
                            "color": {"value": "#1f2937"},
                        },
                    },
                ],
                "height": 180,
            },
            use_container_width=True,
        )


def render_config_bar() -> tuple[str, list[Path]]:
    with st.container():
        left, middle, right = st.columns([1.2, 1.4, 1])

        with left:
            harness = st.selectbox(
                "Harness",
                options=["crawl", "walk", "run"],
                index=0,
                format_func=lambda value: f"{value}_harness",
            )

        with middle:
            selected_paths = selected_result_directories(harness)

        with right:
            st.metric("Selected runs", len(selected_paths))

    return harness, selected_paths


def main() -> None:
    st.set_page_config(
        page_title="Realtime Results Viewer",
        page_icon=":bar_chart:",
        layout="wide",
    )

    st.title("Realtime Results Viewer")
    st.caption(
        "Scaffold only for now: choose a harness and one or more saved result directories."
    )

    harness, selected_paths = render_config_bar()
    results_root = HARNESS_RESULTS_DIRS[harness]

    st.divider()

    if not selected_paths:
        st.info(
            f"Choose one or more result directories from `{results_root.relative_to(ROOT_DIR)}` to continue."
        )
        return

    summaries, load_errors = load_selected_summaries(selected_paths, results_root)
    for error_message in load_errors:
        st.warning(error_message)

    if not summaries:
        st.error(
            "No valid `summary.json` files could be loaded from the selected runs."
        )
        return

    st.subheader("Selected Result Directories")
    st.write([str(path.relative_to(ROOT_DIR)) for path in selected_paths])

    score_keys, latency_config, token_config = selected_metric_controls(
        harness, summaries
    )

    st.subheader("Overall Scores")
    render_grouped_bar_chart(build_score_chart_frame(summaries, score_keys))

    st.subheader("Latency")
    render_percentile_ladder_chart(
        build_percentile_chart_frame(summaries, latency_config),
        y_title="Latency (ms)",
    )

    st.subheader("Token Consumption")
    render_percentile_ladder_chart(
        build_percentile_chart_frame(summaries, token_config),
        y_title="Tokens",
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
        st.dataframe(summary_table, use_container_width=True)


if __name__ == "__main__":
    main()
