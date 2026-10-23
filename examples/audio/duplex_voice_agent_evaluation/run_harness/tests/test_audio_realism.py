import math
import random
import wave
from array import array
from pathlib import Path

import pytest

from shared.audio.effects import (
    DEFAULT_BACKGROUND_GAIN,
    DEFAULT_BACKGROUND_SPEECH,
    DEFAULT_NOISY_RMS,
    SAMPLE_RATE,
    AudioRealism,
    AudioRealismProcessor,
)
from shared.audio.pcm import AudioQueue, chunk_pcm, condition_pcm, rms_pcm16, speech_intervals_pcm16, tone_for_text
from shared.scenarios import AudioCondition


def test_chunking_pads_and_queue_emits_silence() -> None:
    chunks = chunk_pcm(b"\x01\x00" * 7, 8)
    assert len(chunks) == 2
    assert all(len(chunk) == 8 for chunk in chunks)
    queue = AudioQueue(24_000, 200, "clean", 3)
    count = queue.enqueue(b"\x01\x00" * 13)
    assert count == 1
    speech, speaking = queue.next_chunk()
    assert speaking and len(speech) == 9_600
    silence, speaking = queue.next_chunk()
    assert not speaking and silence == bytes(9_600)


def test_streaming_queue_waits_for_a_complete_tick_and_only_pads_at_end() -> None:
    queue = AudioQueue(24_000, 200, "clean", 3)
    assert queue.append(b"\x01\x00" * 2_000) == 0
    assert queue.queued_chunks == 0
    silence, speaking = queue.next_chunk()
    assert not speaking and silence == bytes(9_600)

    assert queue.append(b"\x02\x00" * 3_000) == 1
    first, speaking = queue.next_chunk()
    assert speaking
    assert first == b"\x01\x00" * 2_000 + b"\x02\x00" * 2_800
    assert queue.queued_chunks == 0

    assert queue.finish() == 1
    last, speaking = queue.next_chunk()
    assert speaking
    assert last == b"\x02\x00" * 200 + bytes(9_200)


def test_discarding_stream_tail_cannot_leak_into_the_next_utterance() -> None:
    queue = AudioQueue(24_000, 200, "clean", 3)
    queue.append(b"\x01\x00" * 100)
    queue.discard_pending()
    assert queue.enqueue(b"\x02\x00" * 100) == 1
    speech, speaking = queue.next_chunk()
    assert speaking
    assert speech == b"\x02\x00" * 100 + bytes(9_400)


def test_noise_is_seeded_and_energy_is_measurable() -> None:
    pcm = tone_for_text("hello there")
    first = condition_pcm(pcm, "noisy", 9)
    assert first == condition_pcm(pcm, "noisy", 9)
    assert first != condition_pcm(pcm, "noisy", 10)
    assert rms_pcm16(first) > 200
    assert rms_pcm16(bytes(100)) == 0


def test_noise_preserves_pcm_length() -> None:
    pcm = tone_for_text("test")
    assert len(condition_pcm(pcm, "noisy", 4)) == len(pcm)


@pytest.mark.parametrize("noise_rms", [18_000.0, 19_000.0, 20_000.0, 25_000.0, 32_767.0])
def test_configured_noise_rms_is_realizable_across_the_full_pcm16_range(noise_rms: float) -> None:
    realism = AudioRealism(noise_rms=noise_rms)
    first = AudioQueue(24_000, 200, "clean", 41, realism=realism)
    replay = AudioQueue(24_000, 200, "clean", 41, realism=realism)

    pcm, speaking = first.next_chunk()
    replayed, replay_speaking = replay.next_chunk()

    assert not speaking
    assert not replay_speaking
    assert pcm == replayed
    assert rms_pcm16(pcm) == pytest.approx(noise_rms, rel=0.025)
    assert first.realism_metadata["effects"]["noise_rms"] == noise_rms


def test_speech_intervals_follow_pcm_frames_and_exclude_padding() -> None:
    sample_rate = 1_000
    silence = bytes(20 * 2)
    speech = b"\xe8\x03" * 40
    padded = silence + speech + silence

    assert speech_intervals_pcm16(padded, 1_000, sample_rate, 220, frame_ms=20) == [(1_020, 1_060)]


