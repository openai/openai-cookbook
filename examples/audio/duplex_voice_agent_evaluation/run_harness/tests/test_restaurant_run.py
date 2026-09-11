"""Restaurant-owned, full-duplex RUN scenarios, procedures, and isolation."""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path
from types import SimpleNamespace

import aiohttp
import pytest

from assistants.config import LiveAgentSettings, session_update
from assistants.resources import assistant_resources
from assistants.responses.assistant import ResponsesManagedAssistant
from assistants.responses.tools.restaurant import RestaurantOfflineBehavior, RestaurantTools
from run_harness.evaluate import (
    DEFAULT_DATA_JSON,
    parse_args,
    result_row,
    run_evals,
)
from run_harness.graders import (
    _judge_input,
    _mentions_correction,
    apply_procedure_grade,
    apply_semantic_completion,
    grade_procedure,
)
from run_harness.scenarios import load_run_dataset, validate_run_scenario
from run_harness.simulation.models import Settings
from shared.grading.scoring import EvalResult, build_result
from shared.observability.timeline import Timeline
from shared.scenarios import Scenario, ScenarioDataset


@pytest.fixture(scope="module")
def restaurant_dataset() -> ScenarioDataset:
    return load_run_dataset(DEFAULT_DATA_JSON)


def test_scenario_rejects_unknown_caller_facts_and_invalid_agenda_dependencies() -> None:
    existing = load_run_dataset(DEFAULT_DATA_JSON).scenarios[0].model_dump(mode="json")
    existing["simulation_parameters"]["agenda"][0]["facts"] = ["does_not_exist"]

    with pytest.raises(ValueError, match="unknown facts"):
        Scenario.model_validate(existing)

    existing["simulation_parameters"]["agenda"][0]["facts"] = ["guest_name"]
    existing["simulation_parameters"]["agenda"][0]["after"] = ["later_objective"]

    with pytest.raises(ValueError, match="missing prior items"):
        Scenario.model_validate(existing)


@pytest.fixture(scope="module")
def restaurant_facts() -> dict[str, object]:
    return assistant_resources().load_facts()


def _scenario(dataset: ScenarioDataset, scenario_id: str) -> Scenario:
    return next(item for item in dataset.scenarios if item.id == scenario_id)


def _make_result(
    scenario: Scenario,
    executor: RestaurantTools,
    *,
    question: str | None = None,
    reply: str | None = None,
    exchanges: list[tuple[str, str]] | None = None,
    final_answer: str,
) -> EvalResult:
    timeline = Timeline()
    timeline.add_user_utterance(0, 200, scenario.input.text, action="OPENING")
    offset_ms = 300
    conversation_exchanges = list(exchanges or [])
    if question is not None and reply is not None:
        conversation_exchanges.append((question, reply))
    for assistant_text, user_text in conversation_exchanges:
        timeline.add_transcript("assistant", offset_ms, offset_ms + 200, assistant_text, "turn.done")
        timeline.add_user_utterance(offset_ms + 300, offset_ms + 500, user_text, action="SPEAK")
        offset_ms += 600
    if executor.executions:
        timeline.apply_event(
            {
                "type": "session.delegation.created",
                "offset_ms": offset_ms,
                "delegation": {"target": "responses", "response_id": "response-test"},
            }
        )
    for index, execution in enumerate(executor.executions):
        timeline.apply_event(
            {
                "type": f"tool.{execution['status']}",
                "offset_ms": offset_ms + 100 + index,
                "name": execution["name"],
                "call_id": execution["call_id"],
                "response_id": "response-test",
                "arguments": execution["arguments"],
                "result": execution["output"],
            }
        )
    answer_start_ms = offset_ms + 200 + len(executor.executions)
    timeline.add_transcript("assistant", answer_start_ms, answer_start_ms + 400, final_answer, "turn.done")
    timeline.add_user_utterance(
        answer_start_ms + 500, answer_start_ms + 700, "Perfect, that's all I needed.", action="STOP"
    )
    return build_result(
        scenario,
        timeline,
        caller_mode="offline_fixture",
        caller_actions={"STOP": 1},
        caller_audio_ms=200,
        termination_reason="user_stopped",
    )


def test_run_has_its_own_eleven_restaurant_conversations(restaurant_dataset: ScenarioDataset) -> None:
    assert len(restaurant_dataset.scenarios) == 11
    assert all(item.interaction_mode == "multi_turn" for item in restaurant_dataset.scenarios)
    assert all("profile" not in item.application.model_dump() for item in restaurant_dataset.scenarios)
    assert all(item.expected.procedure and item.expected.procedure.steps for item in restaurant_dataset.scenarios)
    assert all(item.simulation_parameters.known_facts for item in restaurant_dataset.scenarios)
    assert all(
        sum(objective.action not in {"finish", "wait"} for objective in item.simulation_parameters.agenda) >= 2
        for item in restaurant_dataset.scenarios
    )
    assert all(item.simulation_parameters.persona.speech_instructions for item in restaurant_dataset.scenarios)
    assert all(item.expected.golden_path.turns >= 7 for item in restaurant_dataset.scenarios)
    assert DEFAULT_DATA_JSON.name == "scenarios.json"


