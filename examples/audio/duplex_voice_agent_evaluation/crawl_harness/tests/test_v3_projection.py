"""Local timing stays independent of provider transcript frames."""

import base64
from types import SimpleNamespace

import pytest

from shared.observability.timeline import Timeline, TranscriptTurnProjector
from shared.single_turn.response import ResponseCollector


def caption(text, start, *, identifier="", role="assistant"):
    event = {
        "type": f"session.{'output' if role == 'assistant' else 'input'}_transcript.delta",
        "start_ms": start,
        "end_ms": start + 200,
        "delta": text,
    }
    if identifier:
        event["event_id"] = identifier
    return event


def test_partial_words_whitespace_and_identity_are_preserved():
    projector = TranscriptTurnProjector()
    for index, text in enumerate(["Hel", "lo", " ", "world."]):
        event = caption(text, 50_000 + index * 200, identifier=str(index))
        assert projector.record("assistant", event, received_ms=100)
        assert not projector.record("assistant", event, received_ms=100)
    turns = projector.project("assistant", ((100, 500),), now_ms=1100)
    assert [(turn.start_ms, turn.end_ms, turn.transcript) for turn in turns] == [(100, 500, "Hello world.")]


def test_speakers_overlap_without_forcing_alternation_and_audio_must_be_delivered():
    projector = TranscriptTurnProjector()
    projector.record("user", caption("Wait.", 50_000), received_ms=100, boundary=1000)
    projector.record("assistant", caption("Hello.", 90_000), received_ms=100)
    assert projector.project("user", ((100, 500),), now_ms=1500, consumed=999) == []
    user = projector.project("user", ((100, 500),), now_ms=1500, consumed=1000)[0]
    assistant = projector.project("assistant", ((300, 700),), now_ms=1500)[0]
    assert user.start_ms < assistant.start_ms < user.end_ms < assistant.end_ms


def test_burst_captions_map_to_observed_speech_episodes_without_invented_timestamps():
    projector = TranscriptTurnProjector()
    projector.record("assistant", caption("First.", 0), received_ms=0)
    projector.record("assistant", caption("Second.", 2000), received_ms=0)
    turns = projector.project("assistant", ((100, 400), (1600, 1800)), now_ms=2500)
    assert [(turn.start_ms, turn.end_ms, turn.transcript) for turn in turns] == [
        (100, 400, "First."),
        (1600, 1800, "Second."),
    ]
    missing = TranscriptTurnProjector()
    missing.record("assistant", caption("Unmatched", 50_000), received_ms=100)
    assert missing.project("assistant", (), now_ms=9000) == []
    assert missing.pending("assistant")


def test_late_fragment_revises_one_stable_turn_and_invalidates_completion_evidence():
    timeline = Timeline()
    projector = timeline.transcript_projection
    projector.record("assistant", caption("It's Fri", 50_000), received_ms=100)
    original = projector.project("assistant", ((100, 500),), now_ms=1100)[0]
    timeline.add_turn(original)
    version = timeline.content_version
    projector.record("assistant", caption("day.", 50_200), received_ms=1500)
    assert projector.pending("assistant")
    assert projector.project("assistant", ((100, 500),), now_ms=1800) == []
    revised = projector.project("assistant", ((100, 500),), now_ms=2100)[0]
    assert revised.turn_id == original.turn_id
    timeline.add_turn(revised)
    assert len(timeline.turns) == 1 and timeline.turns[0].transcript == "It's Friday."
    assert timeline.content_version > version


def test_untimed_audio_uses_queued_samples_and_only_underflow_inserts_silence():
    state = ResponseCollector(
        chunk_ms=20, sample_rate_hz=24000, tool_observer=SimpleNamespace(executions=[], snapshot=lambda: {})
    )
    now = [100]
    state.timeline_clock_ms = lambda: now[0]
    pcm = (1000).to_bytes(2, "little", signed=True) * 2400
    event = {"type": "session.output_audio.delta", "delta": base64.b64encode(pcm).decode()}
    state.observe(event, 0)
    now[0] = 110  # First 100 ms remains queued; append the next chunk without a gap.
    state.observe(event, 10)
    assert state.output_audio == pcm * 2
    now[0] = 500  # The queue drained at 300 ms: this is actual local underflow.
    state.observe(event, 400)
    assert state.output_audio == pcm * 2 + bytes(9600) + pcm
    assert state.event_timeline.speech_intervals("assistant") == ((100, 300), (500, 600))


