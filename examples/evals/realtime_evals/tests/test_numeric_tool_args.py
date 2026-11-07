"""Offline checks that numeric tool arguments retain signs and magnitudes."""

import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shared.graders import (
    check_tool_args_correct,
    compute_tool_call_grade,
    expected_args_subset,
)


@pytest.mark.parametrize(
    "expected,actual",
    [(-2, "2"), (-0.5, "0.5"), (1e-5, "1e+05"), (1.25, "1 25"), (1.25, "1-25")],
)
@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("nested", [False, True])
def test_numeric_comparisons_do_not_discard_signs_or_punctuation(
    expected, actual, reverse, nested
):
    if reverse:
        expected, actual = actual, expected
    wrap = (
        (lambda value: {"items": [{"amount": value}]})
        if nested
        else (lambda value: {"amount": value})
    )
    assert not expected_args_subset(wrap(expected), wrap(actual))
    passed, reason = check_tool_args_correct(
        [{"name": "synthetic", "arguments": wrap(actual)}], "synthetic", wrap(expected)
    )
    assert not passed and reason


@pytest.mark.parametrize(
    "expected,actual",
    [
        (2, "2"),
        (-2, "-2"),
        (1.25, "1.25"),
        (0, "0"),
        (1, 1.0),
        (1e-5, "1e-05"),
        (1e-5, "0.00001"),
        (1000, "1e3"),
        (9007199254740993, "9007199254740993"),
    ],
)
@pytest.mark.parametrize("reverse", [False, True])
def test_equivalent_numeric_arguments_are_equal(expected, actual, reverse):
    if reverse:
        expected, actual = actual, expected
    assert expected_args_subset(
        {"amount": expected}, {"amount": actual, "extra": "permitted"}
    )


@pytest.mark.parametrize(
    "actual", [True, False, "true", "null", "[2]", "2 units", "02", "", None]
)
def test_non_numeric_values_do_not_satisfy_numeric_arguments(actual):
    assert not expected_args_subset({"amount": 2}, {"amount": actual})


def test_compatibility_grade_rejects_wrong_signed_argument():
    result = compute_tool_call_grade(
        "synthetic",
        '{"amount":-2}',
        [{"name": "synthetic", "arguments": {"amount": "2"}}],
    )
    assert result["tool_call_correctness"] == 1
    assert result["tool_call_arg_correctness"] == 0


def test_text_address_and_identifier_normalization_is_unchanged():
    assert expected_args_subset(
        {
            "label": "HELLO, WORLD!",
            "order_id": "ORD-123",
            "new_address": "12 Harbor St, Seattle, WA",
            "flag": True,
        },
        {
            "label": "hello world",
            "order_id": "ord 123",
            "new_address": "12 Harbor Street Seattle Washington",
            "flag": True,
        },
    )
