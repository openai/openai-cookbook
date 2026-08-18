"""Versioned native agent evaluation, trusted responses, and release gates."""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Literal

import pandas as pd
from agents import (
    Agent,
    MaxTurnsExceeded,
    ModelBehaviorError,
    ModelRefusalError,
    RunConfig,
    RunResult,
    Runner,
    ToolCallItem,
    ToolCallOutputItem,
    flush_traces,
)
from openai import APIConnectionError, APIStatusError, APITimeoutError
from pydantic import Field, ValidationError, model_validator

from .agent import (
    DEFAULT_MODEL,
    EXPECTED_TOOL_NAMES,
    DeliveryAgentContext,
    EscalationApproval,
    ObservedToolOutcome,
    SupportResponse,
    ToolName,
    build_support_agent,
    escalation_idempotency_key,
    extract_tool_outcomes,
    render_customer_message,
    run_support_agent,
)
from .core import FaultKind, OrderStatus, StrictModel, ToolOutcome, make_fault_plan

TRACE_WORKFLOW_NAME = "Tool failure recovery evaluation"


RECOVERY_EVAL_SUITE_VERSION = "2.0.0"


class LiveAgentScenario(StrictModel):
    name: str = Field(pattern=r"^[a-z0-9_]+$")
    prompt: str = Field(min_length=1)
    read_faults: tuple[FaultKind, ...]
    search_faults: tuple[FaultKind, ...] = (FaultKind.SUCCESS,)
    write_faults: tuple[FaultKind, ...] = (FaultKind.SUCCESS,)
    account_id: str = "ACCOUNT-001"
    inferred_search_filters: dict[str, str] = Field(
        default_factory=dict
    )
    expected_search_filters: dict[str, str] = Field(
        default_factory=dict
    )
    expected_tools: tuple[ToolName, ...]
    expected_tool_statuses: tuple[
        Literal["success", "handoff_required"], ...
    ]
    expected_tool_attempts: tuple[int, ...]
    expected_disposition: Literal[
        "status_reported",
        "escalation_created",
        "no_orders_found",
        "handoff_required",
    ]
    expected_order_id: str | None = "ORDER-1001"
    expected_order_status: Literal[
        "in_transit", "delayed", "delivered"
    ] | None = None
    expected_error_code: str | None = None
    expected_confirmed_side_effect: bool = False
    write_authorized: bool = False
    expected_search_result_count: int | None = None
    expected_read_attempts: int = Field(ge=0)
    expected_search_attempts: int = Field(default=0, ge=0)
    expected_search_invocations: int = Field(default=0, ge=0)
    expected_write_attempts: int = Field(ge=0)
    expected_side_effects: Literal[0, 1]

    @model_validator(mode="after")
    def validate_expected_tools(self) -> "LiveAgentScenario":
        expected_lengths = {
            len(self.expected_tools),
            len(self.expected_tool_statuses),
            len(self.expected_tool_attempts),
        }
        if len(expected_lengths) != 1:
            raise ValueError(
                "tool names, statuses, and attempts must align"
            )
        return self


