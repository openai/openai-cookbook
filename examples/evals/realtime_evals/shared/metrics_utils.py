"""Shared metrics helpers for the realtime eval harnesses."""

from typing import Any, Dict, Iterable, List

import pandas as pd


def add_grade_means(summary: Dict[str, Any], results: pd.DataFrame) -> None:
    """Add mean values for any columns that end with `_grade`."""
    grade_columns = [column for column in results.columns if column.endswith("_grade")]
    for column in grade_columns:
        series = results[column].dropna()
        if series.empty:
            continue
        summary[f"{column}_mean"] = float(series.mean())


def add_numeric_summaries(
    summary: Dict[str, Any], results: pd.DataFrame, columns: Iterable[str]
) -> None:
    """Add avg and percentile stats for the requested numeric columns."""
    for column in columns:
        if column not in results.columns:
            continue
        series = results[column].dropna()
        if series.empty:
            continue
        summary[f"{column}_avg"] = float(series.mean())
        summary[f"{column}_p50"] = float(series.quantile(0.5))
        summary[f"{column}_p95"] = float(series.quantile(0.95))
        summary[f"{column}_p99"] = float(series.quantile(0.99))


def order_columns(results: pd.DataFrame, preferred_columns: List[str]) -> pd.DataFrame:
    """Reorder columns so the most important fields are grouped first."""
    remaining_columns = [
        column for column in results.columns if column not in preferred_columns
    ]
    ordered_columns = [
        column for column in preferred_columns if column in results.columns
    ] + remaining_columns
    return results.loc[:, ordered_columns]

