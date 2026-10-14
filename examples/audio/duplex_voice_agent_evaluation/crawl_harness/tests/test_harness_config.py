"""Configuration contracts shared by three independently runnable phases."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
from dotenv import dotenv_values

from crawl_harness.evaluate import parse_args as parse_crawl_args
from run_harness.evaluate import parse_args as parse_run_args
from shared.audio.effects import AUDIO_CONDITIONS, audio_realism_from_args
from shared.config import load_harness_config
from walk_harness.evaluate import parse_args as parse_walk_args
from walk_harness.generate_audio import parse_args as parse_walk_generator_args


def test_every_distribution_excludes_sensitive_results_and_development_artifacts() -> None:
    project_root = Path(__file__).resolve().parents[2]
    with (project_root / "pyproject.toml").open("rb") as project_file:
        build = tomllib.load(project_file)["tool"]["hatch"]["build"]

    assert {
        "**/results/**",
        "**/tests/**",
        "**/__pycache__/**",
        "**/*.py[cod]",
        "temporary_skills/**",
    }.issubset(build["exclude"])
    assert build["targets"]["wheel"]["packages"] == [
        "assistants",
        "crawl_harness",
        "walk_harness",
        "run_harness",
        "shared",
    ]


def test_result_directories_are_ignored_from_one_root_configuration() -> None:
    project_root = Path(__file__).resolve().parents[2]
    ignored = (project_root / ".gitignore").read_text(encoding="utf-8")

    for phase in ("crawl_harness", "walk_harness", "run_harness"):
        assert f"/{phase}/results/" in ignored
        assert not (project_root / phase / ".gitignore").exists()


def test_project_registers_each_harness_fixture_generator_and_run_viewer() -> None:
    project_root = Path(__file__).resolve().parents[2]
    with (project_root / "pyproject.toml").open("rb") as project_file:
        scripts = tomllib.load(project_file)["project"]["scripts"]

    assert scripts == {
        "crawl-eval": "crawl_harness.evaluate:main",
        "walk-eval": "walk_harness.evaluate:main",
        "walk-generate-audio": "walk_harness.generate_audio:main",
        "run-eval": "run_harness.evaluate:main",
        "run-view": "run_harness.visualization.export_viewer:main",
        "client-assistant": "assistants.client.service:main",
    }
    assert all(
        (project_root / phase / "evaluate.py").is_file() for phase in ("crawl_harness", "walk_harness", "run_harness")
    )


@pytest.mark.parametrize(
    ("parse_args", "phase"),
    [
        (parse_crawl_args, "crawl_harness"),
        (parse_walk_args, "walk_harness"),
        (parse_run_args, "run_harness"),
    ],
)
def test_each_phase_loads_its_own_restaurant_configuration(
    parse_args: object,
    phase: str,
) -> None:
    assert callable(parse_args)
    args = parse_args([])

    assert args.config.name == "config.toml"
    assert args.config.parent.name == phase
    assert args.data.name == "scenarios.json"
    assert not hasattr(args, "application_profile")
    assert args.concurrency == 1
    assert args.verbose is False


@pytest.mark.parametrize("parse_args", [parse_crawl_args, parse_walk_args, parse_run_args])
def test_cli_flags_override_module_configuration(parse_args: object) -> None:
    assert callable(parse_args)

    assert parse_args(["--concurrency", "3"]).concurrency == 3
    assert parse_args(["--verbose"]).verbose is True


@pytest.mark.parametrize("parse_args", [parse_crawl_args, parse_walk_args, parse_run_args])
def test_assistant_environment_settings_override_module_defaults(
    parse_args: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert callable(parse_args)
    monkeypatch.setenv("OPENAI_ASSISTANT_MODE", "client")
    monkeypatch.setenv("OPENAI_CLIENT_ASSISTANT_ENDPOINT", "wss://assistant.example.test/ws")

    args = parse_args([])

    assert args.assistant == "client"
    assert args.assistant_endpoint == "wss://assistant.example.test/ws"
    assert parse_args(["--assistant", "responses"]).assistant == "responses"


def test_run_ignores_removed_caller_backend_environment_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_USER_BACKEND", "chained")

    assert not hasattr(parse_run_args([]), "user_backend")
    with pytest.raises(SystemExit):
        parse_run_args(["--user-backend", "realtime"])


def test_example_environment_documents_assistant_caller_and_judge_settings() -> None:
    project_root = Path(__file__).resolve().parents[2]
    template_path = project_root / ".env.example"
    values = dotenv_values(template_path)
    template = template_path.read_text(encoding="utf-8")

    assert values["OPENAI_ASSISTANT_MODE"] == "responses"
    assert values["OPENAI_COMPLETION_MODEL"] == "gpt-5.6-terra"
    assert values["OPENAI_LIVE_BACKEND_MODEL"] == "gpt-5.6-terra"
    assert values["OPENAI_TTS_MODEL"] == "gpt-4o-mini-tts"
    assert values["OPENAI_EVAL_JUDGE_MODEL"] == "gpt-5.6-terra"
    assert "# OPENAI_ASSISTANT_MODE=client" in template
    assert "OPENAI_USER_BACKEND" not in template
    assert "OPENAI_REALTIME_USER_MODEL" not in template
    assert "OPENAI_USER_MODEL" not in template
    assert "OPENAI_USER_REASONING_EFFORT" not in template
    assert "# OPENAI_CLIENT_ASSISTANT_ENDPOINT=wss://agent.example.com/ws/assistant" in template
    assert "OPENAI_LIVE_APPLICATION_PROFILE" not in template


@pytest.mark.parametrize(
    ("parse_args", "attribute"),
    [(parse_crawl_args, "example"), (parse_walk_args, "example"), (parse_run_args, "scenario")],
)
@pytest.mark.parametrize("option", ["--example", "--scenario"])
def test_every_phase_accepts_the_same_scenario_selector(
    parse_args: object,
    attribute: str,
    option: str,
) -> None:
    assert callable(parse_args)

    assert getattr(parse_args([option, "selected_scenario"]), attribute) == "selected_scenario"


def test_walk_fixture_generation_and_run_share_the_same_audio_realism_options() -> None:
    options = [
        "--condition",
        "realistic",
        "--noise-rms",
        "75",
        "--background-gain",
        "0.2",
        "--echo-delay-ms",
        "90",
        "--echo-decay",
        "0.3",
        "--packet-loss-rate",
        "0.05",
        "--packet-loss-burst",
        "2",
        "--cough-every-ms",
        "1800",
        "--non-directed-every-ms",
        "3000",
    ]
    generated = parse_walk_generator_args(options)
    simulated = parse_run_args(options)

    assert generated.condition == simulated.condition == "realistic"
    assert audio_realism_from_args(generated) == audio_realism_from_args(simulated)
    assert AUDIO_CONDITIONS == (
        "clean",
        "noisy",
        "telephony",
        "background_speech",
        "echo",
        "packet_loss",
        "realistic",
    )


@pytest.mark.parametrize("parse_args", [parse_crawl_args, parse_walk_args, parse_run_args])
def test_every_phase_uses_shared_judge_environment_settings(
    parse_args: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert callable(parse_args)
    monkeypatch.setenv("OPENAI_EVAL_JUDGE_MODEL", "shared-judge-model")
    monkeypatch.setenv("OPENAI_EVAL_JUDGE_REASONING_EFFORT", "high")

    args = parse_args([])

    assert args.judge_model == "shared-judge-model"
    assert args.judge_reasoning_effort == "high"


def test_synthetic_caller_phases_use_shared_tts_environment_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_TTS_MODEL", "shared-tts-model")

    assert parse_crawl_args([]).tts_model == "shared-tts-model"
    assert parse_walk_generator_args([]).model == "shared-tts-model"


@pytest.mark.parametrize("parse_args", [parse_crawl_args, parse_walk_args, parse_run_args])
def test_verbose_logging_can_be_enabled_in_module_configuration(parse_args: object, tmp_path: Path) -> None:
    assert callable(parse_args)
    config_path = tmp_path / "verbose.toml"
    config_path.write_text("[execution]\nverbose = true\n", encoding="utf-8")

    assert parse_args(["--config", str(config_path)]).verbose is True


def test_custom_module_configuration_resolves_dataset_relative_to_itself(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        '[dataset]\npath = "fixtures/custom.json"\n\n[execution]\nconcurrency = 2\n',
        encoding="utf-8",
    )

    args = parse_crawl_args(["--config", str(config_path)])

    assert args.config == config_path.resolve()
    assert args.data == tmp_path / "fixtures" / "custom.json"
    assert args.concurrency == 2


def test_run_configuration_owns_continuous_simulation_policy() -> None:
    args = parse_run_args([])

    assert args.tick_ms == 200
    assert args.max_duration_seconds == 90.0
    assert args.semantic_drain is True
    assert args.completion_model == "gpt-5.6-terra"
    assert args.simulator_backend_model == "gpt-5.6-luna"
    assert args.simulator_backend_reasoning_effort == "low"
    assert args.condition == "clean"
    assert args.seed == 7
    assert args.judge is True


def test_missing_module_configuration_fails_clearly(tmp_path: Path) -> None:
    path = tmp_path / "missing.toml"

    with pytest.raises(ValueError, match="Harness configuration does not exist"):
        load_harness_config(["--config", str(path)], path)


def test_invalid_module_configuration_fails_clearly(tmp_path: Path) -> None:
    path = tmp_path / "invalid.toml"
    path.write_text("[audio\nchunk_ms = 20\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid harness configuration"):
        load_harness_config(["--config", str(path)], path)


def test_module_configuration_rejects_incorrect_setting_types(tmp_path: Path) -> None:
    path = tmp_path / "invalid-types.toml"
    path.write_text('[execution]\nconcurrency = "four"\n', encoding="utf-8")

    with pytest.raises(ValueError, match="execution.concurrency must be an integer"):
        parse_walk_args(["--config", str(path)])
