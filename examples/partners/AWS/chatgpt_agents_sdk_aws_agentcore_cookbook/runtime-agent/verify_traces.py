from __future__ import annotations

import argparse
import json
import os
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Literal, Protocol, cast

import boto3

from endpoint_validation import resolve_aws_region

TraceVerificationStatus = Literal["verified", "failed", "not_configured", "not_checked"]
DEFAULT_LOG_GROUP = "aws/spans"
DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_POLL_SECONDS = 5
CORRELATION_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


class LogsClient(Protocol):
    def start_query(self, **kwargs: Any) -> dict[str, Any]: ...

    def get_query_results(self, **kwargs: Any) -> dict[str, Any]: ...


@dataclass(frozen=True)
class DestinationVerification:
    status: TraceVerificationStatus
    detail: str


def resolve_observability_region(
    *,
    environment: Mapping[str, str] | None = None,
    profile_region: str | None = None,
) -> str:
    """Use the selected route's explicit Region before the AWS profile fallback."""
    values = os.environ if environment is None else environment
    mode = values.get("COOKBOOK_EXECUTION_MODE", "").strip()
    if mode not in {"", "local", "deployed"}:
        raise RuntimeError("COOKBOOK_EXECUTION_MODE must be local or deployed")
    legacy_source = values.get("FLIGHT_DATA_SOURCE", "").strip()
    legacy_mode = {"local-agent": "local", "agentcore-runtime": "deployed"}.get(legacy_source)
    if legacy_source and legacy_mode is None:
        raise RuntimeError("FLIGHT_DATA_SOURCE must be local-agent or agentcore-runtime")
    if mode and legacy_mode and mode != legacy_mode:
        raise RuntimeError("COOKBOOK_EXECUTION_MODE conflicts with legacy FLIGHT_DATA_SOURCE")
    mode = mode or legacy_mode or "local"

    primary = values.get("AWS_REGION", "").strip()
    fallback = values.get("AWS_DEFAULT_REGION", "").strip()
    if mode == "local" and primary and fallback and primary != fallback:
        raise RuntimeError("AWS_REGION and AWS_DEFAULT_REGION must match")
    runtime_region = (
        values.get("AGENTCORE_RUNTIME_REGION", "").strip() if mode == "deployed" else ""
    )
    region = runtime_region or primary or fallback or (profile_region or "").strip()
    if not region:
        raise RuntimeError(
            "AWS Region is missing. Set AWS_REGION (or AGENTCORE_RUNTIME_REGION for "
            "deployed mode) in the repository-root .env, or configure the selected AWS profile."
        )
    return resolve_aws_region(region, None)


def _positive_integer_from_environment(name: str, default: int, maximum: int) -> int:
    raw_value = os.environ.get(name, str(default))
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer from 1 to {maximum}") from exc
    if value < 1 or value > maximum:
        raise RuntimeError(f"{name} must be an integer from 1 to {maximum}")
    return value


def _trace_query(correlation_id: str) -> str:
    if not CORRELATION_ID_PATTERN.fullmatch(correlation_id):
        raise RuntimeError(
            "correlation ID must contain only letters, digits, dot, underscore, or hyphen"
        )
    literal_correlation_id = correlation_id.replace(".", r"\.")
    return "\n".join(
        [
            "fields @timestamp, @message",
            f"| filter @message like /{literal_correlation_id}/",
            "| sort @timestamp desc",
            "| limit 20",
        ]
    )


def _aws_error_status(error: Exception) -> DestinationVerification:
    error_name = error.__class__.__name__
    message = str(error)
    if "AccessDenied" in error_name or "AccessDenied" in message:
        return DestinationVerification(
            "not_checked",
            "AWS query permission was denied; ask the assigned observability verifier "
            "for read access.",
        )
    if "ResourceNotFound" in error_name or "ResourceNotFound" in message:
        return DestinationVerification(
            "not_configured",
            "The configured span log group is not visible in this Region.",
        )
    return DestinationVerification("failed", f"AWS trace query failed: {error_name}")


