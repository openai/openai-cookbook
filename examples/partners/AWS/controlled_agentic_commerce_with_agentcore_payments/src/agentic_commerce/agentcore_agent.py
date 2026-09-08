"""Agents SDK boundary for the optional AgentCore testnet join."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Literal

from agents import (
    Agent,
    Model,
    ModelSettings,
    RunConfig,
    Runner,
    function_tool,
)
from agents.tracing import set_trace_provider
from agents.tracing.provider import DefaultTraceProvider
from openai.types.shared import Reasoning
from pydantic import BaseModel, ConfigDict, Field

from .agentcore_application import (
    AgentCoreAccessResult,
    AgentCoreAuthorizedApplication,
)
from .errors import AgentResultInvalid, CommerceError
from .models import ApprovalGrant, PurchaseRequest


class AgentCoreAccessOutput(BaseModel):
    """Typed, non-authoritative summary of application transport evidence."""

    model_config = ConfigDict(frozen=True)

    status: Literal["completed"]
    merchant: str
    status_code: int = Field(ge=200, lt=300)
    amount: str
    currency: Literal["USDC"]
    network: Literal["eip155:84532"]
    payment_attempts: int = Field(ge=1)
    response_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    response_bytes: int = Field(ge=0)
    requires_human_approval: bool


@dataclass
class AgentCoreAccessRecorder:
    invocations: int = 0
    results: list[AgentCoreAccessResult] = field(default_factory=list)
    failures: list[tuple[str, str]] = field(default_factory=list)
    _lock: Any = field(default_factory=Lock, repr=False)

    def begin_invocation(self) -> bool:
        """Consume the one-shot tool capability before any side effect."""

        with self._lock:
            self.invocations += 1
            return self.invocations == 1

    def record(self, result: AgentCoreAccessResult) -> None:
        self.results.append(result)

    def record_failure(self, error: CommerceError) -> None:
        self.failures.append((error.code, str(error)))


@dataclass(frozen=True)
class AgentCoreAgentRun:
    output: AgentCoreAccessOutput
    access: AgentCoreAccessResult


def build_agentcore_access_agent(
    application: AgentCoreAuthorizedApplication,
    *,
    model: str | Model,
    request_id: str,
    idempotency_key: str,
    approval: ApprovalGrant | None,
    recorder: AgentCoreAccessRecorder,
) -> Agent[None]:
    """Build one agent with one application-controlled economic tool."""

    @function_tool(name_override="x402_fetch")
    def x402_fetch(resource_url: str, purpose: str) -> str:
        """Access one allowlisted x402 testnet resource for one purpose."""

        if not recorder.begin_invocation():
            error = AgentResultInvalid(
                "access_count_invalid",
                "The economic tool permits exactly one invocation.",
            )
            recorder.record_failure(error)
            return json.dumps(
                {
                    "status": "denied",
                    "code": error.code,
                    "message": str(error),
                },
                sort_keys=True,
            )
        try:
            result = application.access(
                PurchaseRequest(
                    request_id=request_id,
                    resource_url=resource_url,
                    purpose=purpose,
                    idempotency_key=idempotency_key,
                ),
                approval=approval,
            )
        except CommerceError as exc:
            recorder.record_failure(exc)
            return json.dumps(
                {
                    "status": "denied",
                    "code": exc.code,
                    "message": str(exc),
                },
                sort_keys=True,
            )
        recorder.record(result)
        return json.dumps(
            {
                "status": result.status,
                "merchant": result.merchant,
                "status_code": result.status_code,
                "amount": str(result.challenge.amount),
                "currency": result.challenge.currency,
                "network": result.challenge.network,
                "payment_attempts": result.payment_attempts,
                "response_sha256": result.response_sha256,
                "response_bytes": result.response_bytes,
                "requires_human_approval": (
                    result.authorization.requires_human_approval
                ),
            },
            sort_keys=True,
        )

    return Agent(
        name="AgentCore testnet access agent",
        model=model,
        model_settings=ModelSettings(
            reasoning=Reasoning(effort="low"),
            store=False,
        ),
        output_type=AgentCoreAccessOutput,
        tools=[x402_fetch],
        instructions=(
            "Use x402_fetch exactly once for the explicitly requested "
            "testnet resource. The application owns merchant policy, "
            "budgets, human approval, payment execution, and audit state. "
            "Return only the typed transport evidence from the tool. Never "
            "invent a payment, settlement, receipt, or resource claim."
        ),
    )


def validate_agentcore_access_output(
    output: AgentCoreAccessOutput,
    recorder: AgentCoreAccessRecorder,
) -> AgentCoreAccessResult:
    """Match every agent field to one application-observed tool result."""

    if recorder.invocations != 1:
        raise AgentResultInvalid(
            "access_count_invalid",
            "A valid testnet result requires exactly one total tool invocation.",
        )
    if len(recorder.results) != 1:
        if not recorder.results and len(recorder.failures) == 1:
            code, message = recorder.failures[0]
            raise AgentResultInvalid(code, message)
        raise AgentResultInvalid(
            "access_count_invalid",
            "A valid testnet result requires exactly one completed access.",
        )
    access = recorder.results[0]
    expected = {
        "status": access.status,
        "merchant": access.merchant,
        "status_code": access.status_code,
        "amount": str(access.challenge.amount),
        "currency": access.challenge.currency,
        "network": access.challenge.network,
        "payment_attempts": access.payment_attempts,
        "response_sha256": access.response_sha256,
        "response_bytes": access.response_bytes,
        "requires_human_approval": (access.authorization.requires_human_approval),
    }
    actual = output.model_dump()
    mismatches = sorted(
        name for name, value in expected.items() if actual[name] != value
    )
    if mismatches:
        raise AgentResultInvalid(
            "agent_output_mismatch",
            "Agent output did not match application evidence for: "
            + ", ".join(mismatches),
        )
    return access


async def run_agentcore_access(
    application: AgentCoreAuthorizedApplication,
    *,
    model: str | Model,
    request_id: str,
    idempotency_key: str,
    approval: ApprovalGrant | None,
    resource_url: str,
    purpose: str = "testnet_integration_validation",
) -> AgentCoreAgentRun:
    """Run and validate the optional AgentCore testnet integration path."""

    recorder = AgentCoreAccessRecorder()
    # Install a disabled provider before Runner initializes the default trace
    # exporter. This keeps the Bedrock-only path from constructing an OpenAI
    # tracing client when no tracing destination has been approved.
    trace_provider = DefaultTraceProvider()
    trace_provider.set_disabled(True)
    set_trace_provider(trace_provider)
    agent = build_agentcore_access_agent(
        application,
        model=model,
        request_id=request_id,
        idempotency_key=idempotency_key,
        approval=approval,
        recorder=recorder,
    )
    prompt = (
        f"Access the approved testnet resource at {resource_url} for the "
        f"{purpose} purpose. Use x402_fetch exactly once, then return only "
        "the typed transport evidence supported by the tool result."
    )
    result = await Runner.run(
        agent,
        prompt,
        max_turns=4,
        run_config=RunConfig(
            tracing_disabled=True,
            workflow_name="AgentCore Testnet Access",
        ),
    )
    output = result.final_output
    if not isinstance(output, AgentCoreAccessOutput):
        raise AgentResultInvalid(
            "typed_output_missing",
            "The agent did not return the required typed output.",
        )
    access = validate_agentcore_access_output(output, recorder)
    return AgentCoreAgentRun(output=output, access=access)
