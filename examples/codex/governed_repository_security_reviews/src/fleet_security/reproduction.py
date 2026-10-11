"""Strict, credential-free accounting checks for the synthetic tutorial.

These checks validate one completed reconciliation cycle. They never retry work,
change a policy, inspect repository content or turn an exhausted scan into success.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
import json
from typing import Any

from .pipeline import FleetPolicy
from .scanner import RETRY_REASON_CODES


DEMO_ATTEMPTED_REPOSITORIES = (
    "synthetic/payments-api", "synthetic/catalog-service",
    "synthetic/edge-auth", "synthetic/adversarial-docs",
)
DEMO_EXPECTED_STATUSES = {
    "synthetic/payments-api": "awaiting_finding_disposition",
    "synthetic/catalog-service": "review_packet_ready",
    "synthetic/edge-auth": "awaiting_finding_disposition",
    "synthetic/adversarial-docs": "failed_safe_abstention",
    "synthetic/unapproved-service": "awaiting_scope_approval",
    "synthetic/restricted-worker": "awaiting_threat_model_approval",
}
_RETRY_REASONS = RETRY_REASON_CODES
_STATUSES = frozenset({
    *DEMO_EXPECTED_STATUSES.values(), "awaiting_coverage_review", "cancelled",
    "deferred_rate_limit", "deferred_budget", "skipped_unchanged_security_scope",
    "awaiting_patch_approval", "awaiting_human_merge", "running",
})
_CONTEXTS = frozenset({
    "cycle", "first_cycle", "restart_cycle", "reviewed_cycle",
    "changed_revision", "changed_boundary", "supervisor_cycle",
    "recipe_cycle", "verify_first_cycle", "verify_restart_cycle",
})
_COUNTERS = (
    "admitted_jobs", "attempted_repositories", "scanner_invocations",
    "retry_attempts", "restricted_docker_receipts", "max_active_workers",
    "consumed_synthetic_units", "max_reserved_synthetic_units",
    "campaign_budget_synthetic_units", "max_concurrent_policy",
    "paid_api_calls", "external_writes",
)
_CHECKS = frozenset({
    "receipt_shape", "expected_contract_shape", "exact_record_set",
    "final_repository_decisions", "decision_state_counts", "counter_types",
    "exact_admitted_and_attempted_jobs", "exact_attempted_repository_set",
    "per_repository_attempt_ceiling", "raw_attempt_accounting",
    "retry_event_count", "retry_event_shape", "retry_event_fields",
    "retry_event_sequence", "retry_event_coverage", "job_admission_budget",
    "worker_concurrency_budget", "campaign_cost_accounting",
    "zero_restart_reservations", "successful_isolation_receipts",
    "synthetic_execution_boundary", "no_external_execution",
    "authenticated_audit", "lifetime_counter_baseline",
    "hostile_fixture_refusal",
})
_HOSTILE_REFUSALS = frozenset({
    "untrusted repository instruction requires safe abstention",
    "restricted synthetic scan abstained on untrusted repository content",
})


def _counter(value: object) -> int | None:
    # bool is intentionally not accepted as a count. Never stringify a value
    # supplied by an adapter: its repr or contents might contain private data.
    return value if type(value) is int and 0 <= value <= 1_000_000_000 else None


def safe_cycle_summary(receipt: object) -> dict[str, object]:
    """Return bounded, allowlisted diagnostics, never a raw receipt or reason.

