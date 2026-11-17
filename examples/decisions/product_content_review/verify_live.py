"""Contributor check: run both entry points with real API requests."""

import getpass
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from review import ROOT, REQUEST_DELAY_SECONDS, load_cases


def main():
    (ROOT / "results" / "live_validation.json").unlink(missing_ok=True)
    # The key stays in process memory and child environments, never in a file.
    key = os.environ.get("OPENAI_API_KEY") or getpass.getpass("Existing work API key (hidden): ")
    if not key.strip():
        raise SystemExit("An API key is required.")
    count = len(load_cases()["cases"])
    print(f"LIVE VALIDATION: {count * 2} paid requests, CLI then notebook.", flush=True)
    env = dict(os.environ, OPENAI_API_KEY=key)
    subprocess.run([sys.executable, "-u", str(ROOT / "run_review.py"), "--all",
                    "--output", str(ROOT / "results" / "cli")], check=True, env=env)

    print(f"CLI complete. Waiting {REQUEST_DELAY_SECONDS}s before the notebook...", flush=True)
    time.sleep(REQUEST_DELAY_SECONDS)

    import nbformat
    from jupyter_client import KernelManager
    from jupyter_client.kernelspec import KernelSpecManager
    from nbclient import NotebookClient

    notebook = nbformat.read(ROOT / "product_content_review.ipynb", as_version=4)
    # A temporary kernel spec selects this exact environment, not a global Python.
    with tempfile.TemporaryDirectory() as temporary:
        spec = Path(temporary) / "cookbook-live"
        spec.mkdir()
        (spec / "kernel.json").write_text(json.dumps({
            "argv": [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
            "display_name": "Cookbook live validation", "language": "python"}))
        manager = KernelManager(kernel_name="cookbook-live", kernel_spec_manager=
                                KernelSpecManager(kernel_dirs=[temporary]))
        runner = NotebookClient(notebook, km=manager, timeout=300,
                                resources={"metadata": {"path": str(ROOT)}})
        runner.on_cell_execute = lambda cell, cell_index: print(
            f"Notebook cell {cell_index + 1}/{len(notebook.cells)}", flush=True)
        print("Running the actual notebook, including all live cells...", flush=True)
        try:
            runner.execute(env=env)
        finally:
            if manager.has_kernel:
                manager.shutdown_kernel(now=True)
    output = ROOT / "results" / "notebook"
    nbformat.write(notebook, output / "executed.ipynb")
    for name in ["cli", "notebook"]:
        rows = json.loads((ROOT / "results" / name / "results.json").read_text())
        if len(rows) != count or any(len(row["answers"]) != 4 for row in rows):
            raise RuntimeError(f"Incomplete live results for {name}.")
        print(f"{name}: {len(rows)} live requests completed; inspect metrics.json for label agreement.")
    manifest = {"completed_at": datetime.now(timezone.utc).isoformat(),
                "requests_per_entry_point": count,
                "source_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in ROOT.iterdir()
                                  if p.suffix in {".py", ".ipynb", ".json"}}}
    (ROOT / "results" / "live_validation.json").write_text(json.dumps(manifest, indent=2))
    print("Both live entry points completed. Reports and evidence are in results/.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Live validation stopped: {type(error).__name__}. No automatic retry.")
        raise SystemExit(1) from None
