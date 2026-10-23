"""CRAWL and WALK own their lifecycles while honoring the same public result contracts."""

from __future__ import annotations

import ast
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from assistants.errors import LiveResponseError
from shared.reporting.schema import SCHEMA_VERSION

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(("phase", "other"), [("crawl", "walk"), ("walk", "crawl")])
def test_production_harness_does_not_import_its_sibling(phase: str, other: str) -> None:
    for path in (ROOT / f"{phase}_harness").rglob("*.py"):
        if "tests" in path.parts:
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            assert not any(name.split(".")[0] == f"{other}_harness" for name in names), path


@pytest.mark.parametrize("phase", ["crawl", "walk"])
@pytest.mark.parametrize("assistant", ["responses", "client"])
def test_own_cli_runs_with_sibling_imports_blocked(tmp_path: Path, phase: str, assistant: str) -> None:
    other = "walk" if phase == "crawl" else "crawl"
    output = tmp_path / "results"
    program = """
import importlib.abc, runpy, sys
blocked, module = sys.argv[1:3]
class BlockSibling(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] == blocked:
            raise AssertionError("Sibling import attempted: " + fullname)
sys.meta_path.insert(0, BlockSibling())
sys.argv = [module, *sys.argv[3:]]
runpy.run_module(module, run_name="__main__")
assert blocked not in sys.modules
"""
    environment = {key: value for key, value in os.environ.items() if not key.startswith("OPENAI_")}
    environment["PYTHONPATH"] = str(ROOT)
    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            program,
            f"{other}_harness",
            f"{phase}_harness.evaluate",
            "--offline",
            "--no-real-time",
            "--assistant",
            assistant,
            "--scenario",
            "restaurant_001",
            "--results-dir",
            str(output),
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    reports = list(output.glob("*/results.json"))
    assert len(reports) == 1
    report = json.loads(reports[0].read_text())
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["run"]["module"] == phase
    assert report["summary"] == {"total": 1, "passed": 1, "failed": 0, "infrastructure_errors": 0}
    row = report["results"][0]
    assert row["assessment"]["passed"] is True
    assert row["metrics"]["task"]["task_completed"] is True
    assert row["observability"]["interaction"]["audio_source"] == ("synthetic" if phase == "crawl" else "recorded")
    for relative in row["artifacts"].values():
        if isinstance(relative, str):
            path = (reports[0].parent / relative).resolve()
            assert path.is_relative_to(reports[0].parent.resolve())
            assert path.is_file()


@pytest.mark.parametrize("phase", ["crawl", "walk"])
async def test_local_batch_reports_infrastructure_errors_without_grading(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
) -> None:
    evaluator = importlib.import_module(f"{phase}_harness.evaluate")

    async def fail(**kwargs):
        raise LiveResponseError("fixture transport failure", failure_stage="response_collection")

    monkeypatch.setattr(evaluator, "_run_session", fail)
    args = evaluator.parse_args(
        ["--offline", "--no-real-time", "--scenario", "restaurant_001", "--results-dir", str(tmp_path)]
    )
    run_dir = await evaluator.run_evals(args)
    report = json.loads((run_dir / "results.json").read_text())
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["summary"]["infrastructure_errors"] == 1
    row = report["results"][0]
    assert row["status"] == "infrastructure_error"
    assert row["error"]["stage"] == "response_collection"
    assert not list((run_dir / "transcripts").glob("*.json"))
