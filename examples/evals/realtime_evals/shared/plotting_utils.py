"""Styled plots for realtime eval run artifacts."""

from pathlib import Path
from typing import Any, Mapping

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns  # type: ignore[import-untyped]
from matplotlib.lines import Line2D

PAPER = "#f7f4ee"
AXIS_BG = "#fbf9f5"
GRID = "#ddd7cc"
TEXT = "#2c2823"
EDGE = "#2d261f"
SPINE = "#d7d0c4"

BASELINE = "#dd7f00"
TEAL_DARK = "#1c7f77"
TEAL_LIGHT = "#3fc4b7"
BLUE_DARK = "#3266d6"
BLUE_LIGHT = "#84acd8"
ORANGE_DARK = "#cc4a06"
ORANGE_LIGHT = "#efb26d"
PURPLE_DARK = "#7b39db"

FONT_STACK = [
    "Avenir Next",
    "Avenir",
    "Helvetica Neue",
    "Helvetica",
    "Arial",
    "DejaVu Sans",
]

LATENCY_COLUMNS = [
    "latency_first_audio_ms",
    "latency_first_text_ms",
    "latency_response_done_ms",
]
TOKEN_COLUMNS = [
    "output_tokens",
    "output_audio_tokens",
    "output_text_tokens",
]


def _coerce_summary_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _coerce_summary_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def build_realtime_eval_plots(
    results: pd.DataFrame,
    summary: Mapping[str, Any],
    output_dir: Path,
    harness_label: str,
    run_name: str,
) -> list[Path]:
    """Render a consistent set of plots for one realtime eval run."""
    output_dir.mkdir(parents=True, exist_ok=True)
    _apply_chart_theme()

    plot_paths: list[Path] = []
    scorecard_path = output_dir / "scorecard.png"
    _plot_scorecard(results, summary, scorecard_path, harness_label, run_name)
    plot_paths.append(scorecard_path)

    detail_path = _plot_detail_panels(
        results=results,
        output_dir=output_dir,
        harness_label=harness_label,
        run_name=run_name,
    )
    if detail_path is not None:
        plot_paths.append(detail_path)

    turn_trends_path = _plot_turn_trends(
        results=results,
        output_dir=output_dir,
        harness_label=harness_label,
        run_name=run_name,
    )
    if turn_trends_path is not None:
        plot_paths.append(turn_trends_path)

    return plot_paths


def _apply_chart_theme() -> None:
    sns.set_theme(
        style="whitegrid",
        rc={
            "figure.facecolor": PAPER,
            "axes.facecolor": AXIS_BG,
            "axes.edgecolor": SPINE,
            "axes.labelcolor": TEXT,
            "text.color": TEXT,
            "xtick.color": TEXT,
            "ytick.color": TEXT,
            "axes.titlecolor": TEXT,
            "axes.titleweight": "normal",
            "axes.labelweight": "normal",
            "font.weight": "normal",
            "font.family": "sans-serif",
            "font.sans-serif": FONT_STACK,
            "grid.color": GRID,
            "grid.linewidth": 0.8,
            "axes.grid": False,
        },
    )


def _plot_scorecard(
    results: pd.DataFrame,
    summary: Mapping[str, Any],
    output_path: Path,
    harness_label: str,
    run_name: str,
) -> None:
    figure, axes = plt.subplots(2, 2, figsize=(16, 12))
    figure.patch.set_facecolor(PAPER)
    figure.suptitle(
        f"{harness_label} realtime evals · {run_name}",
        x=0.06,
        y=0.98,
        ha="left",
        fontsize=19,
        fontweight="normal",
    )

    score_ax = axes[0, 0]
    latency_ax = axes[0, 1]
    token_ax = axes[1, 0]
    status_ax = axes[1, 1]

    _style_axis(score_ax)
    _style_axis(latency_ax)
    _style_axis(token_ax)
    _style_axis(status_ax)

    _plot_score_metrics(score_ax, summary)
    _plot_latency_quantiles(latency_ax, summary)
    _plot_token_summary(token_ax, summary)
    _plot_status_donut(status_ax, results)

    figure.subplots_adjust(left=0.07, right=0.97, top=0.90, bottom=0.08, hspace=0.34)
    figure.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(figure)


