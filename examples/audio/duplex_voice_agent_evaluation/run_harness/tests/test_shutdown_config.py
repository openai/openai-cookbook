"""Shutdown budgets survive configuration boundaries and fail before side effects."""

import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from assistants.runtime import ToolExecutor
from run_harness.evaluate import DEFAULT_DATA_JSON, _settings, load_run_scenarios, parse_args, run_evals
from run_harness.simulation.gpt_live_participants import SimulatorControlTools, VoiceParticipant
from run_harness.simulation.gpt_live_runner import DualGptLiveRunner
from run_harness.simulation.models import Settings
from shared.scenarios import Scenario

BUDGET_FIELDS = ("work_grace_seconds", "cleanup_timeout_seconds")
INVALID_BUDGETS = [
    pytest.param(0.0, id="zero"),
    pytest.param(-0.25, id="negative"),
    pytest.param(float("nan"), id="nan"),
    pytest.param(float("inf"), id="positive-infinity"),
    pytest.param(float("-inf"), id="negative-infinity"),
    pytest.param(True, id="true"),
    pytest.param(False, id="false"),
]


@pytest.fixture
def scenario() -> Scenario:
    return load_run_scenarios(DEFAULT_DATA_JSON, scenario_id="restaurant_booking_complete")[0]


def _runner(scenario: Scenario, executor: Mock, output: Path, **budgets: float) -> DualGptLiveRunner:
    return DualGptLiveRunner(
        scenario,
        caller=Mock(spec=VoiceParticipant),
        assistant=Mock(spec=VoiceParticipant),
        caller_tools=SimulatorControlTools(),
        application_tools=executor,
        save_conversations=output,
        event_log_path=output / "events.jsonl",
        offline=True,
        **budgets,
    )


@pytest.mark.parametrize(
    ("toml", "cli", "expected"),
    [
        ("", [], (5.0, 10.0)),
        (
            "[simulation]\nwork_grace_seconds = 2\ncleanup_timeout_seconds = 7.5\n",
            [],
            (2.0, 7.5),
        ),
        (
            "[simulation]\nwork_grace_seconds = 2\ncleanup_timeout_seconds = 7.5\n",
            ["--work-grace-seconds", "0.75"],
            (0.75, 7.5),
        ),
        (
            "[simulation]\nwork_grace_seconds = 2\ncleanup_timeout_seconds = 7.5\n",
            ["--work-grace-seconds", "0.75", "--cleanup-timeout-seconds", "1.25"],
            (0.75, 1.25),
        ),
    ],
    ids=["defaults", "toml", "one-cli-override", "both-cli-overrides"],
)
def test_shutdown_budgets_keep_independent_values_through_settings_and_runner(
    tmp_path: Path, scenario: Scenario, toml: str, cli: list[str], expected: tuple[float, float]
) -> None:
    config = tmp_path / "config.toml"
    config.write_text(toml, encoding="utf-8")
    output = tmp_path / "results"
    args = parse_args(["--config", str(config), "--offline", "--results-dir", str(output), *cli])
    settings = _settings(args, scenario, output)
    selected = {name: getattr(settings, name) for name in BUDGET_FIELDS}
    executor = Mock(spec=ToolExecutor)
    executor.snapshot.return_value = {}

    runner = _runner(scenario, executor, output, **selected)

    assert tuple(getattr(args, name) for name in BUDGET_FIELDS) == expected
    assert tuple(getattr(settings, name) for name in BUDGET_FIELDS) == expected
    assert tuple(getattr(runner, name) for name in BUDGET_FIELDS) == expected
    assert not output.exists()


@pytest.mark.parametrize("field", BUDGET_FIELDS)
@pytest.mark.parametrize("value", INVALID_BUDGETS)
@pytest.mark.parametrize("source", ["cli", "toml"])
async def test_invalid_shutdown_budget_is_rejected_before_run_artifacts(
    tmp_path: Path, field: str, value: float | bool, source: str
) -> None:
    output = tmp_path / "must-not-exist"
    argv = ["--offline", "--no-judge", "--results-dir", str(output)]
    encoded = str(value).lower()
    if source == "toml":
        config = tmp_path / "config.toml"
        config.write_text(f"[simulation]\n{field} = {encoded}\n", encoding="utf-8")
        argv += ["--config", str(config)]
    else:
        argv += [f"--{field.replace('_', '-')}={encoded}"]

    if source == "cli" and isinstance(value, bool):
        with pytest.raises(SystemExit) as rejected:
            parse_args(argv)
        assert rejected.value.code == 2
    elif isinstance(value, bool):
        with pytest.raises(ValueError, match=f"simulation.{field} must be a number"):
            parse_args(argv)
    else:
        args = parse_args(argv)
        with pytest.raises(ValueError, match=f"{field.replace('_', '-')} must be finite and positive"):
            await run_evals(args)

    assert not output.exists()


@pytest.mark.parametrize("field", BUDGET_FIELDS)
@pytest.mark.parametrize("value", INVALID_BUDGETS)
def test_settings_reject_invalid_shutdown_budget_without_boolean_coercion(field: str, value: float | bool) -> None:
    with pytest.raises(ValidationError) as rejected:
        Settings(**{field: value})

    assert any(error["loc"] == (field,) for error in rejected.value.errors())


@pytest.mark.parametrize("field", BUDGET_FIELDS)
@pytest.mark.parametrize("value", INVALID_BUDGETS)
def test_direct_runner_rejects_invalid_budget_before_touching_application_state(
    tmp_path: Path, scenario: Scenario, field: str, value: float | bool
) -> None:
    output = tmp_path / "must-not-exist"
    executor = Mock(spec=ToolExecutor)
    executor.snapshot.side_effect = AssertionError("Invalid configuration must not inspect application state")

    with pytest.raises(ValueError, match=f"{field} must be finite and positive"):
        _runner(scenario, executor, output, **{field: value})

    executor.snapshot.assert_not_called()
    assert not output.exists()


async def test_effective_shutdown_budgets_survive_offline_run_and_saved_results(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text("[simulation]\nwork_grace_seconds = 2.0\ncleanup_timeout_seconds = 1.25\n", encoding="utf-8")
    args = parse_args(
        [
            "--config",
            str(config),
            "--offline",
            "--no-judge",
            "--scenario",
            "restaurant_booking_complete",
            "--results-dir",
            str(tmp_path / "results"),
            "--work-grace-seconds",
            "0.75",
        ]
    )

    run_dir = await run_evals(args)

    report = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    result = report["results"][0]
    detail = json.loads((run_dir / result["artifacts"]["details"]).read_text(encoding="utf-8"))
    for name, expected in (("work_grace_seconds", 0.75), ("cleanup_timeout_seconds", 1.25)):
        assert report["run"]["configuration"][name] == expected
        assert detail["run_metadata"][name] == expected
    assert report["summary"]["infrastructure_errors"] == 0
    assert result["status"] == "passed"
