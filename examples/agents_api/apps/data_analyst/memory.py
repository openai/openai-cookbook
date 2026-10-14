"""Search and persist personal or team analyst corrections."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import uuid4


def relevant(record: dict[str, Any], query: str) -> bool:
    terms = {word for word in re.findall(r"[a-z0-9_]+", query.lower()) if len(word) > 2}
    if not terms:
        return True
    text = json.dumps(record, default=str).lower()
    return any(term in text for term in terms)


class MemoryStore:
    """Keep explicitly saved analyst corrections in a local JSON file."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def list(self, *, user_id: str = "analyst") -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        memories = json.loads(self.path.read_text())
        if not isinstance(memories, list):
            return []
        return [
            cast(dict[str, Any], memory)
            for memory in memories
            if isinstance(memory, dict)
            and (memory.get("scope") == "team" or memory.get("user_id") == user_id)
        ]

    def search(
        self, arguments: dict[str, Any], *, user_id: str = "analyst"
    ) -> dict[str, Any]:
        query = str(arguments.get("query", ""))
        return {
            "memories": [
                memory
                for memory in self.list(user_id=user_id)
                if relevant(memory, query)
            ][:10]
        }

    def save(
        self, arguments: dict[str, Any], *, user_id: str = "analyst"
    ) -> dict[str, Any]:
        note = str(arguments.get("note", "")).strip()
        scope = str(arguments.get("scope", "personal"))
        if not note:
            raise ValueError("A saved memory must contain a note.")
        if scope not in {"personal", "team"}:
            raise ValueError("A memory scope must be personal or team.")

        memories = (
            cast(list[dict[str, Any]], json.loads(self.path.read_text()))
            if self.path.exists()
            else []
        )
        memory: dict[str, Any] = {
            "id": uuid4().hex,
            "note": note,
            "scope": scope,
            "user_id": user_id,
            "created_at": datetime.now(UTC).isoformat(),
        }
        memories.append(memory)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(memories, indent=2) + "\n")
        return {"status": "saved", "memory": memory}

    def delete(self, memory_id: str, *, user_id: str = "analyst") -> dict[str, Any]:
        memory = next(
            (
                memory
                for memory in self.list(user_id=user_id)
                if memory.get("id") == memory_id
            ),
            None,
        )
        if memory is None:
            raise ValueError("Memory not found.")

        memories = cast(list[dict[str, Any]], json.loads(self.path.read_text()))
        memories = [item for item in memories if item.get("id") != memory_id]
        self.path.write_text(json.dumps(memories, indent=2) + "\n")
        return {"status": "deleted", "memory": memory}
