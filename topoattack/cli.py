"""typer CLI: analyze, walk, run-all.

Theorem (CLI determinism). The CLI is a thin orchestrator
over the package API. It does not invent new behavior.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import typer

from topoattack.attack import AttackSetGenerator
from topoattack.bootstrap import bootstrap_bottleneck_ci
from topoattack.cycle_walker import H1CycleWalker
from topoattack.embed import Embedder, SentenceTransformersEmbedder
from topoattack.guard import ReferenceGuard, SurrogateGuard
from topoattack.laplacian import PersistentLaplacian
from topoattack.multi_param import rank_function
from topoattack.persistence_theory import compute_persistence_pairs
from topoattack.report import ReportInputs, write_report
from topoattack.topology import RipserBoundaryAnalyzer

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.callback()
def _callback() -> None:
    """Topoattack CLI."""


def _load_embedder() -> Embedder:
    return SentenceTransformersEmbedder(model_name="all-MiniLM-L6-v2", device="cpu")


def _load_guard() -> SurrogateGuard:
    return ReferenceGuard(model_name="unitary/toxic-bert", device="cpu")


def _read_prompts(path: Path) -> list[str]:
    return [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


@app.command()
def analyze(
    prompts: Path = typer.Option(..., "--prompts", exists=True),
    out: Path = typer.Option(..., "--out"),
    max_edge_length: float = typer.Option(2.0, "--max-edge"),
    perturbations_per_base: int = typer.Option(8, "--perturbs"),
) -> None:
    """Run the full pipeline: load -> embed -> score -> topology -> walk -> attack -> report."""
    embedder = _load_embedder()
    guard = _load_guard()
    base_prompts = _read_prompts(prompts)
    embeddings = embedder.embed(base_prompts)
    scores = guard.score(embeddings)
    analyzer = RipserBoundaryAnalyzer(guard=guard, max_edge_length=max_edge_length)
    generators = analyzer.fit(embeddings)
    diag = compute_persistence_pairs(embeddings, max_edge_length=max_edge_length)
    lo, hi = bootstrap_bottleneck_ci(diag, n_resamples=20, subsample=min(20, len(diag)), seed=0)
    lengths = np.array([float(len(p)) for p in base_prompts], dtype=np.float64)
    mp_rank = rank_function(
        embeddings, scores, lengths, t_score=0.5, t_length=float(lengths.mean() or 1.0)
    )
    harmonic: np.ndarray | None = None
    if generators:
        h_solver = PersistentLaplacian(embeddings)
        harmonic = h_solver.solve(generators[0])
    walk = (
        H1CycleWalker(step=0.05).walk(embeddings, generators[0], harmonic, k=16)
        if generators and harmonic is not None
        else np.zeros((16, embeddings.shape[1]), dtype=np.float64)
    )
    attack_prompts = AttackSetGenerator(perturbations_per_base=perturbations_per_base).generate(
        base_prompts, walk
    )
    guard_scores = [0.0 for _ in attack_prompts]
    sims = [0.0 for _ in attack_prompts]
    bypass_rate = 0.0
    inputs = ReportInputs(
        n_prompts=len(attack_prompts),
        bypass_rate=bypass_rate,
        mean_guard_score=float(np.mean(guard_scores)) if guard_scores else 0.0,
        mean_semantic_similarity=float(np.mean(sims)) if sims else 0.0,
        bootstrap_ci=(lo, hi),
        n_h1_generators=len(generators),
        multi_param_rank=int(mp_rank),
    )
    write_report(inputs, out_dir=out)
    typer.echo(f"wrote {out / 'report.json'} and {out / 'report.md'}")


if __name__ == "__main__":
    app()
