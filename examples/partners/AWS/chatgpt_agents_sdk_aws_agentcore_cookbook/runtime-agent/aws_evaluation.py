from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, cast
from uuid import UUID, uuid4

import boto3
from bedrock_agentcore.evaluation import EvaluationClient, ReferenceInputs
from botocore.exceptions import BotoCoreError, ClientError
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from agent import run_deterministic
from demo_date import demo_travel_date, materialize_demo_date
from schemas import RuntimeRequest, RuntimeResponse

FIXTURE_PATH = Path(__file__).parent / "evals" / "fixtures" / "flight-status-results.jsonl"
DEFAULT_RESULT_DIRECTORY = Path(__file__).parent / "evals" / "results"
DEFAULT_EVALUATORS = (
    "Builtin.Correctness",
    "Builtin.GoalSuccessRate",
    "Builtin.TrajectoryExactOrderMatch",
)
EXPECTED_EVALUATOR_LEVELS = {
    "Builtin.Correctness": "TRACE",
    "Builtin.GoalSuccessRate": "SESSION",
    "Builtin.TrajectoryExactOrderMatch": "SESSION",
}
REQUIRED_REFERENCE_FIELD_BY_EVALUATOR = {
    "Builtin.Correctness": "expectedResponse",
    "Builtin.GoalSuccessRate": "assertions",
    "Builtin.TrajectoryExactOrderMatch": "expectedTrajectory",
}
EXPECTED_TOOL_BY_ACTION = {
    "search_flights": "get_eliza_airlines_flight_options",
    "get_upcoming_status": "get_mock_upcoming_eliza_airlines_trip",
    "get_live_status": "get_mock_live_eliza_airlines_status",
}
RUNTIME_ARN_PATTERN = re.compile(
    r"^arn:(?P<partition>aws[a-zA-Z-]*):bedrock-agentcore:"
    r"(?P<region>[^:]+):(?P<account_id>\d{12}):runtime/(?P<runtime_id>[A-Za-z0-9_-]+)$"
)


class AwsEvaluationError(RuntimeError):
    """An expected, safe-to-display AWS evaluation failure."""


class AwsEvaluationMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request: RuntimeRequest
    assertions: list[str] = Field(min_length=1)
    expected_trajectory: list[str] = Field(min_length=1)

    @field_validator("assertions", "expected_trajectory")
    @classmethod
    def require_non_empty_strings(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("items must be non-empty strings")
        return [value.strip() for value in values]


@dataclass(frozen=True)
class AwsEvaluationCase:
    case_id: str
    request: RuntimeRequest
    expected_response: RuntimeResponse
    assertions: tuple[str, ...]
    expected_trajectory: tuple[str, ...]


@dataclass(frozen=True)
class AwsEvaluationConfig:
    runtime_arn: str
    region: str
    log_group_name: str
    qualifier: str | None
    case_ids: tuple[str, ...]
    wait_seconds: int
    poll_seconds: int
    attempts: int
    minimum_score: float
    evaluator_ids: tuple[str, ...] = DEFAULT_EVALUATORS


@dataclass(frozen=True)
class RuntimeInvocation:
    case: AwsEvaluationCase
    session_id: str
    trace_id: str
    actual_response: RuntimeResponse


@dataclass(frozen=True)
class CaseEvaluation:
    invocation: RuntimeInvocation
    results: tuple[dict[str, Any], ...]


class RuntimeClient(Protocol):
    def invoke_agent_runtime(self, **kwargs: Any) -> dict[str, Any]: ...


class AgentCoreEvaluationClient(Protocol):
    def get_evaluator(self, **kwargs: Any) -> dict[str, Any]: ...

    def run(self, **kwargs: Any) -> list[dict[str, Any]]: ...


def load_aws_evaluation_cases(path: Path = FIXTURE_PATH) -> list[AwsEvaluationCase]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise AwsEvaluationError(f"Cannot read evaluation fixture: {path}") from exc

    cases: list[AwsEvaluationCase] = []
    travel_date = demo_travel_date()
    seen_case_ids: set[str] = set()
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        location = f"{path}:{line_number}"
        try:
            record = materialize_demo_date(json.loads(line), travel_date)
        except json.JSONDecodeError as exc:
            raise AwsEvaluationError(f"{location} is not valid JSON") from exc
        if not isinstance(record, dict):
            raise AwsEvaluationError(f"{location} must contain a JSON object")

        case_id = record.get("case_id")
        if not isinstance(case_id, str) or not case_id.strip():
            raise AwsEvaluationError(f"{location} is missing a non-empty case_id")
        case_id = case_id.strip()
        if case_id in seen_case_ids:
            raise AwsEvaluationError(f"{location} duplicates case_id {case_id!r}")
        seen_case_ids.add(case_id)

        aws_metadata = record.get("aws_evaluation")
        if aws_metadata is None:
            continue
        if record.get("expected_contract_valid", True) is not True:
            raise AwsEvaluationError(
                f"{location} cannot mark an expected-invalid contract for AWS evaluation"
            )
        if record.get("expected_provider") != "agentcore-runtime":
            raise AwsEvaluationError(
                f"{location} AWS evaluation requires expected_provider agentcore-runtime"
            )
        if record.get("expected_execution_mode") != "local":
            raise AwsEvaluationError(
                f"{location} AWS evaluation requires expected_execution_mode local"
            )

        try:
            metadata = AwsEvaluationMetadata.model_validate(aws_metadata)
            canonical_local_response = RuntimeResponse.model_validate(record.get("output"))
        except ValidationError as exc:
            raise AwsEvaluationError(
                f"{location} has invalid AWS evaluation ground truth: {exc}"
            ) from exc

        expected_action = record.get("expected_action")
        if expected_action != metadata.request.action:
            raise AwsEvaluationError(
                f"{location} expected_action must match aws_evaluation.request.action"
            )
        if canonical_local_response.action != metadata.request.action:
            raise AwsEvaluationError(
                f"{location} output.action must match aws_evaluation.request.action"
            )
        if canonical_local_response != run_deterministic(
            metadata.request,
            execution_mode="local",
        ):
            raise AwsEvaluationError(
                f"{location} output must match the current deterministic Runtime response"
            )
        expected_response = run_deterministic(
            metadata.request,
            execution_mode="deployed",
        )

        expected_tool = EXPECTED_TOOL_BY_ACTION[metadata.request.action]
        if metadata.expected_trajectory != [expected_tool]:
            raise AwsEvaluationError(
                f"{location} expected_trajectory must be exactly [{expected_tool!r}]"
            )

        cases.append(
            AwsEvaluationCase(
                case_id=case_id,
                request=metadata.request,
                expected_response=expected_response,
                assertions=tuple(metadata.assertions),
                expected_trajectory=tuple(metadata.expected_trajectory),
            )
        )

    if not cases:
        raise AwsEvaluationError(f"{path} contains no aws_evaluation cases")
    return cases


def select_cases(
    cases: Sequence[AwsEvaluationCase], requested_case_ids: Sequence[str]
) -> list[AwsEvaluationCase]:
    if not requested_case_ids:
        return list(cases)

    requested = list(dict.fromkeys(requested_case_ids))
    by_id = {case.case_id: case for case in cases}
    unknown = [case_id for case_id in requested if case_id not in by_id]
    if unknown:
        raise AwsEvaluationError(f"Unknown AWS evaluation case IDs: {', '.join(unknown)}")
    return [by_id[case_id] for case_id in requested]


def _environment_flag(name: str) -> bool:
    value = os.environ.get(name, "").strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"", "0", "false", "no", "off"}:
        return False
    raise AwsEvaluationError(f"{name} must be a boolean value such as 1 or 0")


def _integer_environment(name: str, default: int, *, minimum: int) -> int:
    raw_value = os.environ.get(name, "").strip()
    try:
        value = int(raw_value) if raw_value else default
    except ValueError as exc:
        raise AwsEvaluationError(f"{name} must be an integer") from exc
    if value < minimum:
        raise AwsEvaluationError(f"{name} must be at least {minimum}")
    return value


def _score_environment(name: str, default: float) -> float:
    raw_value = os.environ.get(name, "").strip()
    try:
        value = float(raw_value) if raw_value else default
    except ValueError as exc:
        raise AwsEvaluationError(f"{name} must be a number from 0 through 1") from exc
    if not 0 <= value <= 1:
        raise AwsEvaluationError(f"{name} must be a number from 0 through 1")
    return value


