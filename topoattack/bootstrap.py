"""Bootstrap confidence intervals on the bottleneck distance.

Theorem (Efron bootstrap CI). For B resamples with replacement
from a diagram d of size n, the empirical quantiles q_alpha/2
and q_{1 - alpha/2} of the resampled bottleneck distances
form a (1 - alpha)-level confidence interval for the
expected bottleneck distance under the empirical distribution
of d.
"""

from __future__ import annotations

import numpy as np

from topoattack.persistence_theory import bottleneck_distance
from topoattack.types import PersistencePair


def bootstrap_bottleneck_ci(
    diagram: list[PersistencePair],
    n_resamples: int = 100,
    subsample: int | None = None,
    alpha: float = 0.05,
    seed: int = 0,
) -> tuple[float, float]:
    """Return the (alpha/2, 1 - alpha/2) bootstrap CI of d_B(d, d_resample)."""
    if not diagram:
        return (0.0, 0.0)
    if subsample is None:
        subsample = len(diagram)
    rng = np.random.default_rng(seed)
    n = len(diagram)
    stats: list[float] = []
    for _ in range(n_resamples):
        idx = rng.integers(0, n, size=subsample)
        resample = [diagram[int(i)] for i in idx]
        stats.append(bottleneck_distance(diagram, resample))
    lo = float(np.quantile(stats, alpha / 2))
    hi = float(np.quantile(stats, 1 - alpha / 2))
    return (lo, hi)
