from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import trace_smoke


def test_compatibility_launcher_uses_the_selected_route_entrypoint(monkeypatch) -> None:
    calls: list[tuple[list[str], bool]] = []
    monkeypatch.setattr(Path, "is_file", lambda _: True)

    def fake_run(command: list[str], *, check: bool) -> SimpleNamespace:
        calls.append((command, check))
        return SimpleNamespace(returncode=7)

    monkeypatch.setattr(trace_smoke.subprocess, "run", fake_run)

    assert trace_smoke.main() == 7
    repository = Path(trace_smoke.__file__).resolve().parents[1]
    assert calls == [
        (
            [
                "node",
                f"--env-file={repository / '.env'}",
                str(repository / "mcp-adapter" / "dist" / "trace-smoke.js"),
            ],
            False,
        )
    ]


def test_compatibility_launcher_explains_the_build_prerequisite(monkeypatch, capsys) -> None:
    monkeypatch.setattr(Path, "is_file", lambda _: False)

    assert trace_smoke.main() == 2
    assert "npm --prefix mcp-adapter run build" in capsys.readouterr().err


def test_instrumented_local_invocation_exports_correlated_agent_spans() -> None:
    # Isolate the process-global SDK providers, use the real Runner/ADOT bridge,
    # and replace only inference and delivery. No AWS or OpenAI network call is allowed.
    code = """
import json
import socket
from unittest.mock import patch

from agents.items import ModelResponse
from agents.models.interface import Model
from agents.usage import Usage
from openai.types.responses import ResponseFunctionToolCall
from opentelemetry import baggage, trace
from opentelemetry.processor.baggage import BaggageSpanProcessor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import agent
import local_invoke

class OfflineModel(Model):
    async def get_response(self, **kwargs):
        assert baggage.get_baggage("session.id") == "cookbook-trace-session"
        assert baggage.get_baggage("mcp.invocation.id") == "cookbook-trace-invocation"
        return ModelResponse(
            output=[ResponseFunctionToolCall(
                id="offline-tool-call", call_id="offline-call", type="function_call",
                name=kwargs["tools"][0].name, arguments="{}",
            )],
            usage=Usage(requests=1),
            response_id=None,
        )

    def stream_response(self, **kwargs):
        raise AssertionError("Unexpected streaming request")

network_attempts = []
def deny_network(*args, **kwargs):
    network_attempts.append("blocked")
    raise AssertionError("Network is forbidden in this test")

def deny_openai_exporter():
    raise AssertionError("AWS-only must not initialize an OpenAI exporter")

provider = TracerProvider()
exporter = InMemorySpanExporter()
# ADOT enables this processor for session.id when AGENT_OBSERVABILITY_ENABLED=true.
provider.add_span_processor(BaggageSpanProcessor(lambda key: key == "session.id"))
provider.add_span_processor(SimpleSpanProcessor(exporter))
trace.set_tracer_provider(provider)
with patch.object(socket.socket, "connect", deny_network), \
     patch.object(socket, "create_connection", deny_network), \
     patch.object(agent, "build_bedrock_model", lambda: OfflineModel()), \
     patch.object(agent, "default_processor", deny_openai_exporter):
    result = local_invoke.invoke_local({
        "request": {"action": "get_live_status", "flight_number": "ELZ1628"},
        "runtime_session_id": "cookbook-trace-session",
        "invocation_id": "cookbook-trace-invocation",
        "execution_mode": "local",
    })

spans = exporter.get_finished_spans()
assert spans, "The SDK/ADOT bridge exported no spans"
assert any("tool" in span.name.lower() for span in spans), [span.name for span in spans]
assert all(span.attributes.get("session.id") == "cookbook-trace-session" for span in spans)
assert not network_attempts, network_attempts
assert baggage.get_baggage("session.id") is None
assert baggage.get_baggage("mcp.invocation.id") is None
print(json.dumps({"result": result, "span_count": len(spans)}))
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[1],
        env={
            "AWS_REGION": "us-west-2",
            "AWS_EC2_METADATA_DISABLED": "true",
            "OPENAI_API_KEY": "offline-bedrock-key",
            "OPENAI_BASE_URL": "https://bedrock-mantle.us-west-2.api.aws/v1",
            "COOKBOOK_EXECUTION_MODE": "local",
            "COOKBOOK_TRACING_MODE": "aws",
            "OPENAI_TRACE_INCLUDE_SENSITIVE_DATA": "0",
            "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "false",
        },
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report["span_count"] >= 3
    assert report["result"]["executionMode"] == "local"
    assert report["result"]["trace"] == {
        "runtimeSessionId": "cookbook-trace-session",
        "invocationId": "cookbook-trace-invocation",
    }
