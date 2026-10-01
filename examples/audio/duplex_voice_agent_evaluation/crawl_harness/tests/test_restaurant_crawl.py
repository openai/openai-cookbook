"""Deterministic contracts for portable, independently graded CRAWL scenarios."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from assistants.frontend.transport import build_session_update, normalize_live_response_tools
from assistants.resources import assistant_resources
from assistants.responses.tools.restaurant import RestaurantOfflineBehavior, RestaurantToolError, RestaurantTools
from crawl_harness.evaluate import (
    DEFAULT_DATA_JSON,
    RESTAURANT_FACTS_PATH,
    RESTAURANT_TOOLS_PATH,
    _render_authorized_context,
    load_dataset,
    load_system_prompt,
    load_tools,
    parse_args,
    run_evals,
)
from crawl_harness.graders import (
    DEFAULT_JUDGE_MODEL,
    SEMANTIC_RUBRICS,
    SemanticJudgeError,
    applicable_semantic_dimensions,
    build_semantic_judge_input,
    compute_tool_call_grade,
    expected_tool_fields,
    grade_deterministic_dimensions,
    judge_semantic_dimensions,
    unassessed_semantic_dimensions,
    verify_final_state,
)
from shared.observability.timeline import Timeline
from shared.scenarios import Scenario
from shared.single_turn.grading import grade_single_turn_example
from shared.single_turn.types import ToolCallGrade


@pytest.fixture
def restaurant_rows() -> dict[str, Scenario]:
    return {scenario.id: scenario for scenario in load_dataset(DEFAULT_DATA_JSON)}


@pytest.fixture
def restaurant_facts() -> dict[str, object]:
    return json.loads(RESTAURANT_FACTS_PATH.read_text(encoding="utf-8"))


def test_restaurant_dataset_preserves_all_twenty_one_portable_customer_rows(
    restaurant_rows: dict[str, Scenario],
) -> None:
    assert all(scenario.interaction == "single_turn" for scenario in restaurant_rows.values())
    assert list(restaurant_rows) == [f"restaurant_{index:03}" for index in range(1, 22)]
    assert sum(bool(scenario.expected.tools.required) for scenario in restaurant_rows.values()) == 15
    assert sum(scenario.expected.delegation == "forbidden" for scenario in restaurant_rows.values()) == 6
    assert sum(expected_tool_fields(scenario)[0] == "create_reservation" for scenario in restaurant_rows.values()) == 8
    assert sum(expected_tool_fields(scenario)[0] == "check_availability" for scenario in restaurant_rows.values()) == 4
    assert sum(expected_tool_fields(scenario)[0] == "cancel_reservation" for scenario in restaurant_rows.values()) == 3


@pytest.mark.parametrize(
    ("field_path", "value", "message"),
    [
        (("interaction",), "history", "single_turn"),
        (("expected", "delegation"), "maybe", "required"),
        (("application", "initial_state"), [], "object"),
        (("expected", "tools", "required", 0, "arguments"), "not-json", "object"),
        (("expected", "state"), None, "object"),
        (("expected", "answer"), "", "at least 1 character"),
        (("title",), "", "at least 1 character"),
    ],
)
def test_portable_dataset_rejects_invalid_customer_values(
    tmp_path: Path,
    restaurant_rows: dict[str, Scenario],
    field_path: tuple[str | int, ...],
    value: object,
    message: str,
) -> None:
    path = tmp_path / "invalid.json"
    scenario = restaurant_rows["restaurant_001"].model_dump(mode="json")
    parent: object = scenario
    for key in field_path[:-1]:
        assert isinstance(parent, dict | list)
        parent = parent[key]  # type: ignore[index]
    assert isinstance(parent, dict | list)
    parent[field_path[-1]] = value  # type: ignore[index]
    path.write_text(json.dumps({"schema_version": "1.0", "scenarios": [scenario]}), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_dataset(path)


def test_portable_dataset_rejects_missing_summary(
    tmp_path: Path,
    restaurant_rows: dict[str, Scenario],
) -> None:
    path = tmp_path / "missing-context.json"
    scenario = restaurant_rows["restaurant_015"].model_dump(mode="json")
    scenario["input"]["context"] = {"summary": ""}
    path.write_text(json.dumps({"schema_version": "1.0", "scenarios": [scenario]}), encoding="utf-8")

    with pytest.raises(ValueError, match="conversation context requires"):
        load_dataset(path)


def test_restaurant_tools_preserve_alpha_compatible_nullable_optional_parameters() -> None:
    original = load_tools(RESTAURANT_TOOLS_PATH)
    normalized = normalize_live_response_tools(original)

    assert [item["name"] for item in original] == [
        "check_availability",
        "create_reservation",
        "cancel_reservation",
    ]
    assert original[0]["parameters"]["required"] == ["date", "time", "party_size"]
    assert original[1]["parameters"]["required"] == ["guest_name", "date", "time", "party_size"]
    assert normalized[0]["parameters"]["properties"]["seating"]["anyOf"][1] == {"type": "null"}
    assert normalized[1]["parameters"]["properties"]["seating"]["anyOf"][1] == {"type": "null"}


def test_restaurant_availability_is_read_only_and_uses_configured_facts(
    restaurant_facts: dict[str, object],
) -> None:
    executor = RestaurantTools(initial_state={}, facts=restaurant_facts)
    output = executor.execute(
        "check_availability",
        {"date": "2026-08-07", "time": "21:00", "party_size": 6},
        call_id="availability_1",
    )

    assert output == {
        "ok": True,
        "date": "2026-08-07",
        "time": "21:00",
        "party_size": 6,
        "available": False,
    }
    assert executor.snapshot() == {}
    assert executor.executions[0]["status"] == "completed"


@pytest.mark.parametrize("missing", ["guest_name", "time"])
def test_reservation_creation_rejects_missing_required_information(
    restaurant_facts: dict[str, object],
    missing: str,
) -> None:
    executor = RestaurantTools(initial_state={}, facts=restaurant_facts)
    arguments: dict[str, object] = {
        "guest_name": "Maya",
        "date": "2026-08-07",
        "time": "19:00",
        "party_size": 2,
    }
    arguments.pop(missing)

    with pytest.raises(RestaurantToolError, match=missing):
        executor.execute("create_reservation", arguments, call_id="invalid_1")

    assert executor.snapshot() == {}
    assert executor.executions == []


def test_reservation_creation_verifies_application_state_without_sharing_fixtures(
    restaurant_facts: dict[str, object],
) -> None:
    executor = RestaurantTools(initial_state={}, facts=restaurant_facts)
    arguments = {
        "guest_name": "Maya",
        "date": "2026-08-07",
        "time": "19:00",
        "party_size": 2,
    }

    output = executor.execute("create_reservation", arguments, call_id="reservation_1")

    assert output["ok"] is True
    assert output["reservation_created"] is True
    assert output["reservation_id"] == "R-001"
    assert verify_final_state({"reservation_created": True, **arguments}, {}, executor.snapshot())
    assert executor.snapshot()["reservations"][0]["guest_name"] == "Maya"


def test_unauthorized_cancellation_never_mutates_or_records_an_execution(
    restaurant_rows: dict[str, Scenario],
    restaurant_facts: dict[str, object],
) -> None:
    initial = restaurant_rows["restaurant_020"].application.initial_state
    executor = RestaurantTools(initial_state=initial, facts=restaurant_facts)

    with pytest.raises(RestaurantToolError, match="Not authorized"):
        executor.execute("cancel_reservation", {"reservation_id": "R-200"}, call_id="unauthorized")

    assert executor.snapshot() == initial
    assert executor.executions == []


def test_authorized_cancellation_changes_only_the_verified_reservation(
    restaurant_rows: dict[str, Scenario],
    restaurant_facts: dict[str, object],
) -> None:
    initial = restaurant_rows["restaurant_009"].application.initial_state
    executor = RestaurantTools(initial_state=initial, facts=restaurant_facts)

    output = executor.execute("cancel_reservation", {"reservation_id": "R-100"}, call_id="cancel_1")

    assert output == {"ok": True, "reservation_id": "R-100", "cancelled": True}
    assert executor.snapshot()["reservations"][0]["cancelled"] is True
    assert initial["reservations"][0]["cancelled"] is False
    assert verify_final_state({"reservation_id": "R-100", "cancelled": True}, initial, executor.snapshot())


def test_application_state_isolated_between_restaurant_examples(restaurant_facts: dict[str, object]) -> None:
    shared_initial: dict[str, object] = {"reservations": []}
    first = RestaurantTools(initial_state=shared_initial, facts=restaurant_facts)
    second = RestaurantTools(initial_state=shared_initial, facts=restaurant_facts)

    first.execute(
        "create_reservation",
        {"guest_name": "Maya", "date": "2026-08-07", "time": "19:00", "party_size": 2},
        call_id="isolated_1",
    )

    assert second.snapshot() == {"reservations": []}
    assert shared_initial == {"reservations": []}


@pytest.mark.parametrize("example_id", [f"restaurant_{index:03}" for index in range(1, 22)])
def test_offline_restaurant_behavior_uses_only_visible_request_and_authorized_context(
    restaurant_rows: dict[str, Scenario],
    restaurant_facts: dict[str, object],
    example_id: str,
) -> None:
    scenario = restaurant_rows[example_id]
    behavior = RestaurantOfflineBehavior(
        conversation_context=scenario.conversation_context,
        initial_state=scenario.application.initial_state,
        facts=restaurant_facts,
    )

    observed = behavior.infer_tool_call(scenario.input.text)
    expected_name, expected_arguments = expected_tool_fields(scenario)

    if expected_name:
        assert observed == (expected_name, json.loads(expected_arguments))
    else:
        assert observed is None
        answer = behavior.direct_answer(scenario.input.text)
        assert answer
        if example_id == "restaurant_012":
            assert "name" in answer.casefold()
        elif example_id == "restaurant_013":
            assert "time" in answer.casefold()
        elif example_id == "restaurant_014":
            assert "name" in answer.casefold() and "time" in answer.casefold()
        elif example_id == "restaurant_018":
            assert str(restaurant_facts["hours"]) in answer
        elif example_id == "restaurant_019":
            assert str(restaurant_facts["parking"]) == answer
        elif example_id == "restaurant_020":
            assert "authorized" in answer.casefold()


def test_assistant_owns_application_tools_facts_and_offline_behavior() -> None:
    resources = assistant_resources()
    facts = resources.load_facts()
    executor = resources.create_executor({}, facts)
    behavior = resources.create_offline_behavior(conversation_context="", initial_state={}, facts=facts)

    assert isinstance(executor, RestaurantTools)
    assert isinstance(behavior, RestaurantOfflineBehavior)


def test_target_session_receives_authorized_context_but_not_hidden_grading_expectations(
    restaurant_rows: dict[str, Scenario],
    restaurant_facts: dict[str, object],
) -> None:
    scenario = restaurant_rows["restaurant_015"].model_copy(deep=True)
    scenario.expected.answer = "EVALUATOR_ONLY_RESPONSE_SENTINEL"
    scenario.expected.criteria = ["EVALUATOR_ONLY_CRITERION_SENTINEL"]
    resources = assistant_resources()
    frontend = _render_authorized_context(load_system_prompt(resources.system_prompt_file), scenario, restaurant_facts)
    backend = _render_authorized_context(
        load_system_prompt(resources.backend_system_prompt_file), scenario, restaurant_facts
    )
    session = build_session_update(
        frontend,
        load_tools(resources.tools_file),
        "backend-test",
        "marin",
        backend_system_prompt=backend,
    )
    serialized = json.dumps(session)

    assert scenario.conversation_context in serialized
    assert str(restaurant_facts["hours"]) in serialized
    assert "EVALUATOR_ONLY_RESPONSE_SENTINEL" not in serialized
    assert "EVALUATOR_ONLY_CRITERION_SENTINEL" not in serialized
    assert "expected_response" not in serialized
    assert "expected_final_state" not in serialized
    assert "expected_tool_args" not in serialized
    assert "availability_overrides" not in serialized
    assert "task_understanding" not in serialized
    assert "initial_items" not in serialized


def test_portable_scenario_exposes_nested_expectations_without_leaking_golden_state(
    restaurant_rows: dict[str, Scenario],
) -> None:
    scenario = restaurant_rows["restaurant_015"]

    assert scenario.id == "restaurant_015"
    assert scenario.input.text == "Yes, book it for 7 p.m."
    assert scenario.expected.answer == "Confirm Maya's reservation for four at 7 p.m."
    assert scenario.expected.requires_delegation
    assert scenario.expected.tools.required[0].name == "create_reservation"
    assert scenario.expected.tools.required[0].arguments["party_size"] == 4
    assert scenario.interaction == "single_turn"


def test_deterministic_clarification_grade_requires_no_tool_and_unchanged_state(
    restaurant_rows: dict[str, Scenario],
) -> None:
    row = restaurant_rows["restaurant_012"]
    grade = ToolCallGrade.from_mapping(compute_tool_call_grade("", "{}", []))

    dimensions = grade_deterministic_dimensions(
        row,
        grade,
        tool_executions=[],
        final_state={},
        initial_state={},
        delegations=[],
        post_tool_assistant_text="",
    )

    assert dimensions["clarification_behavior"].passed is True
    assert dimensions["delegation_decision"].passed is True
    assert dimensions["final_state"].passed is True
    assert dimensions["grounded_relay_order"].status == "not_applicable"


@pytest.mark.parametrize(
    ("policy", "observed", "passed"),
    [
        ("required", True, True),
        ("required", False, False),
        ("forbidden", True, False),
        ("forbidden", False, True),
        ("optional", True, True),
        ("optional", False, True),
    ],
)
def test_single_turn_delegation_policy_accepts_optional_delegation(
    restaurant_rows: dict[str, Scenario],
    policy: str,
    observed: bool,
    passed: bool,
) -> None:
    scenario = restaurant_rows["restaurant_018"].model_copy(deep=True)
    scenario.expected.delegation = policy
    grade = ToolCallGrade.from_mapping(compute_tool_call_grade("", "{}", []))

    dimensions = grade_deterministic_dimensions(
        scenario,
        grade,
        tool_executions=[],
        final_state=scenario.application.initial_state,
        initial_state=scenario.application.initial_state,
        delegations=[{"id": "delegation-1"}] if observed else [],
        post_tool_assistant_text="",
    )

    assert dimensions["delegation_decision"].passed is passed
    assert dimensions["delegation_decision"].evidence["expected"] == policy


def test_single_turn_grader_requires_all_expected_tools_in_order(
    restaurant_rows: dict[str, Scenario],
    restaurant_facts: dict[str, object],
) -> None:
    scenario = restaurant_rows["restaurant_001"].model_copy(deep=True)
    reservation = scenario.expected.tools.required[0]
    availability = reservation.model_copy(
        update={
            "name": "check_availability",
            "arguments": {"date": "2026-08-07", "time": "19:00", "party_size": 2},
        }
    )
    scenario.expected.tools.required = [availability, reservation]
    executor = RestaurantTools(initial_state={}, facts=restaurant_facts)
    for index, expected in enumerate(scenario.expected.tools.required, start=1):
        executor.execute(expected.name, expected.arguments, call_id=f"call-{index}")
    timeline = Timeline()
    timeline.add_user_utterance(0, 200, scenario.input.text, action="OPENING")
    timeline.apply_event(
        {
            "type": "session.delegation.created",
            "offset_ms": 250,
            "delegation": {"target": "responses", "response_id": "response-1"},
        }
    )
    for index, execution in enumerate(executor.executions):
        timeline.apply_event(
            {
                "type": "tool.completed",
                "offset_ms": 300 + index * 100,
                "name": execution["name"],
                "call_id": execution["call_id"],
                "arguments": execution["arguments"],
                "result": execution["output"],
            }
        )
    timeline.add_transcript("assistant", 500, 900, scenario.expected.answer, "turn.done")
    calls = [
        {"name": execution["name"], "arguments": execution["arguments"], "call_id": execution["call_id"]}
        for execution in executor.executions
    ]

    grade = grade_single_turn_example(
        scenario,
        calls,
        timeline,
        interaction_metrics={"response_latencies_ms": [300], "yield_latencies_ms": []},
        turn_metrics=[],
        user_audio_ms=200,
        run_name="ordered-tool-sequence",
        tts_model="offline",
        offline=True,
        tool_executions=executor.executions,
        initial_state={},
        final_state=executor.snapshot(),
        delegations=[{"id": "delegation-1"}],
        post_tool_assistant_text=scenario.expected.answer,
    )

    assert grade.tool_call.grade == 1
    assert grade.dimension_grades["tool_selection"].passed is True
    assert grade.dimension_grades["parameter_accuracy"].passed is True
    assert grade.dimension_grades["tool_execution"].passed is True
    assert grade.source_result.task_metrics["task_completed"] is True
    assert grade.source_result.task_metrics["expected_tool_call_count"] == 2
    assert grade.source_result.task_metrics["matched_tool_call_count"] == 2
    assert grade.source_result.efficiency_metrics["unexpected_completed_tool_invocation_count"] == 0


@pytest.mark.parametrize("failure", ["missing", "reversed", "wrong_arguments", "extra"])
def test_single_turn_grader_rejects_missing_reordered_or_incorrect_tools(
    restaurant_rows: dict[str, Scenario],
    failure: str,
) -> None:
    scenario = restaurant_rows["restaurant_001"].model_copy(deep=True)
    reservation = scenario.expected.tools.required[0]
    availability = reservation.model_copy(
        update={"name": "check_availability", "arguments": {"date": "2026-08-07", "time": "19:00"}}
    )
    scenario.expected.tools.required = [availability, reservation]
    calls: list[dict[str, object]] = [
        {"name": tool.name, "arguments": dict(tool.arguments)} for tool in scenario.expected.tools.required
    ]
    if failure == "missing":
        calls.pop()
    elif failure == "reversed":
        calls.reverse()
    elif failure == "wrong_arguments":
        calls[0]["arguments"] = {"date": "2026-08-09", "time": "19:00"}
    else:
        calls.append({"name": "cancel_reservation", "arguments": {"reservation_id": "R-100"}})

    result = compute_tool_call_grade(
        reservation.name,
        json.dumps(reservation.arguments),
        calls,
        expected_tools=scenario.expected.tools.required,
    )

    assert ToolCallGrade.from_mapping(result).grade == 0


def test_state_grader_rejects_unexpected_change_and_accepts_normalized_subset() -> None:
    assert not verify_final_state({"unchanged": True}, {}, {"reservation_created": True})
    assert verify_final_state(
        {"guest_name": "maya", "party_size": 2},
        {},
        {"guest_name": "Maya", "party_size": 2, "reservation_id": "R-001"},
    )


@pytest.mark.parametrize(
    ("example_id", "expected"),
    [
        ("restaurant_001", ("task_understanding", "grounded_communication")),
        (
            "restaurant_003",
            (
                "task_understanding",
                "context_fidelity",
                "grounded_communication",
            ),
        ),
        ("restaurant_012", ("task_understanding", "clarification_quality")),
        (
            "restaurant_015",
            (
                "task_understanding",
                "context_fidelity",
                "grounded_communication",
            ),
        ),
        ("restaurant_018", ("task_understanding",)),
        ("restaurant_020", ("task_understanding",)),
    ],
)
def test_only_applicable_semantic_dimensions_are_selected(
    restaurant_rows: dict[str, Scenario],
    example_id: str,
    expected: tuple[str, ...],
) -> None:
    assert applicable_semantic_dimensions(restaurant_rows[example_id]) == expected


def test_offline_semantic_dimensions_are_not_invented(
    restaurant_rows: dict[str, Scenario],
) -> None:
    grades = unassessed_semantic_dimensions(restaurant_rows["restaurant_015"])

    assert set(grades) == set(SEMANTIC_RUBRICS)
    assert grades["context_fidelity"].status == "not_assessed"
    assert grades["grounded_communication"].status == "not_assessed"
    assert grades["task_understanding"].status == "not_assessed"
    assert grades["clarification_quality"].status == "not_applicable"
    assert grades["conversational_coherence"].status == "not_applicable"
    assert all(grade.passed is None for grade in grades.values())


class _FakeJudgeResponses:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def parse(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        messages = kwargs["input"]
        assert isinstance(messages, list)
        content = str(messages[1]["content"])
        dimension = next(name for name in SEMANTIC_RUBRICS if f"RUBRIC: {name}\n" in content)
        decision_type = kwargs["text_format"]
        parsed = decision_type(
            passed=True,
            score={
                "context_fidelity": 0.75,
                "clarification_quality": 0.5,
                "grounded_communication": 0.75,
                "task_understanding": 1.0,
                "conversational_coherence": 0.75,
            }[dimension],
            rationale=f"Verified {dimension} independently.",
            evidence=[f"Observed evidence for {dimension}."],
        )
        usage = SimpleNamespace(
            model_dump=lambda **_: {
                "total_tokens": 15,
                "input_tokens": 10,
                "output_tokens": 5,
                "input_tokens_details": {"cached_tokens": 2},
            }
        )
        return SimpleNamespace(output_parsed=parsed, usage=usage)


class _FakeJudgeClient:
    def __init__(self) -> None:
        self.responses = _FakeJudgeResponses()


@pytest.mark.asyncio
@pytest.mark.parametrize("example_id", ["restaurant_003", "restaurant_012", "restaurant_015", "restaurant_018"])
async def test_semantic_judge_requests_each_applicable_dimension_independently(
    restaurant_rows: dict[str, Scenario],
    restaurant_facts: dict[str, object],
    example_id: str,
) -> None:
    row = restaurant_rows[example_id]
    client = _FakeJudgeClient()
    applicable = applicable_semantic_dimensions(row)

    grades, usage = await judge_semantic_dimensions(
        row,
        assistant_text="The actual grounded assistant answer.",
        delegations=[],
        backend_messages=[],
        tool_executions=[],
        final_state={},
        facts=restaurant_facts,
        client=client,
    )

    assert len(client.responses.calls) == len(applicable)
    assert len(usage) == len(applicable)
    assert {event["dimension"] for event in usage} == set(applicable)
    assert all(event["source"] == "evaluation_judge" for event in usage)
    assert all(event["model"] == DEFAULT_JUDGE_MODEL for event in usage)
    assert all(event["input_tokens"] == 10 for event in usage)
    assert all(event["cached_input_tokens"] == 2 for event in usage)
    assert all(event["output_tokens"] == 5 for event in usage)
    assert all(grades[name].passed for name in applicable)
    assert all(0.0 <= grades[name].score <= 1.0 for name in applicable)
    assert all(grades[name].evidence["rubric_version"] == "voice-semantic-v2" for name in applicable)
    assert grades["task_understanding"].score == 1.0
    assert all(grades[name].score is None for name in set(SEMANTIC_RUBRICS).difference(applicable))
    assert all("severity-aware score" in str(call["input"][0]["content"]) for call in client.responses.calls)
    assert all(
        "exactly 0, 0.25, 0.5, 0.75, or 1" in str(call["input"][0]["content"]) for call in client.responses.calls
    )
    assert all(grades[name].status == "not_applicable" for name in set(SEMANTIC_RUBRICS).difference(applicable))
    assert all(call["store"] is False for call in client.responses.calls)


def test_semantic_judge_receives_golden_evidence_only_in_independent_judge_input(
    restaurant_rows: dict[str, Scenario],
    restaurant_facts: dict[str, object],
) -> None:
    row = restaurant_rows["restaurant_015"]
    execution = {
        "call_id": "verified-reservation",
        "name": "create_reservation",
        "arguments": {"guest_name": "Maya", "party_size": 4},
        "status": "completed",
        "output": {"ok": True, "reservation_id": "R-001", "party_size": 4},
    }

    judge_input = build_semantic_judge_input(
        row,
        dimension="context_fidelity",
        assistant_text="Maya, your table for four is confirmed at 7 p.m.",
        delegations=[],
        backend_messages=[],
        tool_executions=[execution],
        final_state={},
        facts=restaurant_facts,
    )

    assert "RUBRIC: context_fidelity\n" in judge_input
    assert row.expected.answer in judge_input
    assert row.conversation_context in judge_input
    assert '"expected_tool_args"' in judge_input
    assert '"final_application_state"' in judge_input
    assert '"success_criteria"' in judge_input
    assert row.expected.criteria[0] in judge_input
    assert "availability_overrides" not in judge_input
    payload = json.loads(judge_input.split("EVALUATION EVIDENCE:\n", maxsplit=1)[1])
    assert payload["observed"]["tool_executions"] == [execution]
    assert payload["observed"]["tool_executions"][0]["output"]["reservation_id"] == "R-001"


@pytest.mark.asyncio
async def test_judge_failure_is_reported_as_evaluation_infrastructure(
    restaurant_rows: dict[str, Scenario],
    restaurant_facts: dict[str, object],
) -> None:
    class FailingResponses:
        async def parse(self, **_: object) -> None:
            raise RuntimeError("judge unavailable")

    with pytest.raises(SemanticJudgeError, match="judge unavailable") as failure:
        await judge_semantic_dimensions(
            restaurant_rows["restaurant_018"],
            assistant_text="The restaurant closes at 10 p.m.",
            delegations=[],
            backend_messages=[],
            tool_executions=[],
            final_state={},
            facts=restaurant_facts,
            client=SimpleNamespace(responses=FailingResponses()),
        )

    assert failure.value.failure_stage == "semantic_judge"


@pytest.mark.asyncio
async def test_complete_offline_restaurant_run_preserves_all_artifacts_and_real_grading_boundaries(
    tmp_path: Path,
) -> None:
    args = parse_args(
        [
            "--offline",
            "--no-real-time",
            "--data",
            str(DEFAULT_DATA_JSON),
            "--results-dir",
            str(tmp_path),
            "--run-name",
            "restaurant-contract",
        ]
    )

    run_dir = await run_evals(args)

    report = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    rows = report["results"]

    assert len(rows) == 21
    assert all(row["status"] == "passed" for row in rows)
    assert all(row["metrics"]["task"]["task_completed"] for row in rows)
    assert all(row["assessment"]["passed"] for row in rows)
    assert all(row["assessment"]["source"] == "deterministic" for row in rows)
    assert all(row["observability"]["interaction"]["audio_source"] == "synthetic" for row in rows)
    assert all("agenda" not in row["observability"] and "floor" not in row["observability"] for row in rows)
    assert sum(row["metrics"]["task"]["tool_calls"]["actual"] for row in rows) == 15
    assert sum(row["metrics"]["task"]["tool_calls"]["actual"] == 0 for row in rows) == 6
    assert "application_profile" not in report["run"]["configuration"]
    assert report["summary"] == {
        "total": 21,
        "passed": 21,
        "failed": 0,
        "infrastructure_errors": 0,
    }
    assert all(row["metrics"]["consumption"]["frontend"]["audio_duration_ms"] > 0 for row in rows)
    assert all("input" not in row["metrics"]["consumption"]["frontend"] for row in rows)
    delegated = [row for row in rows if row["metrics"]["task"]["tool_calls"]["actual"]]
    assert all(row["metrics"]["consumption"]["backend"]["input"]["total_tokens"] for row in delegated)

    hydrated = json.loads((run_dir / "transcripts" / "restaurant_015.json").read_text(encoding="utf-8"))
    assert hydrated["context_mode"] == "summary"
    assert hydrated["tool_executions"][0]["arguments"]["party_size"] == 4
    assert hydrated["tool_executions"][0]["arguments"]["time"] == "19:00"
    assert hydrated["semantic_grades"]["context_fidelity"]["status"] == "not_assessed"
    assert hydrated["assessment"]["passed"] is True
    assert hydrated["observability"]["completion"]["failed_checks"] == []

    structured = json.loads((run_dir / "transcripts" / "restaurant_021.json").read_text(encoding="utf-8"))
    assert structured["context_mode"] == "history"
    assert structured["tool_executions"][0]["arguments"] == {
        "guest_name": "Maya",
        "date": "2026-08-07",
        "time": "19:00",
        "party_size": 4,
    }
    history_trace = [
        json.loads(line)
        for line in (run_dir / "events" / "restaurant_021.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    history_session = history_trace[0]["event"]["session"]
    assert [item["role"] for item in history_session["input"]] == ["user", "assistant", "user", "assistant"]
    assert "previous_conversation_summary" not in history_session["instructions"]
    assert "Use the prior conversation to recover" not in json.dumps(history_session)

    refusal = json.loads((run_dir / "transcripts" / "restaurant_020.json").read_text(encoding="utf-8"))
    assert refusal["delegations"] == []
    assert refusal["tool_executions"] == []
    assert refusal["final_state"] == refusal["initial_state"]

    trace = [
        json.loads(line)
        for line in (run_dir / "events" / "restaurant_015.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    session = json.dumps(trace[0]["event"])
    assert any(event["type"] == "evaluation.checks.assessed" for event in trace)
    assert any(event["type"] == "evaluation.outcome.assessed" for event in trace)
    assert [event["event_index"] for event in trace] == list(range(1, len(trace) + 1))
    assert "expected_response" not in session
    assert "expected_final_state" not in session
    assert "expected_tool_args" not in session
    assert "availability_overrides" not in session
