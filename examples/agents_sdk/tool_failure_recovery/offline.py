"""Deterministic, network-free regression coverage for recovery primitives."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from typing import Any

import pandas as pd

from .adapter import CallableDeliveryServiceAdapter
from .core import (
    DeliveryServiceAdapter,
    EscalationRecord,
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
    policy = RecoveryPolicy(
        max_attempts=3,
        base_delay_seconds=0,
        jitter_ratio=0,
    )
    scenario_results: list[dict[str, Any]] = []

    # Verify backoff without adding real delay to the notebook.
    recorded_delays: list[float] = []


    async def record_delay(delay_seconds: float) -> None:
        recorded_delays.append(delay_seconds)


    production_policy = RecoveryPolicy()
    assert production_policy.base_delay_seconds > 0
    assert production_policy.jitter_ratio > 0
    production_backoff = await run_read_with_recovery(
        SyntheticDeliveryService(),
        "ACCOUNT-001",
        "ORDER-1001",
        make_fault_plan(
            FaultKind.TIMEOUT,
            FaultKind.TIMEOUT,
            FaultKind.SUCCESS,
        ),
        production_policy,
        sleep_fn=record_delay,
        random_seed=7,
    )
    assert production_backoff.status == "success"
    assert len(recorded_delays) == 2
    for attempt, delay in enumerate(recorded_delays, start=1):
        base = production_policy.base_delay_seconds * 2 ** (
            attempt - 1
        )
        assert base <= delay <= base * (
            1 + production_policy.jitter_ratio
        )
    recorded_delays.clear()


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
            "error_code": "order_not_found",
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

    scoped_read_errors = {
        row["scenario"]: row["error_code"]
        for row in scenario_results
        if row["scenario"] in {
            "foreign_order_direct_read_rejected",
            "unknown_owned_order_not_found",
        }
    }
    assert scoped_read_errors == {
        "foreign_order_direct_read_rejected": "order_not_found",
        "unknown_owned_order_not_found": "order_not_found",
    }

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
        service: SyntheticDeliveryService | DeliveryServiceAdapter,
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


    # A non-retryable error after dispatch must still prove commit state.
    service = SyntheticDeliveryService()
    permanent_commit_plan = make_fault_plan(
        FaultKind.PERMANENT_AFTER_COMMIT, FaultKind.SUCCESS
    )
    permanent_commit = await run_write_with_reconciliation(
        service,
        "ACCOUNT-001",
        request,
        permanent_commit_plan,
        policy,
        write_authorized=True,
    )
    assert permanent_commit.status == "success"
    assert permanent_commit.confirmed_side_effect is True
    assert permanent_commit.events[0].result == (
        "reconciled_permanent_error"
    )
    assert permanent_commit.events[0].error_code == (
        "post_commit_permanent_failure"
    )
    assert permanent_commit_plan.attempts == 1
    assert service.escalation_count == 1
    record_security_scenario(
        "permanent_failure_after_commit_reconciled",
        permanent_commit,
        service,
    )

    service = SyntheticDeliveryService()
    failed_permanent_plan = make_fault_plan(
        FaultKind.PERMANENT_AFTER_COMMIT, FaultKind.SUCCESS
    )
    failed_lookup_plan = make_fault_plan(FaultKind.UNAVAILABLE)
    unverified_permanent_commit = await run_write_with_reconciliation(
        service,
        "ACCOUNT-001",
        request,
        failed_permanent_plan,
        policy,
        write_authorized=True,
        reconciliation_fault_plan=failed_lookup_plan,
    )
    assert unverified_permanent_commit.error_code == "ambiguous_write"
    assert unverified_permanent_commit.confirmed_side_effect is False
    assert failed_permanent_plan.attempts == 1
    assert failed_lookup_plan.attempts == 1
    assert service.escalation_count == 1
    record_security_scenario(
        "permanent_post_commit_lookup_failure_never_replays",
        unverified_permanent_commit,
        service,
    )

    service = SyntheticDeliveryService()
    permanent_precommit_plan = make_fault_plan(
        FaultKind.FORBIDDEN, FaultKind.SUCCESS
    )
    skipped_lookup_plan = make_fault_plan(FaultKind.SUCCESS)
    definitive_precommit_failure = await run_write_with_reconciliation(
        service,
        "ACCOUNT-001",
        request,
        permanent_precommit_plan,
        policy,
        write_authorized=True,
        reconciliation_fault_plan=skipped_lookup_plan,
    )
    assert definitive_precommit_failure.error_code == "forbidden"
    assert permanent_precommit_plan.attempts == 1
    assert skipped_lookup_plan.attempts == 0
    assert service.escalation_count == 0
    record_security_scenario(
        "definitive_precommit_permanent_failure_skips_lookup",
        definitive_precommit_failure,
        service,
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
            "error_code": "order_not_found",
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


    class BackendHTTPError(Exception):
        def __init__(
            self,
            status_code: int,
            headers: dict[str, str] | None = None,
        ) -> None:
            super().__init__(f"HTTP {status_code}")
            self.status_code = status_code
            self.headers = headers or {}


    backend_orders = {
        ("ACCOUNT-001", "ORDER-1001"): {
            "order_id": "ORDER-1001",
            "status": "delayed",
            "carrier": "Example Carrier",
            "last_scan": "Regional sorting facility",
        },
        ("ACCOUNT-002", "ORDER-2002"): {
            "order_id": "ORDER-2002",
            "status": "delayed",
            "carrier": "Other Carrier",
            "last_scan": "Another customer's sorting facility",
        },
    }
    backend_records: dict[
        tuple[str, str], EscalationRecord
    ] = {}
    backend_state: dict[str, Any] = {
        "read_attempts": 0,
        "search_attempts": 0,
        "write_attempts": 0,
        "lookup_attempts": 0,
        "next_read_error": None,
        "next_search_error": None,
        "next_write_error": None,
        "post_commit_error": None,
        "tamper_reason": False,
    }


    async def backend_authorizes_order(
        account_id: str, order_id: str
    ) -> bool:
        return (account_id, order_id) in backend_orders


    async def backend_reads_order(
        account_id: str, order_id: str
    ) -> dict[str, Any]:
        backend_state["read_attempts"] += 1
        pending_error = backend_state["next_read_error"]
        if pending_error is not None:
            backend_state["next_read_error"] = None
            raise pending_error
        return dict(backend_orders[(account_id, order_id)])


    async def backend_searches_orders(
        account_id: str, filters: dict[str, str]
    ) -> list[dict[str, Any]]:
        backend_state["search_attempts"] += 1
        pending_error = backend_state["next_search_error"]
        if pending_error is not None:
            backend_state["next_search_error"] = None
            raise pending_error
        return [
            dict(order)
            for (owner_account_id, _), order in backend_orders.items()
            if owner_account_id == account_id
            and all(
                order.get(name) == value
                for name, value in filters.items()
            )
        ]


    async def backend_creates_escalation(
        account_id: str,
        request: EscalationRequest,
    ) -> dict[str, Any]:
        backend_state["write_attempts"] += 1
        pending_error = backend_state["next_write_error"]
        if pending_error is not None:
            backend_state["next_write_error"] = None
            raise pending_error
        ledger_key = (account_id, request.idempotency_key)
        existing = backend_records.get(ledger_key)
        if existing is not None:
            return existing.model_dump(mode="json")
        if backend_orders[(account_id, request.order_id)][
            "status"
        ] != "delayed":
            raise PermanentToolError(
                "write_precondition_failed",
                retryable=False,
                committed=False,
            )
        record = EscalationRecord(
            escalation_id=f"BACKEND-{len(backend_records) + 1:04d}",
            account_id=account_id,
            order_id=request.order_id,
            reason=request.reason,
            idempotency_key=request.idempotency_key,
        )
        backend_records[ledger_key] = record
        pending_error = backend_state["post_commit_error"]
        if pending_error is not None:
            backend_state["post_commit_error"] = None
            raise pending_error
        return record.model_dump(mode="json")


    async def backend_looks_up_escalation(
        account_id: str, idempotency_key: str
    ) -> dict[str, Any] | None:
        backend_state["lookup_attempts"] += 1
        record = backend_records.get((account_id, idempotency_key))
        if record is None:
            return None
        serialized = record.model_dump(mode="json")
        if backend_state["tamper_reason"]:
            serialized["reason"] = "Another operation's investigation."
        return serialized


    production_adapter = CallableDeliveryServiceAdapter(
        authenticated_account_id="ACCOUNT-001",
        authorize_order_fn=backend_authorizes_order,
        read_order_fn=backend_reads_order,
        search_orders_fn=backend_searches_orders,
        create_escalation_fn=backend_creates_escalation,
        lookup_escalation_fn=backend_looks_up_escalation,
    )
    assert isinstance(production_adapter, DeliveryServiceAdapter)

    for name, transport_error, expected_error_code, expected_delay in (
        (
            "http_429_honors_retry_after_within_budget",
            BackendHTTPError(429, {"Retry-After": "1.25"}),
            "rate_limited",
            1.25,
        ),
        (
            "http_503_recovers",
            BackendHTTPError(503),
            "dependency_unavailable",
            0,
        ),
        (
            "async_transport_timeout_recovers",
            asyncio.TimeoutError(),
            "timeout",
            0,
        ),
    ):
        backend_state["next_read_error"] = transport_error
        recorded_delays.clear()
        adapter_read = await run_read_with_recovery(
            production_adapter,
            "ACCOUNT-001",
            "ORDER-1001",
            policy=policy,
            sleep_fn=record_delay,
        )
        assert adapter_read.status == "success", name
        assert adapter_read.attempts == 2, name
        assert adapter_read.events[0].error_code == (
            expected_error_code
        ), name
        assert recorded_delays == [expected_delay], name
        record_security_scenario(
            f"production_adapter_{name}",
            adapter_read,
            production_adapter,
        )

    retry_after_date = format_datetime(
        datetime.now(timezone.utc) + timedelta(seconds=60),
        usegmt=True,
    )
    backend_state["next_read_error"] = BackendHTTPError(
        429, {"retry-after": retry_after_date}
    )
    recorded_delays.clear()
    date_policy = policy.model_copy(
        update={"max_delay_seconds": 90.0}
    )
    date_retry = await run_read_with_recovery(
        production_adapter,
        "ACCOUNT-001",
        "ORDER-1001",
        policy=date_policy,
        sleep_fn=record_delay,
    )
    assert date_retry.status == "success"
    assert date_retry.attempts == 2
    assert len(recorded_delays) == 1
    assert 58 <= recorded_delays[0] <= 60
    record_security_scenario(
        "production_adapter_honors_http_date_retry_after",
        date_retry,
        production_adapter,
    )

    backend_state["next_read_error"] = BackendHTTPError(
        429, {"Retry-After": "60"}
    )
    attempts_before = backend_state["read_attempts"]
    recorded_delays.clear()
    over_budget_read = await run_read_with_recovery(
        production_adapter,
        "ACCOUNT-001",
        "ORDER-1001",
        policy=policy,
        sleep_fn=record_delay,
    )
    assert over_budget_read.status == "handoff_required"
    assert over_budget_read.error_code == "rate_limited"
    assert over_budget_read.attempts == 1
    assert over_budget_read.events[0].retryable is False
    assert backend_state["read_attempts"] == attempts_before + 1
    assert not recorded_delays
    record_security_scenario(
        "production_adapter_read_rejects_excessive_retry_after",
        over_budget_read,
        production_adapter,
    )

    backend_state["next_search_error"] = BackendHTTPError(
        429, {"Retry-After": "60"}
    )
    attempts_before = backend_state["search_attempts"]
    over_budget_search = await run_order_search_with_recovery(
        production_adapter,
        "ACCOUNT-001",
        {"status": "delayed"},
        {},
        policy,
        sleep_fn=record_delay,
    )
    assert over_budget_search.status == "handoff_required"
    assert over_budget_search.error_code == "rate_limited"
    assert over_budget_search.attempts == 1
    assert over_budget_search.events[0].retryable is False
    assert backend_state["search_attempts"] == attempts_before + 1
    assert not recorded_delays
    record_security_scenario(
        "production_adapter_search_rejects_excessive_retry_after",
        over_budget_search,
        production_adapter,
    )

    backend_state["next_write_error"] = BackendHTTPError(
        429, {"Retry-After": "60"}
    )
    over_budget_write = await run_write_with_reconciliation(
        production_adapter,
        "ACCOUNT-001",
        request.model_copy(
            update={"idempotency_key": "rate-limited-write-operation"}
        ),
        policy=policy,
        write_authorized=True,
        sleep_fn=record_delay,
    )
    assert over_budget_write.status == "handoff_required"
    assert over_budget_write.error_code == "rate_limited"
    assert over_budget_write.attempts == 1
    assert over_budget_write.events[0].retryable is False
    assert backend_state["write_attempts"] == 1
    assert backend_state["lookup_attempts"] == 1
    assert not recorded_delays
    record_security_scenario(
        "production_adapter_write_rejects_excessive_retry_after",
        over_budget_write,
        production_adapter,
    )
    backend_state["write_attempts"] = 0
    backend_state["lookup_attempts"] = 0

    foreign_backend_order = await run_read_with_recovery(
        production_adapter,
        "ACCOUNT-001",
        "ORDER-2002",
        policy=policy,
    )
    missing_backend_order = await run_read_with_recovery(
        production_adapter,
        "ACCOUNT-001",
        "ORDER-9999",
        policy=policy,
    )
    assert foreign_backend_order.error_code == "order_not_found"
    assert missing_backend_order.error_code == (
        foreign_backend_order.error_code
    )
    record_security_scenario(
        "production_adapter_hides_foreign_order_existence",
        foreign_backend_order,
        production_adapter,
    )

    adapter_search = await run_order_search_with_recovery(
        production_adapter,
        "ACCOUNT-001",
        {"status": "delayed"},
        {"carrier": "Unavailable Carrier"},
        policy,
    )
    assert adapter_search.status == "success"
    assert adapter_search.attempts == 2
    assert adapter_search.data is not None
    assert adapter_search.data["order_ids"] == ["ORDER-1001"]
    record_security_scenario(
        "production_adapter_false_empty_search_recovers",
        adapter_search,
        production_adapter,
    )

    backend_state["post_commit_error"] = BackendHTTPError(409)
    adapter_write = await run_write_with_reconciliation(
        production_adapter,
        "ACCOUNT-001",
        request,
        policy=policy,
        write_authorized=True,
    )
    assert adapter_write.status == "success"
    assert adapter_write.events[0].result == (
        "reconciled_permanent_error"
    )
    assert adapter_write.events[0].error_code == (
        "dependency_http_409"
    )
    assert backend_state["write_attempts"] == 1
    assert backend_state["lookup_attempts"] == 1
    verified_backend_record = (
        production_adapter.get_escalation_by_key(
            "ACCOUNT-001", request.idempotency_key
        )
    )
    assert verified_backend_record is not None
    assert production_adapter.escalation_count == 1
    record_security_scenario(
        "production_adapter_post_commit_http_409_reconciled",
        adapter_write,
        production_adapter,
    )

    tampered_request = request.model_copy(
        update={"idempotency_key": "a-tampered-backend-operation"}
    )
    backend_state["post_commit_error"] = BackendHTTPError(422)
    backend_state["tamper_reason"] = True
    tampered_backend_write = await run_write_with_reconciliation(
        production_adapter,
        "ACCOUNT-001",
        tampered_request,
        policy=policy,
        write_authorized=True,
    )
    assert tampered_backend_write.error_code == (
        "idempotency_key_conflict"
    )
    assert tampered_backend_write.attempts == 1
    assert backend_state["write_attempts"] == 2
    assert production_adapter.escalation_count == 1
    assert production_adapter.get_escalation_by_key(
        "ACCOUNT-001", tampered_request.idempotency_key
    ) is None
    record_security_scenario(
        "production_adapter_never_caches_unverified_lookup",
        tampered_backend_write,
        production_adapter,
    )
    try:
        production_adapter.get_escalation_by_key(
            "ACCOUNT-002", request.idempotency_key
        )
    except PermanentToolError as error:
        assert error.code == "forbidden"
    else:
        raise AssertionError("The verified adapter cache leaked tenants.")

    deadline_policy = policy.model_copy(
        update={"max_attempts": 1}
    )

    def delayed_authorization_adapter(
        delayed_call: int,
    ) -> tuple[CallableDeliveryServiceAdapter, dict[str, int]]:
        authorization_state = {"calls": 0}

        async def delayed_ownership(
            account_id: str, order_id: str
        ) -> bool:
            authorization_state["calls"] += 1
            if authorization_state["calls"] == delayed_call:
                await asyncio.sleep(0.05)
            return await backend_authorizes_order(
                account_id, order_id
            )

        return (
            CallableDeliveryServiceAdapter(
                authenticated_account_id="ACCOUNT-001",
                authorize_order_fn=delayed_ownership,
                read_order_fn=backend_reads_order,
                search_orders_fn=backend_searches_orders,
                create_escalation_fn=backend_creates_escalation,
                lookup_escalation_fn=backend_looks_up_escalation,
            ),
            authorization_state,
        )

    delayed_read_adapter, read_authorization = (
        delayed_authorization_adapter(3)
    )
    delayed_read = await run_read_with_recovery(
        delayed_read_adapter,
        "ACCOUNT-001",
        "ORDER-1001",
        policy=deadline_policy,
        attempt_timeout_seconds=0.01,
    )
    assert delayed_read.status == "handoff_required"
    assert delayed_read.error_code == "timeout"
    assert delayed_read.data is None
    assert delayed_read.attempts == 1
    assert read_authorization["calls"] == 3
    record_security_scenario(
        "production_adapter_bounds_read_ownership_recheck",
        delayed_read,
        delayed_read_adapter,
    )

    delayed_search_adapter, search_authorization = (
        delayed_authorization_adapter(1)
    )
    delayed_search = await run_order_search_with_recovery(
        delayed_search_adapter,
        "ACCOUNT-001",
        {"status": "delayed"},
        {},
        deadline_policy,
        attempt_timeout_seconds=0.01,
    )
    assert delayed_search.status == "handoff_required"
    assert delayed_search.error_code == "timeout"
    assert delayed_search.data is None
    assert delayed_search.attempts == 1
    assert search_authorization["calls"] == 1
    record_security_scenario(
        "production_adapter_bounds_search_ownership_recheck",
        delayed_search,
        delayed_search_adapter,
    )

    delayed_write_adapter, write_authorization = (
        delayed_authorization_adapter(2)
    )
    delayed_write_request = request.model_copy(
        update={"idempotency_key": "delayed-write-authorization"}
    )
    writes_before = backend_state["write_attempts"]
    delayed_write = await run_write_with_reconciliation(
        delayed_write_adapter,
        "ACCOUNT-001",
        delayed_write_request,
        policy=deadline_policy,
        write_authorized=True,
        attempt_timeout_seconds=0.01,
    )
    assert delayed_write.status == "handoff_required"
    assert delayed_write.error_code == "timeout"
    assert delayed_write.attempts == 1
    assert write_authorization["calls"] == 2
    assert backend_state["write_attempts"] == writes_before
    assert (
        "ACCOUNT-001", delayed_write_request.idempotency_key
    ) not in backend_records
    record_security_scenario(
        "production_adapter_bounds_prewrite_authorization",
        delayed_write,
        delayed_write_adapter,
    )

    backend_state["tamper_reason"] = False
    backend_state["post_commit_error"] = BackendHTTPError(409)
    delayed_lookup_adapter, lookup_authorization = (
        delayed_authorization_adapter(3)
    )
    delayed_lookup_request = request.model_copy(
        update={"idempotency_key": "delayed-lookup-authorization"}
    )
    writes_before = backend_state["write_attempts"]
    delayed_lookup = await run_write_with_reconciliation(
        delayed_lookup_adapter,
        "ACCOUNT-001",
        delayed_lookup_request,
        policy=deadline_policy,
        write_authorized=True,
        attempt_timeout_seconds=0.01,
        reconciliation_timeout_seconds=0.01,
    )
    assert delayed_lookup.status == "handoff_required"
    assert delayed_lookup.error_code == "ambiguous_write"
    assert delayed_lookup.confirmed_side_effect is False
    assert delayed_lookup.attempts == 1
    assert lookup_authorization["calls"] == 3
    assert backend_state["write_attempts"] == writes_before + 1
    assert (
        "ACCOUNT-001", delayed_lookup_request.idempotency_key
    ) in backend_records
    assert delayed_lookup_adapter.escalation_count == 0
    record_security_scenario(
        "production_adapter_bounds_postcommit_ownership_recheck",
        delayed_lookup,
        delayed_lookup_adapter,
    )


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
            "error_code": "order_not_found",
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
        case_policy = policy.model_copy(
            update={
                "max_attempts": case.get(
                    "max_attempts", policy.max_attempts
                )
            }
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
