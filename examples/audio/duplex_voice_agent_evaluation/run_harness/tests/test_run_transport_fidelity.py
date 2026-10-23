"""Live RUN packet cadence must not redefine the evaluation simulation clock."""

from __future__ import annotations

import asyncio
import base64
import io
import json
import statistics
import time
from collections.abc import AsyncIterator
from typing import Any

import pytest

from assistants.resources import assistant_resources
from run_harness.evaluate import DEFAULT_DATA_JSON, load_run_scenarios
from run_harness.simulation.gpt_live_participants import SimulatorControlTools
from run_harness.simulation.gpt_live_runner import DualGptLiveRunner


class RecordingLiveParticipant:
    """Protocol-only participant; no credentials, real connection, or fixture clock."""

    def __init__(self, label: str, *, first_send_delay_s: float = 0.0) -> None:
        self.agent_id = f"recording-{label}"
        self.first_send_delay_s = first_send_delay_s
        self.sent: list[tuple[float, bytes]] = []
        self._events: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    async def start(self) -> None:
        return None

    async def trigger_opening(self, _text: str) -> None:
        return None

    async def send_audio(self, pcm: bytes) -> None:
        self.sent.append((time.monotonic(), pcm))
        if len(self.sent) == 1 and self.first_send_delay_s:
            await asyncio.sleep(self.first_send_delay_s)

    async def incoming(self) -> AsyncIterator[dict[str, Any]]:
        while (event := await self._events.get()) is not None:
            yield event

    async def wait_for_tools(self) -> None:
        return None

    async def close(self) -> None:
        await self._events.put({"type": "session.closed", "usage": {"seconds": 0.0}, "reason": "client_request"})
        await self._events.put(None)


def make_dual_runner(
    caller: RecordingLiveParticipant,
    assistant: RecordingLiveParticipant,
    *,
    offline: bool,
    max_duration_s: float = 0.2,
    tick_ms: int = 200,
    real_time: bool | None = None,
) -> DualGptLiveRunner:
    scenario = load_run_scenarios(DEFAULT_DATA_JSON, scenario_id="restaurant_booking_complete")[0]
    resources = assistant_resources()
    application = resources.create_executor(scenario.application.initial_state, resources.load_facts())
    runner = DualGptLiveRunner(
        scenario,
        caller=caller,
        assistant=assistant,
        caller_tools=SimulatorControlTools(),
        application_tools=application,
        tick_ms=tick_ms,
        max_duration_s=max_duration_s,
        real_time=not offline if real_time is None else real_time,
        offline=offline,
    )
    opening_pcm = (1_200).to_bytes(2, byteorder="little", signed=True) * 4_800
    runner.audio["caller"].extend(opening_pcm)
    runner.received_audio_bytes["caller"] += len(opening_pcm)
    return runner


@pytest.mark.asyncio
async def test_dual_live_relay_paces_20ms_packets_and_preserves_200ms_decisions() -> None:
    caller = RecordingLiveParticipant("caller")
    assistant = RecordingLiveParticipant("assistant")
    runner = make_dual_runner(caller, assistant, offline=False, max_duration_s=0.8)

    result = await asyncio.wait_for(runner.run(), timeout=1.5)

    assert runner.tick_ms == 200
    assert runner.input_ms == 800
    assert result.run_metadata is not None
    assert result.run_metadata["frame_ms"] == 200
    assert result.run_metadata["synchronized_tick_ms"] == 200
    assert len(runner.recorder.user) == 19_200
    assert len(runner.recorder.assistant) == 19_200
    for participant in (caller, assistant):
        assert len(participant.sent) == 40
        assert all(len(pcm) == 960 for _, pcm in participant.sent)
        gaps_ms = [
            (second[0] - first[0]) * 1_000
            for first, second in zip(participant.sent, participant.sent[1:], strict=False)
        ]
        assert min(gaps_ms) >= 14
        assert gaps_ms[9] <= 50
        assert 15 <= statistics.median(gaps_ms) <= 35
    paired_skew_ms = [
        abs(caller_packet[0] - assistant_packet[0]) * 1_000
        for caller_packet, assistant_packet in zip(caller.sent, assistant.sent, strict=True)
    ]
    assert max(paired_skew_ms) < 15


@pytest.mark.asyncio
async def test_dual_live_relay_recovers_paired_packet_cadence_after_backpressure() -> None:
    caller = RecordingLiveParticipant("caller")
    assistant = RecordingLiveParticipant("assistant", first_send_delay_s=0.075)
    runner = make_dual_runner(caller, assistant, offline=False, max_duration_s=0.6)

    await asyncio.wait_for(runner.run(), timeout=1.5)

    assert len(caller.sent) == len(assistant.sent) == 30
    for participant in (caller, assistant):
        assert all(len(pcm) == 960 for _, pcm in participant.sent)
        gaps_ms = [
            (second[0] - first[0]) * 1_000
            for first, second in zip(participant.sent, participant.sent[1:], strict=False)
        ]
        assert gaps_ms[0] >= 65
        assert min(gaps_ms[1:]) >= 14
        assert 15 <= statistics.median(gaps_ms[1:]) <= 35
    assert runner.input_ms == 600
    assert runner.tick_ms == 200


