"""Live stereo monitoring and single-example selection for CRAWL."""

from __future__ import annotations

import asyncio
import base64
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest

from crawl_harness.evaluate import DEFAULT_DATA_JSON, parse_args, run_evals
from shared.testing.live import OfflineLiveConnection


class RecordingMonitor:
    """Capture both live audio channels without requiring physical speakers."""

    def __init__(self, sample_rate: int) -> None:
        self.sample_rate = sample_rate
        self.started = False
        self.closed = False
        self.drain_calls = 0
        self.audio: list[tuple[str, bytes]] = []

    def start(self) -> None:
        self.started = True

    def push(self, role: str, pcm: bytes, *, start_ms: int | None = None) -> None:
        del start_ms
        assert self.started
        assert role in {"user", "assistant"}
        self.audio.append((role, pcm))

    def wait_until_drained(self, timeout_s: float) -> bool:
        assert timeout_s > 0
        self.drain_calls += 1
        return True

    def close(self) -> None:
        self.closed = True


class EarlyAudioLiveConnection(OfflineLiveConnection):
    """Emit assistant timeline frames while the caller recording is still streaming."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.early_output_received = False
        self.output_offset_ms = 0

    async def send_json(self, payload: dict[str, Any]) -> None:
        await super().send_json(payload)
        if payload.get("type") != "session.input_audio.append" or self.started_response:
            return
        start_ms = self.output_offset_ms
        self.output_offset_ms += 20
        await self.events.put(
            {
                "type": "session.output_audio.delta",
                "start_ms": start_ms,
                "end_ms": self.output_offset_ms,
                "delta": base64.b64encode(bytes(960)).decode("ascii"),
            }
        )

    async def receive_json(self, *, timeout: float | None = None) -> dict[str, Any]:  # noqa: ASYNC109
        event = await super().receive_json(timeout=timeout)
        if event.get("type") == "session.output_audio.delta" and self.received_audio_bytes < self.input_audio_length:
            self.early_output_received = True
        return event


def test_crawl_listening_and_example_selection_are_opt_in() -> None:
    args = parse_args([])

    assert args.listen is False
    assert args.verbose is False
    assert args.example == "all"


@pytest.mark.asyncio
async def test_crawl_streams_one_selected_example_to_both_stereo_channels(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monitors: list[RecordingMonitor] = []

    def create_monitor(sample_rate: int) -> RecordingMonitor:
        monitor = RecordingMonitor(sample_rate)
        monitors.append(monitor)
        return monitor

    monkeypatch.setattr("crawl_harness.evaluate.LiveMonitor", create_monitor)
    args = parse_args(
        [
            "--offline",
            "--no-real-time",
            "--data",
            str(DEFAULT_DATA_JSON),
            "--example",
            "restaurant_003",
            "--listen",
            "--verbose",
            "--results-dir",
            str(tmp_path),
        ]
    )

    run_dir = await run_evals(args)
    output = capsys.readouterr().out

    assert len(monitors) == 1
    monitor = monitors[0]
    assert monitor.sample_rate == 24_000
    assert monitor.started
    assert monitor.closed
    assert monitor.drain_calls >= 1
    assert {role for role, _ in monitor.audio} == {"user", "assistant"}
    assert all(pcm for _, pcm in monitor.audio)
    assert "-> session.input_audio.append" in output
    assert "<- session.output_audio.delta" in output
    assert "chunks=" in output
    assert "<- session.input_transcript.delta" in output
    assert "<- session.output_transcript.delta" in output
    assert "<- turn.done" not in output
    assert "timing=untimed" in output
    assert ".. tool.called name=create_reservation" in output
    assert ".. tool.completed name=create_reservation" in output
    assert "USER       Book a table for Maya" in output
    assert "ASSISTANT  " in output
    assert "TOOL       create_reservation" in output
    assert "RESULT     PASS" in output
    assert "tool=1.00" in output
    assert "tools=1/1" in output
    assert "response_rate=1.00" in output
    assert "CHECKS     " in output
    assert "JUDGE      not assessed (offline fixture)" in output
    assert "[base64 PCM;" not in output

    report = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    rows = report["results"]

    assert len(rows) == 1
    assert rows[0]["scenario_id"] == "restaurant_003"
    assert rows[0]["status"] == "passed"
    assert (run_dir / "audio" / "restaurant_003" / "conversation.wav").is_file()


@pytest.mark.asyncio
async def test_crawl_receives_assistant_audio_while_caller_audio_is_still_streaming(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    connections: list[EarlyAudioLiveConnection] = []
    monitors: list[RecordingMonitor] = []

    @asynccontextmanager
    async def open_early_connection(**kwargs: Any):
        connection = EarlyAudioLiveConnection(
            example_id=kwargs["example_id"],
            user_text=kwargs["user_text"],
            input_audio_length=kwargs["input_audio_length"],
            sample_rate_hz=kwargs["sample_rate_hz"],
            application_behavior=kwargs.get("offline_behavior"),
        )
        connections.append(connection)
        try:
            yield connection
        finally:
            await connection.close()

    def create_monitor(sample_rate: int) -> RecordingMonitor:
        monitor = RecordingMonitor(sample_rate)
        monitors.append(monitor)
        return monitor

    monkeypatch.setattr("crawl_harness.evaluate.open_live_connection", open_early_connection)
    monkeypatch.setattr("crawl_harness.evaluate.LiveMonitor", create_monitor)
    args = parse_args(
        [
            "--offline",
            "--no-real-time",
            "--data",
            str(DEFAULT_DATA_JSON),
            "--example",
            "restaurant_003",
            "--listen",
            "--results-dir",
            str(tmp_path),
        ]
    )

    run_dir = await run_evals(args)

    assert len(connections) == 1
    assert connections[0].early_output_received
    monitor = monitors[0]
    first_assistant_audio = next(index for index, (role, _) in enumerate(monitor.audio) if role == "assistant")
    last_caller_audio = max(index for index, (role, _) in enumerate(monitor.audio) if role == "user")
    assert first_assistant_audio < last_caller_audio

    records = [
        json.loads(line)
        for line in (run_dir / "events" / "restaurant_003.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    first_output_index = min(
        record["event_index"] for record in records if record["type"] == "session.output_audio.delta"
    )
    last_speech_input_index = max(
        record["event_index"]
        for record in records
        if record["type"] == "session.input_audio.append" and record["event"].get("audio_kind") != "silence"
    )
    assert first_output_index < last_speech_input_index
    assert all(
        record["event_index"] > last_speech_input_index
        for record in records
        if record["type"] == "session.input_audio.append" and record["event"].get("audio_kind") == "silence"
    )

    report = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    row = report["results"][0]
    assert row["status"] == "passed"
    assert row["metrics"]["task"]["task_completed"] is True
    assert row["metrics"]["task"]["tool_accuracy"] == 1.0


@pytest.mark.asyncio
async def test_crawl_does_not_open_audio_device_when_listening_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def unexpected_monitor(_sample_rate: int) -> None:
        raise AssertionError("normal CRAWL evaluations must not open an audio device")

    monkeypatch.setattr("crawl_harness.evaluate.LiveMonitor", unexpected_monitor)
    args = parse_args(
        [
            "--offline",
            "--no-real-time",
            "--max-examples",
            "1",
            "--results-dir",
            str(tmp_path),
        ]
    )

    run_dir = await run_evals(args)

    report = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    assert report["summary"]["passed"] == 1


@pytest.mark.asyncio
async def test_unknown_crawl_example_fails_before_creating_artifacts(tmp_path: Path) -> None:
    args = parse_args(
        [
            "--offline",
            "--data",
            str(DEFAULT_DATA_JSON),
            "--example",
            "restaurant_does_not_exist",
            "--results-dir",
            str(tmp_path),
        ]
    )

    with pytest.raises(ValueError, match="Unknown CRAWL example: restaurant_does_not_exist"):
        await run_evals(args)

    assert not await asyncio.to_thread(lambda: any(tmp_path.iterdir()))
