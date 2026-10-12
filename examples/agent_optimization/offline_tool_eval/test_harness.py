"""Harness self-tests: the eval must pass the oracle and fail the buggy policy.

These are meta-tests — they test the *evaluator*, not an agent. If someone
breaks scoring, these go red before any agent result can be trusted.
"""
from harness.metrics import aggregate, markdown_report, score_trace
from harness.policies import buggy_policy, oracle_policy
from harness.runner import run_suite
from harness.tasks import TASKS
from harness.tools import ToolCall, ToolRouter, default_router


def _scores(policy):
    traces = run_suite(policy, TASKS, default_router)
    by_id = {t["id"]: t for t in TASKS}
    return [score_trace(tr, by_id[tr.task_id]["expected_calls"]) for tr in traces]


def test_oracle_policy_scores_perfect():
    scores = _scores(oracle_policy)
    assert all(s["success"] for s in scores)
    summary = aggregate(scores)
    assert summary["pass_rate"] == 1.0
    assert summary["passed"] == len(TASKS)


def test_buggy_policy_is_caught():
    scores = _scores(buggy_policy)
    assert not all(s["success"] for s in scores)
    assert aggregate(scores)["pass_rate"] < 1.0


def test_unknown_tool_marks_call_failed():
    router = default_router()
    call = router.dispatch("no_such_tool", {})
    assert call.ok is False
    assert "unknown tool" in call.output


def test_step_guard_truncates_long_plans():
    def chatty(task):
        return [("calc", {"expr": "1+1"})] * 20

    traces = run_suite(chatty, TASKS[:1], default_router, max_steps=3)
    assert traces[0].truncated is True
    assert len(traces[0].executed) == 3


def test_report_renders_results_table():
    scores = _scores(oracle_policy)
    report = markdown_report(scores, aggregate(scores))
    assert "Pass rate" in report
    for t in TASKS:
        assert t["id"] in report
