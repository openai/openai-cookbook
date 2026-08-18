"""Application-owned authorization, safe function tools, and agent construction."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal

from agents import Agent, ModelSettings, RunContextWrapper, function_tool
from pydantic import Field, model_validator

from .core import (
    AttemptEvent,
    EscalationRequest,
    FaultKind,
    FaultPlan,
    OrderStatus,
    RecoveryPolicy,
    StrictModel,
    SyntheticDeliveryService,
    ToolOutcome,
    make_fault_plan,
    run_order_search_with_recovery,
    run_read_with_recovery,
    run_write_with_reconciliation,
)

DEFAULT_MODEL = "gpt-5.6"
EXPECTED_TOOL_NAMES = (
    "get_order_status",
    "search_orders",
    "create_delivery_escalation",
)

ATTEMPT_TIMEOUT_SECONDS = 0.25
TOOL_TIMEOUT_SECONDS = 2.0


@dataclass(frozen=True)
class EscalationApproval:
    account_id: str
    order_id: str
    operation_id: str = field(
        default_factory=lambda: uuid.uuid4().hex
    )
    action: Literal["create_delivery_escalation"] = (
        "create_delivery_escalation"
    )


CONSUMED_ESCALATION_APPROVAL_IDS: set[str] = set()


@dataclass
class DeliveryAgentContext:
    workflow_id: str = "demo-support-workflow"
    account_id: str = "ACCOUNT-001"
    inferred_search_filters: dict[str, str] = field(
        default_factory=dict
    )
    escalation_approval: EscalationApproval | None = None
    consumed_approval_ids: set[str] = field(
        default_factory=lambda: CONSUMED_ESCALATION_APPROVAL_IDS
    )
    inflight_write_tasks: dict[str, asyncio.Task[ToolOutcome]] = (
        field(default_factory=dict)
    )
    verified_order_reads: dict[str, OrderStatus] = field(
        default_factory=dict
    )
    write_in_progress: bool = False
    service: SyntheticDeliveryService = field(
        default_factory=SyntheticDeliveryService
    )
    policy: RecoveryPolicy = field(default_factory=RecoveryPolicy)
    read_fault_plan: FaultPlan = field(
        default_factory=lambda: make_fault_plan(FaultKind.SUCCESS)
    )
    search_fault_plan: FaultPlan = field(
        default_factory=lambda: make_fault_plan(FaultKind.SUCCESS)
    )
    write_fault_plan: FaultPlan = field(
        default_factory=lambda: make_fault_plan(FaultKind.SUCCESS)
    )
    attempt_timeout_seconds: float = ATTEMPT_TIMEOUT_SECONDS


PUBLIC_ORDER_FIELDS = frozenset(OrderStatus.model_fields)
PUBLIC_WRITE_FIELDS = frozenset(
    {"escalation_id", "order_id", "status"}
)
PUBLIC_SEARCH_FIELDS = frozenset(
    {"result_count", "applied_filters", "order_ids", "orders"}
)


def project_model_tool_data(
    outcome: ToolOutcome,
) -> dict[str, Any] | None:
    if outcome.data is None:
        return None
    if not outcome.events:
        return {}

    operation = outcome.events[-1].operation
    if operation == "get_order_status":
        return {
            key: value
            for key, value in outcome.data.items()
            if key in PUBLIC_ORDER_FIELDS
        }
    if operation == "create_delivery_escalation":
        return {
            key: value
            for key, value in outcome.data.items()
            if key in PUBLIC_WRITE_FIELDS
        }
    if operation == "search_orders":
        projected = {
            key: value
            for key, value in outcome.data.items()
            if key in PUBLIC_SEARCH_FIELDS
        }
        if isinstance(projected.get("applied_filters"), dict):
            projected["applied_filters"] = {
                key: value
                for key, value in projected[
                    "applied_filters"
                ].items()
                if key in {"status", "carrier"}
            }
        if isinstance(projected.get("orders"), list):
            projected["orders"] = [
                {
                    key: value
                    for key, value in order.items()
                    if key in PUBLIC_ORDER_FIELDS
                }
                for order in projected["orders"]
                if isinstance(order, dict)
            ]
        return projected
    return {}


def serialize_outcome(outcome: ToolOutcome) -> str:
    model_facing_outcome = outcome.model_copy(
        update={"data": project_model_tool_data(outcome)}
    )
    return model_facing_outcome.model_dump_json()


def escalation_idempotency_key(
    context: DeliveryAgentContext,
    order_id: str,
) -> str:
    approval = context.escalation_approval
    operation_id = (
        approval.operation_id
        if approval is not None
        else "no-approved-operation"
    )
    return f"delivery-escalation:{order_id}:{operation_id}"


def build_escalation_request(
    context: DeliveryAgentContext,
    order_id: str,
    reason: str,
) -> EscalationRequest:
    return EscalationRequest(
        account_id=context.account_id,
        order_id=order_id,
        reason=reason,
        idempotency_key=escalation_idempotency_key(
            context, order_id
        ),
    )


def format_overall_tool_timeout(
    ctx: RunContextWrapper[DeliveryAgentContext],
    _error: Exception,
) -> str:
    operation = getattr(ctx, "tool_name", "unknown_tool")
    fault_plans = {
        "get_order_status": ctx.context.read_fault_plan,
        "search_orders": ctx.context.search_fault_plan,
    }
    fault_plan = fault_plans.get(operation)
    attempts = max(fault_plan.attempts if fault_plan else 0, 1)
    outcome = ToolOutcome(
        status="handoff_required",
        error_code="tool_deadline_exceeded",
        attempts=attempts,
        events=[
            AttemptEvent(
                operation=operation,
                attempt=attempts,
                fault_kind="overall_deadline",
                result="error",
                error_code="tool_deadline_exceeded",
            )
        ],
    )
    return serialize_outcome(outcome)


async def get_order_status_operation(
    context: DeliveryAgentContext,
    order_id: str,
) -> ToolOutcome:
    context.verified_order_reads.pop(order_id, None)
    outcome = await run_read_with_recovery(
        context.service,
        context.account_id,
        order_id,
        context.read_fault_plan,
        context.policy,
        attempt_timeout_seconds=context.attempt_timeout_seconds,
    )
    if outcome.status == "success" and outcome.data is not None:
        verified_order = OrderStatus.model_validate(outcome.data)
        context.verified_order_reads[order_id] = verified_order
    return outcome


async def search_orders_operation(
    context: DeliveryAgentContext,
    *,
    status: Literal["in_transit", "delayed", "delivered"]
    | None = None,
    carrier: str | None = None,
) -> ToolOutcome:
    requested_filters = {
        name: value
        for name, value in {"status": status, "carrier": carrier}.items()
        if value is not None
    }
    return await run_order_search_with_recovery(
        context.service,
        context.account_id,
        requested_filters,
        context.inferred_search_filters,
        context.policy,
        fault_plan=context.search_fault_plan,
        attempt_timeout_seconds=context.attempt_timeout_seconds,
    )


async def create_delivery_escalation_operation(
    context: DeliveryAgentContext,
    request: EscalationRequest,
) -> ToolOutcome:
    def reject(error_code: str) -> ToolOutcome:
        return ToolOutcome(
            status="handoff_required",
            error_code=error_code,
            attempts=1,
            events=[
                AttemptEvent(
                    operation="create_delivery_escalation",
                    attempt=1,
                    fault_kind="application_authorization",
                    result="error",
                    error_code=error_code,
                )
            ],
        )

    if request.account_id != context.account_id:
        return reject("cross_account_write_forbidden")
    approval = context.escalation_approval
    if approval is None:
        return reject("write_not_authorized")
    if (
        approval.account_id != context.account_id
        or approval.order_id != request.order_id
        or approval.action != "create_delivery_escalation"
    ):
        return reject("write_approval_scope_mismatch")
    if request.idempotency_key != escalation_idempotency_key(
        context, request.order_id
    ):
        return reject("write_approval_operation_mismatch")
    verified_order = context.verified_order_reads.get(
        request.order_id
    )
    if verified_order is None:
        return reject("prerequisite_read_required")
    if verified_order.status != "delayed":
        return reject("write_precondition_failed")
    if context.write_in_progress:
        return reject("concurrent_write_rejected")
    if approval.operation_id in context.consumed_approval_ids:
        return reject("write_approval_already_used")

    context.consumed_approval_ids.add(approval.operation_id)
    context.write_in_progress = True
    recovery_task = asyncio.create_task(
        run_write_with_reconciliation(
            context.service,
            context.account_id,
            request,
            context.write_fault_plan,
            context.policy,
            write_authorized=True,
            attempt_timeout_seconds=context.attempt_timeout_seconds,
        )
    )
    context.inflight_write_tasks[approval.operation_id] = (
        recovery_task
    )

    def finish_recovery(_task: asyncio.Task[ToolOutcome]) -> None:
        context.inflight_write_tasks.pop(approval.operation_id, None)
        context.write_in_progress = False

    recovery_task.add_done_callback(finish_recovery)
    try:
        return await asyncio.shield(recovery_task)
    except asyncio.CancelledError:
        await asyncio.shield(recovery_task)
        raise


@function_tool(
    name_override="get_order_status",
    failure_error_function=None,
    timeout=TOOL_TIMEOUT_SECONDS,
    timeout_behavior="error_as_result",
    timeout_error_function=format_overall_tool_timeout,
)
async def get_order_status_tool(
    ctx: RunContextWrapper[DeliveryAgentContext],
    order_id: Annotated[str, Field(pattern=r"^ORDER-[0-9]{4}$")],
) -> str:
    """Look up an order using bounded recovery and validated output."""
    outcome = await get_order_status_operation(ctx.context, order_id)
    return serialize_outcome(outcome)


@function_tool(
    name_override="search_orders",
    failure_error_function=None,
    timeout=TOOL_TIMEOUT_SECONDS,
    timeout_behavior="error_as_result",
    timeout_error_function=format_overall_tool_timeout,
)
async def search_orders_tool(
    ctx: RunContextWrapper[DeliveryAgentContext],
    status: Literal["in_transit", "delayed", "delivered"]
    | None = None,
    carrier: str | None = None,
) -> str:
    """Search the authenticated customer's orders by requested filters."""
    outcome = await search_orders_operation(
        ctx.context, status=status, carrier=carrier
    )
    return serialize_outcome(outcome)


