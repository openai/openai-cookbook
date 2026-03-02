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
    "#79b7ff",
    "#67ecff",
    "#ff8ea9",
    "#ffb066",
    "#c894ff",
    "#77a1ff",
]


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


def results_csv_path_for_run(run_directory: Path) -> Path:
    return run_directory / "results.csv"


def coerce_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float, str)):
        return float(value)
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


def selected_result_directories(harness: str) -> list[Path]:
    results_root = HARNESS_RESULTS_DIRS[harness]
    available_paths = discover_result_directories(results_root)
    available_labels = relative_directory_labels(available_paths, results_root)

    selection_key = f"selected_results_{harness}"
    select_all_key = f"selected_results_all_{harness}"

    current_selection = st.session_state.get(selection_key, [])
    valid_defaults = [label for label in current_selection if label in available_labels]
    all_selected = bool(available_labels) and len(valid_defaults) == len(available_labels)

    if selection_key not in st.session_state:
        st.session_state[selection_key] = valid_defaults
    if select_all_key not in st.session_state:
        st.session_state[select_all_key] = all_selected

    if st.session_state.get(select_all_key) and st.session_state.get(
        selection_key
    ) != available_labels:
        st.session_state[selection_key] = available_labels
    elif not st.session_state.get(select_all_key) and st.session_state.get(
        selection_key
    ) != valid_defaults:
        st.session_state[selection_key] = valid_defaults

    with st.popover("Results browser"):
        st.caption(f"Browsing `{results_root.relative_to(ROOT_DIR)}`")
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
    results_root = HARNESS_RESULTS_DIRS[harness]
    available_paths = discover_result_directories(results_root)
    available_labels = relative_directory_labels(available_paths, results_root)

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
    )
    if not selected_label:
        return None

    return available_paths[available_labels.index(selected_label)]


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


def load_results_frame(run_directory: Path) -> tuple[pd.DataFrame | None, str | None]:
    results_csv_path = results_csv_path_for_run(run_directory)
    if not results_csv_path.exists():
        return None, "This run is missing `results.csv`."

    try:
        results = pd.read_csv(results_csv_path, keep_default_na=False)
    except Exception as exc:
        return None, f"Could not load `results.csv`: {exc}"

    return results, None


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
            "config": {
                "view": {"stroke": None},
                "background": "transparent",
                "axis": {
                    "labelColor": "#eef4ff",
                    "titleColor": "#eef4ff",
                    "domainColor": "rgba(167, 184, 218, 0.18)",
                    "gridColor": "rgba(167, 184, 218, 0.12)",
                    "tickColor": "rgba(167, 184, 218, 0.18)",
                },
                "legend": {
                    "labelColor": "#eef4ff",
                    "titleColor": "#eef4ff",
                },
            },
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
                            "value": "#eef4ff",
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
                "config": {
                    "view": {"stroke": None},
                    "background": "transparent",
                    "axis": {
                        "labelColor": "#eef4ff",
                        "titleColor": "#eef4ff",
                        "domainColor": "rgba(167, 184, 218, 0.18)",
                        "gridColor": "rgba(167, 184, 218, 0.12)",
                        "tickColor": "rgba(167, 184, 218, 0.18)",
                    },
                    "legend": {
                        "labelColor": "#eef4ff",
                        "titleColor": "#eef4ff",
                    },
                },
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
                            "color": {"value": "#eef4ff"},
                        },
                    },
                ],
                "height": 180,
            },
            use_container_width=True,
        )


def render_comparison_config_bar() -> tuple[str, list[Path]]:
    with st.container():
        left, right = st.columns([1.6, 1])

        with left:
            harness = st.selectbox(
                "Harness",
                options=["crawl", "walk", "run"],
                index=0,
                format_func=lambda value: f"{value}_harness",
                key="comparison_harness",
            )

        with right:
            selected_runs_metric = st.empty()

        selected_paths = selected_result_directories(harness)
        selected_runs_metric.metric("Selected runs", len(selected_paths))

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


def clean_path_value(value: object) -> Path | None:
    if not isinstance(value, str):
        return None
    cleaned_value = value.strip()
    if not cleaned_value:
        return None
    return Path(cleaned_value)


