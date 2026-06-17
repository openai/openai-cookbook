#!/usr/bin/env python3
"""Return success when an OTLP/HTTP export response reports no rejected data."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REJECTED_COUNT_KEYS = {
    "logs": "rejectedLogRecords",
    "traces": "rejectedSpans",
    "metrics": "rejectedDataPoints",
}


def validation_error(signal: str, response_text: str) -> str | None:
    if not response_text.strip():
        return None
    try:
        payload: Any = json.loads(response_text)
    except json.JSONDecodeError as exc:
        return f"invalid JSON response - {exc}"
    if not isinstance(payload, dict):
        return "response root must be an object"

    partial_success = payload.get("partialSuccess")
    if partial_success is None:
        return None
    if not isinstance(partial_success, dict):
        return "partialSuccess must be an object"

    count_key = REJECTED_COUNT_KEYS[signal]
    raw_rejected_count = partial_success.get(count_key, 0)
    if isinstance(raw_rejected_count, bool):
        return f"{count_key} must be a non-negative integer"
    if isinstance(raw_rejected_count, int):
        rejected_count = raw_rejected_count
    elif isinstance(raw_rejected_count, str) and raw_rejected_count.isdigit():
        rejected_count = int(raw_rejected_count)
    else:
        return f"{count_key} must be a non-negative integer"
    if rejected_count < 0:
        return f"{count_key} must be a non-negative integer"
    if rejected_count:
        return f"Collector rejected {rejected_count} {signal} item(s)"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("signal", choices=tuple(REJECTED_COUNT_KEYS))
    parser.add_argument("response", type=Path)
    args = parser.parse_args()

    try:
        response_text = args.response.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        print(f"ERROR - could not read OTLP response - {exc}", file=sys.stderr)
        return 1
    error = validation_error(args.signal, response_text)
    if error:
        print(f"ERROR - {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