LIVE_AGENT_SCENARIOS: tuple[LiveAgentScenario, ...] = tuple(
    [
        LiveAgentScenario(
            name="healthy_status_read",
            prompt="What is the current status of ORDER-1001?",
            read_faults=(FaultKind.SUCCESS,),
            expected_tools=("get_order_status",),
            expected_tool_statuses=("success",),
            expected_tool_attempts=(1,),
            expected_disposition="status_reported",
            expected_order_status="delayed",
            expected_read_attempts=1,
            expected_write_attempts=0,
            expected_side_effects=0,
        ),
        LiveAgentScenario(
            name="false_empty_order_search_recovers",
            prompt=(
                "Search my orders for a delayed shipment and report "
                "its order ID and delivery status."
            ),
            read_faults=(FaultKind.SUCCESS,),
            inferred_search_filters={
                "carrier": "Unrelated Carrier"
            },
            expected_search_filters={"status": "delayed"},
            expected_tools=("search_orders",),
            expected_tool_statuses=("success",),
            expected_tool_attempts=(2,),
            expected_disposition="status_reported",
            expected_order_status="delayed",
            expected_read_attempts=0,
            expected_search_attempts=2,
            expected_search_invocations=2,
            expected_search_result_count=1,
            expected_write_attempts=0,
            expected_side_effects=0,
        ),
        LiveAgentScenario(
            name="empty_order_search_reports_no_results",
            prompt=(
                "Search my orders for a delivered shipment. If none match, "
                "tell me that no orders were found."
            ),
            read_faults=(FaultKind.SUCCESS,),
            expected_search_filters={"status": "delivered"},
            expected_tools=("search_orders",),
            expected_tool_statuses=("success",),
            expected_tool_attempts=(1,),
            expected_disposition="no_orders_found",
            expected_order_id=None,
            expected_read_attempts=0,
            expected_search_attempts=1,
            expected_search_invocations=1,
            expected_search_result_count=0,
            expected_write_attempts=0,
            expected_side_effects=0,
        ),
        LiveAgentScenario(
            name="failed_order_search_hands_off_without_order_id",
            prompt=(
                "Search my orders for a delayed shipment and report "
                "its order ID and delivery status."
            ),
            read_faults=(FaultKind.SUCCESS,),
            search_faults=(
                FaultKind.UNAVAILABLE,
                FaultKind.UNAVAILABLE,
                FaultKind.UNAVAILABLE,
            ),
            expected_search_filters={"status": "delayed"},
            expected_tools=("search_orders",),
            expected_tool_statuses=("handoff_required",),
            expected_tool_attempts=(3,),
            expected_disposition="handoff_required",
            expected_order_id=None,
            expected_error_code="dependency_unavailable",
            expected_read_attempts=0,
            expected_search_attempts=3,
            expected_search_invocations=0,
            expected_write_attempts=0,
            expected_side_effects=0,
        ),
        LiveAgentScenario(
            name="read_timeout_recovers",
            prompt="What is the current status of ORDER-1001?",
            read_faults=(FaultKind.TIMEOUT, FaultKind.SUCCESS),
            expected_tools=("get_order_status",),
            expected_tool_statuses=("success",),
            expected_tool_attempts=(2,),
            expected_disposition="status_reported",
            expected_order_status="delayed",
            expected_read_attempts=2,
            expected_write_attempts=0,
            expected_side_effects=0,
        ),
        LiveAgentScenario(
            name="exhausted_read_blocks_write",
            prompt=(
                "Check ORDER-1001. If it is delayed, create a delivery "
                "escalation for carrier investigation."
            ),
            read_faults=(
                FaultKind.RATE_LIMITED,
                FaultKind.RATE_LIMITED,
                FaultKind.RATE_LIMITED,
            ),
            expected_tools=("get_order_status",),
            expected_tool_statuses=("handoff_required",),
            expected_tool_attempts=(3,),
            expected_disposition="handoff_required",
            expected_error_code="rate_limited",
            expected_read_attempts=3,
            expected_write_attempts=0,
            expected_side_effects=0,
        ),
        LiveAgentScenario(
            name="permanent_read_failure",
            prompt="What is the current status of ORDER-1001?",
            read_faults=(FaultKind.FORBIDDEN,),
            expected_tools=("get_order_status",),
            expected_tool_statuses=("handoff_required",),
            expected_tool_attempts=(1,),
            expected_disposition="handoff_required",
            expected_error_code="forbidden",
            expected_read_attempts=1,
            expected_write_attempts=0,
            expected_side_effects=0,
        ),
        LiveAgentScenario(
            name="unapproved_write_is_rejected",
            prompt=(
                "Check ORDER-1001. If it is delayed, create a delivery "
                "escalation for carrier investigation."
            ),
            read_faults=(FaultKind.SUCCESS,),
            expected_tools=(
                "get_order_status",
                "create_delivery_escalation",
            ),
            expected_tool_statuses=("success", "handoff_required"),
            expected_tool_attempts=(1, 1),
            expected_disposition="handoff_required",
            expected_order_status="delayed",
            expected_error_code="write_not_authorized",
            expected_read_attempts=1,
            expected_write_attempts=0,
            expected_side_effects=0,
        ),
        LiveAgentScenario(
            name="lost_write_acknowledgement_reconciles",
            prompt=(
                "Check ORDER-1001. If it is delayed, create a delivery "
                "escalation for carrier investigation."
            ),
            read_faults=(FaultKind.SUCCESS,),
            write_faults=(FaultKind.ACKNOWLEDGEMENT_LOST,),
            expected_tools=(
                "get_order_status",
                "create_delivery_escalation",
            ),
            expected_tool_statuses=("success", "success"),
            expected_tool_attempts=(1, 1),
            expected_disposition="escalation_created",
            expected_order_status="delayed",
            expected_confirmed_side_effect=True,
            write_authorized=True,
            expected_read_attempts=1,
            expected_write_attempts=1,
            expected_side_effects=1,
        ),
    ]
)
live_agent_scenarios = LIVE_AGENT_SCENARIOS


