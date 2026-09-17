"""Single-turn protocol evidence and completion policy, independent of sockets."""

from __future__ import annotations

import base64
from types import SimpleNamespace

import pytest

from assistants.errors import LiveResponseError
from shared.single_turn.response import ResponseCollector
from shared.single_turn.runtime import CallerAudioCompletion


def collector(completion: CallerAudioCompletion | None = None) -> ResponseCollector:
    observer = SimpleNamespace(executions=[], snapshot=lambda: {"unchanged": True})
    state = ResponseCollector(
        chunk_ms=20, sample_rate_hz=24_000, tool_observer=observer, caller_audio_completion=completion
    )
    state.now_ms = 0
    state.timeline_clock_ms = lambda: state.now_ms
    return state


def speech(state: ResponseCollector, text: str) -> None:
    pcm = (1000).to_bytes(2, "little", signed=True) * 480
    state.observe({"type": "session.output_audio.delta", "delta": base64.b64encode(pcm).decode()}, 0)
    state.observe(
        {
            "type": "session.output_transcript.delta",
            "start_ms": 50_000 + state.now_ms,
            "end_ms": 50_020 + state.now_ms,
            "delta": text,
        },
        0,
    )


def settled(state: ResponseCollector, *, pending_tools: bool = False) -> bool:
    state.now_ms += 1000
    state.last_meaningful_event_at = 0
    return state.is_complete(pending_tools=pending_tools)


@pytest.mark.parametrize("blocker", ["caller", "response", "client_delegation", "tool", "post_tool_text", "turn"])
def test_completion_waits_for_each_required_piece_of_evidence(blocker: str) -> None:
    progress = CallerAudioCompletion()
    progress.completed.set()
    state = collector(progress)
    speech(state, "Answer")
    assert settled(state)
    if blocker == "caller":
        progress.completed.clear()
    elif blocker == "response":
        state.active_response_ids.add("response")
    elif blocker == "client_delegation":
        state.active_client_delegations.add("delegation")
    elif blocker == "post_tool_text":
        state.tool_calls.append({"call_id": "call"})
    elif blocker == "turn":
        state.event_timeline.add_audio("assistant", state.now_ms, state.now_ms + 20, True)
    assert not settled(state, pending_tools=blocker == "tool")


def test_backend_messages_and_tool_observations_are_correlated_and_deduplicated() -> None:
    state = collector()
    events = [
        {"type": "response.created", "response": {"id": "r1"}},
        {"type": "response.output_text.done", "item_id": "message", "text": "Backend response"},
        {
            "type": "response.output_item.done",
            "item": {
                "id": "message",
                "type": "message",
                "content": [{"type": "output_text", "text": "Backend response"}],
            },
        },
        {"type": "tool.called", "call_id": "call", "response_id": "r1", "name": "lookup", "arguments": '{"x":1}'},
        {"type": "tool.called", "call_id": "call", "name": "duplicate"},
        {"type": "response.done", "response": {"id": "r1", "usage": {"input_tokens": 3, "output_tokens": 2}}},
    ]
    for event in events:
        state.observe(event, 100)
    result = state.result(200)
    assert result["backend_messages"] == [{"item_id": "message", "response_id": "r1", "text": "Backend response"}]
    assert len(result["tool_calls"]) == 1
    assert result["tool_calls"][0]["arguments"] == {"x": 1}
    assert result["final_state"] == {"unchanged": True}
    assert not state.active_response_ids


def test_client_completion_requires_a_new_grounded_spoken_turn() -> None:
    state = collector()
    state.observe({"type": "session.delegation.created", "delegation": {"id": "d1", "target": "client"}}, 1)
    speech(state, "One moment")
    assert not settled(state)
    state.observe({"type": "client_delegation.completed", "delegation_id": "d1", "text": "All done"}, 3)
    assert not settled(state)
    speech(state, "All done")
    assert settled(state)


@pytest.mark.parametrize(
    ("event", "stage"),
    [
        ({"type": "error", "error": {"message": "failed"}}, "response_collection"),
        ({"type": "response.failed", "response": {"error": {"message": "failed"}}}, "delegated_response"),
        ({"type": "session.closed"}, "session_close"),
        ({"type": "session.output_audio.delta", "delta": "!invalid!"}, "output_audio"),
        ({"type": "session.output_audio.delta", "delta": None}, "output_audio"),
        ({"type": "response.output_item.added", "item": {"type": "function_call"}}, "tool_correlation"),
        ({"type": "tool.called"}, "tool_correlation"),
    ],
)
def test_protocol_errors_keep_their_failure_stages(event: dict, stage: str) -> None:
    with pytest.raises(LiveResponseError) as error:
        collector().observe(event, 1)
    assert error.value.failure_stage == stage


