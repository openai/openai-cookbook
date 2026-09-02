#!/usr/bin/env python3
"""Reproduce the focused example, with optional real Docker and Jupyter checks."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
NAME = "governed_repository_security_reviews.ipynb"
sys.dont_write_bytecode = True


def _safe_notebook_failure(stderr: str) -> dict[str, object] | None:
    """Read only the runner's bounded failure protocol, never arbitrary logs."""
    for line in reversed(stderr[-16_384:].splitlines()):
        if not line.startswith("{") or len(line) > 12_000:
            continue
        try:
            value = json.loads(line)
        except (ValueError, RecursionError):
            continue
        if (type(value) is not dict or value.get("format") != "governed-notebook-failure/v1"
                or value.get("status") != "FAIL"):
            continue
        result: dict[str, object] = {"format": value["format"], "status": "FAIL"}
        for name in (
            "raw_cell_index_zero_based", "notebook_cell_number_one_based",
            "code_cell_number_one_based", "code_cells_completed", "line_in_cell_one_based",
        ):
            observed = value.get(name)
            if type(observed) is int and 0 <= observed <= 1_000_000:
                result[name] = observed
        kind = value.get("error_type")
        if type(kind) is str and kind in {
            "AssertionError", "RuntimeError", "ValueError", "TypeError", "KeyError",
            "OSError", "SyntaxError", "TimeoutError", "KeyboardInterrupt", "SystemExit",
            "OtherError", "NotebookSetupError",
        }:
            result["error_type"] = kind
        cleanup = value.get("temporary_state_cleanup")
        if type(cleanup) is str and cleanup in {"complete", "failed", "not_registered"}:
            result["temporary_state_cleanup"] = cleanup
        if type(value.get("working_directory_restored")) is bool:
            result["working_directory_restored"] = value["working_directory_restored"]
        contract = value.get("contract_failure")
        if type(contract) is dict:
            from fleet_security.reproduction import redact_reproduction_failure

            # The nested payload is re-allowlisted even though the child runner
            # already emitted a safe report. No subprocess can grant trust to text.
            redacted = redact_reproduction_failure(contract)
            if redacted is not None:
                result["contract_failure"] = redacted
        return result
    return None


def _command_failure(label: str, completed: subprocess.CompletedProcess[str]) -> RuntimeError:
    payload: dict[str, object] = {
        "format": "governed-verification-failure/v1", "status": "FAIL",
        "check": label, "returncode": completed.returncode,
        "raw_subprocess_output_included": False,
    }
    notebook = _safe_notebook_failure(completed.stderr)
    if notebook is not None:
        payload["notebook_failure"] = notebook
    return RuntimeError(json.dumps(payload, sort_keys=True))