def _plot_detail_panels(
    *,
    results: pd.DataFrame,
    output_dir: Path,
    harness_label: str,
    run_name: str,
) -> Path | None:
    panels: list[tuple[str, str]] = []
    if _numeric_series(results, "latency_response_done_ms") is not None:
        panels.append(("latency_distribution", "latency"))
    if (
        _numeric_series(results, "output_tokens") is not None
        and _numeric_series(results, "latency_response_done_ms") is not None
    ):
        panels.append(("token_latency_scatter", "scatter"))

    if not panels:
        return None

    figure, axes = plt.subplots(1, len(panels), figsize=(8 * len(panels), 5.8))
    if len(panels) == 1:
        axes = [axes]
    figure.patch.set_facecolor(PAPER)
    figure.suptitle(
        f"{harness_label} distributions · {run_name}",
        x=0.06,
        y=0.98,
        ha="left",
        fontsize=18,
        fontweight="normal",
    )

    for axis, (_, panel_kind) in zip(axes, panels, strict=False):
        _style_axis(axis)
        if panel_kind == "latency":
            _plot_latency_distribution(axis, results)
        else:
            _plot_token_latency_scatter(axis, results)

    figure.subplots_adjust(left=0.07, right=0.97, top=0.85, bottom=0.12, wspace=0.24)
    output_path = output_dir / "detail_panels.png"
    figure.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(figure)
    return output_path


def _plot_turn_trends(
    *,
    results: pd.DataFrame,
    output_dir: Path,
    harness_label: str,
    run_name: str,
) -> Path | None:
    turn_index = _numeric_series(results, "turn_index")
    if turn_index is None or turn_index.nunique() < 2:
        return None

    grouped = pd.DataFrame({"turn_index": turn_index})
    latency_series = _numeric_series(results, "latency_response_done_ms")
    if latency_series is not None:
        grouped["latency_response_done_ms"] = latency_series

    grade_column = _preferred_grade_column(results)
    if grade_column is not None:
        grouped[grade_column] = _numeric_series(results, grade_column)

    grouped = grouped.groupby("turn_index", as_index=False).mean(numeric_only=True)
    if grouped.empty:
        return None

    figure, axes = plt.subplots(1, 2, figsize=(15, 5.8))
    figure.patch.set_facecolor(PAPER)
    figure.suptitle(
        f"{harness_label} turn trends · {run_name}",
        x=0.06,
        y=0.98,
        ha="left",
        fontsize=18,
        fontweight="normal",
    )

    latency_ax, grade_ax = axes
    _style_axis(latency_ax)
    _style_axis(grade_ax)

    if "latency_response_done_ms" in grouped.columns:
        latency_ax.plot(
            grouped["turn_index"],
            grouped["latency_response_done_ms"],
            color=TEAL_DARK,
            linewidth=2.8,
            marker="o",
            markersize=6,
            markeredgecolor=EDGE,
        )
        latency_ax.set_title(
            "response latency by turn", loc="left", pad=12, fontsize=14
        )
        latency_ax.set_xlabel("turn index", fontsize=12)
        latency_ax.set_ylabel("ms", fontsize=12)
        latency_ax.set_xticks(grouped["turn_index"])
    else:
        _empty_panel(latency_ax, "No turn-level latency values available.")

    if grade_column is not None and grade_column in grouped.columns:
        grade_ax.plot(
            grouped["turn_index"],
            grouped[grade_column],
            color=BLUE_DARK,
            linewidth=2.8,
            marker="o",
            markersize=6,
            markeredgecolor=EDGE,
        )
        grade_ax.set_ylim(0, 1.05)
        grade_ax.set_title("turn-level score by turn", loc="left", pad=12, fontsize=14)
        grade_ax.set_xlabel("turn index", fontsize=12)
        grade_ax.set_ylabel("score", fontsize=12)
        grade_ax.set_xticks(grouped["turn_index"])
        for _, row in grouped.iterrows():
            grade_ax.text(
                row["turn_index"],
                row[grade_column] + 0.03,
                f"{row[grade_column]:.0%}",
                ha="center",
                va="bottom",
                fontsize=10,
                color=TEXT,
            )
    else:
        _empty_panel(grade_ax, "No turn-level grader column found.")

    figure.subplots_adjust(left=0.07, right=0.97, top=0.84, bottom=0.14, wspace=0.22)
    output_path = output_dir / "turn_trends.png"
    figure.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(figure)
    return output_path


