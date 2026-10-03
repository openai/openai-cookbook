"""Sanitized caption/audio mismatches must not invent measured transcript turns."""

import base64
from types import SimpleNamespace

import pytest

from assistants.errors import LiveResponseError
from shared.single_turn import response
from shared.single_turn.runtime import CallerAudioCompletion


def collector(monkeypatch, policy="returned_audio"):
    clock = SimpleNamespace(ms=0)
    monkeypatch.setattr(response, "time", SimpleNamespace(monotonic=lambda: clock.ms / 1000))
    progress = CallerAudioCompletion()
    progress.completed.set()
    state = response.ResponseCollector(
        chunk_ms=20,
        sample_rate_hz=24_000,
        tool_observer=SimpleNamespace(executions=[], snapshot=lambda: {}),
        caller_audio_completion=progress,
        completion_policy=policy,
    )
    state.timeline_clock_ms = lambda: clock.ms
    return state, clock


def event(state, clock, received, kind, **fields):
    clock.ms = received
    state.observe({"type": kind, **fields}, received)


def backend(state, clock, *, publish=True, complete=True, returned_at=50):
    started_at = clock.ms
    event(state, clock, started_at, "session.delegation.created", delegation={"id": "d1", "target": "client"})
    event(
        state,
        clock,
        started_at + 10,
        "tool.called",
        call_id="c1",
        name="lookup",
        delegation_id="d1",
        _client_managed=True,
    )
    event(state, clock, started_at + 20, "tool.completed", call_id="c1", delegation_id="d1", _client_managed=True)
    if publish:
        event(
            state,
            clock,
            returned_at,
            "evaluation.command.sent",
            command_type="session.commentary.append",
            delegation_id="d1",
        )
    if complete:
        event(state, clock, returned_at + 10, "client_delegation.completed", delegation_id="d1", text="Order shipped.")


def caption(state, clock, received, index, text):
    event(
        state,
        clock,
        received,
        "session.output_transcript.delta",
        start_ms=50_000 + index * 2000,
        end_ms=50_100 + index * 2000,
        delta=text,
    )


def audio(state, clock, received, duration=400, *, silent=False):
    pcm = ((0 if silent else 1000).to_bytes(2, "little", signed=True)) * (24 * duration)
    event(state, clock, received, "session.output_audio.delta", delta=base64.b64encode(pcm).decode())


def mismatch(state, clock, *, groups=3):
    for index in range(groups):
        caption(state, clock, 100 * (index + 1), index, ("Order ", "has ", "shipped.")[index])
    audio(state, clock, 1000)
    audio(state, clock, 2000)


@pytest.mark.parametrize("now", [5000, 50_000])
def test_strict_default_preserves_unresolved_three_caption_two_episode_projection(monkeypatch, now):
    state, clock = collector(monkeypatch, "projected_turn")
    backend(state, clock)
    mismatch(state, clock)
    clock.ms = now
    assert not state.is_complete(pending_tools=False)
    assert state.turns == []
    assert state.event_timeline.transcript_projection.pending("assistant")


def test_opt_in_drains_same_audio_without_manufacturing_turns(monkeypatch):
    state, clock = collector(monkeypatch)
    backend(state, clock)
    mismatch(state, clock)
    clock.ms = 2999
    assert not state.is_complete(pending_tools=False)
    clock.ms = 3000
    assert state.is_complete(pending_tools=False)
    result = state.result(3000)
    assert result["completion_basis"] == "returned_audio_with_unaligned_captions"
    assert not result["projection_complete"]
    assert result["turns"] == []
    assert result["assistant_text"] == "Order has shipped."
    assert result["raw_assistant_text"] == "Order has shipped."
    assert state.event_timeline.transcript_projection.pending("assistant")
    assert result["first_audio_time_ms"] is None  # No fabricated user/word timing.


@pytest.mark.parametrize("policy", ["projected_turn", "returned_audio"])
def test_two_caption_two_episode_success_keeps_existing_projection(monkeypatch, policy):
    state, clock = collector(monkeypatch, policy)
    backend(state, clock)
    mismatch(state, clock, groups=2)
    clock.ms = 3000
    assert state.is_complete(pending_tools=False)
    result = state.result(3000)
    assert result["completion_basis"] == "projected_turn"
    assert result["projection_complete"]
    assert [(turn["start_ms"], turn["end_ms"]) for turn in result["turns"]] == [(1000, 1400), (2000, 2400)]


