"""Use existing CRAWL graders and transport fixtures with the verification example."""

from __future__ import annotations

import copy
import json
import socket
from pathlib import Path
from typing import Any

import openai
import pytest

from assistants.examples.verification.application import VerificationTools
from assistants.examples.verification.resources import load_scenarios
from shared.observability.timeline import Timeline
from shared.scenarios import Scenario
from shared.single_turn.grading import apply_semantic_grades, grade_single_turn_example, unassessed_semantic_dimensions
from shared.single_turn.types import SingleTurnEvalResult
from shared.testing.live import OfflineLiveConnection


@pytest.fixture
def scenarios() -> dict[str, Scenario]:
    return {row.id: row for row in load_scenarios()}


def observed_grade(
    scenario: Scenario,
    *,
    calls: list[dict[str, Any]],
    executions: list[dict[str, Any]],
    final_state: dict[str, Any],
    delegated: bool = True,
    reply: str = "The requested check is complete.",
):
    timeline = Timeline()
    timeline.add_user_utterance(0, 100, scenario.input.text, action="OPENING")
    delegations = [{"id": "delegation-observed"}] if delegated else []
    if delegated:
        timeline.apply_event(
            {
                "type": "session.delegation.created",
                "offset_ms": 150,
                "delegation": {"id": "delegation-observed", "target": "responses", "response_id": "response-observed"},
            }
        )
    for index, execution in enumerate(executions):
        timeline.apply_event(
            {
                "type": "tool.completed",
                "offset_ms": 200 + index * 50,
                "call_id": execution["call_id"],
                "name": execution["name"],
                "arguments": execution["arguments"],
                "result": execution["output"],
            }
        )
    if reply:
        timeline.add_transcript("assistant", 600, 900, reply, "turn.done")
    return grade_single_turn_example(
        scenario,
        calls,
        timeline,
        interaction_metrics={"response_latencies_ms": [500], "yield_latencies_ms": []},
        turn_metrics=[],
        user_audio_ms=100,
        run_name="verification-grader-test",
        tts_model="offline",
        offline=True,
        tool_executions=executions,
        initial_state=scenario.application.initial_state,
        final_state=final_state,
        delegations=delegations,
        post_tool_assistant_text=reply,
    )


def execute(scenario: Scenario, name: str, arguments: dict[str, Any], *, record: str = "1990-09-05"):
    application = VerificationTools(scenario.application.initial_state, record=record)
    application.execute(name, arguments, call_id="call-observed")
    call = {"call_id": "call-observed", "name": name, "arguments": arguments}
    return application, call


def test_correct_negative_verification_is_a_valid_tool_and_state_outcome(scenarios: dict[str, Scenario]) -> None:
    scenario = scenarios["dob_mismatch"]
    application, call = execute(scenario, "verify_date_of_birth", {"date_of_birth": "1992-09-01"})
    grade = observed_grade(
        scenario,
        calls=[call],
        executions=application.executions,
        final_state=application.snapshot(),
        reply="That date did not match the record. Please check it and try again.",
    )

    assert application.executions[0]["output"]["matched"] is False
    assert grade.tool_call.grade == 1
    assert grade.dimension_grades["tool_execution"].passed is True
    assert grade.dimension_grades["final_state"].passed is True
    assert grade.source_result.task_metrics["task_completed"] is True
    checks = grade.source_result.task_metrics["outcome_assessment"]["checks"]
    assert next(check for check in checks if check["id"] == "semantic_outcome")["status"] == "not_assessed"


def test_delegation_and_requested_call_do_not_establish_execution(scenarios: dict[str, Scenario]) -> None:
    scenario = scenarios["dob_match"]
    grade = observed_grade(
        scenario,
        calls=[{"call_id": "pending", "name": "verify_date_of_birth", "arguments": {"date_of_birth": "1990-09-05"}}],
        executions=[],
        final_state=scenario.application.initial_state,
    )

    assert grade.dimension_grades["delegation_decision"].passed is True
    assert grade.dimension_grades["tool_selection"].passed is True
    assert grade.dimension_grades["tool_execution"].status == "failed"
    assert grade.source_result.task_metrics["task_completed"] is False
    assert unassessed_semantic_dimensions(scenario)["task_understanding"].status == "not_assessed"


def test_wrong_date_is_rejected_even_when_the_expected_tool_runs(scenarios: dict[str, Scenario]) -> None:
    scenario = scenarios["dob_correction"]
    application, call = execute(scenario, "verify_date_of_birth", {"date_of_birth": "1990-09-05"}, record="1992-09-01")
    grade = observed_grade(
        scenario,
        calls=[call],
        executions=application.executions,
        final_state=application.snapshot(),
    )

    assert grade.dimension_grades["tool_selection"].passed is True
    assert grade.dimension_grades["parameter_accuracy"].passed is False
    assert grade.source_result.task_metrics["task_completed"] is False


@pytest.mark.parametrize("case_id", ["no_person_request", "person_request_canceled"])
def test_unrequested_transfer_fails_action_grades_even_when_delegation_is_optional(
    scenarios: dict[str, Scenario],
    case_id: str,
) -> None:
    scenario = scenarios[case_id]
    application, call = execute(scenario, "transfer_to_human", {"reason": "Transfer requested."})
    grade = observed_grade(
        scenario,
        calls=[call],
        executions=application.executions,
        final_state=application.snapshot(),
    )

    assert grade.dimension_grades["delegation_decision"].passed is True
    assert grade.dimension_grades["tool_selection"].passed is False
    assert grade.dimension_grades["final_state"].passed is False
    assert grade.source_result.task_metrics["task_completed"] is False


