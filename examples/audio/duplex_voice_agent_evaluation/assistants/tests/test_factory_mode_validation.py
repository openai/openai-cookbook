"""Reject unsupported delegation modes before constructing an assistant."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from assistants import create_assistant
from assistants.config import LiveAgentSettings
from run_harness.simulation.models import Settings

INVALID_MODES = [
    pytest.param("decisions", id="unsupported-delegation"),
    pytest.param("unknown", id="unknown"),
    pytest.param("", id="empty"),
    pytest.param(" responses", id="whitespace"),
    pytest.param("CLIENT", id="wrong-case"),
    pytest.param(None, id="null"),
    pytest.param(True, id="boolean"),
    pytest.param(0, id="integer"),
    pytest.param(1.5, id="float"),
    pytest.param(b"client", id="bytes"),
    pytest.param(["client"], id="list"),
    pytest.param({"mode": "client"}, id="mapping"),
]


@pytest.fixture
def constructors(monkeypatch: pytest.MonkeyPatch) -> dict[str, Mock]:
    factories = {"responses": Mock(name="responses_constructor"), "client": Mock(name="client_constructor")}
    monkeypatch.setattr("assistants.ResponsesManagedAssistant", factories["responses"])
    monkeypatch.setattr("assistants.ClientDelegatedAssistant", factories["client"])
    return factories


@pytest.mark.parametrize("mode", ["responses", "client"])
def test_valid_settings_mode_selects_only_matching_constructor(mode: str, constructors: dict[str, Mock]) -> None:
    scenario, executor = object(), Mock()
    settings = SimpleNamespace(assistant_mode=mode)

    result = create_assistant(scenario=scenario, settings=settings, api_key="", tool_executor=executor)

    assert result is constructors[mode].return_value
    constructors[mode].assert_called_once_with(
        scenario=scenario, settings=settings, api_key="", config=None, tool_executor=executor
    )
    constructors["client" if mode == "responses" else "responses"].assert_not_called()


@pytest.mark.parametrize("mode", INVALID_MODES)
@pytest.mark.parametrize("source", ["settings", "config"])
def test_invalid_effective_mode_does_not_construct_an_assistant(
    mode: object, source: str, constructors: dict[str, Mock]
) -> None:
    settings = SimpleNamespace(assistant_mode=mode if source == "settings" else "responses")
    # A caller can bypass Pydantic validation or mutate a previously valid config.
    config = LiveAgentSettings.model_construct(assistant_mode=mode) if source == "config" else None

    with pytest.raises(ValueError, match="assistant_mode.*responses.*client"):
        create_assistant(scenario=object(), settings=settings, api_key="", config=config)

    for factory in constructors.values():
        factory.assert_not_called()


@pytest.mark.parametrize("mode", ["responses", "client"])
@pytest.mark.parametrize("settings_mode", ["responses", "client", "unknown", None])
def test_explicit_config_takes_precedence_over_settings(
    mode: str, settings_mode: object, constructors: dict[str, Mock]
) -> None:
    config = LiveAgentSettings(assistant_mode=mode)
    settings = SimpleNamespace(assistant_mode=settings_mode)

    result = create_assistant(scenario=object(), settings=settings, api_key="", config=config)

    assert result is constructors[mode].return_value
    constructors[mode].assert_called_once()
    assert constructors[mode].call_args.kwargs["config"] is config
    constructors["client" if mode == "responses" else "responses"].assert_not_called()


@pytest.mark.parametrize("settings", [None, SimpleNamespace(), object()], ids=["none", "namespace", "legacy-object"])
def test_absent_legacy_mode_retains_responses_default(settings: object, constructors: dict[str, Mock]) -> None:
    result = create_assistant(scenario=object(), settings=settings, api_key="")

    assert result is constructors["responses"].return_value
    constructors["responses"].assert_called_once()
    constructors["client"].assert_not_called()


@pytest.mark.parametrize("model", [LiveAgentSettings, Settings])
@pytest.mark.parametrize("mode", ["unknown", None, ["client"]], ids=["unknown", "null", "list"])
def test_typed_settings_already_reject_unsupported_modes(model: type, mode: object) -> None:
    with pytest.raises(ValidationError) as caught:
        model(assistant_mode=mode)

    assert any(error["loc"] == ("assistant_mode",) for error in caught.value.errors())