@pytest.mark.parametrize("blocker", ["caller", "response", "delegation", "tool", "publication", "completion"])
def test_opt_in_still_waits_for_pending_work_and_correlated_publication(monkeypatch, blocker):
    state, clock = collector(monkeypatch)
    backend(state, clock, publish=blocker != "publication", complete=blocker != "completion")
    mismatch(state, clock)
    if blocker == "caller":
        state.caller_audio_completion.completed.clear()
    elif blocker == "response":
        state.active_response_ids.add("pending")
    elif blocker == "delegation":
        event(state, clock, 2500, "session.delegation.created", delegation={"id": "d2", "target": "client"})
    clock.ms = 5000
    assert not state.is_complete(pending_tools=blocker == "tool")


@pytest.mark.parametrize("evidence", ["neither", "caption_only", "audio_only", "whitespace_caption", "silent_audio"])
def test_backend_completion_alone_or_non_speech_output_cannot_finish(monkeypatch, evidence):
    state, clock = collector(monkeypatch)
    backend(state, clock)
    if evidence in {"caption_only", "whitespace_caption", "silent_audio"}:
        caption(state, clock, 100, 0, " " if evidence == "whitespace_caption" else "Answer")
    if evidence in {"audio_only", "whitespace_caption", "silent_audio"}:
        audio(state, clock, 1000, silent=evidence == "silent_audio")
    clock.ms = 5000
    assert not state.is_complete(pending_tools=False)


def test_pre_return_caption_cannot_be_reused_even_with_later_audio(monkeypatch):
    state, clock = collector(monkeypatch)
    caption(state, clock, 0, 0, "One moment.")
    backend(state, clock)
    audio(state, clock, 1000)
    caption(state, clock, 1500, 0, " Still checking.")  # Extends the excluded group.
    clock.ms = 5000
    assert not state.is_complete(pending_tools=False)


def test_late_caption_and_acknowledgment_tail_are_not_a_new_answer(monkeypatch):
    state, clock = collector(monkeypatch)
    backend(state, clock, publish=False, complete=False)
    audio(state, clock, 1000)
    event(state, clock, 1200, "evaluation.command.sent", command_type="session.commentary.append", delegation_id="d1")
    event(state, clock, 1250, "client_delegation.completed", delegation_id="d1", text="Order shipped.")
    caption(state, clock, 1500, 0, "I will check.")
    audio(state, clock, 1600, duration=200)  # <=500 ms gap continues the earlier episode.
    clock.ms = 5000
    assert not state.is_complete(pending_tools=False)
    assert state.event_timeline.assistant_speech_started_ms == 1000


def test_speech_queued_before_publication_is_not_a_post_result_episode(monkeypatch):
    state, clock = collector(monkeypatch)
    backend(state, clock, publish=False, complete=False)
    speech = (1000).to_bytes(2, "little", signed=True) * (24 * 400)
    queued = speech + bytes(24 * 1000 * 2) + speech
    event(state, clock, 100, "session.output_audio.delta", delta=base64.b64encode(queued).decode())
    event(state, clock, 600, "evaluation.command.sent", command_type="session.commentary.append", delegation_id="d1")
    event(state, clock, 610, "client_delegation.completed", delegation_id="d1", text="Order shipped.")
    caption(state, clock, 700, 0, "Order shipped.")
    clock.ms = 5000
    assert state.event_timeline.assistant_speech_started_ms > 600
    assert not state.is_complete(pending_tools=False)


@pytest.mark.parametrize("late", ["caption", "speech"])
def test_late_evidence_resets_both_quiet_boundaries(monkeypatch, late):
    state, clock = collector(monkeypatch)
    backend(state, clock)
    mismatch(state, clock)
    clock.ms = 3000
    assert state.is_complete(pending_tools=False)
    if late == "caption":
        caption(state, clock, 3100, 3, " More detail.")
        boundary = 3700
    else:
        audio(state, clock, 3100, duration=200)
        boundary = 3900
    clock.ms = boundary - 1
    assert not state.is_complete(pending_tools=False)
    clock.ms = boundary
    assert state.is_complete(pending_tools=False)