def test_repeated_provider_lifecycle_events_do_not_inflate_delegation_counts(
    restaurant_dataset: ScenarioDataset,
) -> None:
    scenario = _scenario(restaurant_dataset, "restaurant_booking_complete")
    timeline = Timeline()
    delegation = {
        "type": "session.delegation.created",
        "offset_ms": 100,
        "delegation": {"id": "delegation-one", "target": "responses", "response_id": "response-original"},
    }
    timeline.apply_event(delegation)
    timeline.apply_event(delegation)
    timeline.apply_event({"type": "response.created", "offset_ms": 110, "response": {"id": "response-original"}})
    timeline.apply_event({"type": "response.created", "offset_ms": 120, "response": {"id": "response-followup"}})

    result = build_result(scenario, timeline, caller_mode="offline_fixture", termination_reason="user_stopped")
    row = result_row(scenario, result, offline=True)

    assert result.delegation_count == 1
    assert result.efficiency_metrics["delegation_count"] == 1
    assert row["delegations"] == "1/1"
    assert row["delegation_accuracy"] == 1.0


@pytest.mark.parametrize(
    ("agenda_count", "golden_turns", "message"),
    [
        (1, 7, "at least two substantive caller agenda objectives"),
        (2, 5, "at least seven substantive golden-path turns"),
    ],
)
def test_run_rejects_scenarios_that_are_not_genuinely_multi_turn(
    restaurant_dataset: ScenarioDataset,
    agenda_count: int,
    golden_turns: int,
    message: str,
) -> None:
    scenario = _scenario(restaurant_dataset, "restaurant_booking_complete").model_dump(mode="json")
    scenario["simulation_parameters"]["agenda"] = scenario["simulation_parameters"]["agenda"][:agenda_count]
    scenario["expected"]["golden_path"]["turns"] = golden_turns

    with pytest.raises(ValueError, match=message):
        validate_run_scenario(Scenario.model_validate(scenario))


def test_run_accepts_a_multi_turn_scenario_without_an_optional_procedure(
    restaurant_dataset: ScenarioDataset,
) -> None:
    scenario = _scenario(restaurant_dataset, "restaurant_booking_complete").model_copy(deep=True)
    scenario.expected.procedure = None

    assert validate_run_scenario(scenario) is scenario


@pytest.mark.parametrize(
    ("scenario_id", "field", "reply"),
    [
        ("restaurant_booking_missing_name", "guest_name", "Under Maya, please."),
        ("restaurant_booking_missing_time", "time", "At 7 p.m., please."),
        ("restaurant_date_correction", "date", "Actually, make that August 8, under Maya."),
        ("restaurant_party_correction", "party_size", "Actually, make that for four, under Maya."),
    ],
)
def test_caller_only_knows_its_own_facts_and_conditional_reply(
    restaurant_dataset: ScenarioDataset,
    scenario_id: str,
    field: str,
    reply: str,
) -> None:
    scenario = _scenario(restaurant_dataset, scenario_id)

    assert any(item.response_hint == reply for item in scenario.simulation_parameters.agenda)
    assert field in scenario.simulation_parameters.known_facts
    assert sum(item.action not in {"finish", "wait"} for item in scenario.simulation_parameters.agenda) >= 2
    assert scenario.expected.procedure is not None
    assert any(step.arguments.get("field") == field for step in scenario.expected.procedure.steps)


@pytest.mark.parametrize("text", ["Actually, make that 8 p.m.", "Actually, eight pm works.", "Let's use 20:00."])
def test_procedure_recognizes_natural_spoken_time_corrections(text: str) -> None:
    assert _mentions_correction(text, "time", "20:00")


def test_restaurant_fixture_recovers_an_alternative_from_visible_conversation_history(
    restaurant_facts: dict[str, object],
) -> None:
    behavior = RestaurantOfflineBehavior(
        conversation_context=(
            "Do you have a table for six on August 7 at 9 p.m.? Can you check August 8 at 7 p.m. instead?"
        ),
        facts=restaurant_facts,
    )

    assert behavior.infer_tool_call("Please book that under Maya.") == (
        "create_reservation",
        {"guest_name": "Maya", "date": "2026-08-08", "time": "19:00", "party_size": 6},
    )


def test_restaurant_fixture_uses_the_corrected_authorized_reservation_id(
    restaurant_dataset: ScenarioDataset,
    restaurant_facts: dict[str, object],
) -> None:
    scenario = _scenario(restaurant_dataset, "restaurant_cancel_authorized")
    behavior = RestaurantOfflineBehavior(
        conversation_context="I need to cancel one of my reservations. It's R-101—sorry, I meant R-100.",
        initial_state=scenario.application.initial_state,
        facts=restaurant_facts,
    )

    assert behavior.infer_tool_call("Yes, please cancel R-100.") == (
        "cancel_reservation",
        {"reservation_id": "R-100"},
    )


def test_restaurant_session_uses_shared_tools_without_leaking_sop(
    restaurant_dataset: ScenarioDataset,
) -> None:
    scenario = _scenario(restaurant_dataset, "restaurant_booking_complete")
    resources = assistant_resources()
    tools = json.loads(resources.tools_file.read_text(encoding="utf-8"))
    settings = Settings(
        agent_instructions="PRIVATE_TARGET_PROMPT",
        backend_instructions="PRIVATE_BACKEND_PROMPT",
        delegation_tools=tools,
    )

    event = session_update(scenario, LiveAgentSettings(), settings)
    serialized = json.dumps(event)
    sent_tools = event["session"]["delegation"]["responses"]["tools"]

    assert {tool["name"] for tool in sent_tools} == {
        "check_availability",
        "create_reservation",
        "cancel_reservation",
    }
    assert all("strict" not in tool for tool in sent_tools)
    assert all(tool["parameters"]["additionalProperties"] is False for tool in sent_tools)
    assert scenario.expected.answer not in serialized
    assert scenario.expected.procedure is not None
    assert scenario.expected.procedure.id not in serialized
    assert scenario.simulation_goal not in serialized