def _local_docker_endpoint() -> str:
    """Validate the caller selection against the unchanged harness's daemon.

    The sandbox deliberately drops Docker overrides and HOME. Inspect with
    that same environment; accepting a different override would validate one
    daemon while running the proof against another.
    """
    sys.path.insert(0, str(ROOT / "src"))
    from field_autonomy.sandbox import scrubbed_environment

    def inspect(context: str | None, environment: dict[str, str]) -> str:
        command = ["docker", "context", "inspect"]
        if context:
            if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", context) is None:
                raise RuntimeError("Docker context name is invalid")
            command.append(context)
        command.extend(["--format", "{{.Endpoints.docker.Host}}"])
        return subprocess.run(command, capture_output=True, text=True, env=environment,
                              timeout=15, check=True).stdout.strip()

    def socket_path(endpoint: str) -> Path:
        parsed = urlsplit(endpoint)
        if (parsed.scheme != "unix" or parsed.netloc or not parsed.path.startswith("/")
                or parsed.query or parsed.fragment or "\x00" in endpoint):
            raise RuntimeError("the local Docker proof requires a Unix-socket daemon")
        return Path(parsed.path).resolve()

    default = inspect(None, scrubbed_environment())
    default_path = socket_path(default)
    context = os.environ.get("DOCKER_CONTEXT")
    host = os.environ.get("DOCKER_HOST")
    selected = inspect(context, dict(os.environ)) if context else host or default
    if socket_path(selected) != default_path:
        raise RuntimeError("this proof supports the default local daemon only; unset Docker overrides")
    return default


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docker", action="store_true", help="Require actual restricted containers; never fall back.")
    parser.add_argument("--jupyter", action="store_true", help="Also execute with nbclient and a real Python kernel.")
    parser.add_argument("--receipt", type=Path, help="Optional new receipt outside this checkout.")
    arguments = parser.parse_args()
    if arguments.receipt:
        receipt = arguments.receipt.expanduser().absolute()
        if receipt.exists() or receipt.is_symlink() or receipt.resolve().is_relative_to(ROOT.resolve()):
            parser.error("--receipt must be a new file outside the checkout")
        if not receipt.parent.is_dir() or receipt.parent.is_symlink():
            parser.error("--receipt parent must be an existing real directory")
    notebook = ROOT / NAME
    if not notebook.is_file():
        notebook = ROOT / "cookbook" / NAME
    if notebook.is_symlink() or not notebook.is_file():
        raise RuntimeError("the complete notebook and support files are required")
    sys.path.insert(0, str(ROOT / "src"))
    from fleet_security.recipe import RecipeConfiguration
    from fleet_security.reproduction import (
        DEMO_ATTEMPTED_REPOSITORIES, DEMO_EXPECTED_STATUSES, assert_cycle_accounting,
    )

    configuration = RecipeConfiguration.from_file(
        ROOT / "cookbook/security-review-pipeline/config.example.json",
    )
    notebook_digest = hashlib.sha256(notebook.read_bytes()).hexdigest()
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="cookbook-reproduction-") as temporary:
        scratch = Path(temporary)
        # These commands are offline. No credentials, private HOME or project
        # root override are forwarded to the reproduction processes.
        environment = {
            name: value for name, value in os.environ.items()
            if name in {"PATH", "SYSTEMROOT", "TMPDIR", "LANG", "LC_ALL"}
        }
        environment.update({
            "HOME": str(scratch), "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(ROOT / "src"),
            "RUN_FLEET_DOCKER": "1" if arguments.docker else "0",
            "RUN_RECIPE_DOCKER": "1" if arguments.docker else "0",
            "RUN_STRESS_DOCKER": "1" if arguments.docker else "0",
            "RUN_SECURITY_COOKBOOK_DOCKER": "1" if arguments.docker else "0",
            "RUN_LIVE_MODEL": "0", "APPROVE_PAID_OPENAI_REQUEST": "0",
        })
        # Docker Desktop's socket is a host prerequisite, not a container mount.
        # Preserve only the already selected daemon address, not HOME credentials.
        docker_prerequisite = {"checked": False}
        if arguments.docker:
            endpoint = _local_docker_endpoint()
            environment["DOCKER_HOST"] = endpoint
            environment.pop("DOCKER_CONTEXT", None)
            cached_image_id = subprocess.run(
                ["docker", "image", "inspect", "python:3.12-alpine", "--format", "{{.Id}}"],
                env=environment, capture_output=True, text=True, timeout=15, check=True,
            ).stdout.strip()
            if re.fullmatch(r"sha256:[0-9a-f]{64}", cached_image_id) is None:
                raise RuntimeError("the cached Docker image has no verifiable content identity")
            docker_prerequisite = {"checked": True, "endpoint": "default_local_unix_socket",
                                   "cached_image_id": cached_image_id, "image_pulled": False}
        runs: list[dict[str, object]] = []

        def run(label: str, argv: list[str], *, cwd: Path = ROOT, timeout: int = 300) -> str:
            tick = time.monotonic()
            completed = subprocess.run(argv, cwd=cwd, env=environment,
                                       capture_output=True, text=True, timeout=timeout, check=False)
            if completed.returncode:
                raise _command_failure(label, completed)
            runs.append({"check": label, "status": "PASS", "elapsed_seconds": round(time.monotonic() - tick, 3)})
            return completed.stdout

        command = [sys.executable, "-B", "scripts/run_security_review_cookbook.py", "--cycles", "2"]
        if arguments.docker:
            command.append("--docker")
        demo = json.loads(run("two-cycle recipe", command))
        cycles = demo.get("cycle_receipts")
        if type(cycles) is not list or len(cycles) != 2:
            raise RuntimeError("the two-cycle recipe must return both original cycle receipts")
        attempt_accounting = [
            assert_cycle_accounting(
                cycle, expected_attempted_repositories=(DEMO_ATTEMPTED_REPOSITORIES if index == 0 else ()),
                expected_statuses=DEMO_EXPECTED_STATUSES, policy=configuration.policy,
                expected_isolation_receipts=3 if arguments.docker and index == 0 else 0,
                context="verify_first_cycle" if index == 0 else "verify_restart_cycle",
            )
            for index, cycle in enumerate(cycles)
        ]
        if (demo.get("scanner_invocations_per_cycle") != [row["scanner_invocations"] for row in cycles]
                or demo.get("latest") != cycles[-1] or demo.get("live_product_execution") is not False
                or demo.get("paid_api_calls") != 0 or demo.get("external_writes") != 0):
            raise RuntimeError("the recipe aggregate does not match its checked cycle receipts")
        expected_states = {
            "awaiting_finding_disposition": 2, "awaiting_scope_approval": 1,
            "awaiting_threat_model_approval": 1, "failed_safe_abstention": 1,
            "review_packet_ready": 1,
        }
        if demo["latest"]["decision_states"] != expected_states:
            raise RuntimeError("the six fictional repositories produced unexpected decisions")
        if arguments.docker and demo["latest"].get("execution_mode") != "synthetic_restricted_docker":
            raise RuntimeError("requested Docker execution was not proved")
        planner = json.loads(run("metadata-only planner", [sys.executable, "-B", "scripts/prepare_repository_review.py"]))
        if planner["scanned_repositories"] != 0 or planner["finding_count"] is not None:
            raise RuntimeError("metadata planning was misrepresented as scanning")
        context_eval = json.loads(run("independent threat-context labels", [sys.executable, "-B", "scripts/evaluate_threat_context.py"]))
        if context_eval.get("status") != "PASS":
            raise RuntimeError("independently labelled threat-context checks failed")
        # The runner deliberately executes from notebook.parent without an
        # injected PROJECT_ROOT. The kernel check below is separate evidence.
        run("ordinary notebook-directory execution", [sys.executable, "-B", str(ROOT / "scripts/execute_notebook.py"), str(notebook)], cwd=notebook.parent)
        suites = []
        for folder in ("fleet-tests", "cookbook/security-review-pipeline/tests", "stress-tests"):
            # Canonical repository includes distribution/development tests too;
            # the staged focused example contains only its selected dependencies.
            completed = subprocess.run(
                [sys.executable, "-B", "-m", "unittest", "discover", "-s", folder, "-q"],
                cwd=ROOT, env=environment, capture_output=True, text=True, timeout=600, check=False,
            )
            if completed.returncode:
                raise _command_failure(f"test suite: {folder}", completed)
            count = re.search(r"Ran\s+(\d+)\s+tests?", completed.stderr)
            if not count or int(count.group(1)) == 0:
                raise RuntimeError(f"test suite did not execute tests: {folder}")
            skipped = re.search(r"skipped=(\d+)", completed.stderr)
            skip_count = int(skipped.group(1)) if skipped else 0
            if arguments.docker and skip_count:
                raise RuntimeError(f"Docker-required verification skipped tests: {folder}")
            suites.append({"suite": folder, "tests": int(count.group(1)), "skipped": skip_count, "status": "PASS"})
        kernel = {"requested": arguments.jupyter, "executed": False}
        if arguments.jupyter:
            import nbformat
            from nbclient import NotebookClient
            document = nbformat.read(notebook, as_version=4)
            old = os.environ.copy()
            try:
                os.environ.clear()
                os.environ.update(environment)
                # Reuse the installed Python kernel, while keeping HOME private.
                os.environ["JUPYTER_PATH"] = str(Path(sys.prefix) / "share/jupyter")
                client = NotebookClient(document, timeout=180, kernel_name="python3",
                                        resources={"metadata": {"path": str(notebook.parent)}})
                client.execute()
            finally:
                os.environ.clear()
                os.environ.update(old)
            code = [cell for cell in document.cells if cell.cell_type == "code"]
            if any(cell.execution_count is None or any(output.output_type == "error" for output in cell.outputs) for cell in code):
                raise RuntimeError("ordinary Jupyter execution left an unexecuted or failed cell")
            kernel = {"requested": True, "executed": True, "code_cells": len(code),
                      "working_directory": "notebook_directory", "project_root_injected": False}
        if hashlib.sha256(notebook.read_bytes()).hexdigest() != notebook_digest:
            raise RuntimeError("verification modified the publication notebook")
        result = {
            "verification": "PASS", "scope": "focused_security_tutorial",
            "notebook_sha256": notebook_digest, "notebook_unmodified": True,
            "docker_required": arguments.docker, "docker_prerequisite": docker_prerequisite, "jupyter": kernel,
            "checks": runs, "test_suites": suites,
            "total_tests": sum(row["tests"] for row in suites),
            "total_skipped": sum(row["skipped"] for row in suites),
            "synthetic_scan_attempts_per_cycle": demo["scanner_invocations_per_cycle"],
            "attempt_accounting_per_cycle": attempt_accounting,
            "decisions": expected_states,
            "threat_context_evaluation": context_eval,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "live_scans": 0, "paid_calls": 0, "provider_writes": 0,
        }
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if arguments.receipt:
        descriptor = os.open(receipt, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(payload)
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
