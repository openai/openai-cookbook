import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shared.scripts import validate_eval_input as validator


def _write_simulation(
    path: Path,
    *,
    prompt_path: str,
    tools_path: str,
) -> None:
    path.write_text(
        json.dumps(
            {
                "simulation_id": "sim-1",
                "scenario": "Synthetic validation scenario",
                "assistant": {
                    "system_prompt_file": prompt_path,
                    "tools_file": tools_path,
                },
                "simulator": {"system_prompt": "Act as the synthetic user."},
                "audio": {},
                "turns": {"fixed_first_user_turn": "Hello"},
                "tool_mocks": [],
                "expected_tool_call": {},
                "graders": {"turn_level": [], "trace_level": []},
            }
        ),
        encoding="utf-8",
    )


def test_run_input_rejects_simulation_directory(tmp_path: Path) -> None:
    simulation_dir = tmp_path / "simulation-dir"
    simulation_dir.mkdir()
    index_path = tmp_path / "simulations.csv"
    pd.DataFrame(
        [{"simulation_id": "sim-1", "simulation_path": "simulation-dir"}]
    ).to_csv(index_path, index=False)

    with pytest.raises(ValueError, match="simulation_path.*is not a file"):
        validator.validate_run_input(index_path)


def test_simulation_rejects_prompt_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(validator, "ROOT_DIR", tmp_path)
    prompt_dir = tmp_path / "prompt-dir"
    prompt_dir.mkdir()
    (tmp_path / "tools.json").write_text("[]", encoding="utf-8")
    simulation_path = tmp_path / "simulation.json"
    _write_simulation(
        simulation_path,
        prompt_path="prompt-dir",
        tools_path="tools.json",
    )

    with pytest.raises(ValueError, match="system prompt path is not a file"):
        validator._validate_run_simulation_file(
            simulation_path,
            expected_simulation_id="sim-1",
        )


def test_simulation_rejects_tools_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(validator, "ROOT_DIR", tmp_path)
    (tmp_path / "prompt.txt").write_text("System prompt", encoding="utf-8")
    tools_dir = tmp_path / "tools-dir"
    tools_dir.mkdir()
    simulation_path = tmp_path / "simulation.json"
    _write_simulation(
        simulation_path,
        prompt_path="prompt.txt",
        tools_path="tools-dir",
    )

    with pytest.raises(ValueError, match="tools path is not a file"):
        validator._validate_run_simulation_file(
            simulation_path,
            expected_simulation_id="sim-1",
        )


def test_walk_input_rejects_audio_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio_dir = tmp_path / "audio-dir"
    audio_dir.mkdir()
    monkeypatch.setattr(
        validator,
        "load_walk_dataset",
        lambda _: pd.DataFrame(
            [{"audio_path": str(audio_dir), "gt_tool_call_arg": ""}]
        ),
    )

    with pytest.raises(ValueError, match="Audio path is not a file"):
        validator.validate_walk_input(tmp_path / "data.csv")
