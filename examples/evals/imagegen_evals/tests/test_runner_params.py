import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from vision_harness.runners import _positive_int_param


def test_positive_int_param_accepts_integer_and_integer_string() -> None:
    assert _positive_int_param(1, name="n") == 1
    assert _positive_int_param(4, name="n") == 4
    assert _positive_int_param("2", name="n") == 2


def test_positive_int_param_rejects_fractional_and_boolean_values() -> None:
    for value in (1.5, "1.5", True, False):
        try:
            _positive_int_param(value, name="n")
        except ValueError as exc:
            assert "positive integer" in str(exc)
        else:
            raise AssertionError(f"Expected {value!r} to be rejected")


def test_positive_int_param_rejects_non_positive_values() -> None:
    for value in (0, -1, "0"):
        try:
            _positive_int_param(value, name="n")
        except ValueError as exc:
            assert "positive integer" in str(exc)
        else:
            raise AssertionError(f"Expected {value!r} to be rejected")
