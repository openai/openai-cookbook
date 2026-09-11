from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

DEMO_TRAVEL_DATE_ENV = "COOKBOOK_DEMO_TRAVEL_DATE"
DEMO_TRAVEL_DATE_TOKEN = "{{COOKBOOK_DEMO_TRAVEL_DATE}}"
DEFAULT_LEAD_DAYS = 45


def demo_travel_date(
    *,
    environment: Mapping[str, str] | None = None,
    today: date | None = None,
) -> str:
    """Return one future ISO date, with an explicit deterministic override for tests."""
    values = os.environ if environment is None else environment
    current_date = today or datetime.now(timezone.utc).date()
    configured = values.get(DEMO_TRAVEL_DATE_ENV, "").strip()
    if not configured:
        return (current_date + timedelta(days=DEFAULT_LEAD_DAYS)).isoformat()
    try:
        resolved = date.fromisoformat(configured)
    except ValueError as exc:
        raise RuntimeError(f"{DEMO_TRAVEL_DATE_ENV} must be an ISO date (YYYY-MM-DD)") from exc
    if resolved <= current_date:
        raise RuntimeError(f"{DEMO_TRAVEL_DATE_ENV} must be later than today")
    return resolved.isoformat()


def materialize_demo_date(value: Any, travel_date: str) -> Any:
    if isinstance(value, str):
        return value.replace(DEMO_TRAVEL_DATE_TOKEN, travel_date)
    if isinstance(value, list):
        return [materialize_demo_date(item, travel_date) for item in value]
    if isinstance(value, dict):
        return {key: materialize_demo_date(item, travel_date) for key, item in value.items()}
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve the cookbook's future demo date.")
    parser.add_argument("--payload", type=Path, help="materialize the demo-date token in JSON")
    args = parser.parse_args()
    travel_date = demo_travel_date()
    if args.payload is None:
        print(travel_date)
        return 0
    payload = json.loads(args.payload.read_text(encoding="utf-8"))
    print(json.dumps(materialize_demo_date(payload, travel_date), separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
