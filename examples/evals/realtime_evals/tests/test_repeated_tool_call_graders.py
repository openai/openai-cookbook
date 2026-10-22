import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shared.graders import (
    check_tool_args_correct,
    check_tool_call_names_correct,
    compute_tool_call_grade,
)


def test_tool_name_grader_preserves_duplicate_call_count() -> None:
    passed, _ = check_tool_call_names_correct(
        [{"name": "lookup_order"}],
        ["lookup_order", "lookup_order"],
    )

    assert passed is False


def test_tool_name_grader_remains_order_insensitive() -> None:
    passed, reason = check_tool_call_names_correct(
        [
            {"name": "lookup_order"},
            {"name": "send_email"},
            {"name": "lookup_order"},
        ],
        ["send_email", "lookup_order", "lookup_order"],
    )

    assert passed is True
    assert reason == ""


def test_tool_args_grader_checks_later_calls_with_same_name() -> None:
    passed, reason = check_tool_args_correct(
        [
            {"name": "lookup_order", "arguments": {"order_id": "ORD-WRONG"}},
            {"name": "lookup_order", "arguments": {"order_id": "ORD-1001"}},
        ],
        "lookup_order",
        {"order_id": "ORD-1001"},
    )

    assert passed is True
    assert reason == ""


def test_compatibility_grade_reports_matching_repeated_call_arguments() -> None:
    result = compute_tool_call_grade(
        "lookup_order",
        '{"order_id":"ORD-1001"}',
        [
            {"name": "lookup_order", "arguments": {"order_id": "ORD-WRONG"}},
            {"name": "lookup_order", "arguments": {"order_id": "ORD-1001"}},
        ],
    )

    assert result["tool_call_correctness"] == 0
    assert result["tool_call_arg_correctness"] == 1
    assert json.loads(result["pred_tool_call_arg"]) == {"order_id": "ORD-1001"}
