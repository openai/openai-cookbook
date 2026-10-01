"""Load, search, and atomically save resolved incident history."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, cast


def load_history(path: Path) -> list[dict[str, Any]]:
    source = (
        path if path.exists() else Path(__file__).with_name("incident_history.json")
    )
    return cast(list[dict[str, Any]], json.loads(source.read_text()))


def save_history(path: Path, history: list[dict[str, Any]]) -> None:
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(history, indent=2) + "\n")
    temporary.replace(path)


def recall_incidents(
    history: list[dict[str, Any]], arguments: dict[str, Any]
) -> dict[str, Any]:
    name = str(arguments["service"])
    words = set(re.findall(r"[a-z0-9]+", str(arguments["query"]).lower()))
    candidates = [record for record in history if record.get("service") == name]
    ranked = sorted(
        candidates,
        key=lambda record: len(
            words.intersection(re.findall(r"[a-z0-9]+", json.dumps(record).lower()))
        ),
        reverse=True,
    )
    return {"service": name, "incidents": ranked[:3]}
