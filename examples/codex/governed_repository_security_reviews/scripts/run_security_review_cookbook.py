#!/usr/bin/env python3
"""Run a durable, customer-neutral synthetic repository security-review recipe."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import json
import os
import sys
import tempfile
from pathlib import Path


sys.dont_write_bytecode = True
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

ROOT = Path(__file__).resolve().parents[1]
for source in (ROOT / "src", *sorted(ROOT.glob("*/src"))):
    if (source / "fleet_security" / "recipe.py").is_file():
        sys.path.insert(0, str(source))
        break
else:
    raise RuntimeError("the customer-neutral fleet_security recipe package is unavailable")

from fleet_security.recipe import RecurringSecurityRecipe


def main() -> int:
    examples = ROOT / "cookbook" / "security-review-pipeline"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=examples / "config.example.json")
    parser.add_argument("--inventory", type=Path, default=examples / "inventory.example.json")
    parser.add_argument("--approvals", type=Path, default=examples / "approvals.example.json")
    parser.add_argument(
        "--state-dir", type=Path, default=None,
        help="Optional durable owner-private state; omitted state is automatically removed "
             "from a temporary location outside the reference checkout.",
    )
    parser.add_argument("--docker", action="store_true", help="Use genuine restricted Docker for synthetic fixtures.")
    parser.add_argument("--cycles", type=int, default=1, help="Run 1-10 immediate governed reconciliation cycles.")
    arguments = parser.parse_args()
    if not 1 <= arguments.cycles <= 10:
        parser.error("--cycles must be between 1 and 10")

    with ExitStack() as cleanups:
        state_directory = arguments.state_dir
        if state_directory is None:
            temporary = cleanups.enter_context(
                tempfile.TemporaryDirectory(prefix="governed-security-review-")
            )
            state_directory = Path(temporary) / "owner-private-state"
        receipts = []
        for _ in range(arguments.cycles):
            recipe = RecurringSecurityRecipe.from_files(
                configuration_path=arguments.config,
                inventory_path=arguments.inventory,
                approvals_path=arguments.approvals,
                state_directory=state_directory,
                docker=arguments.docker,
            )
            receipts.append(recipe.cycle())
        print(json.dumps({
            "cycles": len(receipts),
            "state_directory": str(state_directory),
            "state_directory_retained": arguments.state_dir is not None,
            "latest": receipts[-1],
            "cycle_receipts": receipts,
            "scanner_invocations_per_cycle": [receipt["scanner_invocations"] for receipt in receipts],
            "attempted_repositories_per_cycle": [receipt["attempted_repositories"] for receipt in receipts],
            "retry_attempts_per_cycle": [receipt["retry_attempts"] for receipt in receipts],
            "paid_api_calls": 0,
            "external_writes": 0,
            "live_product_execution": False,
        }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