def config_from_environment() -> AwsEvaluationConfig:
    if not _environment_flag("RUN_AWS_EVALUATION"):
        raise AwsEvaluationError(
            "Live AWS evaluation is disabled. Run `npm run eval:aws:validate` first, "
            "then set RUN_AWS_EVALUATION=1 for the credentialed run."
        )
    if not _environment_flag("AGENTCORE_EVALUATION_CONTENT_CAPTURE_CONFIRMED"):
        raise AwsEvaluationError(
            "AGENTCORE_EVALUATION_CONTENT_CAPTURE_CONFIRMED=1 is required. "
            "Use only a dedicated evaluation Runtime configured with "
            "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true after the "
            "Runtime owner approves trace-content handling."
        )

    runtime_arn = os.environ.get("AGENTCORE_RUNTIME_AGENT_ARN", "").strip()
    log_group_name = os.environ.get("AGENTCORE_EVALUATION_LOG_GROUP", "").strip()
    if not runtime_arn:
        raise AwsEvaluationError("AGENTCORE_RUNTIME_AGENT_ARN is required")
    if not log_group_name:
        raise AwsEvaluationError("AGENTCORE_EVALUATION_LOG_GROUP is required")

    arn_match = RUNTIME_ARN_PATTERN.fullmatch(runtime_arn)
    if arn_match is None:
        raise AwsEvaluationError(
            "AGENTCORE_RUNTIME_AGENT_ARN must be an exact AgentCore Runtime ARN"
        )

    region = (
        os.environ.get("AGENTCORE_RUNTIME_REGION", "").strip()
        or os.environ.get("AWS_REGION", "").strip()
        or arn_match.group("region")
    )
    if region != arn_match.group("region"):
        raise AwsEvaluationError(
            "AGENTCORE_RUNTIME_REGION must match the Region in AGENTCORE_RUNTIME_AGENT_ARN"
        )

    case_ids = tuple(
        value.strip()
        for value in os.environ.get("AGENTCORE_EVALUATION_CASE_IDS", "").split(",")
        if value.strip()
    )
    qualifier = os.environ.get("AGENTCORE_RUNTIME_QUALIFIER", "").strip() or None
    return AwsEvaluationConfig(
        runtime_arn=runtime_arn,
        region=region,
        log_group_name=log_group_name,
        qualifier=qualifier,
        case_ids=case_ids,
        wait_seconds=_integer_environment("AGENTCORE_EVALUATION_WAIT_SECONDS", 180, minimum=0),
        poll_seconds=_integer_environment("AGENTCORE_EVALUATION_POLL_SECONDS", 30, minimum=0),
        attempts=_integer_environment("AGENTCORE_EVALUATION_ATTEMPTS", 5, minimum=1),
        minimum_score=_score_environment("AGENTCORE_EVALUATION_MIN_SCORE", 0.5),
    )


def preflight_evaluators(client: AgentCoreEvaluationClient, evaluator_ids: Sequence[str]) -> None:
    for evaluator_id in evaluator_ids:
        try:
            response = client.get_evaluator(evaluatorId=evaluator_id)
        except Exception as exc:
            raise AwsEvaluationError(
                f"Cannot read evaluator metadata for {evaluator_id}; "
                "ask the AWS administrator for bedrock-agentcore:GetEvaluator"
            ) from exc
        expected_level = EXPECTED_EVALUATOR_LEVELS[evaluator_id]
        actual_level = response.get("level")
        if actual_level != expected_level:
            raise AwsEvaluationError(
                f"{evaluator_id} reported level {actual_level!r}; expected {expected_level}"
            )


def _runtime_session_id(case_id: str, unique_id: UUID) -> str:
    safe_case_id = re.sub(r"[^A-Za-z0-9-]", "-", case_id).strip("-") or "case"
    return f"aws-eval-{safe_case_id[:58]}-{unique_id.hex}"


def _w3c_trace_parent(
    trace_unique_id: UUID,
    parent_unique_id: UUID,
) -> tuple[str, str]:
    trace_id = trace_unique_id.hex
    parent_span_id = parent_unique_id.hex[-16:]
    if trace_id == "0" * 32 or parent_span_id == "0" * 16:
        raise AwsEvaluationError("Generated trace identifiers must not be all zeroes")
    return trace_id, f"00-{trace_id}-{parent_span_id}-01"


