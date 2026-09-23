"""No-network scripted model for teaching the Agents SDK tool loop."""

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

from .agent import SupplierResearchOutput


class ScriptedCommerceLearningModel(Model):
    """Request x402_fetch once, then copy its synthetic evidence.

    This is a deterministic test fixture, not an inference engine. It exists
    so learners can run the real Agents SDK Runner loop without credentials,
    paid inference, AWS, AgentCore Payments, a wallet, or value transfer.
    """

    def __init__(self) -> None:
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
                                "resource_url": (
                                    "https://merchant.invalid/reports/"
                                    "SYNTH-SUPPLIER-RISK-001"
                                ),
                                "purpose": "supplier_due_diligence",
                            }
                        ),
                        call_id="learning-x402-call-001",
                        name="x402_fetch",
                        type="function_call",
                        id="learning-x402-item-001",
                        status="completed",
                    )
                ],
                usage=Usage(),
                response_id=None,
            )

        evidence = self._tool_evidence(input)
        report = evidence["report"]
        output = SupplierResearchOutput(
            status=evidence["status"],
            report_id=report["report_id"],
            supplier=report["supplier"],
            signals=tuple(report["signals"]),
            disclaimer=report["disclaimer"],
            receipt_id=evidence["receipt_id"],
            amount=evidence["amount"],
            currency=evidence["currency"],
            requires_human_approval=evidence["requires_human_approval"],
        )
        return ModelResponse(
            output=[
                ResponseOutputMessage(
                    id="learning-final-001",
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
                        "The learning model received an invalid tool output."
                    )
                parsed = json.loads(raw_output)
                if not isinstance(parsed, dict) or parsed.get("status") != "completed":
                    raise RuntimeError("The synthetic purchase did not complete.")
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
            "The local learning model supports non-streaming runs only."
        )
