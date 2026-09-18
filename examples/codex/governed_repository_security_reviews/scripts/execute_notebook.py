"""Execute a clean Cookbook notebook offline without requiring Jupyter or nbformat."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")


def execution_mode(namespace: dict[str, object]) -> str:
    transport = namespace.get("live_transport")
    evidence = getattr(transport, "request_evidence", ())
    hosted_completed = any(
        isinstance(event, dict)
        and event.get("policy_decision") == "approved_responses_create"
        and event.get("verification_result") == "completed"
        for event in evidence
    )
    if hosted_completed:
        return "live_responses_and_restricted_docker"
    if namespace.get("docker_enabled") is True:
        return "offline_replay_with_restricted_docker"
    return "offline_by_default"


class NotebookExecutionFailure(RuntimeError):
    """A safe location/contract receipt, without arbitrary exception messages."""

    def __init__(self, diagnostic: dict[str, object], *, returncode: int = 1) -> None:
        self.diagnostic = diagnostic
        self.returncode = returncode
        super().__init__(json.dumps(diagnostic, sort_keys=True))


def _failure_details(error: BaseException, *, raw_index: int, code_number: int,
                     executed: int, filename: str) -> dict[str, object]:
    line = None
    cursor = error.__traceback__
    while cursor is not None:
        if cursor.tb_frame.f_code.co_filename == filename:
            line = cursor.tb_lineno
        cursor = cursor.tb_next
    if type(error) is SyntaxError and type(error.lineno) is int:
        line = error.lineno
    known_errors = (
        AssertionError, RuntimeError, ValueError, TypeError, KeyError, OSError,
        SyntaxError, TimeoutError, KeyboardInterrupt, SystemExit,
    )
    error_type = next((kind.__name__ for kind in known_errors if isinstance(error, kind)), "OtherError")
    diagnostic: dict[str, object] = {
        "format": "governed-notebook-failure/v1", "status": "FAIL",
        "raw_cell_index_zero_based": raw_index,
        "notebook_cell_number_one_based": raw_index + 1,
        "code_cell_number_one_based": code_number,
        "code_cells_completed": executed,
        "line_in_cell_one_based": line, "error_type": error_type,
    }
    # Do not import or inject a project root. A tutorial that deliberately used
    # the checked helper already loaded this trusted module in its setup cell.
    support = sys.modules.get("fleet_security.reproduction")
    failure_type = getattr(support, "ReproductionFailure", None)
    if isinstance(failure_type, type) and type(error) is failure_type:
        # Reconstruct from the helper's already-redacted fields, not repr(error),
        # the notebook namespace, source snippets or an untrusted scanner reason.
        diagnostic["contract_failure"] = support.redact_reproduction_failure(error.diagnostic)
    return diagnostic


def _cleanup_notebook_state(namespace: dict[str, object]) -> str:
    state = namespace.get("temporary_state")
    if type(state) is not tempfile.TemporaryDirectory:
        return "not_registered"
    try:
        state.cleanup()
        return "complete" if not Path(state.name).exists() else "failed"
    except Exception:
        return "failed"


def execute_notebook(notebook: Path) -> dict[str, object]:
    notebook = notebook.resolve(strict=True)
    document = json.loads(notebook.read_text(encoding="utf-8"))
    if document.get("nbformat") != 4:
        raise ValueError("expected a Jupyter notebook using nbformat 4")
    # Match a normal notebook kernel: start beside the notebook and require
    # its own setup cell to find the package, without hidden root injection.
    namespace = {"__name__": "__main__"}
    initial_directory = Path.cwd()
    os.chdir(notebook.parent)
    executed = 0
    code_number = 0
    failure = None
    failure_returncode = 1
    try:
        for number, cell in enumerate(document.get("cells", [])):
            if cell.get("cell_type") != "code":
                continue
            code_number += 1
            filename = f"notebook-cell-{number}"
            try:
                if cell.get("outputs") or cell.get("execution_count") is not None:
                    raise ValueError("notebook contains saved execution state")
                source = "".join(cell.get("source", []))
                exec(compile(source, filename, "exec"), namespace)
            except BaseException as error:
                failure = _failure_details(error, raw_index=number, code_number=code_number,
                                           executed=executed, filename=filename)
                failure_returncode = 130 if isinstance(error, KeyboardInterrupt) else 1
                break
            executed += 1
    finally:
        if failure is not None:
            failure["temporary_state_cleanup"] = _cleanup_notebook_state(namespace)
        try:
            os.chdir(initial_directory)
        except OSError:
            if failure is None:
                failure = {"format": "governed-notebook-failure/v1", "status": "FAIL"}
            failure["working_directory_restored"] = False
        else:
            if failure is not None:
                failure["working_directory_restored"] = True
    if failure is not None:
        raise NotebookExecutionFailure(failure, returncode=failure_returncode) from None
    return {
        "notebook": str(notebook),
        "code_cells_executed": executed,
        "mode": execution_mode(namespace),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute every notebook code cell in one shared Python namespace.")
    parser.add_argument("notebook", type=Path, nargs="?", default=ROOT / "cookbook" / "bounded_autonomous_development.ipynb")
    arguments = parser.parse_args()
    try:
        result = execute_notebook(arguments.notebook)
    except NotebookExecutionFailure as error:
        print(json.dumps(error.diagnostic, sort_keys=True), file=sys.stderr)
        return error.returncode
    except Exception:
        print(json.dumps({
            "format": "governed-notebook-failure/v1", "status": "FAIL",
            "phase": "setup", "error_type": "NotebookSetupError",
        }, sort_keys=True), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
