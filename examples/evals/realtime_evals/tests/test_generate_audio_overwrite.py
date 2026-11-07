"""Offline command-line regressions using real ffmpeg and synthetic PCM."""

import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from walk_harness import generate_audio

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None, reason="ffmpeg is required"
)


@pytest.fixture
def generation(tmp_path, monkeypatch):
    source = tmp_path / "source.csv"
    output_csv = tmp_path / "output.csv"
    output_dir = tmp_path / "audio"
    output_dir.mkdir()
    pd.DataFrame(
        [
            {
                "example_id": "synthetic",
                "user_text": "Synthetic request.",
                "gt_tool_call": "lookup",
                "gt_tool_call_arg": "{}",
            }
        ]
    ).to_csv(source, index=False)
    wav = output_dir / "synthetic.wav"
    synthesized = []
    commands = []
    original_run = subprocess.run

    def tts(client, text, path, model, voice):
        synthesized.append(text)
        # 10 ms of mono PCM16 silence at the existing 24 kHz source rate.
        path.write_bytes(b"\x00\x00" * 240)

    def run(command, **kwargs):
        commands.append(command)
        # Baseline ffmpeg must fail rather than wait for interactive confirmation.
        return original_run(
            command,
            **kwargs,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
        )

    monkeypatch.setattr(generate_audio, "OpenAI", lambda: object())
    monkeypatch.setattr(generate_audio, "tts_to_pcm_file", tts)
    monkeypatch.setattr(generate_audio.subprocess, "run", run)

    def invoke(overwrite):
        argv = [
            "generate_audio.py",
            "--source-csv",
            str(source),
            "--output-dir",
            str(output_dir),
            "--output-csv",
            str(output_csv),
        ]
        if overwrite:
            argv.append("--overwrite")
        monkeypatch.setattr(sys, "argv", argv)
        generate_audio.main()
        result = pd.read_csv(output_csv)
        assert result["audio_path"].tolist() == [str(Path("audio") / "synthetic.wav")]
        assert result["user_text"].tolist() == ["Synthetic request."]
        assert not (output_dir / "synthetic.pcm").exists()

    return wav, synthesized, commands, invoke


@pytest.mark.parametrize("exists", [False, True])
@pytest.mark.parametrize("overwrite", [False, True])
def test_overwrite_flag_controls_existing_audio(generation, exists, overwrite):
    wav, synthesized, commands, invoke = generation
    sentinel = b"Existing synthetic file; no real audio."
    if exists:
        wav.write_bytes(sentinel)
    invoke(overwrite)
    if exists and not overwrite:
        assert wav.read_bytes() == sentinel
        assert synthesized == [] and commands == []
    else:
        assert synthesized == ["Synthetic request."]
        assert len(commands) == 1
        assert wav.read_bytes().startswith(b"RIFF")
        assert b"WAVE" in wav.read_bytes()[:16]


def test_repeat_generation_with_overwrite_does_not_prompt(generation):
    wav, synthesized, commands, invoke = generation
    invoke(True)
    first = wav.read_bytes()
    invoke(True)
    assert wav.read_bytes() == first
    assert len(synthesized) == 2 and len(commands) == 2


def test_repeated_default_run_skips_existing_audio(generation):
    wav, synthesized, commands, invoke = generation
    invoke(False)
    first = wav.read_bytes()
    invoke(False)
    assert wav.read_bytes() == first
    assert len(synthesized) == 1 and len(commands) == 1
