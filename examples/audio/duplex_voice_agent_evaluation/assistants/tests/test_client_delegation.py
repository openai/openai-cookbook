"""Client-delegation protocol, context, memory, tools, and endpoint isolation."""

from __future__ import annotations

import asyncio
import base64
import io
import json
import time
from dataclasses import dataclass
from typing import Any

import pytest
from aiohttp.test_utils import TestClient, TestServer

from assistants import ClientDelegatedAssistant, ResponsesManagedAssistant, create_assistant
from assistants.client.backend import ApplicationBackend, DelegationHandoff
from assistants.client.delegation import ClientDelegationController
from assistants.client.memory import TranscriptLedger
from assistants.client.openai_backend import ResponsesBackend, ResponsesConversation, _safe_stream_event
from assistants.client.protocol import build_context_events, client_delegation, split_context_text
from assistants.client.remote import RemoteClientDelegationController
from assistants.client.service import create_app
from assistants.client.session import build_client_session
from assistants.client.tools.restaurant import RestaurantOfflineBehavior as ClientOfflineBehavior
from assistants.client.tools.restaurant import RestaurantTools as ClientRestaurantTools
from assistants.config import LiveAgentSettings, build_assistant_session
from assistants.frontend.assistant import LiveFrontend
from assistants.resources import assistant_resources
from assistants.responses.tools.restaurant import RestaurantOfflineBehavior as ResponsesOfflineBehavior
from assistants.responses.tools.restaurant import RestaurantTools
from assistants.runtime import RemoteToolObserver
from run_harness.simulation.models import Settings
from shared.observability.timeline import Timeline, project_agent_event
from shared.scenarios import Scenario
from shared.single_turn.runtime import collect_live_response

SERVICE_TOKEN = "test-client-service-token-0123456789abcdef"
AUTH_HEADERS = {"Authorization": f"Bearer {SERVICE_TOKEN}"}


@dataclass(frozen=True, slots=True)
class FakeEvent:
    payload: dict[str, Any]

    def model_dump(self, **_: Any) -> dict[str, Any]:
        return dict(self.payload)


class FakeStream:
    def __init__(self, events: list[dict[str, Any]]) -> None:
        self.events = iter(events)

    def __aiter__(self) -> FakeStream:
        return self

    async def __anext__(self) -> FakeEvent:
        try:
            return FakeEvent(next(self.events))
        except StopIteration as error:
            raise StopAsyncIteration from error


class FakeResponses:
    def __init__(self, batches: list[list[dict[str, Any]]]) -> None:
        self.batches = iter(batches)
        self.requests: list[dict[str, Any]] = []

    async def create(self, **request: Any) -> FakeStream:
        self.requests.append(request)
        return FakeStream(next(self.batches))


class FakeOpenAI:
    def __init__(self, batches: list[list[dict[str, Any]]]) -> None:
        self.responses = FakeResponses(batches)


def scenario() -> Scenario:
    return Scenario(
        id="client_delegation",
        title="Delegated availability request",
        interaction="multi_turn",
        input={"text": "Is a table available?"},
        expected={"answer": "A table is available.", "criteria": ["Confirm availability."]},
        simulation_parameters={"goal": "Check availability", "persona": {"id": "caller", "description": "Caller"}},
    )


def function_response(identifier: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": identifier,
        "status": "completed",
        "output": [
            {
                "id": "item_tool",
                "type": "function_call",
                "status": "completed",
                "name": "check_availability",
                "call_id": "call_availability",
                "arguments": json.dumps(arguments),
            }
        ],
    }


def message_response(identifier: str, text: str) -> dict[str, Any]:
    return {
        "id": identifier,
        "status": "completed",
        "output": [
            {
                "id": "item_message",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": text}],
            }
        ],
    }


def test_client_session_contains_no_backend_instructions_tools_or_expected_answer() -> None:
    event = build_assistant_session(
        LiveAgentSettings(assistant_mode="client"),
        instructions="Speak naturally and delegate application work.",
        backend_instructions="Private application instructions.",
        tools=[{"type": "function", "name": "secret_tool"}],
    )

    assert event["session"]["delegation"] == {"type": "client"}
    assert "Private application instructions" not in json.dumps(event)
    assert "secret_tool" not in json.dumps(event)