def _read_runtime_body(body: object) -> object:
    reader = getattr(body, "read", None)
    if callable(reader):
        body = reader()
    if isinstance(body, bytes):
        try:
            body = body.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise AwsEvaluationError("AgentCore Runtime response was not UTF-8") from exc
    if not isinstance(body, str):
        raise AwsEvaluationError("AgentCore Runtime returned an unreadable response body")
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise AwsEvaluationError("AgentCore Runtime returned invalid JSON") from exc


def invoke_runtime_case(
    client: RuntimeClient,
    config: AwsEvaluationConfig,
    case: AwsEvaluationCase,
    *,
    uuid_factory: Callable[[], UUID] = uuid4,
) -> RuntimeInvocation:
    session_id = _runtime_session_id(case.case_id, uuid_factory())
    trace_id, trace_parent = _w3c_trace_parent(uuid_factory(), uuid_factory())
    request: dict[str, Any] = {
        "agentRuntimeArn": config.runtime_arn,
        "contentType": "application/json",
        "accept": "application/json",
        "runtimeSessionId": session_id,
        "traceParent": trace_parent,
        "payload": json.dumps(
            case.request.model_dump(exclude_none=True),
            separators=(",", ":"),
        ).encode("utf-8"),
    }
    if config.qualifier:
        request["qualifier"] = config.qualifier

    response = client.invoke_agent_runtime(**request)
    status_code = response.get("statusCode")
    if isinstance(status_code, int) and not 200 <= status_code < 300:
        raise AwsEvaluationError(f"{case.case_id}: AgentCore Runtime returned HTTP {status_code}")
    returned_session_id = response.get("runtimeSessionId")
    if returned_session_id is not None and returned_session_id != session_id:
        raise AwsEvaluationError(
            f"{case.case_id}: AgentCore Runtime returned a different session ID"
        )
    if "response" not in response:
        raise AwsEvaluationError(f"{case.case_id}: AgentCore Runtime returned no response body")

    parsed_body = _read_runtime_body(response["response"])
    try:
        actual_response = RuntimeResponse.model_validate(parsed_body)
    except ValidationError as exc:
        raise AwsEvaluationError(
            f"{case.case_id}: AgentCore Runtime response failed the cookbook contract"
        ) from exc
    if actual_response.action != case.request.action:
        raise AwsEvaluationError(f"{case.case_id}: AgentCore Runtime returned the wrong action")
    if actual_response.executionMode != "deployed":
        raise AwsEvaluationError(
            f"{case.case_id}: AgentCore Runtime returned the wrong executionMode"
        )
    return RuntimeInvocation(
        case=case,
        session_id=session_id,
        trace_id=trace_id,
        actual_response=actual_response,
    )


def _expected_response_text(case: AwsEvaluationCase) -> str:
    return json.dumps(
        case.expected_response.model_dump(),
        separators=(",", ":"),
        sort_keys=True,
    )