def test_provider_frames_do_not_create_local_latency_or_grading_evidence():
    timeline = Timeline()
    event = caption("Not yet aligned", 999_000, identifier="p")
    timeline.apply_event(event)
    timeline.apply_event(event)
    assert len(timeline.provider_fragments) == 1
    assert timeline.fragments == [] and timeline.turns == []
    assert timeline.last_assistant_text_ms == -1
    assert timeline.evaluation_transcript() == ""


def test_caption_gap_can_split_one_speech_episode_at_observed_audio_boundaries():
    # A real v3 response put a 600 ms gap between caption frames, while its
    # corresponding acoustic pause was shorter than the 500 ms integration gap.
    projector = TranscriptTurnProjector()
    for text, start, received in [
        ("Checking.", 6200, 7180),
        ("You're all set—table", 9200, 10140),
        (" for two, Maya, August 6th at 7 p.m.", 10400, 11480),
    ]:
        event = caption(text, start)
        if start == 9200:
            event["end_ms"] = 9800
        projector.record("assistant", event, received_ms=received)
    intervals = ((7380, 8720), (10340, 10440), (10900, 11360), (11740, 11940), (11960, 14540))
    turns = projector.project("assistant", intervals, now_ms=16000)
    assert [(turn.start_ms, turn.end_ms) for turn in turns] == [(7380, 8720), (10340, 11360), (11740, 14540)]
    assert not projector.pending("assistant")
    assert "August 6th" in turns[-1].transcript


def test_missing_user_timing_cannot_be_replaced_by_receiver_elapsed_time():
    state = ResponseCollector(
        chunk_ms=20, sample_rate_hz=24000, tool_observer=SimpleNamespace(executions=[], snapshot=lambda: {})
    )
    pcm = (1000).to_bytes(2, "little", signed=True) * 480
    state.observe({"type": "session.output_audio.delta", "delta": base64.b64encode(pcm).decode()}, 200)
    state.observe(caption("Hello.", 50_000), 300)
    result = state.result(1000)
    assert result["first_audio_time_ms"] is None
    assert result["first_text_time_ms"] is None


def test_caption_ahead_of_audio_does_not_claim_the_previous_words_tail():
    projector = TranscriptTurnProjector()
    prior = caption("Perfect, thanks.", 28400)
    prior["end_ms"] = 28800
    projector.record("user", prior, received_ms=29760)
    projector.record("user", caption("Bye!", 29400), received_ms=30360)
    # The Bye caption arrives while the final word of "thanks" is still heard.
    intervals = ((29800, 30000), (30300, 30440))
    turns = projector.project("user", intervals, now_ms=31040)
    assert [(turn.transcript, turn.end_ms) for turn in turns] == [("Perfect, thanks.", 30440)]
    assert projector.pending("user")
    turns = projector.project("user", (*intervals, (31080, 31320)), now_ms=32000)
    assert [(turn.transcript, turn.start_ms, turn.end_ms) for turn in turns] == [("Bye!", 31080, 31320)]
    assert not projector.pending("user")


def test_pcm_chunks_that_end_between_milliseconds_keep_every_sample():
    from shared.audio.conversation import ConversationRecorder, LiveMonitor

    recorder = ConversationRecorder(24000)
    monitor = LiveMonitor(24000)
    state = ResponseCollector(
        chunk_ms=20,
        sample_rate_hz=24000,
        tool_observer=SimpleNamespace(executions=[], snapshot=lambda: {}),
        recorder=recorder,
        audio_monitor=monitor,
    )
    state.timeline_clock_ms = lambda: 0
    chunks = [(1000).to_bytes(2, "little", signed=True) * 1001, (2000).to_bytes(2, "little", signed=True) * 997]
    for pcm in chunks:
        state.observe({"type": "session.output_audio.delta", "delta": base64.b64encode(pcm).decode()}, 0)
    expected = b"".join(chunks)
    assert state.output_audio == expected
    assert recorder.assistant.tobytes() == expected
    assert monitor._assistant == expected


