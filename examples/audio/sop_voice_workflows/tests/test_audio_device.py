"""A queued audio frame reaches the speaker only when the device takes it."""

import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from delivery import backend
from delivery_voice.application import Application
from voice.audio import MicrophoneAudio, known_signal
from voice.webrtc import Bundle, SILENCE


def test_hardware_callback_cannot_present_future_buffered_audio(tmp_path, monkeypatch):
    class Device:
        def __init__(self, *, callback, samplerate, blocksize, channels, dtype):
            self.callback = callback
            assert (samplerate, blocksize, channels, dtype) == (24000, 480, 1, "int16")

        def start(self):
            pass

        def abort(self):
            pass

        def close(self):
            pass

    monkeypatch.setitem(sys.modules, "sounddevice", SimpleNamespace(RawStream=Device))
    source = MicrophoneAudio()
    bundle = Bundle(tmp_path / "mic", source)
    bundle.adapter = Application(bundle, backend.DEFAULT_BACKEND_MODEL, AsyncMock(), AsyncMock())
    source.open()
    bundle.source_started = True
    native = known_signal(0.02)
    bundle.enqueue(native * 2)
    status = SimpleNamespace(input_overflow=False, output_underflow=False)
    try:
        # Two physical callbacks run before WebRTC requests either captured frame.
        for incoming in (native, SILENCE):
            speaker = bytearray(len(SILENCE))
            source.stream.callback(incoming, speaker, 480, None, status)
            assert speaker == native
        assert bundle.remaining_native_voice == 960
        assert asyncio.run(bundle.source_frame()) == native
        assert bundle.remaining_native_voice == 480
        assert asyncio.run(bundle.source_frame()) == SILENCE
        assert bundle.remaining_native_voice == 0 and bundle.media_ms == 40
        assert bundle.adapter.store.revision == 1
    finally:
        source.close()
        bundle.finish()
    assert bundle.recorder.input == native + SILENCE
    assert bundle.recorder.output == native * 2
    assert bundle.receipt["receiver_queued_samples_at_close"] == 0


def test_recording_failure_closes_both_trace_files(tmp_path, monkeypatch):
    bundle = Bundle(tmp_path / "mic", MicrophoneAudio())

    def full_disk(_directory):
        raise OSError("disk full")

    monkeypatch.setattr(bundle.recorder, "save", full_disk)
    with pytest.raises(OSError, match="disk full"):
        bundle.finish()
    assert bundle.events.closed and bundle.frames.closed