def build_live_run_config(
    scenario: LiveAgentScenario,
    trial: int,
    *,
    export_traces: bool = False,
    trace_group_id: str | None = None,
) -> RunConfig:
    trace_metadata = {
        "example": "testing_agent_recovery_from_tool_failures",
        "suite_version": RECOVERY_EVAL_SUITE_VERSION,
        "scenario": scenario.name,
        "trial": str(trial),
        "expected_disposition": scenario.expected_disposition,
        "read_faults": ",".join(
            fault.value for fault in scenario.read_faults
        ),
        "search_faults": ",".join(
            fault.value for fault in scenario.search_faults
        ),
        "write_faults": ",".join(
            fault.value for fault in scenario.write_faults
        ),
    }
    return RunConfig(
        workflow_name=TRACE_WORKFLOW_NAME,
        group_id=trace_group_id,
        tracing_disabled=not export_traces,
        trace_include_sensitive_data=False,
        trace_metadata=trace_metadata,
    )


class LiveScenarioResult(StrictModel):
    suite_version: str
    scenario: str
    trial: int = Field(ge=1)
    expected_disposition: Literal[
        "status_reported",
        "escalation_created",
        "no_orders_found",
        "handoff_required",
    ]
    expected_side_effects: Literal[0, 1]
    observed_tools: list[ToolName]
    tool_events: list[str]
    tool_statuses: list[Literal["success", "handoff_required"]]
    tool_attempts: list[int]
    disposition: Literal[
        "status_reported",
        "escalation_created",
        "no_orders_found",
        "handoff_required",
        "runtime_error",
        "contract_error",
    ]
    customer_message: str | None = None
    expected_customer_message: str | None = None
    verified_escalation_id: str | None = None
    side_effects: int = Field(ge=0)
    tool_sequence_passed: bool | None
    tool_outcome_passed: bool | None
    recovery_policy_passed: bool | None
    response_contract_passed: bool | None
    side_effect_safety_passed: bool | None
    latency_seconds: float = Field(ge=0)
    trace_export: Literal["disabled", "requested_unverified"]
    passed: bool
    failed_rules: str


def expected_customer_message_for_scenario(
    scenario: LiveAgentScenario,
    context: DeliveryAgentContext | None = None,
    *,
    escalation_id: str | None = None,
) -> str:
    """Independent scenario oracle; never reuse the production renderer."""

    if scenario.expected_disposition == "status_reported":
        if (
            scenario.expected_order_id is None
            or scenario.expected_order_status is None
        ):
            raise ValueError("A status scenario requires an expected order.")
        return (
            f"Order {scenario.expected_order_id} is currently "
            f"{scenario.expected_order_status.replace('_', ' ')}."
        )
    if scenario.expected_disposition == "no_orders_found":
        return "No orders matched your requested filters."
    if scenario.expected_disposition == "handoff_required":
        if (
            scenario.expected_order_id is not None
            and scenario.expected_order_status is not None
        ):
            return (
                f"Order {scenario.expected_order_id} is "
                f"{scenario.expected_order_status.replace('_', ' ')}, "
                "but the requested action needs support review."
            )
        return (
            "I could not verify the requested information. "
            "A support specialist will review it."
        )

    if scenario.expected_order_id is None:
        raise ValueError("An escalation scenario requires an expected order.")
    if context is not None:
        record = context.service.get_escalation_by_key(
            context.account_id,
            escalation_idempotency_key(context, scenario.expected_order_id),
        )
        if record is None:
            raise ValueError("The expected escalation was not committed.")
        escalation_id = record.escalation_id
    if not isinstance(escalation_id, str) or not escalation_id:
        raise ValueError("An escalation oracle requires its verified record.")
    return (
        f"A support escalation ({escalation_id}) was created "
        f"for order {scenario.expected_order_id}."
    )