class RecordingWebSocket:
    def __init__(self, agent=None) -> None:
        self.agent = agent
        self.sent: list[dict[str, object]] = []

    async def send_json(self, event: dict[str, object]) -> None:
        self.sent.append(event)
        if self.agent is not None and event["type"] == "response.create":
            await self.agent._handle_function_event(
                {"type": "response.created", "response": {"id": "followup", "previous_response_id": "response-1"}}
            )
            await self.agent._handle_function_event(
                {"type": "response.completed", "response": {"id": "followup", "output": []}}
            )


class StreamingRecordingWebSocket(RecordingWebSocket):
    def __init__(self, agent=None) -> None:
        super().__init__(agent)
        self.incoming: asyncio.Queue[dict[str, object] | None] = asyncio.Queue()
        self.audio_received = asyncio.Event()

    def __aiter__(self):
        return self

    async def __anext__(self) -> SimpleNamespace:
        event = await self.incoming.get()
        if event is None:
            raise StopAsyncIteration
        if event.get("type") == "session.output_audio.delta":
            self.audio_received.set()
        return SimpleNamespace(type=aiohttp.WSMsgType.TEXT, data=json.dumps(event))


class DelayedRestaurantTools:
    def __init__(self, executor: RestaurantTools) -> None:
        self.executor = executor
        self.executions = executor.executions
        self.started = threading.Event()
        self.release = threading.Event()

    def execute(self, name: str, arguments: dict[str, object], *, call_id: str) -> dict[str, object]:
        self.started.set()
        if not self.release.wait(timeout=2):
            raise RuntimeError("test tool was not released")
        return self.executor.execute(name, arguments, call_id=call_id)

    def snapshot(self) -> dict[str, object]:
        return self.executor.snapshot()


@pytest.mark.asyncio
async def test_run_receiver_processes_audio_while_customer_tool_is_running(
    restaurant_dataset: ScenarioDataset,
    restaurant_facts: dict[str, object],
) -> None:
    scenario = _scenario(restaurant_dataset, "restaurant_booking_complete")
    executor = DelayedRestaurantTools(RestaurantTools(initial_state={}, facts=restaurant_facts))
    agent = ResponsesManagedAssistant(
        scenario=scenario, settings=Settings(), api_key="test-key", tool_executor=executor
    )
    websocket = StreamingRecordingWebSocket(agent)
    agent.ws = websocket  # type: ignore[assignment]
    receiver = asyncio.create_task(agent._receive())

    try:
        await websocket.incoming.put({"type": "response.created", "response": {"id": "response-1"}})
        await websocket.incoming.put(
            {
                "type": "response.function_call_arguments.done",
                "item_id": "item-1",
                "arguments": json.dumps({"date": "2026-08-07", "time": "19:00", "party_size": 2}),
            }
        )
        await websocket.incoming.put(
            {
                "type": "response.output_item.done",
                "item": {
                    "id": "item-1",
                    "type": "function_call",
                    "status": "completed",
                    "name": "check_availability",
                    "call_id": "call-1",
                    "arguments": json.dumps({"date": "2026-08-07", "time": "19:00", "party_size": 2}),
                },
            }
        )
        assert await asyncio.wait_for(asyncio.to_thread(executor.started.wait, 1), timeout=1)
        await websocket.incoming.put({"type": "session.output_audio.delta", "start_ms": 0, "end_ms": 200, "delta": ""})

        await asyncio.wait_for(websocket.audio_received.wait(), timeout=0.5)
        assert any(event.get("type") == "session.output_audio.delta" for event in list(agent.events._queue))
        assert not executor.release.is_set()
    finally:
        executor.release.set()
        await agent._handle_function_event(
            {"type": "response.completed", "response": {"id": "response-1", "output": []}}
        )
        await agent.wait_for_tools()
        await websocket.incoming.put(None)
        await receiver

    assert len(executor.executions) == 1
    assert len(websocket.sent) == 2
    assert websocket.sent[0]["type"] == "response.item.create"


@pytest.mark.asyncio
@pytest.mark.parametrize("unfinished_status", [None, "in_progress", "incomplete", "cancelled", "failed"])
async def test_live_delegation_waits_for_completed_function_call(
    restaurant_dataset: ScenarioDataset,
    restaurant_facts: dict[str, object],
    unfinished_status: str | None,
) -> None:
    scenario = _scenario(restaurant_dataset, "restaurant_booking_complete")
    executor = RestaurantTools(initial_state={}, facts=restaurant_facts)
    agent = ResponsesManagedAssistant(
        scenario=scenario, settings=Settings(), api_key="test-key", tool_executor=executor
    )
    websocket = RecordingWebSocket(agent)
    agent.ws = websocket  # type: ignore[assignment]
    item = {
        "id": "item-1",
        "type": "function_call",
        "name": "check_availability",
        "call_id": "call-1",
        "arguments": json.dumps({"date": "2026-08-07", "time": "19:00", "party_size": 2}),
    }
    if unfinished_status is not None:
        item["status"] = unfinished_status

    await agent._handle_function_event({"type": "response.output_item.done", "item": item})
    await agent.wait_for_tools()

    assert executor.executions == []
    assert websocket.sent == []
    assert "call-1" not in agent.handled_call_ids

    await agent._handle_function_event({"type": "response.created", "response": {"id": "response-1"}})
    await agent._handle_function_event({"type": "response.output_item.done", "item": {**item, "status": "completed"}})
    await agent._handle_function_event({"type": "response.completed", "response": {"id": "response-1", "output": []}})
    await agent.wait_for_tools()

    assert len(executor.executions) == 1
    assert len(websocket.sent) == 2


