from __future__ import annotations

"""Shared utilities for the multi-agent investment workflow."""

from pathlib import Path
import json

from agents.tracing.processor_interface import TracingExporter

# ---------------------------------------------------------------------------
# Global disclaimer for all agents
# ---------------------------------------------------------------------------

DISCLAIMER = (
    "DISCLAIMER: I am an AI language model, not a registered investment adviser. "
    "Information provided is educational and general in nature. Consult a qualified "
    "financial professional before making any investment decisions.\n\n"
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT_DIR: Path = Path(__file__).resolve().parent  # repository root


def repo_path(rel: str | Path) -> Path:
    """Return an absolute Path inside the repository given a relative string."""
    return (ROOT_DIR / rel).resolve()


def outputs_dir() -> Path:
    """Return the global `outputs/` folder, creating it if needed."""
    out = repo_path("outputs")
    out.mkdir(parents=True, exist_ok=True)
    return out

# ---------------------------------------------------------------------------
# Prompt loader
# ---------------------------------------------------------------------------

PROMPTS_DIR: Path = repo_path("prompts")


def load_prompt(name: str, **subs) -> str:
    """Load a Markdown prompt template and substitute <PLACEHOLDERS>."""
    content = (PROMPTS_DIR / name).read_text()
    for key, val in subs.items():
        content = content.replace(f"<{key}>", str(val))
    return content

# ---------------------------------------------------------------------------
# Local trace exporter
# ---------------------------------------------------------------------------

class FileSpanExporter(TracingExporter):
    """Write spans/traces to a JSONL file under `logs/`."""

    def __init__(self, logfile: str | Path = "logs/agent_traces.jsonl") -> None:
        path = repo_path(logfile)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.logfile = path

    def export(self, items):  # noqa: D401 – simple signature required by SDK
        with self.logfile.open("a", encoding="utf-8") as f:
            for item in items:
                try:
                    f.write(json.dumps(item.export(), default=str) + "\n")
                except Exception:
                    f.write(str(item) + "\n")

# ---------------------------------------------------------------------------
# Output path helper
# ---------------------------------------------------------------------------


def output_file(name: str | Path, *, make_parents: bool = True) -> Path:
    """Return an absolute Path under the shared outputs/ directory.

    If *name* already starts with the string "outputs/", that prefix is removed
    to avoid accidentally nesting a second outputs folder (e.g.
    `outputs/outputs/foo.png`).  Absolute paths are returned unchanged.
    """

    path = Path(name)

    if path.is_absolute():
        return path

    # Strip leading "outputs/" if present
    if path.parts and path.parts[0] == "outputs":
        path = Path(*path.parts[1:])

    final = outputs_dir() / path

    if make_parents:
        final.parent.mkdir(parents=True, exist_ok=True)

    return final

__all__ = [
    "ROOT_DIR",
    "repo_path",
    "outputs_dir",
    "load_prompt",
    "FileSpanExporter",
    "output_file",
] 