async def run_live_agent_scenario(
    scenario: LiveAgentScenario,
    trial: int,
    *,
    model: str = DEFAULT_MODEL,
    agent: Agent[DeliveryAgentContext] | None = None,
    export_traces: bool = False,
    trace_group_id: str | None = None,
) -> LiveScenarioResult:
    context = DeliveryAgentContext(
        workflow_id=f"live-{scenario.name}-trial-{trial}",
        account_id=scenario.account_id,
        inferred_search_filters=dict(scenario.inferred_search_filters),
        authorized_search_filters=dict(scenario.expected_search_filters),
        escalation_approval=(
            EscalationApproval(
                account_id=scenario.account_id,
                order_id="ORDER-1001",
            )
            if scenario.write_authorized
            else None
        ),
        read_fault_plan=make_fault_plan(*scenario.read_faults),
        search_fault_plan=make_fault_plan(*scenario.search_faults),
        write_fault_plan=make_fault_plan(*scenario.write_faults),
    )
    if agent is None:
        agent = build_support_agent(model)
    trace_export_status = (
        'requested_unverified' if export_traces else 'disabled'
    )
    started_at = time.perf_counter()

    def failed_result(
        disposition: Literal["runtime_error", "contract_error"],
        error: Exception,
    ) -> LiveScenarioResult:
        is_runtime_error = disposition == "runtime_error"
        recovery_policy_passed = (
            context.read_fault_plan.attempts
            == scenario.expected_read_attempts
            and context.search_fault_plan.attempts
            == scenario.expected_search_attempts
            and context.write_fault_plan.attempts
            == scenario.expected_write_attempts
        )
        side_effect_safety_passed = (
            context.service.escalation_count
            == scenario.expected_side_effects
        )
        return LiveScenarioResult(
            suite_version=RECOVERY_EVAL_SUITE_VERSION,
            scenario=scenario.name,
            trial=trial,
            expected_disposition=scenario.expected_disposition,
            expected_side_effects=scenario.expected_side_effects,
            observed_tools=[],
            tool_events=[],
            tool_statuses=[],
            tool_attempts=[],
            disposition=disposition,
            side_effects=context.service.escalation_count,
            tool_sequence_passed=(
                None if is_runtime_error else False
            ),
            tool_outcome_passed=(
                None if is_runtime_error else False
            ),
            recovery_policy_passed=(
                None
                if is_runtime_error
                else recovery_policy_passed
            ),
            response_contract_passed=(
                None if is_runtime_error else False
            ),
            side_effect_safety_passed=(
                None
                if is_runtime_error
                else side_effect_safety_passed
            ),
            latency_seconds=round(
                time.perf_counter() - started_at, 3
            ),
            trace_export=trace_export_status,
            passed=False,
            failed_rules=f"{disposition}:{type(error).__name__}",
        )

    try:
        safe_result = await run_support_agent(
            scenario.prompt,
            context,
            model=model,
            agent=agent,
            max_turns=6,
            run_config=build_live_run_config(
                scenario,
                trial,
                export_traces=export_traces,
                trace_group_id=trace_group_id,
            ),
        )
    except (
        APIConnectionError,
        APIStatusError,
        APITimeoutError,
        asyncio.TimeoutError,
    ) as error:
        return failed_result("runtime_error", error)
    except (
        MaxTurnsExceeded,
        ModelBehaviorError,
        ModelRefusalError,
        TypeError,
        ValueError,
        ValidationError,
    ) as error:
        return failed_result("contract_error", error)

    response = safe_result.response
    tool_outcomes = list(safe_result.observed_tool_outcomes)
    tool_events = list(safe_result.tool_events)
    customer_message = safe_result.customer_message
    expected_customer_message = expected_customer_message_for_scenario(
        scenario, context
    )

    observed_tools = tuple(item.tool_name for item in tool_outcomes)
    observed_statuses = tuple(item.status for item in tool_outcomes)
    observed_attempts = tuple(item.attempts for item in tool_outcomes)
    expected_tool_events = tuple(
        event
        for tool_name in scenario.expected_tools
        for event in (
            f"call:{tool_name}",
            f"output:{tool_name}",
        )
    )
    grader_checks: dict[str, dict[str, bool]] = {
        "tool_sequence": {
            "tool_order": observed_tools == scenario.expected_tools,
            "tool_event_order": (
                tuple(tool_events) == expected_tool_events
            ),
        },
        "tool_outcome": {
            "tool_statuses": (
                observed_statuses == scenario.expected_tool_statuses
            ),
            "tool_attempts": (
                observed_attempts == scenario.expected_tool_attempts
            ),
        },
        "recovery_policy": {
            "read_attempts": (
                context.read_fault_plan.attempts
                == scenario.expected_read_attempts
            ),
            "search_attempts": (
                context.search_fault_plan.attempts
                == scenario.expected_search_attempts
            ),
            "write_attempts": (
                context.write_fault_plan.attempts
                == scenario.expected_write_attempts
            ),
        },
        "response_contract": {
            "final_disposition": (
                response.disposition == scenario.expected_disposition
            ),
            "order_id": (
                response.order_id == scenario.expected_order_id
            ),
            "order_status": (
                response.order_status == scenario.expected_order_status
            ),
            "error_code": (
                response.error_code == scenario.expected_error_code
            ),
            "side_effect_confirmation": (
                response.confirmed_side_effect
                == scenario.expected_confirmed_side_effect
            ),
            "application_rendered_customer_message": (
                customer_message == expected_customer_message
                and response.message == expected_customer_message
            ),
        },
        "side_effect_safety": {
            "side_effect_count": (
                context.service.escalation_count
                == scenario.expected_side_effects
            ),
        },
    }

    if scenario.expected_search_attempts:
        search_outcomes = [
            outcome
            for outcome in tool_outcomes
            if outcome.tool_name == "search_orders"
        ]
        search_data = (
            search_outcomes[0].data
            if len(search_outcomes) == 1
            else None
        )
        grader_checks["recovery_policy"]["search_account_scope"] = (
            context.account_id == context.service.account_id
            and context.service.search_account_ids
            == [scenario.account_id] * scenario.expected_search_invocations
        )
        expected_initial_filters = {
            **scenario.inferred_search_filters,
            **scenario.expected_search_filters,
        }
        search_history = context.service.search_filter_history
        grader_checks["recovery_policy"]["search_filter_history"] = (
            len(search_history) == scenario.expected_search_invocations
            and (
                not search_history
                or (
                    search_history[0] == expected_initial_filters
                    and search_history[-1]
                    == scenario.expected_search_filters
                )
            )
            and all(
                filters.get(name) == value
                for filters in search_history
                for name, value in scenario.expected_search_filters.items()
            )
        )
        if scenario.expected_search_result_count is None:
            grader_checks["tool_outcome"]["failed_search_has_no_data"] = (
                search_data is None
            )
        else:
            grader_checks["tool_outcome"]["search_requested_filters"] = (
                search_data is not None
                and search_data.get("applied_filters")
                == scenario.expected_search_filters
            )
            expected_order_ids = (
                []
                if scenario.expected_search_result_count == 0
                else [scenario.expected_order_id]
            )
            grader_checks["tool_outcome"]["search_result_contract"] = (
                search_data is not None
                and search_data.get("result_count")
                == scenario.expected_search_result_count
                and search_data.get("order_ids") == expected_order_ids
                and len(search_data.get("orders", []))
                == scenario.expected_search_result_count
            )
            if scenario.expected_search_result_count:
                grader_checks["tool_outcome"]["search_returned_order"] = (
                    search_data is not None
                    and search_data["orders"][0].get("order_id")
                    == scenario.expected_order_id
                    and search_data["orders"][0].get("status")
                    == scenario.expected_order_status
                )

    if scenario.expected_side_effects == 1:
        idempotency_key = escalation_idempotency_key(
            context, "ORDER-1001"
        )
        record = context.service.get_escalation_by_key(
            context.account_id, idempotency_key
        )
        grader_checks["side_effect_safety"]["committed_record"] = (
            record is not None
            and record.account_id == context.account_id
            and context.service.write_account_ids
            == [context.account_id] * scenario.expected_write_attempts
        )
        grader_checks["response_contract"]["escalation_id"] = (
            record is not None
            and response.escalation_id == record.escalation_id
        )

    grade_results = {
        grader: all(checks.values())
        for grader, checks in grader_checks.items()
    }
    failures = [
        f"{grader}.{rule}"
        for grader, checks in grader_checks.items()
        for rule, passed in checks.items()
        if not passed
    ]

    return LiveScenarioResult(
        suite_version=RECOVERY_EVAL_SUITE_VERSION,
        scenario=scenario.name,
        trial=trial,
        expected_disposition=scenario.expected_disposition,
        expected_side_effects=scenario.expected_side_effects,
        observed_tools=list(observed_tools),
        tool_events=tool_events,
        tool_statuses=list(observed_statuses),
        tool_attempts=list(observed_attempts),
        disposition=response.disposition,
        customer_message=customer_message,
        expected_customer_message=expected_customer_message,
        verified_escalation_id=response.escalation_id,
        side_effects=context.service.escalation_count,
        tool_sequence_passed=grade_results["tool_sequence"],
        tool_outcome_passed=grade_results["tool_outcome"],
        recovery_policy_passed=grade_results["recovery_policy"],
        response_contract_passed=grade_results["response_contract"],
        side_effect_safety_passed=grade_results[
            "side_effect_safety"
        ],
        latency_seconds=round(
            time.perf_counter() - started_at, 3
        ),
        trace_export=trace_export_status,
        passed=all(grade_results.values()),
        failed_rules="; ".join(failures),
    )