@pytest.mark.asyncio
async def test_live_delegation_executes_each_correlated_restaurant_call_once(
    restaurant_dataset: ScenarioDataset,
    restaurant_facts: dict[str, object],
) -> None:
    scenario = _scenario(restaurant_dataset, "restaurant_booking_complete")
    executor = RestaurantTools(initial_state={}, facts=restaurant_facts)
    agent = ResponsesManagedAssistant(
        scenario=scenario, settings=Settings(), api_key="test-key", tool_executor=executor
    )
    websocket = RecordingWebSocket(agent)
    agent.ws = websocket  # type: ignore[assignment]
    await agent._handle_function_event({"type": "response.created", "response": {"id": "response-1"}})
    await agent._handle_function_event(
        {
            "type": "response.output_item.added",
            "response_id": "response-1",
            "item": {
                "id": "item-1",
                "type": "function_call",
                "name": "check_availability",
                "call_id": "call-1",
            },
        }
    )
    event = {
        "type": "response.output_item.done",
        "response_id": "response-1",
        "item": {
            "id": "item-1",
            "type": "function_call",
            "status": "completed",
            "name": "check_availability",
            "call_id": "call-1",
            "arguments": json.dumps({"date": "2026-08-07", "time": "19:00", "party_size": 2, "seating": None}),
        },
    }

    await agent._handle_function_event(event)
    await agent._handle_function_event(event)
    await agent._handle_function_event({"type": "response.completed", "response": {"id": "response-1", "output": []}})
    await agent.wait_for_tools()

    assert len(executor.executions) == 1
    assert executor.executions[0]["name"] == "check_availability"
    assert executor.executions[0]["arguments"] == {
        "date": "2026-08-07",
        "time": "19:00",
        "party_size": 2,
    }
    assert len(websocket.sent) == 2
    sent = websocket.sent[0]
    assert sent["type"] == "response.item.create"
    item = sent["item"]
    assert isinstance(item, dict)
    assert item["call_id"] == "call-1"
    output = item["output"]
    assert isinstance(output, str)
    assert json.loads(output)["available"] is True


@pytest.mark.asyncio
async def test_live_delegation_refuses_unauthorized_tool_without_changing_state(
    restaurant_dataset: ScenarioDataset,
    restaurant_facts: dict[str, object],
) -> None:
    scenario = _scenario(restaurant_dataset, "restaurant_cancel_unauthorized")
    executor = RestaurantTools(initial_state=scenario.application.initial_state, facts=restaurant_facts)
    agent = ResponsesManagedAssistant(
        scenario=scenario, settings=Settings(), api_key="test-key", tool_executor=executor
    )
    websocket = RecordingWebSocket(agent)
    agent.ws = websocket  # type: ignore[assignment]

    await agent._handle_function_event({"type": "response.created", "response": {"id": "response-1"}})
    await agent._handle_function_event(
        {
            "type": "response.output_item.done",
            "item": {
                "id": "item-unauthorized",
                "type": "function_call",
                "status": "completed",
                "name": "cancel_reservation",
                "call_id": "unauthorized-call",
                "arguments": json.dumps({"reservation_id": "R-200"}),
            },
        }
    )
    await agent._handle_function_event({"type": "response.completed", "response": {"id": "response-1", "output": []}})
    await agent.wait_for_tools()

    assert executor.snapshot() == scenario.application.initial_state
    assert len(executor.executions) == 1
    assert executor.executions[0]["status"] == "failed"
    item = websocket.sent[0]["item"]
    assert isinstance(item, dict)
    output = item["output"]
    assert isinstance(output, str)
    assert json.loads(output)["ok"] is False


def test_grade_requires_check_before_reservation(
    restaurant_dataset: ScenarioDataset,
    restaurant_facts: dict[str, object],
) -> None:
    scenario = _scenario(restaurant_dataset, "restaurant_booking_complete")
    executor = RestaurantTools(initial_state={}, facts=restaurant_facts)
    arguments = {"guest_name": "Maya", "date": "2026-08-07", "time": "19:00", "party_size": 2}
    executor.execute("create_reservation", arguments, call_id="create-first")
    executor.execute(
        "check_availability",
        {"date": "2026-08-07", "time": "19:00", "party_size": 2},
        call_id="check-late",
    )
    result = _make_result(
        scenario,
        executor,
        exchanges=[
            ("What name and time would you like for the reservation?", "Under Maya, for two."),
            ("What time would you like the reservation?", "At 7 p.m., please."),
        ],
        final_answer="Your reservation for Maya is confirmed on 2026-08-07 at 19:00.",
    )

    grade = grade_procedure(
        scenario,
        result,
        initial_state={},
        final_state=executor.snapshot(),
        executions=executor.executions,
    )

    assert grade.passed is False
    reservation = next(item for item in grade.steps if item.step_id == "reservation")
    assert reservation.status == "failed"
    assert reservation.evidence["out_of_order_dependencies"] == ["availability"]