def evaluate_invocation(
    client: AgentCoreEvaluationClient,
    config: AwsEvaluationConfig,
    invocation: RuntimeInvocation,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> CaseEvaluation:
    reference_inputs = ReferenceInputs(
        expected_response=_expected_response_text(invocation.case),
        assertions=list(invocation.case.assertions),
        expected_trajectory=list(invocation.case.expected_trajectory),
    )
    results: list[dict[str, Any]] = []
    for attempt in range(config.attempts):
        results = client.run(
            evaluator_ids=list(config.evaluator_ids),
            session_id=invocation.session_id,
            log_group_name=config.log_group_name,
            trace_id=invocation.trace_id,
            reference_inputs=reference_inputs,
        )
        if results:
            break
        if attempt + 1 < config.attempts:
            sleep(config.poll_seconds)

    if not results:
        raise AwsEvaluationError(
            f"{invocation.case.case_id}: no CloudWatch spans or evaluation results "
            f"were found after {config.attempts} attempts"
        )
    return CaseEvaluation(invocation=invocation, results=tuple(results))


def run_live_evaluations(
    config: AwsEvaluationConfig,
    cases: Sequence[AwsEvaluationCase],
    *,
    runtime_client: RuntimeClient | None = None,
    evaluation_client: AgentCoreEvaluationClient | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> list[CaseEvaluation]:
    if runtime_client is None:
        runtime_client = cast(
            RuntimeClient,
            boto3.client("bedrock-agentcore", region_name=config.region),
        )
    if evaluation_client is None:
        evaluation_client = cast(
            AgentCoreEvaluationClient,
            EvaluationClient(
                region_name=config.region,
                integration_source="openai-agents-sdk-cookbook",
            ),
        )

    preflight_evaluators(evaluation_client, config.evaluator_ids)
    invocations = [
        invoke_runtime_case(runtime_client, config, evaluation_case) for evaluation_case in cases
    ]
    if config.wait_seconds:
        sleep(config.wait_seconds)
    return [
        evaluate_invocation(evaluation_client, config, invocation, sleep=sleep)
        for invocation in invocations
    ]


def assert_evaluation_quality(
    evaluations: Sequence[CaseEvaluation],
    evaluator_ids: Sequence[str],
    minimum_score: float,
) -> None:
    failures: list[str] = []
    for case_evaluation in evaluations:
        case_id = case_evaluation.invocation.case.case_id
        by_evaluator: dict[str, list[dict[str, Any]]] = {}
        for result in case_evaluation.results:
            evaluator_id = result.get("evaluatorId")
            if isinstance(evaluator_id, str):
                by_evaluator.setdefault(evaluator_id, []).append(result)
            if result.get("errorCode") or result.get("errorMessage"):
                failures.append(f"{case_id}: an evaluator returned an error")

        for evaluator_id in evaluator_ids:
            evaluator_results = by_evaluator.get(evaluator_id, [])
            if not evaluator_results:
                failures.append(f"{case_id}: missing result for {evaluator_id}")
                continue
            for result in evaluator_results:
                value = result.get("value")
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    failures.append(f"{case_id}: {evaluator_id} returned no numeric score")
                elif float(value) < minimum_score:
                    failures.append(
                        f"{case_id}: {evaluator_id} score {value} is below {minimum_score}"
                    )

                context = result.get("context")
                span_context = context.get("spanContext") if isinstance(context, dict) else None
                if not isinstance(span_context, dict):
                    failures.append(f"{case_id}: {evaluator_id} returned no span context")
                    continue
                if span_context.get("sessionId") != case_evaluation.invocation.session_id:
                    failures.append(
                        f"{case_id}: {evaluator_id} returned the wrong session correlation"
                    )
                if (
                    evaluator_id == "Builtin.Correctness"
                    and span_context.get("traceId") != case_evaluation.invocation.trace_id
                ):
                    failures.append(
                        f"{case_id}: {evaluator_id} returned the wrong trace correlation"
                    )

                ignored_fields = result.get("ignoredReferenceInputFields", [])
                required_field = REQUIRED_REFERENCE_FIELD_BY_EVALUATOR[evaluator_id]
                if not isinstance(ignored_fields, list):
                    failures.append(
                        f"{case_id}: {evaluator_id} returned invalid ignored-field metadata"
                    )
                elif required_field in ignored_fields:
                    failures.append(
                        f"{case_id}: {evaluator_id} ignored required ground truth {required_field}"
                    )

    if failures:
        raise AwsEvaluationError("AWS evaluation quality gate failed: " + "; ".join(failures))


def _redacted_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_redacted_evidence(
    config: AwsEvaluationConfig,
    evaluations: Sequence[CaseEvaluation],
    *,
    generated_at: datetime | None = None,
    fixture_path: Path = FIXTURE_PATH,
) -> dict[str, Any]:
    timestamp = generated_at or datetime.now(timezone.utc)
    try:
        fixture_sha256 = hashlib.sha256(fixture_path.read_bytes()).hexdigest()
    except OSError as exc:
        raise AwsEvaluationError(f"Cannot read evidence fixture: {fixture_path}") from exc
    try:
        assert_evaluation_quality(
            evaluations,
            config.evaluator_ids,
            config.minimum_score,
        )
        quality_gate_passed = True
    except AwsEvaluationError:
        quality_gate_passed = False
    return {
        "schema_version": 1,
        "generated_at": timestamp.isoformat(),
        "fixture": {
            "name": fixture_path.name,
            "sha256": fixture_sha256,
        },
        "region": config.region,
        "runtime_arn_sha256": _redacted_hash(config.runtime_arn),
        "minimum_score": config.minimum_score,
        "quality_gate_passed": quality_gate_passed,
        "evaluators": list(config.evaluator_ids),
        "cases": [
            {
                "case_id": case_evaluation.invocation.case.case_id,
                "runtime_session_id_sha256": _redacted_hash(case_evaluation.invocation.session_id),
                "trace_id_sha256": _redacted_hash(case_evaluation.invocation.trace_id),
                "results": [
                    {
                        "evaluator_id": result.get("evaluatorId"),
                        "value": result.get("value"),
                        "label": result.get("label"),
                        "ignored_reference_input_fields": result.get(
                            "ignoredReferenceInputFields", []
                        ),
                        "error_code": result.get("errorCode"),
                    }
                    for result in case_evaluation.results
                ],
            }
            for case_evaluation in evaluations
        ],
    }


def write_evidence(
    evidence: dict[str, Any],
    output_path: Path | None = None,
    *,
    generated_at: datetime | None = None,
) -> Path:
    timestamp = generated_at or datetime.now(timezone.utc)
    path = output_path or (
        DEFAULT_RESULT_DIRECTORY / f"aws-evaluation-{timestamp.strftime('%Y%m%dT%H%M%SZ')}.json"
    )
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise AwsEvaluationError(f"Cannot create evidence directory: {path.parent}") from exc
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError as exc:
        raise AwsEvaluationError(f"Refusing to overwrite existing evidence file: {path}") from exc
    except OSError as exc:
        raise AwsEvaluationError(f"Cannot create evidence file: {path}") from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(evidence, output, indent=2, sort_keys=True)
            output.write("\n")
    except OSError as exc:
        raise AwsEvaluationError(f"Cannot write evidence file: {path}") from exc
    return path


def _print_summary(evaluations: Sequence[CaseEvaluation]) -> None:
    for case_evaluation in evaluations:
        case_id = case_evaluation.invocation.case.case_id
        for result in case_evaluation.results:
            evaluator_id = result.get("evaluatorId", "unknown evaluator")
            value = result.get("value", "no score")
            label = result.get("label", "no label")
            print(f"{case_id}: {evaluator_id} = {value} ({label})")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate or run the opt-in AWS AgentCore evaluation cases embedded "
            "in the shared Promptfoo flight JSONL fixture."
        )
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="validate and list AWS-tagged fixture cases without creating AWS clients",
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=FIXTURE_PATH,
        help="path to the shared flight JSONL fixture",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="write redacted live evidence to this new file",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        cases = load_aws_evaluation_cases(args.fixture)
        if args.validate_only:
            actions = sorted({case.request.action for case in cases})
            print(
                f"Validated {len(cases)} AWS evaluation cases from {args.fixture}: "
                f"{', '.join(case.case_id for case in cases)}"
            )
            print(f"Covered actions: {', '.join(actions)}")
            return 0

        config = config_from_environment()
        selected_cases = select_cases(cases, config.case_ids)
        evaluations = run_live_evaluations(config, selected_cases)
        generated_at = datetime.now(timezone.utc)
        evidence = build_redacted_evidence(
            config,
            evaluations,
            generated_at=generated_at,
            fixture_path=args.fixture,
        )
        evidence_path = write_evidence(
            evidence,
            args.output,
            generated_at=generated_at,
        )
        _print_summary(evaluations)
        print(f"Redacted evidence: {evidence_path}")
        assert_evaluation_quality(
            evaluations,
            config.evaluator_ids,
            config.minimum_score,
        )
        print("AWS AgentCore evaluation passed.")
        return 0
    except AwsEvaluationError as exc:
        print(f"AWS evaluation failed: {exc}", file=sys.stderr)
        return 1
    except ClientError as exc:
        code = str(exc.response.get("Error", {}).get("Code", "ClientError"))
        print(
            f"AWS evaluation failed: AWS returned {code}. "
            "Check the evaluator role and Runtime configuration.",
            file=sys.stderr,
        )
        return 1
    except BotoCoreError:
        print(
            "AWS evaluation failed: AWS credentials or connectivity are unavailable.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
