"""One evaluator-owned semantic-quality contract for every voice-evaluation mode."""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

from shared.scenarios import Scenario

RUBRIC_VERSION = "voice-semantic-v2"
SEMANTIC_SCORES = (0.0, 0.25, 0.5, 0.75, 1.0)

SEMANTIC_RUBRICS: dict[str, str] = {
    "task_understanding": (
        "Assess whether the assistant understood and appropriately addressed the caller's actual request, "
        "satisfied the scenario-specific success criteria, and achieved the verified intended outcome. Accept "
        "equivalent wording; do not require the reference answer's exact phrasing."
    ),
    "context_fidelity": (
        "Assess whether the assistant preserved relevant, authorized conversation context and followed "
        "the caller's latest correction without relying on evaluator-only expectations."
    ),
    "clarification_quality": (
        "Assess whether the assistant requested genuinely missing information clearly and appropriately, "
        "without guessing, fabricating details, or initiating unauthorized work."
    ),
    "grounded_communication": (
        "Assess whether the assistant accurately communicated verified business facts, completed tool "
        "outputs, and application outcomes without inventing confirmations, identifiers, or external actions."
    ),
    "conversational_coherence": (
        "Assess whether the assistant maintained a clear, coherent, relevant, appropriately responsive "
        "multi-turn conversation without penalizing simulated-caller behavior or audio fragmentation."
    ),
}


class SemanticJudgeDecision(BaseModel):
    """One independently assessed semantic dimension with severity-aware partial credit."""

    passed: bool
    score: float = Field(strict=True, json_schema_extra={"enum": list(SEMANTIC_SCORES)})
    rationale: str = Field(min_length=1)
    evidence: list[str] = Field(default_factory=list)
    task_completed: bool | None = Field(default=None)

    @field_validator("score")
    @classmethod
    def validate_score(cls, value: float) -> float:
        if value not in SEMANTIC_SCORES:
            raise ValueError("score must be one of 0, 0.25, 0.5, 0.75, or 1")
        return value


def applicable_semantic_dimensions(scenario: Scenario) -> tuple[str, ...]:
    """Select the same semantic dimensions using scenario evidence in every mode."""

    dimensions = ["task_understanding"]
    correction = bool(re.search(r"\b(?:sorry|actually|instead)\b", scenario.input.text, re.IGNORECASE))
    if scenario.input.context is not None or correction or scenario.interaction == "multi_turn":
        dimensions.append("context_fidelity")
    procedure = scenario.expected.procedure
    needs_clarification = scenario.scenario_type == "clarification" or (
        procedure is not None and any(step.kind == "clarification" for step in procedure.steps)
    )
    if needs_clarification:
        dimensions.append("clarification_quality")
    if scenario.expected.tools.required:
        dimensions.append("grounded_communication")
    if scenario.interaction == "multi_turn":
        dimensions.append("conversational_coherence")
    return tuple(dimensions)


SEMANTIC_JUDGE_SYSTEM_PROMPT = (
    "You are an independent voice-agent evaluation judge. Assess only the requested semantic dimension "
    "using the provided scenario-specific criteria and verified evidence. Return an explicit pass or fail "
    "and a severity-aware score of exactly 0, 0.25, 0.5, 0.75, or 1. "
    "Use 1 for fully satisfied: meets the rubric's required behavior; stylistic preferences alone do not "
    "reduce the score. Use 0.75 for mostly satisfied: a small, localized error or omission with limited "
    "impact; the main required behavior remains correct. Use 0.5 for partially satisfied: useful behavior, "
    "but a material error or omission leaves an important requirement unmet. Use 0.25 for minimally "
    "satisfied: limited useful behavior; major errors or omissions leave most requirements unmet. "
    "Use 0 for wholly incorrect, fabricated, or unsafe behavior. Choose one of these five scores directly; "
    "do not return other values. The numeric score never overrides the separate binary task-completion decision or "
    "deterministic authorization and application-state checks. Mark passed only when the dimension's "
    "required behavior is satisfied. Do not assume unobserved tool executions, infer acoustic naturalness "
    "from transcripts, or require an exact match to the reference answer. Include a concise rationale and "
    "specific supporting evidence."
)