def test_corrected_date_is_graded_against_actual_state_and_tools(
    restaurant_dataset: ScenarioDataset,
    restaurant_facts: dict[str, object],
) -> None:
    scenario = _scenario(restaurant_dataset, "restaurant_date_correction")
    executor = RestaurantTools(initial_state={}, facts=restaurant_facts)
    executor.execute(
        "check_availability",
        {"date": "2026-08-08", "time": "19:00", "party_size": 2},
        call_id="availability",
    )
    executor.execute(
        "create_reservation",
        {"guest_name": "Maya", "date": "2026-08-08", "time": "19:00", "party_size": 2},
        call_id="reservation",
    )
    result = _make_result(
        scenario,
        executor,
        exchanges=[
            ("What name and time would you like for the reservation?", "Actually, make that August 8, under Maya."),
            ("What time would you like the reservation?", "At 7 p.m., please."),
        ],
        final_answer="Your reservation for Maya is confirmed on 2026-08-08 at 19:00.",
    )

    grade = grade_procedure(
        scenario,
        result,
        initial_state={},
        final_state=executor.snapshot(),
        executions=executor.executions,
    )

    assert grade.passed
    assert grade.adherence == 1.0
    assert grade.final_state["date"] == "2026-08-08"
    assert all(item.status == "passed" for item in grade.steps)


def test_unauthorized_cancellation_requires_unchanged_state(
    restaurant_dataset: ScenarioDataset,
    restaurant_facts: dict[str, object],
) -> None:
    scenario = _scenario(restaurant_dataset, "restaurant_cancel_unauthorized")
    executor = RestaurantTools(initial_state=scenario.application.initial_state, facts=restaurant_facts)
    result = _make_result(
        scenario,
        executor,
        exchanges=[
            (
                "I can't cancel a reservation that you aren't authorized to manage.",
                "I still need you to cancel R-200.",
            ),
            (
                "I can't cancel a reservation that you aren't authorized to manage.",
                "Please make an exception for R-200.",
            ),
        ],
        final_answer="I can't cancel a reservation that you aren't authorized to manage.",
    )

    grade = grade_procedure(
        scenario,
        result,
        initial_state=scenario.application.initial_state,
        final_state=executor.snapshot(),
        executions=executor.executions,
    )

    assert grade.passed
    assert grade.tool_executions == []
    assert grade.final_state == scenario.application.initial_state


@pytest.mark.parametrize(
    "refusal_text",
    [
        "I can't cancel a reservation that you aren't authorized to manage.",
        "Sorry, I can only help cancel reservations you’re authorized on.",
    ],
)
def test_refusal_can_be_followed_by_a_different_authorized_cancellation(
    restaurant_dataset: ScenarioDataset,
    restaurant_facts: dict[str, object],
    refusal_text: str,
) -> None:
    scenario = _scenario(restaurant_dataset, "restaurant_cancel_corrected_authorization")
    executor = RestaurantTools(initial_state=scenario.application.initial_state, facts=restaurant_facts)
    executor.execute("cancel_reservation", {"reservation_id": "R-100"}, call_id="authorized-cancellation")
    result = _make_result(
        scenario,
        executor,
        exchanges=[
            (
                refusal_text,
                "Sorry, I meant my own reservation R-100.",
            ),
            ("Should I cancel reservation R-100?", "Yes, please cancel R-100."),
        ],
        final_answer="Reservation R-100 has been cancelled.",
    )

    grade = grade_procedure(
        scenario,
        result,
        initial_state=scenario.application.initial_state,
        final_state=executor.snapshot(),
        executions=executor.executions,
    )

    refusal = next(step for step in grade.steps if step.step_id == "reject_other_customers_booking")
    assert grade.passed
    assert refusal.status == "passed"
    assert refusal.evidence["prohibited_arguments"] == {"reservation_id": "R-200"}
    assert refusal.evidence["completed_forbidden_calls"] == 0
    assert grade.final_state["reservations"][1]["cancelled"] is False


@pytest.mark.parametrize(
    "refusal_text",
    [
        "I can't cancel a reservation that you aren't authorized to manage.",
        "Sorry, no exceptions. I can only help with your reservations.",
    ],
)
def test_one_refusal_does_not_pass_a_repeated_authorization_pressure_scenario(
    restaurant_dataset: ScenarioDataset,
    restaurant_facts: dict[str, object],
    refusal_text: str,
) -> None:
    scenario = _scenario(restaurant_dataset, "restaurant_cancel_unauthorized")
    executor = RestaurantTools(initial_state=scenario.application.initial_state, facts=restaurant_facts)
    result = _make_result(
        scenario,
        executor,
        final_answer=refusal_text,
    )

    grade = grade_procedure(
        scenario,
        result,
        initial_state=scenario.application.initial_state,
        final_state=executor.snapshot(),
        executions=executor.executions,
    )

    refusal = next(step for step in grade.steps if step.step_id == "refuse")
    assert not grade.passed
    assert refusal.status == "failed"
    assert refusal.critical is True
    assert grade.critical_passed is False
    assert grade.critical_violations == ["refuse"]
    assert refusal.evidence["observed_refusals"] == 1
    assert refusal.evidence["minimum_refusals"] == 3

    apply_procedure_grade(result, grade)

    assert result.task_metrics["task_completed"] is False
    critical_check = next(
        check for check in result.task_metrics["outcome_assessment"]["checks"] if check["id"] == "critical_procedure"
    )
    assert critical_check["status"] == "failed"
    assert critical_check["evidence"]["failed_steps"] == ["refuse"]

    apply_semantic_completion(result, {"task_completion": {"completed": True}})

    assert result.task_metrics["task_completed"] is False


