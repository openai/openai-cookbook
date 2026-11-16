import asyncio
import json
import subprocess
import sys
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest

from assistants.config import render_authorized_context
from assistants.resources import assistant_resources
from run_harness.evaluate import (
    DEFAULT_BACKEND_PROMPT_PATH,
    DEFAULT_DATA_JSON,
    DEFAULT_SYSTEM_PROMPT_PATH,
    _settings,
    _token_counts,
    _validate_distinct_gpt_live_voices,
    load_run_scenarios,
    parse_args,
    run_evals,
)
from run_harness.simulation.gpt_live_participants import OfflineRestaurantParticipant
from shared.reporting.results import build_results_report
from shared.scenarios import ConversationContext


def test_run_dataset_contains_only_independent_multi_turn_personas() -> None:
    scenarios = load_run_scenarios(DEFAULT_DATA_JSON)

    assert [scenario.id for scenario in scenarios] == [
        "restaurant_booking_complete",
        "restaurant_booking_missing_name",
        "restaurant_booking_missing_time",
        "restaurant_date_correction",
        "restaurant_party_correction",
        "restaurant_unavailable",
        "restaurant_cancel_authorized",
        "restaurant_cancel_unauthorized",
        "restaurant_multiple_corrections",
        "restaurant_interrupted_alternative",
        "restaurant_cancel_corrected_authorization",
    ]
    assert all(scenario.interaction_mode == "multi_turn" for scenario in scenarios)
    assert all(scenario.simulation_parameters is not None for scenario in scenarios)
    assert all(scenario.expected.golden_path.turns >= 7 for scenario in scenarios)
    assert all(scenario.simulation_parameters.known_facts for scenario in scenarios)
    assert all(
        sum(item.action not in {"finish", "wait"} for item in scenario.simulation_parameters.agenda) >= 2
        for scenario in scenarios
    )
    assert all(scenario.persona.voice.casefold() != "marin" for scenario in scenarios)


def test_run_rejects_live_voice_collisions_from_personas_and_overrides() -> None:
    scenarios = load_run_scenarios(DEFAULT_DATA_JSON, max_examples=2)

    with pytest.raises(ValueError, match=scenarios[0].id):
        _validate_distinct_gpt_live_voices(
            scenarios,
            agent_voice=scenarios[0].persona.voice,
            simulator_voice="",
        )
    with pytest.raises(ValueError, match="collides for"):
        _validate_distinct_gpt_live_voices(
            scenarios,
            agent_voice="marin",
            simulator_voice="MARIN",
        )

    _validate_distinct_gpt_live_voices(
        scenarios,
        agent_voice="marin",
        simulator_voice="cedar",
    )


def test_run_scenarios_can_be_selected_and_limited() -> None:
    assert [item.id for item in load_run_scenarios(DEFAULT_DATA_JSON, scenario_id="restaurant_date_correction")] == [
        "restaurant_date_correction"
    ]
    assert len(load_run_scenarios(DEFAULT_DATA_JSON, max_examples=2)) == 2


def test_run_rejects_unknown_scenario_and_negative_example_limit() -> None:
    with pytest.raises(ValueError, match="Unknown multi-turn scenario"):
        load_run_scenarios(DEFAULT_DATA_JSON, scenario_id="missing")
    with pytest.raises(ValueError, match="zero or greater"):
        load_run_scenarios(DEFAULT_DATA_JSON, max_examples=-1)


def test_run_defaults_to_gpt_live_caller_and_continuous_200ms_tick() -> None:
    args = parse_args([])

    assert args.tick_ms == 200
    assert args.judge is True
    assert args.concurrency == 1