def test_speech_intervals_ignore_quiet_background_audio() -> None:
    quiet = b"\x64\x00" * 40

    assert speech_intervals_pcm16(quiet, 500, 1_000, 220, frame_ms=20) == []


def test_noisy_queue_emits_continuous_seeded_ambience_during_pauses() -> None:
    first = AudioQueue(24_000, 200, "noisy", 7)
    second = AudioQueue(24_000, 200, "noisy", 7)
    chunks = [first.next_chunk() for _ in range(3)]
    replay = [second.next_chunk() for _ in range(3)]
    assert chunks == replay
    assert all(not speaking for _, speaking in chunks)
    assert all(len(pcm) == 9_600 and rms_pcm16(pcm) == pytest.approx(DEFAULT_NOISY_RMS, rel=0.04) for pcm, _ in chunks)
    assert first.realism_metadata["effects"]["noise_rms"] == DEFAULT_NOISY_RMS
    assert len({pcm for pcm, _ in chunks}) == 3


def test_ambience_continues_through_final_speech_padding_and_next_pause() -> None:
    queue = AudioQueue(24_000, 200, "noisy", 11)
    queue.enqueue(b"\x20\x03" * 200)
    speech, speaking = queue.next_chunk()
    pause, pause_speaking = queue.next_chunk()
    assert speaking and not pause_speaking
    assert rms_pcm16(speech[400:]) > 50
    assert rms_pcm16(pause) > 50


def test_clean_remains_unchanged_and_noisy_uses_the_stronger_deterministic_preset() -> None:
    pcm = array("h", [-32_768, -1_000, 0, 1_000, 32_767]).tobytes()
    rng = random.Random(13)
    amplitude = round(DEFAULT_NOISY_RMS * math.sqrt(3))
    expected = array(
        "h",
        (max(-32_768, min(32_767, value + rng.randint(-amplitude, amplitude))) for value in array("h", pcm)),
    ).tobytes()

    assert condition_pcm(pcm, "clean", 13) == pcm
    assert condition_pcm(pcm, "noisy", 13) == expected


@pytest.mark.parametrize(
    "condition",
    ["clean", "noisy", "telephony", "background_speech", "echo", "packet_loss", "realistic"],
)
def test_every_audio_preset_preserves_seed_and_transport_cadence(condition: AudioCondition) -> None:
    first = AudioQueue(24_000, 200, condition, 17)
    second = AudioQueue(24_000, 200, condition, 17)
    speech = tone_for_text("A reproducible audio realism sample.")
    first.enqueue(speech)
    second.enqueue(speech)

    observed = [first.next_chunk() for _ in range(5)]
    replayed = [second.next_chunk() for _ in range(5)]

    assert observed == replayed
    assert all(len(pcm) == 9_600 for pcm, _ in observed)


@pytest.mark.parametrize("condition", ["telephony", "background_speech", "echo", "packet_loss", "realistic"])
def test_condition_pcm_supports_all_new_presets(condition: str) -> None:
    pcm = tone_for_text("test")

    assert len(condition_pcm(pcm, condition, 4)) == len(pcm)


def test_condition_pcm_rejects_unknown_presets() -> None:
    with pytest.raises(ValueError, match="unknown audio condition"):
        condition_pcm(b"\x01\x00", "unknown", 4)


def test_telephony_filters_speech_without_changing_pcm_format() -> None:
    pcm = tone_for_text("A telephone bandwidth test.")
    conditioned = condition_pcm(pcm, "telephony", 4)

    assert conditioned != pcm
    assert len(conditioned) == len(pcm)
    assert rms_pcm16(conditioned) > 0


def test_telephony_applies_an_eight_kilohertz_g711_channel() -> None:
    samples = array("h", (round(9_000 * math.sin(2 * math.pi * 1_000 * index / SAMPLE_RATE)) for index in range(300)))
    processor = AudioRealismProcessor("telephony", 4)

    conditioned = array("h", processor.process(samples.tobytes()))

    assert len(conditioned) == len(samples)
    assert all(len(set(conditioned[index : index + 3])) == 1 for index in range(0, len(conditioned), 3))
    assert processor.metadata["effects"]["telephony_sample_rate_hz"] == 8_000
    assert processor.metadata["effects"]["telephony_band_hz"] == [300, 3_400]
    assert processor.metadata["effects"]["telephony_codec"] == "g711_mulaw"


