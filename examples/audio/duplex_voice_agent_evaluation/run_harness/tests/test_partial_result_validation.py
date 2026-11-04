"""Malformed partial evidence cannot abort an already failed RUN scenario."""

from __future__ import annotations

import asyncio
import json
import socket
from collections.abc import Iterable
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from assistants.errors import LiveResponseError
from run_harness import evaluate
from shared.reporting.validation import ResultValidationError


def existing_artifacts(paths: Iterable[str]) -> set[Path]:
    return {Path(path).resolve() for path in paths if Path(path).is_file()}


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("Partial-result validation tests must stay offline")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


@pytest.mark.parametrize("fault", ["nonboolean", "missing", "prior-failure-validation", "typed-primary"])
async def test_primary_failure_with_invalid_partial_completion_retains_evidence_and_next_scenario(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    fault: str,
) -> None:
    real_evaluate = evaluate.run_gpt_live_conversation
    completed: list[str] = []
    captured: dict = {}
    primary = {"stage": "assistant_connection", "message": "Connection failed after captured work"}

    async def inject_after_real_offline_result(*args, **kwargs):
        result = await real_evaluate(*args, **kwargs)
        completed.append(result.scenario_id)
        assert result.task_metrics["task_completed"] is True
        if len(completed) == 1:
            captured["artifacts"] = await asyncio.to_thread(existing_artifacts, (result.artifacts or {}).values())
            captured["detail"] = Path(result.artifacts["result"])
            captured["efficiency"] = deepcopy(result.efficiency_metrics)
            if fault == "missing":
                result.task_metrics.pop("task_completed")
            else:
                result.task_metrics["task_completed"] = "false"
            if fault == "prior-failure-validation":
                result.run_metadata["failure"] = primary.copy()
                error = ResultValidationError("task_completed must be an explicitly observed boolean")
            else:
                if fault == "typed-primary":
                    result.run_metadata["failure"] = {"stage": "secondary", "message": "Secondary diagnostic"}
                error = LiveResponseError(primary["message"], failure_stage=primary["stage"])
            error.partial_result = result
            raise error
        return result

    monkeypatch.setattr(evaluate, "run_gpt_live_conversation", inject_after_real_offline_result)
    args = evaluate.parse_args(
        [
            "--offline",
            "--no-judge",
            "--max-examples",
            "2",
            "--concurrency",
            "1",
            "--verbose",
            "--results-dir",
            str(tmp_path),
        ]
    )

    run_dir = await asyncio.wait_for(evaluate.run_evals(args), timeout=45)

    report = json.loads((run_dir / "results.json").read_text())
    assert len(completed) == 2, "A malformed partial result must not prevent the next scenario"
    assert report["summary"] == {"total": 2, "passed": 1, "failed": 0, "infrastructure_errors": 1}
    invalid, following = report["results"]
    assert [invalid["scenario_id"], following["scenario_id"]] == completed
    assert invalid["status"] == "infrastructure_error"
    assert invalid["error"] == primary
    assert invalid["metrics"]["task"]["task_completed"] is False
    assert following["status"] == "passed"
    linked = {(run_dir / path).resolve() for path in invalid["artifacts"].values()}
    assert captured["artifacts"] <= linked
    assert all(path.is_file() for path in linked)
    assert any(path.suffix == ".wav" for path in linked)
    assert any(path.suffix == ".jsonl" for path in linked)
    detail = json.loads(captured["detail"].read_text())
    assert detail["task_status"] == "error"
    assert detail["task_metrics"]["task_completed"] is False
    assert detail["termination_reason"] == primary["stage"]
    assert detail["run_metadata"]["failure"] == primary
    assert detail["efficiency_metrics"] == captured["efficiency"]
    output = capsys.readouterr().out
    assert all(identifier in output for identifier in completed)


@pytest.mark.parametrize("completed", [True, False])
def test_valid_partial_completion_keeps_original_diagnostics_without_rewriting(
    monkeypatch: pytest.MonkeyPatch, completed: bool
) -> None:
    scenario = evaluate.load_run_scenarios(evaluate.DEFAULT_DATA_JSON, max_examples=1)[0]
    partial = SimpleNamespace(
        task_metrics={"task_completed": completed},
        run_metadata={"failure": {"stage": "secondary", "message": "Secondary diagnostic"}},
        artifacts={"result": "existing-diagnostic.json"},
    )
    projected = {"task_completed": completed, "result_path": "existing-diagnostic.json", "tool_calls": "1/1"}
    project = Mock(return_value=projected)
    write = Mock()
    monkeypatch.setattr(evaluate, "result_row", project)
    monkeypatch.setattr(evaluate, "write_json", write)
    error = LiveResponseError("Primary failure", failure_stage="assistant_connection")
    error.partial_result = partial

    row = evaluate.failed_row(
        scenario, error, offline=True, args=SimpleNamespace(condition="clean", model="fixture", backend_model="fixture")
    )

    project.assert_called_once_with(scenario, partial, offline=True)
    write.assert_not_called()
    assert partial.task_metrics["task_completed"] is completed
    assert row["status"] == "infrastructure_error"
    assert row["task_completed"] is False, "Failed rows retain their existing completion policy"
    assert row["failure_stage"] == "assistant_connection"
    assert row["error_message"] == "Primary failure"
    assert row["result_path"] == "existing-diagnostic.json"
    assert row["tool_calls"] == "1/1"
