import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shared.path_utils import (
    InvalidPathComponentError,
    resolve_safe_path,
    validate_safe_path_component,
)


@pytest.mark.parametrize(
    "component",
    [
        "../../escaped",
        "..",
        "nested/../escape",
        "has/slash",
        "has\\backslash",
        "C:drive",
        "/absolute",
        "   ",
        "",
    ],
)
def test_validate_safe_path_component_rejects_unsafe_values(component: str) -> None:
    with pytest.raises(InvalidPathComponentError):
        validate_safe_path_component(component, "example_id")


@pytest.mark.parametrize("reserved", ["CON", "prn", "AUX", "COM1", "LPT9"])
def test_validate_safe_path_component_rejects_windows_reserved_names(
    reserved: str,
) -> None:
    with pytest.raises(InvalidPathComponentError):
        validate_safe_path_component(reserved, "example_id")


def test_validate_safe_path_component_rejects_none() -> None:
    with pytest.raises(InvalidPathComponentError):
        validate_safe_path_component(None, "example_id")  # type: ignore[arg-type]


def test_validate_safe_path_component_accepts_ordinary_ids() -> None:
    assert validate_safe_path_component(" example_001 ", "example_id") == "example_001"
    assert validate_safe_path_component("sim-2026.09.24", "simulation_id") == (
        "sim-2026.09.24"
    )


def test_resolve_safe_path_accepts_path_within_base(tmp_path: Path) -> None:
    resolved = resolve_safe_path("audio/example_001.wav", tmp_path)
    assert resolved == (tmp_path / "audio" / "example_001.wav").resolve()


def test_resolve_safe_path_rejects_traversal_out_of_base(tmp_path: Path) -> None:
    with pytest.raises(InvalidPathComponentError):
        resolve_safe_path("../../outside.wav", tmp_path)


def test_resolve_safe_path_rejects_nested_traversal_out_of_base(
    tmp_path: Path,
) -> None:
    with pytest.raises(InvalidPathComponentError):
        resolve_safe_path("audio/../../../escaped.wav", tmp_path)


def test_resolve_safe_path_rejects_empty_value(tmp_path: Path) -> None:
    with pytest.raises(InvalidPathComponentError):
        resolve_safe_path("", tmp_path)
    with pytest.raises(InvalidPathComponentError):
        resolve_safe_path("   ", tmp_path)


def test_resolve_safe_path_preserves_absolute_paths(tmp_path: Path) -> None:
    absolute = tmp_path / "outside" / "simulation.json"
    resolved = resolve_safe_path(str(absolute), tmp_path / "data")
    assert resolved == absolute.resolve()
