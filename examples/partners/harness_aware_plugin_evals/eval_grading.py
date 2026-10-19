def csv_values(value) -> set[str]:
    if isinstance(value, str):
        return {item.strip() for item in value.split(",") if item.strip()}
    return {str(item) for item in value or []}


def grade(calls: list[dict], variables: dict, answer: str, completed: bool) -> dict:
    """Grade one run from tool calls normalized to {"name", "arguments", "result"}."""
    used_tools = {call["name"] for call in calls}
    expected_tools = csv_values(variables.get("expected_tools"))
    missing_tools = sorted(expected_tools - used_tools)

    fetched_series = {
        series_id
        for call in calls
        if call["name"] == "fetch_bls_data"
        for series_id in call["arguments"].get("series_ids", [])
    }
    returned_series = {
        record.get("series_id")
        for call in calls
        if call["name"] == "fetch_bls_data"
        for record in ((call.get("result") or {}).get("data") or [])
        if not record.get("error")
    }
    expected_series = csv_values(variables.get("expected_series_ids"))
    missing_series = sorted(expected_series - returned_series)
    unexpected_series = sorted(fetched_series - expected_series)

    reasons = []
    if not completed:
        reasons.append("run did not finish before the step limit")
    if missing_tools:
        reasons.append(f"missing tools: {missing_tools}")
    if missing_series:
        reasons.append(f"no observations for: {missing_series}")
    if unexpected_series:
        reasons.append(f"fetched series outside the expectation: {unexpected_series}")
    if not answer.strip():
        reasons.append("empty final answer")

    return {
        "pass": not reasons,
        "score": 0.0 if reasons else 1.0,
        "reason": "; ".join(reasons) or "expected tools called and BLS series fetched",
    }
