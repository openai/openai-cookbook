"""Offline answer grading and comparison; no agent calls are made here."""

from typing import Any

import pandas as pd
from live_api import JUDGE_MODEL, live_judge_response
from openai import OpenAIError
from simulation import deterministic_guardrail_check


def evaluate_answer_traces(
    tickets: list[dict[str, Any]],
    traces: list[dict[str, Any]],
    *,
    client: Any = None,
) -> pd.DataFrame:
    """Grade existing traces once each, or report not_run without a client."""
    tickets_by_id = {ticket["ticket_id"]: ticket for ticket in tickets}
    rows = []
    for trace in traces:
        ticket = tickets_by_id[trace["ticket_id"]]
        grade = {
            "judge_model": JUDGE_MODEL,
            "judge_status": "not_run",
            "passed": None,
            "reason": "Set RUN_LLM_JUDGE=true to enable the optional judge.",
            "judge_cost_usd": None,
            "judge_usage": None,
        }
        if client is not None:
            try:
                grade = live_judge_response(
                    ticket,
                    trace["customer_response"],
                    trace["tool_results"],
                    client=client,
                )
            except OpenAIError as exc:
                grade.update(
                    judge_status="error",
                    reason=f"Judge request failed ({type(exc).__name__}); no grade available.",
                )
        rows.append(
            {
                "variant": trace["variant"],
                "variant_label": trace["variant_label"],
                "ticket_id": trace["ticket_id"],
                "deterministic_passed": not deterministic_guardrail_check(
                    ticket, trace
                ),
                **grade,
            }
        )
    return pd.DataFrame(rows)


def summarize_answer_evals(results: pd.DataFrame) -> pd.DataFrame:
    """Report coverage and known evaluation spend alongside independent quality gates."""
    rows = []
    for variant, group in results.groupby("variant", sort=False):
        graded = group[group["judge_status"] == "graded"]
        attempted = group[group["judge_status"] != "not_run"]
        rows.append(
            {
                "variant": variant,
                "variant_label": group["variant_label"].iloc[0],
                "tickets": len(group),
                "deterministic_pass_rate": group["deterministic_passed"].mean(),
                "judge_graded": len(graded),
                "judge_coverage": len(graded) / len(group),
                "judge_errors": int((group["judge_status"] == "error").sum()),
                "judge_pass_rate": graded["passed"].mean()
                if len(graded)
                else float("nan"),
                "both_pass_rate": (
                    (graded["passed"] & graded["deterministic_passed"]).mean()
                    if len(graded)
                    else float("nan")
                ),
                "known_judge_cost_usd": group["judge_cost_usd"].sum(min_count=1),
                "judge_cost_unavailable": int(attempted["judge_cost_usd"].isna().sum()),
            }
        )
    return pd.DataFrame(rows)