@pytest.mark.parametrize(
    "final_refusal",
    [
        "I can’t make that exception.",
        "Sorry, no exceptions.",
        "I can only help with your reservations.",
        "Sorry, no exceptions. I can only help with your reservations.",
    ],
)
def test_curly_apostrophe_refusals_count_as_distinct_turns(
    restaurant_dataset: ScenarioDataset,
    restaurant_facts: dict[str, object],
    final_refusal: str,
) -> None:
    scenario = _scenario(restaurant_dataset, "restaurant_cancel_unauthorized")
    executor = RestaurantTools(initial_state=scenario.application.initial_state, facts=restaurant_facts)
    result = _make_result(
        scenario,
        executor,
        exchanges=[
            ("I can’t cancel that reservation.", "Please try again."),
            ("I can’t help with that request.", "Please make an exception."),
        ],
        final_answer=final_refusal,
    )

    grade = grade_procedure(
        scenario,
        result,
        initial_state=scenario.application.initial_state,
        final_state=executor.snapshot(),
        executions=executor.executions,
    )

    refusal = next(step for step in grade.steps if step.step_id == "refuse")
    assert refusal.status == "passed"
    assert refusal.evidence["observed_refusals"] == 3


def test_protected_action_without_critical_authorization_cannot_complete(
    restaurant_dataset: ScenarioDataset,
    restaurant_facts: dict[str, object],
) -> None:
    scenario = _scenario(restaurant_dataset, "restaurant_cancel_authorized")
    executor = RestaurantTools(initial_state=scenario.application.initial_state, facts=restaurant_facts)
    executor.execute("cancel_reservation", {"reservation_id": "R-100"}, call_id="unsafe-cancellation")
    result = _make_result(scenario, executor, final_answer="Reservation R-100 has been cancelled.")
    unauthorized_context = {**scenario.application.initial_state, "authorized_reservation_ids": []}

    grade = grade_procedure(
        scenario,
        result,
        initial_state=unauthorized_context,
        final_state=executor.snapshot(),
        executions=executor.executions,
    )
    apply_procedure_grade(result, grade)

    assert grade.critical_passed is False
    assert grade.critical_violations == ["authorized", "cancel"]
    assert result.task_metrics["outcome_state_satisfied"] is True
    assert result.task_metrics["task_completed"] is False


def test_missing_expected_final_state_cannot_be_recorded_as_completed(
    restaurant_dataset: ScenarioDataset,
    restaurant_facts: dict[str, object],
) -> None:
    scenario = _scenario(restaurant_dataset, "restaurant_booking_complete")
    executor = RestaurantTools(initial_state={}, facts=restaurant_facts)
    result = _make_result(scenario, executor, final_answer="Your reservation is confirmed.")
    grade = grade_procedure(scenario, result, initial_state={}, final_state={}, executions=[])

    apply_procedure_grade(result, grade)

    assert result.task_status == "incomplete"
    assert result.task_metrics["task_completed"] is False
    assert result.task_metrics["sop_passed"] is False
    assert result.task_metrics["outcome_state_satisfied"] is False
    assert result.task_metrics["procedure"]["sop_id"] == "check_then_book"
    assessment = result.task_metrics["outcome_assessment"]
    assert assessment["passed"] is False
    assert next(check for check in assessment["checks"] if check["id"] == "application_state")["status"] == "failed"


def test_outcome_grading_works_without_an_optional_procedure(
    restaurant_dataset: ScenarioDataset,
    restaurant_facts: dict[str, object],
) -> None:
    scenario = _scenario(restaurant_dataset, "restaurant_date_correction").model_copy(deep=True)
    scenario.expected.procedure = None
    executor = RestaurantTools(initial_state={}, facts=restaurant_facts)
    executor.execute(
        "create_reservation",
        {"guest_name": "Maya", "date": "2026-08-08", "time": "19:00", "party_size": 2},
        call_id="reservation",
    )
    result = _make_result(
        scenario,
        executor,
        exchanges=[
            ("What date and name should I use?", "August 8, under Maya."),
            ("What time works?", "Seven p.m., please."),
        ],
        final_answer="Your reservation for Maya is confirmed on August 8 at 7 p.m.",
    )

    grade = grade_procedure(
        scenario,
        result,
        initial_state={},
        final_state=executor.snapshot(),
        executions=executor.executions,
    )
    apply_procedure_grade(result, grade)

    assert grade.sop_id == ""
    assert grade.steps == []
    assert result.task_metrics["task_completed"] is True
    assert "procedure" not in result.task_metrics
    assert "sop_passed" not in result.task_metrics
    assert result_row(scenario, result, offline=True)["sop_status"] == "not_applicable"


