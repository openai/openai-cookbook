from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

import agent as agent_module
from agent import handler, parse_event, run_deterministic
from schemas import Flight, RuntimeRequest


def test_search_flights_returns_expected_shape() -> None:
    request = RuntimeRequest(
        action="search_flights",
        origin="DAL",
        destination="MDW",
        travel_date="2099-09-21",
    )

    result = run_deterministic(request)

    assert result.provider == "agentcore-runtime"
    assert result.executionMode == "local"
    assert result.action == "search_flights"
    flights = result.data["flights"]
    assert [flight["flightNumber"] for flight in flights] == ["ELZ1234", "ELZ1458"]
    for flight in flights:
        validated_flight = Flight.model_validate(flight)
        assert validated_flight.flightNumber.startswith("ELZ")
        assert validated_flight.travelDate == "2099-09-21"


def test_primary_demo_preserves_date_from_search_through_status() -> None:
    travel_date = "2099-09-21"
    search_result = run_deterministic(
        RuntimeRequest(
            action="search_flights",
            origin="DAL",
            destination="MDW",
            travel_date=travel_date,
        )
    )
    first_flight = search_result.data["flights"][0]

    assert first_flight["travelDate"] == travel_date

    status_result = run_deterministic(
        RuntimeRequest(
            action="get_live_status",
            flight_number=str(first_flight["flightNumber"]),
            origin=str(first_flight["origin"]),
            destination=str(first_flight["destination"]),
            travel_date=str(first_flight["travelDate"]),
        )
    )

    assert status_result.data["flight"]["flightNumber"] == first_flight["flightNumber"]
    assert status_result.data["flight"]["travelDate"] == travel_date
    assert (
        run_deterministic(RuntimeRequest(action="get_upcoming_status")).data["flight"][
            "travelDate"
        ]
        == travel_date
    )


@pytest.mark.parametrize(
    ("runtime_request", "expected_tool_name"),
    [
        (
            RuntimeRequest(
                action="search_flights",
                origin="DAL",
                destination="MDW",
                travel_date="2099-09-21",
            ),
            "get_eliza_airlines_flight_options",
        ),
        (RuntimeRequest(action="get_upcoming_status"), "get_mock_upcoming_eliza_airlines_trip"),
        (
            RuntimeRequest(action="get_live_status", flight_number="ELZ1628"),
            "get_mock_live_eliza_airlines_status",
        ),
    ],
)
def test_every_runtime_action_is_an_agents_sdk_function_tool(
    runtime_request: RuntimeRequest,
    expected_tool_name: str,
) -> None:
    built_agent = agent_module.build_agent(runtime_request, "local")

    assert [tool.name for tool in built_agent.tools] == [expected_tool_name]
    assert built_agent.tool_use_behavior == "stop_on_first_tool"
    assert built_agent.model_settings.tool_choice == expected_tool_name


def test_prompt_event_parses_agentcore_cli_payload() -> None:
    event = {
        "prompt": json.dumps(
            {
                "action": "get_live_status",
                "flight_number": "ELZ1628",
            }
        )
    }

    request = parse_event(event)

    assert request.action == "get_live_status"
    assert request.flight_number == "ELZ1628"


def test_enveloped_event_parses_runtime_request() -> None:
    request = parse_event(
        {
            "request": {"action": "get_upcoming_status"},
            "invocation_id": "mcp-invocation-456",
        }
    )

    assert request.action == "get_upcoming_status"


def test_execution_mode_defaults_and_legacy_compatibility(monkeypatch) -> None:
    monkeypatch.delenv("COOKBOOK_EXECUTION_MODE", raising=False)
    monkeypatch.delenv("FLIGHT_DATA_SOURCE", raising=False)
    assert agent_module.resolve_execution_mode() == "local"

    monkeypatch.setenv("FLIGHT_DATA_SOURCE", "agentcore-runtime")
    assert agent_module.resolve_execution_mode() == "deployed"


def test_execution_mode_rejects_conflicting_settings(monkeypatch) -> None:
    monkeypatch.setenv("COOKBOOK_EXECUTION_MODE", "local")
    monkeypatch.setenv("FLIGHT_DATA_SOURCE", "agentcore-runtime")

    with pytest.raises(RuntimeError, match="conflict"):
        agent_module.resolve_execution_mode()


