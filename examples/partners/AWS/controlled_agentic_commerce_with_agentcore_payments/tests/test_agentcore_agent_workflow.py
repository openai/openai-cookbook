from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
import pytest
from agents.tool_context import ToolContext

from agentic_commerce.agentcore_agent import (
    AgentCoreAccessOutput,
    AgentCoreAccessRecorder,
    build_agentcore_access_agent,
    run_agentcore_access,
    validate_agentcore_access_output,
)
from agentic_commerce.agentcore_application import (
    AgentCoreAuthorizedApplication,
)
from agentic_commerce.agentcore_e2e import (
    _bedrock_profile,
    _blocked_report,
)
from agentic_commerce.agentcore_learning_model import (
    ScriptedAgentCoreLearningModel,
)
from agentic_commerce.agentcore_payments import (
    AgentCorePaymentsSettings,
    AgentCoreX402Client,
    AuthorizationCallback,
)
from agentic_commerce.errors import (
    AgentResultInvalid,
    CommerceError,
    PolicyDenied,
)
from agentic_commerce.models import (
    ApprovalGrant,
    AuditEventType,
    CommercePolicy,
    PurchaseRequest,
)
from agentic_commerce.policy import PolicyEngine

RESOURCE_URL = "https://merchant.example/report"
PURPOSE = "testnet_integration_validation"
ASSET = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"
APPROVED_PAY_TO = "synthetic-testnet-recipient"


def challenge_header() -> str:
    challenge = {
        "x402Version": 2,
        "resource": {
            "url": RESOURCE_URL,
            "description": "Synthetic paid test resource",
            "mimeType": "application/json",
        },
        "accepts": [
            {
                "scheme": "exact",
                "network": "eip155:84532",
                "amount": "2000",
                "asset": ASSET,
                "payTo": APPROVED_PAY_TO,
                "maxTimeoutSeconds": 300,
                "extra": {"name": "USDC", "version": "2"},
            }
        ],
    }
    return base64.b64encode(json.dumps(challenge).encode("utf-8")).decode("ascii")


