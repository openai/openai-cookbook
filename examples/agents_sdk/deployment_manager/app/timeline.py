from __future__ import annotations

import json
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import ContainerInfo, Deployment, Project, SessionInfo, TimelineEvent
from .trace_store import TraceStore


def _event_id() -> str:
    return uuid.uuid4().hex[:12]


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _data_dir(project: Project, deployment: Deployment) -> Path:
    return (
        Path(deployment.data_path)
        if deployment.data_path
        else Path(project.path) / "data"
    )


def _task_events(
    project: Project, deployment: Deployment
) -> list[tuple[str, Path, list[dict[str, Any]]]]:
    task_dir = _data_dir(project, deployment) / "task_state"
    if not task_dir.exists():
        return []
    sessions: list[tuple[str, Path, list[dict[str, Any]]]] = []
    for path in sorted(task_dir.glob("*.events.jsonl")):
        events: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                payload = {"type": "raw", "message": line}
            events.append(payload)
        sessions.append((path.stem.removesuffix(".events"), path, events))
    return sessions


def _expense_statuses(
    project: Project, deployment: Deployment
) -> dict[str, dict[str, Any]]:
    state_path = _data_dir(project, deployment) / "expenses.json"
    if not state_path.exists():
        return {}
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    expenses = payload.get("expenses", [])
    if not isinstance(expenses, list):
        return {}
    return {
        str(expense.get("id")): expense
        for expense in expenses
        if isinstance(expense, dict) and expense.get("id")
    }


def _research_runs(project: Project, deployment: Deployment) -> list[dict[str, Any]]:
    state_path = _data_dir(project, deployment) / "runs.json"
    if not state_path.exists():
        return []
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict) and item.get("id")]


def list_sessions(
    project: Project, deployment: Deployment, trace_store: TraceStore | None = None
) -> list[SessionInfo]:
    results: list[SessionInfo] = []
    captured_sessions = _captured_trace_sessions(trace_store, project, deployment)
    used_captured_sessions: set[str] = set()
    expense_statuses = _expense_statuses(project, deployment)
    for expense_id, path, events in _task_events(project, deployment):
        updated = datetime.fromtimestamp(path.stat().st_mtime).isoformat(
            timespec="seconds"
        )
        expense = expense_statuses.get(expense_id, {})
        trace_id, trace_url = _trace_info_from_events(events)
        timeline_events = _semantic_events(
            _events_from_payloads(expense_id, path, events)
        )
        captured_session = captured_sessions.get(expense_id)
        if captured_session:
            used_captured_sessions.add(expense_id)
            timeline_events = []
            trace_id = captured_session.trace_id or trace_id
            trace_url = captured_session.trace_url or trace_url
        if expense.get("review_running"):
            status = "running"
        else:
            status = str(expense.get("status") or "completed")
            if events:
                joined = "\n".join(
                    str(event.get("message", "")) for event in events[-3:]
                )
                if "failed" in joined.lower() or "error" in joined.lower():
                    status = "failed"
        results.append(
            SessionInfo(
                id=f"{deployment.id}:{expense_id}",
                deployment_id=deployment.id,
                project_id=project.id,
                deployment_name=deployment.name,
                project_name=project.name,
                expense_id=expense_id,
                status=status,
                event_count=captured_session.event_count
                if captured_session
                else len(timeline_events),
                trace_id=trace_id,
                trace_url=trace_url,
                started_at=updated,
                updated_at=updated,
            )
        )
    for run in _research_runs(project, deployment):
        run_id = str(run.get("id"))
        captured_session = captured_sessions.get(run_id)
        if captured_session:
            used_captured_sessions.add(run_id)
        events = run.get("events", [])
        event_count = len(events) if isinstance(events, list) else 0
        if run.get("trace_id"):
            event_count += 1
        results.append(
            SessionInfo(
                id=f"{deployment.id}:{run_id}",
                deployment_id=deployment.id,
                project_id=project.id,
                deployment_name=deployment.name,
                project_name=project.name,
                expense_id=run_id,
                status=str(run.get("status") or "completed"),
                event_count=captured_session.event_count
                if captured_session
                else event_count,
                trace_id=captured_session.trace_id
                if captured_session
                else str(run.get("trace_id"))
                if run.get("trace_id")
                else None,
                trace_url=captured_session.trace_url
                if captured_session
                else str(run.get("trace_url"))
                if run.get("trace_url")
                else None,
                started_at=str(run.get("created_at") or ""),
                updated_at=str(run.get("updated_at") or run.get("created_at") or ""),
            )
        )
    for key, session in captured_sessions.items():
        if key not in used_captured_sessions:
            results.append(session)
    return sorted(results, key=lambda item: item.updated_at or "", reverse=True)