@pytest.mark.asyncio
async def test_dual_live_relay_never_bursts_after_a_brief_scheduling_delay() -> None:
    class DelayedSchedulingParticipant(RecordingLiveParticipant):
        async def send_audio(self, pcm: bytes) -> None:
            if len(self.sent) == 10:
                await asyncio.sleep(0.011)
            await super().send_audio(pcm)

    caller = DelayedSchedulingParticipant("caller")
    assistant = RecordingLiveParticipant("assistant")
    runner = make_dual_runner(caller, assistant, offline=False, max_duration_s=0.8)

    await asyncio.wait_for(runner.run(), timeout=1.5)

    gaps_ms = [(second[0] - first[0]) * 1_000 for first, second in zip(caller.sent, caller.sent[1:], strict=False)]
    assert len(caller.sent) == 40
    assert min(gaps_ms) >= 14


@pytest.mark.asyncio
async def test_dual_offline_relay_keeps_fixture_packets_at_simulation_tick_size() -> None:
    caller = RecordingLiveParticipant("caller")
    assistant = RecordingLiveParticipant("assistant")
    runner = make_dual_runner(caller, assistant, offline=True)

    result = await asyncio.wait_for(runner.run(), timeout=1)

    assert [len(pcm) for _, pcm in caller.sent] == [9_600]
    assert [len(pcm) for _, pcm in assistant.sent] == [9_600]
    assert runner.input_ms == 200
    assert result.run_metadata is not None
    assert result.run_metadata["synchronized_tick_ms"] == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("tick_ms", [20, 50, 200])
@pytest.mark.parametrize("echo_after_packet", range(1, 11))
async def test_live_echo_is_forwarded_after_bounded_prefill_independent_of_analysis_tick(
    tick_ms: int, echo_after_packet: int
) -> None:
    echoed_pcm = (2_500).to_bytes(2, byteorder="little", signed=True) * 480

    class EchoParticipant(RecordingLiveParticipant):
        async def send_audio(self, pcm: bytes) -> None:
            await super().send_audio(pcm)
            if len(self.sent) == echo_after_packet:
                await self._events.put(
                    {"type": "session.output_audio.delta", "delta": base64.b64encode(echoed_pcm).decode()}
                )

    caller = RecordingLiveParticipant("caller")
    assistant = EchoParticipant("assistant")
    runner = make_dual_runner(caller, assistant, offline=False, max_duration_s=0.66, tick_ms=tick_ms, real_time=False)

    await runner.run()

    assert all(len(pcm) == 960 for _, pcm in caller.sent)
    # The 400 ms reserve adds 20 wire frames, independent of report tick size.
    echoed_packet = echo_after_packet + 20
    assert [index for index, (_, pcm) in enumerate(caller.sent) if any(pcm)] == [echoed_packet]
    assert caller.sent[echoed_packet][1] == echoed_pcm


@pytest.mark.asyncio
async def test_live_echo_prefill_remains_bounded_after_paired_backpressure() -> None:
    echoed_pcm = (2_500).to_bytes(2, byteorder="little", signed=True) * 480

    class EchoParticipant(RecordingLiveParticipant):
        async def send_audio(self, pcm: bytes) -> None:
            await super().send_audio(pcm)
            if len(self.sent) == 1:
                await self._events.put(
                    {"type": "session.output_audio.delta", "delta": base64.b64encode(echoed_pcm).decode()}
                )

    caller = RecordingLiveParticipant("caller")
    assistant = EchoParticipant("assistant", first_send_delay_s=0.075)
    runner = make_dual_runner(caller, assistant, offline=False, max_duration_s=0.66)

    await asyncio.wait_for(runner.run(), timeout=1.5)

    assert [index for index, (_, pcm) in enumerate(caller.sent) if any(pcm)] == [21]
    assert caller.sent[21][1] == echoed_pcm
    assert caller.sent[1][0] - caller.sent[0][0] >= 0.075


@pytest.mark.asyncio
@pytest.mark.parametrize(("provider_offset", "expected_offset"), [(None, 120), (77, 77)])
async def test_queued_events_keep_receipt_media_position_without_overwriting_provider_time(
    provider_offset: int | None, expected_offset: int
) -> None:
    caller = RecordingLiveParticipant("caller")
    assistant = RecordingLiveParticipant("assistant")
    runner = make_dual_runner(caller, assistant, offline=False, real_time=False)
    runner.started = time.monotonic() - 30
    runner.input_ms = 120
    trace = io.StringIO()
    runner.event_log = trace
    event: dict[str, Any] = {
        "type": "session.delegation.created",
        "delegation": {"target": "responses", "response_id": "work"},
    }
    if provider_offset is not None:
        event["offset_ms"] = provider_offset
    pump = asyncio.create_task(runner._pump("assistant", assistant))
    try:
        await assistant._events.put(event)
        await asyncio.sleep(0)
        runner.input_ms = 1_000
        await runner._drain_events()
    finally:
        await assistant.close()
        await pump

    assert runner.timeline.agent_events[0].timestamp_ms == expected_offset
    assert "_relay_receipt" not in event
    received = json.loads(trace.getvalue())["event"]
    assert received["_relay_receipt"]["media_ms"] == 120
    assert received["_relay_receipt"]["monotonic_elapsed_ms"] >= 30_000
    assert received["_relay_queue_delay_ms"] >= 0


