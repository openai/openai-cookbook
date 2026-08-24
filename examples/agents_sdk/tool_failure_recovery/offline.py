"""Small, deterministic regression suite for the documented recovery patterns."""

from __future__ import annotations

from typing import Any

import pandas as pd

from .core import (
    EscalationRequest,
    FaultKind,
    FaultStep,
    RecoveryPolicy,
    SyntheticDeliveryService,
    ToolOutcome,
    make_fault_plan,
    make_slow_then_success_plan,
    run_order_search_with_recovery,
    run_read_with_recovery,
    run_write_with_reconciliation,
)

ACCOUNT_ID = "ACCOUNT-001"
ORDER_ID = "ORDER-1001"


def _record_result(
    results: list[dict[str, Any]],
    scenario: str,
    outcome: ToolOutcome,
    *,
    side_effects: int = 0,
) -> None:
    assert outcome.attempts == len(outcome.events), scenario
    results.append(
        {
            "scenario": scenario,
            "status": outcome.status,
            "error_code": outcome.error_code,
            "attempts": outcome.attempts,
            "side_effects": side_effects,
            "passed": True,
        }
    )


class _SubstitutedOrderService(SyntheticDeliveryService):
    """Return a valid foreign order so identity verification can reject it."""

    def execute_order_status_step(
        self, account_id: str, order_id: str, step: FaultStep
    ) -> dict[str, Any]:
        super().execute_order_status_step(account_id, order_id, step)
        return self.orders["ORDER-2002"].model_dump(mode="json")


class _InvalidSearchResultService(SyntheticDeliveryService):
    def __init__(self, failure: str) -> None:
        super().__init__()
        self.failure = failure

    def execute_order_search_step(
        self, account_id: str, filters: dict[str, str], step: FaultStep
    ) -> list[dict[str, Any]]:
        orders = super().execute_order_search_step(account_id, filters, step)
        if self.failure == "duplicate":
            return orders + orders
        if self.failure == "foreign":
            return [self.orders["ORDER-2002"].model_dump(mode="json")]
        return [{**orders[0], "status": "in_transit"}]


async def _check_read_recovery(
    results: list[dict[str, Any]], policy: RecoveryPolicy
) -> None:
    cases = (
        ("healthy_read", (FaultKind.SUCCESS,), "success", None, 1),
        (
            "timeout_then_success",
            (FaultKind.TIMEOUT, FaultKind.SUCCESS),
            "success",
            None,
            2,
        ),
        (
            "unavailable_twice_then_success",
            (FaultKind.UNAVAILABLE, FaultKind.UNAVAILABLE, FaultKind.SUCCESS),
            "success",
            None,
            3,
        ),
        (
            "rate_limit_budget_exhausted",
            (FaultKind.RATE_LIMITED,) * 3,
            "handoff_required",
            "rate_limited",
            3,
        ),
        (
            "malformed_output_then_success",
            (FaultKind.MALFORMED_RESPONSE, FaultKind.SUCCESS),
            "success",
            None,
            2,
        ),
        (
            "permanent_403",
            (FaultKind.FORBIDDEN, FaultKind.SUCCESS),
            "handoff_required",
            "forbidden",
            1,
        ),
        (
            "permanent_404",
            (FaultKind.NOT_FOUND, FaultKind.SUCCESS),
            "handoff_required",
            "not_found",
            1,
        ),
    )
    for name, faults, expected_status, error_code, attempts in cases:
        outcome = await run_read_with_recovery(
            SyntheticDeliveryService(), ACCOUNT_ID, ORDER_ID, make_fault_plan(*faults), policy
        )
        assert (outcome.status, outcome.error_code, outcome.attempts) == (
            expected_status,
            error_code,
            attempts,
        ), name
        _record_result(results, name, outcome)

    for name, account_id, order_id, expected_error, service in (
        (
            "cross_account_direct_read_rejected",
            "ACCOUNT-002",
            ORDER_ID,
            "forbidden",
            SyntheticDeliveryService(),
        ),
        (
            "foreign_order_direct_read_rejected",
            ACCOUNT_ID,
            "ORDER-2002",
            "order_not_found",
            SyntheticDeliveryService(),
        ),
        (
            "shape_valid_wrong_order_response_rejected",
            ACCOUNT_ID,
            ORDER_ID,
            "unexpected_order_identity",
            _SubstitutedOrderService(),
        ),
    ):
        outcome = await run_read_with_recovery(service, account_id, order_id, policy=policy)
        assert outcome.error_code == expected_error, name
        _record_result(results, name, outcome)

    outcome = await run_read_with_recovery(
        SyntheticDeliveryService(),
        ACCOUNT_ID,
        ORDER_ID,
        make_slow_then_success_plan(0.03),
        policy,
        attempt_timeout_seconds=0.005,
    )
    assert outcome.status == "success" and outcome.attempts == 2
    assert outcome.events[0].error_code == "timeout"
    _record_result(results, "wall_clock_timeout_then_success", outcome)


