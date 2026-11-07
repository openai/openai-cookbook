"""Regression for validating forced bootstrap inputs before overwriting files."""

import importlib.util
import sys
from pathlib import Path

import pytest


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "bootstrap-realtime-eval"
    / "scripts"
    / "bootstrap_realtime_eval.py"
)


def test_invalid_tool_mocks_do_not_delete_forced_output(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("realtime_bootstrap_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    bootstrap = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bootstrap)

    monkeypatch.setattr(bootstrap, "HARNESS_ROOT", tmp_path)
    target = tmp_path / "existing_eval"
    target.mkdir()
    original_file = target / "keep.txt"
    original_file.write_text("existing content\n", encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(SCRIPT),
            "--name",
            "existing",
            "--harness",
            "run",
            "--output-dir",
            str(target),
            "--tool-mocks-json",
            '[{"name": "valid"}, null]',
            "--force",
        ],
    )
    with pytest.raises(ValueError, match="array of objects"):
        bootstrap.main()

    assert original_file.read_text(encoding="utf-8") == "existing content\n"
    assert sorted(path.name for path in target.iterdir()) == ["keep.txt"]
