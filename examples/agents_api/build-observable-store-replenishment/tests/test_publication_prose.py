from __future__ import annotations

import json
from pathlib import Path

EXAMPLE_DIR = Path(__file__).parents[1]
ARTICLE = EXAMPLE_DIR.parent / "build-observable-store-replenishment.md"
NOTEBOOK = EXAMPLE_DIR.parent / "build-observable-store-replenishment.ipynb"

REVISION_HISTORY_PHRASES = (
    "as discussed",
    "like we discussed",
    "as requested",
    "based on your feedback",
    "in response to feedback",
    "we changed",
    "we added",
    "we updated",
    "this now also",
    "now also shows",
    "previous draft",
    "earlier version",
)


def notebook_markdown() -> str:
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    return "\n".join(
        "".join(cell.get("source", []))
        for cell in notebook["cells"]
        if cell.get("cell_type") == "markdown"
    )


def test_publication_prose_contains_no_revision_history():
    publication_text = "\n".join(
        [ARTICLE.read_text(encoding="utf-8"), notebook_markdown()]
    ).lower()

    found = [
        phrase for phrase in REVISION_HISTORY_PHRASES if phrase in publication_text
    ]
    assert not found, f"Remove revision-history language from publication prose: {found}"
