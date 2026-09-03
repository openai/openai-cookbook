from __future__ import annotations

import hashlib
import json
import stat
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

import aws_evaluation
from aws_evaluation import (
    DEFAULT_EVALUATORS,
    AwsEvaluationConfig,
    AwsEvaluationError,
    CaseEvaluation,
    RuntimeInvocation,
    assert_evaluation_quality,
    build_redacted_evidence,
    config_from_environment,
    evaluate_invocation,
    invoke_runtime_case,
    load_aws_evaluation_cases,
    run_live_evaluations,
    select_cases,
    write_evidence,
)


def evaluation_config(**overrides: Any) -> AwsEvaluationConfig:
    values: dict[str, Any] = {
        "runtime_arn": (
            "arn:aws:bedrock-agentcore:us-west-2:123456789012:runtime/flight-status-runtime"
        ),
        "region": "us-west-2",
        "log_group_name": ("/aws/bedrock-agentcore/runtimes/flight-status-runtime-DEFAULT"),
        "qualifier": "DEFAULT",
        "case_ids": (),
        "wait_seconds": 0,
        "poll_seconds": 0,
        "attempts": 1,
        "minimum_score": 0.5,
    }
    values.update(overrides)
    return AwsEvaluationConfig(**values)


def successful_results(
    session_id: str = "session-123",
    trace_id: str = "trace-123",
) -> list[dict[str, Any]]:
    return [
        {
            "evaluatorId": evaluator_id,
            "value": 1.0,
            "label": "Pass",
            "context": {
                "spanContext": {
                    "sessionId": session_id,
                    **({"traceId": trace_id} if evaluator_id == "Builtin.Correctness" else {}),
                }
            },
        }
        for evaluator_id in DEFAULT_EVALUATORS
    ]


class ResponseBody:
    def __init__(self, value: dict[str, Any]) -> None:
        self.value = value

    def read(self) -> bytes:
        return json.dumps(self.value).encode("utf-8")