def test_assistant_selection_keeps_independent_implementations(monkeypatch: pytest.MonkeyPatch) -> None:
    # Exercise the real factory/frontends without constructing an external SDK
    # transport. Proxy support is unrelated to selecting a delegation mode.
    monkeypatch.setattr("assistants.client.assistant.ResponsesBackend", lambda **_: FakeBackend())
    executor = RestaurantTools(initial_state={}, facts={})
    managed = create_assistant(scenario=scenario(), settings=Settings(), api_key="test-key", tool_executor=executor)
    client = create_assistant(
        scenario=scenario(),
        settings=Settings(assistant_mode="client"),
        api_key="test-key",
        tool_executor=executor,
    )

    assert isinstance(managed, ResponsesManagedAssistant)
    assert isinstance(client, ClientDelegatedAssistant)
    assert isinstance(managed, LiveFrontend)
    assert isinstance(client, LiveFrontend)
    assert type(managed) is not type(client)


def test_assistant_resources_share_frontend_but_keep_backend_tools_independent() -> None:
    managed = assistant_resources(assistant_mode="responses")
    client = assistant_resources(assistant_mode="client")

    assert managed.system_prompt_file == client.system_prompt_file
    assert managed.system_prompt_file.parts[-3:] == ("frontend", "prompts", "voice.txt")
    assert managed.backend_system_prompt_file.parts[-3:] == ("responses", "prompts", "backend.txt")
    assert client.backend_system_prompt_file.parts[-3:] == ("client", "prompts", "backend.txt")
    assert managed.tools_file != client.tools_file
    assert managed.tools_file.parts[-3:] == ("responses", "tools", "definitions.json")
    assert client.tools_file.parts[-3:] == ("client", "tools", "definitions.json")
    assert managed.facts_file != client.facts_file
    assert managed.facts_file.parts[-3:] == ("responses", "tools", "restaurant_facts.json")
    assert client.facts_file.parts[-3:] == ("client", "tools", "restaurant_facts.json")
    assert isinstance(managed.create_executor({}, managed.load_facts()), RestaurantTools)
    assert isinstance(client.create_executor({}, client.load_facts()), ClientRestaurantTools)
    assert isinstance(
        managed.create_offline_behavior(conversation_context="", initial_state={}, facts=managed.load_facts()),
        ResponsesOfflineBehavior,
    )
    assert isinstance(
        client.create_offline_behavior(conversation_context="", initial_state={}, facts=client.load_facts()),
        ClientOfflineBehavior,
    )


