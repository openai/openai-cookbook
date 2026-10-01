"""Current result writers must not resurrect retired caller-controller state."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from run_harness.tests.test_run_visualization import _run_fixture
from run_harness.visualization.export_viewer import build_view_data, export_viewer
from shared.grading.scoring import build_result
from shared.observability.timeline import Timeline
from shared.reporting.compat import normalize_run_configuration, normalize_run_observability
from shared.reporting.schema import SCHEMA_VERSION
from shared.scenarios import Scenario

ROOT = Path(__file__).resolve().parents[2]
RETIRED_FIELDS = {
    "user_backend",
    "user_model",
    "decision_latencies_ms",
    "tts_latencies_ms",
    "tts_first_audio_latencies_ms",
    "user_response_gaps_ms",
    "floor_wait_latencies_ms",
    "tts_input_chars",
    "wait_decisions",
    "stale_actions",
    "stall_recoveries",
    "floor_owner",
    "caller_backend_model",
}


def assert_no_retired_fields(value: object) -> None:
    if isinstance(value, dict):
        assert not RETIRED_FIELDS.intersection(value)
        if isinstance(value.get("observability"), dict):
            assert "floor" not in value["observability"]
        for nested in value.values():
            assert_no_retired_fields(nested)
    elif isinstance(value, list):
        for nested in value:
            assert_no_retired_fields(nested)


def scenario() -> Scenario:
    return Scenario(
        id="schema-test",
        title="Schema",
        interaction="single_turn",
        input={"text": "Hello"},
        expected={"answer": "Hello"},
    )


@pytest.mark.parametrize("mode", ["gpt-live", "offline_fixture", "tts", "recorded_audio"])
def test_current_result_has_no_retired_state(mode: str) -> None:
    interaction = {
        "response_latencies_ms": [120],
        "yield_latencies_ms": [40],
        "floor_hold_silence_ms": {"cumulative": 30, "maximum": 30},
    }
    result = build_result(
        scenario(),
        Timeline(),
        caller_mode=mode,
        caller_model="test-model",
        caller_actions={"OPENING": 1},
        caller_audio_ms=200,
        interaction_metrics=interaction,
        termination_reason="response_completed",
        caller_usage=[{"source": "caller", "input_tokens": 3}],
    ).model_dump()
    assert result["schema_version"] == SCHEMA_VERSION == "2.0"
    assert result["caller_mode"] == mode
    assert result["caller_model"] == "test-model"
    assert result["caller_actions"] == {"OPENING": 1}
    assert result["caller_audio_ms"] == 200
    assert "actions" not in result and "user_audio_ms" not in result
    assert result["response_latencies_ms"] == [120]
    assert result["yield_latencies_ms"] == [40]
    assert result["interaction_metrics"] == interaction
    assert result["usage"] == [{"source": "caller", "input_tokens": 3}]
    assert_no_retired_fields(result)


@pytest.mark.parametrize("mode", ["chained", "realtime", "", None])
def test_result_rejects_retired_caller_modes(mode: object) -> None:
    with pytest.raises(ValueError, match="Unsupported caller mode"):
        build_result(scenario(), Timeline(), caller_mode=mode, termination_reason="response_completed")


@pytest.mark.parametrize(
    "actions", [{"WAIT": 1}, {"STALE_DISCARDED": 1}, {"STALL_RECOVERY": 1}, {"SPEAK": -1}, {"STOP": True}]
)
def test_result_rejects_controller_actions(actions: dict) -> None:
    with pytest.raises(ValueError, match="observed speech behavior"):
        build_result(
            scenario(), Timeline(), caller_mode="gpt-live", caller_actions=actions, termination_reason="user_stopped"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["crawl", "walk", "run"])
@pytest.mark.parametrize("assistant", ["responses", "client"])
async def test_each_harness_writes_schema_two(tmp_path: Path, phase: str, assistant: str) -> None:
    module = importlib.import_module(f"{phase}_harness.evaluate")
    arguments = [
        "--offline",
        "--assistant",
        assistant,
        "--results-dir",
        str(tmp_path),
        "--scenario",
        "restaurant_booking_complete" if phase == "run" else "restaurant_001",
    ]
    if phase == "run":
        arguments.extend(["--no-judge", "--debug-artifacts"])
    elif phase == "walk":
        arguments.append("--no-real-time")
    args = module.parse_args(arguments)
    if phase == "crawl":
        args.audio_cache_dir = tmp_path / "cache"
    run_dir = await module.run_evals(args)
    report = json.loads((run_dir / "results.json").read_text())
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["summary"]["passed"] == 1
    assert_no_retired_fields(report)
    details = json.loads((run_dir / report["results"][0]["artifacts"]["details"]).read_text())
    assert details["schema_version"] == SCHEMA_VERSION
    assert_no_retired_fields(details)
    if phase == "run":
        assert details["caller_mode"] == "offline_fixture"
        assert "floor_hold_silence_ms" in report["results"][0]["metrics"]["audio"]
        for path in run_dir.rglob("*.ticks.jsonl"):
            for line in path.read_text().splitlines():
                tick = json.loads(line)
                assert_no_retired_fields(tick)
                assert all(event.get("type") != "simulator.action" for event in tick["events"])


@pytest.mark.parametrize("backend", ["gpt-live", "offline_fixture"])
def test_historical_dual_live_viewer_discards_controller_state(tmp_path: Path, backend: str) -> None:
    path = _run_fixture(tmp_path)
    report = json.loads(path.read_text())
    report["schema_version"] = "1.6"
    report["run"]["configuration"]["user_backend"] = backend
    report["results"][0]["observability"]["floor"].update(
        {
            "decisions": [{"text": "PRIVATE_RETIRED_DECISION"}],
            "caller_actions": {"OPENING": 1, "WAIT": 2, "STALE_DISCARDED": 1},
            "stall_recoveries": 3,
        }
    )
    path.write_text(json.dumps(report))
    data = build_view_data(path)
    assert data["scenarios"][0]["interaction"]["callerActions"] == {"OPENING": 1}
    assert "floor" not in data["scenarios"][0]
    assert_no_retired_fields(data)
    html = export_viewer(path).read_text()
    for retired in ("PRIVATE_RETIRED_DECISION", "floor-mode", "floor-explanation", "STALE_DISCARDED"):
        assert retired not in html


def test_compatibility_is_confined_to_read_boundary() -> None:
    assert normalize_run_configuration({"user_backend": "gpt-live", "model": "x"}) == {"model": "x"}
    with pytest.raises(ValueError, match="legacy RUN caller"):
        normalize_run_configuration({"user_backend": "chained"})
    current = {"interaction": {"caller_actions": {"SPEAK": 2, "STOP": True, "WAIT": 1}}, "tools": {"executed": []}}
    normalized = normalize_run_observability(current)
    assert normalized["interaction"]["caller_actions"] == {"SPEAK": 2}
    assert normalized["tools"] == current["tools"]
    for package in ("assistants", "crawl_harness", "walk_harness", "run_harness", "shared"):
        for path in (ROOT / package).rglob("*.py"):
            if "tests" in path.parts or path == ROOT / "shared/reporting/compat.py":
                continue
            source = path.read_text()
            for name in RETIRED_FIELDS | {"simulator.action", "simulator.floor.decision"}:
                assert name not in source, f"Retired state {name!r} in {path.relative_to(ROOT)}"
