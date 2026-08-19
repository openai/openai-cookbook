from __future__ import annotations

import json
import math
import os
import re
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Sequence

import pandas as pd

DEFAULT_DATA_DIR = Path("data")
DEFAULT_DOC_COLUMNS = (
    "doc_full_trace",
    "doc_failure_window",
    "doc_state_transition_summary",
    "doc_tool_error_summary",
    "doc_structured_summary",
)
OUTCOME_GROUP_MAP = {
    "completed": "successful_completion",
    "accepted": "review_escalation",
    "failed": "hard_failure",
}
SEVERITY_BY_OUTCOME = {
    "successful_completion": ("low", 1.0),
    "review_escalation": ("medium", 2.0),
    "hard_failure": ("high", 3.0),
}
STAGE_LABELS = ("early", "middle", "late")
STATUS_SORT_PRIORITY = {
    "status": 0,
    "handoff": 1,
    "agent": 2,
    "response": 3,
    "function": 4,
    "finding": 5,
}
FAILURE_TEXT_MARKERS = (
    "severity='error'",
    'severity="error"',
    "issues_found",
    "awaiting_review",
    "failed",
    "request_changes",
    "warning",
    "retry",
)


def resolve_dataset_root(data_dir: str | Path = DEFAULT_DATA_DIR) -> Path:
    data_dir = Path(data_dir)
    candidates: list[tuple[int, int, str, Path]] = []
    result_paths = list(data_dir.rglob("results.jsonl")) + list(
        data_dir.rglob("trace_results.jsonl")
    )
    for results_path in result_paths:
        dataset_root = results_path.parent
        summary = (
            _safe_json_loads(dataset_root / "summary.json")
            or _safe_json_loads(dataset_root / "run_summary.json")
            or {}
        )
        trace_count = int(
            summary.get("count")
            or summary.get("requested_runs")
            or summary.get("batch_size")
            or 0
        )
        bundle_bytes = (
            (dataset_root / "bundles.zip").stat().st_size
            if (dataset_root / "bundles.zip").exists()
            else 0
        )
        candidates.append((trace_count, bundle_bytes, dataset_root.name, dataset_root))

    if not candidates:
        raise FileNotFoundError(f"Could not find a dataset root under {data_dir}.")

    return max(candidates)[-1]