def test_ongoing_audio_and_queued_future_speech_must_drain(monkeypatch):
    state, clock = collector(monkeypatch)
    backend(state, clock)
    mismatch(state, clock)
    audio(state, clock, 2500, duration=3000)
    clock.ms = 5000
    assert not state.is_complete(pending_tools=False)
    clock.ms = state.event_timeline.last_assistant_speech_ms + 599
    assert not state.is_complete(pending_tools=False)
    clock.ms += 1
    assert state.is_complete(pending_tools=False)


def test_perpetual_silent_tail_does_not_extend_completion(monkeypatch):
    state, clock = collector(monkeypatch)
    backend(state, clock)
    mismatch(state, clock)
    for now in range(3000, 5000, 100):
        audio(state, clock, now, duration=400, silent=True)
        assert state.is_complete(pending_tools=False)


def test_playout_clock_cannot_replace_monotonic_quiet_time(monkeypatch):
    state, clock = collector(monkeypatch)
    backend(state, clock)
    mismatch(state, clock)
    clock.ms = 5000
    wall = SimpleNamespace(seconds=2.599)
    monkeypatch.setattr(response, "time", SimpleNamespace(monotonic=lambda: wall.seconds))
    assert not state.is_complete(pending_tools=False)
    wall.seconds = 2.6
    assert state.is_complete(pending_tools=False)


@pytest.mark.parametrize(
    "command,identifier",
    [
        ("session.commentary.append", "unknown"),
        ("session.thinking.append", "d1"),
    ],
)
def test_unrelated_publication_cannot_enable_operational_completion(monkeypatch, command, identifier):
    state, clock = collector(monkeypatch)
    backend(state, clock, publish=False)
    event(state, clock, 70, "evaluation.command.sent", command_type=command, delegation_id=identifier)
    mismatch(state, clock)
    clock.ms = 5000
    assert not state.is_complete(pending_tools=False)


@pytest.mark.parametrize("duplicate_completion", [False, True])
def test_completion_before_publication_cannot_establish_return_boundary(monkeypatch, duplicate_completion):
    state, clock = collector(monkeypatch)
    backend(state, clock, publish=False)
    mismatch(state, clock)
    event(state, clock, 2500, "evaluation.command.sent", command_type="session.commentary.append", delegation_id="d1")
    if duplicate_completion:
        event(state, clock, 2510, "client_delegation.completed", delegation_id="d1", text="Order shipped.")
        event(
            state,
            clock,
            2520,
            "evaluation.command.sent",
            command_type="session.commentary.append",
            delegation_id="d1",
        )
    clock.ms = 5000
    assert not state.is_complete(pending_tools=False)
    assert state.completion_basis is None


def test_partial_projection_does_not_replace_final_captions_with_filler(monkeypatch):
    state, clock = collector(monkeypatch)
    caption(state, clock, 0, 0, "One moment.")
    audio(state, clock, 0, duration=20)
    clock.ms = 700
    assert not state.is_complete(pending_tools=False)
    assert state.turns[0]["transcript"] == "One moment."
    backend(state, clock, returned_at=800)
    for index in range(3):
        caption(state, clock, 900 + index * 100, index + 1, ("Order ", "has ", "shipped.")[index])
    audio(state, clock, 2000)
    audio(state, clock, 3000)
    clock.ms = 4000
    assert state.is_complete(pending_tools=False)
    result = state.result(4000)
    assert result["completion_basis"] == "returned_audio_with_unaligned_captions"
    assert result["assistant_text"] == "Order has shipped."
    assert "One moment." in result["raw_assistant_text"]
    assert result["assistant_turn_transcript"] == "One moment."
    assert not result["projection_complete"]


@pytest.mark.parametrize(
    "event",
    [
        {"type": "session.output_audio.delta", "delta": "malformed!"},
        {"type": "response.failed", "response": {"error": {"message": "failed"}}},
        {"type": "session.closed", "usage": {"seconds": 1}},
    ],
)
def test_opt_in_does_not_turn_protocol_errors_into_completion(monkeypatch, event):
    state, clock = collector(monkeypatch)
    backend(state, clock)
    mismatch(state, clock)
    with pytest.raises(LiveResponseError):
        state.observe(event, 3000)


def test_unknown_completion_policy_is_rejected(monkeypatch):
    with pytest.raises(ValueError, match="Unknown completion policy"):
        collector(monkeypatch, "guess_audio_timing")
