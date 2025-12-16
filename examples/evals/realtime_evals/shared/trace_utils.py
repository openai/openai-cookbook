from typing import Any, Optional


def event_to_dict(event: Any) -> dict[str, Any]:
    if isinstance(event, dict):
        return event
    return event.model_dump()


def truncate_string(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    truncated = value[:max_length]
    omitted = len(value) - max_length
    return f"{truncated}...[truncated {omitted} chars]"


def sanitize_value(value: Any, max_string_length: int) -> Any:
    if isinstance(value, dict):
        return sanitize_dict(value, max_string_length)
    if isinstance(value, list):
        return [sanitize_value(item, max_string_length) for item in value]
    if isinstance(value, str):
        return truncate_string(value, max_string_length)
    return value


def sanitize_dict(payload: dict[str, Any], max_string_length: int) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in payload.items():
        sanitized[key] = sanitize_value(value, max_string_length)
    return sanitized


def build_event_record(
    event: Any,
    event_time_ms: Optional[float] = None,
    event_index: Optional[int] = None,
    source: Optional[str] = None,
    turn_index: Optional[int] = None,
    max_string_length: int = 400,
) -> dict[str, Any]:
    payload = event_to_dict(event)
    event_type = payload.get("type", "unknown")

    record: dict[str, Any] = {"type": event_type}
    if source is not None:
        record["source"] = source
    if turn_index is not None:
        record["turn_index"] = turn_index
    if event_index is not None:
        record["event_index"] = event_index
    if event_time_ms is not None:
        record["event_time_ms"] = event_time_ms
    record["event"] = sanitize_value(payload, max_string_length)
    return record