@pytest.mark.asyncio
async def test_response_deadline_cli_controls_scoring_and_survives_saved_reports(tmp_path: Path) -> None:
    args = parse_args(
        [
            "--offline",
            "--no-judge",
            "--scenario",
            "restaurant_booking_complete",
            "--results-dir",
            str(tmp_path),
            "--response-deadline-ms",
            "1",
        ]
    )
    run_dir = await run_evals(args)
    report = json.loads((run_dir / "results.json").read_text())
    result = report["results"][0]
    detail = json.loads((run_dir / result["artifacts"]["details"]).read_text())
    metrics = detail["interaction_metrics"]
    # Every fixture response waits longer than 1 ms. This checks the policy's
    # effect, not just argument parsing or metadata copying.
    assert metrics["counts"]["response_count"] == 0
    assert metrics["counts"]["no_response_count"] > 0
    assert metrics["counts"]["response_late_count"] > 0
    assert report["run"]["configuration"]["response_deadline_ms"] == 1
    assert result["metrics"]["audio"]["response_deadline_ms"] == 1
    assert result["metrics"]["audio"]["metrics_version"] == metrics["metrics_version"]
    assert (
        result["metrics"]["audio"]["response_opportunities"]["no_response_count"]
        == metrics["counts"]["no_response_count"]
    )
    assert detail["run_metadata"]["response_deadline_ms"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("deadline", [0, -1])
async def test_run_rejects_nonpositive_response_deadline_before_writing_artifacts(
    tmp_path: Path, deadline: int
) -> None:
    args = parse_args(["--offline", "--no-judge", "--results-dir", str(tmp_path)])
    args.response_deadline_ms = deadline
    with pytest.raises(ValueError, match="response-deadline-ms must be positive"):
        await run_evals(args)
    assert not await asyncio.to_thread(lambda: list(tmp_path.iterdir()))


def test_visualize_automatically_enables_detailed_conversation_artifacts() -> None:
    args = parse_args(["--visualize"])

    assert args.visualize is True
    assert args.debug_artifacts is True


def test_default_runs_do_not_enable_visualization_or_debug_artifacts() -> None:
    args = parse_args([])

    assert args.visualize is False
    assert args.debug_artifacts is False


def test_importing_run_evaluator_without_visualization_does_not_require_viewer() -> None:
    project_root = Path(__file__).resolve().parents[2]
    probe = """
import builtins

original_import = builtins.__import__

def deny_visualization(name, globals=None, locals=None, fromlist=(), level=0):
    if name == "run_harness.visualization" or name.startswith("run_harness.visualization."):
        raise ImportError("optional visualization is unavailable")
    return original_import(name, globals, locals, fromlist, level)

builtins.__import__ = deny_visualization
import run_harness.evaluate
"""

    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_run_accepts_an_explicit_gpt_live_caller_model() -> None:
    args = parse_args(["--simulator-model", "caller-live-model"])

    assert args.simulator_model == "caller-live-model"
    assert args.drain_ms == 1_500


@pytest.mark.parametrize(
    "flag",
    ["--user-backend", "--user-model", "--realtime-user-model", "--tts-model"],
)
def test_run_rejects_removed_caller_flags(flag: str) -> None:
    with pytest.raises(SystemExit):
        parse_args([flag, "legacy"])


def test_run_accepts_deterministic_audio_realism_overrides(tmp_path: Path) -> None:
    scenario = load_run_scenarios(DEFAULT_DATA_JSON, max_examples=1)[0]
    args = parse_args(
        [
            "--offline",
            "--condition",
            "realistic",
            "--noise-rms",
            "75",
            "--echo-delay-ms",
            "90",
            "--packet-loss-rate",
            "0.05",
        ]
    )

    settings = _settings(args, scenario, tmp_path)

    assert settings.condition == "realistic"
    assert settings.audio_realism.noise_rms == 75
    assert settings.audio_realism.echo_delay_ms == 90
    assert settings.audio_realism.packet_loss_rate == 0.05


@pytest.mark.parametrize(
    ("caller_config", "caller_model", "caller_effort"),
    [
        ("", "gpt-5.6-luna", "low"),
        (
            '[simulation]\nsimulator_backend_model = "caller-responses-model"\n'
            'simulator_backend_reasoning_effort = "low"\n',
            "caller-responses-model",
            "low",
        ),
    ],
)
def test_run_reads_assistant_environment_and_independent_caller_configuration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caller_config: str,
    caller_model: str,
    caller_effort: str,
) -> None:
    monkeypatch.setenv("OPENAI_LIVE_MODEL", "env-live-model")
    monkeypatch.setenv("OPENAI_LIVE_VOICE", "env-voice")
    monkeypatch.setenv("OPENAI_LIVE_ENDPOINT", "https://live.example.test/v1/live")
    monkeypatch.setenv("OPENAI_LIVE_BACKEND_MODEL", "env-backend-model")
    monkeypatch.setenv("OPENAI_LIVE_BACKEND_REASONING_EFFORT", "high")
    config_path = tmp_path / "config.toml"
    config_path.write_text(caller_config, encoding="utf-8")

    args = parse_args(["--config", str(config_path)])

    assert args.model == "env-live-model"
    assert args.voice == "env-voice"
    assert args.endpoint == "https://live.example.test/v1/live"
    assert args.backend_model == "env-backend-model"
    assert not hasattr(args, "application_profile")
    assert not hasattr(args, "system_prompt_file")

    scenario = load_run_scenarios(DEFAULT_DATA_JSON, max_examples=1)[0]
    settings = _settings(args, scenario, tmp_path)
    assert settings.backend_model == "env-backend-model"
    assert settings.simulator_backend_model == caller_model
    assert settings.simulator_backend_reasoning_effort == caller_effort


