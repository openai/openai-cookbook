from __future__ import annotations

import json
import os
from typing import Any, Literal, Protocol, cast

from agents import (
    Agent,
    AgentOutputSchema,
    ModelSettings,
    OpenAIChatCompletionsModel,
    RunConfig,
    Runner,
    flush_traces,
    function_tool,
    set_trace_processors,
    set_trace_provider,
    set_tracing_disabled,
    set_tracing_export_api_key,
)
from agents.tracing import TracingConfig
from agents.tracing.processors import default_processor
from agents.tracing.provider import DefaultTraceProvider
from openai import AsyncOpenAI
from opentelemetry import baggage
from opentelemetry import context as otel_context
from opentelemetry import trace as otel_trace
from opentelemetry.instrumentation.openai_agents import OpenAIAgentsInstrumentor
from pydantic import ValidationError

from endpoint_validation import resolve_aws_region, validate_bedrock_base_url
from schemas import ExecutionMode, RuntimeRequest, RuntimeResponse
from tools import live_status, search_flights, upcoming_status

MODEL_ENV = "OPENAI_AGENTS_MODEL"
DEFAULT_MODEL = "openai.gpt-oss-120b"
TRACE_API_KEY_ENV = "OPENAI_TRACE_API_KEY"
TRACE_INCLUDE_SENSITIVE_DATA_ENV = "OPENAI_TRACE_INCLUDE_SENSITIVE_DATA"
DEFAULT_TRACE_WORKFLOW_NAME = "ChatGPT flight agent"
TracingMode = Literal["aws", "dual"]
LEGACY_EXECUTION_MODES: dict[str, ExecutionMode] = {
    "local-agent": "local",
    "agentcore-runtime": "deployed",
}


class RuntimeContext(Protocol):
    session_id: str | None


class BedrockOpenAIClient(AsyncOpenAI):
    """Prevent OpenAI Platform routing headers from reaching the Bedrock endpoint."""

    @property
    def default_headers(self) -> dict[str, Any]:
        headers = super().default_headers
        headers.pop("OpenAI-Organization", None)
        headers.pop("OpenAI-Project", None)
        return headers


def _event_payload(event: dict[str, Any]) -> dict[str, Any]:
    payload = event
    if "prompt" in event and isinstance(event["prompt"], str):
        payload = json.loads(event["prompt"])
    return payload


def parse_event(event: dict[str, Any]) -> RuntimeRequest:
    payload = _event_payload(event)
    if "request" in payload and isinstance(payload["request"], dict):
        payload = payload["request"]
    return RuntimeRequest.model_validate(payload)


def resolve_execution_mode(explicit_mode: str | None = None) -> ExecutionMode:
    configured_mode = os.environ.get("COOKBOOK_EXECUTION_MODE", "").strip() or None
    if configured_mode not in {None, "local", "deployed"}:
        raise RuntimeError("COOKBOOK_EXECUTION_MODE must be local or deployed")

    legacy_data_source = os.environ.get("FLIGHT_DATA_SOURCE", "").strip() or None
    legacy_mode = LEGACY_EXECUTION_MODES.get(legacy_data_source or "")
    if legacy_data_source and legacy_mode is None:
        raise RuntimeError("FLIGHT_DATA_SOURCE must be local-agent or agentcore-runtime")

    values = [value for value in (explicit_mode, configured_mode, legacy_mode) if value]
    if any(value not in {"local", "deployed"} for value in values):
        raise RuntimeError("execution_mode must be local or deployed")
    if len(set(values)) > 1:
        raise RuntimeError("Execution mode settings conflict")
    return cast(ExecutionMode, values[0] if values else "local")


def trace_workflow_name(execution_mode: ExecutionMode) -> str:
    base_name = (
        os.environ.get("OPENAI_TRACE_WORKFLOW_NAME", "").strip() or DEFAULT_TRACE_WORKFLOW_NAME
    )
    return f"{base_name} ({execution_mode})"


