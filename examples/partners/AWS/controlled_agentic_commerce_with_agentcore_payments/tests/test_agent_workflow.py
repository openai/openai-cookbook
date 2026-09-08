from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from agents.tool_context import ToolContext
from agents.usage import Usage

from agentic_commerce.agent import (
    PurchaseResultRecorder,
    SupplierResearchOutput,
    build_supplier_research_agent,
    run_supplier_research,
    validate_supplier_research_output,
)
from agentic_commerce.demo import build_demo
from agentic_commerce.errors import AgentResultInvalid
from agentic_commerce.learning_model import ScriptedCommerceLearningModel
from agentic_commerce.merchant import RESOURCE_URL
from agentic_commerce.models import (
    ApprovalGrant,
    PurchaseRequest,
    PurchaseResult,
)
from agentic_commerce.tool import build_x402_fetch_tool

NOW = datetime(2026, 7, 31, 15, 0, tzinfo=UTC)


def make_approval(now: datetime = NOW) -> ApprovalGrant:
    return ApprovalGrant(
        approval_id="approval-agent-001",
        request_id="request-agent-001",
        resource_url=RESOURCE_URL,
        purpose="supplier_due_diligence",
        maximum_amount=Decimal("0.25"),
        approved_by="synthetic-reviewer",
        approved_at=now,
        expires_at=now + timedelta(minutes=10),
    )


def make_purchase() -> PurchaseResult:
    application, _, _ = build_demo(NOW)
    request = PurchaseRequest(
        request_id="request-agent-001",
        resource_url=RESOURCE_URL,
        purpose="supplier_due_diligence",
        idempotency_key="purchase-agent-001",
    )
    return application.purchase(request, approval=make_approval(), now=NOW)


def output_for(purchase: PurchaseResult) -> SupplierResearchOutput:
    return SupplierResearchOutput(
        status=purchase.status,
        report_id=purchase.report.report_id,
        supplier=purchase.report.supplier,
        signals=purchase.report.signals,
        disclaimer=purchase.report.disclaimer,
        receipt_id=purchase.receipt.receipt_id,
        amount=str(purchase.receipt.amount),
        currency=purchase.receipt.currency,
        requires_human_approval=(purchase.authorization.requires_human_approval),
    )


def test_agent_has_one_bound_tool_typed_output_and_no_storage() -> None:
    application, _, _ = build_demo(NOW)
    recorder = PurchaseResultRecorder()

    agent = build_supplier_research_agent(
        application,
        model="synthetic-model-id",
        request_id="request-agent-001",
        idempotency_key="purchase-agent-001",
        approval=make_approval(),
        recorder=recorder,
    )

    assert [tool.name for tool in agent.tools] == ["x402_fetch"]
    assert agent.output_type is SupplierResearchOutput
    assert agent.model_settings.store is False


def test_application_validation_accepts_exact_tool_evidence() -> None:
    purchase = make_purchase()
    recorder = PurchaseResultRecorder(results=[purchase])

    validated = validate_supplier_research_output(
        output_for(purchase),
        recorder,
    )

    assert validated == purchase


def test_application_validation_rejects_fabricated_receipt() -> None:
    purchase = make_purchase()
    fabricated = output_for(purchase).model_copy(
        update={"receipt_id": "receipt-fabricated"}
    )

    with pytest.raises(AgentResultInvalid) as exc_info:
        validate_supplier_research_output(
            fabricated,
            PurchaseResultRecorder(results=[purchase]),
        )

    assert exc_info.value.code == "agent_output_mismatch"
    assert "receipt_id" in str(exc_info.value)


def test_application_validation_rejects_missing_tool_purchase() -> None:
    purchase = make_purchase()

    with pytest.raises(AgentResultInvalid) as exc_info:
        validate_supplier_research_output(
            output_for(purchase),
            PurchaseResultRecorder(),
        )

    assert exc_info.value.code == "purchase_count_invalid"


def test_tool_returns_minimum_evidence_and_keeps_full_receipt_in_app() -> None:
    now = datetime.now(UTC)
    application, _, _ = build_demo(now)
    recorder = PurchaseResultRecorder()
    tool = build_x402_fetch_tool(
        application,
        request_id="request-agent-001",
        idempotency_key="purchase-agent-001",
        approval=make_approval(now),
        on_purchase=recorder.record,
    )
    arguments = json.dumps(
        {
            "resource_url": RESOURCE_URL,
            "purpose": "supplier_due_diligence",
        }
    )
    context = ToolContext(
        context=None,
        usage=Usage(),
        tool_name="x402_fetch",
        tool_call_id="call-agent-001",
        tool_arguments=arguments,
    )

    raw_result = asyncio.run(tool.on_invoke_tool(context, arguments))
    visible = json.loads(raw_result)

    assert len(recorder.results) == 1
    assert visible["receipt_id"] == recorder.results[0].receipt.receipt_id
    assert "transaction" not in raw_result
    assert "audit_events" not in raw_result
    assert "proof_header" not in raw_result


def test_scripted_model_runs_the_real_agents_sdk_tool_loop() -> None:
    now = datetime.now(UTC)
    application, merchant, payments = build_demo(now)
    model = ScriptedCommerceLearningModel()

    result = asyncio.run(
        run_supplier_research(
            application,
            model=model,
            request_id="request-agent-001",
            idempotency_key="purchase-agent-001",
            approval=make_approval(now),
        )
    )

    assert model.model_turns == 2
    assert model.requested_tools == ["x402_fetch"]
    assert merchant.request_count == 2
    assert payments.charge_count == 1
    assert result.output.receipt_id == result.purchase.receipt.receipt_id
