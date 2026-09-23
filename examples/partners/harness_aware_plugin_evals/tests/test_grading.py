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
