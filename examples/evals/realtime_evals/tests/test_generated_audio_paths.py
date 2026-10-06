"""Offline path roundtrips for configurable walk-harness output locations."""

import argparse
import os
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from walk_harness import generate_audio


@pytest.mark.parametrize("layout", ["nested", "sibling", "parent", "same_directory"])
@pytest.mark.parametrize("path_mode", ["relative", "absolute", "mixed", "csv_absolute"])
@pytest.mark.parametrize("existing", [False, True])
def test_generated_manifest_resolves_to_requested_audio(
    tmp_path, monkeypatch, layout, path_mode, existing
):
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "source.csv"
    pd.DataFrame(
        [
            {
                "example_id": "synthetic",
                "user_text": "Synthetic request.",
                "gt_tool_call": "lookup",
                "gt_tool_call_arg": "{}",
                "expected_keywords": "unused",
            }
        ]
    ).to_csv(source, index=False)
    layouts = {
        "nested": ("results/audio", "results/manifest.csv"),
        "sibling": ("audio", "results/manifest.csv"),
        "parent": ("audio", "audio/manifests/manifest.csv"),
        "same_directory": ("results", "results/manifest.csv"),
    }
    audio_name, csv_name = layouts[layout]
    audio_dir, output_csv = Path(audio_name), Path(csv_name)
    if path_mode in ("absolute", "mixed"):
        audio_dir = tmp_path / audio_dir
    if path_mode in ("absolute", "csv_absolute"):
        output_csv = tmp_path / output_csv
    target = (audio_dir / "synthetic.wav").resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if existing:
        target.write_bytes(b"Existing synthetic audio fixture")
    calls = []

    def synthesize(client, text, output, model, voice):
        calls.append((text, model, voice))
        output.write_bytes(b"Synthetic PCM fixture")

    def encode(input_path, output_path, input_sample_rate_hz, target_sample_rate_hz):
        assert input_path.read_bytes() == b"Synthetic PCM fixture"
        output_path.write_bytes(b"Generated synthetic audio fixture")

    args = argparse.Namespace(
        source_csv=source,
        output_dir=audio_dir,
        output_csv=output_csv,
        tts_model="synthetic-model",
        voice="synthetic-voice",
        tts_sample_rate_hz=24000,
        target_sample_rate_hz=8000,
        overwrite=False,
    )
    monkeypatch.setattr(generate_audio, "parse_args", lambda: args)
    monkeypatch.setattr(generate_audio, "OpenAI", lambda: object())
    monkeypatch.setattr(generate_audio, "tts_to_pcm_file", synthesize)
    monkeypatch.setattr(generate_audio, "encode_pcm_to_ulaw_wav", encode)
    generate_audio.main()

    manifest = pd.read_csv(output_csv)
    relative = manifest.loc[0, "audio_path"]
    assert not Path(relative).is_absolute()
    assert (output_csv.parent / relative).resolve() == target
    assert relative == os.path.relpath(target, output_csv.parent.resolve())
    assert manifest.loc[0, "example_id"] == "synthetic"
    assert manifest.loc[0, "user_text"] == "Synthetic request."
    assert "expected_keywords" not in manifest.columns
    assert len(calls) == (0 if existing else 1)
    assert target.read_bytes() == (
        b"Existing synthetic audio fixture"
        if existing
        else b"Generated synthetic audio fixture"
    )
    assert not (audio_dir / "synthetic.pcm").exists()