def test_run_loads_shared_restaurant_prompts_and_only_authorized_application_context(tmp_path: Path) -> None:
    resources = assistant_resources()
    scenario = next(item for item in load_run_scenarios(DEFAULT_DATA_JSON) if item.id == "restaurant_cancel_authorized")
    args = parse_args(["--offline", "--results-dir", str(tmp_path)])
    facts = resources.load_facts()
    tools = json.loads(resources.tools_file.read_text(encoding="utf-8"))

    settings = _settings(args, scenario, tmp_path, resources=resources, tools=tools, facts=facts)

    assert resources.system_prompt_file == DEFAULT_SYSTEM_PROMPT_PATH
    assert resources.backend_system_prompt_file == DEFAULT_BACKEND_PROMPT_PATH
    assert settings.agent_instructions == render_authorized_context(
        resources.system_prompt_file.read_text(encoding="utf-8").strip(),
        facts=facts,
        initial_state=scenario.application.initial_state,
    )
    assert settings.backend_instructions == render_authorized_context(
        resources.backend_system_prompt_file.read_text(encoding="utf-8").strip(),
        facts=facts,
        initial_state=scenario.application.initial_state,
    )
    assert "authorized_application_state" in settings.agent_instructions
    assert "availability_overrides" not in settings.agent_instructions
    assert "availability_overrides" not in settings.backend_instructions
    assert scenario.expected.answer not in settings.agent_instructions
    assert scenario.expected.answer not in settings.backend_instructions
    assert scenario.expected.procedure is not None
    assert scenario.expected.procedure.id not in settings.agent_instructions


def test_run_hydrates_authorized_prior_context_without_leaking_evaluator_data(tmp_path: Path) -> None:
    resources = assistant_resources()
    scenario = load_run_scenarios(DEFAULT_DATA_JSON, max_examples=1)[0].model_copy(deep=True)
    scenario.input.context = ConversationContext(summary="The caller previously requested a patio table under Maya.")
    args = parse_args(["--offline", "--results-dir", str(tmp_path)])
    facts = resources.load_facts()
    tools = json.loads(resources.tools_file.read_text(encoding="utf-8"))

    settings = _settings(args, scenario, tmp_path, resources=resources, tools=tools, facts=facts)

    assert scenario.conversation_context in settings.agent_instructions
    assert scenario.conversation_context in settings.backend_instructions
    assert scenario.expected.answer not in settings.agent_instructions
    assert scenario.simulation_goal not in settings.agent_instructions


