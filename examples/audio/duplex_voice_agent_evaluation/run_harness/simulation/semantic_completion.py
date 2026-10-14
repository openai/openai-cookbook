"""Evaluator-owned semantic observation of natural conversation completion."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Literal

from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field

from shared.observability.timeline import Turn
from shared.scenarios import Scenario


class SemanticCompletionDecision(BaseModel):
    """One grounded, structured decision about whether a conversation should drain."""

    model_config = ConfigDict(extra="forbid")

    should_drain: bool
    outcome: Literal["resolved", "refused", "unresolved"]
    reason: str = Field(min_length=1, max_length=500)


class SemanticCompletionObserver:
    """Observe finalized turns without controlling either live participant."""

    def __init__(self, client: AsyncOpenAI, *, model: str, timeout_seconds: float = 8.0) -> None:
        if not model.strip():
            raise ValueError("A semantic completion observer requires a model")
        if timeout_seconds <= 0:
            raise ValueError("Semantic completion timeout must be positive")
        self.client = client
        # Initialize the SDK's lazy Responses resource before live audio starts.
        _ = self.client.responses
        self.model = model.strip()
        self.timeout_seconds = timeout_seconds
        self.assessments: list[dict[str, Any]] = []
        self.usage: list[dict[str, Any]] = []

    async def assess(
        self,
        scenario: Scenario,
        *,
        turns: list[Turn],
        initial_state: dict[str, Any],
        observed_state: dict[str, Any],
        state_verified: bool,
        tool_executions: list[dict[str, Any]],
        assistant_work_pending: bool,
    ) -> SemanticCompletionDecision:
        """Classify conversational finality from dialogue and evaluator-owned evidence."""
        parameters = scenario.simulation_parameters
        if parameters is None:
            raise ValueError("Semantic completion requires an interactive scenario")
        payload = {
            "caller_goal": parameters.goal,
            "caller_expectations": parameters.expectations,
            "required_caller_objectives": [
                {"commitment": item.commitment, "completion_condition": item.completion_condition}
                for item in parameters.agenda
                if item.required and item.action not in {"finish", "wait"}
            ],
            "expected_application_state": scenario.expected.state,
            "initial_application_state": initial_state,
            "observed_application_state": observed_state,
            "expected_state_verified": state_verified,
            "delegation_forbidden": scenario.expected.forbids_delegation,
            "assistant_work_pending": assistant_work_pending,
            "completed_application_tools": [
                {"name": item.get("name"), "status": item.get("status"), "output": item.get("output")}
                for item in tool_executions
            ],
            "conversation": [
                {"role": turn.role, "text": turn.transcript, "end_ms": turn.end_ms}
                for turn in sorted(turns[-12:], key=lambda item: (item.start_ms, item.end_ms))
            ],
        }
        started = time.perf_counter()
        try:
            async with asyncio.timeout(self.timeout_seconds):
                response = await self.client.responses.parse(
                    model=self.model,
                    input=[
                        {
                            "role": "system",
                            "content": (
                                "You are an independent conversation-completion observer, not a caller, "
                                "assistant, or grader. You do not control either voice participant. "
                                "Decide whether this spoken exchange "
                                "has naturally ended. Return should_drain=true only when the assistant has "
                                "resolved the caller's goal or clearly communicated a terminal refusal, the "
                                "caller semantically indicates that no further help is needed, and no "
                                "assistant work remains pending. Interpret intent in any language and do not "
                                "depend on exact goodbye words. A brief thanks, acknowledgement, or pause "
                                "during an unfinished task is not an ending. Do not accept an unverified "
                                "state-changing success. Informational answers can resolve without state "
                                "changes; authorization refusals can resolve while state remains unchanged. "
                                "If the caller is still challenging a refusal, requesting clarification, "
                                "correcting details, or waiting for a result, return should_drain=false. "
                                "Keep the reason brief and grounded in the observed conversation."
                            ),
                        },
                        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)},
                    ],
                    text_format=SemanticCompletionDecision,
                    text={"verbosity": "low"},
                    reasoning={"effort": "none"},
                    store=False,
                )
        except TimeoutError as exc:
            raise TimeoutError(f"Semantic completion observer timed out after {self.timeout_seconds:g}s") from exc
        decision = response.output_parsed
        if decision is None:
            raise RuntimeError("Semantic completion observer returned no structured decision")
        latency_ms = round((time.perf_counter() - started) * 1_000, 1)
        self.assessments.append({**decision.model_dump(), "latency_ms": latency_ms, "turn_count": len(turns)})
        if response.usage is not None:
            self.usage.append(response.usage.model_dump(exclude_none=True))
        return decision
