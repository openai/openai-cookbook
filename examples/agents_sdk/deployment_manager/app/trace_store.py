from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, default=str, separators=(",", ":"))


def _loads(value: str | None) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _duration_ms(started_at: Any, ended_at: Any) -> int | None:
    if not started_at or not ended_at:
        return None
    try:
        started = datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
        ended = datetime.fromisoformat(str(ended_at).replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(0, int((ended - started).total_seconds() * 1000))


def _payload(record: dict[str, Any]) -> dict[str, Any]:
    payload = record.get("payload")
    return payload if isinstance(payload, dict) else record


def _trace_id(record: dict[str, Any], payload: dict[str, Any]) -> str:
    return str(
        payload.get("trace_id") or payload.get("id") or record.get("trace_id") or ""
    )


def _span_id(record: dict[str, Any], payload: dict[str, Any]) -> str | None:
    span_id = payload.get("id") or record.get("span_id")
    return str(span_id) if span_id else None


def _run_id(payload: dict[str, Any]) -> str | None:
    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        for key in ("expense_id", "run_id", "session_id"):
            value = metadata.get(key)
            if value:
                return str(value)
    group_id = payload.get("group_id")
    return str(group_id) if group_id else None


def _span_name(span_data: dict[str, Any]) -> str | None:
    for key in ("name", "server_label", "tool_name"):
        value = span_data.get(key)
        if value:
            return str(value)
    span_type = span_data.get("type")
    return str(span_type) if span_type else None


class TraceStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_schema(self) -> None:
        with self._lock, self._connect() as connection:
            connection.executescript(
                """
                create table if not exists traces (
                  trace_id text primary key,
                  deployment_id text,
                  project_id text,
                  workflow_name text,
                  group_id text,
                  run_id text,
                  status text,
                  started_at text,
                  ended_at text,
                  updated_at text,
                  metadata_json text,
                  raw_json text
                );

                create table if not exists spans (
                  span_id text primary key,
                  trace_id text not null,
                  parent_id text,
                  span_type text,
                  name text,
                  started_at text,
                  ended_at text,
                  duration_ms integer,
                  error_json text,
                  span_data_json text,
                  raw_json text,
                  foreign key(trace_id) references traces(trace_id)
                );

                create table if not exists trace_events (
                  id integer primary key autoincrement,
                  trace_id text not null,
                  span_id text,
                  deployment_id text,
                  project_id text,
                  event_type text not null,
                  received_at text not null,
                  raw_json text not null
                );

                create index if not exists idx_trace_events_trace_id
                  on trace_events(trace_id, id);
                create index if not exists idx_traces_deployment_id
                  on traces(deployment_id, updated_at);
                create index if not exists idx_spans_trace_id
                  on spans(trace_id);
                """
            )

    def ingest_many(self, records: list[dict[str, Any]]) -> int:
        count = 0
        for record in records:
            if self.ingest(record):
                count += 1
        return count

    def ingest(self, record: dict[str, Any]) -> bool:
        payload = _payload(record)
        trace_id = _trace_id(record, payload)
        if not trace_id:
            return False

        event_type = str(record.get("event") or record.get("capture_event") or "")
        if not event_type:
            event_type = "trace_event"
        received_at = str(
            record.get("recorded_at") or record.get("received_at") or _now()
        )
        deployment_id = _string_or_none(record.get("deployment_id"))
        project_id = _string_or_none(record.get("project_id"))
        span_id = _span_id(record, payload)

        with self._lock, self._connect() as connection:
            self._upsert_trace(
                connection, record, payload, trace_id, event_type, received_at
            )
            if payload.get("object") == "trace.span" and span_id:
                self._upsert_span(connection, payload, trace_id, span_id)
            connection.execute(
                """
                insert into trace_events
                  (trace_id, span_id, deployment_id, project_id, event_type, received_at, raw_json)
                values (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trace_id,
                    span_id,
                    deployment_id,
                    project_id,
                    event_type,
                    received_at,
                    _json(record),
                ),
            )
        return True

    def _upsert_trace(
        self,
        connection: sqlite3.Connection,
        record: dict[str, Any],
        payload: dict[str, Any],
        trace_id: str,
        event_type: str,
        received_at: str,
    ) -> None:
        metadata = (
            payload.get("metadata")
            if isinstance(payload.get("metadata"), dict)
            else None
        )
        workflow_name = _string_or_none(payload.get("workflow_name"))
        group_id = _string_or_none(payload.get("group_id"))
        run_id = _run_id(payload)
        started_at = _string_or_none(payload.get("started_at"))
        ended_at = _string_or_none(payload.get("ended_at"))
        if event_type == "trace_start":
            started_at = started_at or received_at
        if event_type == "trace_end":
            ended_at = ended_at or received_at
        status = "completed" if event_type == "trace_end" else "running"

        connection.execute(
            """
            insert into traces
              (trace_id, deployment_id, project_id, workflow_name, group_id, run_id, status,
               started_at, ended_at, updated_at, metadata_json, raw_json)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(trace_id) do update set
              deployment_id = coalesce(excluded.deployment_id, traces.deployment_id),
              project_id = coalesce(excluded.project_id, traces.project_id),
              workflow_name = coalesce(excluded.workflow_name, traces.workflow_name),
              group_id = coalesce(excluded.group_id, traces.group_id),
              run_id = coalesce(excluded.run_id, traces.run_id),
              status = case
                when excluded.status = 'completed' then excluded.status
                else coalesce(traces.status, excluded.status)
              end,
              started_at = coalesce(traces.started_at, excluded.started_at),
              ended_at = coalesce(excluded.ended_at, traces.ended_at),
              updated_at = excluded.updated_at,
              metadata_json = coalesce(excluded.metadata_json, traces.metadata_json),
              raw_json = excluded.raw_json
            """,
            (
                trace_id,
                _string_or_none(record.get("deployment_id")),
                _string_or_none(record.get("project_id")),
                workflow_name,
                group_id,
                run_id,
                status,
                started_at,
                ended_at,
                received_at,
                _json(metadata) if metadata is not None else None,
                _json(payload),
            ),
        )

    def _upsert_span(
        self,
        connection: sqlite3.Connection,
        payload: dict[str, Any],
        trace_id: str,
        span_id: str,
    ) -> None:
        span_data = (
            payload.get("span_data")
            if isinstance(payload.get("span_data"), dict)
            else {}
        )
        started_at = _string_or_none(payload.get("started_at"))
        ended_at = _string_or_none(payload.get("ended_at"))
        connection.execute(
            """
            insert into spans
              (span_id, trace_id, parent_id, span_type, name, started_at, ended_at, duration_ms,
               error_json, span_data_json, raw_json)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(span_id) do update set
              trace_id = excluded.trace_id,
              parent_id = coalesce(excluded.parent_id, spans.parent_id),
              span_type = coalesce(excluded.span_type, spans.span_type),
              name = coalesce(excluded.name, spans.name),
              started_at = coalesce(excluded.started_at, spans.started_at),
              ended_at = coalesce(excluded.ended_at, spans.ended_at),
              duration_ms = coalesce(excluded.duration_ms, spans.duration_ms),
              error_json = coalesce(excluded.error_json, spans.error_json),
              span_data_json = coalesce(excluded.span_data_json, spans.span_data_json),
              raw_json = excluded.raw_json
            """,
            (
                span_id,
                trace_id,
                _string_or_none(payload.get("parent_id")),
                _string_or_none(span_data.get("type")),
                _span_name(span_data),
                started_at,
                ended_at,
                _duration_ms(started_at, ended_at),
                _json(payload.get("error"))
                if payload.get("error") is not None
                else None,
                _json(span_data),
                _json(payload),
            ),
        )

    def traces_for_deployment(self, deployment_id: str) -> dict[str, dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                select * from traces
                where deployment_id = ?
                order by coalesce(updated_at, ended_at, started_at, trace_id) desc
                """,
                (deployment_id,),
            ).fetchall()
            return {
                str(row["trace_id"]): self._trace_from_events(connection, row)
                for row in rows
            }

    def trace_summaries(self, deployment_id: str | None = None) -> list[dict[str, Any]]:
        query = "select * from traces"
        params: tuple[Any, ...] = ()
        if deployment_id:
            query += " where deployment_id = ?"
            params = (deployment_id,)
        query += " order by coalesce(updated_at, ended_at, started_at, trace_id) desc"
        with self._connect() as connection:
            return [
                _trace_summary(row)
                for row in connection.execute(query, params).fetchall()
            ]

    def delete_deployment(self, deployment_id: str) -> int:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "select trace_id from traces where deployment_id = ?",
                (deployment_id,),
            ).fetchall()
            trace_ids = [str(row["trace_id"]) for row in rows]
            connection.execute(
                "delete from trace_events where deployment_id = ?",
                (deployment_id,),
            )
            if trace_ids:
                placeholders = ",".join("?" for _ in trace_ids)
                connection.execute(
                    f"delete from trace_events where trace_id in ({placeholders})",
                    trace_ids,
                )
                connection.execute(
                    f"delete from spans where trace_id in ({placeholders})",
                    trace_ids,
                )
                connection.execute(
                    f"delete from traces where trace_id in ({placeholders})",
                    trace_ids,
                )
            return len(trace_ids)

    def spans_for_trace(self, trace_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "select raw_json from spans where trace_id = ? order by started_at, span_id",
                (trace_id,),
            ).fetchall()
        return [
            payload
            for row in rows
            if isinstance((payload := _loads(row["raw_json"])), dict)
        ]

    def _trace_from_events(
        self, connection: sqlite3.Connection, row: sqlite3.Row
    ) -> dict[str, Any]:
        trace = {
            "trace_id": row["trace_id"],
            "records": [],
            "spans": {},
            "span_order": [],
            "metadata": _loads(row["metadata_json"]) or {},
            "workflow_name": row["workflow_name"],
            "group_id": row["group_id"],
            "started_at": row["started_at"],
            "ended_at": row["ended_at"],
        }
        events = connection.execute(
            "select * from trace_events where trace_id = ? order by id",
            (row["trace_id"],),
        ).fetchall()
        for event in events:
            record = _loads(event["raw_json"])
            if not isinstance(record, dict):
                continue
            payload = _payload(record)
            trace["records"].append(record)
            if payload.get("object") == "trace":
                trace["workflow_name"] = payload.get("workflow_name") or trace.get(
                    "workflow_name"
                )
                trace["group_id"] = payload.get("group_id") or trace.get("group_id")
                if isinstance(payload.get("metadata"), dict):
                    trace["metadata"] = payload["metadata"]
                if event["event_type"] == "trace_start":
                    trace["started_at"] = (
                        record.get("recorded_at") or event["received_at"]
                    )
                elif event["event_type"] == "trace_end":
                    trace["ended_at"] = (
                        record.get("recorded_at") or event["received_at"]
                    )
                continue
            if payload.get("object") != "trace.span":
                continue
            span_id = _span_id(record, payload)
            if not span_id:
                continue
            spans = trace["spans"]
            if span_id not in spans:
                spans[span_id] = {}
                trace["span_order"].append(span_id)
            span = spans[span_id]
            if event["event_type"] == "span_start":
                span["start_payload"] = payload
                span["started_recorded_at"] = (
                    record.get("recorded_at") or event["received_at"]
                )
            elif event["event_type"] == "span_end":
                span["end_payload"] = payload
                span["ended_recorded_at"] = (
                    record.get("recorded_at") or event["received_at"]
                )
            span["payload"] = payload
        return trace


def _string_or_none(value: Any) -> str | None:
    return str(value) if value is not None and value != "" else None


def _trace_summary(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "trace_id": row["trace_id"],
        "deployment_id": row["deployment_id"],
        "project_id": row["project_id"],
        "workflow_name": row["workflow_name"],
        "group_id": row["group_id"],
        "run_id": row["run_id"],
        "status": row["status"],
        "started_at": row["started_at"],
        "ended_at": row["ended_at"],
        "updated_at": row["updated_at"],
        "metadata": _loads(row["metadata_json"]) or {},
    }
