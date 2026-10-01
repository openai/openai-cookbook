"""Illustrative architecture comparisons using caller-supplied summary metrics."""

from typing import Any

import pandas as pd

ARCHITECTURE_OPTIONS = {
    "baseline_one_big_agent": {
        "label": "One broad agent",
        "variant": "00_bad_baseline",
        "models": "gpt-5.4 for every step",
        "tools": "all tools exposed",
        "cache": "none",
        "workflow": "all work synchronous",
        "best_for": "prototype smell test only",
    },
    "controlled_full_model": {
        "label": "Controlled full model",
        "variant": "01_prompt_tool_context_controls",
        "models": "gpt-5.4 for resolution",
        "tools": "allowed tools by routed path",
        "cache": "none",
        "workflow": "some follow-up still synchronous",
        "best_for": "high-risk launch or low confidence in routing/model mix",
    },
    "routed_no_cache": {
        "label": "Routed, no cache",
        "variant": "02_model_routing",
        "models": "nano triage, mini routine, gpt-5.4 high risk",
        "tools": "allowed tools by routed path",
        "cache": "none",
        "workflow": "some follow-up still synchronous",
        "best_for": "mixed ticket queues with moderate repeat traffic",
    },
    "routed_split_no_cache": {
        "label": "Routed split, no cache",
        "variant": None,
        "models": "nano triage/tags, mini routine, gpt-5.4 high risk",
        "tools": "allowed tools by routed path",
        "cache": "none",
        "workflow": "customer path sync, QA/tags/reporting async",
        "best_for": "low-repeat queues that still need async follow-up work",
    },
    "routed_cache": {
        "label": "Routed + cache",
        "variant": "03_prompt_caching",
        "models": "nano triage, mini routine, gpt-5.4 high risk",
        "tools": "stable full tool list plus allowed_tools",
        "cache": "stable playbook prefix",
        "workflow": "some follow-up still synchronous",
        "best_for": "high-volume repeated workflows with good cache locality",
    },
    "balanced_split": {
        "label": "Balanced split workflow",
        "variant": "04_split_workflow",
        "models": "nano triage/tags, mini routine, gpt-5.4 high risk",
        "tools": "stable full tool list plus allowed_tools",
        "cache": "stable playbook prefix",
        "workflow": "customer path sync, QA/tags/reporting async",
        "best_for": "most mature repeated-workflow support deployments",
    },
}


def architecture_metrics(option_key: str, summary: pd.DataFrame) -> dict[str, Any]:
    option = ARCHITECTURE_OPTIONS[option_key]
    if option["variant"] is not None:
        row = summary.loc[summary["variant"] == option["variant"]].iloc[0].to_dict()
        return {
            "quality": row["mean_quality"],
            "policy_compliance": row["policy_compliance"],
            "p50_latency_s": row["p50_latency_s"],
            "cost_per_ticket_usd": row["cost_per_ticket_usd"],
            "monthly_cost_at_100k_tickets": row["monthly_cost_at_100k_tickets"],
        }

    # Custom combination: use the routed model/tool strategy, remove sync follow-up work,
    # but do not add the larger cache-friendly prefix. This is useful when cache locality is low.
    routed = summary.loc[summary["variant"] == "02_model_routing"].iloc[0].to_dict()
    split = summary.loc[summary["variant"] == "04_split_workflow"].iloc[0].to_dict()
    cost_per_ticket = (
        max(routed["cost_per_ticket_usd"] - 0.00028, 0)
        + split["background_cost_per_ticket_usd"]
    )
    return {
        "quality": routed["mean_quality"],
        "policy_compliance": routed["policy_compliance"],
        "p50_latency_s": max(routed["p50_latency_s"] - 0.30, 0.5),
        "cost_per_ticket_usd": cost_per_ticket,
        "monthly_cost_at_100k_tickets": cost_per_ticket * 100_000,
    }


