from __future__ import annotations

import json
from typing import Any

from bedrock_agentcore import BedrockAgentCoreApp
from bedrock_agentcore.runtime.context import RequestContext
from opentelemetry import baggage
from opentelemetry import context as otel_context

from agent import handler

app = BedrockAgentCoreApp()


@app.entrypoint
def invoke(payload: dict[str, Any], context: RequestContext) -> dict[str, object]:
    """Adapt the tested cookbook handler to the AgentCore Runtime contract."""
    token = None
    if context.session_id:
        trace_context = baggage.set_baggage("session.id", context.session_id)
        invocation_id = str(payload.get("invocation_id") or "").strip()
        if invocation_id:
            trace_context = baggage.set_baggage(
                "mcp.invocation.id", invocation_id, context=trace_context
            )
        token = otel_context.attach(trace_context)
    try:
        if isinstance(payload.get("request"), dict):
            runtime_payload = {
                **payload,
                "execution_mode": "deployed",
            }
        else:
            runtime_payload = {
                "request": payload,
                "execution_mode": "deployed",
            }
        response = handler(runtime_payload, context)
    finally:
        if token is not None:
            otel_context.detach(token)
    body = json.loads(str(response["body"]))
    if response["statusCode"] != 200:
        return {"error": str(body.get("error", "Invalid request"))}
    if not isinstance(body, dict):
        raise TypeError("Runtime handler must return a JSON object")
    return body


if __name__ == "__main__":
    app.run()
