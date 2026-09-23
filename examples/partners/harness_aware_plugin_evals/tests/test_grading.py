import pytest

from assert_codex_result import get_assert
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
