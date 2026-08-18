"""Deterministic, network-free regression coverage for recovery primitives."""

from __future__ import annotations

from typing import Any

import pandas as pd

from .core import (
    EscalationRequest,
    FaultKind,
    FaultPlan,
    FaultStep,
    PermanentToolError,
    RecoveryPolicy,
    SyntheticDeliveryService,
    ToolOutcome,
    make_fault_plan,
    make_slow_then_success_plan,
    run_order_search_with_recovery,
    run_read_with_recovery,
    run_write_with_reconciliation,
)


async def run_offline_recovery_suite() -> pd.DataFrame:
    """Run all account-scope, retry, reconciliation, and search scenarios."""
    policy = RecoveryPolicy(max_attempts=3)
    scenario_results: list[dict[str, Any]] = []

    # Verify backoff without adding real delay to the notebook.
    recorded_delays: list[float] = []


    async def record_delay(delay_seconds: float) -> None:
        recorded_delays.append(delay_seconds)


    backoff_policy = RecoveryPolicy(
        max_attempts=3, base_delay_seconds=0.25, jitter_ratio=0
    )
    backoff_result = await run_read_with_recovery(
        SyntheticDeliveryService(),
        "ACCOUNT-001",
        "ORDER-1001",
        make_fault_plan(FaultKind.TIMEOUT, FaultKind.SUCCESS),
        backoff_policy,
        sleep_fn=record_delay,
    )
    assert backoff_result.status == "success"
    assert recorded_delays == [0.25]


    class SubstitutedOrderReadService(SyntheticDeliveryService):
        def __init__(self, substituted_order_id: str) -> None:
            super().__init__()
            self.substituted_order_id = substituted_order_id

        def execute_order_status_step(
            self, account_id: str, order_id: str, step: FaultStep
        ) -> dict[str, Any]:
            super().execute_order_status_step(account_id, order_id, step)
            return self.orders[self.substituted_order_id].model_dump(
                mode="json"
            )


    read_cases = [
        {
            "name": "healthy_read",
            "faults": [FaultKind.SUCCESS],
            "status": "success",
            "error_code": None,
            "attempts": 1,
        },
        {
            "name": "timeout_then_success",
            "faults": [FaultKind.TIMEOUT, FaultKind.SUCCESS],
            "status": "success",
            "error_code": None,
            "attempts": 2,
        },
        {
            "name": "unavailable_twice_then_success",
            "faults": [
                FaultKind.UNAVAILABLE,
                FaultKind.UNAVAILABLE,
                FaultKind.SUCCESS,
            ],
            "status": "success",
            "error_code": None,
            "attempts": 3,
        },
        {
            "name": "rate_limit_budget_exhausted",
            "faults": [
                FaultKind.RATE_LIMITED,
                FaultKind.RATE_LIMITED,
                FaultKind.RATE_LIMITED,
            ],
            "status": "handoff_required",
            "error_code": "rate_limited",
            "attempts": 3,
        },
        {
            "name": "malformed_output_then_success",
            "faults": [FaultKind.MALFORMED_RESPONSE, FaultKind.SUCCESS],
            "status": "success",
            "error_code": None,
            "attempts": 2,
        },
        {
            "name": "incomplete_output_then_success",
            "faults": [FaultKind.INCOMPLETE_RESPONSE, FaultKind.SUCCESS],
            "status": "success",
            "error_code": None,
            "attempts": 2,
        },
        {
            "name": "permanent_403",
            "faults": [FaultKind.FORBIDDEN, FaultKind.SUCCESS],
            "status": "handoff_required",
            "error_code": "forbidden",
            "attempts": 1,
        },
        {
            "name": "permanent_404",
            "faults": [FaultKind.NOT_FOUND, FaultKind.SUCCESS],
            "status": "handoff_required",
            "error_code": "not_found",
            "attempts": 1,
        },
        {
            "name": "cross_account_direct_read_rejected",
            "account_id": "ACCOUNT-002",
            "faults": [FaultKind.SUCCESS],
            "status": "handoff_required",
            "error_code": "forbidden",
            "attempts": 1,
        },
        {
            "name": "foreign_order_direct_read_rejected",
            "order_id": "ORDER-2002",
            "faults": [FaultKind.SUCCESS],
            "status": "handoff_required",
            "error_code": "forbidden",
            "attempts": 1,
        },
        {
            "name": "unknown_owned_order_not_found",
            "order_id": "ORDER-9999",
            "faults": [FaultKind.SUCCESS],
            "status": "handoff_required",
            "error_code": "order_not_found",
            "attempts": 1,
        },
        {
            "name": "shape_valid_wrong_order_response_rejected",
            "substituted_order_id": "ORDER-2002",
            "faults": [FaultKind.SUCCESS],
            "status": "handoff_required",
            "error_code": "unexpected_order_identity",
            "attempts": 1,
        },
    ]

    for case in read_cases:
        service = (
            SubstitutedOrderReadService(case["substituted_order_id"])
            if "substituted_order_id" in case
            else SyntheticDeliveryService()
        )
        result = await run_read_with_recovery(
            service,
            case.get("account_id", "ACCOUNT-001"),
            case.get("order_id", "ORDER-1001"),
            make_fault_plan(*case["faults"]),
            policy,
        )
        assert result.status == case["status"], case["name"]
        assert result.error_code == case["error_code"], case["name"]
        assert result.attempts == case["attempts"], case["name"]
        assert len(result.events) == result.attempts, case["name"]
        if result.status == "handoff_required":
            assert result.events[-1].retryable is False, case["name"]
        scenario_results.append(
            {
                "scenario": case["name"],
                "status": result.status,
                "error_code": result.error_code,
                "attempts": result.attempts,
                "side_effects": 0,
                "passed": True,
            }
        )

    # A real wall-clock deadline becomes a retryable timeout event.
    service = SyntheticDeliveryService()
    deadline_recovery = await run_read_with_recovery(
        service,
        "ACCOUNT-001",
        "ORDER-1001",
        make_slow_then_success_plan(delay_seconds=0.05),
        policy,
        attempt_timeout_seconds=0.01,
    )
    assert deadline_recovery.status == "success"
    assert deadline_recovery.attempts == 2
    assert deadline_recovery.events[0].fault_kind == "slow_response"
    assert deadline_recovery.events[0].error_code == "timeout"
    scenario_results.append(
        {
            "scenario": "wall_clock_timeout_then_success",
            "status": deadline_recovery.status,
            "error_code": deadline_recovery.error_code,
            "attempts": deadline_recovery.attempts,
            "side_effects": 0,
            "passed": True,
        }
    )


    # A pre-commit timeout is reconciled, then retried with the same key.
    service = SyntheticDeliveryService()
    request = EscalationRequest(
        account_id="ACCOUNT-001",
        order_id="ORDER-1001",
        reason="The delayed shipment needs carrier investigation.",
        idempotency_key="order-1001-carrier-investigation",
    )
    write_after_timeout = await run_write_with_reconciliation(
        service,
        "ACCOUNT-001",
        request,
        make_fault_plan(FaultKind.TIMEOUT, FaultKind.SUCCESS),
        policy,
        write_authorized=True,
    )
    assert write_after_timeout.status == "success"
    assert write_after_timeout.attempts == 2
    assert write_after_timeout.events[0].retryable is True
    assert write_after_timeout.events[0].side_effect_committed is False
    assert service.escalation_count == 1
    scenario_results.append(
        {
            "scenario": "write_timeout_then_success",
            "status": write_after_timeout.status,
            "error_code": write_after_timeout.error_code,
            "attempts": write_after_timeout.attempts,
            "side_effects": service.escalation_count,
            "passed": True,
        }
    )

    # A lost acknowledgement is reconciled without replaying the write.
    service = SyntheticDeliveryService()
    acknowledgement_lost = await run_write_with_reconciliation(
        service,
        "ACCOUNT-001",
        request,
        make_fault_plan(FaultKind.ACKNOWLEDGEMENT_LOST),
        policy,
        write_authorized=True,
    )
    assert acknowledgement_lost.status == "success"
    assert acknowledgement_lost.confirmed_side_effect is True
    assert acknowledgement_lost.attempts == 1
    assert acknowledgement_lost.events[0].result == "reconciled"
    assert acknowledgement_lost.events[0].side_effect_committed is True
    assert service.escalation_count == 1

    scenario_results.append(
        {
            "scenario": "ack_lost_without_duplicate",
            "status": acknowledgement_lost.status,
            "error_code": acknowledgement_lost.error_code,
            "attempts": acknowledgement_lost.attempts,
            "side_effects": service.escalation_count,
            "passed": True,
        }
    )

    # Invalid write output is also reconciled against the committed record.
    service = SyntheticDeliveryService()
    invalid_write_output = await run_write_with_reconciliation(
        service,
        "ACCOUNT-001",
        request,
        make_fault_plan(FaultKind.MALFORMED_RESPONSE),
        policy,
        write_authorized=True,
    )
    assert invalid_write_output.status == "success"
    assert invalid_write_output.attempts == 1
    assert invalid_write_output.events[0].result == "reconciled_invalid_output"
    assert service.escalation_count == 1
    scenario_results.append(
        {
            "scenario": "invalid_write_output_reconciled",
            "status": invalid_write_output.status,
            "error_code": invalid_write_output.error_code,
            "attempts": invalid_write_output.attempts,
            "side_effects": service.escalation_count,
            "passed": True,
        }
    )

    # Reusing a key for different inputs fails closed.
    service = SyntheticDeliveryService()
    first_write = await run_write_with_reconciliation(
        service,
        "ACCOUNT-001",
        request,
        make_fault_plan(FaultKind.SUCCESS),
        policy,
        write_authorized=True,
    )
    conflicting_request = request.model_copy(
        update={"reason": "Use the same key for a different investigation."}
    )
    key_conflict = await run_write_with_reconciliation(
        service,
        "ACCOUNT-001",
        conflicting_request,
        make_fault_plan(FaultKind.SUCCESS),
        policy,
        write_authorized=True,
    )
    assert first_write.status == "success"
    assert key_conflict.status == "handoff_required"
    assert key_conflict.error_code == "idempotency_key_conflict"
    assert key_conflict.attempts == 1
    assert service.escalation_count == 1
    scenario_results.append(
        {
            "scenario": "idempotency_key_conflict",
            "status": key_conflict.status,
            "error_code": key_conflict.error_code,
            "attempts": key_conflict.attempts,
            "side_effects": service.escalation_count,
            "passed": True,
        }
    )

    security_scenario_names: set[str] = set()


    def record_security_scenario(
        name: str,
        outcome: ToolOutcome,
        service: SyntheticDeliveryService,
    ) -> None:
        assert name not in security_scenario_names, name
        security_scenario_names.add(name)
        scenario_results.append(
            {
                "scenario": name,
                "status": outcome.status,
                "error_code": outcome.error_code,
                "attempts": outcome.attempts,
                "side_effects": service.escalation_count,
                "passed": True,
            }
        )


    authorization_cases = [
        {
            "name": "write_without_application_approval",
            "authorized": False,
            "error_code": "write_not_authorized",
            "dependency_attempts": 0,
        },
        {
            "name": "cross_account_write_rejected",
            "account_id": "ACCOUNT-002",
            "request_account_id": "ACCOUNT-002",
            "error_code": "forbidden",
            "dependency_attempts": 1,
        },
        {
            "name": "foreign_order_write_rejected",
            "order_id": "ORDER-2002",
            "error_code": "forbidden",
            "dependency_attempts": 1,
        },
        {
            "name": "spoofed_request_account_rejected",
            "request_account_id": "ACCOUNT-002",
            "error_code": "forbidden",
            "dependency_attempts": 0,
        },
    ]
    for case in authorization_cases:
        service = SyntheticDeliveryService()
        write_plan = make_fault_plan(FaultKind.SUCCESS)
        case_request = request.model_copy(
            update={
                "account_id": case.get(
                    "request_account_id", "ACCOUNT-001"
                ),
                "order_id": case.get("order_id", "ORDER-1001"),
            }
        )
        outcome = await run_write_with_reconciliation(
            service,
            case.get("account_id", "ACCOUNT-001"),
            case_request,
            write_plan,
            policy,
            write_authorized=case.get("authorized", True),
        )
        assert outcome.status == "handoff_required", case["name"]
        assert outcome.error_code == case["error_code"], case["name"]
        assert outcome.attempts == 1, case["name"]
        assert write_plan.attempts == (
            case["dependency_attempts"]
        ), case["name"]
        assert service.escalation_count == 0, case["name"]
        record_security_scenario(case["name"], outcome, service)

    # Approval and an earlier read cannot override current service state.
    for current_status in ("in_transit", "delivered"):
        service = SyntheticDeliveryService()
        previously_verified = await run_read_with_recovery(
            service,
            "ACCOUNT-001",
            "ORDER-1001",
            make_fault_plan(FaultKind.SUCCESS),
            policy,
        )
        assert previously_verified.data is not None
        assert previously_verified.data["status"] == "delayed"
        service.orders["ORDER-1001"] = (
            service.orders["ORDER-1001"].model_copy(
                update={"status": current_status}
            )
        )
        write_plan = make_fault_plan(FaultKind.SUCCESS)
        outcome = await run_write_with_reconciliation(
            service,
            "ACCOUNT-001",
            request,
            write_plan,
            policy,
            write_authorized=True,
        )
        assert outcome.status == "handoff_required"
        assert outcome.error_code == "write_precondition_failed"
        assert outcome.attempts == 1
        assert write_plan.attempts == 1
        assert service.escalation_count == 0
        record_security_scenario(
            f"stale_delayed_read_rejects_{current_status}_write",
            outcome,
            service,
        )

    # An exact replay remains safe after its already-committed order changes.
    service = SyntheticDeliveryService()
    original_commit = await run_write_with_reconciliation(
        service,
        "ACCOUNT-001",
        request,
        make_fault_plan(FaultKind.SUCCESS),
        policy,
        write_authorized=True,
    )
    assert original_commit.status == "success"
    service.orders["ORDER-1001"] = (
        service.orders["ORDER-1001"].model_copy(
            update={"status": "delivered"}
        )
    )
    safe_replay = await run_write_with_reconciliation(
        service,
        "ACCOUNT-001",
        request,
        make_fault_plan(FaultKind.SUCCESS),
        policy,
        write_authorized=True,
    )
    assert safe_replay.status == "success"
    assert service.escalation_count == 1
    record_security_scenario(
        "exact_idempotent_replay_survives_order_status_change",
        safe_replay,
        service,
    )
    new_operation = request.model_copy(
        update={"idempotency_key": "a-second-delivery-operation"}
    )
    stale_new_operation = await run_write_with_reconciliation(
        service,
        "ACCOUNT-001",
        new_operation,
        make_fault_plan(FaultKind.SUCCESS),
        policy,
        write_authorized=True,
    )
    assert stale_new_operation.status == "handoff_required"
    assert stale_new_operation.error_code == "write_precondition_failed"
    assert service.escalation_count == 1
    record_security_scenario(
        "new_operation_rechecks_delivered_order",
        stale_new_operation,
        service,
    )


    class OrderChangesOnRetryService(SyntheticDeliveryService):
        def execute_escalation_step(
            self,
            account_id: str,
            request: EscalationRequest,
            step: FaultStep,
        ) -> dict[str, Any]:
            if step.kind == FaultKind.SUCCESS:
                self.orders[request.order_id] = (
                    self.orders[request.order_id].model_copy(
                        update={"status": "delivered"}
                    )
                )
            return super().execute_escalation_step(
                account_id, request, step
            )


    service = OrderChangesOnRetryService()
    retry_write_plan = make_fault_plan(
        FaultKind.TIMEOUT, FaultKind.SUCCESS
    )
    changed_during_retry = await run_write_with_reconciliation(
        service,
        "ACCOUNT-001",
        request,
        retry_write_plan,
        policy,
        write_authorized=True,
    )
    assert changed_during_retry.status == "handoff_required"
    assert changed_during_retry.error_code == "write_precondition_failed"
    assert changed_during_retry.attempts == 2
    assert retry_write_plan.attempts == 2
    assert service.escalation_count == 0
    record_security_scenario(
        "retry_rechecks_current_order_status",
        changed_during_retry,
        service,
    )


    # A pre-commit failure cannot turn another request's record into success.
    for collision_fault in (
        FaultKind.TIMEOUT,
        FaultKind.RATE_LIMITED,
        FaultKind.UNAVAILABLE,
    ):
        service = SyntheticDeliveryService()
        initial_commit = await run_write_with_reconciliation(
            service,
            "ACCOUNT-001",
            request,
            make_fault_plan(FaultKind.SUCCESS),
            policy,
            write_authorized=True,
        )
        assert initial_commit.status == "success"
        collision_plan = make_fault_plan(
            collision_fault, FaultKind.SUCCESS
        )
        lookup_plan = make_fault_plan(FaultKind.SUCCESS)
        collision_outcome = await run_write_with_reconciliation(
            service,
            "ACCOUNT-001",
            conflicting_request,
            collision_plan,
            policy,
            write_authorized=True,
            reconciliation_fault_plan=lookup_plan,
        )
        assert collision_outcome.status == "handoff_required"
        assert collision_outcome.error_code == (
            "idempotency_key_conflict"
        )
        assert collision_outcome.attempts == 1
        assert collision_plan.attempts == 1
        assert lookup_plan.attempts == 1
        assert service.escalation_count == 1
        record_security_scenario(
            f"idempotency_collision_after_{collision_fault.value}",
            collision_outcome,
            service,
        )

    # An unavailable authority makes a committed write unresolved, never replayed.
    reconciliation_failure_cases = [
        (
            "reconciliation_unavailable_after_commit",
            make_fault_plan(FaultKind.UNAVAILABLE),
            1.0,
            "reconciliation_dependency_unavailable",
        ),
        (
            "reconciliation_timeout_after_commit",
            make_fault_plan(FaultKind.TIMEOUT),
            1.0,
            "reconciliation_timeout",
        ),
        (
            "reconciliation_deadline_after_commit",
            make_slow_then_success_plan(0.05),
            0.01,
            "reconciliation_timeout",
        ),
        (
            "reconciliation_invalid_output_after_commit",
            make_fault_plan(FaultKind.MALFORMED_RESPONSE),
            1.0,
            "reconciliation_invalid_tool_output",
        ),
    ]
    for name, lookup_plan, lookup_timeout, lookup_error in (
        reconciliation_failure_cases
    ):
        service = SyntheticDeliveryService()
        write_plan = make_fault_plan(
            FaultKind.ACKNOWLEDGEMENT_LOST, FaultKind.SUCCESS
        )
        outcome = await run_write_with_reconciliation(
            service,
            "ACCOUNT-001",
            request,
            write_plan,
            policy,
            write_authorized=True,
            reconciliation_fault_plan=lookup_plan,
            reconciliation_timeout_seconds=lookup_timeout,
        )
        assert outcome.status == "handoff_required", name
        assert outcome.error_code == "ambiguous_write", name
        assert outcome.events[0].result == (
            "reconciliation_failed"
        ), name
        assert outcome.events[0].error_code == lookup_error, name
        assert outcome.confirmed_side_effect is False, name
        assert write_plan.attempts == 1, name
        assert lookup_plan.attempts == 1, name
        assert service.escalation_count == 1, name
        record_security_scenario(name, outcome, service)


    class UntrustedReconciliationService(SyntheticDeliveryService):
        def __init__(self, field_name: str, value: str | None) -> None:
            super().__init__()
            self.field_name = field_name
            self.value = value

        def execute_escalation_lookup_step(
            self,
            account_id: str,
            idempotency_key: str,
            step: FaultStep,
        ) -> dict[str, Any] | None:
            record = super().execute_escalation_lookup_step(
                account_id, idempotency_key, step
            )
            if self.field_name == "missing":
                return None
            assert record is not None
            return {**record, self.field_name: self.value}


    fingerprint_cases = [
        ("account_id", "ACCOUNT-002"),
        ("order_id", "ORDER-2002"),
        ("reason", "Another request's investigation."),
        ("idempotency_key", "different-idempotency-key"),
    ]
    for field_name, wrong_value in fingerprint_cases:
        service = UntrustedReconciliationService(
            field_name, wrong_value
        )
        write_plan = make_fault_plan(
            FaultKind.ACKNOWLEDGEMENT_LOST, FaultKind.SUCCESS
        )
        outcome = await run_write_with_reconciliation(
            service,
            "ACCOUNT-001",
            request,
            write_plan,
            policy,
            write_authorized=True,
        )
        assert outcome.status == "handoff_required"
        assert outcome.error_code == "idempotency_key_conflict"
        assert write_plan.attempts == 1
        assert service.escalation_count == 1
        record_security_scenario(
            f"reconciliation_rejects_wrong_{field_name}",
            outcome,
            service,
        )

    service = UntrustedReconciliationService("missing", None)
    missing_record_plan = make_fault_plan(
        FaultKind.ACKNOWLEDGEMENT_LOST, FaultKind.SUCCESS
    )
    missing_record_outcome = await run_write_with_reconciliation(
        service,
        "ACCOUNT-001",
        request,
        missing_record_plan,
        policy,
        write_authorized=True,
    )
    assert missing_record_outcome.status == "handoff_required"
    assert missing_record_outcome.error_code == "ambiguous_write"
    assert missing_record_plan.attempts == 1
    assert service.escalation_count == 1
    record_security_scenario(
        "committed_record_missing_fails_closed",
        missing_record_outcome,
        service,
    )

    # The dependency commits before a real wall-clock attempt timeout.
    service = SyntheticDeliveryService()
    commit_timeout_plan = FaultPlan(
        [FaultStep(FaultKind.COMMIT_THEN_TIMEOUT, 0.05)]
    )
    commit_timeout_outcome = await run_write_with_reconciliation(
        service,
        "ACCOUNT-001",
        request,
        commit_timeout_plan,
        policy,
        write_authorized=True,
        attempt_timeout_seconds=0.01,
    )
    assert commit_timeout_outcome.status == "success"
    assert commit_timeout_outcome.confirmed_side_effect is True
    assert commit_timeout_outcome.events[0].error_code == "timeout"
    assert commit_timeout_outcome.events[0].result == (
        "reconciled_transient_error"
    )
    assert commit_timeout_plan.attempts == 1
    assert service.escalation_count == 1
    record_security_scenario(
        "commit_before_wall_clock_timeout_reconciled",
        commit_timeout_outcome,
        service,
    )

    try:
        service.get_escalation_by_key(
            "ACCOUNT-002", request.idempotency_key
        )
    except PermanentToolError as error:
        assert error.code == "forbidden"
    else:
        raise AssertionError("Cross-account reconciliation was allowed.")


    class MalformedSearchContainerService(SyntheticDeliveryService):
        def __init__(self, malformed_response: Any) -> None:
            super().__init__()
            self.malformed_response = malformed_response
            self.malformed_response_pending = True

        def execute_order_search_step(
            self,
            account_id: str,
            filters: dict[str, str],
            step: FaultStep,
        ) -> Any:
            orders = super().execute_order_search_step(
                account_id, filters, step
            )
            if self.malformed_response_pending:
                self.malformed_response_pending = False
                return self.malformed_response
            return orders


    class UntrustedSearchResultService(SyntheticDeliveryService):
        def __init__(self, substitution: str) -> None:
            super().__init__()
            self.substitution = substitution

        def execute_order_search_step(
            self,
            account_id: str,
            filters: dict[str, str],
            step: FaultStep,
        ) -> list[dict[str, Any]]:
            legitimate = super().execute_order_search_step(
                account_id, filters, step
            )
            if self.substitution == "foreign_order":
                return [
                    self.orders["ORDER-2002"].model_dump(mode="json")
                ]
            if self.substitution == "unknown_order":
                return [
                    self.orders["ORDER-1001"]
                    .model_copy(update={"order_id": "ORDER-9999"})
                    .model_dump(mode="json")
                ]
            if self.substitution == "duplicate_order":
                return [legitimate[0], legitimate[0]]
            updates = (
                {"status": "delivered"}
                if self.substitution == "requested_status"
                else {"carrier": "Different Carrier"}
            )
            return [
                self.orders["ORDER-1001"]
                .model_copy(update=updates)
                .model_dump(mode="json")
            ]


    # Exercise semantic recovery, dependency failures, and authorization.
    order_search_cases = [
        {
            "name": "false_empty_order_search_recovers",
            "inferred": {"carrier": "Unavailable Carrier"},
            "count": 1,
            "attempts": 2,
            "first_result": "semantic_empty",
        },
        {
            "name": "unfiltered_search_excludes_foreign_orders",
            "requested": {},
            "count": 1,
            "attempts": 1,
        },
        {
            "name": "useful_inferred_filter_is_preserved",
            "inferred": {"carrier": "Example Carrier"},
            "count": 1,
            "attempts": 1,
            "applied_filters": {
                "status": "delayed",
                "carrier": "Example Carrier",
            },
        },
        {
            "name": "explicit_carrier_filter_stays_empty",
            "requested": {
                "status": "delayed",
                "carrier": "Unavailable Carrier",
            },
            "count": 0,
            "attempts": 1,
        },
        {
            "name": "explicit_filter_overrides_inference",
            "requested": {"status": "delivered"},
            "inferred": {"status": "delayed"},
            "max_attempts": 1,
            "count": 0,
            "attempts": 1,
        },
        {
            "name": "empty_after_one_semantic_relaxation",
            "requested": {"status": "delivered"},
            "inferred": {"carrier": "Unavailable Carrier"},
            "count": 0,
            "attempts": 2,
            "first_result": "semantic_empty",
        },
        {
            "name": "cross_account_search_rejected",
            "account_id": "ACCOUNT-002",
            "count": None,
            "attempts": 1,
            "error_code": "forbidden",
        },
        {
            "name": "shape_valid_foreign_search_result_rejected",
            "substitution": "foreign_order",
            "count": None,
            "attempts": 1,
            "error_code": "forbidden",
        },
        {
            "name": "unknown_search_result_identity_rejected",
            "substitution": "unknown_order",
            "count": None,
            "attempts": 1,
            "error_code": "order_not_found",
        },
        {
            "name": "duplicate_search_result_rejected",
            "substitution": "duplicate_order",
            "count": None,
            "attempts": 1,
            "error_code": "duplicate_search_result",
        },
        {
            "name": "search_result_violates_requested_status",
            "substitution": "requested_status",
            "count": None,
            "attempts": 1,
            "error_code": "search_result_filter_mismatch",
        },
        {
            "name": "search_result_violates_inferred_carrier",
            "inferred": {"carrier": "Example Carrier"},
            "substitution": "inferred_carrier",
            "count": None,
            "attempts": 1,
            "error_code": "search_result_filter_mismatch",
        },
        {
            "name": "requested_account_scope_injection_rejected",
            "requested": {
                "status": "delayed",
                "account_id": "ACCOUNT-002",
            },
            "count": None,
            "attempts": 1,
            "dependency_attempts": 0,
            "error_code": "invalid_search_filter",
        },
        {
            "name": "inferred_account_scope_injection_rejected",
            "inferred": {"account_id": "ACCOUNT-002"},
            "count": None,
            "attempts": 1,
            "dependency_attempts": 0,
            "error_code": "invalid_search_filter",
        },
        {
            "name": "search_timeout_then_success",
            "faults": (FaultKind.TIMEOUT, FaultKind.SUCCESS),
            "count": 1,
            "attempts": 2,
            "first_error": "timeout",
        },
        {
            "name": "search_rate_limit_then_success",
            "faults": (FaultKind.RATE_LIMITED, FaultKind.SUCCESS),
            "count": 1,
            "attempts": 2,
            "first_error": "rate_limited",
        },
        {
            "name": "search_unavailable_twice_then_success",
            "faults": (
                FaultKind.UNAVAILABLE,
                FaultKind.UNAVAILABLE,
                FaultKind.SUCCESS,
            ),
            "count": 1,
            "attempts": 3,
            "first_error": "dependency_unavailable",
        },
        {
            "name": "search_malformed_output_then_success",
            "faults": (
                FaultKind.MALFORMED_RESPONSE, FaultKind.SUCCESS
            ),
            "count": 1,
            "attempts": 2,
            "first_error": "invalid_tool_output",
        },
        {
            "name": "search_incomplete_output_then_success",
            "faults": (
                FaultKind.INCOMPLETE_RESPONSE, FaultKind.SUCCESS
            ),
            "count": 1,
            "attempts": 2,
            "first_error": "invalid_tool_output",
        },
        {
            "name": "search_dict_output_then_success",
            "malformed_container": {},
            "count": 1,
            "attempts": 2,
            "first_result": "invalid_output",
            "first_error": "invalid_tool_output",
        },
        {
            "name": "search_null_output_then_success",
            "malformed_container": None,
            "count": 1,
            "attempts": 2,
            "first_result": "invalid_output",
            "first_error": "invalid_tool_output",
        },
        {
            "name": "search_retry_budget_exhausted",
            "faults": (
                FaultKind.RATE_LIMITED,
                FaultKind.RATE_LIMITED,
                FaultKind.RATE_LIMITED,
            ),
            "count": None,
            "attempts": 3,
            "error_code": "rate_limited",
        },
        {
            "name": "semantic_empty_budget_exhausted",
            "inferred": {"carrier": "Unavailable Carrier"},
            "max_attempts": 1,
            "count": None,
            "attempts": 1,
            "error_code": "semantic_empty_unverified",
            "first_result": "semantic_empty",
        },
        {
            "name": "transport_and_semantic_retry_share_budget",
            "inferred": {"carrier": "Unavailable Carrier"},
            "faults": (
                FaultKind.TIMEOUT,
                FaultKind.SUCCESS,
                FaultKind.SUCCESS,
            ),
            "count": 1,
            "attempts": 3,
            "first_error": "timeout",
        },
        {
            "name": "search_wall_clock_timeout_then_success",
            "fault_plan": make_slow_then_success_plan(0.05),
            "attempt_timeout_seconds": 0.01,
            "count": 1,
            "attempts": 2,
            "first_error": "timeout",
        },
    ]


    for case in order_search_cases:
        name = case["name"]
        requested = case.get("requested", {"status": "delayed"})
        inferred = case.get("inferred", {})
        original_requested = dict(requested)
        original_inferred = dict(inferred)
        fault_plan = case.get("fault_plan") or make_fault_plan(
            *case.get("faults", (FaultKind.SUCCESS,))
        )
        case_policy = RecoveryPolicy(
            max_attempts=case.get("max_attempts", policy.max_attempts)
        )
        service = (
            UntrustedSearchResultService(case["substitution"])
            if "substitution" in case
            else MalformedSearchContainerService(
                case["malformed_container"]
            )
            if "malformed_container" in case
            else SyntheticDeliveryService()
        )
        account_id = case.get("account_id", "ACCOUNT-001")
        outcome = await run_order_search_with_recovery(
            service,
            account_id,
            requested,
            inferred,
            case_policy,
            fault_plan=fault_plan,
            attempt_timeout_seconds=case.get(
                "attempt_timeout_seconds", 1.0
            ),
        )
        assert requested == original_requested, name
        assert inferred == original_inferred, name
        assert outcome.attempts == case["attempts"], name
        assert len(outcome.events) == outcome.attempts, name
        assert [event.attempt for event in outcome.events] == list(
            range(1, outcome.attempts + 1)
        ), name
        assert all(
            event.operation == "search_orders"
            for event in outcome.events
        ), name
        assert fault_plan.attempts == case.get(
            "dependency_attempts", case["attempts"]
        ), name
        assert all(
            attempted_account == account_id
            for attempted_account in service.search_account_ids
        ), name
        if case.get("dependency_attempts") == 0:
            assert not service.search_account_ids, name
            assert not service.search_filter_history, name
        assert outcome.error_code == case.get("error_code"), name
        assert outcome.status == (
            "success" if case["count"] is not None
            else "handoff_required"
        ), name
        if "first_result" in case:
            assert outcome.events[0].result == (
                case["first_result"]
            ), name
        if "first_error" in case:
            assert outcome.events[0].error_code == (
                case["first_error"]
            ), name
        if case["count"] is not None:
            assert outcome.data is not None, name
            assert outcome.data["result_count"] == case["count"], name
            assert outcome.data["applied_filters"] == case.get(
                "applied_filters", original_requested
            ), name
            assert len(outcome.data["orders"]) == case["count"], name
            assert outcome.data["order_ids"] == [
                order["order_id"] for order in outcome.data["orders"]
            ], name
            assert all(
                all(
                    filters.get(key) == value
                    for key, value in original_requested.items()
                )
                for filters in service.search_filter_history
            ), name
            if outcome.events[0].result == "semantic_empty":
                assert service.search_account_ids == [
                    account_id, account_id
                ], name
                assert service.search_filter_history == [
                    {**original_inferred, **original_requested},
                    original_requested,
                ], name
            assert outcome.events[-1].result == "success", name
        else:
            assert outcome.events[-1].retryable is False, name
        scenario_results.append(
            {
                "scenario": name,
                "status": outcome.status,
                "error_code": outcome.error_code,
                "attempts": outcome.attempts,
                "side_effects": 0,
                "passed": True,
            }
        )

    # Semantic correction also respects the application's backoff policy.
    recorded_delays.clear()
    semantic_backoff = await run_order_search_with_recovery(
        SyntheticDeliveryService(),
        "ACCOUNT-001",
        {"status": "delayed"},
        {"carrier": "Unavailable Carrier"},
        backoff_policy,
        sleep_fn=record_delay,
    )
    assert semantic_backoff.status == "success"
    assert recorded_delays == [0.25]

    offline_scenario_results = pd.DataFrame(scenario_results)
    assert len(offline_scenario_results) == (
        len(read_cases)
        + 5
        + len(security_scenario_names)
        + len(order_search_cases)
    )
    assert offline_scenario_results["scenario"].is_unique
    assert offline_scenario_results["passed"].all()
    return offline_scenario_results
