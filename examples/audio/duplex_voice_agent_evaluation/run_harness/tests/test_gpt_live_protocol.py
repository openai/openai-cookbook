"""Shared GPT Live protocol configuration used by the RUN harness."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from assistants.config import LiveAgentSettings, build_assistant_session, session_update, websocket_url
from assistants.resources import assistant_resources
from assistants.responses.assistant import ResponsesManagedAssistant
from run_harness.simulation.models import Scenario, Settings
from shared.scenarios import ConversationContext


def scenario() -> Scenario:
    return Scenario(
        id="x",
        title="x",
        interaction="multi_turn",
        input={"text": "hi"},
        expected={"answer": "x", "criteria": ["x"]},
        simulation_parameters={"goal": "x", "persona": {"id": "p", "description": "p"}},
    )


def test_run_loads_the_independent_managed_agent() -> None:
    assert LiveAgentSettings.__module__ == "assistants.config"
    assert ResponsesManagedAssistant.__module__ == "assistants.responses.assistant"
    assert "agent_adapter" not in Settings.model_fields


def test_gpt_live_configuration_reads_agent_values_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment = {
        "OPENAI_LIVE_ENDPOINT": "https://live.example.test/v1/live/sessions",
        "OPENAI_LIVE_MODEL": "env-live-model",
        "OPENAI_LIVE_VOICE": "env-voice",
        "OPENAI_LIVE_BACKEND_MODEL": "env-backend-model",
        "OPENAI_LIVE_BACKEND_REASONING_EFFORT": "medium",
        "OPENAI_LIVE_BACKEND_MAX_OUTPUT_TOKENS": "432",
        "OPENAI_LIVE_BACKEND_VERBOSITY": "high",
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)

    settings = LiveAgentSettings()

    assert settings.endpoint == "https://live.example.test/v1/live/sessions"
    assert settings.model == "env-live-model"
    assert settings.voice == "env-voice"
    assert settings.backend_model == "env-backend-model"
    assert settings.backend_reasoning_effort == "medium"
    assert settings.backend_max_output_tokens == 432
    assert settings.backend_verbosity == "high"


@pytest.mark.parametrize(
    ("name", "attribute", "expected"),
    [
        ("OPENAI_LIVE_ENDPOINT", "endpoint", "https://api.openai.com/v1/live/sessions"),
        ("OPENAI_LIVE_MODEL", "model", "gpt-live-1"),
        ("OPENAI_LIVE_VOICE", "voice", "marin"),
        ("OPENAI_LIVE_BACKEND_MODEL", "backend_model", "gpt-5.6-terra"),
        ("OPENAI_LIVE_BACKEND_REASONING_EFFORT", "backend_reasoning_effort", "none"),
        ("OPENAI_LIVE_BACKEND_MAX_OUTPUT_TOKENS", "backend_max_output_tokens", 1000),
        ("OPENAI_LIVE_BACKEND_VERBOSITY", "backend_verbosity", "low"),
    ],
)
def test_gpt_live_uses_application_defaults_when_environment_settings_are_missing(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    attribute: str,
    expected: str | int,
) -> None:
    monkeypatch.delenv(name, raising=False)

    assert getattr(LiveAgentSettings(), attribute) == expected


def test_example_environment_is_never_loaded_at_runtime() -> None:
    project_root = Path(__file__).resolve().parents[2]
    probe = (
        "import json\n"
        "from unittest.mock import patch\n"
        "with patch('dotenv.load_dotenv') as load:\n"
        "    import assistants.config\n"
        "print(json.dumps([str(call.args[0]) for call in load.call_args_list]))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(result.stdout) == []


def test_gpt_live_url_and_session_delegation_schema() -> None:
    settings = LiveAgentSettings(model="custom-live-model", voice="voice_123")
    assert websocket_url("https://api.openai.com/v1/live/sessions", settings.model) == (
        "wss://api.openai.com/v1/live/sessions"
    )
    event = session_update(scenario(), settings)
    assert event["type"] == "session.start"
    assert event["session"]["model"] == "custom-live-model"
    assert event["session"]["audio"]["output"]["voice"] == {"id": "voice_123"}
    responses = event["session"]["delegation"]["responses"]
    assert {tool["name"] for tool in responses["tools"]} == {
        "check_availability",
        "create_reservation",
        "cancel_reservation",
    }
    assert responses["reasoning"] == {"effort": settings.backend_reasoning_effort}
    assert responses["max_output_tokens"] == settings.backend_max_output_tokens
    assert responses["text"] == {"verbosity": settings.backend_verbosity}


def test_gpt_live_builtin_voice_is_sent_as_a_string() -> None:
    event = session_update(scenario(), LiveAgentSettings(voice="marin"))

    assert event["session"]["audio"]["output"]["voice"] == "marin"


@pytest.mark.parametrize("assistant_mode", ["responses", "client"])
def test_gpt_live_session_uses_mode_specific_prompt_files(assistant_mode: str) -> None:
    resources = assistant_resources(assistant_mode=assistant_mode)
    event = session_update(scenario(), LiveAgentSettings(assistant_mode=assistant_mode))

    assert event["session"]["instructions"] == resources.system_prompt_file.read_text(encoding="utf-8").strip()
    if assistant_mode == "responses":
        backend = event["session"]["delegation"]["responses"]
        assert backend["instructions"] == resources.backend_system_prompt_file.read_text(encoding="utf-8").strip()


def test_gpt_live_hydrates_prior_conversation_as_text_items() -> None:
    existing = scenario().model_copy(deep=True)
    existing.input.context = ConversationContext(
        history=[
            {"role": "user", "text": "The reservation should be under Maya."},
            {"role": "assistant", "text": "Which date works for you?"},
        ]
    )

    event = session_update(existing, LiveAgentSettings())

    assert event["session"]["input"] == [
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "The reservation should be under Maya."}],
        },
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "Which date works for you?"}],
        },
    ]


def test_run_uses_the_shared_session_builder() -> None:
    config = LiveAgentSettings(backend_reasoning_effort="low", backend_max_output_tokens=250)
    settings = Settings(
        agent_instructions="Shared target frontend instructions.",
        backend_instructions="Shared target backend instructions.",
        delegation_tools=[{"type": "web_search"}],
    )
    expected = build_assistant_session(
        config,
        instructions=settings.agent_instructions,
        backend_instructions=settings.backend_instructions,
        tools=settings.delegation_tools,
    )

    assert session_update(scenario(), config, settings) == expected


def test_gpt_live_keeps_delegation_available_with_customer_like_settings() -> None:
    config = LiveAgentSettings(voice="marin")
    settings = Settings(agent_instructions="Use tools only when the caller's request requires them.")
    event = session_update(scenario(), config, settings)

    responses = event["session"]["delegation"]["responses"]
    assert event["session"]["instructions"] == settings.agent_instructions
    assert responses["model"] == config.backend_model
    assert {tool["name"] for tool in responses["tools"]} == {
        "check_availability",
        "create_reservation",
        "cancel_reservation",
    }


def test_gpt_live_delegation_uses_configured_reasoning_and_output_parameters() -> None:
    settings = LiveAgentSettings(
        backend_reasoning_effort="low",
        backend_max_output_tokens=250,
        backend_verbosity="medium",
    )

    responses = session_update(scenario(), settings)["session"]["delegation"]["responses"]
    assert responses["reasoning"] == {"effort": "low"}
    assert responses["max_output_tokens"] == 250
    assert responses["text"] == {"verbosity": "medium"}


def test_gpt_live_agent_never_receives_evaluator_only_data() -> None:
    hidden = Scenario(
        id="no_leakage",
        title="Keep evaluator data private",
        interaction="multi_turn",
        input={"text": "Please answer my question."},
        expected={"answer": "PRIVATE_GOLDEN_ANSWER", "criteria": ["PRIVATE_GRADING_CRITERION"]},
        simulation_parameters={
            "goal": "PRIVATE_SIMULATOR_GOAL",
            "persona": {"id": "p", "description": "PRIVATE_PERSONA_DESCRIPTION"},
        },
    )
    settings = Settings(agent_instructions="Answer only from caller audio and verified tools.")

    sent = json.dumps(session_update(hidden, LiveAgentSettings(voice="marin"), settings))

    assert "PRIVATE_GOLDEN_ANSWER" not in sent
    assert "PRIVATE_GRADING_CRITERION" not in sent
    assert "PRIVATE_SIMULATOR_GOAL" not in sent
    assert "PRIVATE_PERSONA_DESCRIPTION" not in sent
