import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shared.reporting import default_run_id


def test_default_run_id_is_unique_for_rapid_runs() -> None:
    first = default_run_id("")
    second = default_run_id("")

    assert first != second


def test_default_run_id_preserves_explicit_name() -> None:
    assert default_run_id("comparison-run") == "comparison-run"
