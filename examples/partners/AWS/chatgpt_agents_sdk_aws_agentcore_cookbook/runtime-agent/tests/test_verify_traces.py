from __future__ import annotations

import json
import os
import socket
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import boto3
import pytest
from botocore.stub import Stubber

import verify_traces
from verify_traces import (
    openai_trace_verification,
    resolve_observability_region,
    verify_aws_trace,
)


@pytest.mark.parametrize(
    ("environment", "profile_region", "expected"),
    [
        ({"AWS_REGION": "us-west-2"}, None, "us-west-2"),
        ({"AWS_DEFAULT_REGION": "us-east-2"}, None, "us-east-2"),
        ({"AWS_REGION": "us-west-2"}, "eu-west-1", "us-west-2"),
        ({}, "eu-west-1", "eu-west-1"),
        (
            {"COOKBOOK_EXECUTION_MODE": "local", "AGENTCORE_RUNTIME_REGION": "us-east-1"},
            "eu-west-1",
            "eu-west-1",
        ),
        (
            {
                "COOKBOOK_EXECUTION_MODE": "deployed",
                "AGENTCORE_RUNTIME_REGION": "us-east-1",
                "AWS_REGION": "us-west-2",
                "AWS_DEFAULT_REGION": "eu-west-1",
            },
            "ap-south-1",
            "us-east-1",
        ),
        (
            {"COOKBOOK_EXECUTION_MODE": "deployed", "AWS_REGION": "us-west-2"},
            "eu-west-1",
            "us-west-2",
        ),
        ({"COOKBOOK_EXECUTION_MODE": "deployed"}, "eu-west-1", "eu-west-1"),
        (
            {
                "FLIGHT_DATA_SOURCE": "agentcore-runtime",
                "AGENTCORE_RUNTIME_REGION": "us-east-1",
            },
            "eu-west-1",
            "us-east-1",
        ),
    ],
)
def test_observability_region_precedence(
    environment: dict[str, str], profile_region: str | None, expected: str
) -> None:
    assert (
        resolve_observability_region(environment=environment, profile_region=profile_region)
        == expected
    )


@pytest.mark.parametrize(
    ("environment", "message"),
    [
        ({}, "AWS Region is missing"),
        (
            {"AWS_REGION": "us-west-2", "AWS_DEFAULT_REGION": "us-east-1"},
            "AWS_REGION and AWS_DEFAULT_REGION must match",
        ),
        ({"COOKBOOK_EXECUTION_MODE": "remote"}, "must be local or deployed"),
        ({"FLIGHT_DATA_SOURCE": "stub"}, "must be local-agent or agentcore-runtime"),
        (
            {"COOKBOOK_EXECUTION_MODE": "local", "FLIGHT_DATA_SOURCE": "agentcore-runtime"},
            "conflicts with legacy FLIGHT_DATA_SOURCE",
        ),
    ],
)
def test_observability_region_rejects_missing_or_conflicting_configuration(
    environment: dict[str, str], message: str
) -> None:
    with pytest.raises(RuntimeError, match=message):
        resolve_observability_region(environment=environment)


@pytest.mark.parametrize(
    ("environment", "profile_region", "expected"),
    [
        ({"AWS_REGION": "us-west-2"}, None, "us-west-2"),
        ({"AWS_REGION": "us-west-2"}, "eu-west-1", "us-west-2"),
        ({}, "eu-west-1", "eu-west-1"),
        (
            {
                "COOKBOOK_EXECUTION_MODE": "deployed",
                "AGENTCORE_RUNTIME_REGION": "us-east-1",
                "AWS_REGION": "us-west-2",
            },
            "eu-west-1",
            "us-east-1",
        ),
    ],
)
def test_verifier_main_creates_a_logs_client_in_the_selected_region(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    environment: dict[str, str],
    profile_region: str | None,
    expected: str,
) -> None:
    # Isolate all AWS configuration; never use the developer's credentials or network.
    for name in list(os.environ):
        if name.startswith(("AWS_", "COOKBOOK_")) or name == "FLIGHT_DATA_SOURCE":
            monkeypatch.delenv(name)
    config = tmp_path / "config"
    config.write_text(
        "[profile cookbook-test]\n" + (f"region = {profile_region}\n" if profile_region else ""),
        encoding="utf-8",
    )
    credentials = tmp_path / "credentials"
    credentials.write_text("", encoding="utf-8")
    for name, value in {
        "AWS_CONFIG_FILE": str(config),
        "AWS_SHARED_CREDENTIALS_FILE": str(credentials),
        "AWS_PROFILE": "cookbook-test",
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_EC2_METADATA_DISABLED": "true",
        **environment,
    }.items():
        monkeypatch.setenv(name, value)

    def reject_network(*_: Any, **__: Any) -> None:
        raise AssertionError("Verifier regression tests must not use the network")

    monkeypatch.setattr(socket.socket, "connect", reject_network)
    monkeypatch.setattr(
        "sys.argv",
        [
            "verify_traces.py",
            "--correlation-id",
            "cookbook-trace-test",
            "--started-at",
            "2026-08-13T00:00:00Z",
        ],
    )
    session_factory = boto3.Session
    stubbers: list[Stubber] = []
    with ExitStack() as stack:

        def isolated_session() -> Any:
            session = session_factory()
            original_client = session.client

            def stubbed_client(service_name: str, **kwargs: Any) -> Any:
                assert service_name == "logs"
                assert kwargs == {"region_name": expected}
                client = original_client(service_name, **kwargs)
                assert client.meta.region_name == expected
                stubber = Stubber(client)
                stubber.add_response("start_query", {"queryId": "query-test"})
                stubber.add_response(
                    "get_query_results",
                    {
                        "status": "Complete",
                        "results": [[{"field": "@message", "value": "cookbook-trace-test"}]],
                    },
                    {"queryId": "query-test"},
                )
                stack.enter_context(stubber)
                stubbers.append(stubber)
                return client

            monkeypatch.setattr(session, "client", stubbed_client)
            return session

        monkeypatch.setattr(verify_traces.boto3, "Session", isolated_session)
        assert verify_traces.main() == 0
        for stubber in stubbers:
            stubber.assert_no_pending_responses()
    report = json.loads(capsys.readouterr().out)
    assert report["region"] == expected
    assert report["destinations"]["aws"]["status"] == "verified"


