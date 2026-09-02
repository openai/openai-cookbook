"""2-parameter persistence over (score, prompt_length).

Theorem (multi-parameter rank function). For a 2-parameter
filtration f: K -> R^2, the rank function
   rank(t1, t2) = dim H_0(f^{-1}(-inf, t1] x (-inf, t2])
is upper semi-continuous and monotone non-increasing in each
argument. I compute rank via a single-linkage union-find on
points satisfying the threshold.
"""

from __future__ import annotations

from topoattack.persistence_theory import build_rips_filtration
from topoattack.types import PointCloud, ScalarField


def rank_function(
    cloud: PointCloud,
    scores: ScalarField,
    lengths: ScalarField,
    t_score: float,
    t_length: float,
    max_edge_length: float = 2.0,
) -> int:
    """Return H0 rank of the sublevel set { (score <= t_score, length <= t_length) }."""
    keep = (scores <= t_score) & (lengths <= t_length)
    if not keep.any():
        return 0
    sub = cloud[keep]
    edges = build_rips_filtration(sub, max_edge_length=max_edge_length)
    parent = list(range(sub.shape[0]))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for (i, j), _, _ in edges:
        union(i, j)
    roots = {find(i) for i in range(sub.shape[0])}
    return len(roots)