class FakeRuntimeClient:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def invoke_agent_runtime(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {
            "statusCode": 200,
            "runtimeSessionId": kwargs["runtimeSessionId"],
            "response": ResponseBody(self.response),
        }


class FakeEvaluationClient:
    def __init__(self, results: list[list[dict[str, Any]]] | None = None) -> None:
        self.results = iter(results) if results is not None else None
        self.metadata_calls: list[str] = []
        self.run_calls: list[dict[str, Any]] = []

    def get_evaluator(self, **kwargs: Any) -> dict[str, Any]:
        evaluator_id = str(kwargs["evaluatorId"])
        self.metadata_calls.append(evaluator_id)
        return {"level": aws_evaluation.EXPECTED_EVALUATOR_LEVELS[evaluator_id]}

    def run(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.run_calls.append(kwargs)
        if self.results is not None:
            return next(self.results)
        return successful_results(kwargs["session_id"], kwargs["trace_id"])


def uuid_values(*values: int) -> Iterator[UUID]:
    return iter(UUID(int=value) for value in values)


def test_loads_only_tagged_cases_from_shared_promptfoo_fixture() -> None:
    cases = load_aws_evaluation_cases()

    assert [case.case_id for case in cases] == [
        "search-flights",
        "upcoming-status",
        "live-status-on-time",
    ]
    assert {case.request.action for case in cases} == {
        "search_flights",
        "get_upcoming_status",
        "get_live_status",
    }
    assert cases[0].expected_trajectory == ("get_eliza_airlines_flight_options",)
    assert {case.expected_response.executionMode for case in cases} == {"deployed"}


def test_rejects_expected_invalid_case_tagged_for_aws(
    tmp_path: Path,
) -> None:
    fixture = tmp_path / "cases.jsonl"
    fixture.write_text(
        json.dumps(
            {
                "case_id": "invalid-live-case",
                "expected_provider": "agentcore-runtime",
                "expected_execution_mode": "local",
                "expected_action": "get_live_status",
                "expected_contract_valid": False,
                "output": {
                    "provider": "agentcore-runtime",
                    "executionMode": "local",
                    "action": "get_live_status",
                    "data": {"flight": {"flightNumber": "ELZ1628", "status": "ON_TIME"}},
                },
                "aws_evaluation": {
                    "request": {
                        "action": "get_live_status",
                        "flight_number": "ELZ1628",
                    },
                    "assertions": ["The response is correct."],
                    "expected_trajectory": ["get_mock_live_eliza_airlines_status"],
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(AwsEvaluationError, match="expected-invalid"):
        load_aws_evaluation_cases(fixture)


def test_rejects_ground_truth_that_drifted_from_deterministic_runtime(
    tmp_path: Path,
) -> None:
    fixture = tmp_path / "cases.jsonl"
    fixture.write_text(
        json.dumps(
            {
                "case_id": "drifted-live-case",
                "expected_provider": "agentcore-runtime",
                "expected_execution_mode": "local",
                "expected_action": "get_live_status",
                "output": {
                    "provider": "agentcore-runtime",
                    "executionMode": "local",
                    "action": "get_live_status",
                    "data": {
                        "flight": {
                            "flightNumber": "ELZ1628",
                            "origin": "DAL",
                            "destination": "MDW",
                            "travelDate": "2099-09-21",
                            "status": "CANCELLED",
                            "summary": "Stale ground truth.",
                        }
                    },
                },
                "aws_evaluation": {
                    "request": {
                        "action": "get_live_status",
                        "flight_number": "ELZ1628",
                    },
                    "assertions": ["The response is correct."],
                    "expected_trajectory": ["get_mock_live_eliza_airlines_status"],
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(AwsEvaluationError, match="deterministic Runtime response"):
        load_aws_evaluation_cases(fixture)


def test_select_cases_preserves_requested_order_and_rejects_unknown() -> None:
    cases = load_aws_evaluation_cases()

    selected = select_cases(cases, ["live-status-on-time", "search-flights"])

    assert [case.case_id for case in selected] == [
        "live-status-on-time",
        "search-flights",
    ]
    with pytest.raises(AwsEvaluationError, match="Unknown.*missing-case"):
        select_cases(cases, ["missing-case"])


def test_live_config_requires_explicit_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RUN_AWS_EVALUATION", raising=False)

    with pytest.raises(AwsEvaluationError, match="disabled"):
        config_from_environment()


def test_live_config_requires_content_capture_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RUN_AWS_EVALUATION", "1")
    monkeypatch.delenv("AGENTCORE_EVALUATION_CONTENT_CAPTURE_CONFIRMED", raising=False)

    with pytest.raises(AwsEvaluationError, match="dedicated evaluation Runtime"):
        config_from_environment()


def test_live_config_rejects_region_that_differs_from_runtime_arn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RUN_AWS_EVALUATION", "1")
    monkeypatch.setenv("AGENTCORE_EVALUATION_CONTENT_CAPTURE_CONFIRMED", "1")
    monkeypatch.setenv(
        "AGENTCORE_RUNTIME_AGENT_ARN",
        "arn:aws:bedrock-agentcore:us-west-2:123456789012:runtime/example",
    )
    monkeypatch.setenv("AGENTCORE_RUNTIME_REGION", "us-east-1")
    monkeypatch.setenv("AGENTCORE_EVALUATION_LOG_GROUP", "/aws/example")

    with pytest.raises(AwsEvaluationError, match="must match"):
        config_from_environment()


def test_invokes_exact_runtime_with_retained_session_and_safe_payload() -> None:
    case = load_aws_evaluation_cases()[0]
    runtime_client = FakeRuntimeClient(case.expected_response.model_dump())
    identifiers = uuid_values(1, 2, 3)

    invocation = invoke_runtime_case(
        runtime_client,
        evaluation_config(),
        case,
        uuid_factory=lambda: next(identifiers),
    )

    request = runtime_client.calls[0]
    payload = json.loads(request["payload"])
    assert request["agentRuntimeArn"] == evaluation_config().runtime_arn
    assert request["runtimeSessionId"] == invocation.session_id
    assert len(invocation.session_id) >= 33
    assert request["qualifier"] == "DEFAULT"
    assert request["traceParent"] == f"00-{UUID(int=2).hex}-{UUID(int=3).hex[-16:]}-01"
    assert payload == {
        "action": "search_flights",
        "origin": "DAL",
        "destination": "MDW",
        "travel_date": "2099-09-21",
    }
    assert invocation.trace_id == UUID(int=2).hex
    assert invocation.actual_response.executionMode == "deployed"


def test_rejects_runtime_response_with_the_wrong_execution_mode() -> None:
    case = load_aws_evaluation_cases()[0]
    wrong_mode_response = case.expected_response.model_copy(update={"executionMode": "local"})
    runtime_client = FakeRuntimeClient(wrong_mode_response.model_dump())
    identifiers = uuid_values(1, 2, 3)

    with pytest.raises(AwsEvaluationError, match="wrong executionMode"):
        invoke_runtime_case(
            runtime_client,
            evaluation_config(),
            case,
            uuid_factory=lambda: next(identifiers),
        )


def test_runtime_session_id_stays_within_the_agentcore_contract() -> None:
    session_id = aws_evaluation._runtime_session_id(
        "case with spaces-" + ("x" * 200),
        UUID(int=1),
    )

    assert 33 <= len(session_id) <= 100
    assert session_id.startswith("aws-eval-case-with-spaces-")
    assert session_id.endswith(UUID(int=1).hex)
    assert session_id.replace("-", "").isalnum()


def test_live_run_supplies_jsonl_ground_truth_to_each_evaluator() -> None:
    case = load_aws_evaluation_cases()[0]
    runtime_client = FakeRuntimeClient(case.expected_response.model_dump())
    evaluation_client = FakeEvaluationClient()
    sleeps: list[float] = []

    evaluations = run_live_evaluations(
        evaluation_config(wait_seconds=7),
        [case],
        runtime_client=runtime_client,
        evaluation_client=evaluation_client,
        sleep=sleeps.append,
    )

    assert sleeps == [7]
    assert evaluation_client.metadata_calls == list(DEFAULT_EVALUATORS)
    call = evaluation_client.run_calls[0]
    assert call["evaluator_ids"] == list(DEFAULT_EVALUATORS)
    assert call["session_id"] == evaluations[0].invocation.session_id
    assert call["trace_id"] == evaluations[0].invocation.trace_id
    assert call["log_group_name"] == evaluation_config().log_group_name
    reference_inputs = call["reference_inputs"]
    assert json.loads(reference_inputs.expected_response) == case.expected_response.model_dump()
    assert reference_inputs.assertions == list(case.assertions)
    assert reference_inputs.expected_trajectory == list(case.expected_trajectory)


def test_empty_evaluation_results_retry_then_fail_closed() -> None:
    case = load_aws_evaluation_cases()[0]
    invocation = RuntimeInvocation(
        case=case,
        session_id="aws-eval-search-flights-12345678901234567890123456789012",
        trace_id="trace-123",
        actual_response=case.expected_response,
    )
    client = FakeEvaluationClient(results=[[], []])
    sleeps: list[float] = []

    with pytest.raises(AwsEvaluationError, match="no CloudWatch spans"):
        evaluate_invocation(
            client,
            evaluation_config(attempts=2, poll_seconds=3),
            invocation,
            sleep=sleeps.append,
        )

    assert sleeps == [3]
    assert len(client.run_calls) == 2


def test_quality_gate_requires_every_numeric_evaluator_score() -> None:
    case = load_aws_evaluation_cases()[0]
    invocation = RuntimeInvocation(
        case=case,
        session_id="aws-eval-search-flights-12345678901234567890123456789012",
        trace_id="trace-123",
        actual_response=case.expected_response,
    )
    incomplete = CaseEvaluation(
        invocation=invocation,
        results=(
            {
                "evaluatorId": "Builtin.Correctness",
                "value": 0.25,
                "label": "Fail",
            },
        ),
    )

    with pytest.raises(AwsEvaluationError, match="quality gate failed"):
        assert_evaluation_quality([incomplete], DEFAULT_EVALUATORS, 0.5)


@pytest.mark.parametrize(
    ("evaluator_id", "ignored_field"),
    [
        ("Builtin.Correctness", "expectedResponse"),
        ("Builtin.GoalSuccessRate", "assertions"),
        ("Builtin.TrajectoryExactOrderMatch", "expectedTrajectory"),
    ],
)
def test_quality_gate_rejects_ignored_required_ground_truth(
    evaluator_id: str,
    ignored_field: str,
) -> None:
    case = load_aws_evaluation_cases()[0]
    session_id = "aws-eval-search-flights-12345678901234567890123456789012"
    trace_id = "trace-123"
    results = successful_results(session_id, trace_id)
    target = next(result for result in results if result["evaluatorId"] == evaluator_id)
    target["ignoredReferenceInputFields"] = [ignored_field]
    evaluation = CaseEvaluation(
        invocation=RuntimeInvocation(
            case=case,
            session_id=session_id,
            trace_id=trace_id,
            actual_response=case.expected_response,
        ),
        results=tuple(results),
    )

    with pytest.raises(AwsEvaluationError, match="ignored required ground truth"):
        assert_evaluation_quality([evaluation], DEFAULT_EVALUATORS, 0.5)


def test_evidence_hashes_runtime_and_correlation_identifiers(
    tmp_path: Path,
) -> None:
    case = load_aws_evaluation_cases()[0]
    session_id = "aws-eval-search-flights-12345678901234567890123456789012"
    trace_id = "trace-sensitive-123"
    evaluation = CaseEvaluation(
        invocation=RuntimeInvocation(
            case=case,
            session_id=session_id,
            trace_id=trace_id,
            actual_response=case.expected_response,
        ),
        results=tuple(successful_results(session_id, trace_id)),
    )
    config = evaluation_config()
    fixture = tmp_path / "custom-flight-cases.jsonl"
    fixture.write_text('{"case_id":"custom"}\n', encoding="utf-8")

    evidence = build_redacted_evidence(config, [evaluation], fixture_path=fixture)
    rendered = json.dumps(evidence)
    output = write_evidence(evidence, tmp_path / "evidence.json")

    assert config.runtime_arn not in rendered
    assert session_id not in rendered
    assert trace_id not in rendered
    assert evidence["fixture"] == {
        "name": "custom-flight-cases.jsonl",
        "sha256": hashlib.sha256(fixture.read_bytes()).hexdigest(),
    }
    assert evidence["cases"][0]["case_id"] == "search-flights"
    assert evidence["quality_gate_passed"] is True
    assert stat.S_IMODE(output.stat().st_mode) == 0o600


def test_validate_only_does_not_create_aws_clients(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_called(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("validate-only created an AWS client")

    monkeypatch.setattr(aws_evaluation.boto3, "client", fail_if_called)

    assert aws_evaluation.main(["--validate-only"]) == 0


def test_pinned_evaluation_client_exposes_get_evaluator_passthrough(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    client = aws_evaluation.EvaluationClient(region_name="us-west-2")

    assert callable(client.get_evaluator)