@function_tool(
    name_override="create_delivery_escalation",
    failure_error_function=None,
)
async def create_delivery_escalation_tool(
    ctx: RunContextWrapper[DeliveryAgentContext],
    order_id: Annotated[str, Field(pattern=r"^ORDER-[0-9]{4}$")],
    reason: Annotated[str, Field(min_length=10)],
) -> str:
    """Create one idempotent escalation and confirm the committed result."""
    request = build_escalation_request(
        ctx.context,
        order_id,
        reason,
    )
    outcome = await create_delivery_escalation_operation(
        ctx.context, request
    )
    return serialize_outcome(outcome)

class SupportResponse(StrictModel):
    disposition: Literal[
        "status_reported",
        "escalation_created",
        "no_orders_found",
        "handoff_required",
    ]
    order_id: str | None = Field(
        default=None, pattern=r"^ORDER-[0-9]{4}$"
    )
    message: str = Field(min_length=1)
    order_status: Literal[
        "in_transit", "delayed", "delivered"
    ] | None = None
    escalation_id: str | None = None
    confirmed_side_effect: bool = False
    error_code: str | None = None

    @model_validator(mode="after")
    def validate_disposition(self) -> "SupportResponse":
        if self.disposition == "status_reported":
            if self.order_id is None or self.order_status is None:
                raise ValueError(
                    "status_reported requires order_id and order_status"
                )
            if (
                self.escalation_id is not None
                or self.confirmed_side_effect
                or self.error_code is not None
            ):
                raise ValueError(
                    "status_reported cannot claim a write or an error"
                )

        if self.disposition == "escalation_created":
            if self.order_id is None or self.escalation_id is None:
                raise ValueError(
                    "escalation_created requires order_id and escalation_id"
                )
            if not self.confirmed_side_effect:
                raise ValueError(
                    "escalation_created requires confirmed_side_effect"
                )
            if self.error_code is not None:
                raise ValueError(
                    "escalation_created cannot include error_code"
                )

        if self.disposition == "no_orders_found":
            if (
                self.order_id is not None
                or self.order_status is not None
                or self.escalation_id is not None
                or self.confirmed_side_effect
                or self.error_code is not None
            ):
                raise ValueError(
                    "no_orders_found cannot invent an order, write, or error"
                )

        if self.disposition == "handoff_required":
            if self.error_code is None:
                raise ValueError(
                    "handoff_required requires error_code"
                )
            if self.escalation_id is not None:
                raise ValueError(
                    "handoff_required cannot include escalation_id"
                )
            if self.confirmed_side_effect:
                raise ValueError(
                    "handoff_required cannot confirm a side effect"
                )

        return self