def resolve_tracing_mode(explicit_mode: str | None = None) -> TracingMode:
    configured_mode = os.environ.get("COOKBOOK_TRACING_MODE", "").strip() or None
    values = [value for value in (explicit_mode, configured_mode) if value]
    if len(set(values)) > 1:
        raise RuntimeError("Tracing mode settings conflict")
    selected_mode = values[0] if values else "aws"
    if selected_mode not in {"aws", "dual"}:
        raise RuntimeError("COOKBOOK_TRACING_MODE must be aws or dual")
    return cast(TracingMode, selected_mode)


def run_deterministic(
    request: RuntimeRequest,
    *,
    execution_mode: ExecutionMode = "local",
) -> RuntimeResponse:
    if request.action == "search_flights":
        data = search_flights(request)
    elif request.action == "get_upcoming_status":
        data = upcoming_status()
    else:
        data = live_status(request)
    return RuntimeResponse(
        executionMode=execution_mode,
        action=request.action,
        data=data,
    )


def _require_model_environment() -> None:
    missing = [
        name
        for name in ("OPENAI_API_KEY", "OPENAI_BASE_URL")
        if not os.environ.get(name, "").strip()
    ]
    if missing:
        raise RuntimeError(f"Missing model environment: {', '.join(missing)}")
    region = resolve_aws_region(os.environ.get("AWS_REGION"), os.environ.get("AWS_DEFAULT_REGION"))
    validate_bedrock_base_url(os.environ["OPENAI_BASE_URL"], region)


def build_bedrock_model() -> OpenAIChatCompletionsModel:
    """Build an isolated model client instead of using the process-global OpenAI client."""
    return OpenAIChatCompletionsModel(
        model=os.environ.get(MODEL_ENV, DEFAULT_MODEL),
        openai_client=BedrockOpenAIClient(
            api_key=os.environ["OPENAI_API_KEY"],
            base_url=os.environ["OPENAI_BASE_URL"],
        ),
    )


def _environment_flag(name: str, *, default: bool = False) -> bool:
    raw_value = os.environ.get(name)
    if raw_value is None or not raw_value.strip():
        return default
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"{name} must be a boolean value such as 1 or 0")


def _require_agentcore_observability() -> None:
    if _environment_flag("DISABLE_ADOT_OBSERVABILITY"):
        raise RuntimeError(
            "DISABLE_ADOT_OBSERVABILITY cannot be enabled: every real agent run "
            "must be exported to AgentCore Observability"
        )
    if _environment_flag("OTEL_SDK_DISABLED"):
        raise RuntimeError(
            "OTEL_SDK_DISABLED cannot be enabled: every real agent run "
            "must be exported to AgentCore Observability"
        )

    disabled_instrumentors = {
        value.strip().lower().replace("-", "_")
        for value in os.environ.get("OTEL_PYTHON_DISABLED_INSTRUMENTATIONS", "").split(",")
        if value.strip()
    }
    manual_agent_instrumentation = _environment_flag(
        "COOKBOOK_MANUAL_OPENAI_AGENTS_INSTRUMENTATION"
    )
    if "openai_agents" in disabled_instrumentors and not manual_agent_instrumentation:
        raise RuntimeError(
            "The OpenAI Agents OpenTelemetry instrumentor cannot be disabled: "
            "function-tool spans must be exported to AgentCore Observability"
        )
    if manual_agent_instrumentation and "openai_agents" not in disabled_instrumentors:
        raise RuntimeError(
            "COOKBOOK_MANUAL_OPENAI_AGENTS_INSTRUMENTATION requires disabling the "
            "automatic openai_agents instrumentor"
        )
    if not callable(getattr(otel_trace.get_tracer_provider(), "force_flush", None)):
        raise RuntimeError(
            "AgentCore OpenTelemetry SDK is not initialized; use the instrumented "
            "MCP adapter launcher (npm --prefix runtime-agent run trace:run)"
        )