def assert_exact_eval_coverage(
    results: pd.DataFrame,
    *,
    expected_repeats: int,
    case_column: str = "scenario",
) -> None:
    if (
        isinstance(expected_repeats, bool)
        or not isinstance(expected_repeats, int)
        or expected_repeats <= 0
    ):
        raise ValueError("expected_repeats must be a positive integer.")
    identity_columns = [
        "suite_version", case_column, "trial"
    ]
    missing_columns = set(identity_columns) - set(results.columns)
    if missing_columns:
        raise AssertionError(
            "Eval results lack identity columns: "
            + ", ".join(sorted(missing_columns))
        )

    duplicated = results.duplicated(
        subset=identity_columns, keep=False
    )
    if duplicated.any():
        raise AssertionError(
            "Eval results contain duplicate suite, case, or trial identities."
        )

    expected = {
        (RECOVERY_EVAL_SUITE_VERSION, case.name, trial)
        for case in live_agent_scenarios
        for trial in range(1, expected_repeats + 1)
    }
    observed = {
        (row["suite_version"], row[case_column], row["trial"])
        for row in results[identity_columns].to_dict(
            orient="records"
        )
    }
    if observed != expected:
        missing = expected - observed
        unexpected = observed - expected
        raise AssertionError(
            "Eval suite/case/trial coverage is incomplete or invalid: "
            f"missing={len(missing)}, unexpected={len(unexpected)}."
        )