def _plot_score_metrics(axis: plt.Axes, summary: Mapping[str, Any]) -> None:
    metric_rows = _score_metric_rows(summary)
    axis.set_title("scorecard metrics", loc="left", pad=12, fontsize=14)
    if not metric_rows:
        _empty_panel(axis, "No score metrics found in summary.json.")
        return

    labels = [label for label, _ in metric_rows]
    values = [value for _, value in metric_rows]
    colors = _palette_cycle(len(metric_rows))
    use_horizontal = len(labels) > 4 or max(len(label) for label in labels) > 12
    if use_horizontal:
        positions = list(range(len(labels)))
        bars = axis.barh(
            positions,
            values,
            color=colors,
            edgecolor=EDGE,
            linewidth=1.2,
            height=0.62,
            zorder=3,
        )
        axis.set_xlim(0, 1.05)
        axis.set_xlabel("share", fontsize=12)
        axis.set_yticks(positions)
        axis.set_yticklabels(labels, fontsize=10)
        axis.tick_params(axis="x", labelsize=10)
        axis.grid(axis="x", color=GRID, linewidth=0.8, alpha=0.9)
        axis.grid(axis="y", visible=False)
        axis.invert_yaxis()
        for bar, value in zip(bars, values, strict=False):
            axis.text(
                value + 0.02,
                bar.get_y() + (bar.get_height() / 2),
                f"{value:.0%}",
                ha="left",
                va="center",
                fontsize=10,
                color=TEXT,
            )
    else:
        bars = axis.bar(
            labels,
            values,
            color=colors,
            edgecolor=EDGE,
            linewidth=1.2,
            width=0.68,
            zorder=3,
        )
        axis.set_ylim(0, 1.05)
        axis.set_ylabel("share", fontsize=12)
        axis.tick_params(axis="x", labelrotation=0, pad=8, labelsize=10)
        axis.tick_params(axis="y", labelsize=10)
        axis.grid(axis="y", color=GRID, linewidth=0.8, alpha=0.9)

        for bar, value in zip(bars, values, strict=False):
            axis.text(
                bar.get_x() + (bar.get_width() / 2),
                value + 0.03,
                f"{value:.0%}",
                ha="center",
                va="bottom",
                fontsize=10,
                color=TEXT,
            )


def _plot_latency_quantiles(axis: plt.Axes, summary: Mapping[str, Any]) -> None:
    quantile_frame = _summary_quantile_frame(
        summary, LATENCY_COLUMNS, ["p50", "p95", "p99"]
    )
    axis.set_title("latency percentiles", loc="left", pad=12, fontsize=14)
    if quantile_frame.empty:
        _empty_panel(axis, "No latency percentile values found.")
        return

    quantile_order = ["p50", "p95", "p99"]
    colors = {
        "p50": TEAL_DARK,
        "p95": BLUE_DARK,
        "p99": ORANGE_DARK,
    }
    for quantile in quantile_order:
        subset = quantile_frame[quantile_frame["stat"] == quantile]
        axis.plot(
            subset["metric_label"],
            subset["value"],
            label=quantile.upper(),
            color=colors[quantile],
            linewidth=2.8,
            marker="o",
            markersize=6,
            markeredgecolor=EDGE,
        )

    axis.set_ylabel("ms", fontsize=12)
    axis.grid(axis="y", color=GRID, linewidth=0.8, alpha=0.9)
    axis.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, 1.12),
        ncol=3,
        frameon=False,
        fontsize=10,
    )


