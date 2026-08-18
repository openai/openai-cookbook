"""Explicit offline security regressions for the SDK integration boundary."""

from __future__ import annotations

import asyncio

import pandas as pd
from agents import AgentOutputSchema
from pydantic import ValidationError

from .agent import (
    DEFAULT_MODEL,
    SUPPORT_AGENT_INSTRUCTIONS,
    TOOL_TIMEOUT_SECONDS,
    DeliveryAgentContext,
    EscalationApproval,
    SupportResponse,
    build_escalation_request,
    build_support_agent,
    create_delivery_escalation_operation,
    create_delivery_escalation_tool,
    format_overall_tool_timeout,
    get_order_status_operation,
    get_order_status_tool,
    search_orders_operation,
    search_orders_tool,
    serialize_outcome,
)
from .core import (
    EscalationRequest,
    FaultKind,
    FaultPlan,
    FaultStep,
    ToolOutcome,
    make_slow_then_success_plan,
)
from .evals import (
    LIVE_AGENT_SCENARIOS,
    RECOVERY_EVAL_SUITE_VERSION,
    ObservedToolOutcome,
    assert_exact_eval_coverage,
    assert_live_eval_release_gate,
    render_customer_message,
)


async def run_security_checks(
    model: str = DEFAULT_MODEL,
) -> pd.DataFrame:
    """Run SDK authorization, privacy, rendering, and coverage regressions."""
    MODEL = model
    support_agent = build_support_agent(model)
    live_agent_scenarios = LIVE_AGENT_SCENARIOS

    tool_test_context = DeliveryAgentContext(
        read_fault_plan=make_slow_then_success_plan(delay_seconds=0.05),
        attempt_timeout_seconds=0.01,
    )
    tool_read_outcome = await get_order_status_operation(
        tool_test_context, "ORDER-1001"
    )
    assert tool_read_outcome.status == "success"
    assert tool_read_outcome.attempts == 2
    assert tool_read_outcome.events[0].error_code == "timeout"
    assert ToolOutcome.model_validate_json(
        serialize_outcome(tool_read_outcome)
    ) == tool_read_outcome

    tool_write_context = DeliveryAgentContext(
        escalation_approval=EscalationApproval(
            account_id="ACCOUNT-001", order_id="ORDER-1001"
        ),
        write_fault_plan=make_slow_then_success_plan(delay_seconds=0.05),
        attempt_timeout_seconds=0.01,
    )
    tool_write_request = build_escalation_request(
        tool_write_context,
        "ORDER-1001",
        "The delayed shipment needs carrier investigation.",
    )
    assert tool_write_context.escalation_approval is not None
    assert tool_write_request.idempotency_key == (
        "delivery-escalation:ORDER-1001:"
        + tool_write_context.escalation_approval.operation_id
    )
    assert tool_write_request.account_id == "ACCOUNT-001"
    verified_write_read = await get_order_status_operation(
        tool_write_context, "ORDER-1001"
    )
    assert verified_write_read.status == "success"
    tool_write_outcome = await create_delivery_escalation_operation(
        tool_write_context, tool_write_request
    )
    assert tool_write_outcome.status == "success"
    assert tool_write_outcome.attempts == 2
    assert tool_write_outcome.events[0].error_code == "timeout"
    assert tool_write_context.service.escalation_count == 1
    assert tool_write_outcome.data is not None
    assert tool_write_outcome.data["account_id"] == "ACCOUNT-001"
    serialized_write = ToolOutcome.model_validate_json(
        serialize_outcome(tool_write_outcome)
    )
    assert serialized_write.data is not None
    assert set(serialized_write.data) == {
        "escalation_id", "order_id", "status"
    }
    assert not {
        "account_id",
        "idempotency_key",
        "workflow_id",
        "operation_id",
        "escalation_approval",
    }.intersection(serialized_write.data)
    assert tool_write_context.escalation_approval.operation_id in (
        tool_write_context.consumed_approval_ids
    )

    replayed_approval_context = DeliveryAgentContext(
        workflow_id="different-support-workflow",
        escalation_approval=tool_write_context.escalation_approval,
        service=tool_write_context.service,
    )
    await get_order_status_operation(
        replayed_approval_context, "ORDER-1001"
    )
    replayed_approval = await create_delivery_escalation_operation(
        replayed_approval_context,
        build_escalation_request(
            replayed_approval_context,
            "ORDER-1001",
            "The delayed shipment needs carrier investigation.",
        ),
    )
    assert replayed_approval.error_code == "write_approval_already_used"
    assert replayed_approval_context.write_fault_plan.attempts == 0
    assert tool_write_context.service.escalation_count == 1

    forged_operation_context = DeliveryAgentContext(
        escalation_approval=EscalationApproval(
            account_id="ACCOUNT-001", order_id="ORDER-1001"
        )
    )
    await get_order_status_operation(
        forged_operation_context, "ORDER-1001"
    )
    forged_request = build_escalation_request(
        forged_operation_context,
        "ORDER-1001",
        "The delayed shipment needs carrier investigation.",
    ).model_copy(
        update={"idempotency_key": "forged-operation-identifier"}
    )
    forged_operation = await create_delivery_escalation_operation(
        forged_operation_context, forged_request
    )
    assert forged_operation.error_code == (
        "write_approval_operation_mismatch"
    )
    assert forged_operation_context.service.escalation_count == 0

    cancellation_context = DeliveryAgentContext(
        escalation_approval=EscalationApproval(
            account_id="ACCOUNT-001", order_id="ORDER-1001"
        ),
        write_fault_plan=FaultPlan(
            [FaultStep(FaultKind.COMMIT_THEN_TIMEOUT, 0.05)]
        ),
        attempt_timeout_seconds=0.01,
    )
    await get_order_status_operation(
        cancellation_context, "ORDER-1001"
    )
    cancelled_write = asyncio.create_task(
        create_delivery_escalation_operation(
            cancellation_context,
            build_escalation_request(
                cancellation_context,
                "ORDER-1001",
                "The delayed shipment needs carrier investigation.",
            ),
        )
    )
    for _ in range(100):
        if cancellation_context.service.escalation_count:
            break
        await asyncio.sleep(0)
    else:
        raise AssertionError("The cancellation fixture never committed.")
    cancelled_write.cancel()
    try:
        await cancelled_write
    except asyncio.CancelledError:
        pass
    else:
        raise AssertionError("The parent write task must remain cancelled.")
    assert cancellation_context.service.escalation_count == 1
    assert cancellation_context.service.reconciliation_account_ids == [
        "ACCOUNT-001"
    ]
    assert not cancellation_context.inflight_write_tasks
    assert cancellation_context.write_in_progress is False

    unauthorized_write_context = DeliveryAgentContext()
    await get_order_status_operation(
        unauthorized_write_context, "ORDER-1001"
    )
    unauthorized_write = await create_delivery_escalation_operation(
        unauthorized_write_context,
        build_escalation_request(
            unauthorized_write_context,
            "ORDER-1001",
            "The delayed shipment needs carrier investigation.",
        ),
    )
    assert unauthorized_write.error_code == "write_not_authorized"
    assert unauthorized_write_context.write_fault_plan.attempts == 0
    assert unauthorized_write_context.service.escalation_count == 0

    unverified_write_context = DeliveryAgentContext(
        escalation_approval=EscalationApproval(
            account_id="ACCOUNT-001", order_id="ORDER-1001"
        )
    )
    unverified_write = await create_delivery_escalation_operation(
        unverified_write_context,
        build_escalation_request(
            unverified_write_context,
            "ORDER-1001",
            "The delayed shipment needs carrier investigation.",
        ),
    )
    assert unverified_write.error_code == "prerequisite_read_required"
    assert unverified_write_context.write_fault_plan.attempts == 0

    cross_account_request = EscalationRequest(
        account_id="ACCOUNT-002",
        order_id="ORDER-1001",
        reason="The delayed shipment needs carrier investigation.",
        idempotency_key="cross-account-rejected",
    )
    cross_account_write = await create_delivery_escalation_operation(
        tool_write_context, cross_account_request
    )
    assert cross_account_write.error_code == (
        "cross_account_write_forbidden"
    )
    assert tool_write_context.service.escalation_count == 1

    wrong_scope_context = DeliveryAgentContext(
        escalation_approval=EscalationApproval(
            account_id="ACCOUNT-002", order_id="ORDER-1001"
        )
    )
    await get_order_status_operation(wrong_scope_context, "ORDER-1001")
    wrong_scope_write = await create_delivery_escalation_operation(
        wrong_scope_context,
        build_escalation_request(
            wrong_scope_context,
            "ORDER-1001",
            "The delayed shipment needs carrier investigation.",
        ),
    )
    assert wrong_scope_write.error_code == "write_approval_scope_mismatch"
    assert wrong_scope_context.service.escalation_count == 0

    parallel_context = DeliveryAgentContext(
        escalation_approval=EscalationApproval(
            account_id="ACCOUNT-001", order_id="ORDER-1001"
        )
    )
    parallel_request = build_escalation_request(
        parallel_context,
        "ORDER-1001",
        "The delayed shipment needs carrier investigation.",
    )
    parallel_write, parallel_read = await asyncio.gather(
        create_delivery_escalation_operation(
            parallel_context, parallel_request
        ),
        get_order_status_operation(parallel_context, "ORDER-1001"),
    )
    assert parallel_write.error_code == "prerequisite_read_required"
    assert parallel_read.status == "success"
    assert parallel_context.service.escalation_count == 0

    foreign_order_context = DeliveryAgentContext()
    foreign_order_read = await get_order_status_operation(
        foreign_order_context, "ORDER-2002"
    )
    assert foreign_order_read.error_code == "forbidden"
    assert not foreign_order_context.verified_order_reads

    tool_search_context = DeliveryAgentContext(
        inferred_search_filters={"carrier": "Unrelated Carrier"}
    )
    tool_search_outcome = await search_orders_operation(
        tool_search_context, status="delayed"
    )
    assert tool_search_outcome.status == "success"
    assert tool_search_outcome.attempts == 2
    assert tool_search_context.search_fault_plan.attempts == 2
    assert tool_search_context.service.search_account_ids == [
        "ACCOUNT-001", "ACCOUNT-001"
    ]
    assert tool_search_context.service.search_filter_history == [
        {"status": "delayed", "carrier": "Unrelated Carrier"},
        {"status": "delayed"},
    ]
    assert tool_search_outcome.data is not None
    assert tool_search_outcome.data["applied_filters"] == {
        "status": "delayed"
    }
    assert tool_search_outcome.data["orders"][0]["order_id"] == (
        "ORDER-1001"
    )
    private_search_data = {
        **tool_search_outcome.data,
        "workflow_id": "private-workflow-fixture",
        "idempotency_key": "private-idempotency-fixture",
        "orders": [
            {
                **tool_search_outcome.data["orders"][0],
                "account_id": "ACCOUNT-001",
                "operation_id": "private-operation-fixture",
            }
        ],
    }
    private_search_outcome = tool_search_outcome.model_copy(
        update={"data": private_search_data}
    )
    projected_search_json = serialize_outcome(private_search_outcome)
    assert "private-workflow-fixture" not in projected_search_json
    assert "private-idempotency-fixture" not in projected_search_json
    assert "private-operation-fixture" not in projected_search_json
    assert "ACCOUNT-001" not in projected_search_json

    unauthorized_search = await search_orders_operation(
        DeliveryAgentContext(account_id="ACCOUNT-002"),
        status="delayed",
    )
    assert unauthorized_search.status == "handoff_required"
    assert unauthorized_search.error_code == "forbidden"
    assert unauthorized_search.attempts == 1

    for tool in (
        get_order_status_tool,
        search_orders_tool,
        create_delivery_escalation_tool,
    ):
        assert tool.strict_json_schema is True
        assert "ctx" not in tool.params_json_schema["properties"]

    assert get_order_status_tool.timeout_seconds == TOOL_TIMEOUT_SECONDS
    assert search_orders_tool.timeout_seconds == TOOL_TIMEOUT_SECONDS
    assert create_delivery_escalation_tool.timeout_seconds is None

    assert set(get_order_status_tool.params_json_schema["properties"]) == {
        "order_id"
    }
    assert set(search_orders_tool.params_json_schema["properties"]) == {
        "status", "carrier"
    }
    assert not {"account_id", "inferred_filters"}.intersection(
        search_orders_tool.params_json_schema["properties"]
    )
    assert not {
        "account_id",
        "escalation_approval",
        "operation_id",
        "consumed_approval_ids",
        "inflight_write_tasks",
    }.intersection(
        create_delivery_escalation_tool.params_json_schema["properties"]
    )
    assert set(
        create_delivery_escalation_tool.params_json_schema["properties"]
    ) == {"order_id", "reason"}

    from agents.tool_context import ToolContext

    timeout_json = format_overall_tool_timeout(
        ToolContext(
            tool_test_context,
            tool_name="get_order_status",
            tool_call_id="offline-timeout",
            tool_arguments="{}",
        ),
        TimeoutError(),
    )
    timeout_outcome = ToolOutcome.model_validate_json(timeout_json)
    assert timeout_outcome.status == "handoff_required"
    assert timeout_outcome.error_code == "tool_deadline_exceeded"
    assert timeout_outcome.attempts == tool_test_context.read_fault_plan.attempts
    assert timeout_outcome.events[0].operation == "get_order_status"
    assert timeout_outcome.events[0].attempt == timeout_outcome.attempts

    sdk_direct_context = DeliveryAgentContext(
        escalation_approval=EscalationApproval(
            account_id="ACCOUNT-001", order_id="ORDER-1001"
        )
    )
    sdk_write_arguments = (
        '{"order_id":"ORDER-1001",'
        '"reason":"The shipment needs carrier investigation."}'
    )
    sdk_direct_output = await create_delivery_escalation_tool.on_invoke_tool(
        ToolContext(
            sdk_direct_context,
            tool_name="create_delivery_escalation",
            tool_call_id="offline-direct-write",
            tool_arguments=sdk_write_arguments,
        ),
        sdk_write_arguments,
    )
    sdk_direct_outcome = ToolOutcome.model_validate_json(sdk_direct_output)
    assert sdk_direct_outcome.error_code == "prerequisite_read_required"
    assert sdk_direct_context.service.escalation_count == 0

    function_tool_contracts = pd.DataFrame(
        [
            {
                "tool": tool.name,
                "parameters": sorted(tool.params_json_schema["properties"]),
                "strict_schema": tool.strict_json_schema,
                "overall_timeout_seconds": tool.timeout_seconds,
            }
            for tool in (
                get_order_status_tool,
                search_orders_tool,
                create_delivery_escalation_tool,
            )
        ]
    )
    function_tool_contracts

    from agents import AgentOutputSchema


    valid_support_responses = [
        SupportResponse(
            disposition="status_reported",
            order_id="ORDER-1001",
            order_status="delayed",
            message="Order ORDER-1001 is delayed.",
        ),
        SupportResponse(
            disposition="escalation_created",
            order_id="ORDER-1001",
            escalation_id="ESC-0001",
            confirmed_side_effect=True,
            message="Escalation ESC-0001 was created.",
        ),
        SupportResponse(
            disposition="handoff_required",
            order_id="ORDER-1001",
            error_code="rate_limited",
            message="A human needs to continue this request.",
        ),
        SupportResponse(
            disposition="no_orders_found",
            message="No orders match the requested filters.",
        ),
        SupportResponse(
            disposition="handoff_required",
            error_code="dependency_unavailable",
            message="The order search needs human follow-up.",
        ),
    ]

    invalid_support_response_cases = [
        {
            "disposition": "escalation_created",
            "order_id": "ORDER-1001",
            "escalation_id": "ESC-0001",
            "message": "Escalation created.",
        },
        {
            "disposition": "handoff_required",
            "order_id": "ORDER-1001",
            "message": "A human needs to continue this request.",
        },
        {
            "disposition": "status_reported",
            "order_id": "ORDER-1001",
            "message": "The order status is available.",
            "error_code": "invalid_tool_output",
        },
        {
            "disposition": "no_orders_found",
            "order_id": "ORDER-1001",
            "message": "No matching orders.",
        },
        {
            "disposition": "status_reported",
            "order_status": "delayed",
            "message": "An order is delayed.",
        },
    ]

    for invalid_case in invalid_support_response_cases:
        try:
            SupportResponse.model_validate(invalid_case)
        except ValidationError:
            pass
        else:
            raise AssertionError(
                f"Expected SupportResponse rejection: {invalid_case}"
            )

    expected_tool_names = [
        "get_order_status",
        "search_orders",
        "create_delivery_escalation",
    ]
    assert support_agent.name == "Delivery support recovery agent"
    assert support_agent.model == MODEL
    assert support_agent.instructions == SUPPORT_AGENT_INSTRUCTIONS
    assert support_agent.output_type is SupportResponse
    assert support_agent.model_settings.store is False
    assert support_agent.model_settings.parallel_tool_calls is False
    assert [tool.name for tool in support_agent.tools] == expected_tool_names

    support_output_schema = AgentOutputSchema(SupportResponse)
    assert support_output_schema.is_strict_json_schema() is True
    assert set(support_output_schema.json_schema()["properties"]) == {
        "disposition",
        "order_id",
        "message",
        "order_status",
        "escalation_id",
        "confirmed_side_effect",
        "error_code",
    }
    for response in valid_support_responses:
        assert support_output_schema.validate_json(
            response.model_dump_json()
        ) == response

    agent_contract = pd.DataFrame(
        [
            {
                "agent": support_agent.name,
                "model": support_agent.model,
                "tools": expected_tool_names,
                "output_type": support_agent.output_type.__name__,
                "live_api_call": False,
            }
        ]
    )
    agent_contract

    adversarial_status_response = SupportResponse(
        disposition="status_reported",
        order_id="ORDER-1001",
        order_status="delayed",
        message="Your refund was approved and your shipment was delivered.",
    )
    adversarial_status_context = DeliveryAgentContext()
    verified_status_evidence = ObservedToolOutcome(
        tool_name="get_order_status",
        status="success",
        attempts=1,
        confirmed_side_effect=False,
        data=adversarial_status_context.service.orders[
            "ORDER-1001"
        ].model_dump(mode="json"),
    )
    trusted_status_message = render_customer_message(
        adversarial_status_response,
        adversarial_status_context,
        [verified_status_evidence],
    )
    assert trusted_status_message == (
        "Order ORDER-1001 is currently delayed."
    )
    assert trusted_status_message != adversarial_status_response.message

    adversarial_handoff_response = SupportResponse(
        disposition="handoff_required",
        order_id="ORDER-1001",
        error_code="write_not_authorized",
        message="Your refund and delivery escalation were completed.",
    )
    verified_handoff_evidence = ObservedToolOutcome(
        tool_name="create_delivery_escalation",
        status="handoff_required",
        attempts=1,
        confirmed_side_effect=False,
        error_code="write_not_authorized",
    )
    trusted_handoff_message = render_customer_message(
        adversarial_handoff_response,
        adversarial_status_context,
        [verified_handoff_evidence],
    )
    assert "refund" not in trusted_handoff_message.lower()
    assert "completed" not in trusted_handoff_message.lower()
    assert trusted_handoff_message != adversarial_handoff_response.message

    fabricated_escalation_response = SupportResponse(
        disposition="escalation_created",
        order_id="ORDER-1001",
        escalation_id="ESC-FAKE",
        confirmed_side_effect=True,
        message="Your escalation and refund were completed.",
    )
    fabricated_escalation_context = DeliveryAgentContext(
        escalation_approval=EscalationApproval(
            account_id="ACCOUNT-001", order_id="ORDER-1001"
        )
    )
    fabricated_write_evidence = ObservedToolOutcome(
        tool_name="create_delivery_escalation",
        status="success",
        attempts=1,
        confirmed_side_effect=True,
        data={"escalation_id": "ESC-FAKE"},
    )
    try:
        render_customer_message(
            fabricated_escalation_response,
            fabricated_escalation_context,
            [fabricated_write_evidence],
        )
    except ValueError:
        pass
    else:
        raise AssertionError(
            "An uncommitted escalation must never reach a customer."
        )


    empty_search_response = SupportResponse(
        disposition="no_orders_found",
        message="No matching orders were found.",
    )
    empty_search_evidence = ObservedToolOutcome(
        tool_name="search_orders",
        status="success",
        attempts=1,
        confirmed_side_effect=False,
        data={"result_count": 0, "order_ids": [], "orders": []},
    )
    invalid_customer_trajectories = [
        (
            adversarial_status_response,
            [verified_status_evidence, fabricated_write_evidence],
        ),
        (
            empty_search_response,
            [empty_search_evidence, fabricated_write_evidence],
        ),
        (
            adversarial_handoff_response,
            [fabricated_write_evidence, verified_handoff_evidence],
        ),
        (
            adversarial_status_response,
            [verified_status_evidence, verified_handoff_evidence],
        ),
        (
            fabricated_escalation_response,
            [fabricated_write_evidence, verified_status_evidence],
        ),
    ]
    for invalid_response, invalid_outcomes in (
        invalid_customer_trajectories
    ):
        try:
            render_customer_message(
                invalid_response,
                fabricated_escalation_context,
                invalid_outcomes,
            )
        except ValueError:
            pass
        else:
            raise AssertionError(
                "Mixed or non-terminal outcomes must not reach a customer."
            )

    runtime_gate_fixture = pd.DataFrame(
        [{"disposition": "runtime_error", "passed": False}]
    )
    try:
        assert_live_eval_release_gate(runtime_gate_fixture)
    except RuntimeError:
        pass
    else:
        raise AssertionError("Runtime errors must fail the live release gate.")


    coverage_gate_fixture = pd.DataFrame(
        [
            {
                "suite_version": RECOVERY_EVAL_SUITE_VERSION,
                "scenario": scenario.name,
                "trial": trial,
            }
            for scenario in live_agent_scenarios
            for trial in range(1, 3)
        ]
    )
    assert_exact_eval_coverage(
        coverage_gate_fixture, expected_repeats=2
    )
    for invalid_coverage in (
        coverage_gate_fixture.iloc[:-1].copy(),
        pd.concat(
            [coverage_gate_fixture.iloc[:-1], coverage_gate_fixture.iloc[[0]]],
            ignore_index=True,
        ),
        coverage_gate_fixture.assign(suite_version="unrecognized-suite"),
    ):
        try:
            assert_exact_eval_coverage(
                invalid_coverage, expected_repeats=2
            )
        except AssertionError:
            pass
        else:
            raise AssertionError(
                "Missing, duplicate, or foreign eval identities must fail."
            )

    return pd.DataFrame(
        [
            {"check": check, "passed": True}
            for check in (
                "account_scoped_reads_and_writes",
                "single_use_bound_approval",
                "cancellation_safe_reconciliation",
                "safe_search_and_output_projection",
                "strict_model_facing_tool_schemas",
                "trusted_customer_message_rendering",
                "exact_eval_coverage_and_runtime_gates",
            )
        ]
    )
