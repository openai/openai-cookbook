#!/usr/bin/env python3
"""Validate registry.yaml and this cookbook's publication entry."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ModuleNotFoundError as exc:
    raise SystemExit(
        "ERROR - registry validation requires PyYAML - install the yaml package"
    ) from exc

try:
    import jsonschema
except ModuleNotFoundError as exc:
    raise SystemExit(
        "ERROR - registry validation requires jsonschema - install the jsonschema package"
    ) from exc


EXPECTED_ENTRY = {
    "title": "Observe Codex with OpenTelemetry and Grafana LGTM",
    "path": "examples/codex/codex-opentelemetry-observability/README.md",
    "slug": "codex-opentelemetry-observability",
    "authors": ["henzelmann-oai"],
    "tags": ["codex", "opentelemetry", "observability", "tracing", "open-source"],
}


def normalize_dates(value: Any) -> Any:
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: normalize_dates(child) for key, child in value.items()}
    if isinstance(value, list):
        return [normalize_dates(child) for child in value]
    return value


def format_json_path(path: Any) -> str:
    location = "$"
    for part in path:
        location += f"[{part}]" if isinstance(part, int) else f".{part}"
    return location


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--schema", type=Path, required=True)
    args = parser.parse_args()

    try:
        registry = normalize_dates(yaml.safe_load(args.registry.read_text(encoding="utf-8")))
        schema = json.loads(args.schema.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, yaml.YAMLError) as exc:
        print(f"ERROR - could not load registry inputs - {exc}", file=sys.stderr)
        return 1

    validator = jsonschema.Draft7Validator(
        schema, format_checker=jsonschema.FormatChecker()
    )
    errors = sorted(validator.iter_errors(registry), key=lambda error: list(error.path))
    for error in errors:
        print(
            f"ERROR - registry schema at {format_json_path(error.path)} - {error.message}",
            file=sys.stderr,
        )

    matching_entries = [
        entry
        for entry in registry
        if isinstance(entry, dict) and entry.get("slug") == EXPECTED_ENTRY["slug"]
    ] if isinstance(registry, list) else []
    if len(matching_entries) != 1:
        print(
            f"ERROR - expected exactly one registry entry for {EXPECTED_ENTRY['slug']}",
            file=sys.stderr,
        )
        errors.append(None)
    else:
        entry = matching_entries[0]
        for key, expected_value in EXPECTED_ENTRY.items():
            if entry.get(key) != expected_value:
                print(
                    f"ERROR - registry entry {key} must be {expected_value!r}",
                    file=sys.stderr,
                )
                errors.append(None)
        if not isinstance(entry.get("description"), str) or not entry["description"].strip():
            print("ERROR - registry entry must have a description", file=sys.stderr)
            errors.append(None)
        publication_path = args.registry.parent / EXPECTED_ENTRY["path"]
        if not publication_path.is_file():
            print(
                f"ERROR - registry publication path does not exist - {publication_path}",
                file=sys.stderr,
            )
            errors.append(None)

    if errors:
        print(f"FAILED - {len(errors)} registry validation error(s)", file=sys.stderr)
        return 1
    print("PASS - registry schema and cookbook publication entry")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
