from __future__ import annotations

from typing import Any, cast

from bedrock_agentcore.runtime.context import RequestContext
from opentelemetry import baggage

import runtime as runtime_module
from runtime import invoke


def test_agentcore_entrypoint_returns_runtime_payload(monkeypatch) -> None:
    monkeypatch.setenv("COOKBOOK_FORCE_LOCAL_TOOLS", "1")

    result = invoke(
        {"action": "get_live_status", "flight_number": "ELZ1628"},
        RequestContext(
            session_id="runtime-session-123",
            request_headers={},
            request={},
        ),
    )

    assert result["provider"] == "agentcore-runtime"
    assert result["executionMode"] == "deployed"
    assert result["action"] == "get_live_status"
    data = cast(dict[str, Any], result["data"])
    assert data["flight"]["flightNumber"] == "ELZ1628"


def test_agentcore_entrypoint_search_matches_deployed_adapter_contract(monkeypatch) -> None:
    monkeypatch.setenv("COOKBOOK_FORCE_LOCAL_TOOLS", "1")

    result = invoke(
        {
            "action": "search_flights",
            "origin": "DAL",
            "destination": "MDW",
            "travel_date": "2099-09-21",
        },
        RequestContext(
            session_id="runtime-session-123",
            request_headers={},
            request={},
        ),
    )

    assert result["provider"] == "agentcore-runtime"
    assert result["executionMode"] == "deployed"
    assert result["action"] == "search_flights"
    data = cast(dict[str, Any], result["data"])
    flights = cast(list[dict[str, object]], data["flights"])
    assert [flight["flightNumber"] for flight in flights] == ["ELZ1234", "ELZ1458"]
    for flight in flights:
        assert str(flight["flightNumber"]).startswith("ELZ")
        assert flight["travelDate"] == "2099-09-21"


def test_agentcore_entrypoint_returns_safe_validation_error(monkeypatch) -> None:
    monkeypatch.setenv("COOKBOOK_FORCE_LOCAL_TOOLS", "1")

    result = invoke(
        {"action": "search_flights", "origin": "DAL"},
        RequestContext(
            session_id="runtime-session-123",
            request_headers={},
            request={},
        ),
    )

    assert "search_flights is missing" in str(result["error"])


def test_agentcore_entrypoint_marks_unlabeled_requests_as_deployed(monkeypatch) -> None:
    observed: dict[str, object] = {}

    def fake_handler(payload: dict[str, object], _context: object) -> dict[str, object]:
        observed.update(payload)
        return {
            "statusCode": 200,
            "body": '{"provider":"agentcore-runtime","executionMode":"deployed"}',
        }

    monkeypatch.setattr(runtime_module, "handler", fake_handler)
    result = runtime_module.invoke(
        {"action": "get_upcoming_status"},
        RequestContext(session_id="runtime-session-123", request_headers={}, request={}),
    )

    assert observed["execution_mode"] == "deployed"
    assert result["provider"] == "agentcore-runtime"
    assert result["executionMode"] == "deployed"


def test_agentcore_entrypoint_overrides_enveloped_execution_mode(monkeypatch) -> None:
    observed: dict[str, object] = {}

    def fake_handler(payload: dict[str, object], _context: object) -> dict[str, object]:
        observed.update(payload)
        return {
            "statusCode": 200,
            "body": '{"provider":"agentcore-runtime","executionMode":"deployed"}',
        }

    monkeypatch.setattr(runtime_module, "handler", fake_handler)
    result = runtime_module.invoke(
        {
            "request": {"action": "get_upcoming_status"},
            "execution_mode": "local",
        },
        RequestContext(session_id="runtime-session-123", request_headers={}, request={}),
    )

    assert observed["execution_mode"] == "deployed"
    assert result["provider"] == "agentcore-runtime"
    assert result["executionMode"] == "deployed"


def test_agentcore_entrypoint_preserves_invocation_metadata_and_baggage(monkeypatch) -> None:
    observed: dict[str, object] = {}

    def fake_handler(payload: dict[str, object], context: RequestContext) -> dict[str, object]:
        observed.update(payload)
        observed["session_id"] = context.session_id
        observed["baggage_session_id"] = baggage.get_baggage("session.id")
        observed["baggage_invocation_id"] = baggage.get_baggage("mcp.invocation.id")
        return {"statusCode": 200, "body": '{"executionMode":"deployed"}'}

    monkeypatch.setattr(runtime_module, "handler", fake_handler)
    previous_session = baggage.get_baggage("session.id")
    previous_invocation = baggage.get_baggage("mcp.invocation.id")
    runtime_module.invoke(
        {
            "request": {"action": "get_upcoming_status"},
            "execution_mode": "deployed",
            "invocation_id": "runtime-invocation-456",
        },
        RequestContext(session_id="runtime-session-123", request_headers={}, request={}),
    )

    assert observed["invocation_id"] == "runtime-invocation-456"
    assert observed["baggage_invocation_id"] == "runtime-invocation-456"
    assert observed["session_id"] == "runtime-session-123"
    assert observed["baggage_session_id"] == "runtime-session-123"
    assert baggage.get_baggage("session.id") == previous_session
    assert baggage.get_baggage("mcp.invocation.id") == previous_invocation
