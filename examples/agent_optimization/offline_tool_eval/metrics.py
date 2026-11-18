"""Metrics: score one trace, then aggregate a suite into a report."""
from __future__ import annotations


def score_trace(trace, expected_calls: list[dict]) -> dict:
    planned = [{"tool": t, "args": a} for t, a in trace.planned]
    exp_tools = [c["tool"] for c in expected_calls]
    got_tools = [c["tool"] for c in planned]
    seq_match = float(planned == expected_calls)

    # Per-call arg match over the overlapping prefix.
    arg_hits, arg_total = 0, 0
    for got, exp in zip(planned, expected_calls):
        if got["tool"] == exp["tool"]:
            for k, v in exp["args"].items():
                arg_total += 1
                if got["args"].get(k) == v:
                    arg_hits += 1
    arg_rate = (arg_hits / arg_total) if arg_total else 1.0

    all_ok = all(c.ok for c in trace.executed) and not trace.truncated
    success = bool(seq_match == 1.0 and all_ok)
    return {
        "task_id": trace.task_id,
        "tool_sequence_match": seq_match,
        "arg_match_rate": round(arg_rate, 3),
        "all_calls_ok": all_ok,
        "truncated": trace.truncated,
        "steps": len(trace.executed),
        "success": success,
    }


def aggregate(scores: list[dict]) -> dict:
    n = len(scores)
    succ = sum(1 for s in scores if s["success"])
    return {
        "tasks": n,
        "passed": succ,
        "pass_rate": round(succ / n, 3) if n else 0.0,
        "mean_arg_match": round(sum(s["arg_match_rate"] for s in scores) / n, 3) if n else 0.0,
        "mean_steps": round(sum(s["steps"] for s in scores) / n, 2) if n else 0.0,
    }


def markdown_report(scores: list[dict], summary: dict) -> str:
    lines = [
        "# Tool-calling eval report",
        "",
        f"Pass rate: **{summary['passed']}/{summary['tasks']} ({summary['pass_rate']})** | "
        f"Mean arg match: {summary['mean_arg_match']} | Mean steps: {summary['mean_steps']}",
        "",
        "| task | seq match | arg match | calls ok | steps | pass |",
        "|---|---|---|---|---|---|",
    ]
    for s in scores:
        lines.append(
            f"| {s['task_id']} | {s['tool_sequence_match']} | {s['arg_match_rate']} | "
            f"{s['all_calls_ok']} | {s['steps']} | {'PASS' if s['success'] else 'FAIL'} |"
        )
    return "\n".join(lines) + "\n"