def simulation_id_for_row(row: pd.Series) -> str:
    return str(row.get("simulation_id", "")).strip()


def selected_row_indices(selection_state: object) -> list[int]:
    selection = getattr(selection_state, "selection", None)
    rows = getattr(selection, "rows", [])
    if not isinstance(rows, list):
        return []
    return [row_index for row_index in rows if isinstance(row_index, int)]


def input_audio_path_for_row(run_directory: Path, row: pd.Series) -> Path | None:
    for column_name in ("input_audio_path", "audio_path"):
        candidate = clean_path_value(row.get(column_name, ""))
        if candidate is not None:
            return candidate

    example_id = str(row.get("example_id", "")).strip()
    if not example_id:
        return None
    candidate = run_directory / "audio" / example_id / "input.wav"
    if candidate.exists():
        return candidate
    return None


def output_audio_path_for_row(run_directory: Path, row: pd.Series) -> Path | None:
    candidate = clean_path_value(row.get("output_audio_path", ""))
    if candidate is not None:
        return candidate

    example_id = str(row.get("example_id", "")).strip()
    if not example_id:
        return None
    candidate = run_directory / "audio" / example_id / "output.wav"
    if candidate.exists():
        return candidate
    return None


def event_log_path_for_row(run_directory: Path, row: pd.Series) -> Path | None:
    candidate = clean_path_value(row.get("event_log_path", ""))
    if candidate is not None:
        return candidate

    example_id = str(row.get("example_id", "")).strip()
    if not example_id:
        return None
    candidate = run_directory / "events" / f"{example_id}.jsonl"
    if candidate.exists():
        return candidate
    return None


def simulation_transcript_path_for_row(run_directory: Path, row: pd.Series) -> Path | None:
    simulation_id = simulation_id_for_row(row)
    if not simulation_id:
        return None

    candidate = run_directory / "conversations" / f"{simulation_id}.txt"
    if candidate.exists():
        return candidate
    return None


def simulation_event_log_path_for_row(run_directory: Path, row: pd.Series) -> Path | None:
    candidate = clean_path_value(row.get("event_log_path", ""))
    if candidate is not None:
        return candidate

    simulation_id = simulation_id_for_row(row)
    if not simulation_id:
        return None

    candidate = run_directory / "events" / f"{simulation_id}.jsonl"
    if candidate.exists():
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

    audio_dir = run_directory / "audio" / simulation_id
    if not audio_dir.exists():
        return []

    return sorted(audio_dir.glob("*.wav"), key=_audio_sort_key)


def render_example_viewer(run_directory: Path, row: pd.Series) -> None:
    example_id = str(row.get("example_id", "")).strip() or "Unknown example"

    st.subheader(example_id)

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
    selected_runs_text = "\n".join(
        f"{index}. {path.relative_to(ROOT_DIR)}"
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
    st.caption("Inspect one saved run and drill into example- or simulation-level artifacts.")

    harness, selected_path = render_run_viewer_config_bar()
    results_root = HARNESS_RESULTS_DIRS[harness]

    st.divider()

    if selected_path is None:
        st.info(
            f"Choose a result directory from `{results_root.relative_to(ROOT_DIR)}` to continue."
        )
        return

    results, load_error = load_results_frame(selected_path)
    if load_error is not None:
        st.error(load_error)
        return
    if results is None or results.empty:
        st.info("This run does not contain any rows in `results.csv`.")
        return

    st.caption(f"Viewing `{selected_path.relative_to(ROOT_DIR)}`")

    table_column, detail_column = st.columns([1.45, 1], gap="large")

    with table_column:
        st.subheader("Examples" if harness != "run" else "Simulation rows")
        selection = st.dataframe(
            results,
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key=f"run_viewer_table_{harness}_{selected_path.name}",
        )

    with detail_column:
        st.subheader("Example Viewer" if harness != "run" else "Simulation Viewer")
        selected_rows = selected_row_indices(selection)
        if not selected_rows:
            st.info(
                "Select a row in the table to inspect its artifacts."
            )
            return

        selected_row = results.iloc[selected_rows[0]]
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
