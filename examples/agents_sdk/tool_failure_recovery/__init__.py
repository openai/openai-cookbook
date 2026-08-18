"""Reusable building blocks for the agent tool-failure recovery cookbook."""

from .core import (
    EscalationRequest,
    FaultKind,
    FaultPlan,
    FaultStep,
    RecoveryPolicy,
    SyntheticDeliveryService,
    ToolOutcome,
    make_fault_plan,
    make_slow_then_success_plan,
    run_order_search_with_recovery,
    run_read_with_recovery,
    run_unsafe_read,
    run_write_with_reconciliation,
)
from .offline import run_offline_recovery_suite

__all__ = [
    "EscalationRequest",
    "FaultKind",
    "FaultPlan",
    "FaultStep",
    "RecoveryPolicy",
    "SyntheticDeliveryService",
    "ToolOutcome",
    "make_fault_plan",
    "make_slow_then_success_plan",
    "run_offline_recovery_suite",
    "run_order_search_with_recovery",
    "run_read_with_recovery",
    "run_unsafe_read",
    "run_write_with_reconciliation",
]
