import json

import pytest

from assert_codex_result import get_assert
from assert_result import get_assert as get_standalone_assert
from eval_grading import grade

VARIABLES = {
    "expected_tools": "resolve,fetch_bls_data",
    "expected_series_ids": "LNS14000000",
}

ANSWER = "The U.S. unemployment rate is 4.1 percent."


def calls(result: dict) -> list[dict]:
    return [
        {"name": "resolve", "arguments": {"indicator": "unemployment rate"}, "result": {}},
        {"name": "fetch_bls_data", "arguments": {"series_ids": ["LNS14000000"]}, "result": result},
    ]


def test_a_fetch_that_returned_observations_passes():
    observations = {"data": [{"series_id": "LNS14000000", "data": [{"value": "4.1"}]}]}

    assert grade(calls(observations), VARIABLES, ANSWER, True)["pass"]


def test_a_fetch_that_returned_a_series_error_fails():
    server_error = {"data": [{"series_id": "LNS14000000", "error": "unknown series"}]}

    verdict = grade(calls(server_error), VARIABLES, ANSWER, True)

    assert not verdict["pass"]
    assert "LNS14000000" in verdict["reason"]


@pytest.mark.parametrize(
    "series_record",
    [
        {"series_id": "LNS14000000"},
        {"series_id": "LNS14000000", "data": None},
        {"series_id": "LNS14000000", "data": []},
    ],
)
@pytest.mark.parametrize("harness", ["standalone", "codex"])
def test_a_fetch_without_observations_fails(series_record, harness):
    tool_calls = calls({"data": [series_record]})
    if harness == "standalone":
        output = json.dumps(
            {"tool_calls": tool_calls, "answer": ANSWER, "completed": True}
        )
        verdict = get_standalone_assert(output, {"vars": VARIABLES})
    else:
        context = {
            "vars": VARIABLES,
            "providerResponse": {
                "raw": {
                    "items": [
                        {
                            "type": "mcp_tool_call",
                            "tool": call["name"],
                            "arguments": call["arguments"],
                            "result": {"structured_content": call["result"]},
                            "status": "completed",
                        }
                        for call in tool_calls
                    ],
                    "finalResponse": ANSWER,
                }
            },
        }
        verdict = get_assert(ANSWER, context)

    assert not verdict["pass"]
    assert verdict["score"] == 0.0
    assert "no observations for: ['LNS14000000']" in verdict["reason"]


def test_every_expected_series_must_return_observations():
    variables = {**VARIABLES, "expected_series_ids": "LNS14000000,LNS12000000"}
    tool_calls = calls(
        {
            "data": [
                {"series_id": "LNS14000000", "data": [{"value": "4.1"}]},
                {"series_id": "LNS12000000", "data": []},
            ]
        }
    )
    tool_calls[1]["arguments"]["series_ids"].append("LNS12000000")

    verdict = grade(tool_calls, variables, ANSWER, True)

    assert not verdict["pass"]
    assert verdict["score"] == 0.0
    assert "no observations for: ['LNS12000000']" in verdict["reason"]


def test_observations_with_zero_values_pass():
    observations = {
        "data": [{"series_id": "LNS14000000", "data": [{"value": "0"}]}]
    }

    assert grade(calls(observations), VARIABLES, ANSWER, True)["pass"]


def test_a_later_fetch_with_observations_satisfies_the_expected_series():
    tool_calls = calls({"data": [{"series_id": "LNS14000000", "data": []}]})
    tool_calls += calls(
        {"data": [{"series_id": "LNS14000000", "data": [{"value": "4.1"}]}]}
    )

    assert grade(tool_calls, VARIABLES, ANSWER, True)["pass"]


@pytest.mark.parametrize(
    "tool_outcome, passes",
    [
        ({"status": "failed"}, False),
        ({"error": {"message": "MCP connection failed"}}, False),
        ({"status": "completed"}, True),
    ],
)
def test_codex_resolve_must_succeed_even_when_no_series_are_expected(tool_outcome, passes):
    answer = "Sorry, I cannot provide that data."
    context = {
        "vars": {"expected_tools": "resolve", "expected_series_ids": ""},
        "providerResponse": {
            "raw": {
                "items": [{"type": "mcp_tool_call", "tool": "resolve", **tool_outcome}],
                "finalResponse": answer,
            }
        },
    }

    verdict = get_assert(answer, context)

    assert verdict["pass"] is passes
    assert verdict["score"] == float(passes)
    if not passes:
        assert "MCP tool call failed: resolve" in verdict["reason"]
