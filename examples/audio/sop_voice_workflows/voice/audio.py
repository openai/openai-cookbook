"""24kHz PCM16 capture/playout, shared by microphone and paced WAV input.

Recordings keep silence and both channels on the same local frame clock. They
prove the app's capture/render path, not what a human heard through a device.
"""

from __future__ import annotations

import asyncio
from array import array
from collections import deque
import math
from pathlib import Path
import queue
import sys
import threading
import time
import wave

RATE = 24000
FRAMES = 480
FRAME_BYTES = FRAMES * 2


class AudioBuffer:
    def __init__(self, max_seconds=15, *, on_render=None):
        self.chunks = deque()
        self.buffered_bytes = 0
        self.maximum = int(RATE * 2 * max_seconds)
        self.lock = threading.Lock()
        self.on_render = on_render

    def append(self, pcm):
        if len(pcm) % 2:
            raise ValueError("PCM16 requires complete two-byte samples")
        with self.lock:
            if self.buffered_bytes + len(pcm) > self.maximum:
                raise RuntimeError("Audio playout buffer exceeded its bound")
            self.chunks.append(bytes(pcm))
            self.buffered_bytes += len(pcm)

    def take_input(self, incoming):
        return self.take(len(incoming))

    def take(self, size):
        with self.lock:
            out = bytearray()
            while self.chunks and len(out) < size:
                chunk = self.chunks.popleft()
                used = min(size - len(out), len(chunk))
                out.extend(chunk[:used])
                self.buffered_bytes -= used
                if used < len(chunk):
                    self.chunks.appendleft(chunk[used:])
            if self.on_render is not None:
                self.on_render(len(out))  # Native bytes consumed before silence padding.
            out.extend(b"\0" * (size - len(out)))
            return bytes(out)


def load_wav(path):
    with wave.open(str(path), "rb") as reader:
        if (
            reader.getnchannels(),
            reader.getsampwidth(),
            reader.getframerate(),
            reader.getcomptype(),
        ) != (1, 2, RATE, "NONE"):
            raise ValueError(
                "Input WAV must be mono uncompressed PCM16 at24000Hz; convert it explicitly first"
            )
        pcm = reader.readframes(reader.getnframes())
        if len(pcm) != reader.getnframes() * 2 or not pcm:
            raise ValueError("Input WAV is empty or truncated")
    return pcm


class WavAudio:
    mode = "paced_wav_recording_only"

    def __init__(self, path):
        self.pcm = load_wav(path)
        self.output = AudioBuffer()
        self.position = 0

    def open(self):
        self.started = time.monotonic()
        self.frames_read = 0

    async def read_frame(self):
        target = self.started + self.frames_read / RATE
        await asyncio.sleep(max(0, target - time.monotonic()))
        incoming = self.pcm[self.position : self.position + FRAME_BYTES]
        self.position += len(incoming)
        self.frames_read += FRAMES
        # Keep sending silence after the fixture ends, including backend work
        # and the spoken reply. EOF is not a Live conversation boundary.
        incoming += b"\0" * (FRAME_BYTES - len(incoming))
        return incoming, self.output.take_input(incoming)

    def close(self):
        pass


class MicrophoneAudio:
    mode = "microphone_and_speaker"

    def __init__(self):
        self.output = AudioBuffer()
        self.frames = queue.Queue(maxsize=100)
        self.error = None
        self.stream = None
        self.on_paired_frame = None

    def open(self):
        import sounddevice as sd

        def callback(indata, outdata, frames, timing, status):
            if status.input_overflow or status.output_underflow:
                self.error = "Audio device overrun or underrun; captured evidence may be incomplete"
            played = self.output.take_input(bytes(indata))
            if self.on_paired_frame is not None:
                self.on_paired_frame(bytes(indata), played)
            outdata[:] = played
            try:
                self.frames.put_nowait((bytes(indata), played))
            except queue.Full:
                self.error = "Microphone capture queue overflowed"

        self.stream = sd.RawStream(
            samplerate=RATE, blocksize=FRAMES, channels=1, dtype="int16", callback=callback
        )
        try:
            self.stream.start()
        except BaseException:
            self.stream.close()
            self.stream = None
            raise

    async def read_frame(self):
        if self.error:
            raise RuntimeError(self.error)
        try:
            return await asyncio.to_thread(self.frames.get, True, 1)
        except queue.Empty:
            raise RuntimeError("Microphone did not produce a frame") from None

    def close(self):
        if self.stream:
            try:
                self.stream.abort()
            finally:
                self.stream.close()


class Recorder:
    def __init__(self):
        self.input = bytearray()
        self.output = bytearray()
        self.frame_count = 0

    def append(self, incoming, played):
        if len(incoming) != len(played) or len(incoming) % 2:
            raise ValueError("Input and rendered output must share complete PCM16 frames")
        self.input.extend(incoming)
        self.output.extend(played)
        self.frame_count += 1

    @staticmethod
    def save_mono(path, pcm):
        with wave.open(str(path), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(RATE)
            out.writeframes(pcm)

    def save(self, directory):
        directory = Path(directory)
        self.save_mono(directory / "input.wav", self.input)
        self.save_mono(directory / "output.wav", self.output)
        left, right = array("h"), array("h")
        left.frombytes(self.input)
        right.frombytes(self.output)
        interleaved = array("h", [0]) * (len(left) * 2)
        interleaved[0::2] = left
        interleaved[1::2] = right
        # Array byte storage is unchanged on big-endian hosts: input bytes were
        # already little endian and only interleaving, not arithmetic, happened.
        with wave.open(str(directory / "conversation.wav"), "wb") as out:
            out.setnchannels(2)
            out.setsampwidth(2)
            out.setframerate(RATE)
            out.writeframes(interleaved.tobytes())

    def receipt(self):
        return {
            "recorded_frames": self.frame_count,
            "input_samples": len(self.input) // 2,
            "rendered_output_samples": len(self.output) // 2,
            "recorded_seconds": len(self.input) / 2 / RATE,
            "input_nonzero_bytes": sum(value != 0 for value in self.input),
            "output_nonzero_bytes": sum(value != 0 for value in self.output),
            "recording_clock": "paired local PCM capture/playout frames, including silence",
        }


def known_signal(seconds=0.25):
    values = array(
        "h",
        (int(1200 * math.sin(2 * math.pi * 440 * i / RATE)) for i in range(int(seconds * RATE))),
    )
    if sys.byteorder != "little":
        values.byteswap()
    return values.tobytes()


async def preflight(source, directory, *, seconds=2):
    """No API: exercise the selected real source and recorder with known output."""
    from .config import save

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    directory.chmod(0o700)
    recorder = Recorder()
    signal = known_signal(min(0.25, seconds))
    source.output.append(signal)
    opened = False
    try:
        source.open()
        opened = True
        while len(recorder.input) / 2 / RATE < seconds:
            recorder.append(*(await source.read_frame()))
    finally:
        if opened:
            source.close()
        recorder.save(directory)
    receipt = {
        "api_requests": 0,
        "input_mode": source.mode,
        "known_output_signal_matches": bytes(recorder.output[: len(signal)]) == signal,
        "hardware_playback_verified_by_human": False,
        **recorder.receipt(),
    }
    save(directory / "receipt.json", receipt)
    if not receipt["known_output_signal_matches"]:
        raise RuntimeError("Known signal did not survive the selected playout/recording path")
    return receipt
