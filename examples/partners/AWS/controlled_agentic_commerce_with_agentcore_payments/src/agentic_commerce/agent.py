"""One-agent, one-tool supplier research workflow for the Cookbook."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from agents import (
    Agent,
    Model,
    ModelSettings,
    RunConfig,
    Runner,
)
from agents.tracing import set_trace_provider
from agents.tracing.provider import DefaultTraceProvider
from openai.types.shared import Reasoning
from pydantic import BaseModel, ConfigDict

from .application import CommerceApplication
from .errors import AgentResultInvalid
from .models import ApprovalGrant, PurchaseResult
from .tool import build_x402_fetch_tool

DEFAULT_PROMPT = (
    "Purchase the approved synthetic supplier-risk report at "
    "https://merchant.invalid/reports/SYNTH-SUPPLIER-RISK-001 for the "
    "supplier_due_diligence purpose. Use x402_fetch exactly once, then "
    "return only the typed summary supported by the tool result."
)


class SupplierResearchOutput(BaseModel):
    """Typed, non-authoritative summary proposed by the agent."""

    model_config = ConfigDict(frozen=True)

    status: Literal["completed"]
    report_id: Literal["SYNTH-SUPPLIER-RISK-001"]
    supplier: Literal["Northstar Components"]
    signals: tuple[str, ...]
    disclaimer: str
    receipt_id: str
    amount: Literal["0.25"]
    currency: Literal["USDC"]
    requires_human_approval: bool


@dataclass
class PurchaseResultRecorder:
    """Application-owned, per-run record of completed tool purchases."""

    results: list[PurchaseResult] = field(default_factory=list)

    def record(self, result: PurchaseResult) -> None:
        self.results.append(result)


@dataclass(frozen=True)
class SupplierResearchRun:
    """Agent proposal paired with the application evidence that validated it."""

    output: SupplierResearchOutput
    purchase: PurchaseResult


def build_supplier_research_agent(
    application: CommerceApplication,
    *,
    model: str | Model,
    request_id: str,
    idempotency_key: str,
    approval: ApprovalGrant | None,
    recorder: PurchaseResultRecorder,
) -> Agent[None]:
    """Create a fresh Agent whose only economic tool is application-bound."""

    tool = build_x402_fetch_tool(
        application,
        request_id=request_id,
        idempotency_key=idempotency_key,
        approval=approval,
        on_purchase=recorder.record,
    )
    return Agent(
        name="Synthetic supplier research agent",
        model=model,
        model_settings=ModelSettings(
            reasoning=Reasoning(effort="low"),
            store=False,
        ),
        output_type=SupplierResearchOutput,
        tools=[tool],
        instructions=(
            "Use x402_fetch exactly once for the requested paid resource. "
            "The application—not you—owns merchant policy, budgets, human "
            "approval, payment execution, receipts, and audit state. Copy "
            "only facts returned by the tool. Never claim success after a "
            "denial, and never invent a report or receipt."
        ),
    )


def validate_supplier_research_output(
    output: SupplierResearchOutput,
    recorder: PurchaseResultRecorder,
) -> PurchaseResult:
    """Fail closed unless one tool purchase supports every returned field."""

    if len(recorder.results) != 1:
        raise AgentResultInvalid(
            "purchase_count_invalid",
            "A valid agent result requires exactly one completed purchase.",
        )

    purchase = recorder.results[0]
    expected = {
        "status": purchase.status,
        "report_id": purchase.report.report_id,
        "supplier": purchase.report.supplier,
        "signals": purchase.report.signals,
        "disclaimer": purchase.report.disclaimer,
        "receipt_id": purchase.receipt.receipt_id,
        "amount": str(purchase.receipt.amount),
        "currency": purchase.receipt.currency,
        "requires_human_approval": (purchase.authorization.requires_human_approval),
    }
    actual = output.model_dump()
    mismatches = sorted(
        field_name
        for field_name, expected_value in expected.items()
        if actual[field_name] != expected_value
    )
    if mismatches:
        raise AgentResultInvalid(
            "agent_output_mismatch",
            "Agent output did not match application evidence for: "
            + ", ".join(mismatches),
        )
    return purchase


async def run_supplier_research(
    application: CommerceApplication,
    *,
    model: str | Model,
    request_id: str,
    idempotency_key: str,
    approval: ApprovalGrant | None,
    prompt: str = DEFAULT_PROMPT,
) -> SupplierResearchRun:
    """Run the agent and validate its proposal against tool-observed evidence."""

    recorder = PurchaseResultRecorder()
    trace_provider = DefaultTraceProvider()
    trace_provider.set_disabled(True)
    set_trace_provider(trace_provider)
    agent = build_supplier_research_agent(
        application,
        model=model,
        request_id=request_id,
        idempotency_key=idempotency_key,
        approval=approval,
        recorder=recorder,
    )
    result = await Runner.run(
        agent,
        prompt,
        max_turns=4,
        run_config=RunConfig(
            tracing_disabled=True,
            workflow_name="Synthetic Agentic Commerce",
        ),
    )
    output = result.final_output
    if not isinstance(output, SupplierResearchOutput):
        raise AgentResultInvalid(
            "typed_output_missing",
            "The agent did not return the required typed output.",
        )
    purchase = validate_supplier_research_output(output, recorder)
    return SupplierResearchRun(output=output, purchase=purchase)
