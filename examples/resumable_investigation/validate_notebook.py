"""Validate a clean notebook and run its cells without Jupyter or networking."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
from pathlib import Path
from unittest.mock import patch


def validate(require_schema: bool = False) -> dict:
    root = Path(__file__).resolve().parent
    path = root / "resume_voice_investigation.ipynb"
    notebook = json.loads(path.read_text(encoding="utf-8"))
    assert notebook["nbformat"] == 4 and notebook["nbformat_minor"] == 5
    schema = "not run (install nbformat for full schema validation)"
    try:
        import nbformat
    except ImportError:
        if require_schema:
            raise RuntimeError("nbformat is required for --require-schema") from None
    else:
        nbformat.validate(nbformat.read(path, as_version=4))
        schema = "passed"

    namespace = {"__name__": "__main__"}
    code_cells = 0
    original_cwd = Path.cwd()
    output = io.StringIO()
    try:
        os.chdir(root)
        # Socket denial is a smoke-test guard, not a general-purpose sandbox.
        with patch("socket.socket", side_effect=AssertionError("Network disabled")), \
             patch("socket.create_connection", side_effect=AssertionError("Network disabled")), \
             contextlib.redirect_stdout(output):
            for index, cell in enumerate(notebook["cells"]):
                if cell["cell_type"] == "code":
                    assert cell["outputs"] == [], "Commit notebooks without saved output"
                    assert cell["execution_count"] is None, "Clear execution counts"
                    source = "".join(cell["source"])
                    compiled = compile(source, f"{path.name}:cell-{index + 1}", "exec")
                    exec(compiled, namespace)
                    code_cells += 1
    finally:
        os.chdir(original_cwd)
    return {
        "notebook": path.name,
        "schema": schema,
        "sequential_code_cells_passed": code_cells,
        "network_during_cells": "Python sockets blocked",
        "full_jupyter_kernel": "not run",
        "cell_output": output.getvalue().splitlines(),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-schema", action="store_true")
    args = parser.parse_args()
    print(json.dumps(validate(args.require_schema), indent=2))