def _configure_trace_processors(tracing_mode: TracingMode) -> None:
    """Rebuild the public Agents-to-OpenTelemetry bridge for the selected mode.

    The SDK's normal provider lazily creates its OpenAI processor the first time
    it is accessed. Installing an empty provider before adding the AgentCore
    ADOT bridge avoids that side effect in AWS-only mode. Rebuilding through the
    Agents provider/processor setters and ``OpenAIAgentsInstrumentor`` makes
    repeated initialization deterministic: AWS-only installs only the ADOT
    bridge and dual installs it alongside the explicit OpenAI backend processor.
    """
    instrumentor = OpenAIAgentsInstrumentor()
    instrumentor.uninstrument()
    set_trace_provider(DefaultTraceProvider())
    if tracing_mode == "dual":
        set_trace_processors([default_processor()])
    else:
        set_trace_processors([])
    instrumentor.instrument()


def _configure_tracing(tracing_mode: TracingMode) -> TracingConfig | None:
    legacy_toggle = os.environ.get("OPENAI_TRACING_ENABLED")
    if (
        tracing_mode == "aws"
        and legacy_toggle is not None
        and _environment_flag("OPENAI_TRACING_ENABLED")
    ):
        raise RuntimeError(
            "OPENAI_TRACING_ENABLED does not select OpenAI tracing; set "
            "COOKBOOK_TRACING_MODE=dual explicitly"
        )
    if (
        tracing_mode == "dual"
        and legacy_toggle is not None
        and not _environment_flag("OPENAI_TRACING_ENABLED")
    ):
        raise RuntimeError("COOKBOOK_TRACING_MODE=dual requires OpenAI tracing to remain enabled")

    _require_agentcore_observability()
    _configure_trace_processors(tracing_mode)
    set_tracing_disabled(False)

    if tracing_mode == "aws":
        return None

    trace_api_key = os.environ.get(TRACE_API_KEY_ENV, "").strip()
    if not trace_api_key:
        raise RuntimeError("OPENAI_TRACE_API_KEY is required when COOKBOOK_TRACING_MODE=dual")
    model_api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if model_api_key and trace_api_key == model_api_key:
        raise RuntimeError("OPENAI_API_KEY and OPENAI_TRACE_API_KEY must use separate credentials")

    # OPENAI_API_KEY belongs to the Bedrock-compatible model endpoint. Supplying
    # the Platform key directly prevents that model credential from being sent to
    # the OpenAI trace-ingest endpoint.
    set_tracing_export_api_key(trace_api_key)
    return {"api_key": trace_api_key}


def _flush_trace_destinations() -> None:
    """Drain configured Agents SDK processors and the AgentCore OpenTelemetry exporter."""
    # Exporter HTTP requests are telemetry plumbing, not part of the agent turn.
    # Remove correlation baggage while draining so those HTTP spans do not become
    # extra traces in the correlated application session.
    export_context = baggage.remove_baggage("session.id")
    export_context = baggage.remove_baggage("mcp.invocation.id", context=export_context)
    token = otel_context.attach(export_context)
    try:
        flush_traces()
        force_flush = getattr(otel_trace.get_tracer_provider(), "force_flush", None)
        if callable(force_flush) and force_flush() is False:
            raise RuntimeError("AgentCore OpenTelemetry trace export did not flush")
    finally:
        otel_context.detach(token)


