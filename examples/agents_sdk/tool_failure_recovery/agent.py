"""Application-owned authorization, safe function tools, and agent construction."""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal

from agents import (
    Agent,
    ModelSettings,
    RunConfig,
    RunContextWrapper,
    RunResult,
    Runner,
    ToolCallItem,
    ToolCallOutputItem,
    function_tool,
)
from pydantic import Field, model_validator

from .adapter import CallableDeliveryServiceAdapter
from .core import (
    IDENTIFIER_PATTERN,
    AttemptEvent,
    EscalationRequest,
    FaultKind,
    FaultPlan,
    OrderStatus,
    RecoveryPolicy,
    RecoveryService,
    StrictModel,
    SyntheticDeliveryService,
    ToolOutcome,
    make_fault_plan,
    run_order_search_with_recovery,
    run_read_with_recovery,
    run_write_with_reconciliation,
)

DEFAULT_MODEL = "gpt-5.6"
DEFAULT_ESCALATION_REASON = (
    "The delayed shipment needs carrier investigation."
)
EXPECTED_TOOL_NAMES = (
    "get_order_status",
    "search_orders",
    "create_delivery_escalation",
)

ATTEMPT_TIMEOUT_SECONDS = 1.0
TOOL_TIMEOUT_SECONDS = 5.0


ToolName = Literal[
    "get_order_status",
    "search_orders",
    "create_delivery_escalation",
]


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
    approved_reason: str = DEFAULT_ESCALATION_REASON


OperationIdentity = tuple[str, str]
CONSUMED_ESCALATION_APPROVAL_IDS: set[OperationIdentity] = set()


@dataclass
class ApprovedOperationState:
    """Persistable operation facts; the task is process-local execution state."""

    account_id: str
    operation_id: str
    workflow_id: str
    order_id: str
    approved_reason: str
    idempotency_key: str
    recovery_task: asyncio.Task[ToolOutcome] | None = None
    outcome: ToolOutcome | None = None
    delivered: bool = False


APPROVED_OPERATION_STATES: dict[
    OperationIdentity, ApprovedOperationState
] = {}


@dataclass(frozen=True)
class ObservedToolRequest:
    """Application-owned invocation identity, never a model control field."""

    tool_name: ToolName
    account_id: str
    order_id: str | None = None
    requested_filters: dict[str, str] = field(default_factory=dict)
    operation_id: str | None = None