def test_audio_and_user_relative_latency_are_preserved() -> None:
    state = collector()
    pcm = (1000).to_bytes(2, "little", signed=True) * 480
    state.event_timeline.add_audio("user", 0, 1000, True)
    state.observe(
        {"type": "session.input_transcript.delta", "start_ms": 50_000, "end_ms": 51_000, "delta": "Request"}, 10
    )
    state.now_ms = 1200
    state.observe({"type": "session.output_audio.delta", "delta": base64.b64encode(pcm).decode()}, 50)
    state.now_ms = 1210
    state.observe(
        {"type": "session.output_transcript.delta", "start_ms": 99_000, "end_ms": 99_200, "delta": "Answer"}, 60
    )
    assert settled(state)
    result = state.result(200)
    assert result["output_audio_bytes"] == pcm
    assert result["first_audio_time_ms"] == 200
    assert result["first_text_time_ms"] == 210
    assert result["assistant_text"] == "Answer"
    assert result["input_transcript"] == "Request"


def test_continuing_silent_pcm_does_not_block_a_completed_answer() -> None:
    state = collector()
    speech(state, "Answer")
    assert settled(state)
    silent = base64.b64encode(bytes(4_800)).decode()
    for _ in range(20):
        state.observe({"type": "session.output_audio.delta", "delta": silent}, state.now_ms)
        assert state._output_end_sample * 1000 // state.sample_rate_hz > state.now_ms
        assert state.is_complete(pending_tools=False)
        assert not state.is_complete(pending_tools=True)
        state.now_ms += 100


def test_queued_future_speech_still_blocks_completion_after_a_silent_gap() -> None:
    state = collector()
    speech(state, "First answer.")
    assert settled(state)
    pcm = bytes(96_000) + (1000).to_bytes(2, "little", signed=True) * 4_800
    state.observe({"type": "session.output_audio.delta", "delta": base64.b64encode(pcm).decode()}, 0)
    state.observe(
        {"type": "session.output_transcript.delta", "start_ms": 90_000, "end_ms": 90_200, "delta": " More detail."}, 0
    )
    state.last_meaningful_event_at = 0
    assert not state.is_complete(pending_tools=False)
    state.now_ms = state.event_timeline.last_assistant_speech_ms + 599
    assert not state.is_complete(pending_tools=False)
    state.now_ms += 1
    assert state.is_complete(pending_tools=False)


def backend_event(state: ResponseCollector, kind: str, response_id: str = "r1", **fields) -> None:
    event = {"type": f"response.{kind}", "response_id": response_id, **fields}
    if kind in {"created", "completed"}:
        event["response"] = {"id": response_id}
    state.observe(event, state.now_ms)


@pytest.mark.parametrize("early_caption", [False, True])
def test_acknowledgment_overlapping_backend_completion_needs_a_subsequent_answer(early_caption: bool) -> None:
    state = collector()
    backend_event(state, "created")
    state.now_ms = 4220
    pcm = (1000).to_bytes(2, "little", signed=True) * (24 * 960)
    state.observe({"type": "session.output_audio.delta", "delta": base64.b64encode(pcm).decode()}, 4220)
    caption = {"type": "session.output_transcript.delta", "start_ms": 54_220, "end_ms": 55_180}
    if early_caption:
        state.observe({**caption, "delta": "I'll check"}, 4220)
    state.now_ms = 4240
    backend_event(state, "output_text.delta", item_id="m1", delta="What time")
    state.now_ms = 4380
    backend_event(state, "completed")
    state.now_ms = 4700
    state.observe({**caption, "delta": " that for you." if early_caption else "I'll check that for you."}, 4700)
    state.now_ms = 6000
    assert not settled(state)
    speech(state, "What time would you like the reservation for?")
    assert settled(state)
    assert len(state.turns) == 2
    assert state.turns[0]["transcript"] == "I'll check that for you."


