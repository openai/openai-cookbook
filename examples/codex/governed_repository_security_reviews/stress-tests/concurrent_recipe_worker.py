#!/usr/bin/env python3
"""One independent OS process in a barrier-synchronised synthetic recipe race."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkout", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--approvals", required=True, type=Path)
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--ready", required=True, type=Path)
    parser.add_argument("--start", required=True, type=Path)
    parser.add_argument("--worker", required=True, type=int)
    parser.add_argument("--barrier-before-bootstrap", action="store_true")
    options = parser.parse_args()
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.path.insert(0, str(options.checkout / "src"))
    from fleet_security.recipe import RecurringSecurityRecipe

    try:
        def barrier() -> None:
            ready = options.ready / f"worker-{options.worker:02}.ready"
            descriptor = os.open(ready, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(descriptor)
            deadline = time.monotonic() + 20
            while not options.start.exists():
                if time.monotonic() >= deadline:
                    raise TimeoutError("bounded synthetic start barrier expired")
                time.sleep(0.002)

        if options.barrier_before_bootstrap:
            barrier()
        recipe = RecurringSecurityRecipe.from_files(
            configuration_path=options.config,
            inventory_path=options.inventory,
            approvals_path=options.approvals,
            state_directory=options.state,
        )
        if not options.barrier_before_bootstrap:
            barrier()
        result = recipe.cycle()
        output = {
            "status": "PASS",
            "worker": options.worker,
            "pid": os.getpid(),
            "run_number": result["run_number"],
            "scanner_invocations": result["scanner_invocations"],
            "audit_valid": result["audit_valid"],
            "external_writes": result["external_writes"],
        }
    except Exception as error:
        output = {
            "status": "FAIL",
            "worker": options.worker,
            "pid": os.getpid(),
            "error_type": type(error).__name__,
        }
    print(json.dumps(output, sort_keys=True))
    return 0 if output["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