@pytest.mark.parametrize("assistant_mode", ["responses", "client"])
def test_assistant_prompts_are_loaded_from_mode_specific_text_files(
    assistant_mode: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_LIVE_INSTRUCTIONS", "Stale frontend environment prompt.")
    monkeypatch.setenv("OPENAI_LIVE_BACKEND_INSTRUCTIONS", "Stale backend environment prompt.")
    resources = assistant_resources(assistant_mode=assistant_mode)

    settings = Settings(assistant_mode=assistant_mode)

    assert settings.agent_instructions == resources.system_prompt_file.read_text(encoding="utf-8").strip()
    assert settings.backend_instructions == resources.backend_system_prompt_file.read_text(encoding="utf-8").strip()


def test_client_session_hydrates_authorized_history() -> None:
    initial_items = [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": "For two."}]}]
    event = build_client_session(instructions="Delegate reservations.", voice="marin", initial_items=initial_items)
    assert event["session"]["input"] == initial_items
    event["session"]["input"][0]["content"][0]["text"] = "Changed."
    assert initial_items[0]["content"][0]["text"] == "For two."


def test_context_append_is_correlated_utf8_safe_and_never_raw_function_output() -> None:
    text = "Confirmed ✓ " * 90
    events = build_context_events("delegation_1", text)
    assert len(events) > 1
    assert "".join(event["content"] for event in events) == text
    assert all(event["type"] == "session.commentary.append" for event in events)
    assert all(event["delegation_id"] == "delegation_1" for event in events)
    assert all(len(event["content"].encode("utf-8")) <= 400 for event in events)
    assert split_context_text("", max_bytes=400) == []


def test_client_delegation_requires_only_target_and_identifier() -> None:
    item = {"id": "delegation_1", "target": "client"}
    assert client_delegation({"type": "session.delegation.created", "delegation": item}) == (
        "delegation_1",
        "Resolve the current user request and corrections from the voice conversation "
        "and verified application context.",
    )
    assert (
        client_delegation({"type": "session.delegation.created", "delegation": {**item, "target": "responses"}}) is None
    )
    assert client_delegation({"type": "session.delegation.created", "delegation": {**item, "id": ""}}) is None


def test_transcript_handoffs_are_incremental_and_actual_transcripts_win() -> None:
    ledger = TranscriptLedger()
    ledger.record("user", "Book Friday", 100, 400, "turn_1", projected=True)
    ledger.record("user", "Book Friday", 100, 400, "transcript_1")
    first = ledger.consume_srt()
    assert first.count("Book Friday") == 1
    assert ledger.consume_srt() == ""
    ledger.record("user", "Actually, Saturday.", 800, 1100, "transcript_2")
    second = ledger.consume_srt()
    assert "Actually, Saturday." in second
    assert "Book Friday" not in second


def test_application_owned_conversation_replays_history_without_server_storage() -> None:
    conversation = ResponsesConversation()
    inputs = conversation.begin(DelegationHandoff("Book Friday", "USER: Book Friday"))
    request = conversation.request_payload(
        model="backend", instructions="Help", tools=[], inputs=inputs, reasoning_effort="none", max_output_tokens=500
    )
    assert request["store"] is False
    assert "previous_response_id" not in request
    conversation.record_response(message_response("resp_1", "What time?"))
    followup = conversation.begin(DelegationHandoff("At seven", "USER: At seven", follow_up=True))
    followup_request = conversation.request_payload(
        model="backend", instructions="Help", tools=[], inputs=followup, reasoning_effort="none", max_output_tokens=500
    )
    assert "previous_response_id" not in followup_request
    assert [item["type"] for item in followup_request["input"]] == ["message", "message", "message"]


def test_client_owned_conversation_replays_encrypted_reasoning_and_tool_outputs() -> None:
    conversation = ResponsesConversation()
    first = conversation.begin(DelegationHandoff("Check Friday", "USER: Check Friday"))
    request = conversation.request_payload(
        model="backend", instructions="Help", tools=[], inputs=first, reasoning_effort="low", max_output_tokens=500
    )
    assert request["store"] is False
    assert request["include"] == ["reasoning.encrypted_content"]
    assert "previous_response_id" not in request
    conversation.record_response(
        {
            "id": "resp_1",
            "output": [
                {"type": "reasoning", "encrypted_content": "encrypted"},
                {"type": "function_call", "name": "check_availability", "call_id": "call_1", "arguments": "{}"},
            ],
        }
    )
    replay = conversation.continue_tools([{"type": "function_call_output", "call_id": "call_1", "output": "{}"}])
    assert [item["type"] for item in replay] == ["message", "reasoning", "function_call", "function_call_output"]
    with pytest.raises(RuntimeError, match="encrypted reasoning"):
        conversation.record_response({"id": "resp_2", "output": [{"type": "reasoning"}]})


def test_streamed_activity_never_exposes_encrypted_reasoning_or_backend_instructions() -> None:
    visible = _safe_stream_event(
        {
            "type": "response.output_item.added",
            "response": {"id": "resp_1", "instructions": "Private instructions", "tools": [{"name": "private"}]},
            "item": {"id": "reasoning_1", "type": "reasoning", "encrypted_content": "sensitive-ciphertext"},
        }
    )
    rendered = json.dumps(visible)
    assert "sensitive-ciphertext" not in rendered
    assert "Private instructions" not in rendered
    assert "private" not in rendered


@pytest.mark.asyncio
async def test_backend_executes_each_tool_once_and_omits_empty_optional_arguments() -> None:
    first = function_response("resp_1", {"date": "2026-08-07", "time": "19:00", "party_size": 2, "seating": ""})
    second = message_response("resp_2", "A table for two is available.")
    client = FakeOpenAI(
        [
            [
                {"type": "response.created", "response": {"id": "resp_1"}},
                {"type": "response.completed", "response": first},
            ],
            [{"type": "response.completed", "response": second}],
        ]
    )
    calls: list[tuple[str, dict[str, Any], str]] = []
    events: list[dict[str, Any]] = []

    async def execute(name: str, arguments: dict[str, Any], call_id: str) -> dict[str, Any]:
        calls.append((name, arguments, call_id))
        return {"ok": True, "available": True}

    backend = ResponsesBackend(
        api_key="test-key",
        model="test-model",
        instructions="Use application tools.",
        tools=[
            {
                "type": "function",
                "name": "check_availability",
                "parameters": {"required": ["date", "time", "party_size"]},
            }
        ],
        reasoning_effort="none",
        max_output_tokens=500,
        execute_tool=execute,
        client=client,  # type: ignore[arg-type]
    )

    answer = await backend.run(DelegationHandoff("Check Friday", "USER: Check Friday"), _append_async(events))

    assert answer == "A table for two is available."
    assert calls == [
        ("check_availability", {"date": "2026-08-07", "time": "19:00", "party_size": 2}, "call_availability")
    ]
    assert [event["type"] for event in events if event["type"].startswith("tool.")] == ["tool.called", "tool.completed"]
    assert client.responses.requests[1]["store"] is False
    assert "previous_response_id" not in client.responses.requests[1]
    assert [item["type"] for item in client.responses.requests[1]["input"]] == [
        "message",
        "function_call",
        "function_call_output",
    ]


class FakeBackend:
    def __init__(self, *, execute_tool: Any | None = None) -> None:
        self.execute_tool = execute_tool
        self.calls: list[DelegationHandoff] = []
        self.closed = False

    async def run(self, handoff: DelegationHandoff, emit: Any) -> str:
        self.calls.append(handoff)
        if self.execute_tool is not None:
            result = await self.execute_tool(
                "check_availability",
                {"date": "2026-08-07", "time": "19:00", "party_size": 2},
                "call_remote",
            )
            await emit({"type": "tool.completed", "name": "check_availability", "result": result})
        return "A table for two is available."

    async def close(self) -> None:
        self.closed = True


def test_any_application_backend_can_implement_the_provider_neutral_contract() -> None:
    assert isinstance(FakeBackend(), ApplicationBackend)


@pytest.mark.asyncio
async def test_controller_deduplicates_delegations_and_injects_correlated_text() -> None:
    backend = FakeBackend()
    sent: list[dict[str, Any]] = []
    emitted: list[dict[str, Any]] = []
    controller = ClientDelegationController(
        backend=backend,
        send_live=_append_async(sent),
        emit=_append_async(emitted),
        initial_items=[{"role": "assistant", "content": [{"type": "output_text", "text": "What day should I check?"}]}],
    )
    await controller.observe(
        {"type": "session.input_transcript.delta", "start_ms": 200, "end_ms": 500, "delta": "Friday."}
    )
    event = {
        "type": "session.delegation.created",
        "delegation": {
            "id": "delegation_1",
            "target": "client",
            "content": [{"type": "input_text", "text": "Check Friday."}],
        },
    }
    await controller.observe(event)
    await controller.observe(event)
    await controller.wait()

    assert len(backend.calls) == 1
    assert "What day should I check?" in backend.calls[0].transcript_srt
    assert "Friday." in backend.calls[0].transcript_srt
    assert sent[0]["type"] == "session.commentary.append"
    assert sent[0]["delegation_id"] == "delegation_1"
    assert sent[0]["content"] == "A table for two is available."
    assert emitted[-1]["type"] == "client_delegation.completed"
    await controller.close()
    assert backend.closed


def test_client_delegation_remains_active_until_its_correlated_result_is_injected() -> None:
    timeline = Timeline()
    timeline.apply_event(
        {
            "type": "session.delegation.created",
            "delegation": {"id": "delegation_1", "target": "client"},
        }
    )
    timeline.apply_event({"type": "response.created", "response": {"id": "response_1"}})
    timeline.apply_event({"type": "response.completed", "response": {"id": "response_1"}})
    assert timeline.delegation_active
    timeline.apply_event({"type": "client_delegation.completed", "delegation_id": "delegation_1"})
    assert not timeline.delegation_active


@pytest.mark.parametrize("terminal", ["client_delegation.completed", "client_delegation.failed"])
def test_client_terminal_event_retains_its_id_time_and_exact_replay_interval(terminal: str) -> None:
    timeline = Timeline()
    timeline.apply_event(
        {"type": "session.delegation.created", "offset_ms": 150, "delegation": {"id": "d1", "target": "client"}}
    )
    timeline.apply_event(project_agent_event({"type": terminal, "delegation_id": "d1"}, 450))

    # The old runtime forgot this terminal event when rebuilding metrics later.
    assert [event.event_type for event in timeline.agent_events] == ["session.delegation.created", terminal]
    assert timeline.agent_events[-1].model_dump()["delegation_id"] == "d1"
    assert timeline.agent_events[-1].timestamp_ms == 450
    assert not timeline.delegation_active
    assert timeline.delegation_intervals(1_000) == ((150, 450),)


def test_client_failure_from_the_local_controller_closes_only_its_correlated_work() -> None:
    timeline = Timeline()
    timeline.apply_event(
        {"type": "session.delegation.created", "offset_ms": 150, "delegation": {"id": "d1", "target": "client"}}
    )
    timeline.apply_event(
        {"type": "session.delegation.created", "offset_ms": 200, "delegation": {"id": "d2", "target": "client"}}
    )
    timeline.apply_event(
        project_agent_event(
            {
                "type": "error",
                "delegation_id": "d1",
                "error": {"code": "client_delegation_failed", "message": "failed"},
            },
            450,
        )
    )
    assert timeline.agent_events[-1].event_type == "client_delegation.failed"
    assert timeline.agent_events[-1].timestamp_ms == 450
    assert timeline.delegation_active
    timeline.apply_event({"type": "client_delegation.completed", "delegation_id": "d2", "offset_ms": 650})
    assert not timeline.delegation_active
    assert timeline.delegation_intervals(1_000) == ((150, 650),)


def test_unknown_client_terminal_does_not_close_known_work_and_replay_clips_to_capture() -> None:
    timeline = Timeline()
    timeline.apply_event(
        {"type": "session.delegation.created", "offset_ms": 150, "delegation": {"id": "d1", "target": "client"}}
    )
    timeline.apply_event({"type": "client_delegation.completed", "delegation_id": "other", "offset_ms": 300})
    assert timeline.delegation_active
    timeline.apply_event({"type": "client_delegation.completed", "delegation_id": "d1", "offset_ms": 650})
    assert timeline.delegation_intervals(450) == ((150, 450),)
    assert timeline.delegation_intervals(650) == ((150, 650),)


def test_failure_of_one_response_does_not_clear_a_concurrent_same_name_tool() -> None:
    timeline = Timeline()
    for response_id, call_id, start in (("r1", "c1", 100), ("r2", "c2", 150)):
        timeline.apply_event(
            {
                "type": "session.delegation.created",
                "offset_ms": start,
                "delegation": {"target": "responses", "response_id": response_id},
            }
        )
        timeline.apply_event(
            {
                "type": "tool.called",
                "offset_ms": start + 10,
                "response_id": response_id,
                "call_id": call_id,
                "name": "lookup",
            }
        )
    timeline.apply_event({"type": "response.completed", "offset_ms": 200, "response": {"id": "r2"}})
    timeline.apply_event({"type": "response.failed", "offset_ms": 250, "response": {"id": "r1"}})
    assert timeline.delegation_active
    timeline.apply_event(
        {"type": "tool.completed", "offset_ms": 350, "response_id": "r2", "call_id": "c2", "name": "lookup"}
    )
    timeline.apply_event(
        {"type": "response.created", "offset_ms": 400, "response": {"id": "followup", "previous_response_id": "r2"}}
    )
    timeline.apply_event({"type": "response.completed", "offset_ms": 450, "response": {"id": "followup"}})
    assert not timeline.delegation_active
    assert timeline.delegation_intervals(600) == ((100, 450),)


def test_correlated_followup_arriving_before_tool_receipt_does_not_leave_work_stuck() -> None:
    timeline = Timeline()
    events = [
        {
            "type": "session.delegation.created",
            "offset_ms": 100,
            "delegation": {"target": "responses", "response_id": "r1"},
        },
        {"type": "tool.called", "offset_ms": 150, "response_id": "r1", "call_id": "c1", "name": "lookup"},
        {"type": "response.created", "offset_ms": 200, "response": {"id": "r2", "previous_response_id": "r1"}},
        {"type": "response.completed", "offset_ms": 250, "response": {"id": "r1"}},
        {"type": "tool.completed", "offset_ms": 300, "response_id": "r1", "call_id": "c1", "name": "lookup"},
        {"type": "response.completed", "offset_ms": 350, "response": {"id": "r2"}},
    ]
    for event in events:
        timeline.apply_event(event)
    assert not timeline.delegation_active
    assert timeline.delegation_intervals(600) == ((100, 350),)


def test_compact_lifecycle_records_round_trip_client_ownership_and_followup_correlation() -> None:
    timeline = Timeline()
    events = [
        {"type": "session.delegation.created", "offset_ms": 100, "delegation": {"id": "d1", "target": "client"}},
        {"type": "response.created", "offset_ms": 120, "delegation_id": "d1", "response": {"id": "r1"}},
        {"type": "tool.called", "offset_ms": 150, "delegation_id": "d1", "response_id": "r1", "call_id": "c1"},
        {"type": "client_delegation.completed", "offset_ms": 350, "delegation_id": "d1"},
    ]
    for event in events:
        timeline.apply_event(event)
    replay = Timeline()
    saved = json.loads(json.dumps(timeline.delegation_events()))
    for event in saved:
        replay.apply_event(event)
    assert replay.delegation_intervals(600) == timeline.delegation_intervals(600) == ((100, 350),)
    assert replay.delegation_active is timeline.delegation_active is False
    assert saved[1]["delegation_id"] == "d1"
    assert saved[2]["call_id"] == "c1"


@pytest.mark.parametrize("target", ["client", "responses"])
def test_late_start_receipt_cannot_reopen_an_already_completed_identifier(target: str) -> None:
    timeline = Timeline()
    if target == "client":
        terminal = {"type": "client_delegation.completed", "delegation_id": "d1", "offset_ms": 450}
        item = {"id": "d1", "target": "client"}
    else:
        terminal = {"type": "response.completed", "response": {"id": "r1"}, "offset_ms": 450}
        item = {"id": "d1", "target": "responses", "response_id": "r1"}
    timeline.apply_event(terminal)
    timeline.apply_event({"type": "session.delegation.created", "offset_ms": 150, "delegation": item})
    assert not timeline.delegation_active
    assert timeline.delegation_intervals(600) == ((150, 450),)


@pytest.mark.parametrize("pending_kind", ["unbound", "followup"])
def test_explicit_client_owner_cannot_claim_an_unrelated_legacy_chain(pending_kind: str) -> None:
    timeline = Timeline()
    if pending_kind == "unbound":
        timeline.apply_event(
            {
                "type": "session.delegation.created",
                "offset_ms": 100,
                "delegation": {"id": "managed", "target": "responses"},
            }
        )
    else:
        for event in [
            {
                "type": "session.delegation.created",
                "offset_ms": 100,
                "delegation": {"target": "responses", "response_id": "managed"},
            },
            {"type": "tool.called", "offset_ms": 120, "response_id": "managed", "call_id": "c1"},
            {"type": "tool.completed", "offset_ms": 150, "response_id": "managed", "call_id": "c1"},
            {"type": "response.completed", "offset_ms": 180, "response": {"id": "managed"}},
        ]:
            timeline.apply_event(event)
    timeline.apply_event(
        {"type": "session.delegation.created", "offset_ms": 200, "delegation": {"id": "client", "target": "client"}}
    )
    timeline.apply_event(
        {"type": "response.created", "offset_ms": 250, "delegation_id": "client", "response": {"id": "client-response"}}
    )
    timeline.apply_event({"type": "client_delegation.completed", "offset_ms": 300, "delegation_id": "client"})
    assert timeline.delegation_active
    assert timeline.delegation_intervals(600) == ((100, 600),)


def test_late_completed_followup_start_still_reconciles_its_parent() -> None:
    timeline = Timeline()
    events = [
        {
            "type": "session.delegation.created",
            "offset_ms": 100,
            "delegation": {"target": "responses", "response_id": "r1"},
        },
        {"type": "tool.called", "offset_ms": 150, "response_id": "r1", "call_id": "c1"},
        {"type": "response.completed", "offset_ms": 200, "response": {"id": "r1"}},
        {"type": "tool.completed", "offset_ms": 250, "response_id": "r1", "call_id": "c1"},
        {"type": "response.completed", "offset_ms": 400, "response": {"id": "r2"}},
        {"type": "response.created", "offset_ms": 300, "response": {"id": "r2", "previous_response_id": "r1"}},
    ]
    for event in events:
        timeline.apply_event(event)
    assert not timeline.delegation_active
    assert timeline.delegation_intervals(600) == ((100, 400),)


def test_duplicate_tool_start_and_terminal_cannot_reopen_finished_work() -> None:
    timeline = Timeline()
    called = {"type": "tool.called", "offset_ms": 150, "response_id": "r1", "call_id": "c1"}
    completed = {"type": "tool.completed", "offset_ms": 250, "response_id": "r1", "call_id": "c1"}
    events = [
        {
            "type": "session.delegation.created",
            "offset_ms": 100,
            "delegation": {"target": "responses", "response_id": "r1"},
        },
        called,
        {"type": "response.completed", "offset_ms": 200, "response": {"id": "r1"}},
        completed,
        {"type": "response.created", "offset_ms": 300, "response": {"id": "r2", "previous_response_id": "r1"}},
        {"type": "response.completed", "offset_ms": 400, "response": {"id": "r2"}},
        called,
        completed,
    ]
    for event in events:
        timeline.apply_event(event)
    assert not timeline.delegation_active
    assert timeline.delegation_intervals(600) == ((100, 400),)


def test_failed_response_late_tool_receipts_cannot_create_a_followup() -> None:
    timeline = Timeline()
    events = [
        {
            "type": "session.delegation.created",
            "offset_ms": 100,
            "delegation": {"target": "responses", "response_id": "r1"},
        },
        {"type": "response.failed", "offset_ms": 300, "response": {"id": "r1"}},
        {"type": "tool.called", "offset_ms": 150, "response_id": "r1", "call_id": "c1"},
        {"type": "tool.completed", "offset_ms": 250, "response_id": "r1", "call_id": "c1"},
    ]
    for event in events:
        timeline.apply_event(event)
    assert not timeline.delegation_active
    assert timeline.delegation_intervals(600) == ((100, 300),)


@pytest.mark.parametrize("terminal", ["tool.completed", "tool.failed"])
def test_tool_terminal_before_start_stays_finished_until_the_followup(terminal: str) -> None:
    timeline = Timeline()
    events = [
        {
            "type": "session.delegation.created",
            "offset_ms": 100,
            "delegation": {"target": "responses", "response_id": "r1"},
        },
        {"type": "response.completed", "offset_ms": 200, "response": {"id": "r1"}},
        {"type": terminal, "offset_ms": 250, "response_id": "r1", "call_id": "c1"},
        {"type": "tool.called", "offset_ms": 150, "response_id": "r1", "call_id": "c1"},
    ]
    for event in events:
        timeline.apply_event(event)
    assert timeline.delegation_active  # The managed chain still needs its follow-up.
    timeline.apply_event(
        {"type": "response.created", "offset_ms": 300, "response": {"id": "r2", "previous_response_id": "r1"}}
    )
    timeline.apply_event({"type": "response.completed", "offset_ms": 400, "response": {"id": "r2"}})
    assert not timeline.delegation_active
    assert timeline.delegation_intervals(600) == ((100, 400),)


def test_completed_response_can_start_real_tool_work_before_its_followup() -> None:
    timeline = Timeline()
    events = [
        {
            "type": "session.delegation.created",
            "offset_ms": 100,
            "delegation": {"target": "responses", "response_id": "r1"},
        },
        {"type": "response.completed", "offset_ms": 150, "response": {"id": "r1"}},
        {"type": "tool.called", "offset_ms": 200, "response_id": "r1", "call_id": "c1"},
        {"type": "tool.completed", "offset_ms": 250, "response_id": "r1", "call_id": "c1"},
    ]
    for event in events:
        timeline.apply_event(event)
    assert timeline.delegation_active
    timeline.apply_event(
        {"type": "response.created", "offset_ms": 300, "response": {"id": "r2", "previous_response_id": "r1"}}
    )
    timeline.apply_event({"type": "response.completed", "offset_ms": 400, "response": {"id": "r2"}})
    assert not timeline.delegation_active
    assert timeline.delegation_intervals(600) == ((100, 150), (200, 400))


@pytest.mark.asyncio
async def test_single_turn_waits_for_client_delegation_after_interim_acknowledgement() -> None:
    events: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    speech = (2_000).to_bytes(2, "little", signed=True) * 480

    class Connection:
        async def send_json(self, _: dict[str, Any]) -> None:
            return None

        async def receive_json(self, *, timeout: float) -> dict[str, Any]:  # noqa: ASYNC109
            return await asyncio.wait_for(events.get(), timeout)

    await events.put(
        {
            "type": "session.delegation.created",
            "delegation": {
                "id": "delegation_1",
                "target": "client",
                "content": [{"type": "input_text", "text": "Book."}],
            },
        }
    )
    await events.put({"type": "session.output_transcript.delta", "start_ms": 0, "end_ms": 20, "delta": "Checking."})
    await events.put({"type": "session.output_audio.delta", "delta": base64.b64encode(speech).decode()})

    async def complete_backend() -> None:
        await asyncio.sleep(0.22)
        await events.put({"type": "client_delegation.completed", "delegation_id": "delegation_1", "text": "Confirmed."})
        await events.put(
            {"type": "session.output_transcript.delta", "start_ms": 1000, "end_ms": 1020, "delta": " Confirmed."}
        )
        await events.put(
            {
                "type": "session.output_audio.delta",
                "start_ms": 200,
                "end_ms": 220,
                "delta": base64.b64encode(bytes(28_800) + speech).decode(),
            }
        )

    pending = asyncio.create_task(complete_backend())
    result = await collect_live_response(
        Connection(),
        io.StringIO(),
        chunk_ms=20,
        sample_rate_hz=24_000,
        timeout_seconds=2,
        trace_started_at=time.monotonic(),
        event_index_state={"value": 0},
        tool_observer=RestaurantTools(initial_state={}, facts={}),
    )
    await pending
    assert "Confirmed." in result["assistant_text"]


@pytest.mark.asyncio
async def test_standalone_assistant_executes_its_own_tools_without_evaluator_callbacks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_RESPONSES_API_KEY", "test-key")
    monkeypatch.setattr(
        "assistants.client.service.ResponsesBackend",
        lambda **kwargs: FakeBackend(execute_tool=kwargs["execute_tool"]),
    )
    async with TestClient(TestServer(create_app(token=SERVICE_TOKEN))) as client:
        assert (await client.get("/health")).status == 200
        async with client.ws_connect("/ws/assistant", headers=AUTH_HEADERS) as socket:
            await socket.send_json(
                {
                    "type": "session.configure",
                    "model": "backend",
                    "instructions": "Use authorized tools.",
                    "tools": [],
                }
            )
            assert (await socket.receive_json())["type"] == "session.ready"
            await socket.send_json(
                {
                    "type": "live.event",
                    "event": {
                        "type": "session.delegation.created",
                        "delegation": {
                            "id": "delegation_remote",
                            "target": "client",
                            "content": [{"type": "input_text", "text": "Check availability."}],
                        },
                    },
                }
            )
            first = await socket.receive_json(timeout=2)
            assert first["type"] == "assistant.event"
            completed = await socket.receive_json(timeout=2)
            injected = await socket.receive_json(timeout=2)
            assert completed["event"]["type"] == "tool.completed"
            assert completed["event"]["call_id"] == "call_remote"
            assert completed["event"]["tool_execution"]["name"] == "check_availability"
            assert completed["event"]["tool_execution"]["status"] == "completed"
            assert completed["event"]["application_state"] == {}
            assert injected["type"] == "live.send"
            assert injected["event"]["type"] == "session.commentary.append"


@pytest.mark.asyncio
async def test_remote_assistant_reports_state_without_executing_tools_in_the_evaluator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_CLIENT_ASSISTANT_ALLOW_INSECURE_LOOPBACK", "true")
    remote_executors: list[RestaurantTools] = []

    def own_tools(_: dict[str, Any]) -> RestaurantTools:
        executor = RestaurantTools(initial_state={}, facts={})
        remote_executors.append(executor)
        return executor

    def backend_factory(_: dict[str, Any], execute_tool: Any) -> ApplicationBackend:
        return FakeBackend(execute_tool=execute_tool)

    observed: list[dict[str, Any]] = []
    sent: list[dict[str, Any]] = []
    completed = asyncio.Event()

    async def observe(event: dict[str, Any]) -> None:
        observed.append(event)
        if event.get("type") == "client_delegation.completed":
            completed.set()

    observer = RemoteToolObserver(initial_state={}, facts={})
    async with TestClient(
        TestServer(create_app(token=SERVICE_TOKEN, backend_factory=backend_factory, tool_factory=own_tools))
    ) as client:
        controller = RemoteClientDelegationController(
            endpoint=str(client.make_url("/ws/assistant")),
            token=SERVICE_TOKEN,
            configuration={"initial_items": []},
            send_live=_append_async(sent),
            emit=observe,
            tool_observer=observer,
        )
        await controller.start()
        try:
            await controller.observe(
                {
                    "type": "session.delegation.created",
                    "delegation": {
                        "id": "remote_delegation",
                        "target": "client",
                        "content": [{"type": "input_text", "text": "Check availability."}],
                    },
                }
            )
            assert controller.pending
            await asyncio.wait_for(controller.wait(), timeout=2)
            assert completed.is_set()
            assert not controller.pending
        finally:
            await controller.close()

    assert len(remote_executors) == 1
    assert len(remote_executors[0].executions) == 1
    assert observer.executions == remote_executors[0].executions
    assert observer.snapshot() == remote_executors[0].snapshot()
    assert any(event["type"] == "tool.completed" for event in observed)
    assert sent[0]["type"] == "session.commentary.append"


@pytest.mark.asyncio
async def test_standalone_assistant_accepts_a_non_openai_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_RESPONSES_API_KEY", raising=False)
    configurations: list[dict[str, Any]] = []

    def backend_factory(configuration: dict[str, Any], execute_tool: Any) -> ApplicationBackend:
        configurations.append(configuration)
        return FakeBackend(execute_tool=execute_tool)

    async with (
        TestClient(TestServer(create_app(token=SERVICE_TOKEN, backend_factory=backend_factory))) as client,
        client.ws_connect("/ws/assistant", headers=AUTH_HEADERS) as socket,
    ):
        await socket.send_json({"type": "session.configure", "model": "customer-owned-backend", "tools": []})

        assert (await socket.receive_json())["type"] == "session.ready"
        assert configurations[0]["model"] == "customer-owned-backend"


def _append_async(items: list[dict[str, Any]]) -> Any:
    async def append(event: dict[str, Any]) -> None:
        items.append(event)

    return append
