"""Offline checks for codec-correct minimum-duration padding."""

import asyncio
import base64
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shared.realtime_harness_utils import stream_audio_to_connection


@pytest.mark.parametrize(
    "audio_format,sample_width,silence",
    [("pcm16", 2, b"\x00"), ("g711_ulaw", 1, b"\xff"), ("g711_alaw", 1, b"\xd5")],
)
@pytest.mark.parametrize("samples", [0, 5, 80, 100])
@pytest.mark.parametrize("real_time", [False, True])
def test_minimum_duration_padding_preserves_encoded_silence(
    audio_format, sample_width, silence, samples, real_time, monkeypatch
):
    calls = []

    class Buffer:
        async def clear(self):
            calls.append(("clear", None))

        async def append(self, *, audio):
            calls.append(("append", base64.b64decode(audio)))

        async def commit(self):
            calls.append(("commit", None))

    sleep = AsyncMock()
    monkeypatch.setattr(asyncio, "sleep", sleep)
    # Distinct synthetic sample bytes verify that the caller's prefix is untouched.
    prefix = bytes(range(samples * sample_width))
    asyncio.run(
        stream_audio_to_connection(
            SimpleNamespace(input_audio_buffer=Buffer()),
            prefix,
            chunk_ms=3,
            sample_rate_hz=8000,
            input_audio_format=audio_format,
            real_time=real_time,
            minimum_duration_seconds=0.01,
        )
    )
    chunks = [data for kind, data in calls if kind == "append"]
    actual = b"".join(chunks)
    padding = max(0, 80 * sample_width - len(prefix))
    assert actual == prefix + silence * padding
    assert calls[0] == ("clear", None)
    assert calls[-1] == ("commit", None)
    assert all(kind == "append" for kind, _ in calls[1:-1])
    assert sleep.await_count == (len(chunks) if real_time else 0)
    if real_time:
        assert all(call.args == (0.003,) for call in sleep.await_args_list)


@pytest.mark.parametrize("audio_format", ["pcm16", "g711_ulaw", "g711_alaw"])
def test_default_minimum_does_not_add_audio(audio_format):
    buffer = SimpleNamespace(clear=AsyncMock(), append=AsyncMock(), commit=AsyncMock())
    asyncio.run(
        stream_audio_to_connection(
            SimpleNamespace(input_audio_buffer=buffer),
            b"",
            20,
            8000,
            audio_format,
            False,
        )
    )
    buffer.clear.assert_awaited_once()
    buffer.append.assert_not_awaited()
    buffer.commit.assert_awaited_once()
