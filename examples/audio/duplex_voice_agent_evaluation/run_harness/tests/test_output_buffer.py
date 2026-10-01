"""Live playout absorbs bounded delivery jitter without changing source PCM."""

from __future__ import annotations

import base64
import io
import json
from array import array

import pytest

from assistants.resources import assistant_resources
from run_harness.evaluate import DEFAULT_DATA_JSON, load_run_scenarios
from run_harness.simulation import gpt_live_runner
from run_harness.simulation.gpt_live_participants import SimulatorControlTools
from run_harness.simulation.gpt_live_runner import DualGptLiveRunner
from run_harness.tests.test_run_transport_fidelity import RecordingLiveParticipant
from shared.audio.pcm import speech_intervals_pcm16

FRAME_BYTES = 960
SPEECH_FRAME = array("h", [1_500] * 480).tobytes()


def make_runner(*, offline: bool = False) -> DualGptLiveRunner:
    scenario = load_run_scenarios(DEFAULT_DATA_JSON, scenario_id="restaurant_booking_complete")[0]
    resources = assistant_resources()
    application = resources.create_executor(scenario.application.initial_state, resources.load_facts())
    return DualGptLiveRunner(
        scenario,
        caller=RecordingLiveParticipant("caller"),
        assistant=RecordingLiveParticipant("assistant"),
        caller_tools=SimulatorControlTools(),
        application_tools=application,
        offline=offline,
        real_time=False,
    )


def receive(runner: DualGptLiveRunner, pcm: bytes, *, label: str = "caller", start_ms: int | None = None) -> None:
    event = {"type": "session.output_audio.delta", "delta": base64.b64encode(pcm).decode()}
    if start_ms is not None:
        event["start_ms"] = start_ms
    assert runner._buffer_output_audio(label, event)


def test_short_voiced_first_burst_plays_intact_after_bounded_wait() -> None:
    runner = make_runner()
    # Initial connection silence must not spend the buffer's deadline.
    for now in range(0, 1_000, 20):
        runner.input_ms = now
        assert runner._pop_audio("caller", FRAME_BYTES) == bytes(FRAME_BYTES)
    runner.input_ms = 1_000
    receive(runner, SPEECH_FRAME)

    output = []
    for now in range(1_000, 1_440, 20):
        runner.input_ms = now
        output.append(runner._pop_audio("caller", FRAME_BYTES))

    assert output[:20] == [bytes(FRAME_BYTES)] * 20
    assert output[20] == SPEECH_FRAME
    assert output[21] == bytes(FRAME_BYTES)
    assert runner.consumed_audio_bytes["caller"] == len(SPEECH_FRAME)
    assert runner.audio["caller"] == b""


def test_silent_tail_drains_and_releases_pending_caption() -> None:
    runner = make_runner()
    pcm = SPEECH_FRAME + bytes(FRAME_BYTES * 5)
    receive(runner, pcm)
    runner.timeline.transcript_projection.record(
        "user",
        {"type": "session.output_transcript.delta", "start_ms": 0, "end_ms": 200, "delta": "Goodbye."},
        received_ms=0,
        boundary=len(pcm),
    )
    relayed_speech = bytearray()
    for now in range(0, 2_200, 20):
        runner.input_ms = now
        frame = runner._pop_audio("caller", FRAME_BYTES)
        if any(frame):
            relayed_speech.extend(frame)
        runner.timeline.add_audio("user", now, now + 20, bool(any(frame)))
        runner._project_completed_turns("caller")

    assert relayed_speech == SPEECH_FRAME
    assert runner.consumed_audio_bytes["caller"] == len(pcm)
    assert not runner.audio["caller"]
    assert not runner.timeline.transcript_projection.pending("user")
    assert [turn.transcript for turn in runner.timeline.turns] == ["Goodbye."]


