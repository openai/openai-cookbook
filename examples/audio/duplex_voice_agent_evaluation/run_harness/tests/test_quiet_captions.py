"""Quiet caption recovery must not change speech detection or invent audio."""

from __future__ import annotations

import asyncio
from array import array

import pytest

from run_harness.simulation.semantic_completion import SemanticCompletionDecision
from run_harness.tests.test_output_buffer import make_runner
from run_harness.tests.test_semantic_completion import observer_for
from shared.audio.pcm import speech_intervals_pcm16
from shared.observability.timeline import TranscriptTurnProjector, Turn


def caption(projector, role, text, start, received, *, boundary=0):
    projector.record(
        role,
        {"type": "session.output_transcript.delta", "start_ms": start, "end_ms": start + 200, "delta": text},
        received_ms=received,
        boundary=boundary,
    )


@pytest.mark.parametrize("role", ["user", "assistant"])
def test_quiet_backchannel_unblocks_farewell_without_changing_existing_alignment(role):
    projector = TranscriptTurnProjector()
    caption(projector, role, "Two, please.", 0, 0)
    caption(projector, role, "Mm-hmm.", 2000, 800)
    caption(projector, role, "Thanks, goodbye.", 4000, 1800)
    normal = ((100, 300), (2000, 2400))
    quiet = ((80, 320), (900, 1060), (1980, 2420))

    baseline = projector.project(role, normal, now_ms=3500)
    assert [turn.transcript for turn in baseline] == ["Two, please."]
    assert projector.pending(role)

    recovered = projector.project(role, normal, now_ms=3500, quiet_intervals=quiet)
    assert [(turn.transcript, turn.start_ms, turn.end_ms) for turn in recovered] == [
        ("Mm-hmm.", 900, 1060),
        ("Thanks, goodbye.", 2000, 2400),
    ]
    assert projector.groups[role][0]["turn"] == baseline[0]
    assert not projector.pending(role)


def test_quiet_caption_waits_for_source_delivery_and_audio_settling():
    projector = TranscriptTurnProjector()
    caption(projector, "user", "Wait.", 50000, 0, boundary=1000)
    assert projector.project("user", (), now_ms=2000, consumed=1000) == []
    assert projector.pending("user")
    quiet = ((2200, 2400),)
    assert projector.project("user", (), now_ms=3000, consumed=999, quiet_intervals=quiet) == []
    assert projector.project("user", (), now_ms=2999, consumed=1000, quiet_intervals=quiet) == []
    turn = projector.project("user", (), now_ms=3000, consumed=1000, quiet_intervals=quiet)[0]
    assert (turn.start_ms, turn.end_ms) == (2200, 2400)


def test_normal_match_takes_priority_over_quieter_audio():
    projector = TranscriptTurnProjector()
    caption(projector, "assistant", "Hello.", 50000, 0)
    turn = projector.project("assistant", ((200, 400),), now_ms=2000, quiet_intervals=((100, 500),))[0]
    assert (turn.start_ms, turn.end_ms) == (200, 400)


@pytest.mark.parametrize("quiet", [(), ((100, 200), (1000, 1100))])
def test_missing_or_ambiguous_quiet_audio_remains_pending(quiet):
    projector = TranscriptTurnProjector()
    caption(projector, "user", "Unresolved correction.", 50000, 0)
    assert projector.project("user", (), now_ms=3000, quiet_intervals=quiet) == []
    assert projector.pending("user")
    assert projector.groups["user"][0]["parts"][0][2] == "Unresolved correction."


@pytest.mark.parametrize("quiet", [((80, 400),), ((900, 2100),)])
def test_quiet_match_cannot_clip_previous_or_next_speech(quiet):
    projector = TranscriptTurnProjector()
    caption(projector, "user", "First.", 0, 0)
    projector.project("user", ((100, 300),), now_ms=1000)
    caption(projector, "user", "Quiet.", 2000, 800)
    caption(projector, "user", "Next.", 4000, 1800)
    assert projector.project("user", ((100, 300),), now_ms=3000, quiet_intervals=quiet) == []
    assert projector.pending("user")
    assert projector.groups["user"][1]["turn"] is None


def test_quiet_turn_revises_for_late_audio_and_text_with_stable_identity():
    projector = TranscriptTurnProjector()
    caption(projector, "user", "No,", 0, 0)
    first = projector.project("user", (), now_ms=1000, quiet_intervals=((100, 300),))[0]
    assert projector.project("user", (), now_ms=1100, quiet_intervals=((100, 600),)) == []
    assert projector.pending("user")
    extended = projector.project("user", (), now_ms=1200, quiet_intervals=((100, 600),))[0]
    assert extended.turn_id == first.turn_id
    assert extended.end_ms == 600
    caption(projector, "user", " Thursday.", 200, 1400)
    assert projector.project("user", (), now_ms=1999, quiet_intervals=((100, 600),)) == []
    final = projector.project("user", (), now_ms=2000, quiet_intervals=((100, 600),))[0]
    assert final.turn_id == first.turn_id
    assert final.transcript == "No, Thursday."
    assert not projector.pending("user")


