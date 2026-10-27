"""Offline regression for schema-scoped warehouse table context."""

from __future__ import annotations

from examples.agents_api.apps.data_analyst.warehouse import Warehouse


def _warehouse(tables: list[dict]) -> Warehouse:
    warehouse = object.__new__(Warehouse)
    warehouse.context = {"tables": tables}
    return warehouse


def test_qualified_context_does_not_apply_across_schemas() -> None:
    warehouse = _warehouse(
        [
            {
                "name": "finance.orders",
                "description": "Settled production orders in USD; exclude cancelled orders.",
                "owner": "Finance",
            }
        ]
    )

    assert warehouse.table_context("finance.orders")["owner"] == "Finance"
    assert warehouse.table_context("staging.customers") == {"name": "staging.customers"}
    assert warehouse.table_context("staging.orders") == {"name": "staging.orders"}


def test_unqualified_context_still_falls_back_by_basename() -> None:
    warehouse = _warehouse(
        [
            {
                "name": "orders",
                "description": "Customer order lifecycle.",
                "owner": "Shared",
            }
        ]
    )

    result = warehouse.table_context("staging.orders")
    assert result["owner"] == "Shared"
    assert result["name"] == "staging.orders"


def test_exact_qualified_match_beats_unqualified_fallback() -> None:
    warehouse = _warehouse(
        [
            {"name": "orders", "owner": "Shared"},
            {"name": "finance.orders", "owner": "Finance"},
        ]
    )

    assert warehouse.table_context("finance.orders")["owner"] == "Finance"
    assert warehouse.table_context("staging.orders")["owner"] == "Shared"