def verify_aws_trace(
    logs_client: LogsClient,
    *,
    correlation_id: str,
    log_group: str,
    started_at: datetime,
    timeout_seconds: int,
    poll_seconds: int,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> DestinationVerification:
    """Poll a read-only CloudWatch Logs Insights query without treating a flush as proof."""
    query_string = _trace_query(correlation_id)
    try:
        query = logs_client.start_query(
            logGroupName=log_group,
            startTime=int(started_at.timestamp()),
            endTime=int(datetime.now(timezone.utc).timestamp()),
            queryString=query_string,
        )
    except Exception as error:  # boto3 exposes generated exception classes at runtime.
        return _aws_error_status(error)

    query_id = query.get("queryId")
    if not isinstance(query_id, str) or not query_id:
        return DestinationVerification("failed", "AWS did not return a trace-query ID.")

    deadline = monotonic() + timeout_seconds
    while True:
        try:
            result = logs_client.get_query_results(queryId=query_id)
        except Exception as error:  # boto3 exposes generated exception classes at runtime.
            return _aws_error_status(error)
        status = str(result.get("status", "Unknown"))
        if status == "Complete":
            if result.get("results"):
                return DestinationVerification(
                    "verified",
                    "A matching AWS span was found by the read-only CloudWatch query.",
                )
            return DestinationVerification(
                "failed",
                "The query completed without a matching AWS span; retry only after "
                "checking ingestion delay.",
            )
        if status in {"Failed", "Cancelled", "Timeout", "Unknown"}:
            return DestinationVerification(
                "failed", f"AWS trace query ended with status {status}."
            )
        remaining = deadline - monotonic()
        if remaining <= 0:
            return DestinationVerification(
                "failed",
                "AWS trace query did not complete before the bounded timeout; delayed "
                "ingestion remains possible.",
            )
        sleep(min(float(poll_seconds), remaining))


def openai_trace_verification(tracing_mode: str) -> DestinationVerification:
    if tracing_mode == "aws":
        return DestinationVerification(
            "not_configured", "AWS-only mode does not export to OpenAI Traces."
        )
    return DestinationVerification(
        "not_checked",
        "Manual OpenAI Traces UI confirmation by a named verifier is required; no "
        "supported query API is used.",
    )


def _parse_started_at(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RuntimeError("--started-at must be an ISO-8601 timestamp") from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Perform bounded, read-only AWS trace verification for a trace-smoke correlation ID."
        )
    )
    parser.add_argument("--correlation-id", required=True)
    parser.add_argument("--started-at", required=True)
    parser.add_argument("--tracing-mode", choices=("aws", "dual"), default="aws")
    parser.add_argument(
        "--log-group",
        default=os.environ.get("COOKBOOK_TRACE_VERIFICATION_LOG_GROUP", DEFAULT_LOG_GROUP),
    )
    args = parser.parse_args()
    timeout_seconds = _positive_integer_from_environment(
        "COOKBOOK_TRACE_VERIFY_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS, 300
    )
    poll_seconds = _positive_integer_from_environment(
        "COOKBOOK_TRACE_VERIFY_POLL_SECONDS", DEFAULT_POLL_SECONDS, timeout_seconds
    )
    session = boto3.Session()
    try:
        region = resolve_observability_region(profile_region=session.region_name)
    except RuntimeError as error:
        parser.error(str(error))
    aws_result = verify_aws_trace(
        cast(LogsClient, session.client("logs", region_name=region)),
        correlation_id=args.correlation_id,
        log_group=args.log_group,
        started_at=_parse_started_at(args.started_at),
        timeout_seconds=timeout_seconds,
        poll_seconds=poll_seconds,
    )
    report = {
        "correlation_id": args.correlation_id,
        "tracing_mode": args.tracing_mode,
        "region": region,
        "destinations": {
            "aws": asdict(aws_result),
            "openai": asdict(openai_trace_verification(args.tracing_mode)),
        },
    }
    print(json.dumps(report, separators=(",", ":")))
    return 0 if aws_result.status == "verified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