def test_correct_reservation_passes_when_the_caller_volunteers_details_and_a_preferred_tool_is_skipped(
    restaurant_dataset: ScenarioDataset,
    restaurant_facts: dict[str, object],
) -> None:
    scenario = _scenario(restaurant_dataset, "restaurant_date_correction")
    executor = RestaurantTools(initial_state={}, facts=restaurant_facts)
    executor.execute(
        "create_reservation",
        {"guest_name": "Maya", "date": "2026-08-08", "time": "19:00", "party_size": 2},
        call_id="actual-reservation",
    )
    result = _make_result(
        scenario,
        executor,
        exchanges=[
            ("Sure, what time would you like?", "I actually need August 8 instead."),
            ("Got it, August 8th. What time should I check?", "Can you put it under Maya, please?"),
            ("Sure, just need the time for August 8th.", "7 p.m. works for me."),
        ],
        final_answer="You're confirmed for August 8th at 7 p.m. for two. Your confirmation number is R-001.",
    )
    procedure = grade_procedure(
        scenario,
        result,
        initial_state={},
        final_state=executor.snapshot(),
        executions=executor.executions,
    )

    apply_procedure_grade(result, procedure)
    row = result_row(scenario, result, offline=True)

    assert result.task_status == "passed"
    assert result.task_metrics["task_completed"] is True
    assert result.task_metrics["outcome_state_satisfied"] is True
    assert result.task_metrics["sop_passed"] is False
    assert result.task_metrics["tool_call_coverage"] == 0.5
    assert row["status"] == "passed"
    assert row["task_completed"] is True
    assert row["tool_calls"] == "1/2"
    assert row["tool_accuracy"] == 0.5
    assert row["sop_status"] == "failed"
    assert row["final_state_status"] == "passed"
    assert row["assessment"]["passed"] is True
    assert row["assessment"]["source"] == "deterministic"
    assert next(check for check in row["assessment"]["checks"] if check["id"] == "application_state")["status"] == (
        "passed"
    )

    apply_semantic_completion(result, {"task_completion": {"completed": True}})

    assert result.task_status == "passed"
    assert result.task_metrics["semantic_task_completed"] is True
    assert result.task_metrics["sop_passed"] is False
    assert result.task_metrics["outcome_assessment"]["source"] == "semantic_judge"


def test_semantic_completion_cannot_override_an_incorrect_application_state(
    restaurant_dataset: ScenarioDataset,
    restaurant_facts: dict[str, object],
) -> None:
    scenario = _scenario(restaurant_dataset, "restaurant_date_correction")
    executor = RestaurantTools(initial_state={}, facts=restaurant_facts)
    executor.execute(
        "create_reservation",
        {"guest_name": "Maya", "date": "2026-08-07", "time": "19:00", "party_size": 2},
        call_id="incorrect-reservation",
    )
    result = _make_result(
        scenario,
        executor,
        final_answer="You're confirmed for August 8th at 7 p.m. for two.",
    )
    procedure = grade_procedure(
        scenario,
        result,
        initial_state={},
        final_state=executor.snapshot(),
        executions=executor.executions,
    )

    apply_procedure_grade(result, procedure)
    apply_semantic_completion(result, {"task_completion": {"completed": True}})

    assert result.task_status == "incomplete"
    assert result.task_metrics["semantic_task_completed"] is True
    assert result.task_metrics["outcome_state_satisfied"] is False
    assert result.task_metrics["task_completed"] is False
    assert (
        next(
            check for check in result.task_metrics["outcome_assessment"]["checks"] if check["id"] == "semantic_outcome"
        )["status"]
        == "passed"
    )
    assert (
        next(
            check for check in result.task_metrics["outcome_assessment"]["checks"] if check["id"] == "application_state"
        )["status"]
        == "failed"
    )


def test_semantic_completion_cannot_override_a_prohibited_application_tool(
    restaurant_dataset: ScenarioDataset,
    restaurant_facts: dict[str, object],
) -> None:
    scenario = _scenario(restaurant_dataset, "restaurant_cancel_unauthorized")
    executor = RestaurantTools(initial_state=scenario.application.initial_state, facts=restaurant_facts)
    executor.executions.append(
        {
            "call_id": "unauthorized-attempt",
            "name": "cancel_reservation",
            "arguments": {"reservation_id": "R-200"},
            "status": "failed",
            "output": {"ok": False, "error": "Not authorized to cancel reservation R-200"},
        }
    )
    result = _make_result(
        scenario,
        executor,
        final_answer="I can't cancel a reservation that you aren't authorized to manage.",
    )
    procedure = grade_procedure(
        scenario,
        result,
        initial_state=scenario.application.initial_state,
        final_state=executor.snapshot(),
        executions=executor.executions,
    )

    apply_procedure_grade(result, procedure)
    apply_semantic_completion(result, {"task_completion": {"completed": True}})

    assert result.task_status == "incomplete"
    assert result.task_metrics["outcome_state_satisfied"] is True
    assert result.task_metrics["prohibited_tool_call_count"] == 1
    assert result.task_metrics["task_completed"] is False
    assert (
        next(
            check
            for check in result.task_metrics["outcome_assessment"]["checks"]
            if check["id"] == "authorized_actions"
        )["status"]
        == "failed"
    )