def load_results_records(
    dataset_root: str | Path | None = None,
    data_dir: str | Path = DEFAULT_DATA_DIR,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    dataset_root = (
        Path(dataset_root) if dataset_root else resolve_dataset_root(data_dir)
    )
    results_path = _first_existing_path(
        dataset_root / "results.jsonl",
        dataset_root / "trace_results.jsonl",
    )
    rows: list[dict[str, Any]] = []
    with results_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
            if limit is not None and len(rows) >= limit:
                break
    return rows


def load_trace_tables(
    dataset_root: str | Path | None = None,
    data_dir: str | Path = DEFAULT_DATA_DIR,
    limit: int | None = None,
    max_workers: int | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    dataset_root = (
        Path(dataset_root) if dataset_root else resolve_dataset_root(data_dir)
    )
    results_rows = load_results_records(dataset_root=dataset_root, limit=limit)

    if max_workers is None:
        max_workers = min(8, os.cpu_count() or 1)
    max_workers = max(1, min(max_workers, len(results_rows) or 1))

    if max_workers == 1:
        normalized_rows = [
            _load_and_normalize_result_row(dataset_root, result_row, record_index)
            for record_index, result_row in enumerate(results_rows, start=1)
        ]
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(
                    _load_and_normalize_result_row,
                    dataset_root,
                    result_row,
                    record_index,
                )
                for record_index, result_row in enumerate(results_rows, start=1)
            ]
            normalized_rows = [future.result() for future in futures]

    trace_rows = [trace_row for trace_row, _ in normalized_rows]
    event_rows = [
        event for _, trace_events in normalized_rows for event in trace_events
    ]

    traces_df = pd.DataFrame(trace_rows)
    events_df = pd.DataFrame(event_rows)

    if traces_df.empty:
        return traces_df, events_df

    if not events_df.empty:
        events_df["ts"] = pd.to_datetime(events_df["ts"], utc=True, errors="coerce")
        events_df["ended_at"] = pd.to_datetime(
            events_df["ended_at"], utc=True, errors="coerce"
        )
        events_df = events_df.sort_values(
            ["trace_id", "sequence_index", "ts", "event_id"]
        ).reset_index(drop=True)

    traces_df["trace_started_at"] = pd.to_datetime(
        traces_df["trace_started_at"], utc=True, errors="coerce"
    )
    traces_df["trace_ended_at"] = pd.to_datetime(
        traces_df["trace_ended_at"], utc=True, errors="coerce"
    )
    traces_df["simulation_date"] = pd.to_datetime(
        traces_df["simulation_date"], errors="coerce"
    )
    traces_df["status_recorded_at"] = pd.to_datetime(
        traces_df["status_recorded_at"], utc=True, errors="coerce"
    )
    traces_df["duration_seconds"] = (
        traces_df["trace_ended_at"]
        .sub(traces_df["trace_started_at"])
        .dt.total_seconds()
        .round(3)
    )
    traces_df["impact_score"] = (
        traces_df["severity_weight"]
        * (1.0 + traces_df["findings_count"].fillna(0))
        * (1.0 + traces_df["loop_count"].fillna(0) / 4.0)
    )
    traces_df["has_failure"] = (
        traces_df["outcome_group"].ne("successful_completion")
        | traces_df["validation_outcome"].fillna("passed").ne("passed")
        | traces_df["findings_count"].fillna(0).gt(0)
    )
    traces_df["owner_candidate"] = traces_df.apply(_infer_owner_candidate, axis=1)

    return traces_df, events_df


def _load_and_normalize_result_row(
    dataset_root: Path,
    result_row: dict[str, Any],
    record_index: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    bundle_path = _resolve_bundle_path(dataset_root, result_row["bundle_path"])
    bundle = load_bundle(bundle_path)
    return _normalize_bundle(bundle, result_row, record_index, bundle_path)


def load_macro_eval_artifacts(
    dataset_root: str | Path | None = None,
    data_dir: str | Path = DEFAULT_DATA_DIR,
    limit: int | None = None,
    use_cache: bool = True,
    refresh_cache: bool = False,
    cache_dir_name: str = ".macro_eval_cache",
) -> dict[str, pd.DataFrame | Path]:
    dataset_root = (
        Path(dataset_root) if dataset_root else resolve_dataset_root(data_dir)
    )
    cache_dir = _macro_eval_cache_dir(
        dataset_root, cache_dir_name=cache_dir_name, limit=limit
    )

    if use_cache and not refresh_cache and _macro_eval_cache_complete(cache_dir):
        return {
            "traces_df": pd.read_pickle(cache_dir / "traces.pkl"),
            "events_df": pd.read_pickle(cache_dir / "events.pkl"),
            "documents_df": pd.read_pickle(cache_dir / "documents.pkl"),
            "stacked_documents_df": pd.read_pickle(cache_dir / "stacked_documents.pkl"),
            "cache_dir": cache_dir,
        }

    traces_df, events_df = load_trace_tables(dataset_root=dataset_root, limit=limit)
    documents_df = build_trace_documents(traces_df, events_df)
    stacked_documents_df = stack_document_views(documents_df)

    if use_cache:
        cache_dir.mkdir(parents=True, exist_ok=True)
        traces_df.to_pickle(cache_dir / "traces.pkl")
        events_df.to_pickle(cache_dir / "events.pkl")
        documents_df.to_pickle(cache_dir / "documents.pkl")
        stacked_documents_df.to_pickle(cache_dir / "stacked_documents.pkl")
        metadata = {
            "dataset_root": str(dataset_root),
            "limit": limit,
            "trace_count": int(len(traces_df)),
            "event_count": int(len(events_df)),
        }
        (cache_dir / "metadata.json").write_text(
            json.dumps(metadata, indent=2), encoding="utf-8"
        )

    return {
        "traces_df": traces_df,
        "events_df": events_df,
        "documents_df": documents_df,
        "stacked_documents_df": stacked_documents_df,
        "cache_dir": cache_dir,
    }


def build_trace_documents(
    traces_df: pd.DataFrame,
    events_df: pd.DataFrame,
    doc_columns: Sequence[str] = DEFAULT_DOC_COLUMNS,
    max_full_trace_events: int = 42,
    failure_window_before: int = 6,
    failure_window_after: int = 8,
) -> pd.DataFrame:
    if traces_df.empty:
        return pd.DataFrame(columns=["trace_id", *doc_columns])

    grouped_events = {
        trace_id: group.sort_values(
            ["sequence_index", "ts"], na_position="last"
        ).reset_index(drop=True)
        for trace_id, group in events_df.groupby("trace_id", sort=False)
    }

    rows: list[dict[str, Any]] = []
    for _, trace_row in traces_df.iterrows():
        trace_id = trace_row["trace_id"]
        trace_events = grouped_events.get(
            trace_id, pd.DataFrame(columns=events_df.columns)
        )
        anchor_event = select_failure_anchor_event(trace_events)

        docs = {
            "trace_id": trace_id,
            "anchor_event_id": (
                None if anchor_event is None else anchor_event["event_id"]
            ),
            "anchor_stage_label": (
                None if anchor_event is None else anchor_event["stage_label"]
            ),
            "doc_full_trace": render_full_trace_document(
                trace_row,
                trace_events,
                anchor_event=anchor_event,
                max_events=max_full_trace_events,
            ),
            "doc_failure_window": render_failure_window_document(
                trace_row,
                trace_events,
                anchor_event=anchor_event,
                before=failure_window_before,
                after=failure_window_after,
            ),
            "doc_state_transition_summary": render_state_transition_summary(
                trace_row, trace_events
            ),
            "doc_tool_error_summary": render_tool_error_summary(
                trace_row, trace_events
            ),
        }
        docs["doc_structured_summary"] = render_structured_summary_document(
            trace_row,
            trace_events,
            docs["doc_failure_window"],
            docs["doc_state_transition_summary"],
            docs["doc_tool_error_summary"],
        )
        for column in doc_columns:
            docs[f"{column}_chars"] = len(docs[column])
            docs[f"{column}_tokens_est"] = estimate_token_count(docs[column])
        rows.append(docs)

    return pd.DataFrame(rows)


def stack_document_views(
    documents_df: pd.DataFrame,
    doc_columns: Sequence[str] = DEFAULT_DOC_COLUMNS,
) -> pd.DataFrame:
    stacked_rows: list[dict[str, Any]] = []
    for _, row in documents_df.iterrows():
        for column in doc_columns:
            stacked_rows.append(
                {
                    "trace_id": row["trace_id"],
                    "doc_type": column.replace("doc_", ""),
                    "document_text": row[column],
                    "document_length_chars": row[f"{column}_chars"],
                    "document_length_tokens_est": row[f"{column}_tokens_est"],
                    "anchor_event_id": row.get("anchor_event_id"),
                    "anchor_stage_label": row.get("anchor_stage_label"),
                }
            )
    return pd.DataFrame(stacked_rows)


def load_promptfoo_label_rows(path: str | Path | None) -> pd.DataFrame:
    if path is None:
        return pd.DataFrame()
    path = Path(path)
    if not path.is_file():
        return pd.DataFrame()
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return pd.DataFrame(rows)


def add_public_label_columns(
    traces_df: pd.DataFrame,
    promptfoo_labels_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    result = traces_df.copy()
    result["case_type"] = result.get("scenario_family", pd.Series(index=result.index, dtype="object"))
    result["risk_area"] = result.get("issue_cluster", pd.Series(index=result.index, dtype="object"))

    status = result.get("runtime_status", result.get("result_status", pd.Series(index=result.index, dtype="object")))
    terminal = result.get("terminal_state", pd.Series(index=result.index, dtype="object"))
    result["run_outcome"] = [
        _public_run_outcome(status_value, terminal_value)
        for status_value, terminal_value in zip(status, terminal)
    ]

    primary_marker = result.get(
        "primary_failure_marker", pd.Series(index=result.index, dtype="object")
    )
    result["eval_finding"] = primary_marker.fillna("none").replace("", "none")
    result["focus_stage"] = result.get(
        "anchor_stage_label", pd.Series(index=result.index, dtype="object")
    )
    result["behavior_pattern"] = result.get(
        "topic_label", pd.Series(index=result.index, dtype="object")
    ).fillna("unassigned")

    if promptfoo_labels_df is not None and not promptfoo_labels_df.empty:
        keep_cols = [
            column
            for column in [
                "run_id",
                "promptfoo_pass",
                "promptfoo_failed_checks",
                "promptfoo_score_mean",
                "promptfoo_check_scores",
                "promptfoo_primary_finding",
            ]
            if column in promptfoo_labels_df.columns
        ]
        if "run_id" in keep_cols:
            result = result.merge(
                promptfoo_labels_df[keep_cols].drop_duplicates(subset=["run_id"]),
                on="run_id",
                how="left",
            )
            if "promptfoo_primary_finding" in result.columns:
                result["eval_finding"] = result["promptfoo_primary_finding"].combine_first(
                    result["eval_finding"]
                )
    return result


def select_failure_anchor_event(trace_events: pd.DataFrame) -> pd.Series | None:
    if trace_events.empty:
        return None

    failure_events = trace_events[
        trace_events["is_failure_marker"].fillna(False)
    ].copy()
    if not failure_events.empty:
        return failure_events.sort_values(["sequence_index", "ts"]).iloc[0]

    degraded_status = trace_events[
        trace_events["node_kind"].eq("status")
        & trace_events["terminal_state"].fillna("completed").ne("completed")
    ]
    if not degraded_status.empty:
        return degraded_status.sort_values(["sequence_index", "ts"]).iloc[0]

    return trace_events.sort_values(["sequence_index", "ts"]).iloc[-1]


def render_full_trace_document(
    trace_row: pd.Series,
    trace_events: pd.DataFrame,
    anchor_event: pd.Series | None = None,
    max_events: int = 42,
) -> str:
    header = _document_header(trace_row, trace_events)
    if trace_events.empty:
        return f"{header}\nNo execution events were recovered from the bundle."

    selected = _select_salient_events(
        trace_events, anchor_event=anchor_event, max_events=max_events
    )
    lines = [header, "Chronological execution sketch:"]
    lines.extend(f"- {_render_event_line(event)}" for _, event in selected.iterrows())
    if len(selected) < len(trace_events):
        lines.append(
            f"- Trace truncated to {len(selected)} salient events from {len(trace_events)} total normalized events."
        )
    return "\n".join(lines)


def render_failure_window_document(
    trace_row: pd.Series,
    trace_events: pd.DataFrame,
    anchor_event: pd.Series | None = None,
    before: int = 6,
    after: int = 8,
) -> str:
    header = _document_header(trace_row, trace_events)
    if trace_events.empty:
        return f"{header}\nFailure window unavailable because the normalized event table is empty."

    anchor_event = (
        anchor_event
        if anchor_event is not None
        else select_failure_anchor_event(trace_events)
    )
    if anchor_event is None:
        return f"{header}\nFailure window unavailable because no anchor event could be selected."

    anchor_index = int(anchor_event["sequence_index"])
    lower = max(anchor_index - before, 0)
    upper = anchor_index + after
    window = trace_events[
        trace_events["sequence_index"].between(lower, upper, inclusive="both")
    ].sort_values(["sequence_index", "ts"])

    lines = [
        header,
        (
            f"Failure anchor: {anchor_event['event_id']} "
            f"({anchor_event['node_kind']}, {anchor_event['failure_marker_type'] or 'degraded_state'})."
        ),
        "Localized failure window:",
    ]
    lines.extend(f"- {_render_event_line(event)}" for _, event in window.iterrows())
    return "\n".join(lines)


def render_state_transition_summary(
    trace_row: pd.Series, trace_events: pd.DataFrame
) -> str:
    lines = [
        f"Trace {trace_row['trace_id']} state-transition summary.",
        (
            f"Outcome group={trace_row['outcome_group']}; result_status={trace_row['result_status']}; "
            f"terminal_state={trace_row['terminal_state']}; validation={trace_row['validation_outcome']}."
        ),
        (
            f"Scenario={trace_row['scenario_family']}; issue_cluster={trace_row['issue_cluster']}; "
            f"route={trace_row['selected_route']}; topology={trace_row['topology_id']}."
        ),
    ]

    if pd.notna(trace_row.get("route_signature")):
        lines.append(f"Route signature: {trace_row['route_signature']}.")
    if pd.notna(trace_row.get("fulfillment_signature")):
        lines.append(f"Fulfillment signature: {trace_row['fulfillment_signature']}.")

    agent_path = trace_events.loc[
        trace_events["node_kind"].eq("handoff"), ["source_agent", "target_agent"]
    ]
    if not agent_path.empty:
        handoffs = [
            f"{row.source_agent}->{row.target_agent}" for row in agent_path.itertuples()
        ]
        lines.append(
            "Observed handoffs: "
            + " | ".join(_dedupe_preserve_order(handoffs[:14]))
            + "."
        )

    status_lines = trace_events.loc[
        trace_events["node_kind"].eq("status"), "text"
    ].tolist()
    if status_lines:
        lines.append(
            "State snapshots: "
            + " | ".join(_dedupe_preserve_order(status_lines[:8]))
            + "."
        )

    lines.append(
        (
            f"Loops={trace_row['loop_count']}; retries={trace_row['retry_count']}; "
            f"arbitrations={trace_row['arbitration_count']}; review_packets={trace_row['review_packet_count']}."
        )
    )
    return "\n".join(lines)


def render_tool_error_summary(trace_row: pd.Series, trace_events: pd.DataFrame) -> str:
    lines = [
        f"Trace {trace_row['trace_id']} tool / review summary.",
        (
            f"Findings={trace_row['findings_count']} ({trace_row['finding_codes_text'] or 'none'}); "
            f"triage={trace_row['triage_outcome'] or 'none'}; review_action={trace_row['review_recommended_action'] or 'none'}."
        ),
    ]

    tool_events = trace_events[trace_events["node_kind"].eq("function")]
    if not tool_events.empty:
        lines.append("Function/tool outputs:")
        for _, event in tool_events.head(10).iterrows():
            lines.append(f"- {_render_event_line(event)}")

    finding_events = trace_events[trace_events["node_kind"].eq("finding")]
    if not finding_events.empty:
        lines.append("Review findings:")
        for _, event in finding_events.iterrows():
            lines.append(f"- {_render_event_line(event)}")

    if pd.notna(trace_row.get("review_summary")):
        lines.append(f"Review packet summary: {trace_row['review_summary']}")
    return "\n".join(lines)


def render_structured_summary_document(
    trace_row: pd.Series,
    trace_events: pd.DataFrame,
    failure_window_text: str,
    state_transition_text: str,
    tool_error_text: str,
) -> str:
    environment_bits = ", ".join(
        bit
        for bit in (
            trace_row.get("customer_region"),
            trace_row.get("vehicle_model"),
            trace_row.get("promo_program"),
            trace_row.get("incentive_program"),
            trace_row.get("tariff_regime"),
        )
        if bit and pd.notna(bit)
    )

    lines = [
        f"Trace {trace_row['trace_id']} structured summary.",
        (
            f"Eval outcome={trace_row['outcome_group']} (status={trace_row['result_status']}, "
            f"terminal={trace_row['terminal_state']}, severity={trace_row['severity_label']})."
        ),
        (
            f"Scenario={trace_row['scenario_family']}; issue_cluster={trace_row['issue_cluster']}; "
            f"selected_route={trace_row['selected_route']}; topology={trace_row['topology_id']}."
        ),
        (
            f"Telemetry: spans={trace_row['span_count']}, normalized_events={trace_row['event_count']}, "
            f"handoffs={trace_row['handoff_count']}, unique_agents={trace_row['unique_agent_count']}, "
            f"loops={trace_row['loop_count']}, retries={trace_row['retry_count']}, "
            f"arbitrations={trace_row['arbitration_count']}."
        ),
    ]

    if environment_bits:
        lines.append(f"Context: {environment_bits}.")
    if trace_row.get("environment_event_count", 0):
        lines.append(
            "Environment events: "
            + ", ".join(_coerce_list(trace_row.get("environment_event_ids"))[:6])
            + "."
        )
    if trace_row.get("specialist_activations"):
        lines.append(
            "Specialists activated: "
            + ", ".join(_coerce_list(trace_row.get("specialist_activations"))[:8])
            + "."
        )
    if pd.notna(trace_row.get("primary_failure_marker")):
        lines.append(f"Primary failure marker: {trace_row['primary_failure_marker']}.")

    lines.extend(
        [
            "State transition digest:",
            _indent_block(state_transition_text),
            "Failure-window digest:",
            _indent_block(failure_window_text),
            "Tool and review digest:",
            _indent_block(tool_error_text),
        ]
    )

    salient_agents = trace_events["agent_name"].dropna().astype(str).tolist()
    if salient_agents:
        lines.append(
            "Agent roster: "
            + ", ".join(_dedupe_preserve_order(salient_agents)[:14])
            + "."
        )
    return "\n".join(lines)


def estimate_token_count(text: str) -> int:
    return math.ceil(len(text) / 4)


@lru_cache(maxsize=4096)
def load_bundle(bundle_path: str | Path) -> dict[str, Any]:
    bundle_path = Path(bundle_path)
    with bundle_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def normalize_bundle(
    bundle: dict[str, Any],
    result_row: dict[str, Any],
    record_index: int,
    bundle_path: str | Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    return _normalize_bundle(bundle, result_row, record_index, Path(bundle_path))


def _normalize_bundle(
    bundle: dict[str, Any],
    result_row: dict[str, Any],
    record_index: int,
    bundle_path: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    run = bundle.get("run") or {}
    trace = bundle.get("trace") or {}
    summary = run.get("summary") or {}
    config = run.get("config") or {}
    trace_meta = _parse_metadata_json(trace.get("metadata_json"))
    review_packet = (
        bundle.get("review_packet")
        if isinstance(bundle.get("review_packet"), dict)
        else {}
    )
    review_decision_payload = review_packet.get("decision")
    if not isinstance(review_decision_payload, dict):
        review_decision_payload = {}
    findings = _merge_findings(summary.get("findings"), review_packet.get("findings"))
    trace_family_bits = _parse_trace_family(
        summary.get("trace_family") or result_row.get("trace_family")
    )

    event_rows = []
    event_rows.extend(
        _normalize_span_events(
            bundle.get("spans") or [], trace_id=trace.get("trace_id")
        )
    )
    event_rows.extend(
        _normalize_status_events(
            bundle.get("events") or [], trace_id=trace.get("trace_id")
        )
    )
    event_rows.extend(
        _normalize_finding_events(
            findings=findings,
            trace_id=trace.get("trace_id"),
            ended_at=trace.get("ended_at") or run.get("updated_at"),
        )
    )
    event_rows = _finalize_trace_events(
        trace_id=trace.get("trace_id"),
        trace_events=event_rows,
        summary=summary,
    )

    outcome_group = OUTCOME_GROUP_MAP.get(result_row.get("status"), "review_escalation")
    severity_label, severity_weight = SEVERITY_BY_OUTCOME[outcome_group]
    primary_failure_marker = _choose_primary_failure_marker(
        findings, summary, review_packet, result_row
    )

    trace_row = {
        "trace_id": trace.get("trace_id") or result_row.get("trace_id"),
        "run_id": run.get("run_id") or result_row.get("run_id"),
        "config_id": run.get("config_id") or result_row.get("config_id"),
        "record_index": record_index,
        "batch_index": result_row.get("batch_index") or trace_meta.get("batch_index"),
        "batch_label": result_row.get("batch_label") or trace_meta.get("batch_label"),
        "bundle_path": str(bundle_path),
        "trace_name": result_row.get("trace_name") or trace_meta.get("trace_name"),
        "result_status": result_row.get("status"),
        "runtime_status": run.get("status"),
        "outcome_group": outcome_group,
        "severity_label": severity_label,
        "severity_weight": severity_weight,
        "trace_started_at": trace.get("started_at"),
        "trace_ended_at": trace.get("ended_at"),
        "status_recorded_at": run.get("updated_at"),
        "scenario_family": result_row.get("scenario_family")
        or summary.get("scenario_family")
        or trace_meta.get("scenario_family"),
        "scenario": result_row.get("scenario") or trace_meta.get("scenario"),
        "issue_cluster": trace_meta.get("issue_cluster")
        or summary.get("issue_cluster"),
        "selected_route": summary.get("selected_route")
        or trace_meta.get("selected_route"),
        "route_signature": trace_family_bits.get("routes"),
        "fulfillment_signature": trace_family_bits.get("fulfillment"),
        "topology_id": trace_family_bits.get("fulfillment")
        or summary.get("selected_route")
        or trace_meta.get("selected_route"),
        "trace_family": summary.get("trace_family") or result_row.get("trace_family"),
        "terminal_state": summary.get("terminal_state") or result_row.get("status"),
        "validation_outcome": summary.get("validation_outcome"),
        "triage_outcome": summary.get("triage_outcome")
        or trace_meta.get("triage_outcome"),
        "review_status": summary.get("review_status"),
        "review_decision": (
            review_decision_payload.get("decision")
            if review_packet
            else summary.get("review_decision")
        ),
        "review_recommended_action": (
            review_packet.get("recommended_action")
            if review_packet
            else summary.get("review_recommended_action")
        ),
        "review_summary": review_packet.get("summary"),
        "review_packet_count": int(bool(review_packet)),
        "customer_region": ((config.get("customer") or {}).get("region")),
        "customer_name": ((config.get("customer") or {}).get("name")),
        "vehicle_model": trace_meta.get("vehicle_model")
        or ((config.get("vehicle") or {}).get("model")),
        "vehicle_trim": ((config.get("vehicle") or {}).get("trim")),
        "vehicle_wheels": ((config.get("vehicle") or {}).get("wheels")),
        "promo_program": summary.get("promo_program")
        or trace_meta.get("promo_program")
        or result_row.get("promo_program"),
        "incentive_program": summary.get("incentive_program")
        or trace_meta.get("incentive_program")
        or result_row.get("incentive_program"),
        "tariff_regime": summary.get("tariff_regime")
        or trace_meta.get("tariff_regime")
        or result_row.get("tariff_regime"),
        "simulation_date": summary.get("simulation_date")
        or trace_meta.get("simulation_date")
        or result_row.get("simulation_date"),
        "factory_assignment": summary.get("factory_assignment")
        or trace_meta.get("factory_assignment")
        or result_row.get("factory_assignment"),
        "factory_release_state": summary.get("factory_release_state"),
        "environment_batch_id": summary.get("environment_batch_id")
        or trace_meta.get("environment_batch_id")
        or result_row.get("environment_batch_id"),
        "environment_event_ids": summary.get("environment_event_ids")
        or trace_meta.get("environment_event_ids")
        or result_row.get("environment_event_ids"),
        "environment_event_count": len(
            _coerce_list(
                summary.get("environment_event_ids")
                or trace_meta.get("environment_event_ids")
                or result_row.get("environment_event_ids")
            )
        ),
        "specialist_activations": summary.get("specialist_activations")
        or result_row.get("specialist_activations"),
        "specialist_activation_count": len(
            _coerce_list(
                summary.get("specialist_activations")
                or result_row.get("specialist_activations")
            )
        ),
        "supplier_mix": summary.get("supplier_mix")
        or trace_meta.get("supplier_mix")
        or result_row.get("supplier_mix"),
        "supplier_mix_count": len(
            _coerce_list(summary.get("supplier_mix") or trace_meta.get("supplier_mix"))
        ),
        "loop_count": _safe_int(
            summary.get("loop_count") or result_row.get("loop_count")
        ),
        "retry_count": _safe_int(summary.get("retry_count")),
        "arbitration_count": _safe_int(
            summary.get("arbitration_count") or result_row.get("arbitration_count")
        ),
        "compound_issue_count": _safe_int(summary.get("compound_issue_count")),
        "findings_count": len(findings),
        "finding_codes": [
            finding.get("code") for finding in findings if finding.get("code")
        ],
        "finding_codes_text": ", ".join(
            [finding.get("code") for finding in findings if finding.get("code")]
        ),
        "finding_agents_text": ", ".join(
            sorted(
                {
                    finding.get("agent_name")
                    for finding in findings
                    if finding.get("agent_name")
                }
            )
        ),
        "finding_messages_text": " | ".join(
            _clean_text(finding.get("message"))
            for finding in findings
            if finding.get("message")
        ),
        "primary_failure_marker": primary_failure_marker,
        "error_text": result_row.get("error"),
        "openai_trace_id": result_row.get("openai_trace_id")
        or run.get("openai_trace_id"),
        "run_created_at": run.get("created_at"),
        "trace_workflow_name": trace.get("workflow_name"),
        "span_count": len(bundle.get("spans") or []),
        "event_count": len(event_rows),
        "handoff_count": sum(row["node_kind"] == "handoff" for row in event_rows),
        "status_event_count": sum(row["node_kind"] == "status" for row in event_rows),
        "function_count": sum(row["node_kind"] == "function" for row in event_rows),
        "agent_span_count": sum(row["node_kind"] == "agent" for row in event_rows),
        "unique_agent_count": len(
            {row["agent_name"] for row in event_rows if row.get("agent_name")}
        ),
        "unique_tool_count": len(
            {row["tool_name"] for row in event_rows if row.get("tool_name")}
        ),
    }

    return trace_row, event_rows


def _normalize_span_events(
    spans: Iterable[dict[str, Any]], trace_id: str | None
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for span in spans:
        span_data = _parse_json_object(span.get("span_data"))
        node_kind = span.get("span_type")
        raw_output = _clean_text(span_data.get("output"))
        row = {
            "trace_id": trace_id,
            "event_id": span.get("span_id"),
            "parent_event_id": span.get("parent_span_id"),
            "ts": span.get("started_at"),
            "ended_at": span.get("ended_at"),
            "duration_ms": _duration_ms(span.get("started_at"), span.get("ended_at")),
            "node_kind": node_kind,
            "event_type": node_kind,
            "payload_type": span_data.get("sdk_span_type") or span_data.get("type"),
            "actor_type": _actor_type_for_node_kind(node_kind),
            "actor_id": span_data.get("name")
            or span_data.get("tool_name")
            or span.get("agent_name"),
            "agent_name": span.get("agent_name"),
            "source_agent": span_data.get("from_agent"),
            "target_agent": span_data.get("to_agent"),
            "tool_name": span_data.get("tool_name"),
            "function_name": span_data.get("name") if node_kind == "function" else None,
            "run_status": None,
            "terminal_state": None,
            "validation_outcome": None,
            "triage_outcome": None,
            "finding_code": None,
            "finding_severity": None,
            "output_excerpt": _truncate(raw_output, 220),
            "raw_output": raw_output,
            "text": _render_span_text(node_kind, span, span_data),
            "failure_marker_type": _infer_span_failure_type(span, span_data),
            "is_failure_marker": _infer_span_failure(span, span_data),
            "metadata_json": json.dumps(span_data, ensure_ascii=True),
            "sort_priority": STATUS_SORT_PRIORITY.get(node_kind, 9),
        }
        rows.append(row)
    return rows


def _normalize_status_events(
    events: Iterable[dict[str, Any]], trace_id: str | None
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for event in events:
        if event.get("event_type") != "status":
            continue
        payload = event.get("payload") or {}
        row = {
            "trace_id": trace_id,
            "event_id": f"status::{event.get('event_id')}",
            "parent_event_id": None,
            "ts": event.get("timestamp"),
            "ended_at": event.get("timestamp"),
            "duration_ms": 0.0,
            "node_kind": "status",
            "event_type": "status",
            "payload_type": "status",
            "actor_type": "system",
            "actor_id": payload.get("active_agent") or event.get("agent_name"),
            "agent_name": event.get("agent_name"),
            "source_agent": event.get("source_agent"),
            "target_agent": event.get("target_agent"),
            "tool_name": None,
            "function_name": None,
            "run_status": payload.get("run_status"),
            "terminal_state": payload.get("terminal_state"),
            "validation_outcome": payload.get("validation_outcome"),
            "triage_outcome": payload.get("triage_outcome"),
            "finding_code": None,
            "finding_severity": None,
            "output_excerpt": None,
            "raw_output": None,
            "text": _render_status_text(payload),
            "failure_marker_type": _infer_status_failure_type(payload),
            "is_failure_marker": _infer_status_failure(payload),
            "metadata_json": json.dumps(payload, ensure_ascii=True),
            "sort_priority": STATUS_SORT_PRIORITY["status"],
        }
        rows.append(row)
    return rows


def _normalize_finding_events(
    findings: list[dict[str, Any]],
    trace_id: str | None,
    ended_at: str | None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for finding_index, finding in enumerate(findings, start=1):
        rows.append(
            {
                "trace_id": trace_id,
                "event_id": f"finding::{finding_index}",
                "parent_event_id": None,
                "ts": ended_at,
                "ended_at": ended_at,
                "duration_ms": 0.0,
                "node_kind": "finding",
                "event_type": "finding",
                "payload_type": "finding",
                "actor_type": "review",
                "actor_id": finding.get("agent_name") or "review",
                "agent_name": finding.get("agent_name"),
                "source_agent": None,
                "target_agent": None,
                "tool_name": None,
                "function_name": None,
                "run_status": None,
                "terminal_state": None,
                "validation_outcome": None,
                "triage_outcome": None,
                "finding_code": finding.get("code"),
                "finding_severity": finding.get("severity"),
                "output_excerpt": _truncate(_clean_text(finding.get("message")), 220),
                "raw_output": _clean_text(finding.get("message")),
                "text": _render_finding_text(finding),
                "failure_marker_type": "review_finding",
                "is_failure_marker": True,
                "metadata_json": json.dumps(finding, ensure_ascii=True),
                "sort_priority": STATUS_SORT_PRIORITY["finding"],
            }
        )
    return rows


def _finalize_trace_events(
    trace_id: str | None,
    trace_events: list[dict[str, Any]],
    summary: dict[str, Any],
) -> list[dict[str, Any]]:
    if not trace_events:
        return []

    trace_events = sorted(
        trace_events,
        key=lambda row: (
            pd.Timestamp(row["ts"]) if row.get("ts") else pd.Timestamp.max,
            row.get("sort_priority", 9),
            row.get("event_id") or "",
        ),
    )

    total = len(trace_events)
    for sequence_index, row in enumerate(trace_events):
        row["sequence_index"] = sequence_index
        stage_index = min(
            int((sequence_index / max(total - 1, 1)) * len(STAGE_LABELS)),
            len(STAGE_LABELS) - 1,
        )
        row["stage_index"] = stage_index
        row["stage_label"] = STAGE_LABELS[stage_index]
        row["trace_outcome_hint"] = summary.get("terminal_state")
        row.pop("sort_priority", None)
        if row["node_kind"] == "finding" and not row.get("ts"):
            row["ts"] = trace_events[-1].get("ts")
            row["ended_at"] = trace_events[-1].get("ended_at")
        if not row.get("event_id"):
            row["event_id"] = f"{trace_id}::event::{sequence_index}"
    return trace_events


def _resolve_bundle_path(dataset_root: Path, bundle_path_value: str) -> Path:
    bundle_name = Path(bundle_path_value).name
    extracted_bundle_dir = _ensure_trace_bundles_extracted(dataset_root)
    candidates = (
        dataset_root / "bundles" / bundle_name,
        dataset_root / "trace_bundles" / bundle_name,
        extracted_bundle_dir / bundle_name if extracted_bundle_dir else None,
        dataset_root / bundle_name,
        Path(bundle_path_value),
    )
    for candidate in candidates:
        if candidate is None:
            continue
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        f"Could not resolve bundle path {bundle_path_value!r} from {dataset_root}."
    )


def _ensure_trace_bundles_extracted(dataset_root: Path) -> Path | None:
    expanded_dir = dataset_root / "trace_bundles"
    if expanded_dir.is_dir() and any(expanded_dir.glob("*.json")):
        return expanded_dir

    bundle_zip = dataset_root / "trace_bundles.zip"
    if not bundle_zip.is_file():
        return None

    cache_dir = dataset_root / ".macro_eval_cache" / "trace_bundles"
    marker = cache_dir / ".extracted_from_trace_bundles_zip"
    if marker.is_file() and any(cache_dir.glob("*.json")):
        return cache_dir

    cache_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(bundle_zip) as archive:
        for member in archive.infolist():
            if member.is_dir() or not member.filename.endswith(".json"):
                continue
            target = cache_dir / Path(member.filename).name
            target.write_bytes(archive.read(member))
    marker.write_text(str(bundle_zip.stat().st_mtime_ns), encoding="utf-8")
    return cache_dir


def _first_existing_path(*paths: Path) -> Path:
    for path in paths:
        if path.exists():
            return path
    raise FileNotFoundError(
        "None of the candidate paths exists: "
        + ", ".join(str(path) for path in paths)
    )


def _safe_json_loads(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _parse_metadata_json(raw_value: Any) -> dict[str, Any]:
    if isinstance(raw_value, dict):
        return raw_value
    if not raw_value:
        return {}
    try:
        parsed = json.loads(raw_value)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _parse_json_object(raw_value: Any) -> dict[str, Any]:
    if isinstance(raw_value, dict):
        return raw_value
    if not raw_value:
        return {}
    try:
        parsed = json.loads(raw_value)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _merge_findings(*finding_lists: Any) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for finding_list in finding_lists:
        for finding in finding_list or []:
            if finding:
                merged.append(finding)
    return merged


def _choose_primary_failure_marker(
    findings: list[dict[str, Any]],
    summary: dict[str, Any],
    review_packet: dict[str, Any],
    result_row: dict[str, Any],
) -> str | None:
    if findings:
        finding = findings[0]
        return finding.get("code") or _clean_text(finding.get("message"))
    if summary.get("triage_outcome"):
        return summary["triage_outcome"]
    if (
        summary.get("validation_outcome")
        and summary.get("validation_outcome") != "passed"
    ):
        return summary["validation_outcome"]
    if review_packet.get("summary"):
        return _clean_text(review_packet["summary"])
    if result_row.get("error"):
        return _truncate(_clean_text(result_row["error"]), 140)
    if summary.get("terminal_state") and summary.get("terminal_state") != "completed":
        return summary.get("terminal_state")
    return None


def _parse_trace_family(trace_family: str | None) -> dict[str, str]:
    if not trace_family:
        return {}
    bits: dict[str, str] = {}
    for chunk in trace_family.split(" | "):
        chunk = chunk.strip()
        if not chunk:
            continue
        if ":" in chunk:
            key, value = chunk.split(":", 1)
            bits[key.strip()] = value.strip()
        elif "scenario_family" not in bits:
            bits["scenario_family"] = chunk
    return bits


def _actor_type_for_node_kind(node_kind: str | None) -> str:
    if node_kind == "handoff":
        return "orchestrator"
    if node_kind in {"agent", "function", "response"}:
        return node_kind
    return "system"


def _render_span_text(
    node_kind: str | None, span: dict[str, Any], span_data: dict[str, Any]
) -> str:
    if node_kind == "handoff":
        return f"handoff {span_data.get('from_agent')} -> {span_data.get('to_agent')}"
    if node_kind == "agent":
        tools = ", ".join(span_data.get("tools") or []) or "none"
        return f"agent {span.get('agent_name')} tools={tools}"
    if node_kind == "response":
        return f"response {span.get('agent_name')} response_id={span_data.get('response_id')}"
    if node_kind == "function":
        output = _truncate(_clean_text(span_data.get("output")), 160)
        return (
            f"function {span_data.get('name')} output={output or 'no output captured'}"
        )
    return _clean_text(json.dumps(span_data, ensure_ascii=True))


def _render_status_text(payload: dict[str, Any]) -> str:
    fragments = [
        f"status active={payload.get('active_agent')}",
        f"run={payload.get('run_status')}",
        f"terminal={payload.get('terminal_state')}",
        f"validation={payload.get('validation_outcome')}",
    ]
    if payload.get("selected_route"):
        fragments.append(f"route={payload.get('selected_route')}")
    if payload.get("triage_outcome"):
        fragments.append(f"triage={payload.get('triage_outcome')}")
    if payload.get("retry_count") is not None:
        fragments.append(f"retries={payload.get('retry_count')}")
    if payload.get("loop_count") is not None:
        fragments.append(f"loops={payload.get('loop_count')}")
    return " ".join(
        fragment for fragment in fragments if fragment and "None" not in fragment
    )


def _render_finding_text(finding: dict[str, Any]) -> str:
    return (
        f"finding agent={finding.get('agent_name') or 'unknown'} "
        f"code={finding.get('code') or 'uncoded'} "
        f"severity={finding.get('severity') or 'unknown'} "
        f"message={_clean_text(finding.get('message'))}"
    )


def _infer_span_failure(span: dict[str, Any], span_data: dict[str, Any]) -> bool:
    return bool(_infer_span_failure_type(span, span_data))


def _infer_span_failure_type(
    span: dict[str, Any], span_data: dict[str, Any]
) -> str | None:
    if span.get("error"):
        return "span_error"
    output = _clean_text(span_data.get("output"))
    if not output:
        return None
    if "findings=[]" not in output and "findings=[" in output:
        return "tool_finding"
    if any(marker in output.lower() for marker in FAILURE_TEXT_MARKERS):
        return "tool_warning"
    return None


def _infer_status_failure(payload: dict[str, Any]) -> bool:
    return bool(_infer_status_failure_type(payload))


def _infer_status_failure_type(payload: dict[str, Any]) -> str | None:
    if payload.get("terminal_state") in {"failed", "awaiting_review"}:
        return payload["terminal_state"]
    if (
        payload.get("validation_outcome")
        and payload.get("validation_outcome") != "passed"
    ):
        return payload.get("validation_outcome")
    if payload.get("triage_outcome"):
        return "triage_route"
    if payload.get("review_status") and payload.get("review_status") != "not_required":
        return "review_required"
    return None


def _macro_eval_cache_dir(
    dataset_root: Path,
    cache_dir_name: str = ".macro_eval_cache",
    limit: int | None = None,
) -> Path:
    scope = "all" if limit is None else f"limit_{int(limit)}"
    return dataset_root / cache_dir_name / scope


def _macro_eval_cache_complete(cache_dir: Path) -> bool:
    required = ("traces.pkl", "events.pkl", "documents.pkl", "stacked_documents.pkl")
    return all((cache_dir / name).exists() for name in required)


@lru_cache(maxsize=32768)
def _parse_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        fallback = pd.to_datetime(value, utc=True, errors="coerce")
        if pd.isna(fallback):
            return None
        return fallback.to_pydatetime()
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _duration_ms(started_at: Any, ended_at: Any) -> float | None:
    if not started_at or not ended_at:
        return None
    if isinstance(started_at, str) and isinstance(ended_at, str):
        started = _parse_timestamp(started_at)
        ended = _parse_timestamp(ended_at)
    else:
        started = pd.to_datetime(started_at, utc=True, errors="coerce")
        ended = pd.to_datetime(ended_at, utc=True, errors="coerce")
        if pd.isna(started) or pd.isna(ended):
            return None
    if started is None or ended is None:
        return None
    return round((ended - started).total_seconds() * 1000.0, 3)


def _render_event_line(event: pd.Series) -> str:
    prefix = f"[{event['sequence_index']:03d} {event['stage_label']}]"
    marker = " failure-marker" if bool(event.get("is_failure_marker")) else ""
    return f"{prefix} {event['text']}{marker}"


def _select_salient_events(
    trace_events: pd.DataFrame,
    anchor_event: pd.Series | None,
    max_events: int,
) -> pd.DataFrame:
    if len(trace_events) <= max_events:
        return trace_events

    head_count = min(max_events // 3, 12)
    tail_count = min(max_events // 4, 10)
    window_count = max_events - head_count - tail_count

    anchor_event = (
        anchor_event
        if anchor_event is not None
        else select_failure_anchor_event(trace_events)
    )
    anchor_index = (
        int(anchor_event["sequence_index"])
        if anchor_event is not None
        else len(trace_events) - 1
    )

    head = trace_events.head(head_count)
    tail = trace_events.tail(tail_count)
    lower = max(anchor_index - (window_count // 2), 0)
    upper = lower + window_count
    window = trace_events[
        trace_events["sequence_index"].between(lower, upper, inclusive="both")
    ]

    selected = (
        pd.concat([head, window, tail], axis=0)
        .drop_duplicates(subset=["event_id"])
        .sort_values(["sequence_index", "ts"], na_position="last")
    )
    return selected.head(max_events)


def _document_header(trace_row: pd.Series, trace_events: pd.DataFrame) -> str:
    return (
        f"Trace {trace_row['trace_id']} "
        f"(scenario={trace_row['scenario_family']}, outcome={trace_row['outcome_group']}, "
        f"severity={trace_row['severity_label']}, events={len(trace_events)})."
    )


def _coerce_list(value: Any) -> list[str]:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item not in (None, "")]
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return []
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            return [str(item) for item in parsed if item not in (None, "")]
        return [part.strip() for part in value.split(",") if part.strip()]
    return [str(value)]


def _dedupe_preserve_order(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _infer_owner_candidate(trace_row: pd.Series) -> str:
    joined = " ".join(
        str(part or "")
        for part in (
            trace_row.get("finding_agents_text"),
            trace_row.get("primary_failure_marker"),
            trace_row.get("selected_route"),
            trace_row.get("scenario_family"),
        )
    ).lower()
    if "pricing" in joined:
        return "pricing and offer owner"
    if "compliance" in joined:
        return "compliance validation owner"
    if "supplier" in joined or "supply" in joined:
        return "supply and routing owner"
    if "factory" in joined or "fulfillment" in joined or "schedule" in joined:
        return "fulfillment orchestration owner"
    if "human" in joined or "triage" in joined:
        return "review and escalation policy owner"
    if "validation" in joined or "buildability" in joined or "designreview" in joined:
        return "validation stack owner"
    return "orchestration owner"


def _public_run_outcome(status_value: Any, terminal_value: Any) -> str:
    status = _clean_text(status_value).lower()
    terminal = _clean_text(terminal_value).lower()
    value = status or terminal
    if value == "completed":
        return "completed"
    if value == "awaiting_review":
        return "review_needed"
    if value == "blocked":
        return "blocked"
    if value == "failed":
        return "runtime_error"
    if value in {"running", "accepted", "in_progress"}:
        return "in_progress"
    return value or "unknown"


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _truncate(text: str, max_chars: int) -> str:
    text = _clean_text(text)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _indent_block(text: str, prefix: str = "  ") -> str:
    return "\n".join(f"{prefix}{line}" for line in text.splitlines())


__all__ = [
    "DEFAULT_DATA_DIR",
    "DEFAULT_DOC_COLUMNS",
    "add_public_label_columns",
    "build_trace_documents",
    "estimate_token_count",
    "load_promptfoo_label_rows",
    "load_macro_eval_artifacts",
    "load_results_records",
    "load_trace_tables",
    "normalize_bundle",
    "render_failure_window_document",
    "render_full_trace_document",
    "render_state_transition_summary",
    "render_structured_summary_document",
    "render_tool_error_summary",
    "resolve_dataset_root",
    "select_failure_anchor_event",
    "stack_document_views",
]
