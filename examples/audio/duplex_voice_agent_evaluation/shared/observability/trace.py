"""Timestamped, sanitized GPT Live evaluation trace utilities."""

from __future__ import annotations

import json
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any, TextIO

from shared.observability.redaction import TraceRedactor, default_redactor
from shared.private_files import private_open


def sanitize_trace_value(value: Any, *, max_string_length: int = 800, redactor: TraceRedactor | None = None) -> Any:
    """Keep useful event evidence while removing audio and configured secrets."""
    return (redactor or default_redactor()).sanitize(value, max_string_length=max_string_length)


def record_event(
    log_file: TextIO,
    event: Mapping[str, Any],
    *,
    started_at: float,
    event_index_state: dict[str, int],
    source: str,
    direction: str,
) -> None:
    """Immediately persist an ordered event with its origin and transport direction."""
    event_index_state["value"] += 1
    payload = dict(event.get("_raw_live_event", event))
    if "_raw_live_event" in event:
        payload["_relay_receipt"] = event.get("_relay_receipt", {})
        if "offset_ms" in event:
            payload["_evaluation_offset_ms"] = event["offset_ms"]
    if (
        str(payload.get("type", ""))
        in {
            "session.context.append",
            "session.context.appended",
            "session.thinking.append",
            "session.instructions.append",
            "session.commentary.append",
            "session.commentary.appended",
            "session.thinking.appended",
            "session.instructions.appended",
        }
        and "content" in payload
    ):
        payload["content"] = "[redacted session context]"
    record = {
        "type": str(payload.get("type", "unknown")),
        "event_index": event_index_state["value"],
        "event_time_ms": round((time.monotonic() - started_at) * 1_000, 3),
        "source": source,
        "direction": direction,
        "event": sanitize_trace_value(payload),
    }
    log_file.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    log_file.flush()


def append_trace_events(
    path: Path,
    events: list[dict[str, Any]],
    *,
    started_at: float | None = None,
    source: str = "evaluator",
    direction: str = "internal",
) -> None:
    """Append ordered evaluator evidence after a transport-owned trace has closed."""

    if not path.exists() or not events:
        return
    last_index = 0
    last_elapsed_ms = 0.0
    with path.open("r", encoding="utf-8") as existing:
        for line in existing:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            last_index = max(last_index, int(record.get("event_index", 0)))
            last_elapsed_ms = max(last_elapsed_ms, float(record.get("event_time_ms", 0)))
    if started_at is None:
        started_at = time.monotonic() - (last_elapsed_ms + 1.0) / 1_000
    else:
        started_at = min(started_at, time.monotonic() - (last_elapsed_ms + 1.0) / 1_000)
    state = {"value": last_index}
    with private_open(path, "a") as log:
        for event in events:
            record_event(
                log,
                event,
                started_at=started_at,
                event_index_state=state,
                source=source,
                direction=direction,
            )
