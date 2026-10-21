"""Agent policies under test.

A policy is any callable ``policy(task) -> list[(tool, args)]``. The harness
does not care whether the plan came from an LLM, a script, or a human — that
is exactly what makes it a reusable eval: swap the policy, keep the tasks,
router, and metrics identical.

Two policies ship here:
- ``oracle_policy``: returns the fixture's expected calls (must score 1.0).
- ``buggy_policy``: drops the final verification call and mistypes one arg
  (must score < 1.0 — proves the harness actually discriminates).
"""
from __future__ import annotations


def oracle_policy(task: dict) -> list[tuple[str, dict]]:
    return [(c["tool"], dict(c["args"])) for c in task["expected_calls"]]


def buggy_policy(task: dict) -> list[tuple[str, dict]]:
    calls = oracle_policy(task)
    if not calls:
        return calls
    mutated = []
    for tool, args in calls[:-1]:  # BUG 1: skip the final verification step
        args = dict(args)
        if tool == "calc" and "expr" in args:
            args["expr"] = "1/0"  # BUG 2: invalid expression for the router
        mutated.append((tool, args))
    return mutated