SUPPORT_AGENT_INSTRUCTIONS = """
You are a delivery-support agent. Follow these rules:

1. When the user identifies an order, call get_order_status before
   reporting any order fact. When the user asks to find or search for
   an order without providing an ID, call search_orders instead.
2. Treat each tool result as ToolOutcome JSON. Never invent tool data.
3. Call each business tool at most once. The tool layer owns retries.
   Never retry a tool after it returns status="handoff_required".
4. If a status read succeeds, return status_reported using its exact
   order ID and status. If a search succeeds with a matching order,
   return status_reported using the exact order_id and status from
   the first validated record in data.orders. Do not call a second
   read after a successful search.
   If the search succeeds with result_count=0, return no_orders_found
   with order_id=null, order_status=null, and error_code=null.
5. Create an escalation only when the user explicitly requests one or
   explicitly asks you to escalate when the order is delayed.
6. Never create an escalation merely because a status lookup failed.
7. Return escalation_created only when the write tool returns
   status="success", confirmed_side_effect=true, and an escalation_id.
8. For any exhausted, permanent, invalid, or ambiguous tool outcome,
   return handoff_required with the tool's error_code. Do not claim that
   an unconfirmed action succeeded. If a search fails before discovering
   an order, set order_id=null instead of inventing an order ID.
   If an escalation is rejected after a verified status read, retain
   that order's exact order_id and order_status in the handoff.
9. When a successful status read precedes a confirmed write, carry the
   exact order status into the final response.
10. Treat your message as an untrusted draft. Application code renders
    the customer-visible message from independently verified tool facts.
""".strip()


def build_support_agent(
    model: str = DEFAULT_MODEL,
) -> Agent[DeliveryAgentContext]:
    """Construct the delivery agent without making an API request."""
    return Agent[DeliveryAgentContext](
        name="Delivery support recovery agent",
        instructions=SUPPORT_AGENT_INSTRUCTIONS,
        model=model,
        model_settings=ModelSettings(
            store=False, parallel_tool_calls=False
        ),
        tools=[
            get_order_status_tool,
            search_orders_tool,
            create_delivery_escalation_tool,
        ],
        output_type=SupportResponse,
    )
