"""Offline regression tests for warehouse table-context resolution."""

import sqlite3
from unittest.mock import Mock

from .warehouse import Warehouse


def make_warehouse(context):
    warehouse = object.__new__(Warehouse)
    warehouse.context = {"tables": context}
    warehouse.engine = "PostgreSQL"
    warehouse.connection = Mock()
    cursor = warehouse.connection.cursor.return_value
    cursor.fetchall.side_effect = lambda: (
        [
            {"table_schema": "finance", "table_name": "orders"},
            {"table_schema": "staging", "table_name": "orders"},
        ]
        if "information_schema.tables" in cursor.execute.call_args.args[0]
        else [{"column_name": "id", "data_type": "integer", "is_nullable": "NO"}]
    )
    return warehouse


def test_qualified_context_does_not_cross_schemas():
    warehouse = make_warehouse(
        [{"name": "finance.orders", "owner": "Finance"}]
    )
    assert warehouse.table_context("finance.orders")["owner"] == "Finance"
    assert warehouse.table_context("staging.orders") == {"name": "staging.orders"}
    assert warehouse.inspect_table({"table": "staging.orders"}) == {
        "name": "staging.orders",
        "columns": [{"name": "id", "type": "integer", "nullable": False}],
    }
    assert [
        table["name"]
        for table in warehouse.search_tables({"query": "Finance"})["tables"]
    ] == ["finance.orders"]


def test_generic_context_is_used_only_without_an_exact_match():
    warehouse = make_warehouse(
        [
            {"name": "orders", "owner": "Shared"},
            {"name": "finance.orders", "owner": "Finance"},
        ]
    )
    assert warehouse.table_context("finance.orders")["owner"] == "Finance"
    assert warehouse.table_context("staging.orders") == {
        "name": "staging.orders",
        "owner": "Shared",
    }
    assert warehouse.context["tables"][0]["name"] == "orders"
    assert [
        table["name"]
        for table in warehouse.search_tables({"query": "staging"})["tables"]
    ] == ["staging.orders"]


def test_sqlite_table_does_not_inherit_qualified_context(tmp_path):
    path = tmp_path / "warehouse.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE orders (id INTEGER)")
    warehouse = Warehouse(
        f"sqlite://{path}",
        context={"tables": [{"name": "finance.orders", "owner": "Finance"}]},
    )
    try:
        assert warehouse.table_context("orders") == {"name": "orders"}
        assert warehouse.search_tables({"query": "Finance"}) == {"tables": []}
    finally:
        warehouse.close()
