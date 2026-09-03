from __future__ import annotations

from opentelemetry import baggage

import local_invoke
from agent import run_deterministic
from schemas import RuntimeRequest


def test_local_invocation_correlates_and_returns_the_agent_result(monkeypatch) -> None:
    observed: dict[str, object] = {}

    def fake_run(
        request: RuntimeRequest,
        *,
        runtime_session_id: str | None = None,
        invocation_id: str | None = None,
        execution_mode: str | None = None,
    ):
        observed["request"] = request
        observed["runtime_session_id"] = runtime_session_id
        observed["invocation_id"] = invocation_id
        observed["execution_mode"] = execution_mode
        observed["baggage_session_id"] = baggage.get_baggage("session.id")
        observed["baggage_invocation_id"] = baggage.get_baggage("mcp.invocation.id")
        return run_deterministic(request)

    monkeypatch.setattr(local_invoke, "run_with_agents_sdk", fake_run)

    result = local_invoke.invoke_local(
        {
            "request": {"action": "get_live_status", "flight_number": "ELZ1628"},
            "runtime_session_id": "chatgpt-session-123",
            "invocation_id": "mcp-invocation-456",
            "execution_mode": "local",
        }
    )

    assert result["action"] == "get_live_status"
    assert result["executionMode"] == "local"
    assert result["trace"] == {
        "runtimeSessionId": "chatgpt-session-123",
        "invocationId": "mcp-invocation-456",
    }
    assert observed["runtime_session_id"] == "chatgpt-session-123"
    assert observed["invocation_id"] == "mcp-invocation-456"
    assert observed["execution_mode"] == "local"
    assert observed["baggage_session_id"] == "chatgpt-session-123"
    assert observed["baggage_invocation_id"] == "mcp-invocation-456"
