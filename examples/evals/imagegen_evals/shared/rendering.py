from __future__ import annotations

import os
from html import escape
from typing import Optional

from vision_harness.types import TestCase

try:  # Optional notebook rendering support.
    from IPython.display import HTML, display
except ImportError:  # pragma: no cover - only used in notebooks.
    HTML = None
    display = None


def summarize_scores(scores: dict[str, object]) -> str:
    return os.linesep.join(f"{k}: {scores[k]}" for k in sorted(scores.keys()))


def summarize_reasons(reasons: dict[str, str]) -> str:
    verdict_reason = (reasons.get("verdict") or "").strip()
    if verdict_reason:
        return verdict_reason
    return os.linesep.join(
        f"{k}: {reasons[k]}" for k in sorted(reasons.keys()) if reasons[k]
    )


def _pre(text: str) -> str:
    return (
        "<pre style='white-space:pre-wrap; word-break:break-word; margin:0'>"
        f"{escape(text)}"
        "</pre>"
    )


def render_result_table(*, case: TestCase, result: dict[str, object], title: str) -> None:
    sep = os.linesep
    prompt_text = f"{case.prompt}{sep}{sep}Criteria:{sep}{case.criteria}"
    scores = result["scores"]
    reasons = result["reasons"]

    if HTML is None or display is None:
        print(title)
        print(prompt_text)
        print(summarize_scores(scores))
        print(summarize_reasons(reasons))
        return

    prompt_html = _pre(prompt_text)
    scores_html = _pre(summarize_scores(scores))
    reasons_html = _pre(summarize_reasons(reasons))

    table_html = (
        "<table style='width:100%; table-layout:fixed; border-collapse:collapse;'>"
        "<colgroup>"
        "<col style='width:33%'>"
        "<col style='width:33%'>"
        "<col style='width:33%'>"
        "</colgroup>"
        "<thead><tr>"
        "<th style='text-align:left; padding:8px; border-bottom:1px solid #ddd'>Input Prompt</th>"
        "<th style='text-align:left; padding:8px; border-bottom:1px solid #ddd'>Scores</th>"
        "<th style='text-align:left; padding:8px; border-bottom:1px solid #ddd'>Reasoning</th>"
        "</tr></thead>"
        "<tbody><tr>"
        f"<td style='text-align:left; padding:8px; vertical-align:top'>{prompt_html}</td>"
        f"<td style='text-align:left; padding:8px; vertical-align:top'>{scores_html}</td>"
        f"<td style='text-align:left; padding:8px; vertical-align:top'>{reasons_html}</td>"
        "</tr></tbody></table>"
    )

    display(HTML(f"<div style='font-weight:600; margin:6px 0'>{escape(title)}</div>"))
    display(HTML(table_html))