OPERATING_SCENARIOS = [
    {
        "scenario": "Early pilot",
        "description": "Low volume, quality learning matters more than unit cost.",
        "quality_floor": 0.94,
        "policy_floor": 0.98,
        "p50_latency_target_s": 3.0,
        "monthly_budget_100k_usd": 800,
        "needs_async": False,
        "cache_locality": "low",
        "recommended": ["controlled_full_model", "routed_no_cache"],
    },
    {
        "scenario": "High-volume routine ecommerce",
        "description": "Many repeated order, return, and damage workflows.",
        "quality_floor": 0.96,
        "policy_floor": 0.99,
        "p50_latency_target_s": 2.0,
        "monthly_budget_100k_usd": 300,
        "needs_async": True,
        "cache_locality": "high",
        "recommended": ["balanced_split", "routed_cache"],
    },
    {
        "scenario": "Premium support",
        "description": "Higher customer value, lower tolerance for wrong actions.",
        "quality_floor": 0.98,
        "policy_floor": 1.0,
        "p50_latency_target_s": 2.5,
        "monthly_budget_100k_usd": 650,
        "needs_async": True,
        "cache_locality": "medium",
        "recommended": [
            "balanced_split",
            "routed_split_no_cache",
            "controlled_full_model",
        ],
    },
    {
        "scenario": "Peak sale burst",
        "description": "Latency and cost matter during temporary traffic spikes.",
        "quality_floor": 0.95,
        "policy_floor": 0.99,
        "p50_latency_target_s": 1.8,
        "monthly_budget_100k_usd": 250,
        "needs_async": True,
        "cache_locality": "high",
        "recommended": ["balanced_split"],
    },
    {
        "scenario": "Low-repeat long tail",
        "description": "Many rare ticket types; cache hit rate is uncertain.",
        "quality_floor": 0.96,
        "policy_floor": 0.99,
        "p50_latency_target_s": 2.5,
        "monthly_budget_100k_usd": 450,
        "needs_async": True,
        "cache_locality": "low",
        "recommended": ["routed_split_no_cache", "routed_no_cache"],
    },
    {
        "scenario": "Account and billing sensitive queue",
        "description": "Risky account recovery and duplicate-charge workflows dominate.",
        "quality_floor": 0.98,
        "policy_floor": 1.0,
        "p50_latency_target_s": 2.8,
        "monthly_budget_100k_usd": 750,
        "needs_async": True,
        "cache_locality": "medium",
        "recommended": [
            "balanced_split",
            "routed_split_no_cache",
            "controlled_full_model",
        ],
    },
]


def scenario_fit_score(
    scenario: dict[str, Any], option_key: str, summary: pd.DataFrame
) -> dict[str, Any]:
    option = ARCHITECTURE_OPTIONS[option_key]
    metrics = architecture_metrics(option_key, summary)

    quality_ok = metrics["quality"] >= scenario["quality_floor"]
    policy_ok = metrics["policy_compliance"] >= scenario["policy_floor"]
    latency_ok = metrics["p50_latency_s"] <= scenario["p50_latency_target_s"]
    budget_ok = (
        metrics["monthly_cost_at_100k_tickets"] <= scenario["monthly_budget_100k_usd"]
    )
    async_ok = (not scenario["needs_async"]) or "async" in option["workflow"]

    cache_penalty = 0
    if scenario["cache_locality"] == "low" and option["cache"] != "none":
        cache_penalty = 3
    elif scenario["cache_locality"] == "medium" and option["cache"] != "none":
        cache_penalty = 1

    score = 0
    score += 3 if quality_ok else -4
    score += 3 if policy_ok else -5
    score += 2 if latency_ok else -2
    score += 2 if budget_ok else -2
    score += 2 if async_ok else -1
    score -= cache_penalty
    if option_key in scenario["recommended"]:
        score += 1

    failed_constraints = []
    if not quality_ok:
        failed_constraints.append("quality")
    if not policy_ok:
        failed_constraints.append("policy")
    if not latency_ok:
        failed_constraints.append("latency")
    if not budget_ok:
        failed_constraints.append("budget")
    if not async_ok:
        failed_constraints.append("async split")
    if cache_penalty:
        failed_constraints.append("cache locality")

    return {
        "scenario": scenario["scenario"],
        "architecture": option_key,
        "label": option["label"],
        "score": score,
        **metrics,
        "failed_constraints": ", ".join(failed_constraints) or "none",
    }