def test_short_digital_silence_inside_speech_is_not_stretched() -> None:
    runner = make_runner()
    # Establish that this is an ongoing stream, rather than its initial burst.
    receive(runner, SPEECH_FRAME)
    runner._pop_audio("caller", FRAME_BYTES)
    runner.input_ms = 400
    assert runner._pop_audio("caller", FRAME_BYTES) == SPEECH_FRAME
    receive(runner, bytes(FRAME_BYTES) + SPEECH_FRAME)

    runner.input_ms = 420
    assert runner._pop_audio("caller", FRAME_BYTES) == bytes(FRAME_BYTES)
    runner.input_ms = 440
    assert runner._pop_audio("caller", FRAME_BYTES) == SPEECH_FRAME
    assert runner.consumed_audio_bytes["caller"] == FRAME_BYTES * 3


def test_explicit_provider_timestamp_gaps_keep_existing_placement() -> None:
    runner = make_runner()
    receive(runner, SPEECH_FRAME, start_ms=0)
    assert runner._pop_audio("caller", FRAME_BYTES) == SPEECH_FRAME
    runner.input_ms = 20
    assert runner._pop_audio("caller", FRAME_BYTES) == bytes(FRAME_BYTES)
    receive(runner, SPEECH_FRAME, start_ms=100)

    # The provider's 80 ms gap already includes 20 ms of relayed silence.
    assert runner.audio["caller"] == bytes(FRAME_BYTES * 3) + SPEECH_FRAME


def test_offline_fixture_audio_remains_immediate() -> None:
    runner = make_runner(offline=True)
    receive(runner, SPEECH_FRAME)
    assert runner._pop_audio("caller", FRAME_BYTES) == SPEECH_FRAME


def test_delayed_100ms_chunks_preserve_every_sample_without_an_internal_zero_gap() -> None:
    runner = make_runner()
    chunks = [array("h", [1_000 + index] * 2_400).tobytes() for index in range(12)]
    # Chunk 6 arrives 280 ms late, inside the configured playout reserve.
    arrivals = [0, 100, 200, 300, 400, 500, 880, 900, 1_000, 1_100, 1_200, 1_300]
    incoming = 0
    output = []
    for now in range(0, 1_800, 20):
        runner.input_ms = now
        while incoming < len(chunks) and arrivals[incoming] <= now:
            receive(runner, chunks[incoming])
            incoming += 1
        output.append(runner._pop_audio("caller", FRAME_BYTES))

    speech = [index for index, frame in enumerate(output) if any(frame)]
    assert speech == list(range(20, 80))
    assert b"".join(output[20:80]) == b"".join(chunks)
    assert runner.consumed_audio_bytes["caller"] == sum(map(len, chunks))
    assert not runner.audio["caller"]


def test_each_direction_has_its_own_first_audio_deadline() -> None:
    runner = make_runner()
    caller_output, assistant_output = [], []
    for now in range(0, 820, 20):
        runner.input_ms = now
        if now == 0:
            receive(runner, SPEECH_FRAME)
        if now == 300:
            receive(runner, SPEECH_FRAME, label="assistant")
        caller_output.append(runner._pop_audio("caller", FRAME_BYTES))
        assistant_output.append(runner._pop_audio("assistant", FRAME_BYTES))

    assert [index * 20 for index, frame in enumerate(caller_output) if any(frame)] == [400]
    assert [index * 20 for index, frame in enumerate(assistant_output) if any(frame)] == [700]
    assert b"".join(frame for frame in caller_output if any(frame)) == SPEECH_FRAME
    assert b"".join(frame for frame in assistant_output if any(frame)) == SPEECH_FRAME


@pytest.mark.parametrize("samples", [1, 479, 481])
def test_partial_pcm_frames_drain_without_dropping_or_repeating_samples(samples: int) -> None:
    runner = make_runner()
    source = array("h", [1_234] * samples).tobytes()
    receive(runner, source)
    output = []
    for now in range(0, 460, 20):
        runner.input_ms = now
        output.append(runner._pop_audio("caller", FRAME_BYTES))

    assert b"".join(output[20:]) == source + bytes(FRAME_BYTES * 3 - len(source))
    assert runner.consumed_audio_bytes["caller"] == len(source)
    assert not runner.audio["caller"]