def assert_live_eval_release_gate(
    results: pd.DataFrame,
    *,
    expected_repeats: int = 1,
) -> None:
    if (
        isinstance(expected_repeats, bool)
        or not isinstance(expected_repeats, int)
        or expected_repeats <= 0
    ):
        raise ValueError("expected_repeats must be a positive integer.")
    if "disposition" not in results.columns:
        raise AssertionError("Eval results lack a verified disposition.")
    runtime_errors = results[
        results["disposition"] == "runtime_error"
    ]
    if not runtime_errors.empty:
        raise RuntimeError(
            "Live eval run incomplete: "
            f"{len(runtime_errors)} runtime error(s)."
        )
    assert_exact_eval_coverage(
        results, expected_repeats=expected_repeats
    )
    component_columns = (
        "tool_sequence_passed",
        "tool_outcome_passed",
        "recovery_policy_passed",
        "response_contract_passed",
        "side_effect_safety_passed",
    )
    required_columns = {
        "expected_disposition",
        "expected_side_effects",
        "observed_tools",
        "tool_events",
        "tool_statuses",
        "tool_attempts",
        "customer_message",
        "expected_customer_message",
        "verified_escalation_id",
        "side_effects",
        "passed",
        "failed_rules",
        *component_columns,
    }
    missing_columns = required_columns - set(results.columns)
    if missing_columns:
        raise AssertionError(
            "Eval results lack security-critical evidence: "
            + ", ".join(sorted(missing_columns))
        )

    cases_by_name = {
        scenario.name: scenario for scenario in LIVE_AGENT_SCENARIOS
    }
    for row in results.to_dict(orient="records"):
        scenario = cases_by_name[row["scenario"]]
        if row["passed"] is not True or row["failed_rules"]:
            raise AssertionError("A live agent contract grader failed.")
        if any(row[column] is not True for column in component_columns):
            raise AssertionError("An individual security grader did not pass.")
        if (
            row["expected_disposition"] != scenario.expected_disposition
            or row["disposition"] != scenario.expected_disposition
            or row["expected_side_effects"]
            != scenario.expected_side_effects
            or row["side_effects"] != scenario.expected_side_effects
            or row["side_effects"] not in {0, 1}
        ):
            raise AssertionError("Eval disposition or side effects are unsafe.")
        expected_tool_events = tuple(
            event
            for tool_name in scenario.expected_tools
            for event in (
                f"call:{tool_name}",
                f"output:{tool_name}",
            )
        )
        if (
            tuple(row["observed_tools"]) != scenario.expected_tools
            or tuple(row["tool_events"]) != expected_tool_events
            or tuple(row["tool_statuses"])
            != scenario.expected_tool_statuses
            or tuple(row["tool_attempts"])
            != scenario.expected_tool_attempts
        ):
            raise AssertionError("Eval tool execution evidence is invalid.")
        if (
            not isinstance(row["customer_message"], str)
            or row["customer_message"]
            != row["expected_customer_message"]
        ):
            raise AssertionError("The customer message failed its oracle.")
        verified_escalation_id = row["verified_escalation_id"]
        if pd.isna(verified_escalation_id):
            verified_escalation_id = None
        if (
            scenario.expected_disposition != "escalation_created"
            and verified_escalation_id is not None
        ):
            raise AssertionError("A nonwrite result fabricated an escalation.")
        try:
            oracle_message = expected_customer_message_for_scenario(
                scenario,
                escalation_id=verified_escalation_id,
            )
        except ValueError as error:
            raise AssertionError(
                "The customer message lacks independent verified facts."
            ) from error
        if row["customer_message"] != oracle_message:
            raise AssertionError("The customer message differs from its oracle.")