def test_telephony_attenuates_audio_outside_the_telephone_voice_band() -> None:
    def processed_rms(frequency: int) -> float:
        samples = array(
            "h",
            (round(8_000 * math.sin(2 * math.pi * frequency * index / SAMPLE_RATE)) for index in range(SAMPLE_RATE)),
        )
        conditioned = AudioRealismProcessor("telephony", 4).process(samples.tobytes())
        return rms_pcm16(conditioned[SAMPLE_RATE // 5 :])

    voice = processed_rms(1_000)

    assert voice > processed_rms(80) * 5
    assert voice > processed_rms(7_000) * 5


def test_background_speech_is_not_marked_as_caller_speech() -> None:
    queue = AudioQueue(24_000, 200, "background_speech", 7)

    observed = []
    for _ in range(3):
        pcm, speaking = queue.next_chunk()
        observed.append(pcm)
        assert not speaking
        assert queue.last_source_pcm == bytes(9_600)
        assert not queue.last_packet_lost

    assert any(rms_pcm16(pcm) > 150 for pcm in observed)
    assert all(rms_pcm16(pcm) < 2_000 for pcm in observed)
    assert queue.realism_metadata["background_provenance"] == "bundled_synthetic_speech"
    assert queue.realism_metadata["effects"]["background_speech"] == "shared/audio/assets/background_conversation.wav"
    assert queue.realism_metadata["effects"]["background_gain"] == DEFAULT_BACKGROUND_GAIN


def test_bundled_background_speech_is_a_real_nonempty_voice_recording() -> None:
    assert DEFAULT_BACKGROUND_SPEECH.is_file()
    with wave.open(str(DEFAULT_BACKGROUND_SPEECH), "rb") as recording:
        assert recording.getnchannels() == 1
        assert recording.getsampwidth() == 2
        assert recording.getframerate() == SAMPLE_RATE
        assert recording.getnframes() > SAMPLE_RATE * 5


def test_realistic_preset_balances_the_upgraded_individual_audio_effects() -> None:
    metadata = AudioRealismProcessor("realistic", 41).metadata
    effects = metadata["effects"]

    assert effects["telephony_codec"] == "g711_mulaw"
    assert effects["noise_rms"] == 500.0
    assert effects["background_speech"] == "shared/audio/assets/background_conversation.wav"
    assert effects["background_gain"] == 0.4
    assert effects["echo_decay"] == 0.25
    assert effects["packet_loss_rate"] == 0.04
    assert effects["packet_loss_burst"] == 1
    assert metadata["background_provenance"] == "bundled_synthetic_speech"


def test_noisy_source_audio_excludes_background_noise() -> None:
    queue = AudioQueue(24_000, 200, "noisy", 7)
    source = b"\x20\x03" * 4_800
    queue.enqueue(source)

    transmitted, speaking = queue.next_chunk()

    assert speaking
    assert transmitted != source
    assert queue.last_source_pcm == source


def test_echo_persists_across_audio_ticks_without_manufacturing_speech() -> None:
    queue = AudioQueue(
        24_000,
        200,
        "echo",
        7,
        realism=AudioRealism(echo_delay_ms=250, echo_decay=0.5),
    )
    source = array("h", [16_000, *([0] * 4_799)]).tobytes()
    queue.enqueue(source)

    first, first_speaking = queue.next_chunk()
    first_source = queue.last_source_pcm
    second, second_speaking = queue.next_chunk()

    assert first_speaking
    assert first_source == source
    assert len(first) == len(second) == 9_600
    assert not second_speaking
    assert queue.last_source_pcm == bytes(9_600)
    assert rms_pcm16(second) > 0


def test_packet_loss_silences_the_transport_tick_and_primary_speech() -> None:
    queue = AudioQueue(
        24_000,
        200,
        "packet_loss",
        7,
        realism=AudioRealism(packet_loss_rate=1.0, packet_loss_burst=2),
    )
    queue.enqueue(tone_for_text("Drop this caller audio."))

    for _ in range(2):
        pcm, speaking = queue.next_chunk()

        assert pcm == bytes(9_600)
        assert not speaking
        assert queue.last_packet_lost
        assert queue.last_source_pcm == bytes(9_600)


def test_zero_packet_loss_preserves_primary_speech() -> None:
    queue = AudioQueue(
        24_000,
        200,
        "packet_loss",
        7,
        realism=AudioRealism(packet_loss_rate=0.0),
    )
    source = b"\x20\x03" * 4_800
    queue.enqueue(source)

    pcm, speaking = queue.next_chunk()

    assert speaking
    assert not queue.last_packet_lost
    assert queue.last_source_pcm == source
    assert pcm == source


def test_burst_packet_loss_is_seeded_and_keeps_all_transport_frames() -> None:
    realism = AudioRealism(packet_loss_rate=0.4, packet_loss_burst=3)
    first = AudioQueue(24_000, 200, "packet_loss", 23, realism=realism)
    second = AudioQueue(24_000, 200, "packet_loss", 23, realism=realism)
    source = b"\x20\x03" * 4_800 * 20
    first.enqueue(source)
    second.enqueue(source)

    observed = []
    replayed = []
    for _ in range(20):
        observed.append((*first.next_chunk(), first.last_packet_lost))
        replayed.append((*second.next_chunk(), second.last_packet_lost))

    assert observed == replayed
    assert any(lost for _, _, lost in observed)
    assert any(not lost for _, _, lost in observed)
    assert all(len(pcm) == 9_600 for pcm, _, _ in observed)


def test_coughs_and_nondirected_speech_are_labeled_without_creating_turns() -> None:
    queue = AudioQueue(
        24_000,
        200,
        "clean",
        7,
        realism=AudioRealism(cough_every_ms=200, non_directed_every_ms=400),
    )
    events = []

    for tick in range(5):
        _, speaking = queue.next_chunk()
        events.extend(queue.last_acoustic_events)

        assert not speaking
        assert queue.last_source_pcm == bytes(9_600)
        assert all(
            tick * 200 <= event.start_ms < event.end_ms <= (tick + 1) * 200 for event in queue.last_acoustic_events
        )

    assert {event.kind for event in events} == {"vocal_tic", "non_directed"}
    assert all(event.provenance for event in events)


def test_background_wav_is_normalized_and_provenance_is_reported(tmp_path: Path) -> None:
    path = tmp_path / "background.wav"
    stereo = array("h", [1_000, 3_000] * 1_600)
    with wave.open(str(path), "wb") as recording:
        recording.setnchannels(2)
        recording.setsampwidth(2)
        recording.setframerate(8_000)
        recording.writeframes(stereo.tobytes())

    queue = AudioQueue(
        24_000,
        200,
        "background_speech",
        7,
        realism=AudioRealism(background_speech=path, background_gain=0.05),
    )
    pcm, speaking = queue.next_chunk()

    assert len(pcm) == 9_600
    assert rms_pcm16(pcm) > 0
    assert not speaking
    assert queue.last_source_pcm == bytes(9_600)
    assert str(path) in str(queue.realism_metadata)


def test_missing_background_recording_fails_clearly(tmp_path: Path) -> None:
    path = tmp_path / "missing.wav"

    with pytest.raises((FileNotFoundError, ValueError), match="missing.wav"):
        AudioQueue(
            24_000,
            200,
            "background_speech",
            7,
            realism=AudioRealism(background_speech=path),
        )


def test_acoustic_mix_clips_without_changing_pcm16_frame_size() -> None:
    queue = AudioQueue(
        24_000,
        200,
        "realistic",
        7,
        realism=AudioRealism(
            noise_rms=20_000,
            background_gain=1.0,
            echo_delay_ms=1,
            echo_decay=1.0,
            packet_loss_rate=0.0,
        ),
    )
    queue.enqueue(array("h", [32_767] * 4_800).tobytes())

    pcm, speaking = queue.next_chunk()
    samples = array("h")
    samples.frombytes(pcm)

    assert speaking
    assert len(pcm) == 9_600
    assert len(samples) == 4_800
    assert all(-32_768 <= sample <= 32_767 for sample in samples)