def test_token_usage_reports_only_evaluated_frontend_and_backend() -> None:
    result = SimpleNamespace(
        usage=[
            {
                "source": "live_frontend",
                "total_tokens": 20,
                "input_tokens": 12,
                "output_tokens": 8,
                "input_token_details": {
                    "audio_tokens": 8,
                    "text_tokens": 4,
                    "cached_tokens": 2,
                    "cache_write_tokens": 3,
                },
                "output_token_details": {"audio_tokens": 5, "text_tokens": 3},
            },
            {
                "source": "delegated_response",
                "total_tokens": 20,
                "input_tokens": 13,
                "output_tokens": 7,
                "input_tokens_details": {"cache_write_tokens": 9, "cached_tokens": 2},
                "output_tokens_details": {"reasoning_tokens": 3},
            },
            {"source": "user_model", "input_tokens": 11, "output_tokens": 3},
            {"source": "caller_gpt_live", "input_tokens": 99, "output_tokens": 66},
            {"source": "semantic_completion", "input_tokens": 55, "output_tokens": 44},
            {"source": "eval_judge", "input_tokens": 33, "output_tokens": 22},
        ],
        rubric_metrics={"usage": [{"source": "eval_judge", "input_tokens": 17, "output_tokens": 4}]},
    )

    assert _token_counts(result) == {
        "frontend_total_tokens": 20,
        "frontend_input_tokens": 12,
        "frontend_cached_input_tokens": 2,
        "frontend_cache_write_input_tokens": 3,
        "frontend_input_audio_tokens": 8,
        "frontend_input_text_tokens": 4,
        "frontend_output_tokens": 8,
        "frontend_output_audio_tokens": 5,
        "frontend_output_text_tokens": 3,
        "backend_total_tokens": 20,
        "backend_input_tokens": 13,
        "backend_cached_input_tokens": 2,
        "backend_cache_write_input_tokens": 9,
        "backend_input_text_tokens": 13,
        "backend_output_tokens": 7,
        "backend_output_text_tokens": 7,
        "backend_output_reasoning_tokens": 3,
    }


def test_token_usage_uses_latest_session_snapshot_and_does_not_double_count_backend_usage() -> None:
    result = SimpleNamespace(
        usage=[
            {"source": "delegated_response", "total_tokens": 120, "input_tokens": 100, "output_tokens": 20},
            {
                "source": "live_frontend",
                "audio_duration_ms": 800,
                "backend_model_usage": [
                    {"model": "gpt-5.6-terra", "total_tokens": 60, "input_tokens": 50, "output_tokens": 10}
                ],
            },
            {
                "source": "live_frontend",
                "audio_duration_ms": 1600,
                "backend_model_usage": [
                    {"model": "gpt-5.6-terra", "total_tokens": 120, "input_tokens": 100, "output_tokens": 20}
                ],
            },
            {"source": "user_model", "total_tokens": 900, "input_tokens": 800, "output_tokens": 100},
        ]
    )

    assert _token_counts(result) == {
        "frontend_audio_duration_ms": 1600,
        "backend_total_tokens": 120,
        "backend_input_tokens": 100,
        "backend_input_text_tokens": 100,
        "backend_output_tokens": 20,
        "backend_output_text_tokens": 20,
        "backend_model_usage": [
            {"model": "gpt-5.6-terra", "total_tokens": 120, "input_tokens": 100, "output_tokens": 20}
        ],
    }


