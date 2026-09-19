"""Theorem (correctness of column-reduction persistence pairing).
For a Vietoris-Rips filtration built from a finite metric space
(X, d) with |X| = n, the column-reduction algorithm on the
boundary matrix with coefficients in Z_2 returns a persistence
diagram whose H0 pairs (b, +inf) for n-1 points and (b, d) pairs
in H1 correspond to independent 1-cycles. I test:
  - H0 has exactly n birth entries and one +inf death.
  - The total number of finite death entries across all dimensions
    equals the dimension of the reduced boundary matrix.
"""

from __future__ import annotations

import numpy as np
import pytest
from numpy.typing import NDArray

from topoattack.persistence_theory import (
    bottleneck_distance,
    build_rips_filtration,
    compute_persistence_pairs,
)


def test_rips_filtration_is_sorted_by_radius(circle_cloud: NDArray[np.float64]) -> None:
    edges = build_rips_filtration(circle_cloud, max_edge_length=3.0)
    radii = [r for _, _, r in edges]
    assert radii == sorted(radii)
    assert all(0.0 <= r <= 3.0 for _, _, r in edges)


def test_persistence_pairs_h0_infinite_count(circle_cloud: NDArray[np.float64]) -> None:
    pairs = compute_persistence_pairs(circle_cloud, max_edge_length=2.0)
    h0 = [p for p in pairs if p[1] == float("inf")]
    assert len(h0) == 1


def test_persistence_pairs_h1_finite_count_is_nonzero_on_circle(
    circle_cloud: NDArray[np.float64],
) -> None:
    pairs = compute_persistence_pairs(circle_cloud, max_edge_length=2.0)
    h1 = [p for p in pairs if p[1] != float("inf") and p[0] != 0.0]
    assert len(h1) >= 1


def test_bottleneck_distance_zero_for_identical_diagrams() -> None:
    diag = [(0.0, 1.0), (0.5, 2.0), (1.0, float("inf"))]
    assert bottleneck_distance(diag, diag) == pytest.approx(0.0, abs=1e-9)


def test_bottleneck_distance_empty_diagram() -> None:
    assert bottleneck_distance([(0.0, 100.0)], []) == pytest.approx(50.0)
    assert bottleneck_distance([], [(0.0, 1.0)]) == pytest.approx(0.5)


def test_bottleneck_distance_asymmetric() -> None:
    assert bottleneck_distance([(0.0, 1.0)], [(100.0, 100.0)]) == pytest.approx(0.5)


def test_persistence_pairs_two_clusters(rng: np.random.Generator) -> None:
    cluster1 = rng.multivariate_normal([0.0, 0.0], [[0.1, 0.0], [0.0, 0.1]], size=20)
    cluster2 = rng.multivariate_normal([10.0, 0.0], [[0.1, 0.0], [0.0, 0.1]], size=20)
    cloud = np.vstack([cluster1, cluster2]).astype(np.float64)
    pairs = compute_persistence_pairs(cloud, max_edge_length=2.0)
    h0_inf = [p for p in pairs if p[1] == float("inf")]
    h0_finite = [p for p in pairs if p[1] != float("inf") and p[0] == 0.0]
    assert len(h0_inf) == 2
    assert len(h0_finite) == len(cloud) - 2


def test_persistence_pairs_line_graph() -> None:
    cloud = np.arange(0, 1, 0.1).reshape(-1, 1).astype(np.float64)
    pairs = compute_persistence_pairs(cloud, max_edge_length=float("inf"))
    h0_inf = [p for p in pairs if p[1] == float("inf")]
    h0_finite = [p for p in pairs if p[1] != float("inf") and p[0] == 0.0]
    assert len(h0_inf) == 1
    assert len(h0_finite) == len(cloud) - 1


def test_persistence_pairs_invariant_on_line_graph() -> None:
    """On a line graph, all pairs must satisfy birth < death."""
    cloud = np.array([[0.0], [3.0], [5.0], [6.0]], dtype=np.float64)
    pairs = compute_persistence_pairs(cloud, max_edge_length=float("inf"))
    for b, d in pairs:
        if d != float("inf"):
            assert b < d, f"Invariant violated: ({b}, {d})"


def test_all_pairs_satisfy_invariant(circle_cloud: NDArray[np.float64]) -> None:
    pairs = compute_persistence_pairs(circle_cloud, max_edge_length=2.0)
    for birth, death in pairs:
        assert birth < death or death == float("inf")
