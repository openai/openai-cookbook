#!/usr/bin/env python3
"""Plan real-looking repository metadata without repository access or execution."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


sys.dont_write_bytecode = True
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

ROOT = Path(__file__).resolve().parents[1]
for source in (ROOT / "src", *sorted(ROOT.glob("*/src"))):
    if (source / "fleet_security" / "planning.py").is_file():
        sys.path.insert(0, str(source))
        break
else:
    raise RuntimeError("the metadata-only repository planning package is unavailable")

from fleet_security.inventory import InventoryError
from fleet_security.pipeline import PipelineError
from fleet_security.planning import prepare_repository_review


def main(argv: list[str] | None = None) -> int:
    examples = ROOT / "cookbook" / "security-review-pipeline"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=examples / "config.example.json")
    parser.add_argument("--inventory", type=Path, default=examples / "inventory.real.example.json")
    parser.add_argument("--approvals", type=Path, default=examples / "approvals.real.example.json")
    options = parser.parse_args(argv)
    try:
        result = prepare_repository_review(
            configuration_path=options.config,
            inventory_path=options.inventory,
            approvals_path=options.approvals,
        )
    except (InventoryError, PipelineError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
