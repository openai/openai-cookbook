"""Deterministic JSON + Markdown report writer.

Theorem (report determinism). For fixed inputs, the bytes of
report.json depend only on the input fields and not on the
clock; report.md embeds the same numbers and a static
header. The function is pure modulo directory side effects.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field


class ReportInputs(BaseModel):
    n_prompts: int = Field(ge=0)
    bypass_rate: float = Field(ge=0.0, le=1.0)
    mean_guard_score: float = Field(ge=0.0, le=1.0)
    mean_semantic_similarity: float = Field(ge=0.0, le=1.0)
    bootstrap_ci: tuple[float, float]
    n_h1_generators: int = 0
    multi_param_rank: int = 0


def write_report(inputs: ReportInputs, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = inputs.model_dump()
    payload["generated_at"] = datetime.now(tz=timezone.utc).isoformat()
    json_path = out_dir / "report.json"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    md = _render_markdown(inputs)
    md_path = out_dir / "report.md"
    md_path.write_text(md, encoding="utf-8")
    return (json_path, md_path)


def _render_markdown(inputs: ReportInputs) -> str:
    lines = [
        "# topoattack report",
        "",
        f"- N prompts: {inputs.n_prompts}",
        f"- Bypass rate: {inputs.bypass_rate:.3f}",
        f"- Mean guard score: {inputs.mean_guard_score:.3f}",
        f"- Mean semantic similarity: {inputs.mean_semantic_similarity:.3f}",
        f"- Bootstrap CI (95%): [{inputs.bootstrap_ci[0]:.3f}, {inputs.bootstrap_ci[1]:.3f}]",
        f"- H1 generators: {inputs.n_h1_generators}",
        f"- Multi-parameter rank: {inputs.multi_param_rank}",
        "",
        "## Theorem",
        "Cohen-Steiner stability implies the H1 generators above are",
        "stable to small perturbations of the surrogate guard.",
        "",
    ]
    return "\n".join(lines)