@pytest.mark.asyncio
async def test_default_live_buffer_preserves_paired_20ms_transport_and_complete_audio() -> None:
    import asyncio
    import statistics

    class ChunkedParticipant(RecordingLiveParticipant):
        def __init__(self, label: str, amplitude: int) -> None:
            super().__init__(label)
            self.chunks = [array("h", [amplitude + index] * 2_400).tobytes() for index in range(6)]
            self.emitted = 0

        async def emit_chunk(self) -> None:
            if self.emitted < len(self.chunks):
                await self._events.put(
                    {
                        "type": "session.output_audio.delta",
                        "delta": base64.b64encode(self.chunks[self.emitted]).decode(),
                    }
                )
                self.emitted += 1

        async def start(self) -> None:
            await self.emit_chunk()

        async def send_audio(self, pcm: bytes) -> None:
            await super().send_audio(pcm)
            if len(self.sent) % 5 == 0:
                await self.emit_chunk()

    caller = ChunkedParticipant("caller", 1_200)
    assistant = ChunkedParticipant("assistant", 2_400)
    runner = make_runner()
    runner.caller = caller
    runner.assistant = assistant
    runner.real_time = True
    runner.max_duration_s = 1.0

    result = await asyncio.wait_for(runner.run(), timeout=3)

    assert runner.input_ms == 1_000
    assert result.run_metadata is not None
    assert result.run_metadata["transport_frame_ms"] == 20
    assert result.run_metadata["analysis_tick_ms"] == 200
    assert len(caller.sent) == len(assistant.sent) == 50
    for participant, peer in ((caller, assistant), (assistant, caller)):
        assert all(len(pcm) == FRAME_BYTES for _, pcm in participant.sent)
        gaps = [(b[0] - a[0]) * 1_000 for a, b in zip(participant.sent, participant.sent[1:], strict=False)]
        assert min(gaps) >= 14
        assert 15 <= statistics.median(gaps) <= 35
        assert b"".join(pcm for _, pcm in participant.sent[:20]) == bytes(20 * FRAME_BYTES)
        assert b"".join(pcm for _, pcm in participant.sent[20:]) == b"".join(peer.chunks)
    assert max(abs(a[0] - b[0]) * 1_000 for a, b in zip(caller.sent, assistant.sent, strict=True)) < 15
    assert runner.recorder.user.tobytes() == bytes(20 * FRAME_BYTES) + b"".join(caller.chunks)
    assert runner.recorder.assistant.tobytes() == bytes(20 * FRAME_BYTES) + b"".join(assistant.chunks)


async def drain_caption(
    runner: DualGptLiveRunner, text: str, start: int, end: int, *, label: str = "caller"
) -> dict[str, object]:
    event = {
        "type": "session.output_transcript.delta",
        "start_ms": start,
        "end_ms": end,
        "delta": text,
        "_relay_receipt": {"media_ms": runner.input_ms, "monotonic_elapsed_ms": runner.input_ms + 700},
    }
    await runner.events.put((label, event))
    await runner._drain_events()
    return event


async def replay_leading_captions() -> DualGptLiveRunner:
    runner = make_runner()
    runner.event_log = io.StringIO()
    for now in range(0, 1_700, 20):
        runner.input_ms = now
        if now == 0:
            await drain_caption(runner, "One.", 0, 200)
        if now in (40, 200):
            await runner.events.put(
                ("caller", {"type": "session.output_audio.delta", "delta": base64.b64encode(SPEECH_FRAME * 5).decode()})
            )
        if now == 140:
            await runner.events.put(
                ("caller", {"type": "session.output_audio.delta", "delta": base64.b64encode(bytes(2_880)).decode()})
            )
        await runner._drain_events()
        if now == 100:
            await drain_caption(runner, "Two.", 800, 1_000)
        pcm = runner._pop_audio("caller", FRAME_BYTES)
        intervals = speech_intervals_pcm16(pcm, now, 24_000, runner.speech_rms_threshold)
        runner.timeline.add_audio("user", now, now + 20, bool(intervals), speech_intervals=intervals)
        runner.input_ms = now + 20
        runner._project_completed_turns("caller")
    return runner


@pytest.mark.asyncio
async def test_leading_captions_follow_their_source_frontier_through_prefill() -> None:
    runner = await replay_leading_captions()

    assert [(turn.transcript, turn.start_ms, turn.end_ms) for turn in runner.timeline.turns] == [
        ("One.", 440, 540),
        ("Two.", 600, 700),
    ]
    # The second caption arrives before the first audio is played. Its cutoff
    # follows the source point the immediate relay had reached, not the queue end.
    groups = runner.timeline.transcript_projection.groups["user"]
    assert [group["first_received_ms"] for group in groups] == [0, 500]
    assert not runner._pending_audio_captions["caller"]
    assert not runner.timeline.transcript_projection.pending("user")


