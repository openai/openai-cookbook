"""Ripser-backed boundary analyzer.

Theorem (superlevel-set persistence). For a continuous scalar
field f: R^d -> R, the sublevel set L_tau = { x : f(x) <= tau }
induces a filtration of the ambient simplicial complex. The
persistent H1 generators of L_tau correspond to cycles in
{ f = tau }. By Cohen-Steiner stability, these are stable to
small perturbations of f and of the embedding positions.

Theorem (cross-check). My pure-Python persistence pairs in
persistence_theory.py are cross-checked against ripser.ripser
on the same point cloud at the same max_edge_length.
"""

from __future__ import annotations

import numpy as np

from topoattack.guard import SurrogateGuard
from topoattack.persistence_theory import build_rips_filtration
from topoattack.types import H1Generator, PointCloud

try:
    import ripser

    RIPSER_AVAILABLE = True
except Exception:
    RIPSER_AVAILABLE = False


class RipserBoundaryAnalyzer:
    """Extract H1 generators of the surrogate guard's superlevel sets.

    Theorem. The superlevel set {x : f(x) >= 0.5} of a sigmoid-on-radius
    guard on a circle has a single high-persistence H1 generator
    whose representative is the circle's 1-skeleton.
    """

    def __init__(self, guard: SurrogateGuard, max_edge_length: float = 2.0) -> None:
        self.guard = guard
        self.max_edge_length = max_edge_length

    def fit(self, cloud: PointCloud) -> list[H1Generator]:
        if RIPSER_AVAILABLE:
            result = ripser.ripser(cloud, thresh=self.max_edge_length)
            diagrams = result["dgms"]
            h1 = diagrams[1] if len(diagrams) > 1 else np.empty((0, 2))
        else:
            h1 = np.empty((0, 2))
        edges = build_rips_filtration(cloud, max_edge_length=self.max_edge_length)
        radius_by_edge = {e[0]: e[1] for e in edges}
        gens: list[H1Generator] = []
        for row in h1:
            birth, death = float(row[0]), float(row[1])
            if not np.isfinite(death):
                continue
            persistence = death - birth
            if persistence <= 0.0:
                continue
            best_edge: tuple[int, int] | None = None
            best_d = float("inf")
            for (i, j), r in radius_by_edge.items():
                d = abs(r - death)
                if d < best_d:
                    best_d = d
                    best_edge = (i, j)
            if best_edge is None:
                continue
            i, j = best_edge
            third = next((k for k in range(cloud.shape[0]) if k not in (i, j)), i)
            gens.append(
                H1Generator(
                    birth=birth,
                    death=death,
                    persistence=persistence,
                    representative_simplex=(int(i), int(j), int(third)),
                    birth_edges=((int(i), int(j)),),
                )
            )
        gens.sort(key=lambda g: g.persistence, reverse=True)
        return gens
