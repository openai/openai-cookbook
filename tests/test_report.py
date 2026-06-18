"""Theorem (deterministic report). The report writer is a pure
function: same input -> same JSON bytes and same Markdown
bytes modulo timestamp. I test that both files exist after
write and that the Markdown contains the bypass-rate line.
"""

from __future__ import annotations

from pathlib import Path

from topoattack.report import ReportInputs, write_report


def test_write_report_creates_files(tmp_path: Path) -> None:
    inputs = ReportInputs(
        n_prompts=8,
        bypass_rate=0.25,
        mean_guard_score=0.4,
        mean_semantic_similarity=0.9,
        bootstrap_ci=(0.0, 0.1),
    )
    write_report(inputs, out_dir=tmp_path)
    assert (tmp_path / "report.json").exists()
    assert (tmp_path / "report.md").exists()
    text = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "Bypass rate" in text