def build_agent(
    request: RuntimeRequest,
    execution_mode: ExecutionMode,
    *,
    model: str | OpenAIChatCompletionsModel | None = None,
) -> Agent:
    tools: list[Any]
    if request.action == "search_flights":

        @function_tool
        def get_eliza_airlines_flight_options() -> dict[str, object]:
            return run_deterministic(
                request,
                execution_mode=execution_mode,
            ).model_dump()

        tools = [get_eliza_airlines_flight_options]
        tool_choice = "get_eliza_airlines_flight_options"
    elif request.action == "get_upcoming_status":

        @function_tool
        def get_mock_upcoming_eliza_airlines_trip() -> dict[str, object]:
            return run_deterministic(
                request,
                execution_mode=execution_mode,
            ).model_dump()

        tools = [get_mock_upcoming_eliza_airlines_trip]
        tool_choice = "get_mock_upcoming_eliza_airlines_trip"
    else:

        @function_tool
        def get_mock_live_eliza_airlines_status() -> dict[str, object]:
            return run_deterministic(
                request,
                execution_mode=execution_mode,
            ).model_dump()

        tools = [get_mock_live_eliza_airlines_status]
        tool_choice = "get_mock_live_eliza_airlines_status"

    return Agent(
        name="ChatGPT MCP flight cookbook agent",
        instructions="Call the selected read-only function tool exactly once and return its JSON.",
        model=model or os.environ.get(MODEL_ENV, DEFAULT_MODEL),
        output_type=AgentOutputSchema(dict, strict_json_schema=False),
        model_settings=ModelSettings(
            parallel_tool_calls=False,
            tool_choice=tool_choice,
        ),
        tools=tools,
        tool_use_behavior="stop_on_first_tool",
    )


def run_with_agents_sdk(
    request: RuntimeRequest,
    *,
    runtime_session_id: str | None = None,
    invocation_id: str | None = None,
    execution_mode: str | None = None,
) -> RuntimeResponse:
    _require_model_environment()
    tracing_mode = resolve_tracing_mode()
    tracing_config = _configure_tracing(tracing_mode)
    try:
        resolved_execution_mode = resolve_execution_mode(execution_mode)
        trace_metadata = {
            "cookbook": "chatgpt-agents-sdk-aws-agentcore",
            "execution_mode": resolved_execution_mode,
            "action": request.action,
            "tracing_mode": tracing_mode,
        }
        if runtime_session_id:
            trace_metadata["runtime_session_id"] = runtime_session_id
        if invocation_id:
            trace_metadata["mcp_invocation_id"] = invocation_id
        result = Runner.run_sync(
            build_agent(request, resolved_execution_mode, model=build_bedrock_model()),
            f"Run the selected cookbook action: {request.action}",
            max_turns=1,
            run_config=RunConfig(
                tracing_disabled=False,
                tracing=tracing_config,
                trace_include_sensitive_data=_environment_flag(TRACE_INCLUDE_SENSITIVE_DATA_ENV),
                workflow_name=trace_workflow_name(resolved_execution_mode),
                group_id=runtime_session_id,
                trace_metadata=trace_metadata,
            ),
        )
    finally:
        # The local worker exits after the request, and an optional AgentCore
        # worker may freeze. Drain both exporters before either can happen.
        _flush_trace_destinations()
    response = RuntimeResponse.model_validate(result.final_output)
    if response.executionMode != resolved_execution_mode:
        raise RuntimeError("Agent output executionMode does not match the selected route")
    return response


def handler(
    event: dict[str, Any],
    context: RuntimeContext | None = None,
) -> dict[str, object]:
    try:
        event_payload = _event_payload(event)
        request = parse_event(event)
        explicit_execution_mode = str(event_payload.get("execution_mode") or "").strip() or None
        if os.environ.get("COOKBOOK_FORCE_LOCAL_TOOLS", "0") == "1":
            result = run_deterministic(
                request,
                execution_mode=resolve_execution_mode(explicit_execution_mode),
            )
        else:
            result = run_with_agents_sdk(
                request,
                runtime_session_id=context.session_id if context else None,
                invocation_id=str(event_payload.get("invocation_id") or "").strip() or None,
                execution_mode=explicit_execution_mode,
            )
    except (json.JSONDecodeError, RuntimeError, ValidationError, ValueError) as exc:
        return {"statusCode": 400, "body": json.dumps({"error": str(exc)})}
    return {"statusCode": 200, "body": result.model_dump_json()}


if __name__ == "__main__":
    print(handler(json.loads(os.environ.get("COOKBOOK_EVENT", "{}")))["body"])
