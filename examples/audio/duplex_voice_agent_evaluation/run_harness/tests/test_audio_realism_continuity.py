from __future__ import annotations

from array import array

import pytest

from shared.audio.effects import SAMPLE_RATE, AudioRealism, AudioRealismProcessor
from shared.audio.pcm import AudioQueue


@pytest.mark.parametrize("condition", ["telephony", "realistic"])
def test_telephone_codec_remains_continuous_across_non_aligned_audio_frames(condition: str) -> None:
    pcm = array("h", (index * 113 % 24_000 - 12_000 for index in range(1_007))).tobytes()
    realism = AudioRealism(noise_rms=0.0, background_gain=0.0, echo_decay=0.0, packet_loss_rate=0.0)
    whole = AudioRealismProcessor(condition, 7, realism).process(pcm)
    streaming = AudioRealismProcessor(condition, 7, realism)

    split = b"".join(streaming.process(pcm[start:end]) for start, end in ((0, 34), (34, 132), (132, len(pcm))))

    assert split == whole


@pytest.mark.parametrize(
    ("option", "kind", "duration_ms"),
    [
        ("cough_every_ms", "vocal_tic", 80),
        ("non_directed_every_ms", "non_directed", 160),
    ],
)
def test_cross_frame_distractions_preserve_waveform_and_clipped_labels(
    option: str,
    kind: str,
    duration_ms: int,
) -> None:
    realism = AudioRealism(**{option: 190})
    queue = AudioQueue(SAMPLE_RATE, 200, "clean", 7, realism=realism)

    first, first_speaking = queue.next_chunk()
    first_events = list(queue.last_acoustic_events)
    second, second_speaking = queue.next_chunk()
    second_events = list(queue.last_acoustic_events)

    reference = AudioRealismProcessor("clean", 7, realism).process(
        bytes(len(first) + len(second)),
        speech_active=False,
    )

    assert not first_speaking
    assert not second_speaking
    assert first + second == reference
    assert (kind, 190, 200) in [(event.kind, event.start_ms, event.end_ms) for event in first_events]
    assert (kind, 200, 190 + duration_ms) in [(event.kind, event.start_ms, event.end_ms) for event in second_events]
    assert [event.origin_start_ms for event in first_events if event.start_ms == 190] == [190]
    assert [event.origin_start_ms for event in second_events if event.start_ms == 200] == [190]
    assert queue.realism_metadata["observations"][f"{kind}_events"] == 3


@pytest.mark.parametrize(
    ("option", "kind", "duration_ms"),
    [
        ("cough_every_ms", "vocal_tic", 80),
        ("non_directed_every_ms", "non_directed", 160),
    ],
)
def test_distractions_continue_across_short_transport_frames(
    option: str,
    kind: str,
    duration_ms: int,
) -> None:
    realism = AudioRealism(**{option: 190})
    queue = AudioQueue(SAMPLE_RATE, 50, "clean", 7, realism=realism)
    frames: list[bytes] = []
    fragments: list[tuple[int, int]] = []

    for tick in range(8):
        pcm, speaking = queue.next_chunk()
        frames.append(pcm)
        assert not speaking
        for event in queue.last_acoustic_events:
            assert event.kind == kind
            assert tick * 50 <= event.start_ms < event.end_ms <= (tick + 1) * 50
            if event.start_ms < duration_ms:
                assert event.origin_start_ms == 0
                fragments.append((event.start_ms, event.end_ms))

    reference = AudioRealismProcessor("clean", 7, realism).process(
        bytes(sum(map(len, frames))),
        speech_active=False,
    )

    assert b"".join(frames) == reference
    assert fragments == [(start, min(start + 50, duration_ms)) for start in range(0, duration_ms, 50)]
    assert queue.realism_metadata["observations"][f"{kind}_events"] == 3


@pytest.mark.parametrize(
    ("option", "kind", "duration_ms"),
    [
        ("cough_every_ms", "vocal_tic", 80),
        ("non_directed_every_ms", "non_directed", 160),
    ],
)
def test_lost_frames_do_not_emit_events_but_deliver_a_surviving_tail(
    option: str,
    kind: str,
    duration_ms: int,
) -> None:
    realism = AudioRealism(**{option: 190, "packet_loss_rate": 0.5, "packet_loss_burst": 1})
    queue = AudioQueue(SAMPLE_RATE, 200, "clean", 0, realism=realism)

    lost, speaking = queue.next_chunk()

    assert not speaking
    assert queue.last_packet_lost
    assert lost == bytes(len(lost))
    assert queue.last_acoustic_events == []

    delivered, speaking = queue.next_chunk()

    assert not speaking
    assert not queue.last_packet_lost
    assert any(delivered)
    assert (kind, 200, 190 + duration_ms) in [
        (event.kind, event.start_ms, event.end_ms) for event in queue.last_acoustic_events
    ]
    assert [event.origin_start_ms for event in queue.last_acoustic_events if event.start_ms == 200] == [190]
    assert queue.realism_metadata["observations"]["lost_frames"] == 1
    assert queue.realism_metadata["observations"][f"{kind}_events"] == 2


@pytest.mark.parametrize(
    "option",
    ["cough_every_ms", "non_directed_every_ms"],
)
def test_distraction_tails_are_not_mixed_into_primary_caller_speech(option: str) -> None:
    queue = AudioQueue(SAMPLE_RATE, 200, "clean", 7, realism=AudioRealism(**{option: 190}))
    queue.next_chunk()
    speech = array("h", [1_000] * (SAMPLE_RATE // 5)).tobytes()
    queue.enqueue(speech)

    delivered, speaking = queue.next_chunk()

    assert speaking
    assert delivered == speech
    assert queue.last_source_pcm == speech
    assert queue.last_acoustic_events == []