def _trace_info_from_events(
    events: list[dict[str, Any]],
) -> tuple[str | None, str | None]:
    for event in events:
        trace_id = event.get("trace_id") or event.get("traceId")
        if trace_id:
            trace_url = event.get("trace_url") or event.get("traceUrl")
            return str(trace_id), str(trace_url) if trace_url else None
    return None, None


def timeline_for_session(
    project: Project,
    deployment: Deployment,
    expense_id: str,
    trace_store: TraceStore | None = None,
) -> list[TimelineEvent]:
    events: list[TimelineEvent] = _captured_timeline_for_session(
        trace_store, project, deployment, expense_id
    )
    if not events:
        for current_expense_id, path, payloads in _task_events(project, deployment):
            if current_expense_id != expense_id:
                continue
            events = _semantic_events(_events_from_payloads(expense_id, path, payloads))
            break
    if not events:
        for run in _research_runs(project, deployment):
            if str(run.get("id")) != expense_id:
                continue
            timestamp = str(run.get("updated_at") or run.get("created_at") or _now())
            trace_id = run.get("trace_id")
            if trace_id:
                events.append(
                    TimelineEvent(
                        id=f"{expense_id}-trace",
                        timestamp=timestamp,
                        source="trace",
                        type="trace",
                        message="Created OpenAI platform trace for this research run.",
                        metadata={
                            "trace_id": trace_id,
                            "trace_url": run.get("trace_url"),
                            "query": run.get("query"),
                            "mode": run.get("mode"),
                        },
                    )
                )
            run_events = run.get("events", [])
            if isinstance(run_events, list):
                for index, payload in enumerate(run_events, 1):
                    if not isinstance(payload, dict):
                        continue
                    label = str(payload.get("label") or payload.get("type") or "event")
                    status = str(payload.get("status") or "complete")
                    events.append(
                        TimelineEvent(
                            id=f"{expense_id}-run-{index}",
                            timestamp=timestamp,
                            source="agent",
                            type=label.lower(),
                            message=str(payload.get("message") or label),
                            level="error"
                            if status.lower() in {"error", "failed"}
                            else "info",
                            metadata={
                                "status": status,
                                "query": run.get("query"),
                                "mode": run.get("mode"),
                                "trace_id": trace_id,
                                "trace_url": run.get("trace_url"),
                            },
                        )
                    )
            if run.get("summary"):
                events.append(
                    TimelineEvent(
                        id=f"{expense_id}-summary",
                        timestamp=timestamp,
                        source="agent",
                        type="summary",
                        message=str(run.get("summary")),
                        metadata={
                            "query": run.get("query"),
                            "mode": run.get("mode"),
                            "trace_id": trace_id,
                            "trace_url": run.get("trace_url"),
                        },
                    )
                )
            break
    if not events:
        events.append(
            TimelineEvent(
                id=_event_id(),
                timestamp=_now(),
                source="session",
                type="empty",
                message="No session events have been recorded yet.",
            )
        )
    return events


def _captured_traces(
    trace_store: TraceStore | None, project: Project, deployment: Deployment
) -> dict[str, dict[str, Any]]:
    if trace_store is None:
        return {}
    return trace_store.traces_for_deployment(deployment.id)