Only the six public fixture labels may be printed. Other repository identities,
free-form error messages, reports, findings, paths and signing material are omitted.
"""
    if type(receipt) is not dict:
        return {"receipt_shape": "invalid"}
    result: dict[str, object] = {
        name: _counter(receipt.get(name)) for name in _COUNTERS
    }
    states = receipt.get("decision_states")
    result["decision_states"] = {
        name: _counter(states.get(name))
        for name in sorted(_STATUSES) if type(states) is dict and name in states
    }
    result["unknown_decision_state_count"] = (
        sum(key not in _STATUSES for key in states) if type(states) is dict else None
    )
    records = receipt.get("records")
    attempts = receipt.get("scanner_attempts_by_repository")
    result["fixture_records"] = {
        name: {
            "status": (
                row.get("status") if type(row.get("status")) is str
                and row["status"] in _STATUSES else "unrecognised"
            ),
            "cycle_attempts": (
                _counter(attempts.get(name, 0)) if type(attempts) is dict else None
            ),
            "hostile_refusal": (
                type(row.get("reason")) is str and row["reason"] in _HOSTILE_REFUSALS
                if name == "synthetic/adversarial-docs" else None
            ),
        }
        for name in sorted(DEMO_EXPECTED_STATUSES)
        if type(records) is dict and type(row := records.get(name)) is dict
    }
    result["other_record_count"] = (
        sum(key not in DEMO_EXPECTED_STATUSES for key in records)
        if type(records) is dict else None
    )
    events = receipt.get("transient_retry_events")
    result["transient_retry_events"] = [
        {
            "repository": (
                event.get("repository_id")
                if type(event.get("repository_id")) is str
                and event["repository_id"] in DEMO_EXPECTED_STATUSES else "other"
            ),
            "failed_attempt": _counter(event.get("failed_attempt")),
            "reason_code": (
                event.get("reason_code") if type(event.get("reason_code")) is str
                and event["reason_code"] in _RETRY_REASONS else "unrecognised"
            ),
        }
        for event in (events[:16] if type(events) is list else [])
        if type(event) is dict
    ]
    result["retry_events_omitted"] = max(0, len(events) - 16) if type(events) is list else None
    return result


class ReproductionFailure(AssertionError):
    """A failed tutorial contract with a bounded, safe machine-readable message."""

    def __init__(self, *, check: str, context: str, receipt: object,
                 expected: dict[str, object] | None = None) -> None:
        expected = expected if type(expected) is dict else {}
        counts = expected.get("decision_states")
        safe_expected = {
            name: _counter(expected.get(name))
            for name in (
                "attempted_repositories", "restricted_docker_receipts",
                "max_attempts_per_repository", "max_campaign_units",
            ) if name in expected
        }
        if type(counts) is dict:
            safe_expected["decision_states"] = {
                name: _counter(counts[name]) for name in sorted(_STATUSES) if name in counts
            }
        self.diagnostic = {
            "format": "governed-reproduction-failure/v1", "status": "FAIL",
            "check": check if type(check) is str and check in _CHECKS else "unrecognised_check",
            "context": context if type(context) is str and context in _CONTEXTS else "cycle",
            "actual": safe_cycle_summary(receipt), "expected": safe_expected,
        }
        super().__init__(json.dumps(self.diagnostic, sort_keys=True))


def redact_reproduction_failure(payload: object) -> dict[str, object] | None:
    """Re-allowlist a serialised failure, preserving public fixture diagnostics."""
    if (type(payload) is not dict or payload.get("format") != "governed-reproduction-failure/v1"
            or payload.get("status") != "FAIL"):
        return None
    actual = payload.get("actual")
    actual = actual if type(actual) is dict else {}
    reconstructed = {name: actual.get(name) for name in _COUNTERS}
    reconstructed["decision_states"] = actual.get("decision_states")
    rows = actual.get("fixture_records")
    rows = rows if type(rows) is dict else {}
    reconstructed["records"] = {
        name: {"status": row.get("status")}
        for name in DEMO_EXPECTED_STATUSES if type(row := rows.get(name)) is dict
    }
    reconstructed["scanner_attempts_by_repository"] = {
        name: row.get("cycle_attempts")
        for name in DEMO_EXPECTED_STATUSES if type(row := rows.get(name)) is dict
    }
    events = actual.get("transient_retry_events")
    reconstructed["transient_retry_events"] = [
        {"repository_id": row.get("repository"), "failed_attempt": row.get("failed_attempt"),
         "reason_code": row.get("reason_code")}
        for row in (events[:16] if type(events) is list else []) if type(row) is dict
    ]
    result = ReproductionFailure(
        check=payload.get("check"), context=payload.get("context"),
        receipt=reconstructed, expected=payload.get("expected"),
    ).diagnostic
    for name in ("other_record_count", "unknown_decision_state_count", "retry_events_omitted"):
        result["actual"][name] = _counter(actual.get(name))
    hostile = rows.get("synthetic/adversarial-docs")
    if type(hostile) is dict and type(hostile.get("hostile_refusal")) is bool:
        result["actual"]["fixture_records"]["synthetic/adversarial-docs"]["hostile_refusal"] = hostile["hostile_refusal"]
    return result


def assert_attempt_accounting(
    receipt: dict[str, Any], *, expected_attempted_repositories: Iterable[str],
    policy: FleetPolicy, scanner_invocations_before: int = 0, context: str = "cycle",
) -> dict[str, object]:
    """Check a completed nominal cycle without inventing recipe-only evidence.

    FleetPipeline's raw invocation counter is lifetime cumulative. When reusing
    a pipeline instance, supply its measured prior count explicitly. This check
    alone makes no claim about final decisions, isolation or durable audit.
    A valid owner cancellation can leave an admitted-but-unattempted job or a
    planned-but-uninvoked retry; it is intentionally not a nominal-cycle PASS.
    Cancellation-specific tests must check those safe outcomes separately.
    """
    expected_ids = tuple(expected_attempted_repositories)
    expected = {"attempted_repositories": len(expected_ids),
                "max_attempts_per_repository": policy.max_attempts}

    def require(condition: bool, check: str) -> None:
        if not condition:
            raise ReproductionFailure(check=check, context=context,
                                      receipt=receipt, expected=expected)

    require(type(receipt) is dict, "receipt_shape")
    require(all(type(name) is str for name in expected_ids)
            and len(set(expected_ids)) == len(expected_ids), "expected_contract_shape")
    require(all(_counter(receipt.get(name)) is not None for name in (
        "admitted_jobs", "attempted_repositories", "scanner_invocations", "retry_attempts",
    )), "counter_types")
    require(_counter(scanner_invocations_before) is not None
            and scanner_invocations_before <= receipt["scanner_invocations"],
            "lifetime_counter_baseline")
    require(receipt["admitted_jobs"] == receipt["attempted_repositories"] == len(expected_ids),
            "exact_admitted_and_attempted_jobs")
    counts = receipt.get("scanner_attempts_by_repository")
    require(type(counts) is dict and set(counts) == set(expected_ids), "exact_attempted_repository_set")
    require(all(_counter(value) is not None and 1 <= value <= policy.max_attempts
                for value in counts.values()), "per_repository_attempt_ceiling")
    raw_attempts = sum(counts.values())
    retries = sum(value - 1 for value in counts.values())
    require(receipt["scanner_invocations"] - scanner_invocations_before == raw_attempts
            and receipt["retry_attempts"] == retries
            and raw_attempts == len(expected_ids) + retries, "raw_attempt_accounting")
    events = receipt.get("transient_retry_events")
    require(type(events) is list and len(events) == retries, "retry_event_count")
    required_events = {(name, attempt) for name, count in counts.items()
                       for attempt in range(1, count)}
    observed_events: set[tuple[str, int]] = set()
    for event in events:
        require(type(event) is dict and set(event) == {
            "repository_id", "failed_attempt", "reason_code",
        }, "retry_event_shape")
        name, attempt, reason = (
            event["repository_id"], event["failed_attempt"], event["reason_code"],
        )
        require(type(name) is str and _counter(attempt) is not None
                and type(reason) is str and reason in _RETRY_REASONS, "retry_event_fields")
        require((name, attempt) in required_events and (name, attempt) not in observed_events,
                "retry_event_sequence")
        observed_events.add((name, attempt))
    require(observed_events == required_events, "retry_event_coverage")
    require(receipt["admitted_jobs"] <= policy.max_scans_per_run, "job_admission_budget")
    return {
        "status": "PASS", "context": context if context in _CONTEXTS else "cycle",
        "admitted_jobs": len(expected_ids), "attempted_repositories": len(expected_ids),
        "scanner_invocations": raw_attempts, "retry_attempts": retries,
    }


def assert_cycle_accounting(
    receipt: dict[str, Any], *, expected_attempted_repositories: Iterable[str],
    expected_statuses: Mapping[str, str], policy: FleetPolicy,
    expected_isolation_receipts: int, context: str = "cycle",
) -> dict[str, object]:
    """Validate exact jobs, final states and policy-bounded, evidenced retries.

    ``expected_attempted_repositories`` names exact repository IDs, not a count.
    An empty collection requires zero admitted jobs, attempts, retries, worker
    receipts, active workers and consumed units. Historical record.attempts are
    deliberately ignored: evidence reuse retains them across process restarts.
    """
    expected_ids = tuple(expected_attempted_repositories)
    expected_states = dict(expected_statuses)
    expected_counts = dict(sorted(Counter(expected_states.values()).items()))
    expected = {
        "attempted_repositories": len(expected_ids),
        "decision_states": {
            key: value for key, value in expected_counts.items() if key in _STATUSES
        },
        "restricted_docker_receipts": expected_isolation_receipts,
        "max_attempts_per_repository": policy.max_attempts,
        "max_campaign_units": policy.max_campaign_units,
    }

    def require(condition: bool, check: str) -> None:
        if not condition:
            raise ReproductionFailure(
                check=check, context=context, receipt=receipt, expected=expected,
            )

    require(type(receipt) is dict, "receipt_shape")
    require(
        all(type(name) is str for name in expected_ids)
        and len(set(expected_ids)) == len(expected_ids)
        and set(expected_ids).issubset(expected_states)
        and all(type(name) is str and type(status) is str and status in _STATUSES
                for name, status in expected_states.items())
        and _counter(expected_isolation_receipts) is not None,
        "expected_contract_shape",
    )
    records = receipt.get("records")
    require(type(records) is dict and set(records) == set(expected_states), "exact_record_set")
    require(
        all(type(records[name]) is dict and records[name].get("status") == status
            for name, status in expected_states.items()), "final_repository_decisions",
    )
    hostile = "synthetic/adversarial-docs"
    if expected_states.get(hostile) == "failed_safe_abstention":
        reason = records[hostile].get("reason")
        require(type(reason) is str and reason in _HOSTILE_REFUSALS, "hostile_fixture_refusal")
    states = receipt.get("decision_states")
    require(type(states) is dict and states == expected_counts
            and all(_counter(value) is not None for value in states.values()), "decision_state_counts")
    require(all(_counter(receipt.get(name)) is not None for name in _COUNTERS), "counter_types")
    accounting = assert_attempt_accounting(
        receipt, expected_attempted_repositories=expected_ids, policy=policy, context=context,
    )
    raw_attempts = accounting["scanner_invocations"]
    retries = accounting["retry_attempts"]
    require(receipt["max_concurrent_policy"] == policy.max_concurrent
            and receipt["max_active_workers"] <= min(policy.max_concurrent, len(expected_ids)),
            "worker_concurrency_budget")
    require(receipt["campaign_budget_synthetic_units"] == policy.max_campaign_units
            and receipt["consumed_synthetic_units"] == raw_attempts * policy.estimated_scan_units
            and receipt["consumed_synthetic_units"] <= policy.max_campaign_units
            and receipt["max_reserved_synthetic_units"] <= policy.max_campaign_units,
            "campaign_cost_accounting")
    if not expected_ids:
        require(receipt["max_reserved_synthetic_units"] == 0, "zero_restart_reservations")
    require(receipt["restricted_docker_receipts"] == expected_isolation_receipts,
            "successful_isolation_receipts")
    mode = receipt.get("execution_mode")
    require(mode in {"synthetic_restricted_docker", "synthetic_offline_not_sandboxed"}
            and (expected_isolation_receipts == 0 or mode == "synthetic_restricted_docker"),
            "synthetic_execution_boundary")
    require(receipt.get("live_product_execution") is False
            and receipt["paid_api_calls"] == receipt["external_writes"] == 0
            and receipt.get("automatic_pr_merge_or_deploy") is False, "no_external_execution")
    require(receipt.get("audit_valid") is True and receipt.get("durable_audit_valid") is True,
            "authenticated_audit")
    return {
        "status": "PASS", "context": context if context in _CONTEXTS else "cycle",
        "admitted_jobs": len(expected_ids), "attempted_repositories": len(expected_ids),
        "scanner_invocations": raw_attempts, "retry_attempts": retries,
        "restricted_docker_receipts": expected_isolation_receipts,
    }
