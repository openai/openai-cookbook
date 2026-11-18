"""Malformed completion cannot turn a real offline batch into a pass or abort it."""

from __future__ import annotations

import asyncio
import importlib
import json
import re
import socket
from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path

import pytest


def existing_artifacts(paths: Iterable[str | Path | None]) -> set[Path]:
    return {Path(path).resolve() for path in paths if path and Path(path).is_file()}


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("Report validation integration tests must stay offline")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


@pytest.mark.parametrize(
    ("phase", "malformed"),
    [
        pytest.param("crawl", "completion", id="crawl"),
        pytest.param("walk", "completion", id="walk"),
        pytest.param("run", "completion", id="run"),
        pytest.param("crawl", "status", id="crawl-unknown-status"),
        pytest.param("walk", "status", id="walk-unknown-status"),
    ],
)
async def test_malformed_completion_preserves_verbose_batch_and_saved_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    phase: str,
    malformed: str,
) -> None:
    evaluator = importlib.import_module(f"{phase}_harness.evaluate")
    boundary = "run_gpt_live_conversation" if phase == "run" else "run_single_eval"
    real_evaluate = getattr(evaluator, boundary)
    completed: list[str] = []
    captured_artifacts: dict[str, set[Path]] = {}

    async def inject_after_real_offline_result(*args, **kwargs):
        result = await real_evaluate(*args, **kwargs)
        identifier = result.scenario_id if phase == "run" else result.example_id
        assert result.task_metrics["task_completed"] is True, "The unmodified fixture must pass"
        completed.append(identifier)
        if phase == "run":
            paths = (result.artifacts or {}).values()
        else:
            paths = (
                result.artifact_paths.event_log_path,
                result.artifact_paths.transcript_path,
                result.artifact_paths.conversation_audio_path,
                result.artifact_paths.conversation_transcript_path,
            )
        captured_artifacts[identifier] = await asyncio.to_thread(existing_artifacts, paths)
        if len(completed) == 2:
            # Inject only the bad value; preserve real transport, grading, and artifacts.
            if malformed == "completion":
                result.task_metrics["task_completed"] = "false"
            else:
                result.error_info = replace(result.error_info, status="unknown")
        return result

    monkeypatch.setattr(evaluator, boundary, inject_after_real_offline_result)
    argv = [
        "--offline",
        "--max-examples",
        "3",
        "--concurrency",
        "1",
        "--verbose",
        "--results-dir",
        str(tmp_path),
    ]
    argv += ["--no-judge"] if phase == "run" else ["--no-real-time"]

    run_dir = await asyncio.wait_for(evaluator.run_evals(evaluator.parse_args(argv)), timeout=45)

    report = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    assert len(completed) == 3, "Invalid result evidence must not stop the following scenario"
    assert [row["scenario_id"] for row in report["results"]] == completed
    assert report["summary"] == {"total": 3, "passed": 2, "failed": 0, "infrastructure_errors": 1}
    before, invalid, after = report["results"]
    assert before["status"] == after["status"] == "passed"
    assert invalid["status"] == "infrastructure_error"
    assert invalid["error"]["stage"] == "result_validation"
    assert invalid["metrics"]["task"]["task_completed"] is False
    assert ("task_completed" if malformed == "completion" else "status") in invalid["error"]["message"]
    saved_artifacts = {(run_dir / value).resolve() for value in invalid["artifacts"].values()}
    original_artifacts = captured_artifacts[completed[1]]
    assert original_artifacts, "The malformed case must already have genuine captured artifacts"
    assert original_artifacts <= saved_artifacts, "Validation must retain links to existing evidence"
    assert all(path.is_file() for path in saved_artifacts)
    assert any(path.suffix == ".wav" for path in saved_artifacts)
    assert any(path.suffix == ".jsonl" for path in saved_artifacts)
    output = capsys.readouterr().out
    assert all(identifier in output for identifier in completed), "Verbose output must tolerate the invalid row"
    assert invalid["error"]["message"] in output, "Verbose output must explain why the case was excluded"
    if phase != "run":
        console_statuses = re.findall(r"^\s*RESULT\s+(PASS|FAIL|ERROR)\b", output, flags=re.MULTILINE)
        assert console_statuses == ["PASS", "ERROR", "PASS"], "Console grades must agree with the saved report"