async def _check_write_recovery(
    results: list[dict[str, Any]], policy: RecoveryPolicy
) -> None:
    request = EscalationRequest(
        account_id=ACCOUNT_ID,
        order_id=ORDER_ID,
        reason="The delayed shipment needs carrier investigation.",
        idempotency_key="order-1001-carrier-investigation",
    )
    cases = (
        ("approved_write_succeeds", (FaultKind.SUCCESS,), "success", None, 1),
        (
            "write_timeout_then_success",
            (FaultKind.TIMEOUT, FaultKind.SUCCESS),
            "success",
            None,
            2,
        ),
        (
            "ack_lost_without_duplicate",
            (FaultKind.ACKNOWLEDGEMENT_LOST,),
            "success",
            None,
            1,
        ),
        (
            "invalid_write_output_reconciled",
            (FaultKind.MALFORMED_RESPONSE,),
            "success",
            None,
            1,
        ),
        (
            "permanent_failure_after_commit_reconciled",
            (FaultKind.PERMANENT_AFTER_COMMIT,),
            "success",
            None,
            1,
        ),
        (
            "definitive_precommit_failure_stops",
            (FaultKind.FORBIDDEN, FaultKind.SUCCESS),
            "handoff_required",
            "forbidden",
            1,
        ),
    )
    for name, faults, expected_status, error_code, attempts in cases:
        service = SyntheticDeliveryService()
        outcome = await run_write_with_reconciliation(
            service,
            ACCOUNT_ID,
            request,
            make_fault_plan(*faults),
            policy,
            write_authorized=True,
        )
        assert (outcome.status, outcome.error_code, outcome.attempts) == (
            expected_status,
            error_code,
            attempts,
        ), name
        assert service.escalation_count == int(expected_status == "success")
        _record_result(results, name, outcome, side_effects=service.escalation_count)

    service = SyntheticDeliveryService()
    denied = await run_write_with_reconciliation(
        service, ACCOUNT_ID, request, policy=policy, write_authorized=False
    )
    assert denied.error_code == "write_not_authorized"
    assert service.escalation_count == 0
    _record_result(results, "write_without_application_approval", denied)

    service = SyntheticDeliveryService()
    unresolved = await run_write_with_reconciliation(
        service,
        ACCOUNT_ID,
        request,
        make_fault_plan(FaultKind.ACKNOWLEDGEMENT_LOST),
        policy,
        write_authorized=True,
        reconciliation_fault_plan=make_fault_plan(FaultKind.UNAVAILABLE),
    )
    assert unresolved.error_code == "ambiguous_write"
    assert unresolved.attempts == service.escalation_count == 1
    _record_result(
        results,
        "reconciliation_failure_never_replays_write",
        unresolved,
        side_effects=service.escalation_count,
    )

    service = SyntheticDeliveryService()
    first = await run_write_with_reconciliation(
        service, ACCOUNT_ID, request, policy=policy, write_authorized=True
    )
    conflict = await run_write_with_reconciliation(
        service,
        ACCOUNT_ID,
        request.model_copy(update={"reason": "A different investigation."}),
        policy=policy,
        write_authorized=True,
    )
    assert first.status == "success"
    assert conflict.error_code == "idempotency_key_conflict"
    assert service.escalation_count == 1
    _record_result(results, "idempotency_key_conflict", conflict, side_effects=1)

    service = SyntheticDeliveryService()
    service.orders[ORDER_ID] = service.orders[ORDER_ID].model_copy(
        update={"status": "delivered"}
    )
    stale = await run_write_with_reconciliation(
        service, ACCOUNT_ID, request, policy=policy, write_authorized=True
    )
    assert stale.error_code == "write_precondition_failed"
    _record_result(results, "stale_delayed_read_rejects_write", stale)


