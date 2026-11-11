"""Offline checks: python -m pytest examples/agents_api/apps/data_analyst/tests."""

import sqlite3
from contextlib import closing

import pytest

from examples.agents_api.apps.data_analyst.warehouse import Warehouse


@pytest.mark.parametrize(
    ("context_name", "requested_name", "matches"),
    [
        ("finance.orders", "finance.orders", True),
        ("finance.orders", "staging.orders", False),
        ("finance.orders", "orders", False),
        ("finance.orders", "staging.customers", False),
        ("orders", "finance.orders", True),
        ("orders", "staging.orders", True),
        ("orders", "orders", True),
    ],
)
def test_table_context_respects_qualified_names(context_name, requested_name, matches):
    warehouse = object.__new__(Warehouse)
    record = {"name": context_name, "owner": "Finance"}
    warehouse.context = {"tables": [record]}

    expected = record if matches else {"name": requested_name}
    assert warehouse.table_context(requested_name) == expected


def test_exact_context_takes_precedence_over_unqualified_fallback():
    warehouse = object.__new__(Warehouse)
    generic = {"name": "orders", "owner": "Shared"}
    finance = {"name": "finance.orders", "owner": "Finance"}
    staging = {"name": "staging.orders", "owner": "Data Engineering"}
    warehouse.context = {"tables": [generic, finance, staging]}

    assert warehouse.table_context("finance.orders") == finance
    assert warehouse.table_context("staging.orders") == staging
    assert warehouse.table_context("other.orders") == generic


@pytest.mark.parametrize("context_name", ["finance.orders", "orders"])
def test_inspect_and_search_use_only_applicable_context(tmp_path, context_name):
    path = tmp_path / "warehouse.db"
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("CREATE TABLE orders (id INTEGER)")

    warehouse = Warehouse(
        f"sqlite://{path}",
        context={"tables": [{"name": context_name, "owner": "Finance"}]},
        memory_path=tmp_path / "memories.json",
    )
    try:
        table = warehouse.inspect_table({"table": "orders"})
        assert table["name"] == "orders"
        assert table["columns"] == [{"name": "id", "type": "INTEGER", "nullable": True}]
        if context_name == "orders":
            assert table["owner"] == "Finance"
            assert warehouse.search_tables({"query": "Finance"}) == {"tables": [table]}
        else:
            assert "owner" not in table
            assert warehouse.search_tables({"query": "Finance"}) == {"tables": []}
        assert warehouse.search_tables({"query": "orders"}) == {"tables": [table]}
    finally:
        warehouse.close()