def _plot_token_summary(axis: plt.Axes, summary: Mapping[str, Any]) -> None:
    token_frame = _summary_quantile_frame(summary, TOKEN_COLUMNS, ["avg", "p50", "p95"])
    axis.set_title("token summary", loc="left", pad=12, fontsize=14)
    if token_frame.empty:
        _empty_panel(axis, "No output token summaries found.")
        return

    metrics = token_frame["metric_label"].drop_duplicates().tolist()
    stats = ["avg", "p50", "p95"]
    stat_labels = {"avg": "avg", "p50": "p50", "p95": "p95"}
    stat_colors = {
        "avg": BASELINE,
        "p50": BLUE_DARK,
        "p95": BLUE_LIGHT,
    }
    x_positions = list(range(len(metrics)))
    width = 0.22

    for stat_index, stat in enumerate(stats):
        subset = (
            token_frame[token_frame["stat"] == stat]
            .set_index("metric_label")
            .reindex(metrics)
            .reset_index()
        )
        positions = [position + ((stat_index - 1) * width) for position in x_positions]
        bars = axis.bar(
            positions,
            subset["value"],
            width=width,
            label=stat_labels[stat],
            color=stat_colors[stat],
            edgecolor=EDGE,
            linewidth=1.2,
            zorder=3,
        )
        for bar, value in zip(bars, subset["value"], strict=False):
            axis.text(
                bar.get_x() + (bar.get_width() / 2),
                value + max(0.6, value * 0.02),
                f"{value:.0f}",
                ha="center",
                va="bottom",
                fontsize=9,
                color=TEXT,
            )

    axis.set_xticks(x_positions)
    axis.set_xticklabels(metrics, fontsize=10)
    axis.set_ylabel("tokens", fontsize=12)
    axis.grid(axis="y", color=GRID, linewidth=0.8, alpha=0.9)
    axis.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, 1.12),
        ncol=3,
        frameon=False,
        fontsize=10,
    )


def _plot_status_donut(axis: plt.Axes, results: pd.DataFrame) -> None:
    axis.set_title("run status", loc="left", pad=12, fontsize=14)
    status_counts = _status_counts(results)
    if status_counts.empty:
        _empty_panel(axis, "No status values found in results.csv.")
        return

    labels = status_counts.index.tolist()
    values = status_counts.tolist()
    colors = [_status_color(label) for label in labels]

    total_rows = sum(values)
    if len(labels) == 1:
        label = labels[0]
        axis.pie(
            values,
            colors=colors,
            startangle=92,
            counterclock=False,
            wedgeprops={"edgecolor": EDGE, "linewidth": 1.2, "width": 0.34},
        )
        axis.text(
            0,
            0.10,
            label.replace("_", " "),
            ha="center",
            va="center",
            fontsize=16,
            color=TEXT,
        )
        axis.text(
            0,
            -0.12,
            f"{total_rows} rows",
            ha="center",
            va="center",
            fontsize=11,
            color=TEXT,
        )
        failure_note = _failure_stage_note(results)
        if failure_note:
            axis.text(
                0,
                -1.12,
                failure_note,
                ha="center",
                va="top",
                fontsize=10,
                color=TEXT,
            )
        return

    pie_result = axis.pie(
        values,
        colors=colors,
        startangle=92,
        counterclock=False,
        wedgeprops={"edgecolor": EDGE, "linewidth": 1.2, "width": 0.42},
        autopct=lambda pct: f"{pct:.0f}%" if pct >= 5 else "",
        textprops={"color": TEXT, "fontsize": 11},
    )
    wedges = pie_result[0]
    autotexts = pie_result[2] if len(pie_result) == 3 else []
    axis.text(0, 0, "status", ha="center", va="center", fontsize=14, color=TEXT)
    axis.legend(
        wedges,
        [label.replace("_", " ") for label in labels],
        loc="upper center",
        bbox_to_anchor=(0.5, 1.05),
        ncol=min(3, len(labels)),
        frameon=False,
        fontsize=10,
    )
    for auto_text in autotexts:
        auto_text.set_color(TEXT)

    failure_note = _failure_stage_note(results)
    if failure_note:
        axis.text(
            0,
            -1.18,
            failure_note,
            ha="center",
            va="top",
            fontsize=10,
            color=TEXT,
        )


def _plot_latency_distribution(axis: plt.Axes, results: pd.DataFrame) -> None:
    axis.set_title("response latency distribution", loc="left", pad=12, fontsize=14)
    latency_series = _numeric_series(results, "latency_response_done_ms")
    if latency_series is None:
        _empty_panel(axis, "No response latency values available.")
        return

    plot_frame = pd.DataFrame({"latency_response_done_ms": latency_series})
    plot_frame["status"] = _status_series(results).reindex(plot_frame.index)
    for status, color in _status_palette(plot_frame["status"].dropna().unique()):
        subset = plot_frame[plot_frame["status"] == status]
        if subset.empty:
            continue
        sns.histplot(
            data=subset,
            x="latency_response_done_ms",
            bins=min(14, max(6, subset.shape[0])),
            stat="count",
            element="step",
            fill=True,
            alpha=0.18,
            linewidth=1.4,
            color=color,
            ax=axis,
            label=status.replace("_", " "),
        )
        axis.axvline(
            subset["latency_response_done_ms"].median(),
            color=color,
            linewidth=1.4,
            linestyle="--",
            alpha=0.9,
        )

    axis.set_xlabel("response latency (ms)", fontsize=12)
    axis.set_ylabel("rows", fontsize=12)
    axis.grid(axis="y", color=GRID, linewidth=0.8, alpha=0.9)
    axis.legend(frameon=False, fontsize=10)