class FakeLogsClient:
    def __init__(self, responses: list[dict[str, object]]) -> None:
        self.responses = iter(responses)
        self.start_query_arguments: dict[str, object] | None = None

    def start_query(self, **kwargs: object) -> dict[str, object]:
        self.start_query_arguments = kwargs
        return {"queryId": "query-123"}

    def get_query_results(self, **_: object) -> dict[str, object]:
        return next(self.responses)


def test_aws_verifier_reports_independent_ingestion_proof() -> None:
    client = FakeLogsClient([{"status": "Complete", "results": [[{"field": "@message"}]]}])

    result = verify_aws_trace(
        client,
        correlation_id="cookbook-trace-123",
        log_group="aws/spans",
        started_at=datetime(2026, 8, 13, tzinfo=timezone.utc),
        timeout_seconds=60,
        poll_seconds=5,
        monotonic=lambda: 0,
        sleep=lambda _: None,
    )

    assert result.status == "verified"
    assert client.start_query_arguments is not None
    assert client.start_query_arguments["logGroupName"] == "aws/spans"
    assert "cookbook-trace-123" in str(client.start_query_arguments["queryString"])


def test_aws_verifier_does_not_treat_an_empty_completed_query_as_success() -> None:
    client = FakeLogsClient([{"status": "Complete", "results": []}])

    result = verify_aws_trace(
        client,
        correlation_id="cookbook-trace-123",
        log_group="aws/spans",
        started_at=datetime(2026, 8, 13, tzinfo=timezone.utc),
        timeout_seconds=60,
        poll_seconds=5,
        monotonic=lambda: 0,
        sleep=lambda _: None,
    )

    assert result.status == "failed"
    assert "without a matching AWS span" in result.detail


def test_aws_verifier_reports_bounded_delayed_ingestion_without_claiming_success() -> None:
    client = FakeLogsClient([{"status": "Running"}])
    clocks = iter([0.0, 1.0])

    result = verify_aws_trace(
        client,
        correlation_id="cookbook-trace-123",
        log_group="aws/spans",
        started_at=datetime(2026, 8, 13, tzinfo=timezone.utc),
        timeout_seconds=1,
        poll_seconds=1,
        monotonic=lambda: next(clocks),
        sleep=lambda _: None,
    )

    assert result.status == "failed"
    assert "bounded timeout" in result.detail


def test_aws_verifier_reports_missing_read_permission_as_not_checked() -> None:
    class AccessDeniedException(Exception):
        pass

    class DeniedLogsClient(FakeLogsClient):
        def start_query(self, **kwargs: object) -> dict[str, object]:
            raise AccessDeniedException("AccessDenied")

    result = verify_aws_trace(
        DeniedLogsClient([]),
        correlation_id="cookbook-trace-123",
        log_group="aws/spans",
        started_at=datetime(2026, 8, 13, tzinfo=timezone.utc),
        timeout_seconds=60,
        poll_seconds=5,
    )

    assert result.status == "not_checked"
    assert "permission" in result.detail


def test_aws_verifier_rejects_query_injection_in_correlation_id() -> None:
    with pytest.raises(RuntimeError, match="correlation ID"):
        verify_aws_trace(
            FakeLogsClient([]),
            correlation_id="trace/.*|fields @message",
            log_group="aws/spans",
            started_at=datetime(2026, 8, 13, tzinfo=timezone.utc),
            timeout_seconds=60,
            poll_seconds=5,
        )


def test_aws_verifier_escapes_dots_in_correlation_ids() -> None:
    client = FakeLogsClient([{"status": "Complete", "results": []}])

    verify_aws_trace(
        client,
        correlation_id="cookbook.trace-123",
        log_group="aws/spans",
        started_at=datetime(2026, 8, 13, tzinfo=timezone.utc),
        timeout_seconds=60,
        poll_seconds=5,
    )

    assert client.start_query_arguments is not None
    assert "filter @message like /cookbook\\.trace-123/" in str(
        client.start_query_arguments["queryString"]
    )


def test_openai_trace_verification_remains_manual_for_dual_mode() -> None:
    assert openai_trace_verification("aws").status == "not_configured"
    manual = openai_trace_verification("dual")
    assert manual.status == "not_checked"
    assert "Manual OpenAI Traces UI" in manual.detail
