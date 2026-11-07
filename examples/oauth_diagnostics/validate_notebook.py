"""Validate this trusted notebook and execute cells sequentially, without a kernel.

This is not a notebook sandbox or a full Jupyter execution test. Never use this
helper to execute an untrusted notebook. Network stubs are a regression guard,
not a security boundary. The filename is intentionally not user-configurable.
"""

import ast
from contextlib import redirect_stdout
import io
from pathlib import Path
import socket
import sys
from unittest.mock import patch

import nbformat


def main():
    root = Path(__file__).resolve().parent
    notebook = nbformat.read(root / "mcp_connection_doctor.ipynb", as_version=4)
    nbformat.validate(notebook)
    cells = [cell for cell in notebook.cells if cell.cell_type == "code"]
    for cell in cells:
        if cell.execution_count is not None or cell.outputs:
            raise AssertionError("The source notebook must not contain saved runtime outputs.")
        ast.parse(cell.source)
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    namespace = {"__name__": "__notebook_check__"}
    output = io.StringIO()
    with patch.object(socket, "socket", side_effect=AssertionError("Network disabled")), \
         patch.object(socket, "getaddrinfo", side_effect=AssertionError("DNS disabled")), \
         redirect_stdout(output):
        for number, cell in enumerate(cells, 1):
            exec(compile(cell.source, f"notebook_cell_{number}", "exec"), namespace)
    print(f"Notebook schema valid; {len(cells)} Python cells executed sequentially with network stubs.")
    print("Full Jupyter kernel execution was not attempted or verified.")
    print(output.getvalue(), end="")


if __name__ == "__main__":
    main()