@pytest.mark.parametrize("label", ["caller", "assistant"])
@pytest.mark.parametrize("amplitude,recovers", [(0, False), (109, False), (110, True), (171, True)])
def test_runner_quiet_detection_preserves_metric_intervals(label, amplitude, recovers):
    runner = make_runner()
    role = "user" if label == "caller" else "assistant"
    pcm = array("h", [amplitude] * 4800).tobytes()
    original = bytes(pcm)
    detected = speech_intervals_pcm16(pcm, 100, runner.sample_rate, runner.speech_rms_threshold)
    assert detected == []
    runner.timeline.add_audio(role, 100, 300, False, speech_intervals=detected)
    runner._record_quiet_caption_audio(label, pcm, 100)
    caption(runner.timeline.transcript_projection, role, "Quiet.", 50000, 0)
    runner.input_ms = 1000
    runner._project_completed_turns(label)

    assert pcm == original
    assert runner.speech_rms_threshold == 220
    assert runner.timeline.speech_intervals(role) == ()
    assert bool(runner.timeline.turns) is recovers
    assert runner.timeline.transcript_projection.pending(role) is not recovers
    if recovers:
        assert (runner.timeline.turns[0].start_ms, runner.timeline.turns[0].end_ms) == (100, 300)


@pytest.mark.asyncio
async def test_quiet_correction_after_goodbye_reaches_completion_evidence():
    runner = make_runner()
    observer, responses = observer_for(
        SemanticCompletionDecision(should_drain=False, outcome="unresolved", reason="Caller corrected the booking.")
    )
    runner.completion_observer = observer
    runner.timeline.add_turn(Turn("assistant", 0, 100, "You're booked.", "assistant-answer"))
    runner.timeline.add_audio("assistant", 0, 100, True)
    caption(runner.timeline.transcript_projection, "user", "Thanks, goodbye.", 0, 0)
    runner.timeline.add_audio("user", 200, 400, True)
    runner.input_ms = 1000
    runner._project_completed_turns("caller")
    assert runner._conversation_evidence_current()

    caption(runner.timeline.transcript_projection, "user", "Wait, Thursday instead.", 2000, 1000)
    assert not runner._conversation_evidence_current()
    runner._record_quiet_caption_audio("caller", array("h", [150] * 4800).tobytes(), 1200)
    runner.input_ms = 2000
    runner._project_completed_turns("caller")
    assert runner._conversation_evidence_current()
    assert runner._advance_semantic_completion() is None
    await asyncio.sleep(0)
    assert responses.calls
    payload = responses.calls[0]["input"][1]["content"]
    assert "Wait, Thursday instead." in payload
    await runner._completion_task


@pytest.mark.asyncio
@pytest.mark.parametrize("lose_quiet_audio", [False, True])
async def test_live_loop_uses_quiet_source_not_mixed_noise_or_lost_packets(lose_quiet_audio):
    from run_harness.tests.test_run_transport_fidelity import RecordingLiveParticipant, make_dual_runner
    from shared.audio.effects import AudioRealism, AudioRealismProcessor
    from shared.audio.pcm import rms_pcm16

    class Processor(AudioRealismProcessor):
        def _is_lost(self):
            return lose_quiet_audio and self._sample_cursor >= 14_400

    caller = RecordingLiveParticipant("caller")
    assistant = RecordingLiveParticipant("assistant")
    runner = make_dual_runner(caller, assistant, offline=False, max_duration_s=1.0, real_time=False)
    quiet = array("h", [150] * 4800).tobytes()
    runner.audio["caller"].extend(quiet)
    runner.received_audio_bytes["caller"] += len(quiet)
    runner.audio_processor = Processor("noisy", 7, AudioRealism(noise_rms=1200))

    await runner.run()

    assert runner.timeline.speech_intervals("user") == ((400, 600),)
    assert runner._quiet_caption_intervals["caller"] == [(400, 600 if lose_quiet_audio else 800)]
    assert runner._quiet_caption_intervals["assistant"] == []
    if not lose_quiet_audio:
        # Noise continues after source speech. It must not become caption evidence.
        assert rms_pcm16(runner.recorder.user[19_200:24_000].tobytes()) > 220