def test_summary_excludes_infrastructure_failures_from_model_grades(tmp_path: Path) -> None:
    dataset = tmp_path / "scenarios.json"
    dataset.write_text("{}", encoding="utf-8")
    rows = [
        {
            "scenario_id": "pass",
            "status": "passed",
            "task_completed": True,
            "response_latency_ms": 400,
            "response_rate": 1.0,
        },
        {
            "scenario_id": "error",
            "status": "infrastructure_error",
            "task_completed": False,
            "response_latency_ms": None,
            "failure_stage": "transport",
            "error_message": "unavailable",
        },
    ]

    summary = build_results_report(
        module="run",
        run_name="run_offline_test",
        execution_mode="offline_fixture",
        interaction="multi_turn",
        dataset=dataset,
        configuration={},
        rows=rows,
        run_dir=tmp_path,
        scenario_id_key="scenario_id",
    )["summary"]

    assert summary == {
        "total": 2,
        "passed": 1,
        "failed": 0,
        "infrastructure_errors": 1,
    }


@pytest.mark.asyncio
async def test_programmatic_run_arguments_predating_visualization_remain_compatible(tmp_path: Path) -> None:
    args = parse_args(
        [
            "--offline",
            "--no-judge",
            "--scenario",
            "restaurant_booking_complete",
            "--results-dir",
            str(tmp_path),
        ]
    )
    del args.visualize

    run_dir = await run_evals(args)
    report = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))

    assert report["results"][0]["status"] == "passed"
    assert not (run_dir / "viewer.html").exists()


@pytest.mark.asyncio
async def test_live_run_requires_a_key_before_creating_artifacts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")
    args = parse_args(["--results-dir", str(tmp_path)])

    with pytest.raises(ValueError, match="OPENAI_API_KEY is required"):
        await run_evals(args)

    assert not await asyncio.to_thread(lambda: any(tmp_path.iterdir()))


@pytest.mark.asyncio
async def test_run_rejects_parallel_live_listening_before_creating_artifacts(tmp_path: Path) -> None:
    args = parse_args(["--offline", "--concurrency", "2", "--listen", "--results-dir", str(tmp_path)])

    with pytest.raises(ValueError, match="--listen requires --concurrency 1"):
        await run_evals(args)

    assert not await asyncio.to_thread(lambda: any(tmp_path.iterdir()))


@pytest.mark.asyncio
async def test_run_classifies_gpt_live_provider_errors_as_infrastructure_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    async def provider_error(self: OfflineRestaurantParticipant):
        del self
        yield {
            "type": "error",
            "error": {
                "code": "inference_service_unavailable_error",
                "message": "The server is overloaded or not ready yet.",
            },
        }

    monkeypatch.setattr(OfflineRestaurantParticipant, "incoming", provider_error)
    args = parse_args(
        [
            "--offline",
            "--scenario",
            "restaurant_date_correction",
            "--results-dir",
            str(tmp_path),
        ]
    )

    run_dir = await run_evals(args)
    report = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))

    assert report["summary"] == {
        "total": 1,
        "passed": 0,
        "failed": 0,
        "infrastructure_errors": 1,
    }
    assert report["results"][0]["status"] == "infrastructure_error"
    assert report["results"][0]["error"] == {
        "stage": "assistant_connection",
        "message": "assistant GPT Live returned an error: The server is overloaded or not ready yet.",
    }