def _captured_trace_sessions(
    trace_store: TraceStore | None, project: Project, deployment: Deployment
) -> dict[str, SessionInfo]:
    sessions: dict[str, SessionInfo] = {}
    for trace in _captured_traces(trace_store, project, deployment).values():
        trace_id = str(trace.get("trace_id") or "")
        if not trace_id:
            continue
        key = _captured_trace_session_key(trace)
        events = _timeline_events_for_captured_trace(key, trace)
        updated_at = str(
            trace.get("ended_at") or _latest_trace_recorded_at(trace) or ""
        )
        started_at = str(trace.get("started_at") or updated_at)
        sessions[key] = SessionInfo(
            id=f"{deployment.id}:{key}",
            deployment_id=deployment.id,
            project_id=project.id,
            deployment_name=deployment.name,
            project_name=project.name,
            expense_id=key,
            status="completed" if trace.get("ended_at") else "running",
            event_count=len(events),
            trace_id=trace_id,
            trace_url=_platform_trace_url(trace_id),
            started_at=started_at,
            updated_at=updated_at,
        )
    return sessions


def _captured_timeline_for_session(
    trace_store: TraceStore | None,
    project: Project,
    deployment: Deployment,
    session_key: str,
) -> list[TimelineEvent]:
    for trace in _captured_traces(trace_store, project, deployment).values():
        if session_key in {
            _captured_trace_session_key(trace),
            str(trace.get("trace_id") or ""),
        }:
            return _timeline_events_for_captured_trace(session_key, trace)
    return []


def _captured_trace_session_key(trace: dict[str, Any]) -> str:
    metadata = trace.get("metadata")
    if isinstance(metadata, dict):
        for key in ("expense_id", "run_id", "session_id"):
            value = metadata.get(key)
            if value:
                return str(value)
    if trace.get("group_id"):
        return str(trace["group_id"])
    return str(trace.get("trace_id") or "trace")


def _latest_trace_recorded_at(trace: dict[str, Any]) -> str | None:
    records = trace.get("records")
    if not isinstance(records, list):
        return None
    for record in reversed(records):
        if isinstance(record, dict) and record.get("recorded_at"):
            return str(record["recorded_at"])
    return None


def _timeline_events_for_captured_trace(
    session_key: str, trace: dict[str, Any]
) -> list[TimelineEvent]:
    events: list[TimelineEvent] = []
    span_order = trace.get("span_order", [])
    spans = trace.get("spans", {})
    if isinstance(span_order, list) and isinstance(spans, dict):
        for span_id in span_order:
            span = spans.get(span_id)
            if not isinstance(span, dict):
                continue
            payload = span.get("end_payload") or span.get("payload")
            if not isinstance(payload, dict):
                continue
            span_data = payload.get("span_data")
            if not isinstance(span_data, dict):
                span_data = {}
            timestamp = str(
                payload.get("started_at")
                or span.get("started_recorded_at")
                or span.get("ended_recorded_at")
                or _latest_trace_recorded_at(trace)
                or _now()
            )
            span_type = str(span_data.get("type") or "span")
            name = _span_display_name(span_type, span_data)
            metadata = {
                "trace_id": trace.get("trace_id"),
                "trace_url": _platform_trace_url(str(trace.get("trace_id"))),
                "span_id": payload.get("id"),
                "parent_id": payload.get("parent_id"),
                "started_at": payload.get("started_at"),
                "ended_at": payload.get("ended_at"),
                "duration_ms": _duration_ms(
                    payload.get("started_at"), payload.get("ended_at")
                ),
                "span_data": span_data,
                "error": payload.get("error"),
            }
            events.append(
                TimelineEvent(
                    id=str(payload.get("id") or f"{session_key}-{len(events) + 1}"),
                    timestamp=timestamp,
                    source=_span_source(span_type, span_data),
                    type=name,
                    message=_span_message(name, span_type, span_data),
                    level="error" if payload.get("error") else "info",
                    metadata={
                        key: value
                        for key, value in metadata.items()
                        if value is not None
                    },
                )
            )
    if events:
        return events

    trace_id = str(trace.get("trace_id") or session_key)
    return [
        TimelineEvent(
            id=f"{session_key}-trace",
            timestamp=str(
                trace.get("started_at") or _latest_trace_recorded_at(trace) or _now()
            ),
            source="trace",
            type="trace",
            message=str(trace.get("workflow_name") or "OpenAI Agents trace"),
            metadata={
                "trace_id": trace_id,
                "trace_url": _platform_trace_url(trace_id),
                "group_id": trace.get("group_id"),
                "metadata": trace.get("metadata"),
            },
        )
    ]