@pytest.mark.asyncio
async def test_live_relay_reports_underflow_as_inserted_silence_not_provider_audio() -> None:
    caller = RecordingLiveParticipant("caller")
    assistant = RecordingLiveParticipant("assistant")
    runner = make_dual_runner(caller, assistant, offline=False, max_duration_s=0.46, real_time=False)

    result = await runner.run()

    assert len(caller.sent) == len(assistant.sent) == 23
    assert result.run_metadata is not None
    transport = result.run_metadata["relay_transport"]
    # The existing counter covers all inserted zeros, including planned prefill.
    assert transport["underflow_samples"] == {"caller": 9_600, "assistant": 11_040}
    assert transport["packets_per_direction"] == 23
    assert result.run_metadata["transport_frame_ms"] == 20
    assert result.run_metadata["analysis_tick_ms"] == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("timestamp_gap", [False, True])
async def test_decoded_audio_cannot_escape_the_relay_buffer_budget(timestamp_gap: bool) -> None:
    caller = RecordingLiveParticipant("caller")
    assistant = RecordingLiveParticipant("assistant")
    runner = make_dual_runner(caller, assistant, offline=False, real_time=False)
    runner.events.max_bytes = 2_000
    pcm = (1_200).to_bytes(2, byteorder="little", signed=True) * 480
    for start_ms in [0, 100] if timestamp_gap else [0, 20, 40]:
        await runner.events.put(
            (
                "assistant",
                {"type": "session.output_audio.delta", "start_ms": start_ms, "delta": base64.b64encode(pcm).decode()},
            )
        )
        await runner._drain_events()

    assert runner.failure is not None
    assert runner.failure.failure_stage == "assistant_connection"
    assert len(runner.audio["assistant"]) <= 2_000


@pytest.mark.asyncio
async def test_extreme_provider_gap_is_rejected_before_the_padding_allocator(monkeypatch: pytest.MonkeyPatch) -> None:
    caller = RecordingLiveParticipant("caller")
    assistant = RecordingLiveParticipant("assistant")
    runner = make_dual_runner(caller, assistant, offline=False, real_time=False)
    pcm = (1_200).to_bytes(2, byteorder="little", signed=True) * 480
    encoded = base64.b64encode(pcm).decode()
    await runner.events.put(("assistant", {"type": "session.output_audio.delta", "start_ms": 160, "delta": encoded}))
    await runner._drain_events()

    def do_not_allocate(_pcm: bytes, *, start_ms: int | None = None) -> bytes:
        pytest.fail(f"Outlier {start_ms} reached the padding allocator")

    monkeypatch.setattr(runner.output_audio_clocks["assistant"], "append", do_not_allocate)
    await runner.events.put(
        ("assistant", {"type": "session.output_audio.delta", "start_ms": 1_000_000_000, "delta": encoded})
    )
    await runner._drain_events()

    assert runner.failure is not None
    assert runner.failure.failure_stage == "assistant_connection"
    assert runner.audio["assistant"] == pcm


@pytest.mark.asyncio
@pytest.mark.parametrize(("relayed_ms", "remaining_gap_bytes"), [(80, 960), (100, 0)])
async def test_provider_gap_does_not_allocate_silence_that_was_already_relayed(
    monkeypatch: pytest.MonkeyPatch, relayed_ms: int, remaining_gap_bytes: int
) -> None:
    caller = RecordingLiveParticipant("caller")
    assistant = RecordingLiveParticipant("assistant")
    runner = make_dual_runner(caller, assistant, offline=False, real_time=False)
    runner.events.max_bytes = 2_000
    pcm = (1_200).to_bytes(2, byteorder="little", signed=True) * 480
    encoded = base64.b64encode(pcm).decode()
    await runner.events.put(("assistant", {"type": "session.output_audio.delta", "start_ms": 160, "delta": encoded}))
    await runner._drain_events()
    runner._pop_audio("assistant", relayed_ms * 48)
    clock = runner.output_audio_clocks["assistant"]
    original_append = clock.append

    def check_allocation(frame: bytes, *, start_ms: int | None = None) -> bytes:
        # start_ms=260 is sample 2,400 relative to the first provider frame.
        # Any already-sent underflow silence must be reconciled before allocation.
        assert max(0, 2_400 - clock.sample_count) * 2 + len(frame) <= 2_000
        return original_append(frame, start_ms=start_ms)

    monkeypatch.setattr(clock, "append", check_allocation)
    await runner.events.put(("assistant", {"type": "session.output_audio.delta", "start_ms": 260, "delta": encoded}))
    await runner._drain_events()

    assert runner.failure is None
    assert runner.audio["assistant"] == bytes(remaining_gap_bytes) + pcm
    assert clock.sample_count == 2_880
