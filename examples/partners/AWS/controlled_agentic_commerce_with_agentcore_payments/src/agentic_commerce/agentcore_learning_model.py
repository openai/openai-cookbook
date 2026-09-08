"""No-inference model fixture for the AgentCore integration boundary."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from agents import (
    AgentOutputSchemaBase,
    Handoff,
    Model,
    ModelResponse,
    ModelSettings,
    ModelTracing,
    Tool,
    TResponseInputItem,
    Usage,
)
from agents.items import TResponseStreamEvent
from openai.types.responses import (
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
)

from .agentcore_agent import AgentCoreAccessOutput


class ScriptedAgentCoreLearningModel(Model):
    """Request the testnet tool once and copy its sanitized evidence."""

    def __init__(self, *, resource_url: str, purpose: str) -> None:
        self.resource_url = resource_url
        self.purpose = purpose
        self.model_turns = 0
        self.requested_tools: list[str] = []

    async def get_response(
        self,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: AgentOutputSchemaBase | None,
        handoffs: list[Handoff],
        tracing: ModelTracing,
        **kwargs: Any,
    ) -> ModelResponse:
        self.model_turns += 1
        if self.model_turns == 1:
            self.requested_tools.append("x402_fetch")
            return ModelResponse(
                output=[
                    ResponseFunctionToolCall(
                        arguments=json.dumps(
                            {
                                "resource_url": self.resource_url,
                                "purpose": self.purpose,
                            }
                        ),
                        call_id="agentcore-learning-call-001",
                        name="x402_fetch",
                        type="function_call",
                        id="agentcore-learning-item-001",
                        status="completed",
                    )
                ],
                usage=Usage(),
                response_id=None,
            )

        evidence = self._tool_evidence(input)
        output = AgentCoreAccessOutput(**evidence)
        return ModelResponse(
            output=[
                ResponseOutputMessage(
                    id="agentcore-learning-final-001",
                    content=[
                        ResponseOutputText(
                            text=output.model_dump_json(),
                            annotations=[],
                            type="output_text",
                        )
                    ],
                    role="assistant",
                    status="completed",
                    type="message",
                )
            ],
            usage=Usage(),
            response_id=None,
        )

    @staticmethod
    def _tool_evidence(
        input: str | list[TResponseInputItem],
    ) -> dict[str, Any]:
        if isinstance(input, str):
            raise TypeError("The learning model did not receive tool output.")
        for item in reversed(input):
            if isinstance(item, dict) and item.get("type") == "function_call_output":
                raw_output = item.get("output")
                if not isinstance(raw_output, str):
                    raise RuntimeError(
                        "The learning model received invalid tool output."
                    )
                parsed = json.loads(raw_output)
                if not isinstance(parsed, dict) or parsed.get("status") != (
                    "completed"
                ):
                    raise RuntimeError(
                        "The application-controlled access did not complete."
                    )
                return parsed
        raise RuntimeError("The learning model did not receive tool output.")

    def stream_response(
        self,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: AgentOutputSchemaBase | None,
        handoffs: list[Handoff],
        tracing: ModelTracing,
        **kwargs: Any,
    ) -> AsyncIterator[TResponseStreamEvent]:
        raise NotImplementedError(
            "The learning model supports non-streaming runs only."
        )
