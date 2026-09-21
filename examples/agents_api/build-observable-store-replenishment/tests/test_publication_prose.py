from __future__ import annotations

import json
from pathlib import Path

import pytest

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
    assert not found, (
        f"Remove revision-history language from publication prose: {found}"
    )


@pytest.mark.parametrize(
    "relative_dir",
    [
        ".",
        "examples/agents_api",
        "examples/agents_api/build-observable-store-replenishment/demo",
    ],
)
def test_notebook_setup_finds_repository_from_kernel_directory(
    monkeypatch, relative_dir
):
    repository = EXAMPLE_DIR.parents[2]
    monkeypatch.chdir(repository / relative_dir)
    notebook = json.loads(NOTEBOOK.read_text())
    source = "".join(
        next(cell for cell in notebook["cells"] if cell["id"] == "imports")["source"]
    )
    paths = source[source.index("REPO_ROOT =") : source.index("load_dotenv(ENV_FILE)")]
    namespace = {"Path": Path}
    exec(paths, namespace)  # noqa: S102 - exercise the checked-in notebook setup
    assert namespace["REPO_ROOT"].resolve() == repository.resolve()
    assert namespace["ENV_FILE"].resolve() == (repository / ".env.local").resolve()
    example_line = next(
        line for line in source.splitlines() if line.startswith("EXAMPLE_DIR =")
    )
    exec(example_line, namespace)  # noqa: S102 - exercise the checked-in notebook setup
    assert (namespace["EXAMPLE_DIR"] / "replenishment_agent.py").is_file()


def test_notebook_has_no_stale_execution_state():
    notebook = json.loads(NOTEBOOK.read_text())
    for cell in notebook["cells"]:
        if cell["cell_type"] == "code":
            assert cell["execution_count"] is None
            assert cell["outputs"] == []
