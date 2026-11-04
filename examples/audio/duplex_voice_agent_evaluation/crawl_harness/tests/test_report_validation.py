"""Invalid imported result records cannot become target-model grades."""

import json

import pytest

from shared.metrics.reporting import build_metric_row
from shared.reporting.results import build_result_item, build_results_report, write_json


@pytest.mark.parametrize("value", ["false", "true", "", 0, 1, 0.0, 1.0, None, [], {}, [False]])
def test_completion_requires_an_actual_boolean_at_both_boundaries(value, tmp_path):
    with pytest.raises(ValueError, match="task_completed"):
        build_result_item({"id": "invalid", "task_completed": value}, run_dir=tmp_path, scenario_id_key="id")
    with pytest.raises(ValueError, match="task_completed"):
        build_metric_row(task={"task_completed": value}, efficiency={}, interaction={}, golden={})


def test_missing_completion_is_not_an_observed_failure(tmp_path):
    with pytest.raises(ValueError, match="task_completed"):
        build_result_item({"id": "unknown"}, run_dir=tmp_path, scenario_id_key="id")
    with pytest.raises(ValueError, match="task_completed"):
        build_metric_row(task={}, efficiency={}, interaction={}, golden={})


@pytest.mark.parametrize("completed", [True, False])
def test_native_completion_booleans_keep_their_meaning(completed, tmp_path):
    item = build_result_item({"id": "known", "task_completed": completed}, run_dir=tmp_path, scenario_id_key="id")
    assert item["status"] == ("passed" if completed else "failed")
    assert item["metrics"]["task"]["task_completed"] is completed


@pytest.mark.parametrize("status", ["infrastructure_error", "error"])
@pytest.mark.parametrize("completed", [True, False])
@pytest.mark.parametrize("details", [{}, {"failure_stage": None, "error_message": None}])
def test_infrastructure_status_is_authoritative_without_failure_details(status, completed, details, tmp_path):
    item = build_result_item(
        {"id": "invalid-run", "status": status, "task_completed": completed, **details},
        run_dir=tmp_path,
        scenario_id_key="id",
    )
    assert item["status"] == "infrastructure_error"
    # Valid diagnostic measurements survive exclusion from target-model grading.
    assert item["metrics"]["task"]["task_completed"] is completed
    assert item["error"] == {"stage": "unknown", "message": ""}


@pytest.mark.parametrize("status", ["passsed", "unknown", None, 1, []])
def test_unknown_status_cannot_silently_turn_into_a_pass(status, tmp_path):
    with pytest.raises(ValueError, match="status"):
        build_result_item(
            {"id": "invalid", "status": status, "task_completed": True}, run_dir=tmp_path, scenario_id_key="id"
        )


def test_invalid_middle_row_keeps_artifacts_and_does_not_abort_saved_report(tmp_path):
    audio = tmp_path / "partial.wav"
    audio.write_bytes(b"partial diagnostic fixture")
    bad = {"id": "bad", "task_completed": "false", "conversation_audio_path": str(audio)}
    report = build_results_report(
        module="run",
        run_name="mixed",
        execution_mode="offline_fixture",
        interaction="multi_turn",
        dataset=tmp_path / "dataset.json",
        configuration={},
        run_dir=tmp_path,
        scenario_id_key="id",
        rows=[
            {"id": "first", "task_completed": True},
            bad,
            {"id": "last", "task_completed": False},
            {"id": "infra", "task_completed": True, "status": "infrastructure_error"},
        ],
    )
    path = write_json(tmp_path / "results.json", report)
    saved = json.loads(path.read_text())
    assert saved["summary"] == {"total": 4, "passed": 1, "failed": 1, "infrastructure_errors": 2}
    assert [item["scenario_id"] for item in saved["results"]] == ["first", "bad", "last", "infra"]
    invalid = saved["results"][1]
    assert invalid["status"] == "infrastructure_error"
    assert invalid["error"]["stage"] == "result_validation"
    assert "task_completed" in invalid["error"]["message"]
    assert invalid["metrics"]["task"]["task_completed"] is False
    assert invalid["artifacts"]["conversation_audio"] == "partial.wav"
    assert bad["task_completed"] == "false", "Projection must not mutate original diagnostic evidence"