@pytest.mark.asyncio
async def test_visualization_never_turns_an_infrastructure_failure_into_an_evaluator_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def provider_error(self: OfflineRestaurantParticipant):
        del self
        yield {
            "type": "error",
            "error": {"code": "inference_service_unavailable_error", "message": "Provider unavailable."},
        }

    monkeypatch.setattr(OfflineRestaurantParticipant, "incoming", provider_error)
    args = parse_args(
        [
            "--offline",
            "--no-judge",
            "--scenario",
            "restaurant_date_correction",
            "--results-dir",
            str(tmp_path),
            "--visualize",
        ]
    )

    run_dir = await run_evals(args)
    report = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))

    assert report["summary"]["infrastructure_errors"] == 1
    assert report["results"][0]["status"] == "infrastructure_error"
    assert not (run_dir / "viewer.html").exists()
    assert "Viewer unavailable: No visualizable RUN conversations" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_visualization_export_failure_preserves_the_completed_evaluation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def unavailable_export(results_path: Path) -> Path:
        del results_path
        raise OSError("viewer storage unavailable")

    monkeypatch.setattr("run_harness.visualization.export_viewer.export_viewer", unavailable_export)
    args = parse_args(
        [
            "--offline",
            "--no-judge",
            "--scenario",
            "restaurant_booking_complete",
            "--results-dir",
            str(tmp_path),
            "--visualize",
        ]
    )

    run_dir = await run_evals(args)
    report = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))

    assert report["results"][0]["status"] == "passed"
    assert not (run_dir / "viewer.html").exists()
    assert "Viewer unavailable: viewer storage unavailable" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_visualize_generates_a_self_contained_gpt_live_viewer(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    args = parse_args(
        [
            "--offline",
            "--no-judge",
            "--scenario",
            "restaurant_booking_complete",
            "--max-duration-seconds",
            "30",
            "--results-dir",
            str(tmp_path),
            "--visualize",
        ]
    )

    run_dir = await run_evals(args)
    audio = run_dir / "audio" / "restaurant_booking_complete" / "conversation.wav"
    html = (run_dir / "viewer.html").read_text(encoding="utf-8")

    assert audio.with_suffix(".ticks.jsonl").is_file()
    assert audio.with_suffix(".turns.jsonl").is_file()
    assert "data:audio/wav;base64," in html
    assert "restaurant_booking_complete" in html
    assert f"Viewer: {run_dir / 'viewer.html'}" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_offline_run_writes_cookbook_artifacts_and_sanitized_duplex_traces(tmp_path: Path) -> None:
    args = parse_args(
        [
            "--offline",
            "--scenario",
            "restaurant_date_correction",
            "--results-dir",
            str(tmp_path),
            "--run-name",
            "portable-run",
            "--tick-ms",
            "100",
            "--max-duration-seconds",
            "20",
            "--debug-artifacts",
        ]
    )

    run_dir = await run_evals(args)

    assert run_dir.parent == tmp_path
    assert run_dir.name.startswith("portable-run_")
    report = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    rows = report["results"]
    assert [row["scenario_id"] for row in rows] == ["restaurant_date_correction"]
    assert all(row["status"] == "passed" for row in rows)
    assert report["run"]["module"] == "run"
    assert report["run"]["execution_mode"] == "offline_fixture"
    assert report["run"]["configuration"]["simulator_backend_model"] is None
    assert report["run"]["configuration"]["simulator_backend_reasoning_effort"] is None
    assert report["summary"] == {
        "total": 1,
        "passed": 1,
        "failed": 0,
        "infrastructure_errors": 0,
    }

    for row in rows:
        scenario_id = row["scenario_id"]
        audio_path = run_dir / "audio" / scenario_id / "conversation.wav"
        transcript_path = audio_path.with_suffix(".transcript.txt")
        result_path = audio_path.with_suffix(".result.json")
        trace_path = run_dir / "events" / f"{scenario_id}.jsonl"
        scenario_result_path = run_dir / "transcripts" / f"{scenario_id}.json"

        assert audio_path.is_file()
        assert transcript_path.is_file()
        assert result_path.is_file()
        assert scenario_result_path.is_file()
        assert audio_path.with_suffix(".ticks.jsonl").is_file()
        assert audio_path.with_suffix(".turns.jsonl").is_file()
        with wave.open(str(audio_path), "rb") as audio:
            assert audio.getnchannels() == 2
            assert audio.getframerate() == 24_000
            assert audio.getnframes() > 0

        events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
        assert any(event["type"] == "session.output_audio.delta" for event in events)
        assert any(event["type"] == "dual_gpt_live.tick" for event in events)
        assert any(
            event["type"] == "evaluation.turn.projected" and event["event"]["role"] == "user" for event in events
        )
        assert not any(event["type"] == "simulator.floor.decision" for event in events)
        assert any(event["type"] == "evaluation.procedure.assessed" for event in events)
        assert any(event["type"] == "evaluation.outcome.assessed" for event in events)
        assert [event["event_index"] for event in events] == list(range(1, len(events) + 1))
        assert all(
            not isinstance(event.get("event", {}).get("audio"), str)
            or event["event"]["audio"].startswith("[base64 PCM;")
            for event in events
        )

        saved = json.loads(result_path.read_text(encoding="utf-8"))
        assert saved["scenario_id"] == scenario_id
        assert saved["task_metrics"]["task_completed"] is True
        assert saved["interaction_mode"] == "multi_turn"
        assert saved["artifacts"]["events"] == str(trace_path)
        assert saved["run_metadata"]["caller_participant_events"]
        assert saved["run_metadata"]["first_speaker"] == "caller"
        assert "assistant_opening_prompt_sha256" not in saved["run_metadata"]
        assert saved["run_metadata"]["observability"]["agenda"]["pending_required"] == []
        assert saved["task_metrics"]["outcome_assessment"]["passed"] is True
        assert any(item["type"] == "response" for item in saved["interaction_metrics"]["events"])

        assert row["assessment"]["passed"] is True
        assert row["assessment"]["source"] == "deterministic"
        assert row["observability"]["agenda"]["pending_required"] == []
        assert row["observability"]["completion"]["passed"] is True
        assert row["observability"]["completion"]["failed_checks"] == []


@pytest.mark.asyncio
async def test_offline_run_integrates_a_dual_gpt_live_caller_with_shared_grading(tmp_path: Path) -> None:
    args = parse_args(
        [
            "--offline",
            "--no-judge",
            "--scenario",
            "restaurant_booking_complete",
            "--condition",
            "noisy",
            "--results-dir",
            str(tmp_path),
            "--debug-artifacts",
        ]
    )

    run_dir = await run_evals(args)
    report = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    row = report["results"][0]
    details = json.loads((run_dir / row["artifacts"]["details"]).read_text(encoding="utf-8"))

    assert report["run"]["module"] == "run"
    assert row["status"] == "passed"
    assert row["metrics"]["audio"]["response_rate"] == 1.0
    assert "floor" not in row["observability"]
    assert row["observability"]["interaction"]["caller_mode"] == "offline_fixture"
    assert row["observability"]["agenda"]["pending_required"] == []
    assert details["audio_condition"] == "noisy"
    assert details["run_metadata"]["audio_realism"]["condition"] == "noisy"
    assert details["run_metadata"]["caller_action_attribution"] == "inferred_from_audio_and_transcript"
    assert details["run_metadata"]["first_speaker"] == "caller"
    assert "assistant_opening_prompt_sha256" not in details["run_metadata"]
    assert details["run_metadata"]["simulator_backend_model"] is None
    assert details["run_metadata"]["simulator_backend_reasoning_effort"] is None
    assert details["run_metadata"]["voice_metrics_limitations"]


@pytest.mark.asyncio
async def test_default_gpt_live_offline_fixture_respects_a_forbidden_delegation(tmp_path: Path) -> None:
    args = parse_args(
        [
            "--offline",
            "--no-judge",
            "--scenario",
            "restaurant_cancel_unauthorized",
            "--results-dir",
            str(tmp_path),
        ]
    )

    run_dir = await run_evals(args)
    report = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    details = json.loads((run_dir / "transcripts" / "restaurant_cancel_unauthorized.json").read_text(encoding="utf-8"))

    assert report["results"][0]["status"] == "passed"
    assert details["task_metrics"]["delegation_prohibited"] is True
    assert details["task_metrics"]["delegation_observed"] is False
    assert details["task_metrics"]["application_tool_executions"] == []
