"""Offline regression tests for schema-scoped warehouse table context.

Run from the repository root with:
    python -m pytest examples/agents_api/apps/data_analyst/tests -q
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest

from examples.agents_api.apps.data_analyst.memory import MemoryStore
from examples.agents_api.apps.data_analyst.warehouse import Warehouse


def _context_only_warehouse(tables: list[dict[str, Any]]) -> Warehouse:
    warehouse = object.__new__(Warehouse)
    warehouse.context = {"tables": tables}
    return warehouse


class _FakePostgresCursor:
    def __init__(self, schemas: dict[tuple[str, str], list[dict[str, Any]]]) -> None:
        self._schemas = schemas
        self._rows: list[dict[str, Any]] = []

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        if "information_schema.tables" in sql:
            self._rows = [
                {"table_schema": schema, "table_name": table}
                for schema, table in sorted(self._schemas)
            ]
        elif "information_schema.columns" in sql:
            schema, table = params
            self._rows = list(self._schemas.get((schema, table), []))
        else:
            raise AssertionError(f"Unexpected SQL in test: {sql}")

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self._rows)


class _FakePostgresConnection:
    def __init__(self, schemas: dict[tuple[str, str], list[dict[str, Any]]]) -> None:
        self._schemas = schemas

    def cursor(self) -> _FakePostgresCursor:
        return _FakePostgresCursor(self._schemas)


def _postgres_warehouse(
    tmp_path: Path,
    schemas: dict[tuple[str, str], list[dict[str, Any]]],
    tables_context: list[dict[str, Any]],
) -> Warehouse:
    warehouse = object.__new__(Warehouse)
    warehouse.engine = "PostgreSQL"
    warehouse.context = {"tables": tables_context}
    warehouse.memory = MemoryStore(tmp_path / "memories.json")
    warehouse.connection = _FakePostgresConnection(schemas)
    return warehouse


def test_qualified_context_does_not_bleed_across_colliding_schemas() -> None:
    warehouse = _context_only_warehouse(
        [
            {
                "name": "finance.orders",
                "description": "Settled production orders in USD; exclude cancelled orders.",
                "owner": "Finance",
            }
        ]
    )

    assert warehouse.table_context("finance.orders") == {
        "name": "finance.orders",
        "description": "Settled production orders in USD; exclude cancelled orders.",
        "owner": "Finance",
    }
    assert warehouse.table_context("staging.customers") == {"name": "staging.customers"}
    assert warehouse.table_context("staging.orders") == {"name": "staging.orders"}
    assert warehouse.table_context("orders") == {"name": "orders"}


def test_unqualified_context_falls_back_for_qualified_tables_and_keeps_table_name() -> (
    None
):
    warehouse = _context_only_warehouse(
        [
            {"name": None, "owner": "Ignored"},
            {"name": "prod.finance.orders", "owner": "Prod Finance"},
            {
                "name": "orders",
                "description": "Customer order lifecycle.",
                "owner": "Shared",
            },
        ]
    )

    assert warehouse.table_context("prod.finance.orders") == {
        "name": "prod.finance.orders",
        "owner": "Prod Finance",
    }
    assert warehouse.table_context("dev.finance.orders") == {
        "name": "dev.finance.orders",
        "description": "Customer order lifecycle.",
        "owner": "Shared",
    }
    assert warehouse.table_context("staging.orders") == {
        "name": "staging.orders",
        "description": "Customer order lifecycle.",
        "owner": "Shared",
    }
    assert warehouse.table_context("orders") == {
        "name": "orders",
        "description": "Customer order lifecycle.",
        "owner": "Shared",
    }


def test_exact_qualified_match_takes_precedence_over_earlier_unqualified_fallback() -> (
    None
):
    warehouse = _context_only_warehouse(
        [
            {"name": "orders", "owner": "Shared"},
            {"name": "finance.orders", "owner": "Finance"},
        ]
    )

    assert warehouse.table_context("finance.orders") == {
        "name": "finance.orders",
        "owner": "Finance",
    }
    assert warehouse.table_context("staging.orders") == {
        "name": "staging.orders",
        "owner": "Shared",
    }


def test_multi_schema_inspect_and_search_isolate_qualified_context(
    tmp_path: Path,
) -> None:
    schemas = {
        ("finance", "orders"): [
            {"column_name": "order_id", "data_type": "bigint", "is_nullable": "NO"}
        ],
        ("staging", "orders"): [
            {"column_name": "raw_payload", "data_type": "jsonb", "is_nullable": "YES"}
        ],
    }
    warehouse = _postgres_warehouse(
        tmp_path,
        schemas,
        [
            {
                "name": "finance.orders",
                "description": "Settled production orders in USD.",
                "owner": "Finance",
            }
        ],
    )

    staging = warehouse.inspect_table({"table": "staging.orders"})
    assert staging == {
        "name": "staging.orders",
        "columns": [{"name": "raw_payload", "type": "jsonb", "nullable": True}],
    }

    finance_matches = warehouse.search_tables({"query": "Finance settled"})["tables"]
    assert [table["name"] for table in finance_matches] == ["finance.orders"]
    assert finance_matches[0]["owner"] == "Finance"


def test_search_by_schema_name_still_matches_when_unqualified_fallback_applies(
    tmp_path: Path,
) -> None:
    schemas = {
        ("staging", "orders"): [
            {"column_name": "id", "data_type": "integer", "is_nullable": "NO"}
        ]
    }
    warehouse = _postgres_warehouse(
        tmp_path,
        schemas,
        [{"name": "orders", "description": "Order records.", "owner": "Commerce"}],
    )

    by_schema = warehouse.search_tables({"query": "staging"})["tables"]
    assert [table["name"] for table in by_schema] == ["staging.orders"]
    assert by_schema[0]["owner"] == "Commerce"


@pytest.mark.parametrize("context_name", ["finance.orders", "orders"])
def test_sqlite_unqualified_tables_ignore_other_schema_context(
    tmp_path: Path, context_name: str
) -> None:
    db_path = tmp_path / "warehouse.sqlite"
    with closing(sqlite3.connect(db_path)) as connection:
        connection.execute("CREATE TABLE orders (id INTEGER NOT NULL)")

    warehouse = Warehouse(
        f"sqlite:///{db_path}",
        context={"tables": [{"name": context_name, "owner": "Finance"}]},
        memory_path=tmp_path / "memories.json",
    )
    try:
        inspected = warehouse.inspect_table({"table": "orders"})
        if context_name == "orders":
            assert inspected["owner"] == "Finance"
            assert warehouse.search_tables({"query": "Finance"}) == {
                "tables": [inspected]
            }
        else:
            assert "owner" not in inspected
            assert warehouse.search_tables({"query": "Finance"}) == {"tables": []}
    finally:
        warehouse.close()
