#!/usr/bin/env python3
"""Hard-disabled legacy Beds24 booking recovery bridge.

The original one-off recovery script contained live booking mutation code.
That behavior is retired. This replacement only records a local safety
attestation and performs no authentication, network, email, or booking action.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import sys
from typing import Any

TRUE_VALUES = {"1", "true", "yes", "on"}


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in TRUE_VALUES


def require_safety_guards() -> None:
    required = (
        "AUMARA_DRY_RUN",
        "AUMARA_DISABLE_EMAIL_SEND",
        "AUMARA_DISABLE_BOOKING_MUTATIONS",
    )
    missing = [name for name in required if not enabled(name)]
    if missing:
        raise RuntimeError(
            "Legacy bridge remains disabled; missing safety guards: "
            + ", ".join(missing)
        )


def load_request_id(path: pathlib.Path) -> str | None:
    if not path.exists():
        return None
    value: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Request file must contain a JSON object")
    request_id = str(value.get("request_id") or "").strip()
    return request_id or None


def parse_args() -> argparse.Namespace:
    root = pathlib.Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--request",
        type=pathlib.Path,
        default=(
            root
            / "beds24-requests"
            / "AUMARA-MEDINA-20260718-660.json"
        ),
    )
    parser.add_argument(
        "--output",
        type=pathlib.Path,
        default=root / "evidence" / "beds24-finalize-status.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        require_safety_guards()
        request_id = load_request_id(args.request)
        evidence = {
            "verified_at_utc": now_utc(),
            "status": "DISABLED_REDUNDANT_V2_BRIDGE",
            "request_id": request_id,
            "reason": (
                "Legacy one-off recovery is retired; native Beds24 state is "
                "the source of truth."
            ),
            "dry_run": True,
            "email_send_disabled": True,
            "booking_mutations_disabled": True,
            "external_network_calls": 0,
            "live_booking_mutations": False,
            "plaintext_secret_committed": False,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"Legacy bridge failed safely: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(evidence, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