def test_duplicate_invocation_is_rejected_even_when_transfer_effect_is_idempotent(
    scenarios: dict[str, Scenario],
) -> None:
    scenario = scenarios["person_requested"]
    arguments = {"reason": "Caller requested a human."}
    application, call = execute(scenario, "transfer_to_human", arguments)
    application.execute("transfer_to_human", arguments, call_id="second-call")
    grade = observed_grade(
        scenario,
        calls=[call, {**call, "call_id": "second-call"}],
        executions=application.executions,
        final_state=application.snapshot(),
    )

    assert application.snapshot()["transfer_count"] == 1
    assert grade.dimension_grades["final_state"].passed is True
    assert grade.dimension_grades["tool_execution"].passed is False
    assert grade.source_result.task_metrics["task_completed"] is False


def test_correct_tool_cannot_compensate_for_wrong_final_state(scenarios: dict[str, Scenario]) -> None:
    scenario = scenarios["dob_match"]
    application, call = execute(scenario, "verify_date_of_birth", {"date_of_birth": "1990-09-05"})
    grade = observed_grade(
        scenario,
        calls=[call],
        executions=application.executions,
        final_state={**application.snapshot(), "verified": False},
    )

    assert grade.dimension_grades["tool_execution"].passed is True
    assert grade.dimension_grades["final_state"].passed is False
    assert grade.source_result.task_metrics["task_completed"] is False


def test_post_tool_speech_presence_and_semantic_truth_are_separate_grades(scenarios: dict[str, Scenario]) -> None:
    scenario = scenarios["dob_mismatch"]
    application, call = execute(scenario, "verify_date_of_birth", {"date_of_birth": "1992-09-01"})
    grade = observed_grade(
        scenario,
        calls=[call],
        executions=application.executions,
        final_state=application.snapshot(),
        reply="Your identity is verified.",
    )

    assert grade.dimension_grades["grounded_relay_order"].passed is True
    assert unassessed_semantic_dimensions(scenario)["grounded_communication"].status == "not_assessed"
    # Supplied labels exercise aggregation, not a semantic judge or grounding-only gating.
    apply_semantic_grades(
        grade.source_result,
        {
            "task_understanding": {"status": "failed", "score": 0.0},
            "grounded_communication": {"status": "failed", "score": 0.0},
        },
    )
    assert grade.source_result.task_metrics["semantic_task_completed"] is False
    assert grade.source_result.task_metrics["task_completed"] is False


async def test_eight_examples_use_native_offline_harness_and_keep_startup_private(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    scenarios: dict[str, Scenario],
) -> None:
    from assistants.examples.verification import __main__ as example

    assert set(scenarios) == {
        "dob_match",
        "dob_mismatch",
        "dob_incomplete",
        "dob_correction",
        "person_requested",
        "no_person_request",
        "person_request_canceled",
        "person_transfer_failure",
    }
    selected = [scenario.model_copy(deep=True) for scenario in scenarios.values()]
    markers = {scenario.id: f"EVALUATOR_ONLY_{scenario.id}_7f2e" for scenario in selected}
    for scenario in selected:
        scenario.expected.answer = markers[scenario.id]
    monkeypatch.setattr(example, "load_scenarios", lambda: selected)
    for name in ("OPENAI_API_KEY", "OPENAI_RESPONSES_API_KEY"):
        monkeypatch.delenv(name, raising=False)

    def unexpected_external_operation(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Offline verification examples must not instantiate API clients or connect to a socket")

    monkeypatch.setattr(socket.socket, "connect", unexpected_external_operation)
    monkeypatch.setattr(openai.OpenAI, "__init__", unexpected_external_operation)
    monkeypatch.setattr(openai.AsyncOpenAI, "__init__", unexpected_external_operation)
    starts: dict[str, dict[str, Any]] = {}
    original_send = OfflineLiveConnection.send_json

    async def capture_start(connection: OfflineLiveConnection, payload: dict[str, Any]) -> None:
        if payload.get("type") == "session.start":
            assert connection.example_id not in starts
            starts[connection.example_id] = copy.deepcopy(payload)
        await original_send(connection, payload)

    monkeypatch.setattr(OfflineLiveConnection, "send_json", capture_start)
    out = tmp_path / "verification-run"
    results = await example.run_examples(out)

    assert len(results) == len(starts) == 8
    for result in results:
        assert isinstance(result, SingleTurnEvalResult)
        assert result.error_info.status == "ok"
        assert result.assessment["passed"] is True
        assert result.final_state == {
            **scenarios[result.example_id].application.initial_state,
            **scenarios[result.example_id].expected.state,
        }
        assert result.semantic_grades
        assert all(grade["status"] in {"not_assessed", "not_applicable"} for grade in result.semantic_grades.values())
        assert result.semantic_grades["task_understanding"]["status"] == "not_assessed"
        assert result.artifact_paths.input_audio_path.is_file()
        assert result.artifact_paths.output_audio_path and result.artifact_paths.output_audio_path.is_file()
        assert result.artifact_paths.event_log_path.is_file()
        assert result.artifact_paths.transcript_path and result.artifact_paths.transcript_path.is_file()
        wire = json.dumps(starts[result.example_id])
        for private_value in (*markers.values(), "1990-09-05", "1992-09-01"):
            assert private_value not in wire
        assert '"expected"' not in wire
    report = json.loads((out / "results.json").read_text())
    assert report["summary"] == {"total": 8, "passed": 8, "failed": 0, "infrastructure_errors": 0}
    failure = next(result for result in results if result.example_id == "person_transfer_failure")
    assert failure.tool_executions[0]["status"] == "completed"
    assert failure.tool_executions[0]["output"]["ok"] is False
    assert failure.final_state["transferred"] is False
