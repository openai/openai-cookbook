"""Validate notebook structure and run its plain Python cells offline, without sockets.

This is not a substitute for upstream Jupyter execution. It provides a repeatable
fallback in sandboxes that cannot launch a Jupyter kernel.
It executes trusted local code, not arbitrary notebooks. The literal LIVE check
is a convenience guard, not a security boundary or network-isolation guarantee.
"""
from pathlib import Path
import contextlib
import io
import os
import sys
import nbformat

root = Path(__file__).resolve().parent
path = root / 'evidence_revision_gate.ipynb'
notebook = nbformat.read(path, as_version=4)
nbformat.validate(notebook)
namespace = {'__name__': '__notebook__'}
os.chdir(root)
sys.path.insert(0, str(root))
for i, cell in enumerate(notebook.cells):
    if cell.cell_type != 'code':
        continue
    if 'LIVE = True' in cell.source:
        raise RuntimeError('Refusing notebook with live extraction enabled.')
    output = io.StringIO()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
        exec(compile(cell.source, f'notebook-cell-{i}', 'exec'), namespace)
    cell.execution_count = None
    cell.outputs = [nbformat.v4.new_output('stream', name='stdout', text=output.getvalue())] if output.getvalue() else []
    print(output.getvalue(), end='')
nbformat.write(notebook, path)
print('All Python cells executed sequentially. Structure valid; counts cleared. Not a Jupyter-kernel run.')
