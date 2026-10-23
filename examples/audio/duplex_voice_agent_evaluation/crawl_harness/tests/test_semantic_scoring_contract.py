"""Raw judge classifications are discrete; report scores and outcomes are not."""

import json

import pytest
from openai.lib._parsing._responses import type_to_text_format_param
from pydantic import ValidationError

from run_harness.graders import RubricScore
from shared.grading.semantic import (
    RUBRIC_VERSION,
    SEMANTIC_JUDGE_SYSTEM_PROMPT,
    SEMANTIC_RUBRICS,
    SEMANTIC_SCORES,
    SemanticJudgeDecision,
)


@pytest.mark.parametrize("decision_type", [SemanticJudgeDecision, RubricScore])
@pytest.mark.parametrize("score", [0, 0.25, 0.5, 0.75, 1])
def test_raw_scores_accept_and_serialize_only_numeric_quarter_points(decision_type, score) -> None:
    data = {"passed": False, "score": score, "rationale": "Observed a shortcoming."}
    for decision in (decision_type(**data), decision_type.model_validate_json(json.dumps(data))):
        assert type(decision.score) is float
        assert decision.score == score
        assert json.loads(decision.model_dump_json())["score"] == score
        assert decision.passed is False
        assert decision.task_completed is None


@pytest.mark.parametrize("decision_type", [SemanticJudgeDecision, RubricScore])
@pytest.mark.parametrize(
    "score",
    [-0.25, 1.25, 0.1, 0.49, 0.7, 0.82, 0.99, float("nan"), float("inf"), -float("inf"), True, False, "0.75", None],
)
def test_raw_scores_reject_invalid_values_without_rounding(decision_type, score) -> None:
    data = {"passed": True, "score": score, "rationale": "Judge response."}
    with pytest.raises(ValidationError):
        decision_type(**data)
    with pytest.raises(ValidationError):
        decision_type.model_validate_json(json.dumps(data))


@pytest.mark.parametrize("decision_type", [SemanticJudgeDecision, RubricScore])
def test_sdk_response_schema_exposes_the_same_numeric_enum(decision_type) -> None:
    response_format = type_to_text_format_param(decision_type)
    assert response_format["type"] == "json_schema"
    assert response_format["strict"] is True
    score_schema = response_format["schema"]["properties"]["score"]
    assert score_schema["type"] == "number"
    assert score_schema["enum"] == list(SEMANTIC_SCORES)
    assert SEMANTIC_SCORES == (0.0, 0.25, 0.5, 0.75, 1.0)


def test_scoring_prompt_has_five_anchors_and_preserves_existing_protections() -> None:
    assert RUBRIC_VERSION == "voice-semantic-v2"
    assert "exactly 0, 0.25, 0.5, 0.75, or 1" in SEMANTIC_JUDGE_SYSTEM_PROMPT
    for anchor in (
        "Use 1 for fully satisfied",
        "Use 0.75 for mostly satisfied",
        "Use 0.5 for partially satisfied",
        "Use 0.25 for minimally satisfied",
        "Use 0 for wholly incorrect, fabricated, or unsafe behavior",
    ):
        assert anchor in SEMANTIC_JUDGE_SYSTEM_PROMPT
    assert "intermediate values reflect" not in SEMANTIC_JUDGE_SYSTEM_PROMPT
    assert "never overrides the separate binary task-completion decision" in SEMANTIC_JUDGE_SYSTEM_PROMPT
    assert "Mark passed only when the dimension's required behavior is satisfied" in SEMANTIC_JUDGE_SYSTEM_PROMPT
    assert "Do not assume unobserved tool executions" in SEMANTIC_JUDGE_SYSTEM_PROMPT
    assert "specific supporting evidence" in SEMANTIC_JUDGE_SYSTEM_PROMPT


def test_all_five_rubric_definitions_remain_unchanged_from_v1() -> None:
    assert SEMANTIC_RUBRICS == {
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
