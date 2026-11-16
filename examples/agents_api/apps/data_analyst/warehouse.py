"""Inspect warehouse schemas and run read-only queries."""

from __future__ import annotations

import importlib
import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, cast
from urllib.parse import unquote, urlparse

from .memory import MemoryStore, relevant

EXAMPLE_DIR = Path(__file__).resolve().parent
MAX_ROWS = 100


class Warehouse:
    """Expose an existing warehouse through a read-only, application-owned connection."""

    def __init__(
        self,
        url: str | None = None,
        *,
        context: dict[str, Any] | None = None,
        context_path: Path | None = None,
        memory_path: Path | None = None,
    ) -> None:
        self.url = url or os.environ.get("WAREHOUSE_URL")
        if not self.url:
            raise ValueError("Set WAREHOUSE_URL to a read-only PostgreSQL connection.")

        configured_context = os.environ.get("DATA_AGENT_CONTEXT")
        if context is not None:
            self.context = context
        elif context_path is not None or configured_context:
            path = context_path or Path(str(configured_context))
            self.context = cast(dict[str, Any], json.loads(path.read_text()))
        else:
            self.context = {}

        self.memory = MemoryStore(memory_path or EXAMPLE_DIR / "memories.json")

        parsed = urlparse(self.url)
        self.connection: Any
        if parsed.scheme in {"postgres", "postgresql"}:
            self.engine = "PostgreSQL"
            try:
                psycopg = importlib.import_module("psycopg")
                rows = importlib.import_module("psycopg.rows")
            except ModuleNotFoundError as error:
                raise RuntimeError(
                    "PostgreSQL requires psycopg. Start the example with "
                    "`uv run examples/agents_api/apps/data_analyst/main.py`."
                ) from error
            self.connection = psycopg.connect(
                self.url,
                autocommit=True,
                row_factory=rows.dict_row,
                options="-c default_transaction_read_only=on -c statement_timeout=30000",
            )
        elif parsed.scheme == "sqlite":
            self.engine = "SQLite"
            path = Path(unquote(parsed.path)).resolve()
            self.connection = sqlite3.connect(
                f"file:{path}?mode=ro", uri=True, check_same_thread=False
            )
            self.connection.row_factory = sqlite3.Row
        else:
            raise ValueError("WAREHOUSE_URL must use postgresql:// or sqlite:///.")

    def records(self, section: str) -> list[dict[str, Any]]:
        records = self.context.get(section, [])
        if not isinstance(records, list):
            return []
        return [
            cast(dict[str, Any], record)
            for record in records
            if isinstance(record, dict)
        ]

    def table_names(self) -> list[str]:
        cursor = self.connection.cursor()
        if self.engine == "PostgreSQL":
            cursor.execute(
                "SELECT table_schema, table_name FROM information_schema.tables "
                "WHERE table_schema NOT IN ('information_schema', 'pg_catalog') "
                "AND table_type IN ('BASE TABLE', 'VIEW') "
                "ORDER BY table_schema, table_name"
            )
            return [
                f"{row['table_schema']}.{row['table_name']}"
                for row in cursor.fetchall()
            ]

        cursor.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        return [str(row["name"]) for row in cursor.fetchall()]

    def table_context(self, name: str) -> dict[str, Any]:
        records = self.records("tables")
        for record in records:
            if record.get("name") == name:
                return record

        table_name = name.rsplit(".", maxsplit=1)[-1]
        return next(
            (
                record
                for record in records
                if str(record.get("name", "")).rsplit(".", maxsplit=1)[-1] == table_name
            ),
            {"name": name},
        )

    def search_tables(self, arguments: dict[str, Any]) -> dict[str, Any]:
        query = str(arguments.get("query", ""))
        names = [
            name
            for name in self.table_names()
            if relevant(self.table_context(name), query)
        ][:20]
        return {"tables": [self.inspect_table({"table": name}) for name in names]}

    def inspect_table(self, arguments: dict[str, Any]) -> dict[str, Any]:
        name = str(arguments.get("table", ""))
        if name not in self.table_names():
            raise ValueError(f"Unknown warehouse table: {name}")

        cursor = self.connection.cursor()
        if self.engine == "PostgreSQL":
            schema, table = name.split(".", maxsplit=1)
            cursor.execute(
                "SELECT column_name, data_type, is_nullable "
                "FROM information_schema.columns "
                "WHERE table_schema = %s AND table_name = %s ORDER BY ordinal_position",
                (schema, table),
            )
            columns: list[dict[str, Any]] = [
                {
                    "name": str(row["column_name"]),
                    "type": str(row["data_type"]),
                    "nullable": row["is_nullable"] == "YES",
                }
                for row in cursor.fetchall()
            ]
        else:
            escaped = name.replace('"', '""')
            cursor.execute(f'PRAGMA table_info("{escaped}")')
            columns = [
                {
                    "name": str(row["name"]),
                    "type": str(row["type"]),
                    "nullable": not bool(row["notnull"]),
                }
                for row in cursor.fetchall()
            ]

        return {**self.table_context(name), "name": name, "columns": columns}

    def search_query_history(self, arguments: dict[str, Any]) -> dict[str, Any]:
        query = str(arguments.get("query", ""))
        return {
            "queries": [
                record
                for record in self.records("query_history")
                if relevant(record, query)
            ][:10]
        }

    def search_company_knowledge(self, arguments: dict[str, Any]) -> dict[str, Any]:
        query = str(arguments.get("query", ""))
        return {
            "metrics": [
                record for record in self.records("metrics") if relevant(record, query)
            ][:10],
            "documents": [
                record
                for record in self.records("documents")
                if relevant(record, query)
            ][:10],
        }

    def search_context(
        self, arguments: dict[str, Any], *, user_id: str = "analyst"
    ) -> dict[str, Any]:
        return {
            **self.search_company_knowledge(arguments),
            **self.search_query_history(arguments),
            **self.memory.search(arguments, user_id=user_id),
        }

    def query(self, arguments: dict[str, Any]) -> dict[str, Any]:
        sql = str(arguments.get("sql", "")).strip().rstrip(";")
        if not re.match(r"^(SELECT|WITH)\b", sql, re.IGNORECASE) or ";" in sql:
            raise ValueError("Only one read-only SELECT query is allowed.")

        cursor = self.connection.cursor()
        cursor.execute(sql)
        rows = [dict(row) for row in cursor.fetchmany(MAX_ROWS)]
        serialized = cast(
            list[dict[str, Any]], json.loads(json.dumps(rows, default=str))
        )
        return {"sql": sql, "rows": serialized, "row_count": len(serialized)}

    def summary(self, *, user_id: str = "analyst") -> dict[str, Any]:
        return {
            "engine": self.engine,
            "tables": len(self.table_names()),
            "metrics": len(self.records("metrics")),
            "documents": len(self.records("documents")),
            "memories": len(self.memory.list(user_id=user_id)),
        }

    def close(self) -> None:
        self.connection.close()
