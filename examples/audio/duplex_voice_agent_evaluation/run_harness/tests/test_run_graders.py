from types import SimpleNamespace

import pytest

from run_harness.evaluate import result_row
from run_harness.graders import RUBRIC_VERSION, RUBRICS, apply_semantic_completion, judge_result
from run_harness.simulation.models import Scenario
from shared.grading.scoring import build_result
from shared.grading.semantic import SEMANTIC_JUDGE_SYSTEM_PROMPT
from shared.observability.timeline import Timeline


class FakeResponses:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.metric_calls: dict[str, int] = {}

    async def parse(self, **kwargs):
        self.calls.append(kwargs)
        prompt = kwargs["input"][1]["content"]
        metric = next(name for name in RUBRICS if f"RUBRIC: {name}\n" in prompt)
        self.metric_calls[metric] = self.metric_calls.get(metric, 0) + 1
        score = {
            "task_understanding": 1.0,
            "context_fidelity": 0.75 if self.metric_calls[metric] % 2 else 1.0,
            "clarification_quality": 0.5,
            "grounded_communication": 0.75,
            "conversational_coherence": 0.75,
        }[metric]
        parsed = kwargs["text_format"](
            passed=True,
            score=score,
            rationale=f"{metric} rationale",
            task_completed=True if metric == "task_understanding" else None,
        )
        usage = SimpleNamespace(model_dump=lambda **_: {"input_tokens": 10, "output_tokens": 4})
        return SimpleNamespace(output_parsed=parsed, usage=usage)


class FakeClient:
    def __init__(self) -> None:
        self.responses = FakeResponses()