@pytest.mark.asyncio
async def test_buffering_preserves_raw_caption_and_receipt_provenance() -> None:
    runner = await replay_leading_captions()
    assert isinstance(runner.event_log, io.StringIO)
    saved = [json.loads(line) for line in runner.event_log.getvalue().splitlines()]
    captions = [item["event"] for item in saved if item["type"] == "session.output_transcript.delta"]

    assert [(event["delta"], event["start_ms"], event["end_ms"]) for event in captions] == [
        ("One.", 0, 200),
        ("Two.", 800, 1_000),
    ]
    assert [event["_relay_receipt"] for event in captions] == [
        {"media_ms": 0, "monotonic_elapsed_ms": 700},
        {"media_ms": 100, "monotonic_elapsed_ms": 800},
    ]
    assert [(item.text, item.start_ms, item.end_ms) for item in runner.timeline.provider_fragments] == [
        ("One.", 0, 200),
        ("Two.", 800, 1_000),
    ]


@pytest.mark.asyncio
async def test_zero_reserve_preserves_immediate_caption_observation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gpt_live_runner, "LIVE_OUTPUT_BUFFER_MS", 0)
    runner = await replay_leading_captions()

    assert [(turn.transcript, turn.start_ms, turn.end_ms) for turn in runner.timeline.turns] == [
        ("One.", 40, 140),
        ("Two.", 200, 300),
    ]
    assert [group["first_received_ms"] for group in runner.timeline.transcript_projection.groups["user"]] == [0, 100]


@pytest.mark.asyncio
async def test_finite_final_burst_releases_deferred_caption_without_more_audio() -> None:
    runner = make_runner()
    for now in range(0, 1_500, 20):
        runner.input_ms = now
        if now == 40:
            receive(runner, SPEECH_FRAME * 5)
        if now == 160:
            await drain_caption(runner, "Goodbye.", 0, 200)
        pcm = runner._pop_audio("caller", FRAME_BYTES)
        intervals = speech_intervals_pcm16(pcm, now, 24_000, runner.speech_rms_threshold)
        runner.timeline.add_audio("user", now, now + 20, bool(intervals), speech_intervals=intervals)
        runner.input_ms = now + 20
        runner._project_completed_turns("caller")

    assert [(turn.transcript, turn.start_ms, turn.end_ms) for turn in runner.timeline.turns] == [("Goodbye.", 440, 540)]
    assert runner.consumed_audio_bytes["caller"] == len(SPEECH_FRAME) * 5
    assert not runner._pending_audio_captions["caller"]
    assert not runner.timeline.transcript_projection.pending("user")


@pytest.mark.asyncio
async def test_caption_received_after_playout_keeps_its_actual_receipt_time() -> None:
    runner = await replay_leading_captions()
    runner.input_ms = 2_000
    await drain_caption(runner, "Late.", 1_600, 1_800)

    assert runner.timeline.transcript_projection.groups["user"][-1]["first_received_ms"] == 2_000


@pytest.mark.asyncio
@pytest.mark.parametrize("label", ["caller", "assistant"])
async def test_deferred_caption_blocks_completion_before_projector_recording(label: str) -> None:
    runner = make_runner()
    receive(runner, bytes(FRAME_BYTES * 5), label=label)
    runner._pop_audio(label, FRAME_BYTES)
    runner.input_ms = 20
    assert runner._caller_evidence_current()
    assert runner._conversation_evidence_current()
    event = await drain_caption(runner, "More to say.", 0, 200, label=label)

    role = "user" if label == "caller" else "assistant"
    assert event["_relay_receipt"] == {"media_ms": 20, "monotonic_elapsed_ms": 720}
    assert runner._pending_audio_captions[label]
    assert not runner.timeline.transcript_projection.pending(role)
    assert not runner._conversation_evidence_current()
    if label == "caller":
        assert not runner._caller_evidence_current()