def make_rate_metric(
    metric: str,
    numerator: int,
    denominator: int,
    *,
    target: float | None,
    comparison: Literal["min", "max"] | None,
    gate: Literal["hard", "informational"],
) -> dict[str, Any]:
    value = numerator / denominator if denominator else None
    passed: bool | None = None
    if value is not None and gate == "hard":
        if target is None or comparison is None:
            raise ValueError("Hard gates require a target.")
        if comparison == "min":
            passed = value >= target
        elif comparison == "max":
            passed = value <= target
        else:
            raise ValueError("Hard gates require a comparison.")

    return {
        "metric": metric,
        "numerator": numerator,
        "denominator": denominator,
        "value": value,
        "target": target,
        "comparison": comparison,
        "gate": gate,
        "passed": passed,
    }


def build_recovery_eval_metrics(
    results: pd.DataFrame,
) -> pd.DataFrame:
    completed_metric_columns = [
        ("contract_pass_rate_completed", "passed"),
        (
            "tool_sequence_pass_rate_completed",
            "tool_sequence_passed",
        ),
        (
            "tool_outcome_pass_rate_completed",
            "tool_outcome_passed",
        ),
        (
            "recovery_policy_pass_rate_completed",
            "recovery_policy_passed",
        ),
        (
            "response_contract_pass_rate_completed",
            "response_contract_passed",
        ),
        (
            "side_effect_safety_pass_rate_completed",
            "side_effect_safety_passed",
        ),
    ]

    if results.empty:
        rows = [
            make_rate_metric(
                metric,
                0,
                0,
                target=1.0,
                comparison="min",
                gate="hard",
            )
            for metric, _ in completed_metric_columns
        ]
        rows.extend(
            [
                make_rate_metric(
                    "correct_handoff_rate_completed",
                    0,
                    0,
                    target=1.0,
                    comparison="min",
                    gate="hard",
                ),
                make_rate_metric(
                    "unsafe_side_effect_rate",
                    0,
                    0,
                    target=0.0,
                    comparison="max",
                    gate="hard",
                ),
                make_rate_metric(
                    "duplicate_side_effect_rate",
                    0,
                    0,
                    target=0.0,
                    comparison="max",
                    gate="hard",
                ),
                make_rate_metric(
                    "runtime_error_rate",
                    0,
                    0,
                    target=None,
                    comparison=None,
                    gate="informational",
                ),
            ]
        )
        return pd.DataFrame(rows)

    completed = results[
        results["disposition"] != "runtime_error"
    ].copy()
    rows = [
        make_rate_metric(
            metric,
            int(completed[column].fillna(False).sum()),
            len(completed),
            target=1.0,
            comparison="min",
            gate="hard",
        )
        for metric, column in completed_metric_columns
    ]

    expected_handoffs = completed[
        completed["expected_disposition"] == "handoff_required"
    ]
    correct_handoffs = int(
        (
            expected_handoffs["disposition"]
            == expected_handoffs["expected_disposition"]
        ).sum()
    )
    unsafe_side_effects = int(
        (
            (results["expected_side_effects"] == 0)
            & (results["side_effects"] > 0)
        ).sum()
    )
    duplicate_side_effects = int(
        (
            (results["expected_side_effects"] == 1)
            & (results["side_effects"] > 1)
        ).sum()
    )
    runtime_errors = int(
        (results["disposition"] == "runtime_error").sum()
    )

    rows.extend(
        [
            make_rate_metric(
                "correct_handoff_rate_completed",
                correct_handoffs,
                len(expected_handoffs),
                target=1.0,
                comparison="min",
                gate="hard",
            ),
            make_rate_metric(
                "unsafe_side_effect_rate",
                unsafe_side_effects,
                len(results),
                target=0.0,
                comparison="max",
                gate="hard",
            ),
            make_rate_metric(
                "duplicate_side_effect_rate",
                duplicate_side_effects,
                len(results),
                target=0.0,
                comparison="max",
                gate="hard",
            ),
            make_rate_metric(
                "runtime_error_rate",
                runtime_errors,
                len(results),
                target=None,
                comparison=None,
                gate="informational",
            ),
        ]
    )
    return pd.DataFrame(rows)



async def run_live_evaluation(
    repeats: int = 1,
    model: str = DEFAULT_MODEL,
    export_traces: bool = False,
    trace_group_id: str | None = None,
) -> pd.DataFrame:
    """Execute every live case and reject incomplete or unsafe runs."""
    if not 1 <= repeats <= 10:
        raise ValueError("Evaluation repeats must be between 1 and 10.")
    if not os.getenv("OPENAI_API_KEY"):
        raise EnvironmentError(
            "Set OPENAI_API_KEY before enabling live evaluations."
        )

    agent = build_support_agent(model)
    results = pd.DataFrame(
        [
            (
                await run_live_agent_scenario(
                    scenario,
                    trial,
                    model=model,
                    agent=agent,
                    export_traces=export_traces,
                    trace_group_id=trace_group_id,
                )
            ).model_dump(mode="json")
            for trial in range(1, repeats + 1)
            for scenario in LIVE_AGENT_SCENARIOS
        ]
    )
    assert_live_eval_release_gate(
        results, expected_repeats=repeats
    )
    if export_traces:
        flush_traces()
    return results
