"""Theorem (CLI smoke). The CLI 'analyze' subcommand reads a
prompt file, builds a default guard + embedder, fits the
RipserBoundaryAnalyzer, and writes a report to the given
output directory. I test the end-to-end path with a mocked
embedder and a synthetic prompt file.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from click.testing import CliRunner
from typer.main import get_group

from topoattack.cli import app


def test_cli_analyze_smoke(tmp_path: Path, monkeypatch) -> None:
    prompts = tmp_path / "p.txt"
    prompts.write_text("a\nb\nc\nd\ne\n", encoding="utf-8")
    out = tmp_path / "out"
    monkeypatch.setattr("topoattack.cli._load_embedder", lambda: _FakeEmbedder())
    monkeypatch.setattr("topoattack.cli._load_guard", lambda: _FakeGuard())
    runner = CliRunner()
    res = runner.invoke(get_group(app), ["analyze", "--prompts", str(prompts), "--out", str(out)])
    assert res.exit_code == 0
    assert (out / "report.json").exists()


class _FakeEmbedder:
    dim = 3

    def embed(self, texts: list[str]) -> np.ndarray:
        return np.zeros((len(texts), 3), dtype=np.float64)


class _FakeGuard:
    def score(self, emb: np.ndarray) -> np.ndarray:
        return np.full(emb.shape[0], 0.5, dtype=np.float64)