@dataclass
class DeliveryAgentContext:
    workflow_id: str = "demo-support-workflow"
    account_id: str = "ACCOUNT-001"
    inferred_search_filters: dict[str, str] = field(
        default_factory=dict
    )
    authorized_search_filters: dict[str, str] | None = None
    escalation_approval: EscalationApproval | None = None
    consumed_approval_ids: set[OperationIdentity] = field(
        default_factory=lambda: CONSUMED_ESCALATION_APPROVAL_IDS
    )
    operation_states: dict[
        OperationIdentity, ApprovedOperationState
    ] = field(default_factory=lambda: APPROVED_OPERATION_STATES)
    inflight_write_tasks: dict[str, asyncio.Task[ToolOutcome]] = (
        field(default_factory=dict)
    )
    verified_order_reads: dict[str, OrderStatus] = field(
        default_factory=dict
    )
    observed_tool_requests: list[ObservedToolRequest] = field(
        default_factory=list
    )
    write_in_progress: bool = False
    service: RecoveryService = field(
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
    return (
        f"delivery-escalation:{context.account_id}:"
        f"{order_id}:{operation_id}"
    )


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
    context.observed_tool_requests.append(
        ObservedToolRequest(
            tool_name="get_order_status",
            account_id=context.account_id,
            order_id=order_id,
        )
    )
    context.verified_order_reads.pop(order_id, None)
    outcome = await run_read_with_recovery(
        context.service,
        context.account_id,
        order_id,
        context.read_fault_plan,
        context.policy,
        attempt_timeout_seconds=context.attempt_timeout_seconds,
        skip_pre_read_authorization=isinstance(
            context.service, CallableDeliveryServiceAdapter
        ),
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
    context.observed_tool_requests.append(
        ObservedToolRequest(
            tool_name="search_orders",
            account_id=context.account_id,
            requested_filters=dict(requested_filters),
        )
    )
    if (
        context.authorized_search_filters is None
        or requested_filters != context.authorized_search_filters
    ):
        return ToolOutcome(
            status="handoff_required",
            error_code="search_filter_not_authorized",
            attempts=1,
            events=[
                AttemptEvent(
                    operation="search_orders",
                    attempt=1,
                    fault_kind="application_authorization",
                    result="error",
                    error_code="search_filter_not_authorized",
                )
            ],
        )

    outcome = await run_order_search_with_recovery(
        context.service,
        context.account_id,
        requested_filters,
        context.inferred_search_filters,
        context.policy,
        fault_plan=context.search_fault_plan,
        attempt_timeout_seconds=context.attempt_timeout_seconds,
    )
    if outcome.status == "success" and outcome.data is not None:
        for raw_order in outcome.data.get("orders", []):
            verified_order = OrderStatus.model_validate(raw_order)
            context.verified_order_reads[
                verified_order.order_id
            ] = verified_order
    return outcome


async def create_delivery_escalation_operation(
    context: DeliveryAgentContext,
    request: EscalationRequest,
) -> ToolOutcome:
    approval = context.escalation_approval
    context.observed_tool_requests.append(
        ObservedToolRequest(
            tool_name="create_delivery_escalation",
            account_id=context.account_id,
            order_id=request.order_id,
            operation_id=(
                approval.operation_id if approval is not None else None
            ),
        )
    )

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
    if request.reason != approval.approved_reason:
        return reject("write_approval_payload_mismatch")
    verified_order = context.verified_order_reads.get(
        request.order_id
    )
    if verified_order is None:
        return reject("prerequisite_read_required")
    if verified_order.status != "delayed":
        return reject("write_precondition_failed")
    operation_identity = (context.account_id, approval.operation_id)
    operation_state = context.operation_states.get(operation_identity)
    if operation_state is not None:
        matching_operation = (
            operation_state.account_id == context.account_id
            and operation_state.workflow_id == context.workflow_id
            and operation_state.order_id == request.order_id
            and operation_state.approved_reason == request.reason
            and operation_state.idempotency_key
            == request.idempotency_key
        )
        if not matching_operation or operation_state.delivered:
            return reject("write_approval_already_used")
        if operation_state.outcome is not None:
            return operation_state.outcome
        recovery_task = operation_state.recovery_task
        if recovery_task is None:
            return reject("write_approval_already_used")
        try:
            outcome = await asyncio.shield(recovery_task)
        except asyncio.CancelledError:
            await asyncio.shield(recovery_task)
            raise
        operation_state.outcome = outcome
        return outcome

    if context.write_in_progress:
        return reject("concurrent_write_rejected")
    if operation_identity in context.consumed_approval_ids:
        return reject("write_approval_already_used")
    for pending_operation in context.operation_states.values():
        if (
            pending_operation.account_id != context.account_id
            or pending_operation.order_id != request.order_id
            or pending_operation.delivered
            or pending_operation.outcome is None
            or not pending_operation.outcome.confirmed_side_effect
        ):
            continue
        existing_record = context.service.get_escalation_by_key(
            context.account_id,
            pending_operation.idempotency_key,
        )
        if (
            existing_record is not None
            and existing_record.account_id == context.account_id
            and existing_record.order_id == request.order_id
            and existing_record.reason
            == pending_operation.approved_reason
        ):
            return reject("write_pending_customer_finalization")

    operation_state = ApprovedOperationState(
        account_id=context.account_id,
        operation_id=approval.operation_id,
        workflow_id=context.workflow_id,
        order_id=request.order_id,
        approved_reason=request.reason,
        idempotency_key=request.idempotency_key,
    )
    context.operation_states[operation_identity] = operation_state
    context.consumed_approval_ids.add(operation_identity)
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
    operation_state.recovery_task = recovery_task

    def finish_recovery(task: asyncio.Task[ToolOutcome]) -> None:
        if not task.cancelled() and task.exception() is None:
            operation_state.outcome = task.result()
        context.inflight_write_tasks.pop(approval.operation_id, None)
        context.write_in_progress = False

    recovery_task.add_done_callback(finish_recovery)
    try:
        outcome = await asyncio.shield(recovery_task)
        operation_state.outcome = outcome
        return outcome
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
    order_id: Annotated[str, Field(pattern=IDENTIFIER_PATTERN)],
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
    order_id: Annotated[str, Field(pattern=IDENTIFIER_PATTERN)],
    reason: Annotated[str, Field(min_length=10)],
) -> str:
    """Create an escalation using the exact application-approved reason."""
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
        default=None, pattern=IDENTIFIER_PATTERN
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
   the first validated record in data.orders. A validated search record
   also satisfies the prerequisite for an explicitly requested escalation;
   do not call a second read after a successful search.
   If the search succeeds with result_count=0, return no_orders_found
   with order_id=null, order_status=null, and error_code=null.
5. Create an escalation only when the user explicitly requests one or
   explicitly asks you to escalate when the order is delayed.
   Pass this exact approved reason to create_delivery_escalation:
   "The delayed shipment needs carrier investigation."
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


def build_support_agent_instructions(
    ctx: RunContextWrapper[DeliveryAgentContext],
    _agent: Agent[DeliveryAgentContext],
) -> str:
    """Expose only the JSON-escaped, application-approved write payload."""

    approval = ctx.context.escalation_approval
    approved_reason = (
        approval.approved_reason
        if approval is not None
        else DEFAULT_ESCALATION_REASON
    )
    return SUPPORT_AGENT_INSTRUCTIONS.replace(
        json.dumps(DEFAULT_ESCALATION_REASON, ensure_ascii=True),
        json.dumps(approved_reason, ensure_ascii=True),
        1,
    )


def build_support_agent(
    model: str = DEFAULT_MODEL,
) -> Agent[DeliveryAgentContext]:
    """Construct the delivery agent without making an API request."""
    return Agent[DeliveryAgentContext](
        name="Delivery support recovery agent",
        instructions=build_support_agent_instructions,
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


class ObservedToolOutcome(StrictModel):
    """Verified SDK output joined to application-owned invocation identity."""

    tool_name: ToolName
    status: Literal["success", "handoff_required"]
    attempts: int = Field(ge=1)
    confirmed_side_effect: bool
    data: dict[str, Any] | None = None
    error_code: str | None = None
    order_id: str | None = None
    operation_id: str | None = None
    requested_filters: dict[str, str] = Field(default_factory=dict)


def extract_tool_outcomes(
    result: RunResult,
    context: DeliveryAgentContext | None = None,
    *,
    request_start_index: int = 0,
) -> tuple[list[ObservedToolOutcome], list[str]]:
    """Pair each SDK call with its output and the trusted application journal."""

    tool_calls: dict[str, ToolName] = {}
    call_arguments: dict[str, dict[str, Any]] = {}
    call_order: list[str] = []
    outputs_by_call: dict[str, ToolOutcome] = {}
    raw_tool_events: list[tuple[str, str]] = []

    for item in result.new_items:
        if isinstance(item, ToolCallItem):
            if item.call_id is None or item.tool_name is None:
                raise ValueError("Function-tool call lacks identity")
            if item.tool_name not in EXPECTED_TOOL_NAMES:
                raise ValueError(f"Unexpected tool: {item.tool_name}")
            if item.call_id in tool_calls:
                raise ValueError("Duplicate tool call ID")
            tool_calls[item.call_id] = item.tool_name
            call_order.append(item.call_id)
            raw_item = item.raw_item
            raw_arguments = (
                raw_item.get("arguments")
                if isinstance(raw_item, dict)
                else getattr(raw_item, "arguments", None)
            )
            if isinstance(raw_arguments, str):
                parsed_arguments = json.loads(raw_arguments)
            elif isinstance(raw_arguments, dict):
                parsed_arguments = raw_arguments
            else:
                parsed_arguments = {}
            if not isinstance(parsed_arguments, dict):
                raise ValueError("Function-tool arguments must be an object")
            call_arguments[item.call_id] = parsed_arguments
            raw_tool_events.append(("call", item.call_id))
        elif isinstance(item, ToolCallOutputItem):
            if item.call_id is None or not isinstance(item.output, str):
                raise ValueError("Function-tool output is not JSON text")
            if item.call_id in outputs_by_call:
                raise ValueError("Duplicate tool output ID")
            outputs_by_call[item.call_id] = (
                ToolOutcome.model_validate_json(item.output)
            )
            raw_tool_events.append(("output", item.call_id))

    if set(tool_calls) != set(outputs_by_call):
        raise ValueError("Tool calls and outputs do not pair one-to-one")

    observed_requests = (
        context.observed_tool_requests[request_start_index:]
        if context is not None
        else []
    )
    if context is not None and len(observed_requests) != len(call_order):
        raise ValueError("Tool calls do not match the application journal")

    observed_outcomes: list[ObservedToolOutcome] = []
    for index, call_id in enumerate(call_order):
        tool_name = tool_calls[call_id]
        outcome = outputs_by_call[call_id]
        trusted_request = (
            observed_requests[index] if context is not None else None
        )
        if trusted_request is not None:
            if (
                trusted_request.tool_name != tool_name
                or trusted_request.account_id != context.account_id
            ):
                raise ValueError("Tool invocation has the wrong trusted scope")
            arguments = call_arguments[call_id]
            if (
                "order_id" in arguments
                and arguments["order_id"] != trusted_request.order_id
            ):
                raise ValueError("Tool invocation changed the requested order")
            model_filters = {
                key: value
                for key, value in arguments.items()
                if key in {"status", "carrier"} and value is not None
            }
            if model_filters and model_filters != trusted_request.requested_filters:
                raise ValueError("Tool invocation changed the requested filters")
            if (
                outcome.data is not None
                and trusted_request.order_id is not None
                and outcome.data.get("order_id")
                != trusted_request.order_id
            ):
                raise ValueError("Tool output describes an unrequested order")
        if outcome.events and outcome.events[-1].operation != tool_name:
            raise ValueError("Tool outcome does not match its invocation")
        observed_outcomes.append(
            ObservedToolOutcome(
                tool_name=tool_name,
                status=outcome.status,
                attempts=outcome.attempts,
                confirmed_side_effect=outcome.confirmed_side_effect,
                data=outcome.data,
                error_code=outcome.error_code,
                order_id=(
                    trusted_request.order_id
                    if trusted_request is not None
                    else None
                ),
                operation_id=(
                    trusted_request.operation_id
                    if trusted_request is not None
                    else None
                ),
                requested_filters=(
                    dict(trusted_request.requested_filters)
                    if trusted_request is not None
                    else {}
                ),
            )
        )

    tool_events = [
        f"{event_kind}:{tool_calls[call_id]}"
        for event_kind, call_id in raw_tool_events
    ]
    return observed_outcomes, tool_events


def render_customer_message(
    response: SupportResponse,
    context: DeliveryAgentContext,
    tool_outcomes: list[ObservedToolOutcome],
) -> str:
    """Render customer-visible text exclusively from verified app-owned facts."""

    if not tool_outcomes:
        raise ValueError("A customer response requires tool evidence.")
    terminal_outcome = tool_outcomes[-1]
    confirmed_write_exists = any(
        outcome.tool_name == "create_delivery_escalation"
        and outcome.confirmed_side_effect
        for outcome in tool_outcomes
    )
    if (
        response.disposition != "escalation_created"
        and confirmed_write_exists
    ):
        raise ValueError(
            "A confirmed escalation cannot be hidden by another outcome."
        )

    if response.disposition == "status_reported":
        if (
            terminal_outcome.tool_name
            not in {"get_order_status", "search_orders"}
            or terminal_outcome.status != "success"
        ):
            raise ValueError(
                "The terminal tool result does not support order status."
            )
        if terminal_outcome.data is None:
            raise ValueError("The terminal order result contains no data.")
        matching_orders: list[OrderStatus] = []
        if terminal_outcome.tool_name == "get_order_status":
            matching_orders.append(
                OrderStatus.model_validate(terminal_outcome.data)
            )
        else:
            matching_orders.extend(
                OrderStatus.model_validate(order)
                for order in terminal_outcome.data.get("orders", [])
            )
        verified_order = next(
            (
                order
                for order in matching_orders
                if order.order_id == response.order_id
                and order.status == response.order_status
            ),
            None,
        )
        if verified_order is None:
            raise ValueError("No verified order supports the response.")
        return (
            f"Order {verified_order.order_id} is currently "
            f"{verified_order.status.replace('_', ' ')}."
        )

    if response.disposition == "no_orders_found":
        authorized_empty_search = (
            terminal_outcome.tool_name == "search_orders"
            and terminal_outcome.status == "success"
            and terminal_outcome.data is not None
            and terminal_outcome.data.get("result_count") == 0
            and not terminal_outcome.data.get("order_ids", [])
            and not terminal_outcome.data.get("orders", [])
        )
        if not authorized_empty_search:
            raise ValueError("No authorized empty search was observed.")
        return "No orders matched your requested filters."

    if response.disposition == "handoff_required":
        verified_handoff = (
            terminal_outcome.status == "handoff_required"
            and terminal_outcome.error_code == response.error_code
        )
        if not verified_handoff:
            raise ValueError("No verified tool handoff was observed.")
        if terminal_outcome.tool_name == "search_orders":
            if response.order_id is not None:
                raise ValueError("An unsuccessful search cannot identify an order.")
        elif (
            terminal_outcome.order_id is None
            or response.order_id != terminal_outcome.order_id
        ):
            raise ValueError("Handoff order differs from the verified invocation.")
        if terminal_outcome.tool_name == "create_delivery_escalation":
            approval = context.escalation_approval
            if (
                terminal_outcome.operation_id is not None
                and (
                    approval is None
                    or approval.operation_id
                    != terminal_outcome.operation_id
                )
            ):
                raise ValueError("Handoff operation differs from its approval.")
        verified_order = (
            context.verified_order_reads.get(response.order_id)
            if response.order_id is not None
            else None
        )
        if response.order_status is not None and (
            verified_order is None
            or verified_order.status != response.order_status
        ):
            raise ValueError("Handoff status is not independently verified.")
        if verified_order is not None:
            return (
                f"Order {verified_order.order_id} is "
                f"{verified_order.status.replace('_', ' ')}, "
                "but the requested action needs support review."
            )
        return (
            "I could not verify the requested information. "
            "A support specialist will review it."
        )

    if response.order_id is None:
        raise ValueError("A confirmed escalation requires an order.")
    verified_order = context.verified_order_reads.get(response.order_id)
    if (
        verified_order is None
        or response.order_status != verified_order.status
    ):
        raise ValueError("Escalation status is not independently verified.")
    if (
        terminal_outcome.tool_name != "create_delivery_escalation"
        or terminal_outcome.status != "success"
        or not terminal_outcome.confirmed_side_effect
        or (
            terminal_outcome.order_id is not None
            and terminal_outcome.order_id != response.order_id
        )
    ):
        raise ValueError(
            "The terminal tool result did not confirm an escalation."
        )
    approval = context.escalation_approval
    if (
        approval is None
        or approval.account_id != context.account_id
        or approval.order_id != response.order_id
        or (
            terminal_outcome.operation_id is not None
            and terminal_outcome.operation_id != approval.operation_id
        )
    ):
        raise ValueError("No application approval supports the escalation.")
    idempotency_key = escalation_idempotency_key(
        context, response.order_id
    )
    record = context.service.get_escalation_by_key(
        context.account_id, idempotency_key
    )
    verified_write = (
        terminal_outcome.data is not None
        and terminal_outcome.data.get("escalation_id")
        == response.escalation_id
    )
    if (
        record is None
        or record.account_id != context.account_id
        or record.order_id != response.order_id
        or record.reason != approval.approved_reason
        or record.escalation_id != response.escalation_id
        or not verified_write
    ):
        raise ValueError("No authoritative committed escalation exists.")
    return (
        f"A support escalation ({record.escalation_id}) was created "
        f"for order {record.order_id}."
    )


@dataclass(frozen=True)
class SafeSupportResult:
    """Application-finalized response; no untrusted model draft is exposed."""

    response: SupportResponse
    customer_message: str
    observed_tool_outcomes: tuple[ObservedToolOutcome, ...]
    tool_events: tuple[str, ...]


def finalize_support_response(
    run_result: RunResult,
    context: DeliveryAgentContext,
    *,
    request_start_index: int = 0,
) -> SafeSupportResult:
    """Validate execution evidence and replace model prose with trusted prose."""

    response = run_result.final_output_as(
        SupportResponse, raise_if_incorrect_type=True
    )
    tool_outcomes, tool_events = extract_tool_outcomes(
        run_result,
        context,
        request_start_index=request_start_index,
    )
    customer_message = render_customer_message(
        response, context, tool_outcomes
    )
    trusted_response = response.model_copy(
        update={"message": customer_message}
    )
    if trusted_response.disposition == "escalation_created":
        approval = context.escalation_approval
        if approval is None:
            raise ValueError("A customer escalation requires its approval.")
        operation_identity = (
            context.account_id,
            approval.operation_id,
        )
        operation_state = context.operation_states.get(operation_identity)
        if (
            operation_state is None
            or operation_state.delivered
            or operation_state.workflow_id != context.workflow_id
            or operation_state.order_id != trusted_response.order_id
            or operation_state.approved_reason != approval.approved_reason
            or operation_state.idempotency_key
            != escalation_idempotency_key(
                context, approval.order_id
            )
            or operation_state.outcome is None
            or not operation_state.outcome.confirmed_side_effect
        ):
            raise ValueError("The escalation operation cannot be finalized.")
        operation_state.delivered = True
    return SafeSupportResult(
        response=trusted_response,
        customer_message=customer_message,
        observed_tool_outcomes=tuple(tool_outcomes),
        tool_events=tuple(tool_events),
    )


async def run_support_agent(
    prompt: str,
    context: DeliveryAgentContext,
    *,
    model: str = DEFAULT_MODEL,
    agent: Agent[DeliveryAgentContext] | None = None,
    max_turns: int = 6,
    run_config: RunConfig | None = None,
) -> SafeSupportResult:
    """Run the SDK and return only an independently verified customer response."""

    support_agent = agent if agent is not None else build_support_agent(model)
    safe_run_config = (
        run_config
        if run_config is not None
        else RunConfig(
            tracing_disabled=True,
            trace_include_sensitive_data=False,
        )
    )
    request_start_index = len(context.observed_tool_requests)
    run_result = await Runner.run(
        support_agent,
        prompt,
        context=context,
        max_turns=max_turns,
        run_config=safe_run_config,
    )
    return finalize_support_response(
        run_result,
        context,
        request_start_index=request_start_index,
    )