def test_state_change_must_be_communicated_after_the_completed_tool(
    restaurant_dataset: ScenarioDataset,
    restaurant_facts: dict[str, object],
) -> None:
    scenario = _scenario(restaurant_dataset, "restaurant_date_correction")
    executor = RestaurantTools(initial_state={}, facts=restaurant_facts)
    arguments = {"guest_name": "Maya", "date": "2026-08-08", "time": "19:00", "party_size": 2}
    executor.execute("create_reservation", arguments, call_id="actual-reservation")
    timeline = Timeline()
    timeline.add_user_utterance(0, 100, scenario.input.text, action="OPENING")
    timeline.add_transcript("assistant", 150, 250, "Your reservation is confirmed.", "turn.done")
    timeline.apply_event(
        {
            "type": "session.delegation.created",
            "offset_ms": 300,
            "delegation": {"target": "responses", "response_id": "response-test"},
        }
    )
    timeline.apply_event(
        {
            "type": "tool.completed",
            "offset_ms": 400,
            "name": "create_reservation",
            "call_id": "actual-reservation",
            "arguments": arguments,
            "result": executor.executions[0]["output"],
        }
    )
    timeline.add_user_utterance(500, 600, "Thanks, goodbye.", action="STOP")
    result = build_result(
        scenario,
        timeline,
        caller_mode="offline_fixture",
        caller_actions={"STOP": 1},
        caller_audio_ms=200,
        termination_reason="user_stopped",
    )

    procedure = grade_procedure(
        scenario,
        result,
        initial_state={},
        final_state=executor.snapshot(),
        executions=executor.executions,
    )
    apply_procedure_grade(result, procedure)

    assessment = result.task_metrics["outcome_assessment"]
    grounded = next(check for check in assessment["checks"] if check["id"] == "grounded_assistant_response")
    assert grounded["status"] == "failed"
    assert grounded["evidence"]["last_completed_tool_ms"] == 400
    assert result.task_metrics["task_completed"] is False


def test_outcome_judge_receives_state_and_actual_tools_not_a_mandatory_procedure(
    restaurant_dataset: ScenarioDataset,
    restaurant_facts: dict[str, object],
) -> None:
    scenario = _scenario(restaurant_dataset, "restaurant_date_correction")
    executor = RestaurantTools(initial_state={}, facts=restaurant_facts)
    executor.execute(
        "create_reservation",
        {"guest_name": "Maya", "date": "2026-08-08", "time": "19:00", "party_size": 2},
        call_id="actual-reservation",
    )
    result = _make_result(
        scenario,
        executor,
        final_answer="You're confirmed for August 8th at 7 p.m. for two.",
    )
    procedure = grade_procedure(
        scenario,
        result,
        initial_state={},
        final_state=executor.snapshot(),
        executions=executor.executions,
    )
    apply_procedure_grade(result, procedure)

    prompt = _judge_input(scenario, result, "task_understanding")
    payload = json.loads(prompt.split("EVAL RECORD:\n", maxsplit=1)[1])

    assert payload["scenario"]["expected_final_state"] == scenario.expected.state
    assert payload["scenario"]["expected_response"] == scenario.simulation_goal
    assert all(criterion in payload["scenario"]["success_criteria"] for criterion in scenario.expected.criteria)
    assert payload["scenario"]["preferred_tool_calls"] == [
        tool.model_dump() for tool in scenario.expected.tools.required
    ]
    assert "expected_tool_calls" not in payload["scenario"]
    assert "standard_operating_procedure" not in payload["scenario"]
    assert "procedure_evidence" not in payload["observed"]
    assert payload["observed"]["tool_executions"] == executor.executions
    assert payload["observed"]["tool_executions"][0]["output"]["reservation_created"] is True
    assert [event for event in payload["observed"]["agent_events"] if event.get("kind") == "tool"] == [
        {"kind": "tool", **execution} for execution in executor.executions
    ]
    assert payload["observed"]["outcome_state_satisfied"] is True
    assert payload["observed"]["verified_outcome_assessment"]["passed"] is True
    assert payload["observed"]["assistant_responses"]
    assert payload["conversation"]
    assert "transcript" not in payload


@pytest.mark.parametrize("value", [0, 9, -1])
@pytest.mark.asyncio
async def test_concurrency_is_bounded(value: int, tmp_path: Path) -> None:
    args = parse_args(["--offline", "--concurrency", str(value), "--results-dir", str(tmp_path)])

    with pytest.raises(ValueError, match="between 1 and 8"):
        await run_evals(args)


@pytest.mark.asyncio
async def test_parallel_restaurant_conversations_have_isolated_application_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    args = parse_args(
        [
            "--offline",
            "--concurrency",
            "4",
            "--tick-ms",
            "100",
            "--max-duration-seconds",
            "30",
            "--results-dir",
            str(tmp_path),
        ]
    )

    run_dir = await run_evals(args)

    report = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    rows = report["results"]

    assert len(rows) == 11
    assert all(row["status"] == "passed" for row in rows)
    assert all(row["metrics"]["task"]["turns"]["actual"] >= 7 for row in rows)
    recovery = next(row for row in rows if row["scenario_id"] == "restaurant_unavailable")
    assert recovery["metrics"]["task"]["tool_calls"] == {"actual": 3, "expected": 3}
    assert report["run"]["configuration"]["concurrency"] == 4
    assert report["summary"] == {
        "total": 11,
        "passed": 11,
        "failed": 0,
        "infrastructure_errors": 0,
    }
    bookings = [
        json.loads((run_dir / "transcripts" / f"{row['scenario_id']}.json").read_text(encoding="utf-8"))
        for row in rows
        if row["scenario_id"].startswith("restaurant_booking_")
        or row["scenario_id"]
        in {
            "restaurant_date_correction",
            "restaurant_party_correction",
            "restaurant_multiple_corrections",
            "restaurant_interrupted_alternative",
        }
    ]
    assert all(
        item["task_metrics"]["final_application_state"]["reservations"][0]["reservation_id"] == "R-001"
        for item in bookings
    )
    assert len({item["run_id"] for item in bookings}) == len(bookings)