def _plot_token_latency_scatter(axis: plt.Axes, results: pd.DataFrame) -> None:
    axis.set_title("tokens vs. response latency", loc="left", pad=12, fontsize=14)
    tokens = _numeric_series(results, "output_tokens")
    latency = _numeric_series(results, "latency_response_done_ms")
    if tokens is None or latency is None:
        _empty_panel(axis, "Need output_tokens and latency_response_done_ms.")
        return

    plot_frame = pd.DataFrame(
        {
            "output_tokens": tokens,
            "latency_response_done_ms": latency,
        }
    ).dropna()
    if plot_frame.empty:
        _empty_panel(axis, "No token/latency rows available.")
        return

    plot_frame["status"] = _status_series(results).reindex(plot_frame.index)
    legend_handles: list[Line2D] = []
    for status, color in _status_palette(plot_frame["status"].dropna().unique()):
        subset = plot_frame[plot_frame["status"] == status]
        if subset.empty:
            continue
        axis.scatter(
            subset["output_tokens"],
            subset["latency_response_done_ms"],
            s=72,
            color=color,
            edgecolor=EDGE,
            linewidth=1.0,
            alpha=0.94,
        )
        legend_handles.append(
            Line2D(
                [0],
                [0],
                marker="o",
                color="none",
                markerfacecolor=color,
                markeredgecolor=EDGE,
                markersize=8,
                label=status.replace("_", " "),
            )
        )

    axis.set_xlabel("output tokens", fontsize=12)
    axis.set_ylabel("response latency (ms)", fontsize=12)
    axis.grid(axis="y", color=GRID, linewidth=0.8, alpha=0.9)
    axis.grid(axis="x", color=GRID, linewidth=0.5, alpha=0.35)
    if legend_handles:
        axis.legend(handles=legend_handles, frameon=False, fontsize=10)


def _style_axis(axis: plt.Axes) -> None:
    axis.set_facecolor(AXIS_BG)
    axis.grid(axis="x", visible=False)
    axis.grid(axis="y", color=GRID, linewidth=0.8, alpha=0.9)
    axis.tick_params(axis="both", labelsize=10, pad=6)
    for spine in axis.spines.values():
        spine.set_color(SPINE)
        spine.set_linewidth(1.0)


def _empty_panel(axis: plt.Axes, message: str) -> None:
    axis.grid(False)
    axis.set_xticks([])
    axis.set_yticks([])
    axis.text(
        0.02,
        0.55,
        message,
        transform=axis.transAxes,
        ha="left",
        va="center",
        fontsize=12,
        color=TEXT,
    )


def _score_metric_rows(summary: Mapping[str, Any]) -> list[tuple[str, float]]:
    rows: list[tuple[str, float]] = []
    total_count = _summary_total_count(summary)
    failed_count = _summary_failed_count(summary)
    if total_count > 0:
        rows.append(("success rate", max(0.0, 1.0 - (failed_count / total_count))))
    grade_mean = _coerce_summary_float(summary.get("grade_mean"))
    if grade_mean is not None:
        rows.append(("overall grade", grade_mean))

    preferred_keys = [
        "tool_call_correctness_mean",
        "tool_call_arg_correctness_mean",
    ]
    for key in preferred_keys:
        metric_value = _coerce_summary_float(summary.get(key))
        if metric_value is not None:
            rows.append((_metric_label(key), metric_value))

    extra_grade_keys = sorted(
        key
        for key in summary
        if key.endswith("_mean")
        and key not in {"grade_mean", *preferred_keys}
        and (key.replace("_mean", "").endswith("_grade") or key.startswith("grade_"))
    )
    for key in extra_grade_keys[:4]:
        metric_value = _coerce_summary_float(summary.get(key))
        if metric_value is not None:
            rows.append((_metric_label(key), metric_value))
    return rows