def test_caption_groups_sharing_continuous_speech_combine_without_losing_text():
    projector = TranscriptTurnProjector()
    for text, start, received in [
        (" or", 10200, 11100),
        (" I", 10600, 11500),
        (" can check", 10800, 11700),
        (" availability", 11000, 11900),
        (" under", 11800, 12720),
        (" your", 12000, 12900),
        (" name.", 12200, 13100),
    ]:
        projector.record("assistant", caption(text, start), received_ms=received)
    intervals = ((11660, 12080), (12120, 12360), (12380, 13840))
    turns = projector.project("assistant", intervals, now_ms=14500)
    assert len(turns) == 1
    assert (turns[0].start_ms, turns[0].end_ms, turns[0].turn_id) == (11660, 13840, "local-assistant-0")
    assert turns[0].transcript == "or I can check availability under your name."
    assert not projector.pending("assistant")
    assert len(projector.groups["assistant"]) == 2  # Keep both original caption groups.
    assert projector.project("assistant", intervals, now_ms=20000) == []

    # A delayed fragment in a combined group revises its original owner once.
    projector.record("assistant", caption(" Thanks.", 12400), received_ms=16000)
    assert projector.pending("assistant")
    revised = projector.project("assistant", intervals, now_ms=16600)
    assert len(revised) == 1 and revised[0].turn_id == turns[0].turn_id
    assert revised[0].transcript == turns[0].transcript + " Thanks."
    assert not projector.pending("assistant")


@pytest.mark.parametrize("role", ["user", "assistant"])
def test_late_audio_revises_a_captioned_tail_without_a_new_text_event(role):
    timeline = Timeline()
    projector = timeline.transcript_projection
    for text, start, received in [
        (" Okay,", 38800, 39660),
        (" thanks", 39000, 40180),
        (" anyway.", 39400, 40380),
        (" Bye.", 40000, 40860),
    ]:
        projector.record(role, caption(text, start, role=role), received_ms=received)
    intervals = ((39980, 41260),)
    first = projector.project(role, intervals, now_ms=42000)[0]
    timeline.add_turn(first)
    version = timeline.content_version
    extended = (*intervals, (42160, 42380))
    assert projector.project(role, extended, now_ms=42600) == []
    assert projector.pending(role)
    revised = projector.project(role, extended, now_ms=44000)
    assert len(revised) == 1
    assert revised[0].turn_id == first.turn_id and revised[0].transcript == first.transcript
    assert (revised[0].start_ms, revised[0].end_ms) == (39980, 42380)
    assert timeline.add_turn(revised[0])
    assert len(timeline.turns) == 1 and timeline.content_version > version
    assert projector.project(role, extended, now_ms=45000) == []


def test_separate_uncaptioned_speech_does_not_extend_a_fully_covered_turn():
    projector = TranscriptTurnProjector()
    projector.record("user", caption("Goodbye.", 50000), received_ms=100)
    first = projector.project("user", ((100, 500),), now_ms=1100)[0]
    assert projector.project("user", ((100, 500), (2000, 2500)), now_ms=3200) == []
    assert projector.groups["user"][0]["turn"] == first


def test_growth_of_an_assigned_acoustic_interval_revises_only_its_endpoint():
    projector = TranscriptTurnProjector()
    projector.record("assistant", caption("Hello.", 50000), received_ms=100)
    first = projector.project("assistant", ((100, 500),), now_ms=1100)[0]
    revised = projector.project("assistant", ((100, 700),), now_ms=1300)
    assert len(revised) == 1
    assert (revised[0].turn_id, revised[0].start_ms, revised[0].end_ms) == (first.turn_id, 100, 700)


def test_pending_audio_revision_does_not_consume_a_long_uncaptioned_utterance():
    projector = TranscriptTurnProjector()
    for text, start, received in [
        (" Okay,", 38800, 39660),
        (" thanks", 39000, 40180),
        (" anyway.", 39400, 40380),
        (" Bye.", 40000, 40860),
    ]:
        projector.record("user", caption(text, start), received_ms=received)
    original = projector.project("user", ((39980, 41260),), now_ms=42000)[0]
    assert projector.project("user", ((39980, 41260), (42160, 42180)), now_ms=42200) == []
    assert projector.pending("user")
    # The new speech grows beyond the remaining caption span. Do not let an
    # audio-only dirty flag act as if additional transcript evidence arrived.
    assert projector.project("user", ((39980, 41260), (42160, 44000)), now_ms=44600) == []
    assert projector.groups["user"][0]["turn"] == original
