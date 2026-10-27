"""Validate and sequentially execute offline cells without starting a kernel."""
from contextlib import redirect_stdout
import io
from pathlib import Path
import sys

import nbformat


def main() -> None:
    root = Path(__file__).resolve().parent
    notebook = nbformat.read(root / "evidence_driven_agent_teams.ipynb", as_version=4)
    nbformat.validate(notebook)
    namespace = {"__name__": "__main__"}
    sys.path.insert(0, str(root))
    count = 0
    for index, cell in enumerate(notebook.cells):
        if cell.cell_type != "code":
            continue
        code = compile(cell.source, f"notebook-cell-{index}", "exec")
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            exec(code, namespace)
        print(f"Cell {index}: passed")
        print(buffer.getvalue(), end="")
        count += 1
    print(f"PASS: nbformat schema, syntax, and {count} sequential Python code cells.")
    print("NOT RUN: a full Jupyter kernel, notebook UI/rendering, or live API calls.")


if __name__ == "__main__":
    main()