@pytest.mark.parametrize("already_projected", [False, True])
def test_existing_caption_group_cannot_become_answer_by_extending_its_audio(already_projected: bool) -> None:
    state = collector()
    backend_event(state, "created")
    if already_projected:
        speech(state, "One moment.")
        assert not settled(state)
    else:
        state.observe(
            {"type": "session.output_transcript.delta", "start_ms": 50_000, "end_ms": 50_020, "delta": "One moment."}, 0
        )
    backend_event(state, "output_text.delta", item_id="m1", delta="Answer")
    backend_event(state, "completed")
    state.now_ms += 20
    state.event_timeline.add_audio("assistant", state.now_ms, state.now_ms + 200, True)
    state.observe(
        {"type": "session.output_transcript.delta", "start_ms": 50_020, "end_ms": 50_220, "delta": " Answer."}, 0
    )
    assert not settled(state)
    assert state.turns[-1]["transcript"] == "One moment. Answer."


@pytest.mark.parametrize("terminal_time", [1030, 3000])
def test_streamed_answer_can_start_or_finish_before_backend_terminal_event(terminal_time: int) -> None:
    state = collector()
    backend_event(state, "created")
    state.now_ms = 1000
    backend_event(state, "output_text.delta", item_id="m1", delta="Answer")
    state.now_ms = 1020
    speech(state, "Answer")
    state.now_ms = terminal_time
    assert not state.is_complete(pending_tools=False)
    backend_event(state, "completed")
    # Duplicate terminal/text events must preserve the first availability marker.
    backend_event(state, "output_text.done", item_id="m1", text="Answer")
    backend_event(state, "completed")
    backend_event(state, "created")
    assert settled(state)


@pytest.mark.parametrize("fallback", ["output_text.done", "output_item.done"])
def test_managed_completed_text_is_a_fallback_when_no_deltas_arrive(fallback: str) -> None:
    state = collector()
    backend_event(state, "created")
    if fallback == "output_text.done":
        backend_event(state, fallback, item_id="m1", text="Answer")
    else:
        backend_event(
            state,
            fallback,
            item={"id": "m1", "type": "message", "content": [{"type": "output_text", "text": "Answer"}]},
        )
    state.now_ms = 20
    speech(state, "Answer")
    backend_event(state, "completed")
    assert settled(state)


@pytest.mark.parametrize("publication", ["command", "completed"])
def test_client_publication_marks_returned_content_before_backend_terminal(publication: str) -> None:
    state = collector()
    state.observe({"type": "session.delegation.created", "delegation": {"id": "d1", "target": "client"}}, 0)
    completion = {"type": "client_delegation.completed", "delegation_id": "d1", "text": "Booked."}
    if publication == "command":
        state.observe(
            {"type": "evaluation.command.sent", "command_type": "session.commentary.append", "delegation_id": "d1"}, 0
        )
    else:
        state.observe(completion, 0)
    state.now_ms = 20
    speech(state, "Booked.")
    if publication == "command":
        assert not settled(state)
    state.observe(completion, 0)
    state.observe({"type": "session.delegation.created", "delegation": {"id": "d1", "target": "client"}}, 0)
    assert settled(state)


@pytest.mark.parametrize(
    "irrelevant", ["raw_text", "general", "thinking", "instructions", "appended", "unknown", "empty"]
)
def test_client_backend_or_context_acceptance_cannot_supply_a_return_marker(irrelevant: str) -> None:
    state = collector()
    state.observe({"type": "session.delegation.created", "delegation": {"id": "d1", "target": "client"}}, 0)
    if irrelevant == "raw_text":
        backend_event(state, "created", _client_managed=True, delegation_id="d1")
        backend_event(
            state, "output_text.delta", item_id="m1", delta="Booked.", _client_managed=True, delegation_id="d1"
        )
        backend_event(state, "completed", _client_managed=True, delegation_id="d1")
    elif irrelevant == "appended":
        state.observe({"type": "session.commentary.appended", "delegation_id": "d1"}, 0)
    elif irrelevant != "empty":
        command = "commentary" if irrelevant in {"general", "unknown"} else irrelevant
        state.observe(
            {
                "type": "evaluation.command.sent",
                "command_type": f"session.{command}.append",
                "delegation_id": None if irrelevant == "general" else "unknown" if irrelevant == "unknown" else "d1",
            },
            0,
        )
    state.observe({"type": "client_delegation.completed", "delegation_id": "d1", "text": " "}, 0)
    state.now_ms = 20
    speech(state, "One moment.")
    assert not settled(state)


