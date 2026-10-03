import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shared.scripts.validate_eval_output import _required_intish, _validate_run_results


def test_summary_integer_field_rejects_fractional_float(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="sample_rate_hz.*must be an integer"):
        _required_intish(
            {"sample_rate_hz": 24_000.5},
            "sample_rate_hz",
            tmp_path / "summary.json",
        )


def test_summary_integer_field_accepts_integer_string(tmp_path: Path) -> None:
    assert (
        _required_intish(
            {"sample_rate_hz": "24000"},
            "sample_rate_hz",
            tmp_path / "summary.json",
        )
        == 24_000
    )


def test_run_turn_index_rejects_fractional_float(tmp_path: Path) -> None:
    results = pd.DataFrame(
        [
            {
                "simulation_id": "sim-1",
                "assistant_model": "assistant-model",
                "simulator_model": "simulator-model",
                "turn_index": 1.5,
                "user_text": "hello",
                "assistant_text": "hi",
                "tool_calls": "[]",
                "tool_outputs": "[]",
                "user_audio_path": "",
                "assistant_audio_path": "",
                "event_log_path": "",
                "status": "failed",
            }
        ]
    )

    with pytest.raises(ValueError, match="turn_index.*must be an integer"):
        _validate_run_results(results, tmp_path / "results.csv")
