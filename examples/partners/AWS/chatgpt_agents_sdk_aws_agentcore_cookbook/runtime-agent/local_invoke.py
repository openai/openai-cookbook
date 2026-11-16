from __future__ import annotations

import json
import sys
from typing import Any

from opentelemetry import baggage
from opentelemetry import context as otel_context

from agent import run_with_agents_sdk
from schemas import RuntimeRequest

LOCAL_RESULT_PREFIX = "COOKBOOK_LOCAL_AGENT_RESULT="


def invoke_local(payload: dict[str, Any]) -> dict[str, object]:
    request = RuntimeRequest.model_validate(payload.get("request"))
    runtime_session_id = str(payload.get("runtime_session_id") or "").strip() or None
    invocation_id = str(payload.get("invocation_id") or "").strip() or None
    execution_mode = str(payload.get("execution_mode") or "").strip() or None
    token = None
    if runtime_session_id:
        trace_context = baggage.set_baggage("session.id", runtime_session_id)
        if invocation_id:
            trace_context = baggage.set_baggage(
                "mcp.invocation.id", invocation_id, context=trace_context
            )
        token = otel_context.attach(trace_context)
    try:
        result = run_with_agents_sdk(
            request,
            runtime_session_id=runtime_session_id,
            invocation_id=invocation_id,
            execution_mode=execution_mode,
        )
    finally:
        if token is not None:
            otel_context.detach(token)

    response = result.model_dump()
    if runtime_session_id:
        response["trace"] = {
            "runtimeSessionId": runtime_session_id,
            **({"invocationId": invocation_id} if invocation_id else {}),
        }
    return response


def main() -> int:
    payload = json.load(sys.stdin)
    print(f"{LOCAL_RESULT_PREFIX}{json.dumps(invoke_local(payload), separators=(',', ':'))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