async def _check_search_recovery(
    results: list[dict[str, Any]], policy: RecoveryPolicy
) -> None:
    cases = (
        (
            "healthy_order_search",
            {"status": "delayed"},
            {},
            (FaultKind.SUCCESS,),
            1,
            1,
            None,
        ),
        (
            "false_empty_order_search_recovers",
            {"status": "delayed"},
            {"carrier": "Unrelated Carrier"},
            (FaultKind.SUCCESS, FaultKind.SUCCESS),
            1,
            2,
            None,
        ),
        (
            "requested_filter_is_never_removed",
            {"status": "delivered"},
            {},
            (FaultKind.SUCCESS,),
            0,
            1,
            None,
        ),
        (
            "search_timeout_then_success",
            {"status": "delayed"},
            {},
            (FaultKind.TIMEOUT, FaultKind.SUCCESS),
            1,
            2,
            None,
        ),
        (
            "search_retry_budget_exhausted",
            {"status": "delayed"},
            {},
            (FaultKind.UNAVAILABLE,) * 3,
            None,
            3,
            "dependency_unavailable",
        ),
        (
            "search_account_filter_injection_rejected",
            {"account_id": "ACCOUNT-002"},
            {},
            (FaultKind.SUCCESS,),
            None,
            1,
            "invalid_search_filter",
        ),
    )
    for name, requested, inferred, faults, count, attempts, error_code in cases:
        service = SyntheticDeliveryService()
        outcome = await run_order_search_with_recovery(
            service,
            ACCOUNT_ID,
            requested,
            inferred,
            policy,
            fault_plan=make_fault_plan(*faults),
        )
        assert outcome.attempts == attempts and outcome.error_code == error_code
        if count is None:
            assert outcome.status == "handoff_required", name
        else:
            assert outcome.data is not None
            assert outcome.data["result_count"] == count, name
            assert outcome.data["applied_filters"] == requested, name
        if name == "false_empty_order_search_recovers":
            assert service.search_filter_history == [{**inferred, **requested}, requested]
        _record_result(results, name, outcome)

    for failure, expected_error in (
        ("duplicate", "duplicate_search_result"),
        ("foreign", "order_not_found"),
        ("mismatch", "search_result_filter_mismatch"),
    ):
        outcome = await run_order_search_with_recovery(
            _InvalidSearchResultService(failure),
            ACCOUNT_ID,
            {"status": "delayed"},
            {},
            policy,
        )
        assert outcome.error_code == expected_error
        _record_result(results, f"{failure}_search_result_rejected", outcome)


async def run_offline_recovery_suite() -> pd.DataFrame:
    """Exercise representative retries, ownership, search, and safe writes."""
    policy = RecoveryPolicy(max_attempts=3, base_delay_seconds=0, jitter_ratio=0)
    results: list[dict[str, Any]] = []
    await _check_read_recovery(results, policy)
    await _check_write_recovery(results, policy)
    await _check_search_recovery(results, policy)
    frame = pd.DataFrame(results)
    assert frame["scenario"].is_unique and frame["passed"].all()
    return frame