@pytest.mark.asyncio
async def test_rubric_judge_scores_each_dimension_independently_and_averages_samples() -> None:
    scenario = Scenario(
        id="faq",
        title="FAQ",
        interaction="multi_turn",
        input={"text": "when are you open?"},
        expected={
            "answer": "We are open nine to five.",
            "golden_path": {"delegations": 0},
            "criteria": ["give the opening hours"],
            "diagnostic_terms": ["nine to five"],
        },
        simulation_parameters={
            "goal": "learn the opening hours",
            "persona": {"id": "p", "description": "concise caller"},
        },
    )
    timeline = Timeline()
    timeline.add_transcript("assistant", 100, 500, "We're open nine to five.", "evaluation.turn.projected")
    result = build_result(
        scenario,
        timeline,
        caller_mode="offline_fixture",
        caller_actions={"STOP": 1},
        caller_audio_ms=200,
        termination_reason="user_stopped",
    )
    client = FakeClient()

    rubric = await judge_result(
        scenario,
        result,
        model="gpt-5.6-terra",
        reasoning_effort="medium",
        repetitions=2,
        golden={"answer": "Open nine to five.", "total_turns": 3, "tool_calls": [], "steps": "Ask, answer, close."},
        client=client,
    )

    assert rubric["version"] == RUBRIC_VERSION
    assert rubric["judge_model"] == "gpt-5.6-terra"
    assert rubric["reasoning_effort"] == "medium"
    assert rubric["repetitions"] == 2
    assert len(client.responses.calls) == 6
    assert all(call["reasoning"] == {"effort": "medium"} and call["store"] is False for call in client.responses.calls)
    assert all(
        '"golden_path": {"answer": "Open nine to five."' in call["input"][1]["content"]
        for call in client.responses.calls
    )
    assert all(call["input"][0]["content"].startswith(SEMANTIC_JUDGE_SYSTEM_PROMPT) for call in client.responses.calls)
    assert rubric["conversational_coherence"]["score"] == 0.75
    assert rubric["task_understanding"]["samples"] == [1.0, 1.0]
    assert rubric["context_fidelity"]["samples"] == [0.75, 1.0]
    assert rubric["context_fidelity"]["score"] == 0.875
    assert rubric["conversational_coherence"]["rationales"] == [
        "conversational_coherence rationale",
        "conversational_coherence rationale",
    ]
    assert rubric["task_completion"] == {
        "completed": True,
        "votes": [True, True],
        "rationales": ["task_understanding rationale", "task_understanding rationale"],
    }
    assert rubric["naturalness"]["score"] is None
    assert len(rubric["usage"]) == len(rubric["latencies_ms"]) == 6
    result.rubric_metrics = rubric
    assert result_row(scenario, result, offline=False)["semantic_dimension_scores"] == {
        "task_understanding": 1.0,
        "context_fidelity": 0.875,
        "conversational_coherence": 0.75,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("diagnostic_score", [0.0, 0.25, 0.5, 0.75, 1.0])
async def test_semantic_completion_accepts_equivalent_wording_and_preserves_evidence_diagnostics(
    diagnostic_score: float,
) -> None:
    scenario = Scenario(
        id="faq",
        title="FAQ",
        interaction="multi_turn",
        input={"text": "how do I reset my password?"},
        expected={
            "answer": "Select forgot password, verify the email, and choose a new password.",
            "criteria": ["give three actionable reset steps"],
            "diagnostic_terms": ["forgot password", "verify", "new password"],
        },
        simulation_parameters={
            "goal": "learn the password-reset steps",
            "persona": {"id": "p", "description": "concise caller"},
        },
    )
    timeline = Timeline()
    timeline.add_transcript(
        "assistant",
        100,
        800,
        'Click "Forgot password", open the reset link in your email, and choose a new password.',
        "evaluation.turn.projected",
    )
    result = build_result(
        scenario,
        timeline,
        caller_mode="offline_fixture",
        caller_actions={"STOP": 1},
        caller_audio_ms=200,
        termination_reason="user_stopped",
    )
    assert not result.task_metrics["task_completed"]
    assert result.task_metrics["evidence_coverage"] < 1.0

    rubric = await judge_result(scenario, result, repetitions=1, client=FakeClient())
    for dimension in RUBRICS:
        if dimension in rubric:
            rubric[dimension]["score"] = diagnostic_score
    apply_semantic_completion(result, rubric)

    assert result.task_status == "passed"
    assert result.task_metrics["task_completed"]
    assert result.task_metrics["semantic_task_completed"]
    assert result.task_metrics["semantic_quality"] == diagnostic_score
    assert not result.task_metrics["deterministic_task_completed"]
    assert result.task_metrics["completion_source"] == "llm"
    assert result.task_metrics["evidence_coverage"] < 1.0
    assert result.criteria[0]["status"] == "passed"
    assessment = result.task_metrics["outcome_assessment"]
    assert assessment["passed"] is True
    assert assessment["source"] == "semantic_judge"
    assert next(check for check in assessment["checks"] if check["id"] == "semantic_outcome")["status"] == "passed"


def test_semantic_judge_cannot_override_a_forbidden_delegation() -> None:
    scenario = Scenario(
        id="name_repeat_back",
        title="Repeat the caller's corrected name",
        interaction="single_turn",
        input={"text": "Please repeat the correct spelling back to me."},
        expected={
            "answer": "Maya, spelled M-A-Y-A.",
            "criteria": ["Repeat the name and spelling without delegating."],
            "diagnostic_terms": ["Maya", "M-A-Y-A"],
            "delegation": "forbidden",
        },
    )
    timeline = Timeline()
    timeline.add_transcript("assistant", 100, 500, "Maya, spelled M-A-Y-A.", "evaluation.turn.projected")
    timeline.apply_event(
        {
            "type": "session.delegation.created",
            "offset_ms": 300,
            "delegation": {"target": "responses", "content": [{"type": "input_text", "text": "Verify spelling."}]},
        }
    )
    result = build_result(
        scenario,
        timeline,
        caller_mode="offline_fixture",
        caller_actions={"STOP": 1},
        caller_audio_ms=200,
        termination_reason="user_stopped",
    )

    apply_semantic_completion(result, {"task_completion": {"completed": True}})

    assert result.task_status == "incomplete"
    assert result.task_metrics["semantic_task_completed"] is True
    assert result.task_metrics["delegation_prohibited"] is True
    assert result.task_metrics["delegation_observed"] is True
    assert result.task_metrics["task_completed"] is False
    assert (
        next(
            check for check in result.task_metrics["outcome_assessment"]["checks"] if check["id"] == "delegation_policy"
        )["status"]
        == "failed"
    )


@pytest.mark.asyncio
async def test_semantic_judge_accepts_correct_name_spelling() -> None:
    scenario = Scenario(
        id="name_repeat_back",
        title="Repeat the caller's corrected name",
        interaction="single_turn",
        input={"text": "My name is Maya, not Mia. Please repeat the spelling back to me."},
        expected={
            "answer": "Maya, spelled M-A-Y-A, not Mia.",
            "criteria": ["Repeat the corrected name and spelling without using a tool."],
            "diagnostic_terms": ["Maya", "M-A-Y-A"],
            "delegation": "forbidden",
        },
    )
    timeline = Timeline()
    timeline.add_transcript(
        "assistant",
        100,
        800,
        "Got it. Your name is Maya, not Mia.",
        "evaluation.turn.projected",
    )
    timeline.add_transcript(
        "assistant",
        900,
        1_300,
        "That's Maya, spelled M-A-Y-A.",
        "evaluation.turn.projected",
    )
    result = build_result(
        scenario,
        timeline,
        caller_mode="offline_fixture",
        caller_actions={"STOP": 1},
        caller_audio_ms=200,
        termination_reason="user_stopped",
    )
    client = FakeClient()

    rubric = await judge_result(scenario, result, repetitions=1, client=client)
    apply_semantic_completion(result, rubric)

    assert result.task_status == "passed"
    assert result.task_metrics["semantic_task_completed"] is True
    assert result.task_metrics["delegation_observed"] is False
    assert all(
        "conversational acknowledgements" in call["input"][0]["content"]
        and "external system update" in call["input"][0]["content"]
        for call in client.responses.calls
    )


@pytest.mark.asyncio
async def test_rubric_judge_rejects_zero_repetitions() -> None:
    scenario = Scenario(
        id="faq",
        title="FAQ",
        interaction="multi_turn",
        input={"text": "when are you open?"},
        expected={"answer": "We are open nine to five.", "criteria": ["give the opening hours"]},
        simulation_parameters={
            "goal": "learn the opening hours",
            "persona": {"id": "p", "description": "concise caller"},
        },
    )
    result = build_result(scenario, Timeline(), caller_mode="offline_fixture", termination_reason="timeout")

    with pytest.raises(ValueError, match="at least 1"):
        await judge_result(scenario, result, repetitions=0, client=FakeClient())
