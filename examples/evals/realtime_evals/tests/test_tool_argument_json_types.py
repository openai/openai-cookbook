"""Prevent text normalization from accepting different JSON value types."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.graders import (
    check_tool_args_correct,
    compute_tool_call_grade,
    expected_args_subset,
)


@pytest.mark.parametrize("key", ["value", "new_address", "order_id"])
@pytest.mark.parametrize(
    "expected,actual",
    [
        (None, "None"),
        ("None", None),
        ("synthetic", ["synthetic"]),
        ("", []),
        ("", {}),
        ("{'id': 'synthetic'}", {"id": "synthetic"}),
    ],
)
def test_mismatched_types_are_not_normalized_into_matches(key, expected, actual):
    assert not expected_args_subset({key: expected}, {key: actual})
    passed, reason = check_tool_args_correct(
        [{"name": "synthetic", "arguments": {key: actual}}],
        "synthetic",
        {key: expected},
    )
    assert not passed and reason


@pytest.mark.parametrize(
    "expected,actual", [(None, "None"), ("synthetic", ["synthetic"]), ("", {})]
)
def test_nested_and_list_values_keep_their_types(expected, actual):
    for wrap in [lambda x: {"nested": {"value": x}}, lambda x: {"items": [x]}]:
        assert not expected_args_subset(wrap(expected), wrap(actual))


@pytest.mark.parametrize(
    "expected,actual",
    [
        ({"value": None}, {"value": None, "extra": 1}),
        ({"value": "Hello, WORLD!"}, {"value": "hello world"}),
        ({"order_id": "ORD-123"}, {"order_id": "ord 123"}),
        (
            {"new_address": "12 Harbor St, Seattle, WA"},
            {"new_address": "12 Harbor Street Seattle Washington"},
        ),
        (
            {"items": [None, {"value": "Hello!"}]},
            {"items": [None, {"value": "hello", "extra": 1}, 2]},
        ),
        ({"value": 42}, {"value": "42"}),
        ({"order_id": 42}, {"order_id": "42"}),
        ({"flag": True}, {"flag": True}),
    ],
)
def test_existing_subset_and_text_rules_remain_supported(expected, actual):
    assert expected_args_subset(expected, actual)


def test_missing_null_key_remains_a_mismatch():
    assert not expected_args_subset({"value": None}, {})


def test_compatibility_grade_rejects_null_as_literal_text():
    result = compute_tool_call_grade(
        "synthetic",
        '{"value":null}',
        [{"name": "synthetic", "arguments": {"value": "None"}}],
    )
    assert result["tool_call_correctness"] == 1
    assert result["tool_call_arg_correctness"] == 0