def test_trace_workflow_name_always_includes_execution_mode(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_TRACE_WORKFLOW_NAME", raising=False)
    assert agent_module.trace_workflow_name("local") == "ChatGPT flight agent (local)"
    assert agent_module.trace_workflow_name("deployed") == "ChatGPT flight agent (deployed)"

    monkeypatch.setenv("OPENAI_TRACE_WORKFLOW_NAME", "Enterprise flight workflow")
    assert agent_module.trace_workflow_name("local") == "Enterprise flight workflow (local)"


def test_handler_can_run_with_local_tools(monkeypatch) -> None:
    monkeypatch.setenv("COOKBOOK_FORCE_LOCAL_TOOLS", "1")

    response = handler({"action": "get_upcoming_status"})
    body = json.loads(str(response["body"]))

    assert response["statusCode"] == 200
    assert body["provider"] == "agentcore-runtime"
    assert body["executionMode"] == "local"
    assert body["data"]["flight"]["status"] == "ON_TIME"


def test_handler_rejects_missing_search_fields(monkeypatch) -> None:
    monkeypatch.setenv("COOKBOOK_FORCE_LOCAL_TOOLS", "1")

    response = handler({"action": "search_flights", "origin": "DAL"})

    assert response["statusCode"] == 400
    assert "search_flights is missing" in str(response["body"])


def _configure_safe_telemetry_environment(monkeypatch) -> None:
    monkeypatch.delenv("COOKBOOK_MANUAL_OPENAI_AGENTS_INSTRUMENTATION", raising=False)
    monkeypatch.delenv("OPENAI_TRACING_ENABLED", raising=False)
    monkeypatch.delenv("DISABLE_ADOT_OBSERVABILITY", raising=False)
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    monkeypatch.delenv("OTEL_PYTHON_DISABLED_INSTRUMENTATIONS", raising=False)
    monkeypatch.setattr(
        agent_module.otel_trace,
        "get_tracer_provider",
        lambda: SimpleNamespace(force_flush=lambda: True),
    )


def test_uninstrumented_agent_fails_before_invoking_the_model(monkeypatch) -> None:
    _configure_safe_telemetry_environment(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "bedrock-model-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://bedrock-mantle.us-west-2.api.aws/v1")
    monkeypatch.setenv("AWS_REGION", "us-west-2")
    monkeypatch.setenv("COOKBOOK_TRACING_MODE", "aws")
    monkeypatch.setattr(agent_module.otel_trace, "get_tracer_provider", lambda: object())
    monkeypatch.setattr(
        agent_module.Runner,
        "run_sync",
        lambda *args, **kwargs: pytest.fail("An uninstrumented run must not invoke the model"),
    )

    with pytest.raises(RuntimeError, match="OpenTelemetry SDK is not initialized"):
        agent_module.run_with_agents_sdk(RuntimeRequest(action="get_upcoming_status"))


def test_tracing_mode_defaults_to_aws_without_an_openai_trace_key(monkeypatch) -> None:
    disabled_values: list[bool] = []
    configured_modes: list[str] = []
    _configure_safe_telemetry_environment(monkeypatch)
    monkeypatch.delenv("COOKBOOK_TRACING_MODE", raising=False)
    monkeypatch.delenv("OPENAI_TRACE_API_KEY", raising=False)
    monkeypatch.setattr(agent_module, "set_tracing_disabled", disabled_values.append)
    monkeypatch.setattr(agent_module, "_configure_trace_processors", configured_modes.append)
    monkeypatch.setattr(
        agent_module,
        "set_tracing_export_api_key",
        lambda _: pytest.fail("AWS-only mode must not configure the OpenAI exporter"),
    )

    assert agent_module.resolve_tracing_mode() == "aws"
    assert agent_module._configure_tracing("aws") is None
    assert disabled_values == [False]
    assert configured_modes == ["aws"]


@pytest.mark.parametrize("value", ["local", "AWS", "dual,aws"])
def test_tracing_mode_rejects_unknown_values(monkeypatch, value: str) -> None:
    monkeypatch.setenv("COOKBOOK_TRACING_MODE", value)

    with pytest.raises(RuntimeError, match="COOKBOOK_TRACING_MODE must be aws or dual"):
        agent_module.resolve_tracing_mode()


def test_dual_tracing_requires_a_distinct_platform_key(monkeypatch) -> None:
    _configure_safe_telemetry_environment(monkeypatch)
    monkeypatch.setattr(agent_module, "_configure_trace_processors", lambda _: None)
    monkeypatch.setattr(agent_module, "set_tracing_disabled", lambda _: None)
    monkeypatch.delenv("OPENAI_TRACE_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="OPENAI_TRACE_API_KEY is required"):
        agent_module._configure_tracing("dual")

    monkeypatch.setenv("OPENAI_API_KEY", "shared-key")
    monkeypatch.setenv("OPENAI_TRACE_API_KEY", "shared-key")
    with pytest.raises(RuntimeError, match="must use separate credentials"):
        agent_module._configure_tracing("dual")


def test_dual_tracing_configures_only_the_platform_exporter(monkeypatch) -> None:
    _configure_safe_telemetry_environment(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "bedrock-model-key")
    monkeypatch.setenv("OPENAI_TRACE_API_KEY", "platform-key")
    observed: dict[str, object] = {}
    monkeypatch.setattr(
        agent_module,
        "_configure_trace_processors",
        lambda mode: observed.update(processor_mode=mode),
    )
    monkeypatch.setattr(
        agent_module,
        "set_tracing_export_api_key",
        lambda key: observed.update(trace_api_key=key),
    )
    monkeypatch.setattr(
        agent_module,
        "set_tracing_disabled",
        lambda disabled: observed.update(tracing_disabled=disabled),
    )

    assert agent_module._configure_tracing("dual") == {"api_key": "platform-key"}
    assert observed == {
        "processor_mode": "dual",
        "trace_api_key": "platform-key",
        "tracing_disabled": False,
    }


def test_trace_processor_setup_uses_public_apis_without_an_openai_exporter_in_aws(
    monkeypatch,
) -> None:
    calls: list[str] = []
    configured: list[list[object]] = []

    class FakeInstrumentor:
        def uninstrument(self) -> None:
            calls.append("uninstrument")

        def instrument(self) -> None:
            calls.append("instrument")

    monkeypatch.setattr(agent_module, "OpenAIAgentsInstrumentor", FakeInstrumentor)
    monkeypatch.setattr(agent_module, "set_trace_provider", lambda _: calls.append("provider"))
    monkeypatch.setattr(agent_module, "set_trace_processors", configured.append)
    monkeypatch.setattr(
        agent_module,
        "default_processor",
        lambda: pytest.fail("AWS-only setup must not create an OpenAI backend exporter"),
    )

    agent_module._configure_trace_processors("aws")

    assert configured == [
        [],
    ]
    assert calls == ["uninstrument", "provider", "instrument"]


def test_trace_processor_setup_rebuilds_adot_without_duplicates(monkeypatch) -> None:
    from agents.tracing import get_trace_provider
    from agents.tracing.provider import DefaultTraceProvider
    from opentelemetry.instrumentation.openai_agents import OpenAIAgentsInstrumentor

    def processor_names() -> list[str]:
        # This assertion intentionally observes installed SDK state; production
        # code uses only public setup APIs above.
        provider = get_trace_provider()
        provider_state = cast(dict[str, Any], vars(provider))
        multi_processor = provider_state["_multi_processor"]
        processor_state = cast(dict[str, Any], vars(multi_processor))
        return [type(processor).__name__ for processor in processor_state["_processors"]]

    OpenAIAgentsInstrumentor().uninstrument()
    agent_module.set_trace_provider(DefaultTraceProvider())

    try:
        agent_module._configure_trace_processors("aws")
        assert processor_names() == ["GenAISemanticProcessor"]

        agent_module._configure_trace_processors("aws")
        assert processor_names() == ["GenAISemanticProcessor"]

        agent_module._configure_trace_processors("dual")
        assert processor_names() == ["BatchTraceProcessor", "GenAISemanticProcessor"]

        agent_module._configure_trace_processors("dual")
        assert processor_names() == ["BatchTraceProcessor", "GenAISemanticProcessor"]
    finally:
        # Leave the process with a single ADOT bridge for remaining tests.
        agent_module._configure_trace_processors("aws")


def test_aws_import_and_setup_do_not_construct_an_openai_backend_exporter() -> None:
    runtime_directory = Path(__file__).resolve().parents[1]
    code = """
from agents.tracing import get_trace_provider
from agents.tracing import processors

def forbidden_default_processor():
    raise AssertionError("AWS-only setup constructed the OpenAI backend processor")

processors.default_processor = forbidden_default_processor
import agent
agent._configure_trace_processors("aws")
provider_state = vars(get_trace_provider())
processors_state = vars(provider_state["_multi_processor"])
print(",".join(type(processor).__name__ for processor in processors_state["_processors"]))
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=runtime_directory,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "GenAISemanticProcessor"


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("DISABLE_ADOT_OBSERVABILITY", "true", "cannot be enabled"),
        ("OTEL_SDK_DISABLED", "true", "cannot be enabled"),
        (
            "OTEL_PYTHON_DISABLED_INSTRUMENTATIONS",
            "requests,openai_agents",
            "instrumentor cannot be disabled",
        ),
    ],
)
def test_all_tracing_modes_require_agentcore_observability(
    monkeypatch, name: str, value: str, message: str
) -> None:
    _configure_safe_telemetry_environment(monkeypatch)
    monkeypatch.setenv(name, value)

    with pytest.raises(RuntimeError, match=message):
        agent_module._configure_tracing("aws")


def test_manual_agent_instrumentation_requires_disabling_automatic_instrumentation(
    monkeypatch,
) -> None:
    _configure_safe_telemetry_environment(monkeypatch)
    monkeypatch.setenv("COOKBOOK_MANUAL_OPENAI_AGENTS_INSTRUMENTATION", "true")

    with pytest.raises(RuntimeError, match="requires disabling"):
        agent_module._configure_tracing("aws")


def test_manual_agent_instrumentation_preserves_the_required_adot_bridge(monkeypatch) -> None:
    _configure_safe_telemetry_environment(monkeypatch)
    monkeypatch.setenv("COOKBOOK_MANUAL_OPENAI_AGENTS_INSTRUMENTATION", "true")
    monkeypatch.setenv("OTEL_PYTHON_DISABLED_INSTRUMENTATIONS", "openai_agents")
    configured_modes: list[str] = []
    monkeypatch.setattr(agent_module, "_configure_trace_processors", configured_modes.append)
    monkeypatch.setattr(agent_module, "set_tracing_disabled", lambda _: None)

    assert agent_module._configure_tracing("aws") is None
    assert configured_modes == ["aws"]


def test_aws_mode_rejects_legacy_opt_in_to_prevent_implicit_dual_export(monkeypatch) -> None:
    _configure_safe_telemetry_environment(monkeypatch)
    monkeypatch.setenv("OPENAI_TRACING_ENABLED", "1")

    with pytest.raises(RuntimeError, match="COOKBOOK_TRACING_MODE=dual explicitly"):
        agent_module._configure_tracing("aws")


def test_bedrock_model_client_isolated_from_platform_headers(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "bedrock-model-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://bedrock-mantle.us-west-2.api.aws/v1")
    monkeypatch.setenv("OPENAI_PROJECT_ID", "proj_platform")
    monkeypatch.setenv("OPENAI_ORG_ID", "org_platform")
    monkeypatch.setenv("OPENAI_CUSTOM_HEADERS", "OpenAI-Project: overridden")

    model = agent_module.build_bedrock_model()

    assert model._client.api_key == "bedrock-model-key"
    assert str(model._client.base_url) == "https://bedrock-mantle.us-west-2.api.aws/v1/"
    assert "OpenAI-Project" not in model._client.default_headers
    assert "OpenAI-Organization" not in model._client.default_headers


def test_agent_run_uses_aws_only_tracing_without_a_platform_key(monkeypatch) -> None:
    request = RuntimeRequest(action="get_upcoming_status")
    observed: dict[str, object] = {}

    monkeypatch.setenv("OPENAI_API_KEY", "bedrock-key")
    monkeypatch.setenv("AWS_REGION", "us-west-2")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://bedrock-mantle.us-west-2.api.aws/v1")
    monkeypatch.setenv("COOKBOOK_TRACING_MODE", "aws")
    _configure_safe_telemetry_environment(monkeypatch)
    monkeypatch.delenv("OPENAI_TRACE_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_TRACE_INCLUDE_SENSITIVE_DATA", "0")
    monkeypatch.setenv("OPENAI_TRACE_WORKFLOW_NAME", "ChatGPT flight agent")
    monkeypatch.setattr(
        agent_module,
        "_configure_tracing",
        lambda mode: observed.update(mode=mode),
    )
    monkeypatch.setattr(agent_module, "build_bedrock_model", lambda: "bedrock-model")
    monkeypatch.setattr(
        agent_module,
        "_flush_trace_destinations",
        lambda: observed.update(flushed=True),
    )

    def fake_run_sync(*args: object, **kwargs: object) -> SimpleNamespace:
        observed["run_config"] = kwargs["run_config"]
        return SimpleNamespace(final_output=run_deterministic(request).model_dump())

    monkeypatch.setattr(agent_module.Runner, "run_sync", fake_run_sync)

    result = agent_module.run_with_agents_sdk(
        request,
        runtime_session_id="runtime-session-123",
        invocation_id="mcp-invocation-456",
        execution_mode="local",
    )
    run_config = cast(agent_module.RunConfig, observed["run_config"])

    assert result.action == "get_upcoming_status"
    assert result.executionMode == "local"
    assert observed["mode"] == "aws"
    assert observed["flushed"] is True
    assert isinstance(run_config, agent_module.RunConfig)
    assert run_config.tracing_disabled is False
    assert run_config.tracing is None
    assert run_config.trace_include_sensitive_data is False
    assert run_config.workflow_name == "ChatGPT flight agent (local)"
    assert run_config.group_id == "runtime-session-123"
    assert run_config.trace_metadata == {
        "cookbook": "chatgpt-agents-sdk-aws-agentcore",
        "execution_mode": "local",
        "action": "get_upcoming_status",
        "tracing_mode": "aws",
        "runtime_session_id": "runtime-session-123",
        "mcp_invocation_id": "mcp-invocation-456",
    }


def test_agent_run_rejects_execution_mode_drift_after_flushing_traces(monkeypatch) -> None:
    request = RuntimeRequest(action="get_upcoming_status")
    flushed: list[bool] = []

    monkeypatch.setenv("OPENAI_API_KEY", "bedrock-key")
    monkeypatch.setenv("AWS_REGION", "us-west-2")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://bedrock-mantle.us-west-2.api.aws/v1")
    monkeypatch.setenv("COOKBOOK_TRACING_MODE", "aws")
    _configure_safe_telemetry_environment(monkeypatch)
    monkeypatch.setattr(agent_module, "_configure_tracing", lambda _: None)
    monkeypatch.setattr(agent_module, "build_bedrock_model", lambda: "bedrock-model")
    monkeypatch.setattr(
        agent_module,
        "_flush_trace_destinations",
        lambda: flushed.append(True),
    )
    monkeypatch.setattr(
        agent_module.Runner,
        "run_sync",
        lambda *args, **kwargs: SimpleNamespace(
            final_output=run_deterministic(
                request,
                execution_mode="deployed",
            ).model_dump()
        ),
    )

    with pytest.raises(RuntimeError, match="does not match the selected route"):
        agent_module.run_with_agents_sdk(request, execution_mode="local")

    assert flushed == [True]


def test_trace_flush_drains_configured_agents_sdk_and_agentcore_exporters(monkeypatch) -> None:
    observed: list[str] = []

    class FakeTracerProvider:
        def force_flush(self) -> bool:
            observed.append("agentcore")
            return True

    def flush_openai() -> None:
        assert agent_module.baggage.get_baggage("session.id") is None
        assert agent_module.baggage.get_baggage("mcp.invocation.id") is None
        observed.append("openai")

    monkeypatch.setattr(agent_module, "flush_traces", flush_openai)
    monkeypatch.setattr(
        agent_module.otel_trace,
        "get_tracer_provider",
        lambda: FakeTracerProvider(),
    )

    trace_context = agent_module.baggage.set_baggage("session.id", "session-123")
    trace_context = agent_module.baggage.set_baggage(
        "mcp.invocation.id", "invocation-456", context=trace_context
    )
    token = agent_module.otel_context.attach(trace_context)
    try:
        agent_module._flush_trace_destinations()
        assert agent_module.baggage.get_baggage("session.id") == "session-123"
        assert agent_module.baggage.get_baggage("mcp.invocation.id") == "invocation-456"
    finally:
        agent_module.otel_context.detach(token)

    assert observed == ["openai", "agentcore"]


def test_trace_flush_fails_when_agentcore_export_cannot_flush(monkeypatch) -> None:
    class FakeTracerProvider:
        def force_flush(self) -> bool:
            return False

    monkeypatch.setattr(agent_module, "flush_traces", lambda: None)
    monkeypatch.setattr(
        agent_module.otel_trace,
        "get_tracer_provider",
        lambda: FakeTracerProvider(),
    )

    with pytest.raises(RuntimeError, match="did not flush"):
        agent_module._flush_trace_destinations()


def test_trace_flush_propagates_a_configured_exporter_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        agent_module,
        "flush_traces",
        lambda: (_ for _ in ()).throw(RuntimeError("hosted exporter rejected the trace")),
    )

    with pytest.raises(RuntimeError, match="hosted exporter rejected"):
        agent_module._flush_trace_destinations()