def _summary_quantile_frame(
    summary: Mapping[str, Any],
    metric_columns: list[str],
    stat_names: list[str],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for column in metric_columns:
        for stat_name in stat_names:
            key = f"{column}_{stat_name}"
            value = _coerce_summary_float(summary.get(key))
            if value is None:
                continue
            rows.append(
                {
                    "metric": column,
                    "metric_label": _metric_label(column),
                    "stat": stat_name,
                    "value": value,
                }
            )
    return pd.DataFrame(rows)


def _summary_total_count(summary: Mapping[str, Any]) -> int:
    for key in ("total_examples", "total_rows"):
        value = _coerce_summary_int(summary.get(key))
        if value is not None:
            return value
    return 0


def _summary_failed_count(summary: Mapping[str, Any]) -> int:
    for key in ("failed_examples", "failed_simulations"):
        value = _coerce_summary_int(summary.get(key))
        if value is not None:
            return value
    return 0


def _status_counts(results: pd.DataFrame) -> pd.Series:
    status = _status_series(results)
    return status.value_counts()


def _status_series(results: pd.DataFrame) -> pd.Series:
    if "status" not in results.columns:
        return pd.Series("ok", index=results.index, dtype="object")
    status = results["status"].fillna("").astype(str).str.strip()
    return status.where(status != "", "ok")


def _failure_stage_note(results: pd.DataFrame) -> str:
    if "status" not in results.columns or "failure_stage" not in results.columns:
        return ""
    failed_rows = results[_status_series(results) == "failed"]
    if failed_rows.empty:
        return ""
    stages = (
        failed_rows["failure_stage"]
        .fillna("")
        .astype(str)
        .str.strip()
        .replace("", "unspecified")
        .value_counts()
    )
    top_stages = stages.head(2)
    notes = [f"{stage}: {count}" for stage, count in top_stages.items()]
    return "top failures · " + "  |  ".join(notes)


def _preferred_grade_column(results: pd.DataFrame) -> str | None:
    if "grade" in results.columns:
        return "grade"
    grade_columns = sorted(
        column for column in results.columns if column.endswith("_grade")
    )
    if grade_columns:
        return grade_columns[0]
    return None


def _numeric_series(results: pd.DataFrame, column: str) -> pd.Series | None:
    if column not in results.columns:
        return None
    series = pd.to_numeric(results[column], errors="coerce").dropna()
    if series.empty:
        return None
    return series


def _metric_label(metric_name: str) -> str:
    label_overrides = {
        "tool_call_correctness_mean": "tool call",
        "tool_call_arg_correctness_mean": "tool args",
        "latency_first_audio_ms": "first audio",
        "latency_first_text_ms": "first text",
        "latency_response_done_ms": "response done",
        "output_tokens": "all output",
        "output_audio_tokens": "audio output",
        "output_text_tokens": "text output",
    }
    if metric_name in label_overrides:
        return label_overrides[metric_name]

    label = metric_name
    if label.endswith("_mean"):
        label = label[: -len("_mean")]
    if label.endswith("_grade"):
        label = label[: -len("_grade")]
    label = label.replace("_tool_call_args", "_args")
    label = label.replace("_tool_call", "_tool")
    words = label.replace("_", " ").split()
    if len(words) > 3:
        words = words[:3]
    return " ".join(words)


def _palette_cycle(count: int) -> list[str]:
    base_palette = [
        BASELINE,
        TEAL_DARK,
        BLUE_DARK,
        ORANGE_DARK,
        PURPLE_DARK,
        TEAL_LIGHT,
        BLUE_LIGHT,
        ORANGE_LIGHT,
    ]
    return [base_palette[index % len(base_palette)] for index in range(count)]


def _status_color(status: str) -> str:
    status_key = status.strip().lower()
    if status_key == "ok":
        return TEAL_DARK
    if status_key == "failed":
        return ORANGE_DARK
    return BLUE_DARK


def _status_palette(status_values: Any) -> list[tuple[str, str]]:
    statuses = sorted(
        {str(value).strip() for value in status_values if str(value).strip()}
    )
    return [(status, _status_color(status)) for status in statuses]