class FakeManager:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def process_payment(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {
            "status": "PROOF_GENERATED",
            "paymentOutput": {
                "cryptoX402": {
                    "version": "2",
                    "payload": {"signature": "test-proof-not-a-secret"},
                }
            },
        }


class RecordingClientFactory:
    def __init__(self, *, paid_status_code: int = 200) -> None:
        self.requests: list[httpx.Request] = []
        self.paid_status_code = paid_status_code

    def __call__(self) -> httpx.Client:
        def handler(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            if "PAYMENT-SIGNATURE" not in request.headers:
                return httpx.Response(
                    402,
                    headers={"PAYMENT-REQUIRED": challenge_header()},
                    text="payment required",
                )
            return httpx.Response(
                self.paid_status_code,
                headers={"content-type": "application/json"},
                json={"resource": "synthetic-testnet-content"},
            )

        return httpx.Client(transport=httpx.MockTransport(handler))


def build_application(
    now: datetime,
    *,
    clock: Callable[[], datetime] | None = None,
    paid_status_code: int = 200,
    session_expires_at: datetime | None = None,
) -> tuple[AgentCoreAuthorizedApplication, RecordingClientFactory, FakeManager]:
    transport = RecordingClientFactory(paid_status_code=paid_status_code)
    manager = FakeManager()
    settings = AgentCorePaymentsSettings(
        enabled=True,
        aws_region="us-east-1",
        payment_manager_arn="arn:test:manager",
        payment_instrument_id="instrument-test",
        payment_session_id="session-test",
        payment_user_id="user-test",
        allowed_merchants=frozenset({"merchant.example"}),
        approved_asset=ASSET,
        approved_pay_to=APPROVED_PAY_TO,
        max_approved_amount_atomic=2000,
        max_payment_attempts=1,
    )
    policy = PolicyEngine(
        CommercePolicy(
            allowed_merchants=frozenset({"merchant.example"}),
            allowed_purposes=frozenset({PURPOSE}),
            per_request_limit=Decimal("0.002"),
            per_run_limit=Decimal("0.002"),
            approval_threshold=Decimal(0),
            session_expires_at=(session_expires_at or now + timedelta(minutes=10)),
        )
    )

    def build_client(
        authorize_challenge: AuthorizationCallback,
    ) -> AgentCoreX402Client:
        return AgentCoreX402Client(
            settings,
            manager=manager,
            client_factory=transport,
            resolver=lambda _: ["8.8.8.8"],
            authorize_challenge=authorize_challenge,
        )

    return (
        AgentCoreAuthorizedApplication(
            policy=policy,
            client_factory=build_client,
            clock=clock or (lambda: now),
        ),
        transport,
        manager,
    )


def approval(
    now: datetime,
    *,
    expires_at: datetime | None = None,
) -> ApprovalGrant:
    return ApprovalGrant(
        approval_id="approval-agentcore-test-001",
        request_id="request-agentcore-test-001",
        resource_url=RESOURCE_URL,
        purpose=PURPOSE,
        maximum_amount=Decimal("0.002"),
        approved_by="test-reviewer",
        approved_at=now,
        expires_at=expires_at or now + timedelta(minutes=5),
    )


def request() -> PurchaseRequest:
    return PurchaseRequest(
        request_id="request-agentcore-test-001",
        resource_url=RESOURCE_URL,
        purpose=PURPOSE,
        idempotency_key="purchase-agentcore-test-001",
    )


def test_full_agents_sdk_agentcore_join_runs_offline() -> None:
    now = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
    application, transport, manager = build_application(now)
    model = ScriptedAgentCoreLearningModel(
        resource_url=RESOURCE_URL,
        purpose=PURPOSE,
    )

    run = asyncio.run(
        run_agentcore_access(
            application,
            model=model,
            request_id=request().request_id,
            idempotency_key=request().idempotency_key,
            approval=approval(now),
            resource_url=RESOURCE_URL,
            purpose=PURPOSE,
        )
    )

    assert model.model_turns == 2
    assert model.requested_tools == ["x402_fetch"]
    assert len(transport.requests) == 2
    assert len(manager.calls) == 1
    assert run.output.amount == "0.002"
    assert run.output.payment_attempts == 1
    assert run.output.requires_human_approval is True
    assert application.policy.spent == Decimal("0.002")
    assert [event.event_type for event in run.access.audit_events] == [
        AuditEventType.RESOURCE_REQUESTED,
        AuditEventType.PAYMENT_REQUIRED,
        AuditEventType.AUTHORIZATION_CHECKED,
        AuditEventType.PAYMENT_ATTEMPTED,
        AuditEventType.CONTENT_RETURNED,
    ]


def test_combined_agent_uses_verified_bedrock_model_settings() -> None:
    now = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
    application, _, _ = build_application(now)
    recorder = AgentCoreAccessRecorder()
    agent = build_agentcore_access_agent(
        application,
        model=ScriptedAgentCoreLearningModel(
            resource_url=RESOURCE_URL,
            purpose=PURPOSE,
        ),
        request_id=request().request_id,
        idempotency_key=request().idempotency_key,
        approval=approval(now),
        recorder=recorder,
    )

    assert agent.model_settings.store is False
    assert agent.model_settings.reasoning is not None
    assert agent.model_settings.reasoning.effort == "low"


def test_missing_human_approval_stops_before_payment_header() -> None:
    now = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
    application, transport, manager = build_application(now)

    with pytest.raises(PolicyDenied) as exc_info:
        application.access(request(), approval=None, now=now)

    assert exc_info.value.code == "human_approval_required"
    assert len(transport.requests) == 1
    assert manager.calls == []
    assert application.policy.spent == Decimal(0)


def test_non_200_paid_retry_cannot_complete() -> None:
    now = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
    application, transport, manager = build_application(
        now,
        paid_status_code=204,
    )

    with pytest.raises(CommerceError) as exc_info:
        application.access(request(), approval=approval(now), now=now)

    assert exc_info.value.code == "paid_resource_unavailable"
    assert len(transport.requests) == 2
    assert len(manager.calls) == 1


def test_authorization_resamples_time_after_merchant_response() -> None:
    now = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
    moments = iter([now, now + timedelta(seconds=2)])
    application, transport, manager = build_application(
        now,
        clock=lambda: next(moments),
    )

    with pytest.raises(PolicyDenied) as exc_info:
        application.access(
            request(),
            approval=approval(
                now,
                expires_at=now + timedelta(seconds=1),
            ),
        )

    assert exc_info.value.code == "approval_expired"
    assert len(transport.requests) == 1
    assert manager.calls == []
    assert application.policy.spent == Decimal(0)


def test_session_expiry_is_rechecked_after_merchant_response() -> None:
    now = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
    moments = iter([now, now + timedelta(seconds=2)])
    application, transport, manager = build_application(
        now,
        clock=lambda: next(moments),
        session_expires_at=now + timedelta(seconds=1),
    )

    with pytest.raises(PolicyDenied) as exc_info:
        application.access(request(), approval=approval(now))

    assert exc_info.value.code == "session_expired"
    assert len(transport.requests) == 1
    assert manager.calls == []
    assert application.policy.spent == Decimal(0)


def test_preflight_denial_stops_before_adapter_or_network() -> None:
    now = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
    application, transport, manager = build_application(now)
    denied = request().model_copy(update={"purpose": "unapproved"})

    with pytest.raises(PolicyDenied) as exc_info:
        application.access(denied, approval=approval(now), now=now)

    assert exc_info.value.code == "purpose_not_allowed"
    assert transport.requests == []
    assert manager.calls == []


def test_fabricated_agent_transport_evidence_is_rejected() -> None:
    now = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
    application, _, _ = build_application(now)
    access = application.access(request(), approval=approval(now), now=now)
    recorder = AgentCoreAccessRecorder(invocations=1, results=[access])
    fabricated = AgentCoreAccessOutput(
        status="completed",
        merchant=access.merchant,
        status_code=access.status_code,
        amount=str(access.challenge.amount),
        currency=access.challenge.currency,
        network=access.challenge.network,
        payment_attempts=access.payment_attempts,
        response_sha256="0" * 64,
        response_bytes=access.response_bytes,
        requires_human_approval=True,
    )

    with pytest.raises(AgentResultInvalid) as exc_info:
        validate_agentcore_access_output(fabricated, recorder)

    assert exc_info.value.code == "agent_output_mismatch"


def test_missing_completed_tool_access_is_rejected() -> None:
    output = AgentCoreAccessOutput(
        status="completed",
        merchant="merchant.example",
        status_code=200,
        amount="0.002",
        currency="USDC",
        network="eip155:84532",
        payment_attempts=1,
        response_sha256="0" * 64,
        response_bytes=2,
        requires_human_approval=True,
    )

    with pytest.raises(AgentResultInvalid) as exc_info:
        validate_agentcore_access_output(output, AgentCoreAccessRecorder())

    assert exc_info.value.code == "access_count_invalid"


def test_single_tool_failure_is_reported_without_masking_its_code() -> None:
    output = AgentCoreAccessOutput(
        status="completed",
        merchant="merchant.example",
        status_code=200,
        amount="0.002",
        currency="USDC",
        network="eip155:84532",
        payment_attempts=1,
        response_sha256="0" * 64,
        response_bytes=2,
        requires_human_approval=True,
    )
    recorder = AgentCoreAccessRecorder()
    assert recorder.begin_invocation() is True
    recorder.record_failure(
        CommerceError(
            "payment_header_generation_failed",
            "AgentCore Payments could not generate a testnet payment header.",
        )
    )

    with pytest.raises(AgentResultInvalid) as exc_info:
        validate_agentcore_access_output(output, recorder)

    assert exc_info.value.code == "payment_header_generation_failed"


def test_second_tool_invocation_is_blocked_before_side_effects() -> None:
    now = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
    application, transport, manager = build_application(now)
    recorder = AgentCoreAccessRecorder()
    agent = build_agentcore_access_agent(
        application,
        model=ScriptedAgentCoreLearningModel(
            resource_url=RESOURCE_URL,
            purpose=PURPOSE,
        ),
        request_id=request().request_id,
        idempotency_key=request().idempotency_key,
        approval=approval(now),
        recorder=recorder,
    )
    tool = agent.tools[0]
    arguments = json.dumps({"resource_url": RESOURCE_URL, "purpose": PURPOSE})

    first = asyncio.run(
        tool.on_invoke_tool(
            ToolContext(
                context=None,
                tool_name="x402_fetch",
                tool_call_id="call-1",
                tool_arguments=arguments,
            ),
            arguments,
        )
    )
    second = asyncio.run(
        tool.on_invoke_tool(
            ToolContext(
                context=None,
                tool_name="x402_fetch",
                tool_call_id="call-2",
                tool_arguments=arguments,
            ),
            arguments,
        )
    )

    assert json.loads(second)["code"] == "access_count_invalid"
    assert recorder.invocations == 2
    assert len(transport.requests) == 2
    assert len(manager.calls) == 1
    output = AgentCoreAccessOutput.model_validate_json(first)
    with pytest.raises(AgentResultInvalid) as exc_info:
        validate_agentcore_access_output(output, recorder)
    assert exc_info.value.code == "access_count_invalid"


def test_bedrock_profile_is_required_and_separate_configuration() -> None:
    with pytest.raises(CommerceError) as exc_info:
        _bedrock_profile({})

    assert exc_info.value.code == "bedrock_profile_missing"
    assert _bedrock_profile({"BEDROCK_AWS_PROFILE": "model"}) == "model"


def test_unexpected_live_failure_report_does_not_echo_provider_details() -> None:
    report = _blocked_report(RuntimeError("secret-token payment-session-identifier"))
    rendered = json.dumps(report)

    assert report["result"] == "BLOCKED"
    assert report["exception_type"] == "RuntimeError"
    assert report["proof_headers_logged"] is False
    assert report["value_transferred"] == "unknown"
    assert "secret-token" not in rendered
    assert "payment-session-identifier" not in rendered
