"""Validity gates for the simulated caller, separate from target task evidence."""

from __future__ import annotations

from typing import Any


def caller_simulation_validity(
    events: list[dict[str, Any]], *, backend_enabled: bool = False, work_pending: bool = False
) -> dict[str, Any]:
    """Allow configured caller reasoning, excluding simulator capability failures.

    Offline callers have no backend. Managed Responses handoffs are expected
    for live callers, but failed or unfinished reasoning is not target evidence.
    Passing this gate does not establish human-like caller realism.
    """
    identifiers: set[str] = set()
    anonymous_count = 0
    for event in events:
        if event.get("type") not in {"session.delegation.created", "delegation.created"}:
            continue
        item = event.get("delegation", event.get("item", {}))
        item = item if isinstance(item, dict) else {}
        if backend_enabled and item.get("target") == "responses":
            continue
        identifier = item.get("id")
        if isinstance(identifier, str) and identifier:
            identifiers.add(identifier)
        else:
            anonymous_count += 1
    count = len(identifiers) + anonymous_count
    reason = "unsupported_caller_delegation" if count else None
    if reason is None and backend_enabled:
        if any(event.get("type") in {"response.failed", "response.incomplete"} for event in events):
            reason = "caller_backend_failed"
        elif work_pending:
            reason = "caller_backend_pending"
    return {
        "scope": "caller_responses_delegation" if backend_enabled else "frontend_only_caller_delegation",
        "status": "invalid" if reason else "valid",
        "target_metrics_eligible": reason is None,
        "reason": reason,
        "unexpected_delegation_count": count,
        "delegation_ids": sorted(identifiers),
    }