def _span_display_name(span_type: str, span_data: dict[str, Any]) -> str:
    for key in ("name", "server_label", "tool_name"):
        value = span_data.get(key)
        if value:
            return str(value)
    return span_type


def _span_message(name: str, span_type: str, span_data: dict[str, Any]) -> str:
    if span_type == "response":
        return "POST /v1/responses"
    if span_type == "generation":
        return "LLM generation"
    return name


def _span_source(span_type: str, span_data: dict[str, Any]) -> str:
    name = str(span_data.get("name") or "")
    if span_type in {"function", "mcp_tools"}:
        return "tool"
    if span_type in {"agent", "generation", "response", "handoff", "guardrail"}:
        return "agent"
    if span_type == "custom" and name in {"task", "turn"}:
        return "session"
    if span_type == "custom" and name.startswith("sandbox."):
        return "sandbox"
    if span_type in {"task", "turn"}:
        return "session"
    return "trace"


def _duration_ms(started_at: Any, ended_at: Any) -> int | None:
    if not started_at or not ended_at:
        return None
    try:
        started = datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
        ended = datetime.fromisoformat(str(ended_at).replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(0, int((ended - started).total_seconds() * 1000))


def _platform_trace_url(trace_id: str) -> str:
    return f"https://platform.openai.com/traces/trace?trace_id={trace_id}"


def _events_from_payloads(
    expense_id: str, path: Path, payloads: list[dict[str, Any]]
) -> list[TimelineEvent]:
    base_time = datetime.fromtimestamp(path.stat().st_mtime).isoformat(
        timespec="seconds"
    )
    events: list[TimelineEvent] = []
    for index, payload in enumerate(payloads, 1):
        event_type = str(payload.get("type", "event"))
        message = str(payload.get("message", event_type))
        source = "session"
        if "trace" in event_type:
            source = "trace"
        elif "tool" in event_type:
            source = "tool"
        elif "approval" in event_type:
            source = "approval"
        elif "sandbox" in event_type:
            source = "sandbox"
        events.append(
            TimelineEvent(
                id=f"{expense_id}-{index}",
                timestamp=str(
                    payload.get("timestamp") or payload.get("created_at") or base_time
                ),
                source=source,
                type=event_type,
                message=message,
                level="error"
                if "error" in event_type or "failed" in message.lower()
                else "info",
                metadata={
                    k: v for k, v in payload.items() if k not in {"type", "message"}
                },
            )
        )
    return events


def _semantic_events(events: list[TimelineEvent]) -> list[TimelineEvent]:
    return _compact_tool_events(_compact_assistant_deltas(events))


def _compact_assistant_deltas(events: list[TimelineEvent]) -> list[TimelineEvent]:
    compacted: list[TimelineEvent] = []
    pending: list[TimelineEvent] = []
    group_index = 0

    def flush() -> None:
        nonlocal group_index
        if not pending:
            return
        group_index += 1
        message = "".join(event.message for event in pending).strip()
        if message:
            compacted.append(
                TimelineEvent(
                    id=f"{pending[0].id}-assistant-message-{group_index}",
                    timestamp=pending[0].timestamp,
                    source="agent",
                    type="model_response",
                    message=message,
                    metadata={
                        "delta_count": len(pending),
                        "event_name": "response_text_delta",
                    },
                )
            )
        pending.clear()

    for event in events:
        if event.type == "assistant_delta":
            pending.append(event)
            continue
        flush()
        compacted.append(event)
    flush()
    return compacted


def _compact_tool_events(events: list[TimelineEvent]) -> list[TimelineEvent]:
    compacted: list[TimelineEvent] = []
    pending_index: dict[str, int] = {}

    for event in events:
        if event.source != "tool":
            compacted.append(event)
            continue

        event_name = str(event.metadata.get("event_name", ""))
        call_id = str(event.metadata.get("call_id", ""))
        if event_name == "tool_called":
            compacted.append(_tool_action_event(event))
            if call_id:
                pending_index[call_id] = len(compacted) - 1
            continue

        if event_name == "tool_output" and call_id and call_id in pending_index:
            index = pending_index.pop(call_id)
            compacted[index] = _merge_tool_action(compacted[index], event)
            continue

        compacted.append(_tool_action_event(event))

    return compacted


def _tool_action_event(event: TimelineEvent) -> TimelineEvent:
    tool_name = str(event.metadata.get("tool_name") or event.type or "tool")
    event_name = str(event.metadata.get("event_name", ""))
    action_state = "completed" if event_name == "tool_output" else "started"
    metadata = dict(event.metadata)
    return TimelineEvent(
        id=event.id,
        timestamp=event.timestamp,
        source="tool",
        type=tool_name,
        message=f"{tool_name} {action_state}.",
        level=event.level,
        metadata=metadata,
    )


def _merge_tool_action(
    call_event: TimelineEvent, output_event: TimelineEvent
) -> TimelineEvent:
    metadata = dict(call_event.metadata)
    output_preview = output_event.metadata.get("output_preview")
    if output_preview:
        metadata["output_preview"] = output_preview
    metadata["completed_at"] = output_event.timestamp
    metadata["output_event_id"] = output_event.id
    return TimelineEvent(
        id=call_event.id,
        timestamp=call_event.timestamp,
        source="tool",
        type=call_event.type,
        message=f"{call_event.type} completed.",
        level="error" if output_event.level == "error" else call_event.level,
        metadata=metadata,
    )


def docker_containers(
    limit: int = 30, deployment_id: str | None = None
) -> list[ContainerInfo]:
    command = [
        "docker",
        "ps",
        "-a",
    ]
    if deployment_id:
        command.extend(["--filter", f"label=agents-sdk.deployment-id={deployment_id}"])
    command.extend(
        [
            "--format",
            "{{json .}}",
        ]
    )
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    if completed.returncode != 0:
        return []
    containers: list[ContainerInfo] = []
    for line in completed.stdout.splitlines()[:limit]:
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        labels = _inspect_labels(str(payload.get("ID", "")))
        containers.append(
            ContainerInfo(
                id=str(payload.get("ID", "")),
                name=str(payload.get("Names", "")),
                image=str(payload.get("Image", "")),
                status=str(payload.get("Status", "")),
                created_at=str(payload.get("CreatedAt", "")),
                role=labels.get("agents-sdk.role")
                or (
                    "sandbox"
                    if "python" in str(payload.get("Image", "")).lower()
                    else "observed"
                ),
                labels=labels,
            )
        )
    return containers


def docker_logs(container_id: str, limit: int = 200) -> str:
    try:
        completed = subprocess.run(
            ["docker", "logs", "--tail", str(limit), container_id],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    return (completed.stdout or "") + (completed.stderr or "")


def _inspect_labels(container_id: str) -> dict[str, str]:
    if not container_id:
        return {}
    try:
        completed = subprocess.run(
            ["docker", "inspect", container_id, "--format", "{{json .Config.Labels}}"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {}
    if completed.returncode != 0 or not completed.stdout.strip():
        return {}
    try:
        labels = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {}
    if not isinstance(labels, dict):
        return {}
    return {
        str(key): str(value)
        for key, value in labels.items()
        if str(key).startswith("agents-sdk.")
    }
