"""Theorem (H1 generator extraction). Given embeddings and a
scalar field, an H1 generator of the superlevel set
{ x : f(x) >= tau } for some threshold tau corresponds to a
high-persistence 1-cycle in the Vietoris-Rips filtration
of the embedding point cloud. I test that the analyzer
returns at least one generator on a noisy circle and zero
generators on a single Gaussian cluster.
"""

from __future__ import annotations

import numpy as np

from topoattack.guard import ReferenceGuard
from topoattack.topology import RipserBoundaryAnalyzer


def test_returns_h1_generators_on_circle(circle_cloud: np.ndarray, ring_score_function) -> None:
    guard = ReferenceGuard(score_fn=ring_score_function)
    analyzer = RipserBoundaryAnalyzer(guard=guard, max_edge_length=2.0)
    gens = analyzer.fit(circle_cloud)
    assert len(gens) >= 1
    assert all(g.persistence >= 0.0 for g in gens)


def test_returns_no_high_persistence_generators_on_cluster(rng: np.random.Generator) -> None:
    cloud = rng.standard_normal((40, 3)).astype(np.float64) * 0.1
    guard = ReferenceGuard(score_fn=lambda x: np.full(x.shape[0], 0.5))
    analyzer = RipserBoundaryAnalyzer(guard=guard, max_edge_length=2.0)
    gens = analyzer.fit(cloud)
    high = [g for g in gens if g.persistence > 0.1]
    assert len(high) == 0