def test_tool_response_text_is_ineligible_and_continuation_needs_its_own_reply() -> None:
    state = collector()
    backend_event(state, "created")
    backend_event(state, "output_text.delta", item_id="m1", delta="Checking")
    backend_event(state, "output_item.added", item={"id": "f1", "type": "function_call"})
    state.observe({"type": "tool.called", "response_id": "r1", "call_id": "c1", "name": "lookup"}, 0)
    state.observe({"type": "tool.completed", "response_id": "r1", "call_id": "c1"}, 0)
    backend_event(state, "completed")
    state.now_ms = 20
    speech(state, "Checking")
    assert not settled(state)
    backend_event(state, "created", "r2", previous_response_id="r1")
    backend_event(state, "output_text.delta", "r2", item_id="m2", delta="Available")
    backend_event(state, "completed", "r2")
    assert not settled(state)
    speech(state, "Available")
    assert settled(state)
    backend_event(state, "created", "r3")
    backend_event(state, "completed", "r3")
    assert not settled(state)


@pytest.mark.parametrize("ownership", ["ambiguous", "item", "explicit", "delegation", "conflict"])
def test_returned_text_ownership_is_resolved_without_guessing(ownership: str) -> None:
    state = collector()
    backend_event(state, "created", "r1", delegation_id="d1")
    backend_event(state, "output_item.added", "r1", item={"id": "m1", "type": "message"})
    backend_event(state, "created", "r2", delegation_id="d2")
    backend_event(state, "output_text.delta", "r2", item_id="m2", delta="Second result")
    fields = {"item_id": "m1"} if ownership in {"item", "conflict"} else {"item_id": "unowned"}
    if ownership in {"explicit", "conflict"}:
        fields["response_id"] = "r1" if ownership == "explicit" else "r2"
    elif ownership == "delegation":
        fields["delegation_id"] = "d1"
    state.observe({"type": "response.output_text.delta", "delta": "First result", **fields}, 0)
    backend_event(state, "completed", "r1")
    backend_event(state, "completed", "r2")
    state.now_ms = 20
    speech(state, "Answer")
    assert settled(state) is (ownership not in {"ambiguous", "conflict"})


def test_backend_terminal_event_and_empty_text_without_returned_content_do_not_complete() -> None:
    state = collector()
    backend_event(state, "created")
    backend_event(state, "output_text.delta", item_id="m1", delta=" ")
    backend_event(state, "completed")
    state.now_ms = 20
    speech(state, "One moment")
    assert not settled(state)


def test_first_delta_with_sole_active_response_survives_late_identified_fallback() -> None:
    state = collector()
    backend_event(state, "created")
    state.observe({"type": "response.output_text.delta", "item_id": "m1", "delta": "Answer"}, 0)
    state.now_ms = 20
    speech(state, "Answer")
    assert not settled(state)
    backend_event(state, "completed")
    # Ownership is retained after the response leaves the active set.
    state.observe({"type": "response.output_text.done", "item_id": "m1", "text": "Answer"}, 0)
    assert settled(state)


def test_later_client_delegation_needs_fresh_speech_and_duplicate_publication_does_not_move_marker() -> None:
    state = collector()
    for identifier in ("d1", "d2"):
        state.observe({"type": "session.delegation.created", "delegation": {"id": identifier, "target": "client"}}, 0)
        command = {
            "type": "evaluation.command.sent",
            "command_type": "session.commentary.append",
            "delegation_id": identifier,
        }
        state.observe(command, 0)
        state.observe({"type": "client_delegation.completed", "delegation_id": identifier, "text": "Answer"}, 0)
        assert not settled(state)
        speech(state, "Answer")
        assert settled(state)
        state.observe(command, 0)
        assert settled(state)


def test_tool_discovered_in_terminal_output_invalidates_earlier_text() -> None:
    state = collector()
    backend_event(state, "created")
    backend_event(state, "output_text.delta", item_id="m1", delta="Checking")
    state.observe(
        {"type": "response.completed", "response": {"id": "r1", "output": [{"id": "f1", "type": "function_call"}]}}, 0
    )
    state.now_ms = 20
    speech(state, "Checking")
    assert not settled(state)


def test_explicit_response_id_can_resolve_missing_delegation_ownership() -> None:
    state = collector()
    backend_event(state, "created")
    backend_event(state, "output_text.delta", delegation_id="d1", item_id="m1", delta="Answer")
    state.now_ms = 20
    speech(state, "Answer")
    backend_event(state, "completed")
    state.observe(
        {"type": "session.delegation.created", "delegation": {"id": "d1", "target": "responses", "response_id": "r1"}},
        0,
    )
    assert settled(state)
